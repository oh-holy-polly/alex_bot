"""
cache.py — SQLite кэш для:
1. История диалога (последние N сообщений)
2. Кэш данных из Notion (обновляется раз в 15 мин)
3. Состояние бота (режим дня, активная задача, время будильника)
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from config import DB_PATH, TIMEZONE

logger = logging.getLogger(__name__)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Создаёт таблицы если их нет"""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notion_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
    logger.info("DB initialized")

# ───────────────────────────────────────────
# ИСТОРИЯ ДИАЛОГА
# ───────────────────────────────────────────

def add_message(role: str, content: str):
    """Добавляет сообщение в историю"""
    now = datetime.now(TIMEZONE).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, now)
        )
        # Оставляем только последние 30 сообщений
        conn.execute("""
            DELETE FROM messages WHERE id NOT IN (
                SELECT id FROM messages ORDER BY id DESC LIMIT 30
            )
        """)

def get_history(limit: int = 20) -> list:
    """Возвращает последние N сообщений для передачи в Groq"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def clear_history():
    """Очищает историю (на случай если что-то пошло не так)"""
    with get_conn() as conn:
        conn.execute("DELETE FROM messages")

# ───────────────────────────────────────────
# КЭШ NOTION
# ───────────────────────────────────────────

CACHE_TTL_MINUTES = 15

def set_cache(key: str, value):
    """Сохраняет данные в кэш. None игнорируется — для инвалидации используй invalidate_cache()"""
    if value is None:  # FIX: не сохраняем None как валидную запись
        return
    now = datetime.now(TIMEZONE).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO notion_cache (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), now)
        )

def get_cache(key: str):
    """
    Возвращает данные из кэша если они свежие (< 15 мин).
    Возвращает None если кэш устарел или отсутствует.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value, updated_at FROM notion_cache WHERE key = ?",
            (key,)
        ).fetchone()

    if not row:
        return None

    updated_at = datetime.fromisoformat(row["updated_at"])
    if datetime.now(TIMEZONE) - updated_at > timedelta(minutes=CACHE_TTL_MINUTES):
        return None

    return json.loads(row["value"])

def invalidate_cache(key: str = None):
    """Сбрасывает кэш (конкретный ключ или весь)"""
    with get_conn() as conn:
        if key:
            conn.execute("DELETE FROM notion_cache WHERE key = ?", (key,))
        else:
            conn.execute("DELETE FROM notion_cache")

# ───────────────────────────────────────────
# СОСТОЯНИЕ БОТА
# ───────────────────────────────────────────

def set_state(key: str, value):
    """Сохраняет состояние (строка, число, dict — всё через JSON)"""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False))
        )

def get_state(key: str, default=None):
    """Возвращает состояние по ключу"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return default
    return json.loads(row["value"])

# Удобные обёртки для часто используемых состояний

def get_day_mode() -> str:
    """Текущий режим дня: рабочий / лёгкий / отпуск / кризисный"""
    return get_state("day_mode", "рабочий")

def set_day_mode(mode: str):
    set_state("day_mode", mode)

def get_active_task() -> dict | None:
    """Текущая активная задача в цикле коучинга"""
    return get_state("active_task", None)

def set_active_task(task: dict | None):
    set_state("active_task", task)

def get_wake_time() -> dict:
    """Время подъёма на завтра {hour, minute}"""
    return get_state("wake_time", {"hour": 10, "minute": 0})

def set_wake_time(hour: int, minute: int):
    set_state("wake_time", {"hour": hour, "minute": minute})

def get_night_mode() -> bool:
    """Ночной режим (после полуночи)"""
    return get_state("night_mode", False)

def set_night_mode(active: bool):
    set_state("night_mode", active)
