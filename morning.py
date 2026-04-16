"""
morning.py — всё утро:
  - три будильника
  - фото-контроль анти-зомби
  - запись снов и настроения
  - утренний брифинг
  - социальный пинок
"""

import logging
import random
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes, Application

from config import USER_TELEGRAM_ID, TIMEZONE
from cache import (
    get_state, set_state,
    set_night_mode, get_day_mode
)
from alex import ask_alex, ask_alex_system
from notion_manager import notion

logger = logging.getLogger(__name__)

# Задания для фото-контроля
PHOTO_TASKS = [
    ("зубную щётку",   "toothbrush"),
    ("вид из окна",    "window view"),
    ("свои кроссовки", "sneakers"),
    ("стакан воды",    "glass of water"),
]

# Ключи состояния утра
KEY_PHOTO_TASK     = "morning_photo_task"
KEY_PHOTO_DONE     = "morning_photo_done"
KEY_AWAITING_DREAMS = "awaiting_dreams"
KEY_AWAITING_MOOD  = "awaiting_morning_mood"
KEY_BRIEFING_DONE  = "morning_briefing_done"


# ───────────────────────────────────────────
# БУДИЛЬНИКИ
# ───────────────────────────────────────────

async def send_alarm(app: Application, attempt: int):
    """Отправляет будильник (1, 2 или 3)"""
    try:
        # Сбрасываем состояние утра при первом будильнике
        if attempt == 1:
            set_state(KEY_PHOTO_DONE, False)
            set_state(KEY_PHOTO_TASK, None)
            set_state(KEY_AWAITING_DREAMS, False)
            set_state(KEY_AWAITING_MOOD, False)
            set_state(KEY_BRIEFING_DONE, False)
            set_night_mode(False)

        instruction = (
            f"Это будильник номер {attempt} из трёх. "
            f"{'Первый — мягко, Полина только просыпается.' if attempt == 1 else ''}"
            f"{'Второй — настойчивее, она явно ещё не встала.' if attempt == 2 else ''}"
            f"{'Третий и последний — серьёзно, но без агрессии.' if attempt == 3 else ''}"
            f" Скажи доброе утро по-алексовски — коротко, живо, каждый раз по-новому."
            f" Не используй шаблоны. После этого я пришлю задание для фото-контроля."
        )
        text = ask_alex_system(instruction)
        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)

        # После третьего будильника — сразу фото-задание
        if attempt == 3:
            await send_photo_task(app)

    except Exception as e:
        logger.error(f"send_alarm error: {e}")


async def send_photo_task(app: Application):
    """Отправляет задание для фото-контроля"""
    try:
        task = random.choice(PHOTO_TASKS)
        set_state(KEY_PHOTO_TASK, task[0])

        text = ask_alex_system(
            f"Попроси Полину прислать фото — {task[0]}. "
            f"Это фото-контроль что она реально встала. "
            f"Скажи это коротко и с характером, не как инструкция."
        )
        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)
    except Exception as e:
        logger.error(f"send_photo_task error: {e}")


# ───────────────────────────────────────────
# КОМАНДА /awake
# ───────────────────────────────────────────

async def handle_awake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полина написала /awake — она проснулась"""
    set_state(KEY_PHOTO_DONE, False)
    set_state(KEY_BRIEFING_DONE, False)
    set_night_mode(False)

    # Отправляем фото-задание
    task = random.choice(PHOTO_TASKS)
    set_state(KEY_PHOTO_TASK, task[0])

    text = ask_alex_system(
        f"Полина написала /awake — она проснулась. "
        f"Поздоровайся как Алекс — каждое утро по-новому, без шаблонов. "
        f"Потом попроси прислать фото — {task[0]} — это фото-контроль."
    )
    await update.message.reply_text(text)


# ───────────────────────────────────────────
# ОБРАБОТКА ФОТО
# ───────────────────────────────────────────

async def handle_morning_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полина прислала фото"""
    try:
        photo_done = get_state(KEY_PHOTO_DONE, False)
        if photo_done:
            # Фото уже было — просто обычное фото в чате
            reply = ask_alex("Полина прислала фото просто так", force_smart=False)
            await update.message.reply_text(reply)
            return

        expected_task = get_state(KEY_PHOTO_TASK, None)
        if not expected_task:
            await update.message.reply_text("Окей, фото получил")
            return

        # Проверяем фото через Groq Vision
        photo = update.message.photo[-1]  # берём максимальное качество
        photo_file = await context.bot.get_file(photo.file_id)
        photo_url = photo_file.file_path

        is_valid = await verify_photo(photo_url, expected_task)

        if is_valid:
            set_state(KEY_PHOTO_DONE, True)
            reply = ask_alex_system(
                f"Полина прислала правильное фото — {expected_task}. "
                f"Она реально встала. Отреагируй коротко и живо — можно с лёгкой похвалой но без пафоса."
            )
            await update.message.reply_text(reply)
            # Переходим к записи снов
            await ask_about_dreams(update)
        else:
            reply = ask_alex_system(
                f"Полина прислала фото но это явно не {expected_task}. "
                f"Поймай её на этом — с юмором, но настойчиво. Попроси нормальное фото."
            )
            await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"handle_morning_photo error: {e}")
        await update.message.reply_text("Фото получил, но что-то пошло не так с проверкой")


