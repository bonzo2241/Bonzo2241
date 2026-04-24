from __future__ import annotations

from datetime import datetime, timedelta
import json

from flask import Flask

import config
from app import compute_sri
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


def make_app() -> Flask:
    flask_app = Flask(
        "lms_demo_seed",
        instance_path=config.BASE_DIR,
        root_path=config.BASE_DIR,
    )
    flask_app.config["SECRET_KEY"] = config.SECRET_KEY
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URI
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = config.SQLALCHEMY_ENGINE_OPTIONS
    db.init_app(flask_app)
    return flask_app


def seed() -> None:
    app = make_app()
    now = datetime.utcnow().replace(microsecond=0)

    with app.app_context():
        db.drop_all()
        db.create_all()
        with db.engine.connect() as conn:
            conn.execute(db.text("PRAGMA journal_mode=WAL"))
            conn.commit()

        teachers = create_users()
        topics, question_map = create_topics(teachers)
        students = create_students()
        create_answers(students, topics, question_map, now)
        adaptations = create_recommendations(students, topics, now)
        create_reports(students, now)
        create_orchestrator_logs(students, now)
        create_chats(students, topics, now)
        create_recommendation_interactions(students, adaptations, now)
        create_profiles_and_consent(students, now)
        create_projects(teachers, students, topics, now)

        for student in students.values():
            profile = StudentProfile.query.filter_by(student_id=student.id).first()
            profile.sri = compute_sri(student.id)
            profile.updated_at = now

        db.session.commit()


def create_users() -> dict[str, User]:
    teachers = {
        "teacher": User(username="teacher", role="teacher", full_name="Иванов И.И."),
        "teacher2": User(username="teacher2", role="teacher", full_name="Смирнова Е.А."),
    }
    teachers["teacher"].set_password("teacher")
    teachers["teacher2"].set_password("teacher2")
    db.session.add_all(teachers.values())
    db.session.flush()
    return teachers


