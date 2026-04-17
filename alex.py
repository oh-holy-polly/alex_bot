"""
alex.py — мозг Алекса:
- загружает system prompt
- роутер моделей (8b / 70b)
- собирает контекст из кэша
- вызывает Groq
"""

import logging
from datetime import datetime
from groq import Groq
from config import (
    GROQ_API_KEY, MODEL_FAST, MODEL_SMART,
    TIMEZONE, PROMPT_PATH
)
from cache import (
    get_history, add_message,
    get_cache, get_day_mode, get_active_task, get_night_mode
)

logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)

# ───────────────────────────────────────────
# ЗАГРУЗКА SYSTEM PROMPT
# ───────────────────────────────────────────

def load_system_prompt() -> str:
    try:
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"System prompt not found at {PROMPT_PATH}")
        return "Ты — Алекс, личный ассистент Полины."

# ───────────────────────────────────────────
# РОУТЕР МОДЕЛЕЙ
# ───────────────────────────────────────────

# Ключевые слова которые требуют умной модели
SMART_TRIGGERS = [
    "брифинг", "план", "расставь", "приоритет",
    "анализ", "паттерн", "ретроспектив", "итог", "неделя", "месяц",
    "почему", "объясни", "помоги разобраться",
    "что делать", "как мне", "посоветуй",
    "не начала", "затупила", "застряла", "не могу",
]

def choose_model(message: str, force_smart: bool = False) -> str:
    """
    Выбирает модель под задачу.
    force_smart=True — всегда 70b (брифинг, вечерний ритуал и т.д.)
    """
    if force_smart:
        return MODEL_SMART

    msg_lower = message.lower()
    if any(trigger in msg_lower for trigger in SMART_TRIGGERS):
        return MODEL_SMART

    if len(message) > 200:
        return MODEL_SMART

    return MODEL_FAST

# ───────────────────────────────────────────
# СБОРКА КОНТЕКСТА
# ───────────────────────────────────────────

def build_context() -> str:
    """
    Собирает динамический контекст из кэша Notion.
    Подставляется в конец system prompt перед каждым запросом.
    Компактно — только самое нужное.
    """
    now = datetime.now(TIMEZONE)

    lines = [
        f"\n=== КОНТЕКСТ ПРЯМО СЕЙЧАС ===",
        f"Время: {now.strftime('%A, %d.%m.%Y %H:%M')}",
        f"Режим дня: {get_day_mode()}",
    ]

    # Настроение
    mood_data = get_cache("recent_mood")
    if mood_data:
        latest = mood_data[0] if isinstance(mood_data, list) else mood_data
        lines.append(f"Последнее настроение: {latest.get('score', '?')}/10 — {latest.get('phase', '?')}")

    # Фаза цикла
    cycle = get_cache("cycle_phase")
    if cycle:
        lines.append(f"Фаза цикла: {cycle.get('phase', '?')}, день {cycle.get('day', '?')}")

    # Активная задача
    active_task = get_active_task()
    if active_task:
        lines.append(f"Активная задача: {active_task.get('name', '?')} (начата в {active_task.get('started_at', '?')})")

    # События сегодня
    events = get_cache("today_events")
    if events:
        events_str = ", ".join(e.get("name", "") for e in events[:3])
        lines.append(f"События сегодня: {events_str}")

    # Цели
    goals = get_cache("active_goals")
    if goals:
        goals_str = ", ".join(g.get("name", "") for g in goals[:3])
        lines.append(f"Активные цели: {goals_str}")

    # Привычки
    habits = get_cache("habits")
    if habits:
        pending = [h.get("name", "") for h in habits if not h.get("done_today")]
        if pending:
            lines.append(f"Привычки не выполнены: {', '.join(pending[:3])}")

    # Паттерны
    patterns = get_cache("patterns")
    if patterns:
        patterns_str = "; ".join(p.get("name", "") for p in patterns[:2])
        lines.append(f"Известные паттерны: {patterns_str}")

    lines.append("=== КОНЕЦ КОНТЕКСТА ===")
    return "\n".join(lines)

# ───────────────────────────────────────────
# ОСНОВНОЙ ВЫЗОВ
# ───────────────────────────────────────────

def ask_alex(
    user_message: str,
    force_smart: bool = False,
    save_history: bool = True,
    extra_instruction: str = ""
) -> str:
    """
    Главная функция — отправляет сообщение Алексу и возвращает ответ.

    user_message — то что написала Полина
    force_smart — принудительно использовать 70b
    save_history — сохранять в историю (False для системных вызовов)
    extra_instruction — дополнительная инструкция в конец system prompt
                        (например: "Это утренний брифинг. Выбери режим дня.")
    """
    try:
        model = choose_model(user_message, force_smart)

        system_prompt = load_system_prompt()
        context = build_context()
        full_system = system_prompt + context

        if extra_instruction:
            full_system += f"\n\n{extra_instruction}"
            # Напоминаем про характер, если пришла системная инструкция, чтобы не стал "роботом"
            full_system += "\nKeep your personality: sarcastic, mix Russian/English, no boring helper talk."

        history = get_history(limit=10)  # было 20
        messages = [{"role": "system", "content": full_system}]
        messages += history
        messages.append({"role": "user", "content": user_message})

        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.85,
                max_tokens=600
            )
        except Exception as groq_err:
            # Если умная модель упала — пробуем быструю
            if model == MODEL_SMART:
                logger.warning(f"Smart model failed ({groq_err}), falling back to fast model")
                response = groq_client.chat.completions.create(
                    model=MODEL_FAST,
                    messages=messages,
                    temperature=0.85,
                    max_tokens=600
                )
            else:
                raise

        reply = response.choices[0].message.content.strip()

        if save_history:
            add_message("user", user_message)
            add_message("assistant", reply)

        logger.info(f"Model: {model} | User: {user_message[:50]}...")
        return reply

    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "Полина, что-то сломалось на моей стороне. Попробуй ещё раз"


def ask_alex_system(instruction: str) -> str:
    """
    Вызов без пользовательского сообщения — для системных задач.
    Например: сгенерировать утреннее приветствие, титул награды и т.д.
    Не сохраняет в историю диалога.
    """
    return ask_alex(
        user_message=instruction,
        force_smart=True,
        save_history=False
    )
