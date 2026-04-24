# LMS Multi-Agent Platform (SPADE)

Многоагентная система поддержки обучения на основе фреймворка **SPADE** (Smart Python Agent Development Environment) с AI-интеграцией через OpenRouter.

## Архитектура

### Агенты (SPADE + XMPP)

| Агент | Функция |
|-------|---------|
| **OrchestratorAgent** | Центральный координатор: маршрутизирует события между агентами, принимает решения, ведёт журнал |
| **MonitoringAgent** | Периодически анализирует успеваемость студентов, выявляет «группу риска» и положительную динамику |
| **AdaptationAgent** | Генерирует персональные AI-рекомендации, адаптирует сложность материалов |
| **NotificationAgent** | Получает команды от оркестратора, формирует уведомления для преподавателя |

Взаимодействие агентов: **hub-and-spoke** через OrchestratorAgent (XMPP-сообщения).

### AI-сервис (OpenRouter)

- Генерация персональных рекомендаций для студентов
- Автогенерация тестовых вопросов по теме
- Анализ паттернов ошибок студента
- AI-чат-ассистент для студентов по темам курса
- **Fallback**: при отсутствии API-ключа все функции работают на правилах

### Веб-приложение (Flask)

**Студент:**
- Просмотр тем и прохождение тестов
- Прогресс по темам с процентами
- Персональные рекомендации от адаптивного агента
- AI-чат-ассистент по темам курса

**Преподаватель:**
- Создание тем и вопросов (вручную + AI-генерация)
- Мониторинг студентов с детализацией по темам
- AI-анализ паттернов ошибок студентов
- Отчёты агентов мониторинга и уведомлений
- Журнал рекомендаций адаптивного агента
- Журнал решений оркестратора

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

Доступны также 11 студентов с различными профилями (login = password):
`sidorova`, `kozlov`, `volkova`, `morozov`, `novikova`, `fedorov`, `egorova`, `pavlov`, `antonova`, `belov`

### 3. AI-функции (опционально)

Получите ключ на https://openrouter.ai/keys и задайте переменную окружения:

```bash
export OPENAI_API_KEY="sk-or-..."
python run.py --web-only
```

### 4. Запуск с агентами (требуется XMPP-сервер)

Установите Prosody или ejabberd, затем создайте аккаунты:

```bash
# Prosody
sudo prosodyctl register orchestrator localhost orchestrator123
sudo prosodyctl register monitoring localhost monitoring123
sudo prosodyctl register adaptation localhost adaptation123
sudo prosodyctl register notification localhost notification123
```

Запуск:
```bash
python run.py
```

## Демо-данные

При первом запуске автоматически создаются:

- **4 темы**: Основы Python, Структуры данных, ООП в Python, Алгоритмы и сложность (по 5 вопросов)
- **11 студентов** с разными профилями успеваемости:

| Студент | Профиль |
|---------|---------|
| Сидорова А.В. | Отличница (~93%) |
| Петров П.П. | Хорошист (~80%) |
| Козлов Д.М. | Хорошист (~68%) |
| Волкова Е.С. | Средняя (~53%) |
| Егорова М.В. | Прогрессирует (50% -> 85%) |
| Новикова О.Л. | Сильная по Python, слабая по алгоритмам |
| Павлов С.Н. | Деградирует (85% -> 30%) |
| Фёдоров А.А. | Новичок (только 2 темы) |
| Антонова К.Р. | Прошла только 1 тему |
| Морозов И.К. | Зона риска (~28%) |
| Белов Р.Д. | Критическая зона (~14%) |

- **Отчёты агентов**: мониторинг зоны риска, уведомления, адаптивные рекомендации
- **Журнал оркестратора**: координация между агентами

## Структура проекта

```
├── app.py              # Flask-приложение (маршруты, представления, seed-данные)
├── agents.py           # SPADE-агенты (оркестратор, мониторинг, адаптация, уведомления)
├── ai_service.py       # AI-сервис (OpenRouter): рекомендации, генерация вопросов, чат
├── config.py           # Конфигурация (XMPP, Flask, AI, пороги)
├── models.py           # Модели БД (User, Topic, Question, StudentAnswer, AgentReport, ...)
├── run.py              # Точка входа (--web-only | полный режим с агентами)
├── requirements.txt
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── login.html / register.html
    ├── student_dashboard.html / student_progress.html / student_chat.html
    ├── topic.html / quiz.html / quiz_results.html
    ├── teacher_dashboard.html / student_detail.html / student_analysis.html
    ├── create_topic.html / manage_topic.html / add_question.html
    ├── generate_questions.html
    ├── reports.html / adaptations.html / orchestrator_log.html
    └── ...
```
