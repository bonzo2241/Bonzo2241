"""
OpenClaw native multi-agent system for LMS.

Each agent is a real OpenClaw LLM-powered entity registered in the local gateway.
Python handles DB access and scheduling; OpenClaw agents handle reasoning and
inter-agent coordination via the agentToAgent tool.

Flow:
  1. Python monitoring loop queries DB, finds at-risk students
  2. Passes data to OpenClaw MonitoringAgent → agent reasons and routes to Orchestrator
  3. OrchestratorAgent (in gateway) routes to Adaptation and Notification agents
  4. AdaptationAgent generates recommendations via LLM
  5. Python captures structured output and persists to DB
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from openclaw import OpenClawClient

import ai_service
import config

log = logging.getLogger("lms.agents")


# ---------------------------------------------------------------------------
#  Flask app context (set from run.py)
# ---------------------------------------------------------------------------

_flask_app = None


def set_flask_app(app):
    global _flask_app
    _flask_app = app


def _app_context():
    if _flask_app is None:
        raise RuntimeError("Flask app not registered with agents module")
    return _flask_app.app_context()


# ---------------------------------------------------------------------------
#  OpenClaw client + agent handles
# ---------------------------------------------------------------------------

_client: OpenClawClient | None = None
_agents: dict = {}


# ---------------------------------------------------------------------------
#  Agent SOUL definitions (instructions for each LLM-powered agent)
# ---------------------------------------------------------------------------

_ORCHESTRATOR_SOUL = """\
You are OrchestratorAgent — central coordinator of an LMS multi-agent learning system.

Your only job is routing: you receive events and dispatch tasks to the right agents.

Rules:
- When you receive a student_risk event → send generate_recommendations to lms-adaptation
  AND send create_alert to lms-notification (both, always).
- When you receive recommendations_ready → log it and stop.
- When you receive adaptation_analysis → log it and stop.
- Never act on student data yourself. Never skip routing steps.

Use agentToAgent for all inter-agent communication.
Always include student_id and student_name in forwarded messages.
"""

_MONITORING_SOUL = """\
You are MonitoringAgent — you detect at-risk students in an LMS system.

When given a list of students with their scores:
- Score below 50%: at risk, severity = "warning"
- Score below 30%: critical, severity = "danger"

For each at-risk student, send a student_risk event to lms-orchestrator via agentToAgent.

Message format (JSON):
{
  "type": "student_risk",
  "student_id": <id>,
  "student_name": "<name>",
  "score": <float>,
  "severity": "warning" | "danger"
}

Send one message per at-risk student. If no students are at risk, respond with "No at-risk students found."
"""

_ADAPTATION_SOUL = """\
You are AdaptationAgent — you generate personalized learning recommendations for students.

When asked to generate recommendations for a student:
1. Review the student's weak topics (score below threshold)
2. For each weak topic, write a specific, encouraging, actionable recommendation
3. Return recommendations as a JSON array:
[
  {"topic": "<topic_name>", "recommendation": "<text>", "priority": "high"|"medium"}
]
4. After generating, notify lms-orchestrator via agentToAgent:
   {"type": "recommendations_ready", "student_id": <id>, "count": <n>}

Keep recommendations concrete and motivating. Max 2-3 sentences per topic.
"""

_NOTIFICATION_SOUL = """\
You are NotificationAgent — you create clear, professional alerts for teachers in an LMS.

When you receive a create_alert task:
1. Compose a concise teacher-facing alert message in Russian
2. Include: student name, score percentage, severity level, suggested action
3. Return the alert as JSON:
   {"message": "<alert text>", "severity": "warning"|"danger"}
4. Notify lms-orchestrator: {"type": "alert_created", "student_id": <id>}

