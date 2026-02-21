import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask
SECRET_KEY = os.environ.get("SECRET_KEY", "lms-secret-key-change-in-production")
DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "lms.db")

# XMPP server (Prosody / ejabberd / any XMPP-compliant server)
XMPP_SERVER = os.environ.get("XMPP_SERVER", "localhost")

XMPP_AGENTS = {
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
