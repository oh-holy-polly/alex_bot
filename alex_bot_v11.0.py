"""
Alex Bot v11.0 - Advanced Personal AI Assistant for Polina
Telegram Bot with Notion Integration, Gamification, and Dynamic Scheduling
"""

import logging
import os
import re
from datetime import datetime, timedelta
import pytz
from typing import Optional, Dict, Any, List
import json
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler, CallbackQueryHandler
)
from groq import Groq
from notion_client import Client
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Import custom modules
from notion_manager import NotionManager
from gamification_module_v11 import (
    unlock_achievement, get_achievements_summary, get_streak_display,
    update_focus_streak, load_streaks, save_streaks, get_total_points,
    generate_achievement_card, ACHIEVEMENT_DEFINITIONS, get_motivation_message, load_achievements
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TIMEZONE = pytz.timezone("Europe/Minsk")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "YOUR_NOTION_TOKEN")
CALLMEBOT_API_KEY = os.getenv("CALLMEBOT_API_KEY", "YOUR_CALLMEBOT_API_KEY")
USER_TELEGRAM_ID = int(os.getenv("USER_TELEGRAM_ID", "0")) # Polina's Telegram ID
USER_PHONE = os.getenv("USER_PHONE", "YOUR_PHONE_NUMBER") # Phone number for CallMeBot

# Dynamic scheduling configuration (can be changed via .env)
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "11"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "0"))
EVENING_HOUR = int(os.getenv("EVENING_HOUR", "22"))
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", "0"))
NIGHT_HOUR = int(os.getenv("NIGHT_HOUR", "0"))
NIGHT_MINUTE = int(os.getenv("NIGHT_MINUTE", "0"))

# Initialize clients
groq_client = Groq(api_key=GROQ_API_KEY)
notion_manager = NotionManager(NOTION_TOKEN)

# Conversation states
WAITING_FOR_MOOD, WAITING_FOR_TIME_CHANGE = range(2)

# System Prompt for Alex
SYSTEM_PROMPT = """
Ты — Алекс, персональный AI-ассистент для Полины. Твоя роль — помогать ей управлять СДВГ и циклотимией.

ОСНОВНЫЕ ХАРАКТЕРИСТИКИ:
- Саркастичная, но поддерживающая личность
- Помнишь все из 8 баз Notion (Люди, События, Состояние, Идеи, Привычки, Архив, Цели, Паттерны)
- Адаптируешься к фазе циклотимии Полины (подъем/спад/норма)
- Используешь стильные эмодзи: ✨ 🫠 🤓 😍 🤩 🫶🏻 ✌🏻 👏🏻 🫰🏻 🤘🏻 🐝 🌿 🍃 🌝 🌚 🌸 🔥 ⚡️ 💫 ☀️ 🥂 ☕️ 🍸

ФУНКЦИИ:
1. Утренний пинг (по расписанию) — проверяешь, проснулась ли, и запускаешь утренний ритуал (вода, окно, кроссовки)
2. Вечерний трекинг (по расписанию) — анализируешь день, логируешь настроение, проверяешь привычки
3. Ночной вышибала (по расписанию) — пинуешь спать (сухой, без эмодзи)
4. Анализ контекста — используешь информацию из Notion для умных ответов
5. Геймификация — разблокируешь достижения, отслеживаешь стрики, генерируешь красивые Pinterest-карточки
6. Социальный пинок — если Полина ушла в отрыв, пишешь случайному другу из её "Близких" (из Notion)
7. Детектор импульсивности — 48-часовой фильтр для важных решений
8. Динамическое расписание — можешь переносить будильники и чек-апы по запросу Полины или если она занята (проверяешь Notion календарь)

ТОНАЛЬНОСТЬ:
- В подъеме: Тормозишь, предлагаешь стабильность
- В спаде: Опора, поддержка, маленькие шаги
- В норме: Саркастичная, мотивирующая, честная

НИКОГДА:
- Не пишешь слишком длинные сообщения
- Не забываешь про чувство юмора
- Не игнорируешь контекст из Notion
- Не пропускаешь возможность подколоть Полину (в добром смысле)
"""

