"""
Flask web application for the LMS.
"""

from __future__ import annotations

import functools
import json
import random
from datetime import datetime, timedelta

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from models import (
    AdaptationLog,
    AgentReport,
    ChatMessage,
    ConsentProfile,
    OrchestratorLog,
    Project,
    ProjectMembership,
    ProjectTask,
    Question,
    RecommendationInteraction,
    StudentAnswer,
    StudentProfile,
    Topic,
    User,
    db,
)
import ai_service


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS

    db.init_app(app)

    with app.app_context():
        db.create_all()
        # Enable WAL mode for better concurrent access (Flask + SPADE agents).
        with db.engine.connect() as conn:
            conn.execute(db.text("PRAGMA journal_mode=WAL"))
            conn.commit()
        _seed_demo_data()

    _register_routes(app)
    return app


# -------------------------------------------------------------------
#  Demo data
# -------------------------------------------------------------------

def _seed_demo_data():  # noqa: C901
    if User.query.first() is not None:
        return

    random.seed(42)
    now = datetime.utcnow()

    # ── Teachers ──────────────────────────────────────────────────
    teacher = User(username="teacher", role="teacher", full_name="Иванов И.И.")
    teacher.set_password("teacher")
    db.session.add(teacher)

    teacher2 = User(username="teacher2", role="teacher", full_name="Смирнова Е.А.")
    teacher2.set_password("teacher2")
    db.session.add(teacher2)

    db.session.flush()

    # ── Topics & Questions ────────────────────────────────────────
    topics_data = [
        {
            "title": "Основы Python",
            "description": "Базовые конструкции языка Python: переменные, типы данных, условия, циклы.",
            "difficulty": 1,
            "created_by": teacher.id,
            "questions": [
                ("Какой тип данных возвращает функция input()?",
                 "int", "str", "float", "bool", "B",
                 "Функция input() всегда возвращает строку (str)."),
                ("Как объявить список в Python?",
                 "list = (1,2,3)", "list = {1,2,3}", "list = [1,2,3]", "list = <1,2,3>", "C",
                 "Списки объявляются с помощью квадратных скобок []."),
                ("Какой оператор используется для целочисленного деления?",
                 "/", "//", "%", "**", "B",
                 "Оператор // выполняет целочисленное деление."),
                ("Что выведет print(type(3.14))?",
                 "<class 'int'>", "<class 'float'>", "<class 'str'>", "<class 'double'>", "B",
                 "Число 3.14 — вещественное, его тип float."),
                ("Какое ключевое слово используется для определения функции?",
                 "func", "function", "def", "lambda", "C",
                 "Ключевое слово def используется для определения функций в Python."),
            ],
        },
        {
            "title": "Структуры данных",
            "description": "Списки, кортежи, словари, множества и их методы.",
            "difficulty": 2,
            "created_by": teacher.id,
            "questions": [
                ("Какой метод добавляет элемент в конец списка?",
                 "insert()", "append()", "extend()", "push()", "B",
                 "Метод append() добавляет один элемент в конец списка."),
                ("Какая структура данных неизменяема?",
                 "list", "dict", "set", "tuple", "D",
                 "Кортеж (tuple) — неизменяемая структура данных."),
                ("Как получить все ключи словаря d?",
                 "d.keys()", "d.values()", "d.items()", "d.all()", "A",
                 "Метод keys() возвращает представление всех ключей словаря."),
                ("Что вернёт len({1, 2, 2, 3})?",
                 "4", "3", "2", "Ошибку", "B",
                 "Множество содержит только уникальные элементы: {1, 2, 3}, длина 3."),
                ("Как объединить два списка a и b?",
                 "a.merge(b)", "a + b", "a.join(b)", "a & b", "B",
                 "Оператор + объединяет два списка в новый."),
            ],
        },
        {
            "title": "ООП в Python",
            "description": "Классы, объекты, наследование, инкапсуляция, полиморфизм.",
            "difficulty": 2,
            "created_by": teacher.id,
            "questions": [
                ("Как создать класс в Python?",
                 "class MyClass:", "new MyClass:", "create MyClass:", "define MyClass:", "A",
                 "Класс определяется ключевым словом class."),
                ("Что такое self в методе класса?",
                 "Имя класса", "Ссылка на текущий экземпляр", "Глобальная переменная", "Декоратор", "B",
                 "self — ссылка на текущий экземпляр объекта."),
                ("Какой метод вызывается при создании экземпляра?",
                 "__str__", "__init__", "__new__", "__call__", "B",
                 "__init__ — конструктор, вызывается при создании объекта."),
                ("Как обозначается наследование?",
                 "class Child -> Parent:", "class Child(Parent):", "class Child extends Parent:", "class Child: Parent", "B",
                 "В Python наследование указывается в скобках после имени класса."),
                ("Что делает декоратор @staticmethod?",
                 "Делает метод приватным", "Убирает параметр self", "Делает метод абстрактным", "Добавляет логирование", "B",
                 "Статический метод не получает self и не привязан к экземпляру."),
            ],
        },
        {
            "title": "Алгоритмы и сложность",
            "description": "Основные алгоритмы сортировки, поиска и оценка вычислительной сложности.",
            "difficulty": 3,
            "created_by": teacher2.id,
            "questions": [
                ("Какова сложность бинарного поиска?",
                 "O(n)", "O(n²)", "O(log n)", "O(1)", "C",
                 "Бинарный поиск делит массив пополам на каждом шаге → O(log n)."),
                ("Какой алгоритм сортировки имеет лучшую среднюю сложность?",
                 "Пузырьковая O(n²)", "Быстрая O(n log n)", "Вставками O(n²)", "Выбором O(n²)", "B",
                 "Быстрая сортировка в среднем работает за O(n log n)."),
                ("Что такое рекурсия?",
                 "Цикл while", "Вызов функцией самой себя", "Обработка исключений", "Чтение файла", "B",
                 "Рекурсия — приём, при котором функция вызывает саму себя."),
                ("Какова сложность доступа к элементу в хеш-таблице?",
                 "O(n)", "O(log n)", "O(1)", "O(n²)", "C",
                 "В среднем случае доступ к элементу хеш-таблицы — O(1)."),
                ("Что такое жадный алгоритм?",
                 "Перебирает все варианты", "На каждом шаге выбирает локально лучший вариант",
                 "Использует только рекурсию", "Работает только с графами", "B",
                 "Жадный алгоритм делает локально оптимальный выбор на каждом шаге."),
            ],
        },
    ]

    topic_objects = []
    question_objects = []  # flat list of all questions
    topic_questions = {}   # topic_index -> [question_objects]

    for i, td in enumerate(topics_data):
        t = Topic(
            title=td["title"],
            description=td["description"],
            difficulty=td["difficulty"],
            created_by=td["created_by"],
        )
        db.session.add(t)
        db.session.flush()
        topic_objects.append(t)
        topic_questions[i] = []
        for qd in td["questions"]:
            q = Question(
                topic_id=t.id, text=qd[0],
                option_a=qd[1], option_b=qd[2], option_c=qd[3], option_d=qd[4],
                correct_answer=qd[5], explanation=qd[6],
            )
            db.session.add(q)
            question_objects.append(q)
            topic_questions[i].append(q)

    db.session.flush()

    # ── Students ──────────────────────────────────────────────────
    # Each student has: name, username, password,
    #   accuracy per topic [t0, t1, t2, t3], attempts per topic
    students_spec = [
        ("Петров П.П.",   "student",   "student",   [0.90, 0.85, 0.80, 0.70], [5, 5, 5, 5]),
        ("Сидорова А.В.", "sidorova",  "sidorova",  [1.00, 0.95, 0.90, 0.85], [5, 5, 5, 5]),
        ("Козлов Д.М.",   "kozlov",    "kozlov",    [0.80, 0.70, 0.65, 0.55], [5, 5, 5, 5]),
        ("Волкова Е.С.",  "volkova",   "volkova",   [0.65, 0.55, 0.50, 0.40], [5, 5, 5, 5]),
        ("Морозов И.К.",  "morozov",   "morozov",   [0.40, 0.30, 0.25, 0.15], [5, 5, 5, 5]),
        ("Новикова О.Л.", "novikova",  "novikova",  [0.95, 0.90, 0.45, 0.30], [5, 5, 5, 5]),
        ("Фёдоров А.А.",  "fedorov",   "fedorov",   [0.60, 0.50, 0.00, 0.00], [3, 2, 0, 0]),
        ("Егорова М.В.",  "egorova",   "egorova",   [0.50, 0.70, 0.75, 0.85], [5, 5, 5, 5]),
        ("Павлов С.Н.",   "pavlov",    "pavlov",    [0.85, 0.70, 0.50, 0.30], [5, 5, 5, 5]),
        ("Антонова К.Р.", "antonova",  "antonova",  [0.80, 0.00, 0.00, 0.00], [5, 0, 0, 0]),
        ("Белов Р.Д.",    "belov",     "belov",     [0.20, 0.15, 0.10, 0.10], [5, 5, 5, 5]),
    ]

    student_objects = []
    for full_name, username, password, _acc, _att in students_spec:
        s = User(username=username, role="student", full_name=full_name)
        s.set_password(password)
        db.session.add(s)
        student_objects.append(s)

    db.session.flush()

    # ── Student Answers ───────────────────────────────────────────
    def _gen_answers(student, accuracies, attempts_per_topic):
        """Generate StudentAnswer rows for a student across all topics."""
        options = ["A", "B", "C", "D"]
        for ti, topic in enumerate(topic_objects):
            n_attempts = attempts_per_topic[ti]
            if n_attempts == 0:
                continue
            acc = accuracies[ti]
            qs = topic_questions[ti]
            for attempt_round in range(n_attempts):
                q = qs[attempt_round % len(qs)]
                is_correct = random.random() < acc
                if is_correct:
                    answer = q.correct_answer
                else:
                    wrong = [o for o in options if o != q.correct_answer]
                    answer = random.choice(wrong)
                sa = StudentAnswer(
                    student_id=student.id,
                    question_id=q.id,
                    topic_id=topic.id,
                    answer=answer,
                    is_correct=is_correct,
                    created_at=now - timedelta(days=random.randint(0, 14),
                                               hours=random.randint(0, 23)),
                )
                db.session.add(sa)

    for idx, s in enumerate(student_objects):
        _gen_answers(s, students_spec[idx][3], students_spec[idx][4])

    db.session.flush()

    # ── Agent Reports (monitoring & notification) ─────────────────
    at_risk = [
        (student_objects[4], "Морозов И.К.", 27.5),   # morozov
        (student_objects[10], "Белов Р.Д.", 13.8),     # belov
        (student_objects[3], "Волкова Е.С.", 47.5),    # volkova — borderline
        (student_objects[8], "Павлов С.Н.", 30.0),     # pavlov — declining
    ]
    for student, name, score in at_risk:
        severity = "danger" if score < 30 else "warning"
        report = AgentReport(
            agent_type="monitoring",
            student_id=student.id,
            message=f"Студент {name} показывает низкую успеваемость: {score}%. Требуется внимание преподавателя.",
            severity=severity,
            is_read=False,
            created_at=now - timedelta(hours=random.randint(1, 48)),
        )
        db.session.add(report)
        # Notification from orchestrator
        notif = AgentReport(
            agent_type="notification",
            student_id=student.id,
            message=f"[Оркестратор → Уведомление] Обнаружен риск для {name}. "
                    f"Текущий балл: {score}%. Рекомендовано адаптивное вмешательство.",
            severity=severity,
            is_read=False,
            created_at=now - timedelta(hours=random.randint(0, 24)),
        )
        db.session.add(notif)

    # Good performance report
    db.session.add(AgentReport(
        agent_type="monitoring",
        student_id=student_objects[1].id,
        message="Студент Сидорова А.В. демонстрирует отличные результаты: 92.5%. Рекомендовано повышение сложности.",
        severity="info",
        is_read=False,
        created_at=now - timedelta(hours=6),
    ))

    # Progress alert for Egorova
    db.session.add(AgentReport(
        agent_type="monitoring",
        student_id=student_objects[7].id,
        message="Студент Егорова М.В. показывает положительную динамику: успеваемость выросла с 50% до 85%.",
        severity="info",
        is_read=False,
        created_at=now - timedelta(hours=3),
    ))

    # ── Adaptation Logs ───────────────────────────────────────────
    adaptations_data = [
        (student_objects[4], topic_objects[0],
         "Рекомендуется вернуться к базовым понятиям Python. "
         "Начните с повторения типов данных и операторов. "
         "Решайте простые задачи на ввод-вывод перед переходом к сложным темам."),
        (student_objects[4], topic_objects[3],
         "Тема алгоритмов пока слишком сложна. Рекомендуется сначала закрепить основы "
         "и структуры данных, прежде чем переходить к оценке сложности."),
        (student_objects[10], topic_objects[0],
         "Критически низкий результат по основам. Рекомендуется индивидуальная консультация "
         "с преподавателем и проработка материала с нуля."),
        (student_objects[10], topic_objects[2],
         "ООП: результаты 10%. Необходимо разобрать концепцию классов на простых примерах. "
         "Рекомендованы интерактивные упражнения с пошаговым разбором."),
        (student_objects[3], topic_objects[3],
         "Алгоритмы: 40%. Рекомендуется визуализация алгоритмов сортировки "
         "и пошаговое прохождение через примеры на бумаге."),
        (student_objects[5], topic_objects[2],
         "ООП: резкое снижение (45%) при хороших результатах по другим темам. "
         "Возможно, пробел в понимании наследования. Рекомендуется разбор практических примеров."),
        (student_objects[8], topic_objects[3],
         "Наблюдается отрицательная динамика: с 85% до 30%. "
         "Рекомендуется проверить понимание базовых концепций сложности "
         "и предложить дополнительные материалы по O-нотации."),
        (student_objects[7], None,
         "Положительная динамика! Студент улучшает результаты от темы к теме. "
         "Рекомендуется поддержать мотивацию и предложить задачи повышенной сложности."),
    ]
    for student, topic, rec in adaptations_data:
        al = AdaptationLog(
            student_id=student.id,
            topic_id=topic.id if topic else None,
            recommendation=rec,
            ai_generated=True,
            created_at=now - timedelta(hours=random.randint(0, 36)),
        )
        db.session.add(al)

    # ── Orchestrator Logs ─────────────────────────────────────────
    orch_events = [
        ("student_risk", "MonitoringAgent", "AdaptationAgent",
         student_objects[4],
         {"student": "Морозов И.К.", "score": 27.5},
         "Обнаружен риск. Направлено задание AdaptationAgent на генерацию рекомендаций."),
        ("student_risk", "MonitoringAgent", "NotificationAgent",
         student_objects[4],
         {"student": "Морозов И.К.", "score": 27.5},
         "Создано уведомление для преподавателя о студенте в зоне риска."),
        ("student_risk", "MonitoringAgent", "AdaptationAgent",
         student_objects[10],
         {"student": "Белов Р.Д.", "score": 13.8},
         "Критически низкий балл. Срочная генерация адаптивных рекомендаций."),
        ("student_risk", "MonitoringAgent", "NotificationAgent",
         student_objects[10],
         {"student": "Белов Р.Д.", "score": 13.8},
         "Создано срочное уведомление: студент в критической зоне."),
        ("generate_recommendations", "AdaptationAgent", None,
         student_objects[4],
         {"topics_below_threshold": ["Основы Python", "Структуры данных", "ООП в Python", "Алгоритмы"]},
         "Сгенерированы персональные рекомендации по 4 темам."),
        ("generate_recommendations", "AdaptationAgent", None,
         student_objects[5],
         {"topics_below_threshold": ["ООП в Python", "Алгоритмы"]},
         "Сильный студент с пробелами. Сгенерированы точечные рекомендации."),
        ("positive_trend", "MonitoringAgent", "AdaptationAgent",
         student_objects[7],
         {"student": "Егорова М.В.", "trend": "improving", "from": 50, "to": 85},
         "Положительная динамика. Рекомендовано повышение сложности материала."),
        ("student_risk", "MonitoringAgent", "AdaptationAgent",
         student_objects[8],
         {"student": "Павлов С.Н.", "score": 30.0, "trend": "declining"},
         "Обнаружена отрицательная динамика. Направлен запрос на адаптацию."),
        ("periodic_scan", "MonitoringAgent", None,
         None,
         {"total_students": 11, "at_risk": 4, "excellent": 2},
         "Периодический скан завершён. 4 студента в зоне риска, 2 с отличными результатами."),
        ("system_start", "OrchestratorAgent", None,
         None,
         {"agents": ["MonitoringAgent", "AdaptationAgent", "NotificationAgent"]},
         "Система агентов запущена. Все агенты активны и готовы к работе."),
    ]
    for evt_type, source, target, student, payload, decision in orch_events:
        ol = OrchestratorLog(
            event_type=evt_type,
            source_agent=source,
            target_agent=target or "",
            student_id=student.id if student else None,
            payload=json.dumps(payload, ensure_ascii=False),
            decision=decision,
            created_at=now - timedelta(hours=random.randint(0, 48)),
        )
        db.session.add(ol)

    db.session.commit()


