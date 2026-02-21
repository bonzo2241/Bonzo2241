"""
SPADE multi-agent system for LMS.

Agents:
  1. MonitoringAgent  – periodically analyses student performance,
                        detects at-risk students.
  2. AdaptationAgent  – generates personalised recommendations and
                        adjusts suggested difficulty.
  3. NotificationAgent – receives messages from other agents and
                         persists alerts for teachers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message

import config

log = logging.getLogger("lms.agents")


# ---------------------------------------------------------------------------
#  Helper: access the DB from inside an agent (needs app context)
# ---------------------------------------------------------------------------

_flask_app = None  # will be set from run.py


def set_flask_app(app):
    global _flask_app
    _flask_app = app


def _app_context():
    """Return the Flask app context so agents can use SQLAlchemy."""
    if _flask_app is None:
        raise RuntimeError("Flask app not registered with agents module")
    return _flask_app.app_context()


# ===================================================================
#  MonitoringAgent
# ===================================================================

class MonitoringAgent(Agent):
    """Periodically scans student results and flags at-risk students."""

    class MonitorBehaviour(PeriodicBehaviour):
        async def run(self):
            log.info("[MonitoringAgent] Running monitoring cycle …")
            with _app_context():
                from models import AgentReport, StudentAnswer, User, db

                students = User.query.filter_by(role="student").all()
                for student in students:
                    answers = StudentAnswer.query.filter_by(student_id=student.id).all()
                    if not answers:
                        continue

                    total = len(answers)
                    correct = sum(1 for a in answers if a.is_correct)
                    score = round(correct / total * 100, 1)

                    # Check recent performance (last 24h)
                    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
                    recent = [a for a in answers if a.created_at >= recent_cutoff]
                    recent_score = None
                    if recent:
                        recent_correct = sum(1 for a in recent if a.is_correct)
                        recent_score = round(recent_correct / len(recent) * 100, 1)

                    if score < config.RISK_SCORE_THRESHOLD:
                        # Check if we already reported in last hour
                        last_report = (
                            AgentReport.query
                            .filter_by(agent_type="monitoring", student_id=student.id)
                            .order_by(AgentReport.created_at.desc())
                            .first()
                        )
                        if last_report and last_report.created_at > datetime.utcnow() - timedelta(hours=1):
                            continue

                        severity = "danger" if score < 30 else "warning"
                        msg_text = (
                            f"Студент «{student.full_name or student.username}» "
                            f"имеет общий балл {score}% ({correct}/{total})."
                        )
                        if recent_score is not None:
                            msg_text += f" За последние 24 ч: {recent_score}%."

                        report = AgentReport(
                            agent_type="monitoring",
                            student_id=student.id,
                            message=msg_text,
                            severity=severity,
                        )
                        db.session.add(report)

                        # Notify the NotificationAgent via XMPP
                        xmpp_msg = Message(
                            to=config.XMPP_AGENTS["notification"]["jid"],
                            body=json.dumps({
                                "type": "risk_alert",
                                "student_id": student.id,
                                "student_name": student.full_name or student.username,
                                "score": score,
                                "severity": severity,
                            }),
                        )
                        xmpp_msg.set_metadata("performative", "inform")
                        await self.send(xmpp_msg)

                        # Also ask the adaptation agent to create recommendations
                        adapt_msg = Message(
                            to=config.XMPP_AGENTS["adaptation"]["jid"],
                            body=json.dumps({
                                "type": "adapt_request",
                                "student_id": student.id,
                                "score": score,
                            }),
                        )
                        adapt_msg.set_metadata("performative", "request")
                        await self.send(adapt_msg)

                db.session.commit()
            log.info("[MonitoringAgent] Monitoring cycle complete.")

    async def setup(self):
        log.info("[MonitoringAgent] Starting …")
        behaviour = self.MonitorBehaviour(period=config.MONITORING_PERIOD)
        self.add_behaviour(behaviour)


# ===================================================================
#  AdaptationAgent
# ===================================================================

class AdaptationAgent(Agent):
    """Receives adapt_request messages and generates recommendations."""

    class ListenBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            try:
                data = json.loads(msg.body)
            except (json.JSONDecodeError, TypeError):
                return

            if data.get("type") != "adapt_request":
                return

            student_id = data["student_id"]
            score = data["score"]

            log.info(
                "[AdaptationAgent] Generating recommendations for student %s (score=%s)",
                student_id, score,
            )

            with _app_context():
                from models import AdaptationLog, StudentAnswer, Topic, db

                # Find weak topics
                answers = StudentAnswer.query.filter_by(student_id=student_id).all()
                topic_stats: dict[int, dict] = {}
                for a in answers:
                    t = topic_stats.setdefault(a.topic_id, {"total": 0, "correct": 0})
                    t["total"] += 1
                    t["correct"] += int(a.is_correct)

                weak_topics = []
                for tid, st in topic_stats.items():
                    pct = st["correct"] / st["total"] * 100 if st["total"] else 0
                    if pct < config.RISK_SCORE_THRESHOLD:
                        topic = Topic.query.get(tid)
                        if topic:
                            weak_topics.append((topic, round(pct, 1)))

                if weak_topics:
                    for topic, pct in weak_topics:
                        rec_text = (
                            f"Рекомендуется повторить тему «{topic.title}» "
                            f"(текущий результат: {pct}%). "
                        )
                        if pct < 30:
                            rec_text += "Рекомендуется начать с более простых материалов."
                        elif pct < 50:
                            rec_text += "Попробуйте пройти тему ещё раз, обращая внимание на пояснения."

                        adaptation = AdaptationLog(
                            student_id=student_id,
                            topic_id=topic.id,
                            recommendation=rec_text,
                        )
                        db.session.add(adaptation)
                else:
                    if score < config.RISK_SCORE_THRESHOLD:
                        adaptation = AdaptationLog(
                            student_id=student_id,
                            recommendation=(
                                "Общий балл ниже порога. "
                                "Рекомендуется пройти все доступные темы повторно."
                            ),
                        )
                        db.session.add(adaptation)

                db.session.commit()

    class PeriodicAdaptBehaviour(PeriodicBehaviour):
        """Proactively scan all students and generate recommendations."""

        async def run(self):
            log.info("[AdaptationAgent] Running periodic adaptation scan …")
            with _app_context():
                from models import AdaptationLog, StudentAnswer, Topic, User, db

                students = User.query.filter_by(role="student").all()
                for student in students:
                    answers = StudentAnswer.query.filter_by(student_id=student.id).all()
                    if not answers:
                        continue

                    topic_stats: dict[int, dict] = {}
                    for a in answers:
                        t = topic_stats.setdefault(a.topic_id, {"total": 0, "correct": 0})
                        t["total"] += 1
                        t["correct"] += int(a.is_correct)

                    for tid, st in topic_stats.items():
                        pct = st["correct"] / st["total"] * 100 if st["total"] else 0
                        if pct >= config.RISK_SCORE_THRESHOLD:
                            continue

                        # Don't duplicate recent recommendations
                        existing = (
                            AdaptationLog.query
                            .filter_by(student_id=student.id, topic_id=tid)
                            .order_by(AdaptationLog.created_at.desc())
                            .first()
                        )
                        if existing and existing.created_at > datetime.utcnow() - timedelta(hours=2):
                            continue

                        topic = Topic.query.get(tid)
                        if not topic:
                            continue

                        rec = (
                            f"Студенту «{student.full_name or student.username}» "
                            f"рекомендуется повторить тему «{topic.title}» "
                            f"(результат: {round(pct, 1)}%)."
                        )
                        db.session.add(AdaptationLog(
                            student_id=student.id,
                            topic_id=topic.id,
                            recommendation=rec,
                        ))

                db.session.commit()
            log.info("[AdaptationAgent] Periodic adaptation scan complete.")

    async def setup(self):
        log.info("[AdaptationAgent] Starting …")
        self.add_behaviour(self.ListenBehaviour())
        self.add_behaviour(self.PeriodicAdaptBehaviour(period=config.ADAPTATION_PERIOD))


# ===================================================================
#  NotificationAgent
# ===================================================================

class NotificationAgent(Agent):
    """Listens for alert messages and persists them as teacher-visible reports."""

    class ListenBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            try:
                data = json.loads(msg.body)
            except (json.JSONDecodeError, TypeError):
                return

            if data.get("type") != "risk_alert":
                return

            log.info(
                "[NotificationAgent] Received risk alert for student %s",
                data.get("student_name"),
            )

            with _app_context():
                from models import AgentReport, db

                report = AgentReport(
                    agent_type="notification",
                    student_id=data.get("student_id"),
                    message=(
                        f"⚠ Уведомление: студент «{data.get('student_name')}» "
                        f"находится в зоне риска (балл: {data.get('score')}%)."
                    ),
                    severity=data.get("severity", "warning"),
                )
                db.session.add(report)
                db.session.commit()

    async def setup(self):
        log.info("[NotificationAgent] Starting …")
        self.add_behaviour(self.ListenBehaviour())


# ===================================================================
#  Convenience: start / stop all agents
# ===================================================================

_agents: list[Agent] = []


async def start_agents():
    """Instantiate and start all three SPADE agents."""
    global _agents

    monitoring = MonitoringAgent(
        config.XMPP_AGENTS["monitoring"]["jid"],
        config.XMPP_AGENTS["monitoring"]["password"],
    )
    adaptation = AdaptationAgent(
        config.XMPP_AGENTS["adaptation"]["jid"],
        config.XMPP_AGENTS["adaptation"]["password"],
    )
    notification = NotificationAgent(
        config.XMPP_AGENTS["notification"]["jid"],
        config.XMPP_AGENTS["notification"]["password"],
    )

    _agents = [monitoring, adaptation, notification]

    for agent in _agents:
        await agent.start(auto_register=True)
        log.info("Agent %s started.", agent.jid)


async def stop_agents():
    for agent in _agents:
        await agent.stop()
        log.info("Agent %s stopped.", agent.jid)