def create_topics(teachers: dict[str, User]) -> tuple[dict[str, Topic], dict[str, list[Question]]]:
    topics_data = [
        {
            "key": "python",
            "title": "Основы Python",
            "description": "Переменные, типы данных, условия, циклы и базовые функции.",
            "difficulty": 1,
            "teacher": teachers["teacher"],
            "questions": [
                ("Какой тип данных возвращает input()?", "int", "str", "float", "bool", "B", "input() всегда возвращает строку."),
                ("Как обозначается список в Python?", "{}", "[]", "()", "<>", "B", "Списки создаются в квадратных скобках."),
                ("Какой оператор используется для целочисленного деления?", "/", "//", "%", "**", "B", "Оператор // выполняет целочисленное деление."),
                ("Что выведет type(3.14)?", "int", "float", "str", "decimal", "B", "3.14 имеет тип float."),
                ("Каким словом объявляют функцию?", "func", "define", "def", "lambda", "C", "Функции объявляются ключевым словом def."),
            ],
        },
        {
            "key": "data",
            "title": "Структуры данных",
            "description": "Списки, словари, множества и кортежи, их свойства и методы.",
            "difficulty": 2,
            "teacher": teachers["teacher"],
            "questions": [
                ("Какой метод добавляет элемент в конец списка?", "push()", "append()", "add()", "insert_end()", "B", "append() добавляет элемент в конец списка."),
                ("Какая структура данных неизменяема?", "list", "dict", "tuple", "set", "C", "Кортеж tuple после создания не изменяется."),
                ("Что вернет len({1, 2, 2, 3})?", "2", "3", "4", "Ошибка", "B", "Во множестве остаются только уникальные элементы."),
                ("Как получить все ключи словаря d?", "d.keys()", "d.items()", "d.values()", "d.all()", "A", "Метод keys() возвращает все ключи словаря."),
                ("Что делает оператор + для списков?", "Сортирует", "Удаляет дубликаты", "Объединяет два списка", "Делает пересечение", "C", "Оператор + создает новый объединенный список."),
            ],
        },
        {
            "key": "oop",
            "title": "ООП в Python",
            "description": "Классы, объекты, наследование, инкапсуляция и полиморфизм.",
            "difficulty": 2,
            "teacher": teachers["teacher"],
            "questions": [
                ("Как объявить класс?", "class MyClass:", "new MyClass:", "def MyClass:", "object MyClass:", "A", "Класс объявляется ключевым словом class."),
                ("Что такое self в методе класса?", "Имя класса", "Ссылка на экземпляр", "Глобальная переменная", "Декоратор", "B", "self ссылается на текущий экземпляр объекта."),
                ("Какой метод вызывается при создании объекта?", "__str__", "__init__", "__repr__", "__call__", "B", "__init__ используется как конструктор."),
                ("Как записывается наследование?", "class Child -> Parent:", "class Child: Parent", "class Child(Parent):", "class Child extends Parent:", "C", "В Python базовый класс указывается в скобках."),
                ("Что делает @staticmethod?", "Запрещает наследование", "Убирает self", "Скрывает метод", "Делает метод приватным", "B", "Статический метод не получает self."),
            ],
        },
        {
            "key": "algo",
            "title": "Алгоритмы и сложность",
            "description": "Базовые алгоритмы поиска, сортировки и оценка сложности.",
            "difficulty": 3,
            "teacher": teachers["teacher2"],
            "questions": [
                ("Какова сложность бинарного поиска?", "O(n)", "O(log n)", "O(n^2)", "O(1)", "B", "Бинарный поиск на каждом шаге делит массив пополам."),
                ("Какая средняя сложность быстрой сортировки?", "O(n)", "O(n^2)", "O(n log n)", "O(log n)", "C", "Средняя сложность quicksort равна O(n log n)."),
                ("Что такое рекурсия?", "Цикл while", "Вызов функции самой себя", "Обработка ошибок", "Работа с файлом", "B", "Рекурсия основана на самовызове функции."),
                ("Какая сложность доступа к элементу хеш-таблицы в среднем?", "O(n)", "O(1)", "O(log n)", "O(n log n)", "B", "Для хорошей хеш-функции доступ обычно O(1)."),
                ("Что характерно для жадного алгоритма?", "Перебирает все варианты", "Выбирает локально лучший шаг", "Всегда использует рекурсию", "Работает только с графами", "B", "Жадный алгоритм принимает локально оптимальные решения."),
            ],
        },
    ]

    topics: dict[str, Topic] = {}
    question_map: dict[str, list[Question]] = {}

    for topic_data in topics_data:
        topic = Topic(
            title=topic_data["title"],
            description=topic_data["description"],
            difficulty=topic_data["difficulty"],
            created_by=topic_data["teacher"].id,
        )
        db.session.add(topic)
        db.session.flush()
        topics[topic_data["key"]] = topic
        question_map[topic_data["key"]] = []
        for text, a, b, c, d, correct, explanation in topic_data["questions"]:
            question = Question(
                topic_id=topic.id,
                text=text,
                option_a=a,
                option_b=b,
                option_c=c,
                option_d=d,
                correct_answer=correct,
                explanation=explanation,
            )
            db.session.add(question)
            question_map[topic_data["key"]].append(question)

    db.session.flush()
    return topics, question_map


def create_students() -> dict[str, User]:
    student_specs = [
        ("student", "Петров П.П."),
        ("sidorova", "Сидорова А.В."),
        ("kozlov", "Козлов Д.М."),
        ("volkova", "Волкова Е.С."),
        ("morozov", "Морозов И.К."),
        ("novikova", "Новикова О.Л."),
        ("fedorov", "Федоров А.А."),
        ("egorova", "Егорова М.В."),
        ("pavlov", "Павлов С.Н."),
        ("antonova", "Антонова К.Р."),
        ("belov", "Белов Р.Д."),
    ]
    students: dict[str, User] = {}
    for username, full_name in student_specs:
        student = User(username=username, role="student", full_name=full_name)
        student.set_password(username)
        db.session.add(student)
        students[username] = student
    db.session.flush()
    return students


