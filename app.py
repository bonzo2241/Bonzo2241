"""
Flask web application for the LMS.
"""

from __future__ import annotations

import functools
from datetime import datetime

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
    Question,
    StudentAnswer,
    Topic,
    User,
    db,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

    topic = Topic(
        title="Основы Python",
        description="Базовые конструкции языка Python: переменные, типы данных, условия, циклы.",
        difficulty=1,
        created_by=teacher.id,
    )
    db.session.add(topic)
    db.session.flush()

    questions = [
        Question(
            topic_id=topic.id, text="Какой тип данных возвращает функция input()?",
            option_a="int", option_b="str", option_c="float", option_d="bool",
            correct_answer="B", explanation="Функция input() всегда возвращает строку (str).",
        ),
        Question(
            topic_id=topic.id, text="Как объявить список в Python?",
            option_a="list = (1,2,3)", option_b="list = {1,2,3}",
            option_c="list = [1,2,3]", option_d="list = <1,2,3>",
            correct_answer="C", explanation="Списки объявляются с помощью квадратных скобок [].",
        ),
        Question(
            topic_id=topic.id, text="Какой оператор используется для целочисленного деления?",
            option_a="/", option_b="//", option_c="%", option_d="**",
            correct_answer="B", explanation="Оператор // выполняет целочисленное деление.",
        ),
    ]
    db.session.add_all(questions)
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