Keep messages professional, factual, and actionable. Do not alarm unnecessarily.
"""


# ---------------------------------------------------------------------------
#  Agent lifecycle
# ---------------------------------------------------------------------------

_tasks: list[asyncio.Task] = []
_AGENT_LOOPS = []


async def start_agents():
    """Register OpenClaw agents in gateway, start all agent loops."""
    global _client, _agents, _tasks, _AGENT_LOOPS

    _client = OpenClawClient(base_url=config.OPENCLAW_GATEWAY_URL)
    log.info("[Agents] Connected to OpenClaw gateway at %s", config.OPENCLAW_GATEWAY_URL)

    # Register all four agents in the OpenClaw gateway
    _agents["orchestrator"] = _client.agents.create(
        name="lms-orchestrator",
        model="openrouter/auto",
        description="Central coordinator — routes events between LMS agents",
        soul=_ORCHESTRATOR_SOUL,
        tools={
            "agentToAgent": {
                "enabled": True,
                "allow": ["lms-adaptation", "lms-notification"],
            }
        },
    )

    _agents["monitoring"] = _client.agents.create(
        name="lms-monitoring",
        model="openrouter/auto",
        description="Detects at-risk students and reports to orchestrator",
        soul=_MONITORING_SOUL,
        tools={
            "agentToAgent": {
                "enabled": True,
                "allow": ["lms-orchestrator"],
            }
        },
    )

    _agents["adaptation"] = _client.agents.create(
        name="lms-adaptation",
        model="openrouter/auto",
        description="Generates personalized learning recommendations",
        soul=_ADAPTATION_SOUL,
        tools={
            "agentToAgent": {
                "enabled": True,
                "allow": ["lms-orchestrator"],
            }
        },
    )

    _agents["notification"] = _client.agents.create(
        name="lms-notification",
        model="openrouter/auto",
        description="Creates teacher-visible alerts for at-risk students",
        soul=_NOTIFICATION_SOUL,
        tools={
            "agentToAgent": {
                "enabled": True,
                "allow": ["lms-orchestrator"],
            }
        },
    )

    log.info("[Agents] All 4 OpenClaw agents registered in gateway.")

    _AGENT_LOOPS = [
        _monitoring_loop,
        _adaptation_loop,
        _orchestrator_heartbeat,
        _notification_heartbeat,
    ]
    _tasks = [asyncio.ensure_future(fn()) for fn in _AGENT_LOOPS]
    log.info("[Agents] Agent loops started.")


async def watch_agents(check_interval: int = 30):
    """Restart any agent loop that has unexpectedly stopped."""
    while True:
        await asyncio.sleep(check_interval)
        for i, task in enumerate(_tasks):
            if task.done():
                exc = task.exception() if not task.cancelled() else None
                name = _AGENT_LOOPS[i].__name__
                log.warning("[Agents] %s died (%s), restarting …", name, exc)
                _tasks[i] = asyncio.ensure_future(_AGENT_LOOPS[i]())


async def stop_agents():
    """Cancel all running agent loops."""
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    log.info("[Agents] All agents stopped.")


# ---------------------------------------------------------------------------
#  MonitoringAgent loop
#  Python queries DB → passes data to OpenClaw agent → agent reasons + routes
# ---------------------------------------------------------------------------

async def _monitoring_loop():
    log.info("[MonitoringAgent] Starting periodic loop (every %ds) …", config.MONITORING_PERIOD)
    while True:
        await asyncio.sleep(config.MONITORING_PERIOD)
        try:
            await _monitoring_cycle()
        except Exception as exc:
            log.error("[MonitoringAgent] Cycle error: %s", exc)


async def _monitoring_cycle():
    at_risk = []

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
            at_risk.append({
                "student_id": student.id,
                "student_name": student.full_name or student.username,
                "score": score,
                "severity": severity,
            })

            db.session.add(AgentReport(
                agent_type="monitoring",
                student_id=student.id,
                message=(
                    f"Студент «{student.full_name or student.username}» "
                    f"имеет балл {score}%."
                ),
                severity=severity,
            ))

        db.session.commit()

    if not at_risk:
        log.info("[MonitoringAgent] No at-risk students found.")
        return

    # Hand off to OpenClaw MonitoringAgent for reasoning and routing
    prompt = (
        f"Student performance data for this monitoring cycle:\n"
        f"{json.dumps(at_risk, ensure_ascii=False, indent=2)}\n\n"
        f"Identify at-risk students and report each one to lms-orchestrator."
    )

    result = await asyncio.to_thread(_agents["monitoring"].run, prompt)
    log.info("[MonitoringAgent] OpenClaw agent response: %s", result)
    _log_orchestrator_event("monitoring_cycle", "monitoring", {"at_risk_count": len(at_risk)})


# ---------------------------------------------------------------------------
#  AdaptationAgent loop
#  Periodic proactive scan — Python finds weak topics, OpenClaw agent generates recs
# ---------------------------------------------------------------------------

async def _adaptation_loop():
    log.info("[AdaptationAgent] Starting periodic loop (every %ds) …", config.ADAPTATION_PERIOD)
    while True:
        await asyncio.sleep(config.ADAPTATION_PERIOD)
        try:
            await _adaptation_cycle()
        except Exception as exc:
            log.error("[AdaptationAgent] Cycle error: %s", exc)


async def _adaptation_cycle():
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

            weak_topics = []
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
                if topic:
                    weak_topics.append({
                        "topic_id": tid,
                        "topic_title": topic.title,
                        "score": round(pct, 1),
                        "total": st["total"],
                        "correct": st["correct"],
                    })

            if not weak_topics:
                continue

            # Ask OpenClaw AdaptationAgent to generate recommendations
            prompt = (
                f"Generate personalized recommendations for student "
                f"«{student.full_name or student.username}» (id={student.id}).\n"
                f"Weak topics:\n"
                f"{json.dumps(weak_topics, ensure_ascii=False, indent=2)}"
            )

            result = await asyncio.to_thread(_agents["adaptation"].run, prompt)
            log.info("[AdaptationAgent] Got recommendations for student %d", student.id)

            # Parse recommendations from agent output and persist
            recs = _extract_json_array(result)
            if recs:
                for rec in recs:
                    topic = Topic.query.filter_by(title=rec.get("topic", "")).first()
                    db.session.add(AdaptationLog(
                        student_id=student.id,
                        topic_id=topic.id if topic else None,
                        recommendation=rec.get("recommendation", result),
                        ai_generated=True,
                    ))
            else:
                # Fallback: use ai_service directly
                for wt in weak_topics:
                    rec_text = ai_service.generate_recommendation(
                        student_name=student.full_name or student.username,
                        topic_title=wt["topic_title"],
                        score_pct=wt["score"],
                        total_answers=wt["total"],
                        correct_answers=wt["correct"],
                    )
                    db.session.add(AdaptationLog(
                        student_id=student.id,
                        topic_id=wt["topic_id"],
                        recommendation=rec_text,
                        ai_generated=config.AI_ENABLED,
                    ))

        db.session.commit()
    log.info("[AdaptationAgent] Proactive adaptation cycle complete.")


# ---------------------------------------------------------------------------
#  Orchestrator and Notification heartbeat loops
#  These agents live in the gateway and respond to agentToAgent messages.
#  Python loops just keep them registered and restartable.
# ---------------------------------------------------------------------------

async def _orchestrator_heartbeat():
    """OrchestratorAgent lives in the gateway. This loop keeps it monitored."""
    log.info("[OrchestratorAgent] Running in OpenClaw gateway (lms-orchestrator).")
    while True:
        await asyncio.sleep(60)


async def _notification_heartbeat():
    """NotificationAgent lives in the gateway. This loop keeps it monitored."""
    log.info("[NotificationAgent] Running in OpenClaw gateway (lms-notification).")
    while True:
        await asyncio.sleep(60)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _extract_json_array(text: str) -> list | None:
    """Extract the first JSON array found in agent output text."""
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def _log_orchestrator_event(event_type: str, source: str, data: dict):
    try:
        with _app_context():
            from models import OrchestratorLog, db
            db.session.add(OrchestratorLog(
                event_type=event_type,
                source_agent=source,
                student_id=data.get("student_id"),
                payload=json.dumps(data, ensure_ascii=False),
            ))
            db.session.commit()
    except Exception as exc:
        log.error("[Agents] Failed to log event: %s", exc)