def add_answers(
    student: User,
    topic_key: str,
    question_map: dict[str, list[Question]],
    pattern: list[bool],
    start_at: datetime,
    gap_hours: int = 8,
) -> None:
    options = ["A", "B", "C", "D"]
    questions = question_map[topic_key]
    for idx, is_correct in enumerate(pattern):
        question = questions[idx % len(questions)]
        if is_correct:
            answer = question.correct_answer
        else:
            answer = next(opt for opt in options if opt != question.correct_answer)
        db.session.add(StudentAnswer(
            student_id=student.id,
            question_id=question.id,
            topic_id=question.topic_id,
            answer=answer,
            is_correct=is_correct,
            created_at=start_at + timedelta(hours=idx * gap_hours),
        ))


def create_answers(
    students: dict[str, User],
    topics: dict[str, Topic],
    question_map: dict[str, list[Question]],
    now: datetime,
) -> None:
    del topics
    plans = {
        "student": [
            ("python", [True, True, True, True, False], now - timedelta(days=13)),
            ("data", [True, True, True, True, False], now - timedelta(days=12)),
            ("oop", [True, True, True, True, True], now - timedelta(days=10)),
            ("algo", [True, True, True, False, True], now - timedelta(days=8)),
        ],
        "sidorova": [
            ("python", [True, True, True, True, True], now - timedelta(days=14)),
            ("data", [True, True, True, True, True], now - timedelta(days=12)),
            ("oop", [True, True, True, True, True], now - timedelta(days=9)),
            ("algo", [True, True, True, True, False], now - timedelta(days=7)),
        ],
        "kozlov": [
            ("python", [True, True, True, True, False], now - timedelta(days=13)),
            ("data", [True, True, True, False, False], now - timedelta(days=11)),
            ("oop", [True, True, False, True, False], now - timedelta(days=9)),
            ("algo", [True, False, True, False, False], now - timedelta(days=6)),
        ],
        "volkova": [
            ("python", [True, True, False, True, False], now - timedelta(days=11)),
            ("data", [True, False, True, False, False], now - timedelta(days=9)),
            ("oop", [True, False, False, True, False], now - timedelta(days=6)),
            ("algo", [False, True, False, False, False], now - timedelta(days=3)),
        ],
        "morozov": [
            ("python", [True, False, False, False, False], now - timedelta(days=10)),
            ("data", [False, False, True, False, False], now - timedelta(days=3)),
            ("oop", [False, False, False, False, True], now - timedelta(days=2, hours=12)),
            ("algo", [False, False, False, False, False], now - timedelta(days=2)),
        ],
        "novikova": [
            ("python", [True, True, True, True, True], now - timedelta(days=13)),
            ("data", [True, True, True, True, True], now - timedelta(days=11)),
            ("oop", [True, False, False, True, False], now - timedelta(days=5)),
            ("algo", [False, True, False, False, False], now - timedelta(days=4)),
        ],
        "fedorov": [
            ("python", [True, True, False, True, False], now - timedelta(days=6)),
            ("data", [True, False, False, True, False], now - timedelta(days=2)),
        ],
        "egorova": [
            ("python", [False, False, True, True, True], now - timedelta(days=13)),
            ("data", [False, True, True, True, True], now - timedelta(days=11)),
            ("oop", [False, True, True, True, True], now - timedelta(days=8)),
            ("algo", [True, True, True, True, False], now - timedelta(days=6)),
        ],
        "pavlov": [
            ("python", [True, True, True, True, False], now - timedelta(days=12)),
            ("data", [True, True, False, True, False], now - timedelta(days=10)),
            ("oop", [True, False, False, False, False], now - timedelta(days=4)),
            ("algo", [False, False, False, True, False], now - timedelta(days=2)),
        ],
        "antonova": [
            ("python", [True, True, True, False, True], now - timedelta(days=5)),
        ],
        "belov": [
            ("python", [False, False, True, False, False], now - timedelta(days=4)),
            ("data", [False, False, False, False, True], now - timedelta(days=3)),
            ("oop", [False, False, False, False, False], now - timedelta(days=2)),
            ("algo", [False, False, False, False, False], now - timedelta(days=1, hours=12)),
        ],
    }

    for username, entries in plans.items():
        for topic_key, pattern, start_at in entries:
            add_answers(students[username], topic_key, question_map, pattern, start_at)

    db.session.flush()