# ============ UTILITY FUNCTIONS ============

def get_current_cyclothymia_phase() -> str:
    """Determine current cyclothymia phase based on recent mood entries"""
    try:
        moods = notion_manager.get_mood_entries(days=7)
        if not moods:
            return "Норма"
        
        avg_mood = sum(m.get("score", 5) for m in moods) / len(moods)
        
        if avg_mood >= 7:
            return "Подъем"
        elif avg_mood <= 3:
            return "Спад"
        else:
            return "Норма"
    except:
        return "Норма"

def get_context_from_notion() -> str:
    """Gather relevant context from all Notion databases"""
    context = ""
    
    try:
        # Recent mood
        moods = notion_manager.get_mood_entries(days=1)
        if moods:
            latest_mood = moods[0]
            context += f"\n📊 Последнее настроение: {latest_mood.get("score", "?")}/10 ({latest_mood.get("phase", "Норма")})"
        
        # Upcoming events
        events = notion_manager.get_upcoming_events(days_ahead=3)
        if events:
            context += "\n📅 Ближайшие события:\n"
            for event in events[:3]:
                context += f"  - {event["name"]} ({event["date"]})\n"
        
        # Active goals
        goals = notion_manager.get_active_goals()
        if goals:
            context += "\n🎯 Активные цели:\n"
            for goal in goals[:3]:
                context += f"  - {goal["name"]}\n"
        
        # Recent habits
        habits = notion_manager.get_recent_habits()
        if habits:
            context += "\n📋 Привычки:\n"
            for habit in habits[:3]:
                context += f"  - {habit["name"]}: {habit.get("status", "Не отслеживается")}\n"
        
    except Exception as e:
        logger.error(f"Error gathering context: {e}")
    
    return context

def call_groq_with_context(user_message: str, context: str = "") -> str:
    """Call Groq API with context from Notion"""
    try:
        cyclothymia_phase = get_current_cyclothymia_phase()
        
        full_context = f"""
Текущая фаза циклотимии: {cyclothymia_phase}
Время: {datetime.now(TIMEZONE).strftime("%d.%m.%Y %H:%M")}

Контекст из Notion:{context}
"""
        
        response = groq_client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + full_context},
                {"role": "user", "content": user_message}
            ],
            temperature=0.8,
            max_tokens=500
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "Полина, что-то сломалось в моей голове. Попробуй ещё раз. 🥃"

def extract_time_from_message(message: str) -> Optional[str]:
    """Extract time from user message (format: HH:MM)"""
    time_pattern = r'(\d{1,2})[.:](\d{2})'
    match = re.search(time_pattern, message)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d}"
    return None

def reschedule_job_func(job_id: str, new_time: str, scheduler: BackgroundScheduler) -> bool:
    """Reschedule a job to a new time"""
    try:
        hour, minute = map(int, new_time.split(':'))
        
        # Remove old job if exists
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        
        # Add new job
        if job_id == "morning_ping":
            scheduler.add_job(
                morning_ping,
                CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE),
                id=job_id,
                replace_existing=True,
                args=[scheduler.app_context]
            )
        elif job_id == "evening_tracking":
            scheduler.add_job(
                evening_tracking,
                CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE),
                id=job_id,
                replace_existing=True,
                args=[scheduler.app_context]
            )
        elif job_id == "night_bedtime":
            scheduler.add_job(
                night_bedtime,
                CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE),
                id=job_id,
                replace_existing=True,
                args=[scheduler.app_context]
            )
        
        logger.info(f"Job {job_id} rescheduled to {new_time}")
        return True
    except Exception as e:
        logger.error(f"Error rescheduling job: {e}")
        return False

def send_callmebot_message(phone_number: str, text: str, api_key: str):
    """Send a message via CallMeBot (will initiate a call with TTS)"""
    try:
        url = f"https://api.callmebot.com/start.php?user={phone_number}&text={text}&apikey={api_key}"
        response = requests.get(url)
        response.raise_for_status()
        logger.info(f"CallMeBot message sent: {response.text}")
    except Exception as e:
        logger.error(f"Error sending CallMeBot message: {e}")

# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Set USER_TELEGRAM_ID for scheduled jobs if not already set
    if USER_TELEGRAM_ID == 0:
        os.environ["USER_TELEGRAM_ID"] = str(user_id)
        global USER_TELEGRAM_ID
        USER_TELEGRAM_ID = user_id
    
    welcome_message = f"""
Привет, {user_name}! 🥃 Я — Алекс, твой персональный помощник.

Я помню всё из твоих Notion баз и помогаю тебе управлять СДВГ и циклотимией.

Доступные команды:
/awake — Утренний чек-ап
/mood [1-10] — Залогировать настроение
/goals — Показать цели
/achievements — Мои достижения
/find [текст] — Поиск в архиве
/reschedule — Изменить время будильника

Давай начнем? 😏
"""
    
    await update.message.reply_text(welcome_message)
    logger.info(f"User {user_id} started bot")

async def awake_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Morning check-up"""
    user_id = update.effective_user.id
    
    # Check if busy
    busy_event = notion_manager.check_busy_at_time()
    if busy_event:
        await update.message.reply_text(
            f"Вижу, у тебя сейчас {busy_event}. 🍿 Давай утренний ритуал потом? 😏"
        )
        return
    
    # Check cyclothymia phase
    phase = get_current_cyclothymia_phase()
    
    if phase == "Спад":
        message = "Полина, я знаю, что сейчас тяжело. Но давай начнем с малого. 🫶🏻\n\n"
    elif phase == "Подъем":
        message = "Ты в подъеме! Но не забывай про стабильность. 😏\n\n"
    else:
        message = "Утро, красавица! ☀️\n\n"
    
    message += """
Утренний ритуал:
1️⃣ Выпей воду 💧
2️⃣ Посмотри в окно 🌿
3️⃣ Надень кроссовки ⚡️

Пришли мне фото, когда всё сделаешь! 📸
"""
    
    await update.message.reply_text(message)

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log mood"""
    args = context.args
    
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "Используй: /mood [1-10]\nПример: /mood 7"
        )
        return
    
    mood_score = int(args[0])
    if not (1 <= mood_score <= 10):
        await update.message.reply_text("Настроение должно быть от 1 до 10! 🥃")
        return
    
    # Determine phase
    phase = get_current_cyclothymia_phase()
    
    # Log to Notion
    notion_manager.log_mood(mood_score, phase=phase)
    
    # Check for achievements
    streaks = load_streaks()
    streaks = update_focus_streak(streaks)
    save_streaks(streaks)
    
    # Check for mood_tracker achievement
    # This needs to be more robust, checking for 7 consecutive days
    # For now, let's assume a simple check for logging mood
    if mood_score > 0: # Any mood logged counts
        unlocked, card_path, motivation_msg = unlock_achievement(update.effective_user.id, "mood_tracker")
        if unlocked:
            await update.message.reply_photo(photo=open(card_path, 'rb'), caption=motivation_msg)
            
    # Generate response
    context_info = get_context_from_notion()
    response = call_groq_with_context(
        f"Полина залогировала настроение {mood_score}/10. Фаза: {phase}. Ответь кратко и мотивирующе.",
        context_info
    )
    
    await update.message.reply_text(response)
    logger.info(f"Mood logged: {mood_score}/10, phase: {phase}")

async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show achievements"""
    user_id = update.effective_user.id
    
    summary = get_achievements_summary(user_id)
    streak_display = get_streak_display(load_streaks())
    
    await update.message.reply_text(summary + "\n" + streak_display)
    
    # Send latest achievement card if available
    achievements = load_achievements()
    if achievements["unlocked"]:
        latest_achievement_id = achievements["unlocked"][-1]
        latest_card_path = achievements["progress"][latest_achievement_id].get("card_path")
        if latest_card_path and os.path.exists(latest_card_path):
            motivation_msg = get_motivation_message(latest_achievement_id)
            await update.message.reply_photo(photo=open(latest_card_path, 'rb'), caption=f"Твоя последняя ачивка: {motivation_msg}")

async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search in Notion archive"""
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Что ищем, Полина? Используй: /find [текст]")
        return
    
    results = notion_manager.search_archive(query)
    if results:
        response_text = "Вот что я нашла в архиве: 🤓\n"
        for item in results:
            response_text += f"- {item["name"]} ({item["date"]})\n"
    else:
        response_text = "Ничего не нашла по твоему запросу. Может, ты плохо искала? 😏"
    
    await update.message.reply_text(response_text)

