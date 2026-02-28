"""
Flask web application for the LMS.
"""

from __future__ import annotations

import functools
from datetime import datetime

from flask import (
    Flask,
    flash,
    jsonify,
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
    OrchestratorLog,
    Question,
    StudentAnswer,
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
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"timeout": 30, "check_same_thread": False},
        "pool_pre_ping": True,
    }

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_demo_data()

    _register_routes(app)
    return app


# -------------------------------------------------------------------
#  Demo data
# -------------------------------------------------------------------

def _seed_demo_data():
    if User.query.first() is not None:
        return

    teacher = User(username="teacher", role="teacher", full_name="Иванов И.И.")
    teacher.set_password("teacher")
    db.session.add(teacher)

    student = User(username="student", role="student", full_name="Петров П.П.")
    student.set_password("student")
    db.session.add(student)

    db.session.flush()

    # ------------------------------------------------------------------
    #  Topic 1: Основы Python
    # ------------------------------------------------------------------
    topic1 = Topic(
        title="Основы Python",
        description="Базовые конструкции языка Python: переменные, типы данных, условия, циклы.",
        difficulty=1,
        created_by=teacher.id,
    )
    db.session.add(topic1)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic1.id, text="Какой тип данных возвращает функция input()?",
            option_a="int", option_b="str", option_c="float", option_d="bool",
            correct_answer="B", explanation="Функция input() всегда возвращает строку (str).",
        ),
        Question(
            topic_id=topic1.id, text="Как объявить список в Python?",
            option_a="list = (1,2,3)", option_b="list = {1,2,3}",
            option_c="list = [1,2,3]", option_d="list = <1,2,3>",
            correct_answer="C", explanation="Списки объявляются с помощью квадратных скобок [].",
        ),
        Question(
            topic_id=topic1.id, text="Какой оператор используется для целочисленного деления?",
            option_a="/", option_b="//", option_c="%", option_d="**",
            correct_answer="B", explanation="Оператор // выполняет целочисленное деление.",
        ),
        Question(
            topic_id=topic1.id, text="Что выведет print(type(3.14))?",
            option_a="<class 'int'>", option_b="<class 'str'>",
            option_c="<class 'float'>", option_d="<class 'double'>",
            correct_answer="C", explanation="Число 3.14 — вещественное, его тип float.",
        ),
        Question(
            topic_id=topic1.id, text="Как правильно написать условие в Python?",
            option_a="if x == 5:", option_b="if (x == 5) then",
            option_c="if x = 5:", option_d="if x == 5 then:",
            correct_answer="A", explanation="В Python условие записывается как if выражение: (с двоеточием).",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 2: Функции и модули Python
    # ------------------------------------------------------------------
    topic2 = Topic(
        title="Функции и модули Python",
        description="Определение функций, аргументы, возвращаемые значения, импорт модулей.",
        difficulty=2,
        created_by=teacher.id,
    )
    db.session.add(topic2)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic2.id, text="Какое ключевое слово используется для определения функции?",
            option_a="function", option_b="def", option_c="func", option_d="define",
            correct_answer="B", explanation="В Python функции определяются с помощью ключевого слова def.",
        ),
        Question(
            topic_id=topic2.id, text="Что вернёт функция, если в ней нет оператора return?",
            option_a="0", option_b="Пустую строку", option_c="None", option_d="Ошибку",
            correct_answer="C", explanation="Функция без return возвращает None.",
        ),
        Question(
            topic_id=topic2.id, text="Как импортировать только функцию sqrt из модуля math?",
            option_a="import sqrt from math", option_b="from math import sqrt",
            option_c="import math.sqrt", option_d="using math import sqrt",
            correct_answer="B", explanation="Синтаксис: from модуль import имя.",
        ),
        Question(
            topic_id=topic2.id, text="Что такое *args в определении функции?",
            option_a="Обязательные аргументы", option_b="Именованные аргументы",
            option_c="Произвольное количество позиционных аргументов", option_d="Аргументы по умолчанию",
            correct_answer="C", explanation="*args позволяет передать произвольное количество позиционных аргументов.",
        ),
        Question(
            topic_id=topic2.id, text="Какая функция возвращает длину списка?",
            option_a="size()", option_b="count()", option_c="length()", option_d="len()",
            correct_answer="D", explanation="Встроенная функция len() возвращает длину последовательности.",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 3: ООП в Python
    # ------------------------------------------------------------------
    topic3 = Topic(
        title="ООП в Python",
        description="Классы, объекты, наследование, инкапсуляция, полиморфизм.",
        difficulty=2,
        created_by=teacher.id,
    )
    db.session.add(topic3)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic3.id, text="Какой метод вызывается при создании объекта класса?",
            option_a="__start__", option_b="__create__", option_c="__init__", option_d="__new__",
            correct_answer="C", explanation="Метод __init__ — конструктор, вызывается при создании экземпляра.",
        ),
        Question(
            topic_id=topic3.id, text="Что означает параметр self в методах класса?",
            option_a="Ссылка на класс", option_b="Ссылка на текущий экземпляр объекта",
            option_c="Ключевое слово Python", option_d="Имя переменной",
            correct_answer="B", explanation="self — ссылка на текущий экземпляр объекта.",
        ),
        Question(
            topic_id=topic3.id, text="Как обозначается наследование в Python?",
            option_a="class Dog extends Animal:", option_b="class Dog(Animal):",
            option_c="class Dog inherits Animal:", option_d="class Dog <- Animal:",
            correct_answer="B", explanation="Наследование указывается в скобках: class Потомок(Родитель).",
        ),
        Question(
            topic_id=topic3.id, text="Что такое инкапсуляция?",
            option_a="Множественное наследование", option_b="Сокрытие внутренней реализации",
            option_c="Перегрузка операторов", option_d="Создание интерфейсов",
            correct_answer="B", explanation="Инкапсуляция — сокрытие деталей реализации от внешнего кода.",
        ),
        Question(
            topic_id=topic3.id, text="Какой декоратор делает метод статическим?",
            option_a="@classmethod", option_b="@static", option_c="@staticmethod", option_d="@method",
            correct_answer="C", explanation="Декоратор @staticmethod делает метод статическим.",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 4: Базы данных и SQL
    # ------------------------------------------------------------------
    topic4 = Topic(
        title="Базы данных и SQL",
        description="Основы реляционных баз данных, SQL-запросы: SELECT, INSERT, UPDATE, DELETE, JOIN.",
        difficulty=2,
        created_by=teacher.id,
    )
    db.session.add(topic4)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic4.id, text="Какой оператор SQL используется для выборки данных?",
            option_a="GET", option_b="FETCH", option_c="SELECT", option_d="EXTRACT",
            correct_answer="C", explanation="Оператор SELECT используется для выборки данных из таблицы.",
        ),
        Question(
            topic_id=topic4.id, text="Какой тип JOIN возвращает только совпадающие записи?",
            option_a="LEFT JOIN", option_b="RIGHT JOIN", option_c="FULL JOIN", option_d="INNER JOIN",
            correct_answer="D", explanation="INNER JOIN возвращает только те строки, которые есть в обеих таблицах.",
        ),
        Question(
            topic_id=topic4.id, text="Какой оператор используется для фильтрации групп в SQL?",
            option_a="WHERE", option_b="HAVING", option_c="FILTER", option_d="GROUP BY",
            correct_answer="B", explanation="HAVING фильтрует результаты после группировки (GROUP BY).",
        ),
        Question(
            topic_id=topic4.id, text="Что такое первичный ключ (PRIMARY KEY)?",
            option_a="Любой столбец таблицы", option_b="Уникальный идентификатор записи",
            option_c="Внешняя ссылка на другую таблицу", option_d="Индекс для ускорения запросов",
            correct_answer="B", explanation="PRIMARY KEY — уникальный идентификатор каждой записи в таблице.",
        ),
        Question(
            topic_id=topic4.id, text="Какой командой добавляется новая запись в таблицу?",
            option_a="ADD INTO", option_b="INSERT INTO", option_c="PUT INTO", option_d="CREATE ROW",
            correct_answer="B", explanation="INSERT INTO используется для добавления новых записей.",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 5: Веб-разработка (HTML/CSS)
    # ------------------------------------------------------------------
    topic5 = Topic(
        title="Веб-разработка: HTML и CSS",
        description="Структура HTML-документа, основные теги, CSS-селекторы, flexbox, позиционирование.",
        difficulty=1,
        created_by=teacher.id,
    )
    db.session.add(topic5)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic5.id, text="Какой тег является корневым элементом HTML-документа?",
            option_a="<body>", option_b="<head>", option_c="<html>", option_d="<doctype>",
            correct_answer="C", explanation="Тег <html> — корневой элемент HTML-документа.",
        ),
        Question(
            topic_id=topic5.id, text="Какое CSS-свойство меняет цвет текста?",
            option_a="text-color", option_b="font-color", option_c="color", option_d="text-style",
            correct_answer="C", explanation="Свойство color задаёт цвет текста.",
        ),
        Question(
            topic_id=topic5.id, text="Что делает display: flex?",
            option_a="Скрывает элемент", option_b="Делает элемент блочным",
            option_c="Включает flex-контейнер", option_d="Фиксирует элемент на странице",
            correct_answer="C", explanation="display: flex превращает элемент в flex-контейнер для гибкой разметки.",
        ),
        Question(
            topic_id=topic5.id, text="Какой тег используется для создания ссылки?",
            option_a="<link>", option_b="<a>", option_c="<href>", option_d="<url>",
            correct_answer="B", explanation="Тег <a> (anchor) создаёт гиперссылку.",
        ),
        Question(
            topic_id=topic5.id, text="Какой CSS-селектор выбирает элемент по id?",
            option_a=".myid", option_b="#myid", option_c="*myid", option_d="@myid",
            correct_answer="B", explanation="Селектор #id выбирает элемент с указанным идентификатором.",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 6: Компьютерные сети
    # ------------------------------------------------------------------
    topic6 = Topic(
        title="Компьютерные сети",
        description="Модель OSI, протоколы TCP/IP, HTTP, DNS, маршрутизация и адресация.",
        difficulty=3,
        created_by=teacher.id,
    )
    db.session.add(topic6)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic6.id, text="Сколько уровней в модели OSI?",
            option_a="4", option_b="5", option_c="6", option_d="7",
            correct_answer="D", explanation="Модель OSI состоит из 7 уровней.",
        ),
        Question(
            topic_id=topic6.id, text="Какой протокол используется для разрешения доменных имён?",
            option_a="HTTP", option_b="FTP", option_c="DNS", option_d="SMTP",
            correct_answer="C", explanation="DNS (Domain Name System) преобразует доменные имена в IP-адреса.",
        ),
        Question(
            topic_id=topic6.id, text="На каком уровне OSI работает протокол TCP?",
            option_a="Сетевой", option_b="Транспортный", option_c="Канальный", option_d="Прикладной",
            correct_answer="B", explanation="TCP работает на транспортном (4-м) уровне модели OSI.",
        ),
        Question(
            topic_id=topic6.id, text="Какой HTTP-метод используется для получения данных?",
            option_a="POST", option_b="PUT", option_c="GET", option_d="PATCH",
            correct_answer="C", explanation="Метод GET запрашивает данные с сервера.",
        ),
        Question(
            topic_id=topic6.id, text="Какой порт по умолчанию использует HTTPS?",
            option_a="80", option_b="8080", option_c="443", option_d="22",
            correct_answer="C", explanation="HTTPS использует порт 443 по умолчанию.",
        ),
    ])

    # ------------------------------------------------------------------
    #  Topic 7: Алгоритмы и структуры данных
    # ------------------------------------------------------------------
    topic7 = Topic(
        title="Алгоритмы и структуры данных",
        description="Сложность алгоритмов, сортировки, поиск, стеки, очереди, деревья, графы.",
        difficulty=3,
        created_by=teacher.id,
    )
    db.session.add(topic7)
    db.session.flush()

    db.session.add_all([
        Question(
            topic_id=topic7.id, text="Какова сложность бинарного поиска?",
            option_a="O(n)", option_b="O(n²)", option_c="O(log n)", option_d="O(1)",
            correct_answer="C", explanation="Бинарный поиск делит массив пополам, сложность O(log n).",
        ),
        Question(
            topic_id=topic7.id, text="Какая структура данных работает по принципу LIFO?",
            option_a="Очередь", option_b="Стек", option_c="Список", option_d="Дерево",
            correct_answer="B", explanation="Стек (stack) работает по принципу Last In, First Out.",
        ),
        Question(
            topic_id=topic7.id, text="Какова средняя сложность быстрой сортировки (Quick Sort)?",
            option_a="O(n)", option_b="O(n log n)", option_c="O(n²)", option_d="O(log n)",
            correct_answer="B", explanation="Средняя сложность Quick Sort — O(n log n).",
        ),
        Question(
            topic_id=topic7.id, text="Что такое хеш-таблица?",
            option_a="Отсортированный массив", option_b="Двусвязный список",
            option_c="Структура с доступом по ключу за O(1)", option_d="Бинарное дерево поиска",
            correct_answer="C", explanation="Хеш-таблица обеспечивает доступ к данным по ключу в среднем за O(1).",
        ),
        Question(
            topic_id=topic7.id, text="Какой алгоритм находит кратчайший путь в графе?",
            option_a="Bubble Sort", option_b="DFS", option_c="Алгоритм Дейкстры", option_d="Merge Sort",
            correct_answer="C", explanation="Алгоритм Дейкстры находит кратчайший путь от одной вершины до всех остальных.",
        ),
    ])

    db.session.commit()


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
        topics = Topic.query.order_by(Topic.created_at.desc()).all()

        # Compute per-topic stats for this student
        topic_stats = {}
        for topic in topics:
            answers = StudentAnswer.query.filter_by(
                student_id=session["user_id"], topic_id=topic.id,
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
            .filter_by(student_id=session["user_id"])
            .order_by(AdaptationLog.created_at.desc())
            .limit(10)
            .all()
        )

        return render_template(
            "student_dashboard.html",
            topics=topics,
            topic_stats=topic_stats,
            recommendations=recommendations,
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
            student_stats.append({"student": s, "total": total, "correct": correct, "pct": pct})

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

        return render_template(
            "student_detail.html",
            student=student,
            topic_results=topic_results,
            reports=reports,
            adaptations=adaptations,
            overall_total=overall_total,
            overall_correct=overall_correct,
            overall_pct=overall_pct,
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
        is_ajax = request.is_json
        if is_ajax:
            data = request.get_json()
            topic_id = data.get("topic_id")
            question_text = (data.get("message") or "").strip()
        else:
            topic_id = request.form.get("topic_id", type=int)
            question_text = request.form.get("message", "").strip()

        if not question_text:
            if is_ajax:
                return jsonify({"error": "Введите вопрос."}), 400
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

        if is_ajax:
            from datetime import datetime as dt
            now = dt.now().strftime("%H:%M")
            return jsonify({"answer": answer, "time": now})

        return redirect(url_for("student_chat", topic_id=topic_id))

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