def add_adaptation(student: User, topic: Topic | None, text: str, created_at: datetime) -> AdaptationLog:
    adaptation = AdaptationLog(
        student_id=student.id,
        topic_id=topic.id if topic else None,
        recommendation=text,
        ai_generated=True,
        created_at=created_at,
    )
    db.session.add(adaptation)
    db.session.flush()
    return adaptation


def create_recommendations(
    students: dict[str, User],
    topics: dict[str, Topic],
    now: datetime,
) -> dict[str, list[AdaptationLog]]:
    rec_specs = {
        "student": ("data", "Рекомендуется закрепить словари и множества на короткой практике."),
        "sidorova": ("algo", "Можно переходить к задачам повышенной сложности по алгоритмам."),
        "kozlov": ("oop", "Полезно повторить наследование и конструкторы на одном практическом примере."),
        "volkova": ("algo", "Нужно визуализировать алгоритмы и еще раз пройтись по O-нотации."),
        "morozov": ("python", "Стоит вернуться к базовым конструкциям Python и пройти тему с самого начала."),
        "novikova": ("algo", "Хорошая база по Python, но алгоритмы пока требуют дополнительной тренировки."),
        "fedorov": ("data", "Следующий шаг - освоить словари, множества и основные методы списков."),
        "egorova": ("oop", "Наблюдается прогресс: можно перейти к более сложным задачам по ООП."),
        "pavlov": ("algo", "Есть спад по алгоритмам, стоит повторить базовые понятия сложности."),
        "antonova": ("data", "После первой темы логично перейти к структурам данных и закрепить списки."),
        "belov": ("python", "Нужна индивидуальная траектория: база Python и повторение самых простых упражнений."),
    }
    interaction_outcomes = {
        "student": ["accepted"] * 6,
        "sidorova": ["accepted"] * 12 + ["self_verified"],
        "kozlov": ["accepted"] * 3 + ["self_verified"],
        "volkova": ["ignored"] * 3 + ["self_verified"],
        "morozov": ["ignored"] * 13,
        "novikova": ["accepted"] * 7,
        "fedorov": ["accepted"] + ["self_verified"] * 2,
        "egorova": ["accepted"] * 9,
        "pavlov": ["ignored"] * 10,
        "antonova": ["accepted"] * 2 + ["self_verified"],
        "belov": ["ignored"] * 16,
    }
    pending_counts = {
        "student": 1,
        "morozov": 1,
        "pavlov": 1,
        "belov": 1,
        "fedorov": 1,
    }

    result: dict[str, list[AdaptationLog]] = {}
    for username, (topic_key, base_text) in rec_specs.items():
        topic = topics[topic_key]
        result[username] = []
        history = interaction_outcomes[username]
        for idx, _action in enumerate(history):
            created_at = now - timedelta(days=35 - idx * 2)
            result[username].append(add_adaptation(
                students[username],
                topic,
                f"{base_text} Рекомендация #{idx + 1}.",
                created_at,
            ))
        for idx in range(pending_counts.get(username, 0)):
            created_at = now - timedelta(hours=18 - idx * 4)
            result[username].append(add_adaptation(
                students[username],
                topic,
                f"{base_text} Новая актуальная рекомендация для демонстрации интерфейса.",
                created_at,
            ))
    return result