# -------------------------------------------------------------------
#  Student Profile helpers (Trust Score, SRI, Consent)
# -------------------------------------------------------------------

def get_or_create_profile(student_id: int) -> "StudentProfile":
    """Return the StudentProfile for a student, creating it if absent."""
    profile = StudentProfile.query.filter_by(student_id=student_id).first()
    if profile is None:
        profile = StudentProfile(student_id=student_id, trust_score=50.0, sri=50.0)
        db.session.add(profile)
        db.session.commit()
    return profile


def get_or_create_consent(student_id: int) -> "ConsentProfile":
    """Return the ConsentProfile for a student, creating it if absent."""
    consent = ConsentProfile.query.filter_by(student_id=student_id).first()
    if consent is None:
        consent = ConsentProfile(student_id=student_id)
        db.session.add(consent)
        db.session.commit()
    return consent


def compute_sri(student_id: int) -> float:  # noqa: C901
    """Compute Self-Regulation Index (0–100) from three equal-weight components.

    1. Initiative  – share of quiz attempts made without a preceding recommendation.
    2. Proactivity – share of activity that happened before first monitoring alert.
    3. Request dynamics – decreasing trend of chat requests over the past two weeks.
    """
    now = datetime.utcnow()
    one_week_ago = now - timedelta(weeks=1)
    two_weeks_ago = now - timedelta(weeks=2)

    # ── Component 1: Initiative ──────────────────────────────────────────────
    answers = (
        StudentAnswer.query
        .filter_by(student_id=student_id)
        .order_by(StudentAnswer.created_at)
        .all()
    )
    recommendations = (
        AdaptationLog.query
        .filter_by(student_id=student_id)
        .order_by(AdaptationLog.created_at)
        .all()
    )
    rec_times = [r.created_at for r in recommendations]

    initiative_score = 100.0
    if answers:
        independent = 0
        for a in answers:
            preceded = any(
                a.created_at - timedelta(hours=48) <= rt <= a.created_at
                for rt in rec_times
            )
            if not preceded:
                independent += 1
        initiative_score = independent / len(answers) * 100

    # ── Component 2: Proactivity ─────────────────────────────────────────────
    alerts = (
        AgentReport.query
        .filter_by(student_id=student_id)
        .filter(AgentReport.severity.in_(["warning", "danger"]))
        .order_by(AgentReport.created_at)
        .all()
    )
    proactivity_score = 100.0
    if alerts and answers:
        first_alert_time = min(a.created_at for a in alerts)
        before = sum(1 for a in answers if a.created_at < first_alert_time)
        total_a = len(answers)
        proactivity_score = (before / total_a * 100) if total_a else 100.0

    # ── Component 3: Request dynamics ────────────────────────────────────────
    week1 = (
        ChatMessage.query
        .filter_by(student_id=student_id, role="user")
        .filter(ChatMessage.created_at >= two_weeks_ago,
                ChatMessage.created_at < one_week_ago)
        .count()
    )
    week2 = (
        ChatMessage.query
        .filter_by(student_id=student_id, role="user")
        .filter(ChatMessage.created_at >= one_week_ago)
        .count()
    )
    if week1 == 0 and week2 == 0:
        dynamics_score = 75.0   # no requests at all → relatively independent
    elif week1 == 0:
        dynamics_score = 25.0   # suddenly started asking a lot
    else:
        ratio = week2 / week1
        if ratio < 0.5:
            dynamics_score = 100.0
        elif ratio < 1.0:
            dynamics_score = 75.0
        elif ratio == 1.0:
            dynamics_score = 50.0
        elif ratio < 2.0:
            dynamics_score = 25.0
        else:
            dynamics_score = 0.0

    sri = (initiative_score + proactivity_score + dynamics_score) / 3
    return round(max(0.0, min(100.0, sri)), 1)


