"""
config.py — все настройки и токены из .env
"""

import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# ===== TELEGRAM =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
USER_TELEGRAM_ID = int(os.getenv("USER_TELEGRAM_ID", "0"))

# ===== GROQ =====
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_FAST = "llama-3.1-8b-instant"       # пинги, короткие ответы
MODEL_SMART = "llama-3.3-70b-versatile"   # брифинг, анализ, генерация

# ===== NOTION =====
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASES = {
    "people":   os.getenv("NOTION_DB_PEOPLE",   "33aee470194180839d16c4391e9fe8e3"),
    "events":   os.getenv("NOTION_DB_EVENTS",   "33bee47019418070bc97f6d0485b4a03"),
    "mood":     os.getenv("NOTION_DB_MOOD",     "33bee4701941809ea0f9da1e7d7d2abf"),
    "ideas":    os.getenv("NOTION_DB_IDEAS",    "33bee47019418027a02fc75732722c18"),
    "habits":   os.getenv("NOTION_DB_HABITS",   "33bee4701941802a8716ecf293cb3ced"),
    "archive":  os.getenv("NOTION_DB_ARCHIVE",  "33bee470194180bab3c7da6e50536fa6"),
    "goals":    os.getenv("NOTION_DB_GOALS",    "33bee4701941809380b9c4e8cbef8943"),
    "patterns": os.getenv("NOTION_DB_PATTERNS", "33bee4701941808683cac5052f283537"),
}

# ===== ВРЕМЯ =====
TIMEZONE = pytz.timezone("Europe/Minsk")

# ===== РАСПИСАНИЕ (defaults, меняются через диалог) =====
DEFAULT_WAKE_HOUR   = int(os.getenv("DEFAULT_WAKE_HOUR",   "10"))
DEFAULT_WAKE_MINUTE = int(os.getenv("DEFAULT_WAKE_MINUTE", "0"))
EVENING_HOUR        = int(os.getenv("EVENING_HOUR",        "22"))
EVENING_MINUTE      = int(os.getenv("EVENING_MINUTE",      "0"))
NIGHT_HOUR          = int(os.getenv("NIGHT_HOUR",          "0"))
NIGHT_MINUTE        = int(os.getenv("NIGHT_MINUTE",        "0"))

# ===== ПУТИ =====
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "alex.db")
PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "system.txt")