def create_reports(students: dict[str, User], now: datetime) -> None:
    report_specs = [
        ("morozov", "monitoring", "danger", "Студент Морозов И.К. находится в зоне риска: низкая успеваемость по базовым темам.", now - timedelta(days=7)),
        ("morozov", "notification", "danger", "Оркестратор направил преподавателю уведомление о риске по Морозову И.К.", now - timedelta(days=7, hours=-2)),
        ("belov", "monitoring", "danger", "Студент Белов Р.Д. показывает критически низкий результат и требует срочной поддержки.", now - timedelta(days=6)),
        ("belov", "notification", "danger", "Создано срочное уведомление преподавателю по Белову Р.Д.", now - timedelta(days=6, hours=-1)),
        ("pavlov", "monitoring", "warning", "У Павлова С.Н. обнаружена отрицательная динамика по алгоритмам.", now - timedelta(days=6)),
        ("pavlov", "notification", "warning", "Преподавателю отправлено уведомление о снижении результатов Павлова С.Н.", now - timedelta(days=6, hours=-1)),
        ("volkova", "monitoring", "warning", "Волкова Е.С. держится на пограничном уровне и нуждается в дополнительной практике.", now - timedelta(days=5)),
        ("sidorova", "monitoring", "info", "Сидорова А.В. показывает высокий результат и готова к усложнению материала.", now - timedelta(days=3)),
        ("egorova", "monitoring", "info", "Егорова М.В. демонстрирует положительную динамику и устойчивый рост.", now - timedelta(days=2)),
    ]
    for username, agent_type, severity, message, created_at in report_specs:
        db.session.add(AgentReport(
            agent_type=agent_type,
            student_id=students[username].id,
            message=message,
            severity=severity,
            is_read=False,
            created_at=created_at,
        ))
    db.session.flush()


def create_orchestrator_logs(students: dict[str, User], now: datetime) -> None:
    entries = [
        ("system_start", "OrchestratorAgent", "", None, {"agents": ["MonitoringAgent", "AdaptationAgent", "NotificationAgent"]}, "Система агентов запущена и готова к работе.", now - timedelta(days=10)),
        ("student_risk", "MonitoringAgent", "AdaptationAgent", students["morozov"], {"score": 24.0}, "Обнаружен риск по Морозову И.К., запрошены адаптивные рекомендации.", now - timedelta(days=7)),
        ("student_risk", "MonitoringAgent", "NotificationAgent", students["belov"], {"score": 8.0}, "По Белову Р.Д. создано срочное уведомление преподавателю.", now - timedelta(days=6)),
        ("positive_trend", "MonitoringAgent", "AdaptationAgent", students["egorova"], {"from": 46, "to": 78}, "По Егоровой М.В. зафиксирован рост, рекомендовано усложнение материала.", now - timedelta(days=2)),
        ("generate_recommendations", "AdaptationAgent", "", students["novikova"], {"weak_topics": ["ООП в Python", "Алгоритмы и сложность"]}, "Сгенерированы точечные рекомендации для сильного студента с локальными пробелами.", now - timedelta(days=4)),
    ]
    for event_type, source, target, student, payload, decision, created_at in entries:
        db.session.add(OrchestratorLog(
            event_type=event_type,
            source_agent=source,
            target_agent=target,
            student_id=student.id if student else None,
            payload=json.dumps(payload, ensure_ascii=False),
            decision=decision,
            created_at=created_at,
        ))
    db.session.flush()


