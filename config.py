import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "lms-secret-key-change-in-production")
DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "lms.db")

# XMPP server (Prosody / ejabberd / any XMPP-compliant server)
XMPP_SERVER = os.environ.get("XMPP_SERVER", "localhost")

XMPP_AGENTS = {
    "orchestrator": {
        "jid": f"orchestrator@{XMPP_SERVER}",
        "password": os.environ.get("ORCHESTRATOR_PWD", "orchestrator123"),
    },
    "monitoring": {
        "jid": f"monitoring@{XMPP_SERVER}",
        "password": os.environ.get("MONITORING_PWD", "monitoring123"),
    },
    "adaptation": {
        "jid": f"adaptation@{XMPP_SERVER}",
        "password": os.environ.get("ADAPTATION_PWD", "adaptation123"),
    },
    "notification": {
        "jid": f"notification@{XMPP_SERVER}",
        "password": os.environ.get("NOTIFICATION_PWD", "notification123"),
    },
}

# Agent thresholds
RISK_SCORE_THRESHOLD = 50          # % below which a student is "at risk"
MONITORING_PERIOD = 30             # seconds between monitoring cycles
ADAPTATION_PERIOD = 60             # seconds between adaptation cycles

# AI / LLM settings (OpenRouter — OpenAI-compatible API)
# Получить ключ: https://openrouter.ai/keys
AI_API_KEY = "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"
AI_BASE_URL = "https://openrouter.ai/api/v1"
AI_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
AI_ENABLED = bool(AI_API_KEY)

# Server settings
SERVER_HOST = "192.168.0.14"
SERVER_PORT = 5000