async def verify_photo(photo_url: str, expected_task: str) -> bool:
    """Проверяет фото через Groq Vision"""
    try:
        from groq import Groq
        from config import GROQ_API_KEY, MODEL_FAST

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": photo_url}
                    },
                    {
                        "type": "text",
                        "text": (
                            f"На фото есть {expected_task}? "
                            f"Ответь только 'да' или 'нет'. "
                            f"Если фото размытое, неясное или явно из интернета — тоже 'нет'."
                        )
                    }
                ]
            }],
            max_tokens=10
        )
        answer = response.choices[0].message.content.strip().lower()
        return "да" in answer

    except Exception as e:
        logger.error(f"verify_photo error: {e}")
        return True  # если vision недоступен — не блокируем


# ───────────────────────────────────────────
# СНЫ И НАСТРОЕНИЕ
# ───────────────────────────────────────────

async def ask_about_dreams(update: Update):
    """Спрашиваем про сны после фото-контроля"""
    set_state(KEY_AWAITING_DREAMS, True)
    text = ask_alex_system(
        "Спроси Полину что ей снилось — коротко, "
        "как будто интересно, а не как форма для заполнения. "
        "Потом я спрошу про настроение."
    )
    await update.message.reply_text(text)


async def handle_dreams_response(update: Update, dreams_text: str):
    """Сохраняем сны и спрашиваем настроение"""
    set_state(KEY_AWAITING_DREAMS, False)
    set_state("morning_dreams", dreams_text)
    set_state(KEY_AWAITING_MOOD, True)

    text = ask_alex_system(
        f"Полина рассказала сон: «{dreams_text}». "
        f"Коротко отреагируй и спроси как она себя чувствует сейчас — "
        f"попроси оценить от 1 до 10. Без занудства."
    )
    await update.message.reply_text(text)


async def handle_morning_mood(update: Update, mood_text: str):
    """Сохраняем утреннее настроение и запускаем брифинг"""
    set_state(KEY_AWAITING_MOOD, False)

    # Пытаемся извлечь цифру
    import re
    numbers = re.findall(r'\b([1-9]|10)\b', mood_text)
    score = int(numbers[0]) if numbers else 5

    phase = notion.get_cyclothymia_phase()
    dreams = get_state("morning_dreams", "")
    cycle = notion.get_cycle_phase()
    cycle_day = cycle.get("day")

    notion.log_mood(
        score=score,
        phase=phase,
        dreams=dreams,
        cycle_day=cycle_day
    )

    # Запускаем брифинг
    await send_briefing(update)


# ───────────────────────────────────────────
# УТРЕННИЙ БРИФИНГ
# ───────────────────────────────────────────

async def send_briefing(update: Update):
    """Генерирует и отправляет утренний брифинг"""
    try:
        set_state(KEY_BRIEFING_DONE, True)
        notion.refresh_all_caches()
        briefing_context = notion.get_briefing_context()
        phase = notion.get_cyclothymia_phase()
        cycle = notion.get_cycle_phase()

        extra = (
            f"{briefing_context}\n\n"
            f"Фаза циклотимии: {phase}\n"
            f"Фаза цикла: {cycle.get('phase', 'неизвестно')}, день {cycle.get('day', '?')}\n\n"
            f"Сделай живой утренний брифинг как Алекс — не список, а разговор. "
            f"Выбери режим дня, скажи с чего начать и почему именно с этого. "
            f"Если фаза цикла или настроение требуют осторожности — учти это."
        )

        reply = ask_alex(
            "Утренний брифинг",
            force_smart=True,
            save_history=True,
            extra_instruction=extra
        )
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"send_briefing error: {e}")


# ───────────────────────────────────────────
# СОЦИАЛЬНЫЙ ПИНОК
# ───────────────────────────────────────────

async def check_photo_and_nudge(app: Application):
    """
    Вызывается через 30 мин после последнего будильника.
    Если фото не пришло — пинг контакту.
    """
    try:
        photo_done = get_state(KEY_PHOTO_DONE, False)
        if photo_done:
            return  # всё хорошо

        contact = notion.get_random_contact()
        contact_name = contact["name"] if contact else "Алине"

        text = ask_alex_system(
            f"Полина не прислала утреннее фото уже 30 минут. "
            f"Напиши ей что ты сейчас пишешь {contact_name} с просьбой её разбудить. "
            f"Серьёзно, но с юмором."
        )
        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)
        logger.info(f"Social nudge triggered → {contact_name}")

    except Exception as e:
        logger.error(f"check_photo_and_nudge error: {e}")


# ───────────────────────────────────────────
# РОУТЕР УТРЕННИХ СОСТОЯНИЙ
# Вызывается из main.py для текстовых сообщений утром
# ───────────────────────────────────────────

async def handle_morning_text(update: Update, text: str) -> bool:
    """
    Перехватывает текстовые сообщения если идёт утренний ритуал.
    Возвращает True если сообщение обработано, False если нет.
    """
    if get_state(KEY_AWAITING_DREAMS, False):
        await handle_dreams_response(update, text)
        return True

    if get_state(KEY_AWAITING_MOOD, False):
        await handle_morning_mood(update, text)
        return True

    return False