def create_chats(students: dict[str, User], topics: dict[str, Topic], now: datetime) -> None:
    chat_specs = {
        "student": [
            ("user", "Нужен еще пример по словарям.", "data", now - timedelta(days=12)),
            ("assistant", "Разберем словарь с вложенными значениями.", "data", now - timedelta(days=12, hours=-1)),
            ("user", "Спасибо, теперь стало понятнее.", "data", now - timedelta(days=3)),
        ],
        "sidorova": [
            ("user", "Покажи более сложную задачу на алгоритмы.", "algo", now - timedelta(days=12)),
            ("assistant", "Сравним две стратегии поиска на большом массиве.", "algo", now - timedelta(days=12, hours=-1)),
            ("user", "Есть еще один challenge?", "algo", now - timedelta(days=4)),
        ],
        "kozlov": [
            ("user", "Не до конца понимаю наследование.", "oop", now - timedelta(days=10)),
            ("assistant", "Давайте разберем базовый пример Parent и Child.", "oop", now - timedelta(days=10, hours=-1)),
            ("user", "Теперь лучше, но нужна еще практика.", "oop", now - timedelta(days=4)),
            ("assistant", "Попробуйте добавить новый метод в дочерний класс.", "oop", now - timedelta(days=4, hours=-1)),
        ],
        "volkova": [
            ("user", "Поясни еще раз O(log n).", "algo", now - timedelta(days=11)),
            ("assistant", "Это рост, который увеличивается медленно при росте данных.", "algo", now - timedelta(days=11, hours=-1)),
            ("user", "И еще один пример по сортировкам.", "algo", now - timedelta(days=3)),
            ("assistant", "Сравним пузырьковую и быструю сортировку.", "algo", now - timedelta(days=3, hours=-1)),
        ],
        "morozov": [
            ("user", "Я снова путаю list и tuple.", "python", now - timedelta(days=10)),
            ("assistant", "Tuple не изменяется, list можно менять.", "python", now - timedelta(days=10, hours=-1)),
            ("user", "Покажи базовый пример цикла for.", "python", now - timedelta(days=3)),
            ("assistant", "Пройдем пример с числами от 1 до 5.", "python", now - timedelta(days=3, hours=-1)),
            ("user", "Мне нужна еще одна подсказка.", "python", now - timedelta(days=2)),
            ("assistant", "Сначала повторите условные операторы и цикл for.", "python", now - timedelta(days=2, hours=-1)),
            ("user", "И еще пример на input.", "python", now - timedelta(days=1)),
            ("assistant", "Давайте разберем простую программу с вводом возраста.", "python", now - timedelta(days=1, hours=-1)),
        ],
        "novikova": [
            ("user", "Напомни идею бинарного поиска.", "algo", now - timedelta(days=9)),
            ("assistant", "На каждом шаге отбрасывается половина диапазона.", "algo", now - timedelta(days=9, hours=-1)),
            ("user", "Хочу пример по полиморфизму.", "oop", now - timedelta(days=3)),
            ("assistant", "Сравним общий интерфейс для разных классов фигур.", "oop", now - timedelta(days=3, hours=-1)),
        ],
        "fedorov": [
            ("user", "Как начать тему про словари?", "data", now - timedelta(days=2)),
            ("assistant", "Начните с пар ключ-значение и метода keys().", "data", now - timedelta(days=2, hours=-1)),
            ("user", "Что повторить перед тестом?", "data", now - timedelta(days=1)),
        ],
        "egorova": [
            ("user", "Какой пример взять для наследования?", "oop", now - timedelta(days=13)),
            ("assistant", "Попробуйте пример Animal и Cat.", "oop", now - timedelta(days=13, hours=-1)),
            ("user", "Теперь я справлюсь сама.", "oop", now - timedelta(days=8)),
        ],
        "pavlov": [
            ("user", "Напомни, что означает O(1).", "algo", now - timedelta(days=10)),
            ("assistant", "Это постоянное время доступа.", "algo", now - timedelta(days=10, hours=-1)),
            ("user", "Нужен еще один пример.", "algo", now - timedelta(days=2)),
            ("assistant", "Сравним доступ по индексу и линейный поиск.", "algo", now - timedelta(days=2, hours=-1)),
            ("user", "И еще коротко по сортировкам.", "algo", now - timedelta(days=1)),
        ],
        "antonova": [
            ("user", "Что лучше повторить после первой темы?", "data", now - timedelta(days=4)),
            ("assistant", "Перейдите к спискам и словарям.", "data", now - timedelta(days=4, hours=-1)),
        ],
        "belov": [
            ("user", "Я не понимаю базовый синтаксис if.", "python", now - timedelta(days=9)),
            ("assistant", "Посмотрим простые условия на сравнение чисел.", "python", now - timedelta(days=9, hours=-1)),
            ("user", "Нужна еще помощь с циклами.", "python", now - timedelta(days=3)),
            ("assistant", "Начнем с простого цикла for по списку.", "python", now - timedelta(days=3, hours=-1)),
            ("user", "Покажи еще один самый простой пример.", "python", now - timedelta(days=2)),
            ("assistant", "Разберем ввод числа и условие if.", "python", now - timedelta(days=2, hours=-1)),
            ("user", "Я все равно путаюсь.", "python", now - timedelta(days=1)),
        ],
    }
    for username, messages in chat_specs.items():
        for role, content, topic_key, created_at in messages:
            db.session.add(ChatMessage(
                student_id=students[username].id,
                topic_id=topics[topic_key].id,
                role=role,
                content=content,
                created_at=created_at,
            ))
    db.session.flush()