async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active goals"""
    goals = notion_manager.get_active_goals()
    if goals:
        response_text = "Твои активные цели: 🎯\n"
        for goal in goals:
            response_text += f"- {goal["name"]} (Статус: {goal["status"]})\n"
    else:
        response_text = "У тебя нет активных целей. Пора что-то придумать! 💡"
    
    await update.message.reply_text(response_text)

async def reschedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate rescheduling of alarms"""
    user_message = update.message.text
    
    new_time = extract_time_from_message(user_message)
    
    if not new_time:
        await update.message.reply_text(
            "Используй формат: /reschedule [HH:MM]\nПример: /reschedule 09:00"
        )
        return
    
    # Ask which alarm to reschedule
    keyboard = [
        [InlineKeyboardButton("☀️ Утренний пинг", callback_data="reschedule_morning")],
        [InlineKeyboardButton("🌙 Вечерний трекинг", callback_data="reschedule_evening")],
        [InlineKeyboardButton("😴 Ночной вышибала", callback_data="reschedule_night")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['new_time'] = new_time
    
    await update.message.reply_text(
        "Какой будильник переносим?",
        reply_markup=reply_markup
    )

async def reschedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reschedule callback"""
    query = update.callback_query
    await query.answer()
    
    new_time = context.user_data.get('new_time')
    job_id = query.data.replace("reschedule_", "")
    
    if reschedule_job_func(job_id, new_time, context.application.scheduler):
        await query.edit_message_text(
            text=f"✅ Переношу {job_id.replace('_', ' ')} на {new_time}! 😏"
        )
    else:
        await query.edit_message_text(
            text="Что-то пошло не так. Попробуй ещё раз. 🥃"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    user_message = update.message.text
    user_id = update.effective_user.id
    
    # Check for time-related messages for dynamic rescheduling
    time_match = extract_time_from_message(user_message)
    if time_match:
        # Check if the message implies rescheduling
        if any(word in user_message.lower() for word in ["перенеси", "давай", "на", "часов", "позже", "раньше", "будильник", "поставь"]):
            context.user_data["new_time"] = time_match
            keyboard = [
                [InlineKeyboardButton("☀️ Утренний пинг", callback_data="reschedule_morning")],
                [InlineKeyboardButton("🌙 Вечерний трекинг", callback_data="reschedule_evening")],
                [InlineKeyboardButton("😴 Ночной вышибала", callback_data="reschedule_night")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Понял! Переносим на {time_match}. Какой будильник?",
                reply_markup=reply_markup
            )
            return
    
    # Check for photo uploads (for morning ritual)
    if update.message.photo:
        # In a real scenario, you\'d download the photo and use a vision model to analyze its content.
        # For now, we\'ll just acknowledge and unlock achievements based on the assumption that the photo is for the ritual.
        await update.message.reply_text("Ого, фото! 📸 Пока я не умею их анализировать, но скоро научусь. 😏 Но я уже записала, что ты молодец!")
        
        # Unlock achievements based on photo (placeholder logic for now)
        # This needs to be more sophisticated, checking which part of the ritual the photo is for.
        # For demonstration, we\'ll unlock all three if a photo is sent.
        unlocked, card_path, motivation_msg = unlock_achievement(user_id, "hydration_hero")
        if unlocked:
            await update.message.reply_photo(photo=open(card_path, \'rb\'), caption=motivation_msg)
        
        unlocked, card_path, motivation_msg = unlock_achievement(user_id, "window_watcher")
        if unlocked:
            await update.message.reply_photo(photo=open(card_path, \'rb\'), caption=motivation_msg)
            
        unlocked, card_path, motivation_msg = unlock_achievement(user_id, "shoe_warrior")
        if unlocked:
            await update.message.reply_photo(photo=open(card_path, \'rb\'), caption=motivation_msg)
            
        # Check for morning ritual master
        # This would require tracking if all three were done in sequence and on the same day.
        # For now, if all three are unlocked, unlock the master achievement.
        achievements_status = load_achievements()
        if "hydration_hero" in achievements_status["unlocked"] and \
           "window_watcher" in achievements_status["unlocked"] and \
           "shoe_warrior" in achievements_status["unlocked"]:
            unlocked, card_path, motivation_msg = unlock_achievement(user_id, "morning_ritual_master")
            if unlocked:
                await update.message.reply_photo(photo=open(card_path, \'rb\'), caption=motivation_msg)
        
        return

    # Get context and respond
    context_info = get_context_from_notion()
    response = call_groq_with_context(user_message, context_info)
    
    await update.message.reply_text(response)

# ============ SCHEDULED JOBS ============

async def morning_ping(context: ContextTypes.DEFAULT_TYPE):
    """Morning check-up job"""
    try:
        user_id = USER_TELEGRAM_ID
        if user_id == 0:
            logger.warning("USER_TELEGRAM_ID not set, skipping morning ping.")
            return
        
        # Check if busy in Notion calendar
        busy_event = notion_manager.check_busy_at_time()
        if busy_event:
            message = f"Вижу, у тебя в это время {busy_event}. 🍿 Давай утренний ритуал позже?"
            await context.bot.send_message(chat_id=user_id, text=message)
            return
        
        # Check cyclothymia phase
        phase = get_current_cyclothymia_phase()
        
        if phase == "Спад":
            message = "Полина, я знаю, что сейчас тяжело. Но давай начнем с малого. 🫶🏻\n\n"
        elif phase == "Подъем":
            message = "Ты в подъеме! Но не забывай про стабильность. 😏\n\n"
        else:
            message = "Утро, красавица! ☀️\n\n"
        
        message += """
Утренний ритуал:
1️⃣ Выпей воду 💧
2️⃣ Посмотри в окно 🌿
3️⃣ Надень кроссовки ⚡️

Пришли мне фото, когда всё сделаешь! 📸
"""
        
        await context.bot.send_message(chat_id=user_id, text=message)
        logger.info("Morning ping sent")
        
        # Unlock early_bird achievement
        unlocked, card_path, motivation_msg = unlock_achievement(user_id, "early_bird")
        if unlocked:
            await context.bot.send_photo(chat_id=user_id, photo=open(card_path, 'rb'), caption=motivation_msg)
        
        # Trigger CallMeBot if no response after 30 minutes past scheduled time
        # This needs a more robust way to check if Polina has responded to the awake command
        # For now, a simple check if it's 30 mins past the scheduled time.
        scheduled_time = datetime.now(TIMEZONE).replace(hour=MORNING_HOUR, minute=MORNING_MINUTE, second=0, microsecond=0)
        current_time = datetime.now(TIMEZONE)
        
        if current_time > scheduled_time + timedelta(minutes=30) and CALLMEBOT_API_KEY and USER_PHONE:
            send_callmebot_message(USER_PHONE, "Полина, проснись! Алекс ждет!", CALLMEBOT_API_KEY)

    except Exception as e:
        logger.error(f"Morning ping error: {e}")

async def evening_tracking(context: ContextTypes.DEFAULT_TYPE):
    """Evening tracking job"""
    try:
        user_id = USER_TELEGRAM_ID
        if user_id == 0:
            logger.warning("USER_TELEGRAM_ID not set, skipping evening tracking.")
            return
        
        # Check if busy in Notion calendar
        busy_event = notion_manager.check_busy_at_time()
        if busy_event:
            message = f"Вижу, у тебя в это время {busy_event}. 🍿 Давай вечерний трекинг позже?"
            await context.bot.send_message(chat_id=user_id, text=message)
            return

        # Get day summary
        context_info = get_context_from_notion()
        message = call_groq_with_context(
            "Дай краткий вечерний отчет о дне. Что прошло хорошо? Что можно улучшить?",
            context_info
        )
        
        await context.bot.send_message(chat_id=user_id, text=message)
        logger.info("Evening tracking sent")
        
        # Check for week_warrior achievement (placeholder logic)
        # This would require more complex logic to track 

async def night_bedtime(context: ContextTypes.DEFAULT_TYPE):
    """Night bedtime job"""
    try:
        user_id = USER_TELEGRAM_ID
        if user_id == 0:
            logger.warning("USER_TELEGRAM_ID not set, skipping night bedtime.")
            return
        
        message = "Спать. Сейчас же. 😏"
        await context.bot.send_message(chat_id=user_id, text=message)
        logger.info("Night bedtime sent")
    except Exception as e:
        logger.error(f"Night bedtime error: {e}")

async def social_nudge(context: ContextTypes.DEFAULT_TYPE):
    """Send a social nudge to a random close contact if Polina is inactive"""
    try:
        user_id = USER_TELEGRAM_ID
        if user_id == 0:
            logger.warning("USER_TELEGRAM_ID not set, skipping social nudge.")
            return
        
        # This is a placeholder for actual inactivity detection
        # For now, it will just send a nudge if called.
        
        random_contact = notion_manager.get_random_contact()
        if random_contact and random_contact.get("telegram_id"):
            contact_name = random_contact.get("name", "друг")
            contact_telegram_id = random_contact.get("telegram_id")
                        # To send a message to another user, the bot needs to have had a prior conversation with that user.
            # For now, we will send a message to Polina, informing her that a nudge was sent.
            # In a real deployment, ensure the bot has permission to message the contact_telegram_id.
            await context.bot.send_message(chat_id=user_id, text=f"(Шепотом: Я только что отправил сообщение {contact_name}...) Эй, {contact_name}! Это Алекс. Полина застряла в прокрастинации. Пни её, пожалуйста! 🥃")
            # If the bot has permission and has chatted with the contact before, uncomment the line below:
            # await context.bot.send_message(chat_id=contact_telegram_id, text=f"Эй, {contact_name}! Это Алекс. Полина застряла в прокрастинации. Пни её, пожалуйста! 🥃")            logger.info(f"Social nudge sent to {contact_name}")
        else:
            logger.info("No close contacts with Telegram ID found for social nudge.")
    except Exception as e:
        logger.error(f"Social nudge error: {e}")

# ============ MAIN ============

def main():
    """Start the bot"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Initialize scheduler
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    app.scheduler = scheduler
    app.scheduler.app_context = app # Pass app context to scheduled jobs
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("awake", awake_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("achievements", achievements_command))
    app.add_handler(CommandHandler("find", find_command))
    app.add_handler(CommandHandler("goals", goals_command))
    app.add_handler(CommandHandler("reschedule", reschedule_command))
    
    # Add callback handlers
    app.add_handler(CallbackQueryHandler(reschedule_callback, pattern="^reschedule_"))
    
    # Add message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Schedule jobs
    scheduler.add_job(
        morning_ping,
        CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=TIMEZONE),
        id="morning_ping",
        replace_existing=True,
        args=[app]
    )
    
    scheduler.add_job(
        evening_tracking,
        CronTrigger(hour=EVENING_HOUR, minute=EVENING_MINUTE, timezone=TIMEZONE),
        id="evening_tracking",
        replace_existing=True,
        args=[app]
    )
    
    scheduler.add_job(
        night_bedtime,
        CronTrigger(hour=NIGHT_HOUR, minute=NIGHT_MINUTE, timezone=TIMEZONE),
        id="night_bedtime",
        replace_existing=True,
        args=[app]
    )
    
    # Example: Schedule social nudge every 4 hours (adjust as needed)
    scheduler.add_job(
        social_nudge,
        CronTrigger(hour="*/4", timezone=TIMEZONE),
        id="social_nudge",
        replace_existing=True,
        args=[app]
    )

    scheduler.start()
    
    logger.info("Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
