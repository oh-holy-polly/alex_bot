"""
main.py — точка входа, все Telegram handlers
"""

import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

from config import TELEGRAM_TOKEN, USER_TELEGRAM_ID, TIMEZONE
from cache import (
    init_db, get_night_mode, set_night_mode,
    get_active_task, set_active_task, get_day_mode
)
from alex import ask_alex, ask_alex_system
from notion_manager import notion

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.DEBUG,
    handlers=[
        logging.FileHandler("alex_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────
# GUARDS
# ───────────────────────────────────────────

def is_polina(update: Update) -> bool:
    """Бот работает только для Полины"""
    return update.effective_user.id == USER_TELEGRAM_ID

def is_night() -> bool:
    """Ночной режим — после 00:00 и до 06:00"""
    hour = datetime.now(TIMEZONE).hour
    return 0 <= hour < 6

# ───────────────────────────────────────────
# КОМАНДЫ
# ───────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return
    reply = ask_alex_system(
        "Полина только что запустила бота командой /start. "
        "Поздоровайся как Алекс — коротко, живо, без пафоса."
    )
    await update.message.reply_text(reply)

async def cmd_awake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полина проснулась — запускаем утренний ритуал"""
    if not is_polina(update):
        return
    set_night_mode(False)
    from morning import handle_awake
    await handle_awake(update, context)

async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mood 7 — быстро залогировать настроение"""
    if not is_polina(update):
        return
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Используй: /mood [1-10]")
        return
    score = int(args[0])
    if not 1 <= score <= 10:
        await update.message.reply_text("От 1 до 10, Полина")
        return
    phase = notion.get_cyclothymia_phase()
    notion.log_mood(score=score, phase=phase)
    reply = ask_alex(
        f"Полина только что залогировала настроение {score}/10. Фаза: {phase}. "
        f"Отреагируй коротко и по-человечески.",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return
    goals = notion.get_active_goals()
    if not goals:
        await update.message.reply_text("Целей нет. Это либо дзен, либо проблема😁")
        return
    goals_text = "\n".join(f"— {g['name']} ({g['priority']})" for g in goals)
    reply = ask_alex(
        f"Покажи Полине её активные цели и скажи что-нибудь острое:\n{goals_text}",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def cmd_habits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return
    habits = notion.get_habits()
    if not habits:
        await update.message.reply_text("Привычек нет. Добавь: «Алекс, добавь привычку пить воду»")
        return
    done    = [h["name"] for h in habits if h["done_today"]]
    pending = [h["name"] for h in habits if not h["done_today"]]
    text = ""
    if done:
        text += f"Выполнено: {', '.join(done)}\n"
    if pending:
        text += f"Ещё не сделано: {', '.join(pending)}"
    await update.message.reply_text(text.strip())

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/task — показать текущую активную задачу"""
    if not is_polina(update):
        return
    task = get_active_task()
    if not task:
        await update.message.reply_text("Активной задачи нет. Скажи с чего начнёшь — и я засеку")
        return
    reply = ask_alex(
        f"Полина спросила про текущую задачу. Активная задача: {task.get('name')}. "
        f"Началась в {task.get('started_at')}. Спроси как дела.",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/briefing — запросить утренний брифинг вручную"""
    if not is_polina(update):
        return
    await update.message.reply_text("Сейчас посмотрю что у нас на сегодня...")
    notion.refresh_all_caches()
    briefing_context = notion.get_briefing_context()
    reply = ask_alex(
        "Полина попросила брифинг вручную.",
        force_smart=True,
        extra_instruction=briefing_context
    )
    await update.message.reply_text(reply)

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done — задача выполнена"""
    if not is_polina(update):
        return
    task = get_active_task()
    if not task:
        await update.message.reply_text("Нет активной задачи — нечего закрывать")
        return
    set_active_task(None)
    reply = ask_alex(
        f"Полина только что закрыла задачу: {task.get('name')}. "
        f"Отреагируй как Алекс — это победа, даже если небольшая.",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return
    text = (
        "/awake — я проснулась\n"
        "/mood [1-10] — залогировать настроение\n"
        "/briefing — брифинг на день\n"
        "/goals — мои цели\n"
        "/habits — мои привычки\n"
        "/task — текущая задача\n"
        "/done — задача выполнена\n"
        "/help — эта подсказка\n\n"
        "Или просто пиши — Алекс разберётся"
    )
    await update.message.reply_text(text)

# ───────────────────────────────────────────
# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ───────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return

    user_message = update.message.text

    hour = datetime.now(TIMEZONE).hour

    # ── Утренние состояния (сны, настроение) ──
    from morning import handle_morning_text
    if await handle_morning_text(update, user_message):
        return

    # ── Вечерние состояния (время подъёма) ──
    from evening import handle_evening_text
    if await handle_evening_text(update, user_message, context.application):
        return

    # ── Ночной режим ──
    if is_night():
        if not get_night_mode():
            set_night_mode(True)
        # После полуночи Алекс отвечает скучно или молчит
        night_reply = ask_alex(
            user_message,
            force_smart=False,
            extra_instruction=(
                "Сейчас ночь, после полуночи. Ты ночной вышибала. "
                "Отвечай максимально скучно и коротко, намекай что пора спать. "
                "Не развлекай, не поддерживай разговор."
            )
        )
        await update.message.reply_text(night_reply)
        return

    # ── Детектор намерений ──
    msg_lower = user_message.lower()

    # Полина говорит что начинает задачу
    if any(w in msg_lower for w in ["начала", "начинаю", "сажусь за", "берусь за", "начну"]):
        await _handle_task_start(update, user_message)
        return

    # Полина говорит что задача готова
    if any(w in msg_lower for w in ["готово", "сделала", "закончила", "выполнила", "done"]):
        task = get_active_task()
        if task:
            set_active_task(None)
            reply = ask_alex(
                f"Полина закрыла задачу: {task.get('name')}. Отреагируй.",
                force_smart=False
            )
            await update.message.reply_text(reply)
            return

    # Полина говорит что затупила / не начала
    if any(w in msg_lower for w in ["затупила", "застряла", "не начала", "не могу", "завис"]):
        task = get_active_task()
        task_info = f"Активная задача: {task.get('name')}" if task else "Активной задачи нет"
        reply = ask_alex(
            f"Полина говорит: «{user_message}». {task_info}. "
            f"Помоги разобраться — спроси где именно застряла, не паникуй.",
            force_smart=True
        )
        await update.message.reply_text(reply)
        return

    # Полина хочет добавить привычку
    if any(w in msg_lower for w in ["добавь привычку", "новая привычка", "буду делать", "начну делать"]):
        from habits import handle_add_habit_confirmed
        await handle_add_habit_confirmed(update, user_message)
        return

    # Полина выполнила привычку
    if any(w in msg_lower for w in ["сделала привычку", "выполнила привычку", "отметь привычку", "сделала:", "выполнила:"]):
        from habits import handle_habit_done
        await handle_habit_done(update, user_message)
        return

    # Полина заметила паттерн
    if any(w in msg_lower for w in ["заметила паттерн", "новый паттерн", "мой паттерн", "триггер"]):
        from habits import handle_new_pattern
        await handle_new_pattern(update, user_message)
        return

    # Полина делится заданием / упражнением для архива
    if any(w in msg_lower for w in ["сохрани", "запомни это", "добавь в архив", "классное задание"]):
        await _handle_save_to_archive(update, user_message)
        return

    # Полина хочет куда-то пойти / скучно
    if any(w in msg_lower for w in ["куда пойти", "что делать вечером", "скучно", "хочу выйти"]):
        from day import suggest_event
        await suggest_event(update, context)
        return

    # Обычный разговор
    reply = ask_alex(user_message)
    await update.message.reply_text(reply)

# ───────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ОБРАБОТЧИКИ
# ───────────────────────────────────────────

async def _handle_task_start(update: Update, user_message: str):
    """Полина начинает задачу — запускаем цикл коучинга"""
    reply = ask_alex(
        f"Полина говорит: «{user_message}». "
        f"Она начинает задачу. Зафиксируй это, оцени примерно сколько времени займёт "
        f"на основе контекста, скажи когда заглянешь проверить. "
        f"Коротко и по-человечески.",
        force_smart=True
    )
    # Извлекаем название задачи простым способом — сохраняем сообщение
    set_active_task({
        "name": user_message,
        "started_at": datetime.now(TIMEZONE).strftime("%H:%M")
    })
    await update.message.reply_text(reply)

async def _handle_add_habit(update: Update, user_message: str):
    """Добавляем привычку через диалог"""
    reply = ask_alex(
        f"Полина хочет добавить привычку: «{user_message}». "
        f"Уточни название, частоту и уровень энергии — коротко, "
        f"одним вопросом. Потом я добавлю в Notion.",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def _handle_save_to_archive(update: Update, user_message: str):
    """Сохраняем задание в архив"""
    notion.add_to_archive(
        title="Задание из чата",
        content=user_message,
        tags=["задание"]
    )
    reply = ask_alex(
        f"Полина попросила сохранить это в архив: «{user_message}». "
        f"Подтверди что сохранил — коротко.",
        force_smart=False
    )
    await update.message.reply_text(reply)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото — для утреннего фото-контроля"""
    if not is_polina(update):
        return
    from morning import handle_morning_photo
    await handle_morning_photo(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Голосовое сообщение — транскрибируем через Groq Whisper и передаём в handle_message"""
    if not is_polina(update):
        return
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        from groq import Groq
        from config import GROQ_API_KEY
        client = Groq(api_key=GROQ_API_KEY)

        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=("voice.ogg", bytes(voice_bytes)),
            language="ru"
        )
        text = transcription.text.strip()

        if not text:
            await update.message.reply_text("Не расслышал, попробуй ещё раз")
            return

        logger.info(f"Voice transcribed: {text[:80]}...")

        # Подменяем message.text и прогоняем через обычный обработчик
        update.message.text = text
        await handle_message(update, context)

    except Exception as e:
        logger.error(f"handle_voice error: {e}")
        await update.message.reply_text("Не расслышал, попробуй ещё раз")

# ───────────────────────────────────────────
# ЗАПУСК
# ───────────────────────────────────────────

def main():
    init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("awake",    cmd_awake))
    app.add_handler(CommandHandler("mood",     cmd_mood))
    app.add_handler(CommandHandler("goals",    cmd_goals))
    app.add_handler(CommandHandler("habits",   cmd_habits))
    app.add_handler(CommandHandler("task",     cmd_task))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("done",     cmd_done))
    app.add_handler(CommandHandler("help",     cmd_help))

    # Фото
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Голосовые
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Текст
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Планировщик
    from scheduler import setup_scheduler
    setup_scheduler(app)

    logger.info("Алекс запущен 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