def create_recommendation_interactions(
    students: dict[str, User],
    adaptations: dict[str, list[AdaptationLog]],
    now: datetime,
) -> None:
    del now
    outcome_map = {
        "accepted": (3.0, 78.0),
        "ignored": (-2.0, 32.0),
        "self_verified": (0.0, None),
    }
    plans = {
        "student": ["accepted"] * 6,
        "sidorova": ["accepted"] * 12 + ["self_verified"],
        "kozlov": ["accepted"] * 3 + ["self_verified"],
        "volkova": ["ignored"] * 3 + ["self_verified"],
        "morozov": ["ignored"] * 13,
        "novikova": ["accepted"] * 7,
        "fedorov": ["accepted"] + ["self_verified"] * 2,
        "egorova": ["accepted"] * 9,
        "pavlov": ["ignored"] * 10,
        "antonova": ["accepted"] * 2 + ["self_verified"],
        "belov": ["ignored"] * 16,
    }
    for username, actions in plans.items():
        for adaptation, action in zip(adaptations[username], actions):
            trust_delta, outcome_score = outcome_map[action]
            db.session.add(RecommendationInteraction(
                student_id=students[username].id,
                adaptation_log_id=adaptation.id,
                action=action,
                outcome_score=outcome_score,
                trust_delta=trust_delta,
                created_at=adaptation.created_at + timedelta(hours=12),
            ))
    db.session.flush()


def create_profiles_and_consent(students: dict[str, User], now: datetime) -> None:
    trust_scores = {
        "student": 68.0,
        "sidorova": 86.0,
        "kozlov": 59.0,
        "volkova": 44.0,
        "morozov": 24.0,
        "novikova": 71.0,
        "fedorov": 53.0,
        "egorova": 77.0,
        "pavlov": 30.0,
        "antonova": 56.0,
        "belov": 18.0,
    }
    consent_map = {
        "student": (True, True, True),
        "sidorova": (True, True, True),
        "kozlov": (True, True, False),
        "volkova": (True, False, False),
        "morozov": (False, False, False),
        "novikova": (True, True, True),
        "fedorov": (False, False, True),
        "egorova": (True, True, True),
        "pavlov": (True, False, False),
        "antonova": (False, True, False),
        "belov": (False, False, False),
    }
    for username, student in students.items():
        behavioral, team_data, engagement = consent_map[username]
        db.session.add(StudentProfile(
            student_id=student.id,
            trust_score=trust_scores[username],
            sri=50.0,
            updated_at=now,
        ))
        db.session.add(ConsentProfile(
            student_id=student.id,
            academic_data=True,
            behavioral_analytics=behavioral,
            team_data=team_data,
            engagement_index=engagement,
            updated_at=now,
        ))
    db.session.flush()


