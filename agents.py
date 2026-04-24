"""
OpenClaw multi-agent system for LMS with orchestrator architecture.

Architecture:
  OrchestratorAgent (central coordinator)
      |
      +-- MonitoringAgent   – periodically analyses student performance,
      |                       sends events to Orchestrator via asyncio Queue.
      +-- AdaptationAgent   – generates AI-powered personalised
      |                       recommendations on Orchestrator's command.
      +-- NotificationAgent – persists alerts for teachers on
                              Orchestrator's command.

All inter-agent communication goes through the OrchestratorAgent.
Agents communicate via asyncio Queues — no XMPP server required.
OpenClaw client connects to the local gateway (default: localhost:18789).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

import ai_service
import config
from agent_transport import LocalQueueTransport, OpenClawTransport
from contracts.events import (
    CMD_ANALYZE_ERRORS,
    CMD_CREATE_ALERT,
    CMD_GENERATE_RECOMMENDATIONS,
    EVENT_ADAPTATION_ANALYSIS,
    EVENT_RECOMMENDATIONS_READY,
    EVENT_STUDENT_RISK,
)

log = logging.getLogger("lms.agents")


# ---------------------------------------------------------------------------
#  Helper: access the DB from inside an agent (needs Flask app context)
# ---------------------------------------------------------------------------

_flask_app = None  # will be set from run.py


def set_flask_app(app):
    global _flask_app
    _flask_app = app


def _app_context():
    if _flask_app is None:
        raise RuntimeError("Flask app not registered with agents module")
    return _flask_app.app_context()


# ---------------------------------------------------------------------------
#  Inter-agent transport
# ---------------------------------------------------------------------------

_transport = None

# OpenClaw client is owned by OpenClawTransport when enabled.
_openclaw_client = None

_CHANNEL_ORCHESTRATOR = "orchestrator"
_CHANNEL_ADAPTATION = "adaptation"
_CHANNEL_NOTIFICATION = "notification"
_CHANNELS = [_CHANNEL_ORCHESTRATOR, _CHANNEL_ADAPTATION, _CHANNEL_NOTIFICATION]


# ===================================================================
#  OrchestratorAgent  (central coordinator)
# ===================================================================

async def run_orchestrator():
    """Central coordinator: routes events from all agents."""
    log.info("[OrchestratorAgent] Starting …")
    while True:
        data = await _transport.recv(_CHANNEL_ORCHESTRATOR, timeout=10)
        if data is None:
            continue

        event_type = data.get("type")
        source = data.get("_source", "unknown")
        log.info("[Orchestrator] Received event '%s' from %s", event_type, source)

        _log_event(event_type, source, data)

        if event_type == EVENT_STUDENT_RISK:
            await _handle_student_risk(data)
        elif event_type == EVENT_RECOMMENDATIONS_READY:
            _handle_recommendations_ready(data)
        elif event_type == EVENT_ADAPTATION_ANALYSIS:
            _handle_adaptation_analysis(data)
        else:
            log.info("[Orchestrator] Unknown event type '%s', ignoring.", event_type)


async def _handle_student_risk(data: dict):
    student_id = data["student_id"]
    student_name = data.get("student_name", "")
    score = data.get("score", 0)
    severity = data.get("severity", "warning")

    _log_decision(
        "student_risk", "monitoring", student_id,
        f"Score={score}%, dispatching to adaptation and notification",
    )

    await _transport.send(_CHANNEL_ADAPTATION, {
        "type": CMD_GENERATE_RECOMMENDATIONS,
        "student_id": student_id,
        "student_name": student_name,
        "score": score,
    })

    await _transport.send(_CHANNEL_NOTIFICATION, {
        "type": CMD_CREATE_ALERT,
        "student_id": student_id,
        "student_name": student_name,
        "score": score,
        "severity": severity,
    })


def _handle_recommendations_ready(data: dict):
    student_id = data.get("student_id")
    count = data.get("recommendations_count", 0)
    ai_used = data.get("ai_used", False)

    _log_decision(
        "recommendations_ready", "adaptation", student_id,
        f"Generated {count} recommendations (AI={'yes' if ai_used else 'no'})",
    )
    log.info(
        "[Orchestrator] %d recommendations ready for student %s (AI=%s)",
        count, student_id, ai_used,
    )


def _handle_adaptation_analysis(data: dict):
    student_id = data.get("student_id")
    suggested = data.get("suggested_difficulty", 1)
    _log_decision(
        "adaptation_analysis", "adaptation", student_id,
        f"Suggested difficulty={suggested}",
    )


def _log_event(event_type: str, source: str, data: dict):
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


def _log_decision(event_type: str, target: str, student_id, decision: str):
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


# ===================================================================
#  MonitoringAgent
# ===================================================================

async def run_monitoring():
    """Periodic monitoring loop: fires every MONITORING_PERIOD seconds."""
    log.info("[MonitoringAgent] Starting …")
    while True:
        await asyncio.sleep(config.MONITORING_PERIOD)
        log.info("[MonitoringAgent] Running monitoring cycle …")
        try:
            await _monitoring_cycle()
        except Exception as exc:
            log.error("[MonitoringAgent] Cycle error: %s", exc)


async def _monitoring_cycle():
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

            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            recent = [a for a in answers if a.created_at >= recent_cutoff]
            recent_score = None
            if recent:
                recent_correct = sum(1 for a in recent if a.is_correct)
                recent_score = round(recent_correct / len(recent) * 100, 1)

            if score >= config.RISK_SCORE_THRESHOLD:
                continue

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

            db.session.add(AgentReport(
                agent_type="monitoring",
                student_id=student.id,
                message=msg_text,
                severity=severity,
            ))

            await _transport.send(_CHANNEL_ORCHESTRATOR, {
                "type": EVENT_STUDENT_RISK,
                "_source": "monitoring",
                "student_id": student.id,
                "student_name": student.full_name or student.username,
                "score": score,
                "recent_score": recent_score,
                "severity": severity,
            })

        db.session.commit()
    log.info("[MonitoringAgent] Monitoring cycle complete.")


# ===================================================================
#  AdaptationAgent  (OpenClaw-powered)
# ===================================================================

async def run_adaptation():
    """Adaptation agent: command listener + periodic proactive scan."""
    log.info("[AdaptationAgent] Starting …")
    listen_task = asyncio.ensure_future(_adaptation_listen_loop())
    period_task = asyncio.ensure_future(_adaptation_periodic_loop())
    await asyncio.gather(listen_task, period_task)


async def _adaptation_listen_loop():
    while True:
        data = await _transport.recv(_CHANNEL_ADAPTATION, timeout=10)
        if data is None:
            continue

        try:
            if data.get("type") == CMD_GENERATE_RECOMMENDATIONS:
                await _generate_recommendations(data)
            elif data.get("type") == CMD_ANALYZE_ERRORS:
                await _analyze_errors(data)
        except Exception as exc:
            log.error("[AdaptationAgent] Error processing task: %s", exc)


async def _adaptation_periodic_loop():
    while True:
        await asyncio.sleep(config.ADAPTATION_PERIOD)
        log.info("[AdaptationAgent] Running periodic adaptation scan …")
        try:
            await _periodic_adapt()
        except Exception as exc:
            log.error("[AdaptationAgent] Periodic scan error: %s", exc)


async def _generate_recommendations(data: dict):
    student_id = data["student_id"]
    student_name = data.get("student_name", "")
    score = data.get("score", 0)

    log.info(
        "[AdaptationAgent] Generating recommendations for student %s (score=%s%%)",
        student_id, score,
    )

    recommendations_count = 0
    ai_used = config.AI_ENABLED

    with _app_context():
        from models import AdaptationLog, StudentAnswer, Topic, db

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
                rec_text = ai_service.generate_recommendation(
                    student_name=student_name,
                    topic_title=topic.title,
                    score_pct=pct,
                    total_answers=total,
                    correct_answers=correct,
                )
                db.session.add(AdaptationLog(
                    student_id=student_id,
                    topic_id=topic.id,
                    recommendation=rec_text,
                    ai_generated=ai_used,
                ))
                recommendations_count += 1
        else:
            if score < config.RISK_SCORE_THRESHOLD:
                db.session.add(AdaptationLog(
                    student_id=student_id,
                    recommendation=ai_service.generate_recommendation(
                        student_name=student_name,
                        topic_title="общая программа",
                        score_pct=score,
                        total_answers=len(answers),
                        correct_answers=sum(1 for a in answers if a.is_correct),
                    ),
                    ai_generated=ai_used,
                ))
                recommendations_count += 1

        db.session.commit()

    await _transport.send(_CHANNEL_ORCHESTRATOR, {
        "type": EVENT_RECOMMENDATIONS_READY,
        "_source": "adaptation",
        "student_id": student_id,
        "recommendations_count": recommendations_count,
        "ai_used": ai_used,
    })


async def _analyze_errors(data: dict):
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

    await _transport.send(_CHANNEL_ORCHESTRATOR, {
        "type": EVENT_ADAPTATION_ANALYSIS,
        "_source": "adaptation",
        "student_id": student_id,
        **analysis,
    })


async def _periodic_adapt():
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

                db.session.add(AdaptationLog(
                    student_id=student.id,
                    topic_id=topic.id,
                    recommendation=ai_service.generate_recommendation(
                        student_name=student.full_name or student.username,
                        topic_title=topic.title,
                        score_pct=round(pct, 1),
                        total_answers=st["total"],
                        correct_answers=st["correct"],
                    ),
                    ai_generated=config.AI_ENABLED,
                ))

        db.session.commit()
    log.info("[AdaptationAgent] Periodic adaptation scan complete.")


# ===================================================================
#  NotificationAgent
# ===================================================================

async def run_notification():
    """Notification agent: persists teacher-visible alerts."""
    log.info("[NotificationAgent] Starting …")
    while True:
        data = await _transport.recv(_CHANNEL_NOTIFICATION, timeout=10)
        if data is None:
            continue

        if data.get("type") != CMD_CREATE_ALERT:
            continue

        log.info(
            "[NotificationAgent] Creating alert for student %s",
            data.get("student_name"),
        )

        try:
            with _app_context():
                from models import AgentReport, db

                db.session.add(AgentReport(
                    agent_type="notification",
                    student_id=data.get("student_id"),
                    message=(
                        f"Уведомление: студент «{data.get('student_name')}» "
                        f"находится в зоне риска (балл: {data.get('score')}%)."
                    ),
                    severity=data.get("severity", "warning"),
                ))
                db.session.commit()
        except Exception as exc:
            log.error("[NotificationAgent] Failed to create alert: %s", exc)


# ===================================================================
#  Lifecycle: start / watch / stop
# ===================================================================

_tasks: list[asyncio.Task] = []

_AGENT_FACTORIES = {
    "orchestrator": run_orchestrator,
    "monitoring": run_monitoring,
    "adaptation": run_adaptation,
    "notification": run_notification,
}


async def start_agents(transport_mode: str = "local", roles: list[str] | None = None):
    """Start selected agent coroutines using requested transport mode."""
    global _tasks, _openclaw_client, _transport

    roles = roles or list(_AGENT_FACTORIES.keys())

    if transport_mode == "openclaw":
        try:
            _transport = OpenClawTransport(config.OPENCLAW_GATEWAY_URL, _CHANNELS)
            _openclaw_client = _transport._client
            log.info("[Agents] OpenClaw transport connected to %s.", config.OPENCLAW_GATEWAY_URL)
        except Exception as exc:
            raise RuntimeError(
                f"OpenClaw transport init failed: {exc}. Start gateway and check dependencies."
            ) from exc
    else:
        _transport = LocalQueueTransport(_CHANNELS)
        log.info("[Agents] Local transport enabled (single-process mode).")

    invalid = [r for r in roles if r not in _AGENT_FACTORIES]
    if invalid:
        raise ValueError(f"Unknown agent roles: {invalid}")

    _tasks = [asyncio.ensure_future(_AGENT_FACTORIES[r]()) for r in roles]
    log.info("[Agents] Started roles: %s", ", ".join(roles))


async def watch_agents(check_interval: int = 30):
    """Restart any agent coroutine that has unexpectedly stopped."""
    while True:
        await asyncio.sleep(check_interval)
        for i, task in enumerate(_tasks):
            if task.done():
                exc = task.exception() if not task.cancelled() else None
                log.warning("[Agents] Task #%d died (%s), restarting …", i, exc)
                # In role-based mode we do not know original role here; skip auto-restart to avoid wrong binding.


async def stop_agents():
    """Cancel all running agent tasks."""
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    log.info("[Agents] All agents stopped.")
