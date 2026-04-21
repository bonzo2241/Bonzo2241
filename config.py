import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "lms-secret-key-change-in-production")
DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "lms.db")
# SQLite concurrency: longer timeout to avoid "database is locked" when
# Flask and OpenClaw agents write simultaneously.
SQLALCHEMY_ENGINE_OPTIONS = {
    "connect_args": {"timeout": 30},
    "pool_pre_ping": True,
}

# OpenClaw gateway (запускается отдельно: openclaw onboard --install-daemon)
OPENCLAW_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")

# Agent thresholds
RISK_SCORE_THRESHOLD = 50          # % below which a student is "at risk"
MONITORING_PERIOD = 30             # seconds between monitoring cycles
ADAPTATION_PERIOD = 60             # seconds between adaptation cycles

# AI / LLM settings (OpenRouter — OpenAI-compatible API)
# Получить ключ: https://openrouter.ai/keys
AI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
AI_MODEL = os.environ.get("AI_MODEL", "openrouter/free")
AI_ENABLED = bool(AI_API_KEY)
