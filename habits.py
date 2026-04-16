"""
habits.py — логика управления привычками и паттернами через диалог
"""

import logging
import re
from telegram import Update
from telegram.ext import ContextTypes

from alex import ask_alex, ask_alex_system
from notion_manager import notion
from cache import get_cache, invalidate_cache

logger = logging.getLogger(__name__)

async def handle_habit_done(update: Update, user_message: str):
    """Полина говорит что выполнила привычку"""
    habits = notion.get_habits()
    if not habits:
        reply = ask_alex(user_message)
        await update.message.reply_text(reply)
        return

    # Пытаемся найти какую именно привычку она выполнила
    msg_lower = user_message.lower()
    found_habit = None
    
    for h in habits:
        # Проверяем вхождение названия привычки в сообщение
        if h["name"].lower() in msg_lower:
            found_habit = h
            break
    
    if not found_habit:
        # Если не нашли по названию, просим Алекса уточнить или найти
        pending = [h["name"] for h in habits if not h["done_today"]]
        extra = f"Полина говорит: «{user_message}». Список невыполненных привычек: {', '.join(pending)}. Какую именно она сделала? Спроси или подтверди если понял."
        reply = ask_alex(user_message, extra_instruction=extra)
        await update.message.reply_text(reply)
        return

    # Отмечаем в Notion
    success = notion.mark_habit_done(found_habit["id"])
    if success:
        invalidate_cache("habits")
        reply = ask_alex(
            f"Полина выполнила привычку: {found_habit['name']}. Отреагируй как Алекс — похвали или подколи, но подтверди что залогировал.",
            force_smart=False
        )
    else:
        reply = "Полина, не смог достучаться до Notion, чтобы отметить привычку. Попробуй позже."
    
    await update.message.reply_text(reply)

async def handle_add_habit_confirmed(update: Update, user_message: str):
    """
    Полина подтвердила добавление привычки.
    Здесь можно использовать LLM для извлечения параметров.
    """
    extra = (
        "Полина хочет добавить новую привычку. Извлеки из её сообщения: "
        "1. Название (коротко) "
        "2. Частоту (Ежедневно/Еженедельно) "
        "3. Уровень энергии (Низкий/Средний/Высокий). "
        "Верни ответ в формате: HABIT_DATA: Название | Частота | Энергия. "
        "И ниже напиши ответ Полине в стиле Алекса."
    )
    
    full_reply = ask_alex(user_message, force_smart=True, extra_instruction=extra)
    
    if "HABIT_DATA:" in full_reply:
        try:
            data_part = full_reply.split("HABIT_DATA:")[1].split("\n")[0].strip()
            name, freq, energy = [x.strip() for x in data_part.split("|")]
            
            # Валидация значений для Notion select
            if freq not in ["Ежедневно", "Еженедельно"]: freq = "Ежедневно"
            if energy not in ["Низкий", "Средний", "Высокий"]: energy = "Средний"
            
            habit_id = notion.add_habit(name, freq, energy)
            if habit_id:
                invalidate_cache("habits")
                # Убираем техническую часть из ответа пользователю
                user_reply = full_reply.split("HABIT_DATA:")[0].strip()
                if not user_reply:
                    user_reply = full_reply.split("\n", 1)[1].strip()
                await update.message.reply_text(user_reply)
                return
        except Exception as e:
            logger.error(f"Error parsing habit data: {e}")

    await update.message.reply_text(full_reply)

async def handle_new_pattern(update: Update, user_message: str):
    """Полина заметила новый паттерн"""
    extra = (
        "Полина заметила у себя новый паттерн поведения. Извлеки: "
        "1. Название паттерна "
        "2. Триггер "
        "3. Сигналы. "
        "Верни ответ в формате: PATTERN_DATA: Название | Триггер | Сигналы. "
        "И ниже напиши ответ Полине."
    )
    
    full_reply = ask_alex(user_message, force_smart=True, extra_instruction=extra)
    
    if "PATTERN_DATA:" in full_reply:
        try:
            data_part = full_reply.split("PATTERN_DATA:")[1].split("\n")[0].strip()
            name, trigger, signals = [x.strip() for x in data_part.split("|")]
            
            pattern_id = notion.add_pattern(name, trigger, signals)
            if pattern_id:
                invalidate_cache("patterns")
                user_reply = full_reply.split("PATTERN_DATA:")[0].strip()
                if not user_reply:
                    user_reply = full_reply.split("\n", 1)[1].strip()
                await update.message.reply_text(user_reply)
                return
        except Exception as e:
            logger.error(f"Error parsing pattern data: {e}")

    await update.message.reply_text(full_reply)

async def handle_new_pattern_from_text(full_text: str):
    """
    Вспомогательная функция для извлечения и записи паттерна из технической строки.
    Используется в системных вызовах (дебрифинг, вечерний ритуал).
    """
    if "PATTERN_DATA:" in full_text:
        try:
            data_part = full_text.split("PATTERN_DATA:")[1].split("\n")[0].strip()
            name, trigger, signals = [x.strip() for x in data_part.split("|")]
            
            pattern_id = notion.add_pattern(name, trigger, signals)
            if pattern_id:
                invalidate_cache("patterns")
                logger.info(f"Auto-pattern added: {name}")
                return True
        except Exception as e:
            logger.error(f"Error parsing auto-pattern data: {e}")
    return False
