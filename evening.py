"""
evening.py — всё вечером и ночью:
- вечерний ритуал
- договор на завтра
- ночной вышибала
- воскресный дебрифинг
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application

from config import USER_TELEGRAM_ID, TIMEZONE
from cache import (
    get_state, set_state,
    set_wake_time, set_night_mode,
    get_day_mode
)
from alex import ask_alex, ask_alex_system
from notion_manager import notion
from scheduler import schedule_alarms

logger = logging.getLogger(__name__)

KEY_EVENING_DONE = "evening_ritual_done"
KEY_AWAITING_TOMORROW = "awaiting_tomorrow_time"

# ───────────────────────────────────────────
# ВЕЧЕРНИЙ РИТУАЛ
# ───────────────────────────────────────────

async def send_evening_ritual(app: Application):
    """Запускает вечерний ритуал"""
    try:
        if get_state(KEY_EVENING_DONE, False):
            return

        notion.refresh_all_caches()

        today_events = notion.get_today_events()
        habits = notion.get_habits()
        impulses = notion.get_pending_impulses()
        phase = notion.get_cyclothymia_phase()
        moods = notion.get_recent_mood(days=1)
        score = moods[0]["score"] if moods and moods[0]["score"] else 5

        done_events = [e["name"] for e in today_events if e.get("status") == "Выполнено"]
        done_habits = [h["name"] for h in habits if h["done_today"]]
        missed_habits = [h["name"] for h in habits if not h["done_today"]]

        extra = (
            f"Вечерний ритуал. Данные за день:\n"
            f"Выполнено задач: {', '.join(done_events) if done_events else 'ничего не отмечено'}\n"
            f"Привычки выполнены: {', '.join(done_habits) if done_habits else 'нет'}\n"
            f"Привычки пропущены: {', '.join(missed_habits) if missed_habits else 'нет'}\n"
            f"Идей на проверке: {len(impulses)}\n"
            f"Настроение за день: {score}/10, фаза: {phase}\n\n"
            f"Проведи вечерний ритуал как Алекс — это диалог, не отчёт:\n"
            f"1. Дофаминовый аудит — на что слили время?\n"
            f"2. Один момент гордости (по-алексовски, без пафоса)\n"
            f"3. Если идей больше 3 — фильтр гипомании\n"
            f"4. Микроплан на завтра — одно главное дело\n"
            f"5. В конце спроси во сколько завтра вставать\n\n"
            f"Всё это одним живым сообщением. Не списком.\n\n"
            f"ВАЖНО: Если ты заметил в данных за день четкую связь (например, пропуск привычки -> низкое настроение), "
            f"сформулируй это как новый паттерн и включи техническую строку PATTERN_DATA в конец сообщения."
        )

        text = ask_alex_system(extra)

        if "PATTERN_DATA:" in text:
            from habits import handle_new_pattern_from_text
            await handle_new_pattern_from_text(text)
            text = text.split("PATTERN_DATA:")[0].strip()

        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)
        set_state(KEY_EVENING_DONE, True)
        set_state(KEY_AWAITING_TOMORROW, True)

    except Exception as e:
        logger.error(f"send_evening_ritual error: {e}")

# ───────────────────────────────────────────
# ДОГОВОР НА ЗАВТРА
# ───────────────────────────────────────────

async def handle_tomorrow_time(update: Update, text: str, app: Application) -> bool:
    """
    Полина называет время подъёма на завтра.
    Возвращает True если обработали, False если нет.
    """
    if not get_state(KEY_AWAITING_TOMORROW, False):
        return False

    if len(text) > 15:
        return False

    import re
    match = re.search(r'(\d{1,2})[.:,]?(\d{2})?', text)
    if not match:
        return False

    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0

    if not (5 <= hour <= 13):
        return False

    set_wake_time(hour, minute)
    set_state(KEY_AWAITING_TOMORROW, False)
    schedule_alarms(app)

    reply = ask_alex_system(
        f"Полина сказала что завтра встаёт в {hour}:{minute:02d}. "
        f"Подтверди что поставил будильник — коротко. "
        f"Потом скажи что уходишь и намекни что пора ложиться."
    )
    await update.message.reply_text(reply)
    return True

# ───────────────────────────────────────────
# НОЧНОЙ ВЫШИБАЛА
# ───────────────────────────────────────────

async def send_night_message(app: Application):
    """Ночное сообщение — коротко и скучно"""
    try:
        set_night_mode(True)
        set_state(KEY_EVENING_DONE, False)  # сброс для следующего дня

        text = ask_alex_system(
            "Сейчас полночь. Ты ночной вышибала. "
            "Отправь одно короткое сообщение — пора спать. "
            "Без эмодзи, без веселья, максимально скучно. "
            "Скажи что если напишет — будешь отвечать занудно."
        )
        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)

    except Exception as e:
        logger.error(f"send_night_message error: {e}")

# ───────────────────────────────────────────
# ВОСКРЕСНЫЙ ДЕБРИФИНГ
# ───────────────────────────────────────────

async def send_weekly_debrief(app: Application):
    """Воскресный дебрифинг — каждое воскресенье в 19:00"""
    try:
        notion.refresh_all_caches()

        moods = notion.get_recent_mood(days=7)
        habits = notion.get_habits()
        goals = notion.get_active_goals()
        patterns = notion.get_patterns()
        phase = notion.get_cyclothymia_phase()

        scores = [m["score"] for m in moods if m["score"]]
        avg_mood = round(sum(scores) / len(scores), 1) if scores else "?"
        phases_this_week = list(set(m["phase"] for m in moods if m["phase"]))

        habit_summary = ""
        for h in habits[:5]:
            last = h.get("last_done", "")
            habit_summary += f"— {h['name']}: последний раз {last or 'давно'}\n"

        # Данные за 3 недели для анализа корреляций
        correlation_data = notion.get_weekly_correlation_data(weeks=3)

        extra = (
            f"Воскресный дебрифинг. Данные за неделю:\n"
            f"Среднее настроение: {avg_mood}/10\n"
            f"Фазы недели: {', '.join(phases_this_week)}\n"
            f"Текущая фаза: {phase}\n\n"
            f"Привычки:\n{habit_summary}\n"
            f"Активных целей: {len(goals)}\n"
            f"Известных паттернов: {len(patterns)}\n\n"
            f"=== ДАННЫЕ ЗА 3 НЕДЕЛИ ДЛЯ АНАЛИЗА КОРРЕЛЯЦИЙ ===\n"
            f"{correlation_data}\n"
            f"=== КОНЕЦ ДАННЫХ ===\n\n"
            f"Проанализируй данные выше и найди устойчивые корреляции — "
            f"например: в дни когда выполнена привычка X, настроение на N баллов выше; "
            f"или: настроение стабильно падает в определённые дни недели. "
            f"Корреляция должна встречаться минимум 3 раза чтобы её называть.\n\n"
            f"Проведи дебрифинг как Алекс — разговор за чашкой чего-нибудь, не отчёт. "
            f"Если нашёл корреляцию — скажи об этом как будто сам давно заметил, "
            f"органично, одной фразой в духе: «Кстати, заметил одну вещь...». "
            f"Отметь что было круто на этой неделе, что можно улучшить. "
            f"В конце спроси — есть ли одна вещь которую хочет изменить на следующей неделе.\n\n"
            f"ВАЖНО: Если нашёл устойчивую корреляцию которой ещё нет в списке паттернов, "
            f"добавь в конец сообщения техническую строку: "
            f"PATTERN_DATA: Название паттерна | Триггер | Сигналы"
        )

        text = ask_alex_system(extra)

        if "PATTERN_DATA:" in text:
            from habits import handle_new_pattern_from_text
            await handle_new_pattern_from_text(text)
            text = text.split("PATTERN_DATA:")[0].strip()

        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)

    except Exception as e:
        logger.error(f"send_weekly_debrief error: {e}")

# ───────────────────────────────────────────
# РОУТЕР ВЕЧЕРНИХ СОСТОЯНИЙ
# Вызывается из main.py
# ───────────────────────────────────────────

async def handle_evening_text(update: Update, text: str, app: Application) -> bool:
    """
    Перехватывает текстовые сообщения если идёт вечерний ритуал.
    Возвращает True если сообщение обработано.
    """
    if get_state(KEY_AWAITING_TOMORROW, False):
        handled = await handle_tomorrow_time(update, text, app)
        if handled:
            return True
    return False
