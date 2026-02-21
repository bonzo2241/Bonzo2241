# LMS Multi-Agent Platform (SPADE)

Многоагентная система поддержки обучения на основе фреймворка **SPADE** (Smart Python Agent Development Environment).

## Архитектура

### Агенты (SPADE)

| Агент | Функция |
|-------|---------|
| **MonitoringAgent** | Периодически анализирует успеваемость студентов, выявляет «группу риска» |
| **AdaptationAgent** | Генерирует персональные рекомендации, адаптирует сложность материалов |
| **NotificationAgent** | Получает сообщения от других агентов, формирует уведомления для преподавателя |

### Веб-приложение (Flask)

- **Студент**: просмотр тем, прохождение тестов, просмотр прогресса и рекомендаций
- **Преподаватель**: создание тем/вопросов, просмотр отчётов агентов, мониторинг студентов

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск (только веб-интерфейс)

```bash
python run.py --web-only
```

Откройте http://localhost:5000. Демо-доступ:
- Преподаватель: `teacher / teacher`
- Студент: `student / student`

### 3. Запуск с агентами (требуется XMPP-сервер)

Установите Prosody или ejabberd, затем создайте аккаунты:

```bash
# Prosody
sudo prosodyctl register monitoring localhost monitoring123
sudo prosodyctl register adaptation localhost adaptation123
sudo prosodyctl register notification localhost notification123
```

Запуск:
```bash
python run.py
```

## Структура проекта

```
lms_spade/
├── app.py              # Flask-приложение (маршруты, представления)
├── agents.py           # SPADE-агенты (мониторинг, адаптация, уведомления)
├── config.py           # Конфигурация (XMPP, Flask, пороги)
├── models.py           # Модели базы данных (SQLAlchemy)
├── run.py              # Точка входа
├── requirements.txt
├── static/
│   └── style.css       # Сине-белая тема
└── templates/
    ├── base.html
    ├── login.html
    ├── register.html
    ├── student_dashboard.html
    ├── student_progress.html
    ├── topic.html
    ├── quiz.html
    ├── quiz_results.html
    ├── teacher_dashboard.html
    ├── create_topic.html
    ├── manage_topic.html
    ├── add_question.html
    ├── reports.html
    ├── adaptations.html
    └── student_detail.html
```