def create_projects(
    teachers: dict[str, User],
    students: dict[str, User],
    topics: dict[str, Topic],
    now: datetime,
) -> None:
    project_specs = [
        {
            "title": "Адаптивный тренажер по Python",
            "description": "Команда собирает задания по Python и проверяет, как их можно адаптировать под разные профили студентов.",
            "teacher": teachers["teacher"],
            "topic": topics["python"],
            "status": "active",
            "max_members": 4,
            "deadline": now + timedelta(days=8),
            "created_at": now - timedelta(days=4),
            "members": [("student", "lead"), ("kozlov", "member"), ("fedorov", "member")],
            "tasks": [
                ("Подготовить базовые упражнения", "Сделать набор задач на input, if и циклы.", "student", "done", now - timedelta(days=2)),
                ("Разбить задания по уровням", "Определить простые, средние и сложные задания.", "kozlov", "in_progress", None),
                ("Проверить объяснения к тестам", "Уточнить формулировки и пояснения после ответов.", "fedorov", "pending", None),
            ],
        },
        {
            "title": "Визуализация алгоритмов сортировки",
            "description": "Проект с командой риска: позволяет показать командный Trust Score и ограничения по consent.",
            "teacher": teachers["teacher2"],
            "topic": topics["algo"],
            "status": "active",
            "max_members": 5,
            "deadline": now + timedelta(days=10),
            "created_at": now - timedelta(days=5),
            "members": [("volkova", "lead"), ("morozov", "member"), ("pavlov", "member"), ("belov", "member")],
            "tasks": [
                ("Собрать примеры сортировок", "Подготовить наглядные шаги пузырьковой сортировки.", "volkova", "done", now - timedelta(days=1)),
                ("Сделать карточку по бинарному поиску", "Описать алгоритм простыми словами.", "morozov", "in_progress", None),
                ("Подготовить памятку по O-нотации", "Сделать короткий лист с примерами сложностей.", "pavlov", "pending", None),
                ("Проверить понятность формулировок", "Отметить места, где нужна дополнительная подсказка.", "belov", "pending", None),
            ],
        },
        {
            "title": "Мини-справочник по ООП",
            "description": "Завершенный проект с сильной командой: показывает сценарий completed и высокий командный Trust Score.",
            "teacher": teachers["teacher"],
            "topic": topics["oop"],
            "status": "completed",
            "max_members": 3,
            "deadline": now - timedelta(days=2),
            "created_at": now - timedelta(days=12),
            "members": [("sidorova", "lead"), ("egorova", "member"), ("novikova", "member")],
            "tasks": [
                ("Подготовить примеры классов", "Собрать три коротких кейса по классам и объектам.", "sidorova", "done", now - timedelta(days=5)),
                ("Описать наследование", "Добавить диаграмму Parent и Child.", "egorova", "done", now - timedelta(days=4)),
                ("Подготовить блок по полиморфизму", "Сделать один практический пример с общим интерфейсом.", "novikova", "done", now - timedelta(days=3)),
            ],
        },
        {
            "title": "Банк стартовых задач",
            "description": "Архивный проект с заготовками для новичков.",
            "teacher": teachers["teacher2"],
            "topic": topics["data"],
            "status": "archived",
            "max_members": 4,
            "deadline": now - timedelta(days=14),
            "created_at": now - timedelta(days=25),
            "members": [("antonova", "lead")],
            "tasks": [
                ("Собрать стартовые упражнения", "Список коротких заданий по спискам и словарям.", "antonova", "done", now - timedelta(days=16)),
            ],
        },
        {
            "title": "Командный разбор типичных ошибок",
            "description": "Пустой активный проект для демонстрации сценария вступления нового участника.",
            "teacher": teachers["teacher"],
            "topic": topics["data"],
            "status": "active",
            "max_members": 3,
            "deadline": now + timedelta(days=12),
            "created_at": now - timedelta(days=1),
            "members": [],
            "tasks": [],
        },
    ]

    for spec in project_specs:
        project = Project(
            title=spec["title"],
            description=spec["description"],
            created_by=spec["teacher"].id,
            topic_id=spec["topic"].id,
            deadline=spec["deadline"],
            max_members=spec["max_members"],
            status=spec["status"],
            created_at=spec["created_at"],
        )
        db.session.add(project)
        db.session.flush()
        for idx, (username, role) in enumerate(spec["members"]):
            db.session.add(ProjectMembership(
                project_id=project.id,
                student_id=students[username].id,
                role=role,
                joined_at=project.created_at + timedelta(hours=idx * 4),
            ))
        db.session.flush()
        for title, description, assignee, status, completed_at in spec["tasks"]:
            db.session.add(ProjectTask(
                project_id=project.id,
                title=title,
                description=description,
                assigned_to=students[assignee].id if assignee else None,
                status=status,
                created_at=project.created_at + timedelta(days=1),
                completed_at=completed_at,
            ))
    db.session.flush()


if __name__ == "__main__":
    seed()
