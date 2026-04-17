"""
main.py — точка входа, все Telegram handlers

ИЗМЕНЕНИЯ v2:
- Умный детектор намерений через LLM (вместо жёсткого keyword matching)
- Намерения: task_start / task_done / task_stuck / no_ping / add_habit /
             habit_done / new_pattern / save_archive / suggest_event /
             new_idea / chat
- Детектор вызывает быструю 8b модель, возвращает JSON
"""

import logging
import json
import re
import tempfile
import os
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
from alex import ask_alex, ask_alex_system, groq_client
from notion_manager import notion
from intent_router import route_message

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
    return update.effective_user.id == USER_TELEGRAM_ID

def is_night() -> bool:
    hour = datetime.now(TIMEZONE).hour
    return 0 <= hour < 6

# ───────────────────────────────────────────
# УМНЫЙ ДЕТЕКТОР НАМЕРЕНИЙ
# ───────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """Ты — классификатор намерений. Определяешь что имеет в виду Полина.

Верни ТОЛЬКО валидный JSON без пояснений и markdown:
{"intent": "<intent>", "confidence": <0.0-1.0>}

Возможные intent:
- task_start     — начинает задачу / говорит что будет делать / собирается за что-то взяться
- task_done      — говорит что закончила, сделала, готово, выполнила
- task_stuck     — застряла, затупила, не может начать, завислa
- no_ping        — просит не беспокоить, не пинговать, оставить в покое
- add_habit      — хочет добавить привычку
- habit_done     — отмечает что сделала привычку
- new_pattern    — замечает паттерн поведения / триггер
- save_archive   — просит сохранить/запомнить что-то
- suggest_event  — скучно, куда пойти, что делать
- new_idea       — пришла с новой идеей / планом / бизнес-идеей
- chat           — просто разговаривает, всё остальное

Примеры:
"надо прошерстить файлы" → task_start
"буду делать отчёт" → task_start
"хочу разобрать почту" → task_start
"всё, сделала" → task_done
"застряла на введении" → task_stuck
"не мешай мне" → no_ping
"начну делать зарядку каждый день" → add_habit
"сделала зарядку" → habit_done
"я всегда откладываю когда устала" → new_pattern
"запомни это упражнение" → save_archive
"скучно" → suggest_event
"придумала новый проект" → new_idea
"как дела?" → chat
"""

def detect_intent(message: str) -> dict:
    """
    Вызывает быструю 8b модель чтобы понять намерение Полины.
    Возвращает {"intent": str, "confidence": float}
    """
    try:
        from groq import Groq
        from config import GROQ_API_KEY, MODEL_FAST

        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=MODEL_FAST,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ],
            temperature=0.1,
            max_tokens=60
        )
        raw = response.choices[0].message.content.strip()

        # Чистим на случай если модель всё же добавила markdown
        raw = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(raw)
        logger.info(f"Intent: {result} | Message: {message[:50]}")
        return result

    except Exception as e:
        logger.error(f"Intent detection error: {e}")
        return {"intent": "chat", "confidence": 0.5}

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
    if not is_polina(update):
        return
    set_night_mode(False)
    from morning import handle_awake
    await handle_awake(update, context)

async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    done = [h["name"] for h in habits if h["done_today"]]
    pending = [h["name"] for h in habits if not h["done_today"]]
    text = ""
    if done:
        text += f"Выполнено: {', '.join(done)}\n"
    if pending:
        text += f"Ещё не сделано: {', '.join(pending)}"
    await update.message.reply_text(text.strip())

async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

PROCESSED_MSGS = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_polina(update):
        return

    # Защита от дублей (если Телеграм перепосылает сообщение из-за таймаута)
    msg_id = update.message.message_id
    now_ts = datetime.now().timestamp()
    
    # Используем глобальный словарь для надежности
    if msg_id in PROCESSED_MSGS:
        if now_ts - PROCESSED_MSGS[msg_id] < 60:
            logger.warning(f"Duplicate message detected: {msg_id}, skipping.")
            return
    
    PROCESSED_MSGS[msg_id] = now_ts
    
    # Очистка старых ID раз в 100 сообщений
    if len(PROCESSED_MSGS) > 100:
        for m_id in list(PROCESSED_MSGS.keys()):
            if now_ts - PROCESSED_MSGS[m_id] > 300:
                del PROCESSED_MSGS[m_id]

    user_message = update.message.text

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
    else:
        # Если утро, сбрасываем ночной режим
        if get_night_mode():
            set_night_mode(False)

    # ── Гибкий роутинг через intent_router ──
    needs_clarification, action_results = route_message(user_message)

    if needs_clarification:
        # Есть что-то требующее уточнения
        clarify_context = "\n".join(needs_clarification)
        reply = ask_alex(
            user_message,
            force_smart=False,
            extra_instruction=(
                f"Результаты попытки записи в Notion:\n{clarify_context}\n\n"
                f"Там где NOTION_CLARIFY — нужно переспросить Полину. "
                f"Сделай это естественно, в стиле Алекса, одним вопросом."
            )
        )
        await update.message.reply_text(reply)
        return

    if action_results:
        # Действия выполнены — Алекс подтверждает в своём стиле
        actions_context = "\n".join(action_results)
        reply = ask_alex(
            user_message,
            force_smart=False,
            extra_instruction=(
                f"Ты только что выполнила следующие действия в Notion:\n{actions_context}\n\n"
                f"Подтверди это Полине коротко и в стиле Алекса. "
                f"Если было несколько действий — упомяни все. "
                f"Если что-то не записалось (NOTION_ERROR) — скажи об этом честно."
            )
        )
        await update.message.reply_text(reply)
        return

    # ── Обычный разговор — просто Алекс ──
    reply = ask_alex(user_message)
    await update.message.reply_text(reply)

# ───────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ОБРАБОТЧИКИ
# ───────────────────────────────────────────

async def _handle_save_to_archive(update: Update, user_message: str):
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
    if not is_polina(update):
        return
    from morning import handle_morning_photo
    await handle_morning_photo(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений через Groq Whisper"""
    if not is_polina(update):
        return
    
    await update.message.reply_text("🎙️")
    
    temp_path = None
    try:
        file = await context.bot.get_file(update.message.voice.file_id)
        
        # Скачиваем во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as f:
            temp_path = f.name
        
        # ОЖИДАЕМ завершения скачивания (await исправлен)
        await file.download_to_drive(temp_path)

        # Транскрибация через Groq Whisper
        with open(temp_path, "rb") as audio_file:
            transcript = groq_client.audio.transcriptions.create(
                file=(os.path.basename(temp_path), audio_file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
            )
        
        text = transcript.text
        logger.info(f"Voice → text: {text[:60]}...")
        
        if not text or len(text.strip()) < 2:
            await update.message.reply_text("Не расслышал, попробуй ещё раз")
            return

        # Подменяем текст и прогоняем через стандартный handle_message
        update.message.text = text
        await handle_message(update, context)
        
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("Не расслышал, попробуй ещё раз")
    finally:
        # Всегда удаляем временный файл
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

# ───────────────────────────────────────────
# ЗАПУСК
# ───────────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("awake", cmd_awake))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("habits", cmd_habits))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("help", cmd_help))

    # Фото
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Текст
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
        handle_message
    ))

    # Голосовое сообщение
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Планировщик
    from scheduler import setup_scheduler
    setup_scheduler(app)

    logger.info("Алекс запущен 🔥")
    app.run_polling()

if __name__ == "__main__":
    main()
