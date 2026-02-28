"""
AI Service module — wrapper around OpenAI-compatible LLM API.

Provides functions for:
  - Generating personalised student recommendations
  - Generating quiz questions from a topic description
  - Analysing student error patterns for adaptive difficulty
  - Answering student questions (chat assistant)

When AI_ENABLED is False (no API key), every function falls back to
deterministic rule-based logic so the platform remains fully functional.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import config

log = logging.getLogger("lms.ai")

# ---------------------------------------------------------------------------
#  Lazy-initialised OpenAI client
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            default_headers={
                "HTTP-Referer": "http://localhost:5000",  # требуется OpenRouter
                "X-Title": "LMS Platform",
            },
        )
    return _client


def _chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """Send a chat-completion request and return the assistant message text."""
    client = _get_client()
    response = client.chat.completions.create(
        model=config.AI_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


# ===================================================================
#  1. Personalised recommendations
# ===================================================================

def generate_recommendation(
    student_name: str,
    topic_title: str,
    score_pct: float,
    total_answers: int,
    correct_answers: int,
) -> str:
    """Return an AI-generated personalised recommendation for a student."""
    if not config.AI_ENABLED:
        return _fallback_recommendation(topic_title, score_pct)

    try:
        prompt = (
            f"Ты — ИИ-помощник в системе дистанционного обучения. "
            f"Студент «{student_name}» изучает тему «{topic_title}». "
            f"Его текущий результат: {score_pct}% ({correct_answers} из {total_answers} правильных). "
            f"Составь краткую персонализированную рекомендацию на русском языке (2–4 предложения). "
            f"Укажи конкретные шаги для улучшения результатов."
        )
        return _chat([
            {"role": "system", "content": "Ты — опытный преподаватель. Отвечай кратко и по делу."},
            {"role": "user", "content": prompt},
        ], temperature=0.7, max_tokens=300)
    except Exception as exc:
        log.warning("AI recommendation failed, using fallback: %s", exc)
        return _fallback_recommendation(topic_title, score_pct)


def _fallback_recommendation(topic_title: str, score_pct: float) -> str:
    if score_pct < 30:
        return (
            f"Рекомендуется повторить тему «{topic_title}» с самого начала. "
            f"Текущий результат ({score_pct}%) показывает, что материал усвоен слабо. "
            f"Начните с теоретической части, затем переходите к практике."
        )
    if score_pct < 50:
        return (
            f"Рекомендуется повторить тему «{topic_title}» "
            f"(текущий результат: {score_pct}%). "
            f"Обратите внимание на пояснения к вопросам, которые вызвали затруднения."
        )
    return (
        f"Результат по теме «{topic_title}» — {score_pct}%. "
        f"Для закрепления рекомендуется пройти тест повторно."
    )


# ===================================================================
#  2. AI question generation
# ===================================================================

def generate_questions(
    topic_title: str,
    topic_description: str,
    count: int = 3,
    difficulty: int = 1,
) -> list[dict[str, Any]]:
    """Generate quiz questions for a topic. Returns list of dicts with keys:
    text, option_a, option_b, option_c, option_d, correct_answer, explanation.
    """
    if not config.AI_ENABLED:
        return _fallback_questions(topic_title, count)

    diff_label = {1: "простой", 2: "средний", 3: "сложный"}.get(difficulty, "средний")

    try:
        prompt = (
            f"Сгенерируй {count} тестовых вопросов по теме «{topic_title}».\n"
            f"Описание темы: {topic_description}\n"
            f"Уровень сложности: {diff_label}.\n\n"
            f"Каждый вопрос должен иметь 4 варианта ответа (A, B, C, D), "
            f"один правильный ответ и краткое пояснение.\n\n"
            f"Ответ верни строго в формате JSON — массив объектов:\n"
            f'[{{"text": "...", "option_a": "...", "option_b": "...", '
            f'"option_c": "...", "option_d": "...", '
            f'"correct_answer": "A", "explanation": "..."}}]\n'
            f"Без markdown-обёрток, только чистый JSON."
        )

        raw = _chat([
            {"role": "system", "content": "Ты — генератор учебных тестов. Отвечай только JSON."},
            {"role": "user", "content": prompt},
        ], temperature=0.8, max_tokens=2000)

        # Strip possible markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        questions = json.loads(raw)
        # Validate structure
        validated = []
        for q in questions:
            validated.append({
                "text": str(q.get("text", "")),
                "option_a": str(q.get("option_a", "")),
                "option_b": str(q.get("option_b", "")),
                "option_c": str(q.get("option_c", "")),
                "option_d": str(q.get("option_d", "")),
                "correct_answer": str(q.get("correct_answer", "A")).upper()[:1],
                "explanation": str(q.get("explanation", "")),
            })
        return validated

    except Exception as exc:
        log.warning("AI question generation failed, using fallback: %s", exc)
        return _fallback_questions(topic_title, count)


def _fallback_questions(topic_title: str, count: int) -> list[dict]:
    """Placeholder questions when AI is unavailable."""
    results = []
    for i in range(1, count + 1):
        results.append({
            "text": f"Вопрос {i} по теме «{topic_title}» (сгенерируйте вручную или подключите AI API)",
            "option_a": "Вариант A",
            "option_b": "Вариант B",
            "option_c": "Вариант C",
            "option_d": "Вариант D",
            "correct_answer": "A",
            "explanation": "Требуется API-ключ для автоматической генерации вопросов.",
        })
    return results


# ===================================================================
#  3. Error pattern analysis (smart adaptation)
# ===================================================================

def analyze_error_patterns(
    student_name: str,
    topic_results: list[dict],
) -> dict[str, Any]:
    """Analyse student error patterns across topics.

    *topic_results* is a list of dicts:
        {"topic_title": str, "total": int, "correct": int, "pct": float}

    Returns {"summary": str, "weak_areas": [str], "suggested_difficulty": int}.
    """
    if not config.AI_ENABLED:
        return _fallback_analysis(topic_results)

    try:
        topics_text = "\n".join(
            f"- {t['topic_title']}: {t['pct']}% ({t['correct']}/{t['total']})"
            for t in topic_results
        )
        prompt = (
            f"Студент «{student_name}» имеет следующие результаты:\n"
            f"{topics_text}\n\n"
            f"Проанализируй паттерн ошибок. Определи слабые области и предложи "
            f"уровень сложности (1=простой, 2=средний, 3=сложный).\n\n"
            f"Ответь строго в JSON:\n"
            f'{{"summary": "...", "weak_areas": ["..."], "suggested_difficulty": 1}}'
        )

        raw = _chat([
            {"role": "system", "content": "Ты — аналитик учебных данных. Отвечай JSON."},
            {"role": "user", "content": prompt},
        ], temperature=0.5, max_tokens=500)

        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        return json.loads(raw.strip())

    except Exception as exc:
        log.warning("AI error analysis failed, using fallback: %s", exc)
        return _fallback_analysis(topic_results)


def _fallback_analysis(topic_results: list[dict]) -> dict:
    weak = [t["topic_title"] for t in topic_results if t["pct"] < 50]
    avg = sum(t["pct"] for t in topic_results) / len(topic_results) if topic_results else 0
    if avg < 30:
        diff = 1
    elif avg < 60:
        diff = 1
    else:
        diff = 2
    return {
        "summary": f"Средний балл: {round(avg, 1)}%. Слабые темы: {', '.join(weak) or 'не выявлены'}.",
        "weak_areas": weak,
        "suggested_difficulty": diff,
    }


# ===================================================================
#  4. Chat assistant
# ===================================================================

def chat_answer(
    student_question: str,
    topic_title: str | None = None,
    conversation_history: list[dict] | None = None,
) -> str:
    """Answer a student question about a learning topic."""
    if not config.AI_ENABLED:
        return _fallback_chat(student_question, topic_title)

    try:
        system_msg = (
            "Ты — ИИ-помощник в системе дистанционного обучения. "
            "Отвечай на вопросы студентов кратко и понятно, на русском языке. "
            "Используй примеры, если это уместно. "
            "Не давай прямых ответов на тестовые вопросы — объясняй концепции."
        )
        if topic_title:
            system_msg += f" Текущая тема: «{topic_title}»."

        messages = [{"role": "system", "content": system_msg}]

        if conversation_history:
            for msg in conversation_history[-10:]:  # Keep last 10 messages for context
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": student_question})

        return _chat(messages, temperature=0.7, max_tokens=800)

    except Exception as exc:
        log.warning("AI chat failed, using fallback: %s", exc)
        return _fallback_chat(student_question, topic_title)


def _fallback_chat(question: str, topic_title: str | None) -> str:
    topic_part = f" по теме «{topic_title}»" if topic_title else ""
    return (
        f"Для ответа на вопрос{topic_part} требуется подключение к AI API. "
        f"Задайте переменную окружения OPENAI_API_KEY и перезапустите приложение. "
        f"А пока обратитесь к материалам курса или преподавателю."
    )