def update_trust_score(student_id: int, action: str, had_good_outcome: bool = False) -> float:
    """Update Trust Score after a recommendation interaction.

    action values:
      "accepted"       – student followed the recommendation
      "ignored"        – student dismissed without acting
      "self_verified"  – student resolved on their own

    Returns the new trust score.
    """
    delta_map = {
        "accepted": 3.0 if had_good_outcome else 0.0,
        "self_verified": 0.0,
        "ignored": -2.0,
    }
    delta = delta_map.get(action, 0.0)

    profile = get_or_create_profile(student_id)
    profile.trust_score = max(0.0, min(100.0, profile.trust_score + delta))
    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return profile.trust_score


# -------------------------------------------------------------------
#  Auth helpers
# -------------------------------------------------------------------

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def teacher_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "teacher":
            flash("Доступ только для преподавателей.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


# -------------------------------------------------------------------
#  Routes
# -------------------------------------------------------------------

def _register_routes(app: Flask):

    # -- Auth -------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                session["user_id"] = user.id
                session["username"] = user.username
                session["role"] = user.role
                session["full_name"] = user.full_name
                return redirect(url_for("index"))
            flash("Неверное имя пользователя или пароль.", "danger")
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            full_name = request.form.get("full_name", "").strip()
            role = request.form.get("role", "student")
            if not username or not password:
                flash("Заполните все обязательные поля.", "warning")
                return render_template("register.html")
            if User.query.filter_by(username=username).first():
                flash("Пользователь с таким именем уже существует.", "warning")
                return render_template("register.html")
            user = User(username=username, role=role, full_name=full_name or username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Регистрация прошла успешно. Войдите в систему.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # -- Index / dashboard ------------------------------------------

    @app.route("/")
    @login_required
    def index():
        if session.get("role") == "teacher":
            return redirect(url_for("teacher_dashboard"))
        return redirect(url_for("student_dashboard"))

    # -- Student views ----------------------------------------------

    @app.route("/student")
    @login_required
    def student_dashboard():
        student_id = session["user_id"]
        topics = Topic.query.order_by(Topic.created_at.desc()).all()

        # Compute per-topic stats for this student
        topic_stats = {}
        for topic in topics:
            answers = StudentAnswer.query.filter_by(
                student_id=student_id, topic_id=topic.id,
            ).all()
            if answers:
                total = len(answers)
                correct = sum(1 for a in answers if a.is_correct)
                topic_stats[topic.id] = {
                    "total": total,
                    "correct": correct,
                    "pct": round(correct / total * 100, 1),
                }

        # Adaptation recommendations for this student
        recommendations = (
            AdaptationLog.query
            .filter_by(student_id=student_id)
            .order_by(AdaptationLog.created_at.desc())
            .limit(10)
            .all()
        )

        # Load / refresh profile (Trust Score + SRI)
        profile = get_or_create_profile(student_id)
        new_sri = compute_sri(student_id)
        if profile.sri != new_sri:
            profile.sri = new_sri
            profile.updated_at = datetime.utcnow()
            db.session.commit()

        return render_template(
            "student_dashboard.html",
            topics=topics,
            topic_stats=topic_stats,
            recommendations=recommendations,
            profile=profile,
        )

    @app.route("/topic/<int:topic_id>")
    @login_required
    def view_topic(topic_id: int):
        topic = Topic.query.get_or_404(topic_id)
        return render_template("topic.html", topic=topic)

    @app.route("/quiz/<int:topic_id>", methods=["GET", "POST"])
    @login_required
    def quiz(topic_id: int):
        topic = Topic.query.get_or_404(topic_id)
        questions = Question.query.filter_by(topic_id=topic_id).all()

        if request.method == "POST":
            results = []
            for q in questions:
                chosen = request.form.get(f"q_{q.id}", "")
                is_correct = chosen.upper() == q.correct_answer.upper()
                # Save answer
                sa = StudentAnswer(
                    student_id=session["user_id"],
                    question_id=q.id,
                    topic_id=topic_id,
                    answer=chosen.upper(),
                    is_correct=is_correct,
                )
                db.session.add(sa)
                results.append({
                    "question": q,
                    "chosen": chosen.upper(),
                    "is_correct": is_correct,
                })
            db.session.commit()

            total = len(results)
            correct = sum(1 for r in results if r["is_correct"])
            return render_template(
                "quiz_results.html",
                topic=topic,
                results=results,
                total=total,
                correct=correct,
                pct=round(correct / total * 100, 1) if total else 0,
            )

        return render_template("quiz.html", topic=topic, questions=questions)

    @app.route("/student/progress")
    @login_required
    def student_progress():
        answers = (
            StudentAnswer.query
            .filter_by(student_id=session["user_id"])
            .order_by(StudentAnswer.created_at.desc())
            .all()
        )

        # Group by topic
        topic_ids = list({a.topic_id for a in answers})
        topics = {t.id: t for t in Topic.query.filter(Topic.id.in_(topic_ids)).all()} if topic_ids else {}

        topic_results = {}
        for a in answers:
            t = topic_results.setdefault(a.topic_id, {"total": 0, "correct": 0, "topic": topics.get(a.topic_id)})
            t["total"] += 1
            t["correct"] += int(a.is_correct)

        for v in topic_results.values():
            v["pct"] = round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0

        overall_total = len(answers)
        overall_correct = sum(1 for a in answers if a.is_correct)
        overall_pct = round(overall_correct / overall_total * 100, 1) if overall_total else 0

        return render_template(
            "student_progress.html",
            topic_results=topic_results,
            overall_total=overall_total,
            overall_correct=overall_correct,
            overall_pct=overall_pct,
        )

    # -- Teacher views -----------------------------------------------

    @app.route("/teacher")
    @teacher_required
    def teacher_dashboard():
        topics = Topic.query.filter_by(created_by=session["user_id"]).order_by(Topic.created_at.desc()).all()
        reports = AgentReport.query.order_by(AgentReport.created_at.desc()).limit(20).all()
        unread_count = AgentReport.query.filter_by(is_read=False).count()

        # Student overview
        students = User.query.filter_by(role="student").all()
        student_stats = []
        for s in students:
            answers = StudentAnswer.query.filter_by(student_id=s.id).all()
            total = len(answers)
            correct = sum(1 for a in answers if a.is_correct)
            pct = round(correct / total * 100, 1) if total else None
            profile = get_or_create_profile(s.id)
            student_stats.append({"student": s, "total": total, "correct": correct, "pct": pct, "profile": profile})

        return render_template(
            "teacher_dashboard.html",
            topics=topics,
            reports=reports,
            unread_count=unread_count,
            student_stats=student_stats,
        )

    @app.route("/teacher/topic/create", methods=["GET", "POST"])
    @teacher_required
    def create_topic():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            difficulty = int(request.form.get("difficulty", 1))
            if not title:
                flash("Название темы обязательно.", "warning")
                return render_template("create_topic.html")
            topic = Topic(
                title=title,
                description=description,
                difficulty=difficulty,
                created_by=session["user_id"],
            )
            db.session.add(topic)
            db.session.commit()
            flash("Тема создана успешно.", "success")
            return redirect(url_for("manage_topic", topic_id=topic.id))
        return render_template("create_topic.html")

    @app.route("/teacher/topic/<int:topic_id>")
    @teacher_required
    def manage_topic(topic_id: int):
        topic = Topic.query.get_or_404(topic_id)
        questions = Question.query.filter_by(topic_id=topic_id).all()
        return render_template("manage_topic.html", topic=topic, questions=questions)

    @app.route("/teacher/topic/<int:topic_id>/question/add", methods=["GET", "POST"])
    @teacher_required
    def add_question(topic_id: int):
        topic = Topic.query.get_or_404(topic_id)
        if request.method == "POST":
            q = Question(
                topic_id=topic_id,
                text=request.form.get("text", "").strip(),
                option_a=request.form.get("option_a", "").strip(),
                option_b=request.form.get("option_b", "").strip(),
                option_c=request.form.get("option_c", "").strip(),
                option_d=request.form.get("option_d", "").strip(),
                correct_answer=request.form.get("correct_answer", "A").upper(),
                explanation=request.form.get("explanation", "").strip(),
            )
            if not q.text or not q.option_a:
                flash("Заполните как минимум текст вопроса и вариант A.", "warning")
                return render_template("add_question.html", topic=topic)
            db.session.add(q)
            db.session.commit()
            flash("Вопрос добавлен.", "success")
            return redirect(url_for("manage_topic", topic_id=topic_id))
        return render_template("add_question.html", topic=topic)

    @app.route("/teacher/reports")
    @teacher_required
    def teacher_reports():
        reports = AgentReport.query.order_by(AgentReport.created_at.desc()).all()
        # Mark all as read
        AgentReport.query.filter_by(is_read=False).update({"is_read": True})
        db.session.commit()
        return render_template("reports.html", reports=reports)

    @app.route("/teacher/adaptations")
    @teacher_required
    def teacher_adaptations():
        adaptations = (
            AdaptationLog.query
            .order_by(AdaptationLog.created_at.desc())
            .limit(50)
            .all()
        )
        return render_template("adaptations.html", adaptations=adaptations)

    @app.route("/teacher/student/<int:student_id>")
    @teacher_required
    def student_detail(student_id: int):
        student = User.query.get_or_404(student_id)
        answers = (
            StudentAnswer.query
            .filter_by(student_id=student_id)
            .order_by(StudentAnswer.created_at.desc())
            .all()
        )

        topic_ids = list({a.topic_id for a in answers})
        topics = {t.id: t for t in Topic.query.filter(Topic.id.in_(topic_ids)).all()} if topic_ids else {}

        topic_results = {}
        for a in answers:
            t = topic_results.setdefault(a.topic_id, {"total": 0, "correct": 0, "topic": topics.get(a.topic_id)})
            t["total"] += 1
            t["correct"] += int(a.is_correct)
        for v in topic_results.values():
            v["pct"] = round(v["correct"] / v["total"] * 100, 1) if v["total"] else 0

        reports = AgentReport.query.filter_by(student_id=student_id).order_by(AgentReport.created_at.desc()).all()
        adaptations = AdaptationLog.query.filter_by(student_id=student_id).order_by(AdaptationLog.created_at.desc()).all()

        overall_total = len(answers)
        overall_correct = sum(1 for a in answers if a.is_correct)
        overall_pct = round(overall_correct / overall_total * 100, 1) if overall_total else 0

        profile = get_or_create_profile(student_id)
        consent = get_or_create_consent(student_id)

        return render_template(
            "student_detail.html",
            student=student,
            topic_results=topic_results,
            reports=reports,
            adaptations=adaptations,
            overall_total=overall_total,
            overall_correct=overall_correct,
            overall_pct=overall_pct,
            profile=profile,
            consent=consent,
        )

    # -- AI: Chat assistant for students --------------------------------

    @app.route("/student/chat", methods=["GET"])
    @login_required
    def student_chat():
        topics = Topic.query.order_by(Topic.title).all()
        topic_id = request.args.get("topic_id", type=int)
        topic = Topic.query.get(topic_id) if topic_id else None

        messages = []
        if topic_id:
            messages = (
                ChatMessage.query
                .filter_by(student_id=session["user_id"], topic_id=topic_id)
                .order_by(ChatMessage.created_at)
                .all()
            )

        return render_template(
            "student_chat.html",
            topics=topics,
            current_topic=topic,
            messages=messages,
        )

    @app.route("/student/chat/send", methods=["POST"])
    @login_required
    def student_chat_send():
        topic_id = request.form.get("topic_id", type=int)
        question_text = request.form.get("message", "").strip()

        if not question_text:
            flash("Введите вопрос.", "warning")
            return redirect(url_for("student_chat", topic_id=topic_id))

        topic = Topic.query.get(topic_id) if topic_id else None
        topic_title = topic.title if topic else None

        # Save user message
        user_msg = ChatMessage(
            student_id=session["user_id"],
            topic_id=topic_id,
            role="user",
            content=question_text,
        )
        db.session.add(user_msg)

        # Get conversation history for context
        history = (
            ChatMessage.query
            .filter_by(student_id=session["user_id"], topic_id=topic_id)
            .order_by(ChatMessage.created_at)
            .all()
        )
        conversation = [{"role": m.role, "content": m.content} for m in history]

        # Get AI answer
        answer = ai_service.chat_answer(
            student_question=question_text,
            topic_title=topic_title,
            conversation_history=conversation,
        )

        # Save assistant message
        assistant_msg = ChatMessage(
            student_id=session["user_id"],
            topic_id=topic_id,
            role="assistant",
            content=answer,
        )
        db.session.add(assistant_msg)
        db.session.commit()

        return redirect(url_for("student_chat", topic_id=topic_id))

    # -- Student profile: Trust Score, SRI, Consent ----------------------

    @app.route("/student/profile")
    @login_required
    def student_profile():
        student_id = session["user_id"]
        profile = get_or_create_profile(student_id)
        consent = get_or_create_consent(student_id)
        # Refresh SRI on every visit
        new_sri = compute_sri(student_id)
        if profile.sri != new_sri:
            profile.sri = new_sri
            profile.updated_at = datetime.utcnow()
            db.session.commit()

        interactions = (
            RecommendationInteraction.query
            .filter_by(student_id=student_id)
            .order_by(RecommendationInteraction.created_at.desc())
            .limit(10)
            .all()
        )
        return render_template(
            "student_profile.html",
            profile=profile,
            consent=consent,
            interactions=interactions,
        )

    @app.route("/student/consent", methods=["POST"])
    @login_required
    def update_consent():
        student_id = session["user_id"]
        consent = get_or_create_consent(student_id)
        consent.behavioral_analytics = bool(request.form.get("behavioral_analytics"))
        consent.team_data = bool(request.form.get("team_data"))
        consent.engagement_index = bool(request.form.get("engagement_index"))
        consent.updated_at = datetime.utcnow()
        db.session.commit()

        # If trust score is high enough → suggest expanding consent
        profile = get_or_create_profile(student_id)
        if profile.trust_score >= 67:
            flash(
                "Профиль согласия обновлён. Ваш высокий Trust Score позволяет расширить доступ к данным.",
                "success",
            )
        else:
            flash("Профиль согласия обновлён.", "success")
        return redirect(url_for("student_profile"))

    @app.route("/student/recommendation/<int:adaptation_id>/interact", methods=["POST"])
    @login_required
    def recommendation_interact(adaptation_id: int):
        """Record student's response to a recommendation and update Trust Score."""
        student_id = session["user_id"]
        action = request.form.get("action", "ignored")
        if action not in ("accepted", "ignored", "self_verified"):
            action = "ignored"

        adaptation = AdaptationLog.query.get_or_404(adaptation_id)
        if adaptation.student_id != student_id:
            flash("Нет доступа.", "danger")
            return redirect(url_for("student_dashboard"))

        # Determine outcome: compare score before/after the recommendation
        had_good_outcome = False
        if action == "accepted":
            topic_id = adaptation.topic_id
            if topic_id:
                answers_after = (
                    StudentAnswer.query
                    .filter_by(student_id=student_id, topic_id=topic_id)
                    .filter(StudentAnswer.created_at > adaptation.created_at)
                    .all()
                )
                if answers_after:
                    correct = sum(1 for a in answers_after if a.is_correct)
                    pct = correct / len(answers_after) * 100
                    had_good_outcome = pct >= 60

        new_trust = update_trust_score(student_id, action, had_good_outcome)

        interaction = RecommendationInteraction(
            student_id=student_id,
            adaptation_log_id=adaptation_id,
            action=action,
            trust_delta=(3.0 if (action == "accepted" and had_good_outcome)
                         else (-2.0 if action == "ignored" else 0.0)),
        )
        db.session.add(interaction)
        db.session.commit()

        labels = {
            "accepted": "принята",
            "ignored": "проигнорирована",
            "self_verified": "верифицирована самостоятельно",
        }
        flash(
            f"Рекомендация {labels[action]}. Trust Score: {new_trust:.1f}.",
            "info",
        )
        return redirect(url_for("student_dashboard"))

    # -- Student: Group Projects ------------------------------------------

    @app.route("/student/projects")
    @login_required
    def student_projects():
        student_id = session["user_id"]
        all_projects = Project.query.filter_by(status="active").order_by(Project.created_at.desc()).all()
        my_memberships = {m.project_id for m in ProjectMembership.query.filter_by(student_id=student_id).all()}
        return render_template(
            "student_projects.html",
            projects=all_projects,
            my_memberships=my_memberships,
        )

    @app.route("/student/project/<int:project_id>")
    @login_required
    def student_project_detail(project_id: int):
        project = Project.query.get_or_404(project_id)
        student_id = session["user_id"]
        membership = ProjectMembership.query.filter_by(
            project_id=project_id, student_id=student_id
        ).first()
        members = (
            ProjectMembership.query
            .filter_by(project_id=project_id)
            .all()
        )
        # Trust Score-aware view: only show full team data if consent allows
        member_profiles = {}
        for m in members:
            consent = get_or_create_consent(m.student_id)
            profile = get_or_create_profile(m.student_id)
            member_profiles[m.student_id] = {
                "profile": profile,
                "consent": consent,
                "show_details": consent.team_data or m.student_id == student_id,
            }
        return render_template(
            "project_detail.html",
            project=project,
            membership=membership,
            members=members,
            member_profiles=member_profiles,
        )

    @app.route("/student/project/<int:project_id>/join", methods=["POST"])
    @login_required
    def join_project(project_id: int):
        student_id = session["user_id"]
        project = Project.query.get_or_404(project_id)
        if project.status != "active":
            flash("Проект недоступен для вступления.", "warning")
            return redirect(url_for("student_projects"))
        if ProjectMembership.query.filter_by(project_id=project_id, student_id=student_id).first():
            flash("Вы уже участник этого проекта.", "info")
            return redirect(url_for("student_project_detail", project_id=project_id))
        current_count = ProjectMembership.query.filter_by(project_id=project_id).count()
        if current_count >= project.max_members:
            flash("Группа уже заполнена.", "warning")
            return redirect(url_for("student_projects"))
        membership = ProjectMembership(project_id=project_id, student_id=student_id)
        db.session.add(membership)
        db.session.commit()
        flash(f"Вы вступили в проект «{project.title}».", "success")
        return redirect(url_for("student_project_detail", project_id=project_id))

    @app.route("/student/project/<int:project_id>/leave", methods=["POST"])
    @login_required
    def leave_project(project_id: int):
        student_id = session["user_id"]
        membership = ProjectMembership.query.filter_by(
            project_id=project_id, student_id=student_id
        ).first_or_404()
        db.session.delete(membership)
        db.session.commit()
        flash("Вы вышли из проекта.", "info")
        return redirect(url_for("student_projects"))

    @app.route("/student/project/<int:project_id>/task/<int:task_id>/update", methods=["POST"])
    @login_required
    def update_task(project_id: int, task_id: int):
        student_id = session["user_id"]
        membership = ProjectMembership.query.filter_by(
            project_id=project_id, student_id=student_id
        ).first()
        if not membership:
            flash("Вы не участник этого проекта.", "danger")
            return redirect(url_for("student_projects"))
        task = ProjectTask.query.filter_by(id=task_id, project_id=project_id).first_or_404()
        new_status = request.form.get("status", task.status)
        if new_status in ("pending", "in_progress", "done"):
            task.status = new_status
            if new_status == "done" and task.completed_at is None:
                task.completed_at = datetime.utcnow()
            db.session.commit()
            flash("Статус задачи обновлён.", "success")
        return redirect(url_for("student_project_detail", project_id=project_id))

    # -- Teacher: Projects ------------------------------------------------

    @app.route("/teacher/projects")
    @teacher_required
    def teacher_projects():
        projects = Project.query.order_by(Project.created_at.desc()).all()
        project_stats = []
        for p in projects:
            member_count = ProjectMembership.query.filter_by(project_id=p.id).count()
            task_count = ProjectTask.query.filter_by(project_id=p.id).count()
            done_count = ProjectTask.query.filter_by(project_id=p.id, status="done").count()
            project_stats.append({
                "project": p,
                "member_count": member_count,
                "task_count": task_count,
                "done_count": done_count,
            })
        return render_template("teacher_projects.html", project_stats=project_stats)

    @app.route("/teacher/project/create", methods=["GET", "POST"])
    @teacher_required
    def create_project():
        topics = Topic.query.order_by(Topic.title).all()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            topic_id = request.form.get("topic_id", type=int)
            max_members = request.form.get("max_members", 5, type=int)
            deadline_str = request.form.get("deadline", "").strip()
            if not title:
                flash("Название проекта обязательно.", "warning")
                return render_template("create_project.html", topics=topics)
            deadline = None
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                except ValueError:
                    flash("Неверный формат даты.", "warning")
                    return render_template("create_project.html", topics=topics)
            project = Project(
                title=title,
                description=description,
                created_by=session["user_id"],
                topic_id=topic_id or None,
                max_members=max(2, min(max_members, 20)),
                deadline=deadline,
            )
            db.session.add(project)
            db.session.commit()
            flash(f"Проект «{title}» создан.", "success")
            return redirect(url_for("teacher_project_detail", project_id=project.id))
        return render_template("create_project.html", topics=topics)

    @app.route("/teacher/project/<int:project_id>")
    @teacher_required
    def teacher_project_detail(project_id: int):
        project = Project.query.get_or_404(project_id)
        members = ProjectMembership.query.filter_by(project_id=project_id).all()
        tasks = ProjectTask.query.filter_by(project_id=project_id).order_by(ProjectTask.created_at).all()
        students = User.query.filter_by(role="student").all()
        # Compute per-member profiles for team Trust Score / SRI / consent view
        member_profiles = {}
        for m in members:
            profile = get_or_create_profile(m.student_id)
            consent = get_or_create_consent(m.student_id)
            member_profiles[m.student_id] = {"profile": profile, "consent": consent}
        # Team Trust Score = minimum among members (per spec)
        team_trust = (
            min(mp["profile"].trust_score for mp in member_profiles.values())
            if member_profiles else None
        )
        return render_template(
            "teacher_project_detail.html",
            project=project,
            members=members,
            tasks=tasks,
            students=students,
            member_profiles=member_profiles,
            team_trust=team_trust,
        )

    @app.route("/teacher/project/<int:project_id>/task/add", methods=["POST"])
    @teacher_required
    def add_project_task(project_id: int):
        Project.query.get_or_404(project_id)
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        assigned_to = request.form.get("assigned_to", type=int)
        if not title:
            flash("Название задачи обязательно.", "warning")
            return redirect(url_for("teacher_project_detail", project_id=project_id))
        task = ProjectTask(
            project_id=project_id,
            title=title,
            description=description,
            assigned_to=assigned_to or None,
        )
        db.session.add(task)
        db.session.commit()
        flash("Задача добавлена.", "success")
        return redirect(url_for("teacher_project_detail", project_id=project_id))

    @app.route("/teacher/project/<int:project_id>/status", methods=["POST"])
    @teacher_required
    def update_project_status(project_id: int):
        project = Project.query.get_or_404(project_id)
        new_status = request.form.get("status", project.status)
        if new_status in ("active", "completed", "archived"):
            project.status = new_status
            db.session.commit()
            flash("Статус проекта обновлён.", "success")
        return redirect(url_for("teacher_project_detail", project_id=project_id))

    # -- AI: Question generation for teachers ---------------------------

    @app.route("/teacher/topic/<int:topic_id>/generate", methods=["GET", "POST"])
    @teacher_required
    def generate_questions(topic_id: int):
        topic = Topic.query.get_or_404(topic_id)

        if request.method == "POST":
            count = int(request.form.get("count", 3))
            count = max(1, min(count, 10))

            generated = ai_service.generate_questions(
                topic_title=topic.title,
                topic_description=topic.description,
                count=count,
                difficulty=topic.difficulty,
            )

            if request.form.get("save") == "1":
                saved = 0
                for q_data in generated:
                    if q_data["text"] and q_data["option_a"]:
                        q = Question(
                            topic_id=topic_id,
                            text=q_data["text"],
                            option_a=q_data["option_a"],
                            option_b=q_data["option_b"],
                            option_c=q_data["option_c"],
                            option_d=q_data["option_d"],
                            correct_answer=q_data["correct_answer"],
                            explanation=q_data.get("explanation", ""),
                        )
                        db.session.add(q)
                        saved += 1
                db.session.commit()
                flash(f"Сохранено {saved} вопросов.", "success")
                return redirect(url_for("manage_topic", topic_id=topic_id))

            return render_template(
                "generate_questions.html",
                topic=topic,
                generated=generated,
                count=count,
            )

        return render_template("generate_questions.html", topic=topic, generated=None, count=3)

    # -- AI: Error pattern analysis for teachers ------------------------

    @app.route("/teacher/student/<int:student_id>/analysis")
    @teacher_required
    def student_analysis(student_id: int):
        student = User.query.get_or_404(student_id)
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
                "topic_title": topic.title if topic else f"Тема {tid}",
                "total": st["total"],
                "correct": st["correct"],
                "pct": round(pct, 1),
            })

        analysis = ai_service.analyze_error_patterns(
            student_name=student.full_name or student.username,
            topic_results=topic_results,
        )

        return render_template(
            "student_analysis.html",
            student=student,
            topic_results=topic_results,
            analysis=analysis,
        )

    # -- Orchestrator log for teachers ----------------------------------

    @app.route("/teacher/orchestrator")
    @teacher_required
    def orchestrator_log():
        logs = (
            OrchestratorLog.query
            .order_by(OrchestratorLog.created_at.desc())
            .limit(50)
            .all()
        )
        return render_template("orchestrator_log.html", logs=logs)
