"""
SPADE multi-agent system for LMS with orchestrator architecture.

Architecture:
  OrchestratorAgent (central coordinator)
      |
      +-- MonitoringAgent   – periodically analyses student performance,
      |                       sends events to Orchestrator.
      +-- AdaptationAgent   – generates AI-powered personalised
      |                       recommendations on Orchestrator's command.
      +-- NotificationAgent – persists alerts for teachers on
                              Orchestrator's command.

All inter-agent communication goes through the OrchestratorAgent.
Agents never communicate directly with each other.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message

import ai_service
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
#  OrchestratorAgent  (central coordinator)
# ===================================================================

class OrchestratorAgent(Agent):
    """Central coordinator that receives events from all agents,
    makes decisions, and dispatches tasks."""

    class DispatchBehaviour(CyclicBehaviour):
        """Listen for incoming messages and route them."""

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            try:
                data = json.loads(msg.body)
            except (json.JSONDecodeError, TypeError):
                log.warning("[Orchestrator] Received unparseable message: %s", msg.body)
                return

            event_type = data.get("type")
            log.info(
                "[Orchestrator] Received event '%s' from %s",
                event_type, msg.sender,
            )

            # Log the decision
            self._log_event(event_type, str(msg.sender), data)

            # --- Routing logic ---
            if event_type == "student_risk":
                await self._handle_student_risk(data)

            elif event_type == "recommendations_ready":
                await self._handle_recommendations_ready(data)

            elif event_type == "adaptation_analysis":
                await self._handle_adaptation_analysis(data)

            else:
                log.info("[Orchestrator] Unknown event type '%s', ignoring.", event_type)

        async def _handle_student_risk(self, data: dict):
            """MonitoringAgent detected an at-risk student.
            Orchestrator decides: request AI adaptation + send notification."""
            student_id = data["student_id"]
            student_name = data.get("student_name", "")
            score = data.get("score", 0)
            severity = data.get("severity", "warning")

            self._log_decision(
                "student_risk", "monitoring", student_id,
                f"Score={score}%, dispatching to adaptation and notification",
            )

            # 1) Ask AdaptationAgent to generate AI recommendations
            adapt_msg = Message(
                to=config.XMPP_AGENTS["adaptation"]["jid"],
                body=json.dumps({
                    "type": "generate_recommendations",
                    "student_id": student_id,
                    "student_name": student_name,
                    "score": score,
                }),
            )
            adapt_msg.set_metadata("performative", "request")
            await self.send(adapt_msg)

            # 2) Ask NotificationAgent to create an alert
            notify_msg = Message(
                to=config.XMPP_AGENTS["notification"]["jid"],
                body=json.dumps({
                    "type": "create_alert",
                    "student_id": student_id,
                    "student_name": student_name,
                    "score": score,
                    "severity": severity,
                }),
            )
            notify_msg.set_metadata("performative", "request")
            await self.send(notify_msg)

        async def _handle_recommendations_ready(self, data: dict):
            """AdaptationAgent finished generating recommendations.
            Orchestrator can trigger further actions if needed."""
            student_id = data.get("student_id")
            count = data.get("recommendations_count", 0)
            ai_used = data.get("ai_used", False)

            self._log_decision(
                "recommendations_ready", "adaptation", student_id,
                f"Generated {count} recommendations (AI={'yes' if ai_used else 'no'})",
            )
            log.info(
                "[Orchestrator] %d recommendations ready for student %s (AI=%s)",
                count, student_id, ai_used,
            )

        async def _handle_adaptation_analysis(self, data: dict):
            """AdaptationAgent completed an error-pattern analysis."""
            student_id = data.get("student_id")
            suggested_difficulty = data.get("suggested_difficulty", 1)

            self._log_decision(
                "adaptation_analysis", "adaptation", student_id,
                f"Suggested difficulty={suggested_difficulty}",
            )

        def _log_event(self, event_type: str, source: str, data: dict):
            """Persist an orchestrator log entry."""
            try:
                with _app_context():
                    from models import OrchestratorLog, db
                    entry = OrchestratorLog(
                        event_type=event_type or "unknown",
                        source_agent=source,
                        student_id=data.get("student_id"),
                        payload=json.dumps(data, ensure_ascii=False),
                    )
                    db.session.add(entry)
                    db.session.commit()
            except Exception as exc:
                log.error("[Orchestrator] Failed to log event: %s", exc)

        def _log_decision(self, event_type: str, target: str, student_id, decision: str):
            try:
                with _app_context():
                    from models import OrchestratorLog, db
                    entry = OrchestratorLog(
                        event_type=event_type,
                        source_agent="orchestrator",
                        target_agent=target,
                        student_id=student_id,
                        decision=decision,
                    )
                    db.session.add(entry)
                    db.session.commit()
            except Exception as exc:
                log.error("[Orchestrator] Failed to log decision: %s", exc)

    async def setup(self):
        log.info("[OrchestratorAgent] Starting …")
        self.add_behaviour(self.DispatchBehaviour())


# ===================================================================
#  MonitoringAgent
# ===================================================================

class MonitoringAgent(Agent):
    """Periodically scans student results and sends risk events
    to the OrchestratorAgent."""

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
                        # Avoid duplicate reports within the last hour
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

                        # Send event to OrchestratorAgent (NOT directly to other agents)
                        orchestrator_msg = Message(
                            to=config.XMPP_AGENTS["orchestrator"]["jid"],
                            body=json.dumps({
                                "type": "student_risk",
                                "student_id": student.id,
                                "student_name": student.full_name or student.username,
                                "score": score,
                                "recent_score": recent_score,
                                "severity": severity,
                            }),
                        )
                        orchestrator_msg.set_metadata("performative", "inform")
                        await self.send(orchestrator_msg)

                db.session.commit()
            log.info("[MonitoringAgent] Monitoring cycle complete.")

    async def setup(self):
        log.info("[MonitoringAgent] Starting …")
        behaviour = self.MonitorBehaviour(period=config.MONITORING_PERIOD)
        self.add_behaviour(behaviour)


# ===================================================================
#  AdaptationAgent  (AI-powered)
# ===================================================================

class AdaptationAgent(Agent):
    """Generates AI-powered personalised recommendations.
    Listens for commands from the OrchestratorAgent."""

    class ListenBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            try:
                data = json.loads(msg.body)
            except (json.JSONDecodeError, TypeError):
                return

            if data.get("type") == "generate_recommendations":
                await self._generate_recommendations(data)
            elif data.get("type") == "analyze_errors":
                await self._analyze_errors(data)

        async def _generate_recommendations(self, data: dict):
            student_id = data["student_id"]
            student_name = data.get("student_name", "")
            score = data.get("score", 0)

            log.info(
                "[AdaptationAgent] Generating AI recommendations for student %s (score=%s%%)",
                student_id, score,
            )

            recommendations_count = 0
            ai_used = config.AI_ENABLED

            with _app_context():
                from models import AdaptationLog, StudentAnswer, Topic, db

                # Find per-topic stats
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
                            weak_topics.append((topic, round(pct, 1), st["total"], st["correct"]))

                if weak_topics:
                    for topic, pct, total, correct in weak_topics:
                        # Use AI to generate personalised recommendation
                        rec_text = ai_service.generate_recommendation(
                            student_name=student_name,
                            topic_title=topic.title,
                            score_pct=pct,
                            total_answers=total,
                            correct_answers=correct,
                        )
                        adaptation = AdaptationLog(
                            student_id=student_id,
                            topic_id=topic.id,
                            recommendation=rec_text,
                            ai_generated=ai_used,
                        )
                        db.session.add(adaptation)
                        recommendations_count += 1
                else:
                    if score < config.RISK_SCORE_THRESHOLD:
                        adaptation = AdaptationLog(
                            student_id=student_id,
                            recommendation=ai_service.generate_recommendation(
                                student_name=student_name,
                                topic_title="общая программа",
                                score_pct=score,
                                total_answers=len(answers),
                                correct_answers=sum(1 for a in answers if a.is_correct),
                            ),
                            ai_generated=ai_used,
                        )
                        db.session.add(adaptation)
                        recommendations_count += 1

                db.session.commit()

            # Notify orchestrator that recommendations are ready
            reply = Message(
                to=config.XMPP_AGENTS["orchestrator"]["jid"],
                body=json.dumps({
                    "type": "recommendations_ready",
                    "student_id": student_id,
                    "recommendations_count": recommendations_count,
                    "ai_used": ai_used,
                }),
            )
            reply.set_metadata("performative", "inform")
            await self.send(reply)

        async def _analyze_errors(self, data: dict):
            """Run AI error-pattern analysis for a student."""
            student_id = data["student_id"]
            student_name = data.get("student_name", "")

            log.info("[AdaptationAgent] Analysing error patterns for student %s", student_id)

            with _app_context():
                from models import StudentAnswer, Topic

                answers = StudentAnswer.query.filter_by(student_id=student_id).all()
                topic_stats: dict[int, dict] = {}
                for a in answers:
                    t = topic_stats.setdefault(a.topic_id, {"total": 0, "correct": 0})
                    t["total"] += 1
                    t["correct"] += int(a.is_correct)

                topic_results = []
                for tid, st in topic_stats.items():
                    topic = Topic.query.get(tid)
                    pct = st["correct"] / st["total"] * 100 if st["total"] else 0
                    topic_results.append({
                        "topic_title": topic.title if topic else f"Topic {tid}",
                        "total": st["total"],
                        "correct": st["correct"],
                        "pct": round(pct, 1),
                    })

            analysis = ai_service.analyze_error_patterns(student_name, topic_results)

            # Send analysis to orchestrator
            reply = Message(
                to=config.XMPP_AGENTS["orchestrator"]["jid"],
                body=json.dumps({
                    "type": "adaptation_analysis",
                    "student_id": student_id,
                    **analysis,
                }),
            )
            reply.set_metadata("performative", "inform")
            await self.send(reply)

    class PeriodicAdaptBehaviour(PeriodicBehaviour):
        """Proactively scan all students and send risk events to orchestrator."""

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

                        rec = ai_service.generate_recommendation(
                            student_name=student.full_name or student.username,
                            topic_title=topic.title,
                            score_pct=round(pct, 1),
                            total_answers=st["total"],
                            correct_answers=st["correct"],
                        )
                        db.session.add(AdaptationLog(
                            student_id=student.id,
                            topic_id=topic.id,
                            recommendation=rec,
                            ai_generated=config.AI_ENABLED,
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
    """Listens for alert commands from OrchestratorAgent and persists
    them as teacher-visible reports."""

    class ListenBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)
            if msg is None:
                return

            try:
                data = json.loads(msg.body)
            except (json.JSONDecodeError, TypeError):
                return

            if data.get("type") != "create_alert":
                return

            log.info(
                "[NotificationAgent] Creating alert for student %s",
                data.get("student_name"),
            )

            with _app_context():
                from models import AgentReport, db

                report = AgentReport(
                    agent_type="notification",
                    student_id=data.get("student_id"),
                    message=(
                        f"Уведомление: студент «{data.get('student_name')}» "
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
    """Instantiate and start all SPADE agents (orchestrator first)."""
    global _agents

    orchestrator = OrchestratorAgent(
        config.XMPP_AGENTS["orchestrator"]["jid"],
        config.XMPP_AGENTS["orchestrator"]["password"],
    )
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

    # Start orchestrator first so it is ready to receive messages
    _agents = [orchestrator, monitoring, adaptation, notification]

    for agent in _agents:
        await agent.start(auto_register=True)
        log.info("Agent %s started.", agent.jid)


async def stop_agents():
    for agent in _agents:
        await agent.stop()
        log.info("Agent %s stopped.", agent.jid)
