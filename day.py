"""
day.py — всё что происходит днём:
  - цикл задачи (живой коучинг)
  - антисаботаж
  - режим дня
  - афиша Минска
"""

import logging
import re
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, Application

from config import USER_TELEGRAM_ID, TIMEZONE
from cache import (
    get_active_task, set_active_task,
    get_day_mode, set_day_mode,
    get_state, set_state
)
from alex import ask_alex, ask_alex_system
from notion_manager import notion

logger = logging.getLogger(__name__)

# Ключи состояния
KEY_TASK_CHECK_TIME   = "task_next_check"   # когда Алекс заглянет следующий раз
KEY_SABOTAGE_COUNT    = "sabotage_count"    # сколько раз подряд просила не пинговать
KEY_NO_PING_REQUESTED = "no_ping_requested"


# ───────────────────────────────────────────
# РЕЖИМ ДНЯ
# ───────────────────────────────────────────

def determine_day_mode() -> str:
    """
    Определяет режим дня на основе контекста.
    Вызывается после брифинга.
    """
    phase = notion.get_cyclothymia_phase()
    cycle = notion.get_cycle_phase()
    moods = notion.get_recent_mood(days=1)
    events = notion.get_today_events()

    score = moods[0]["score"] if moods and moods[0]["score"] else 5
    cycle_phase = cycle.get("phase", "")

    # Кризисный — спад или низкое настроение
    if phase == "Спад" or score <= 3:
        return "кризисный"

    # ПМС — почти кризисный
    if "ПМС" in cycle_phase or score <= 4:
        return "лёгкий"

    # Проверяем есть ли события помеченные как отдых
    for e in events:
        if "отдых" in e.get("category", "").lower() or "отпуск" in e.get("name", "").lower():
            return "отпуск"

    # Подъём — рабочий режим
    if phase == "Подъём" or score >= 7:
        return "рабочий"

    return "рабочий"


# ───────────────────────────────────────────
# ЦИКЛ ЗАДАЧИ
# ───────────────────────────────────────────

async def start_task_cycle(update: Update, task_name: str):
    """
    Полина сказала что начинает задачу.
    Запускаем цикл коучинга.
    """
    now = datetime.now(TIMEZONE)

    # Оцениваем время на задачу
    events = notion.get_today_events()
    patterns = notion.get_patterns()
    phase = notion.get_cyclothymia_phase()
    mode = get_day_mode()

    patterns_text = ""
    for p in patterns:
        if any(word in task_name.lower() for word in p.get("name", "").lower().split()):
            patterns_text = f"Паттерн: {p['name']} — {p['trigger']}"
            break

    extra = (
        f"Полина начинает задачу: «{task_name}».\n"
        f"Фаза: {phase}, режим дня: {mode}\n"
        f"{patterns_text}\n\n"
        f"Оцени сколько времени займёт задача на основе её названия и контекста. "
        f"Скажи когда заглянешь проверить — не точное время, а примерно "
        f"('минут через 40', 'через час'). Коротко и по-алексовски."
    )

    # Рассчитываем когда заглянуть
    estimated_minutes = _estimate_task_duration(task_name, phase)
    check_time = now + timedelta(minutes=estimated_minutes * 0.7)
    set_state(KEY_TASK_CHECK_TIME, check_time.isoformat())
    set_state(KEY_NO_PING_REQUESTED, False)
    set_state(KEY_SABOTAGE_COUNT, 0)

    set_active_task({
        "name": task_name,
        "started_at": now.strftime("%H:%M"),
        "estimated_minutes": estimated_minutes,
        "check_time": check_time.isoformat()
    })

    reply = ask_alex(
        f"Начинаю: {task_name}",
        force_smart=True,
        extra_instruction=extra
    )
    await update.message.reply_text(reply)


def _estimate_task_duration(task_name: str, phase: str) -> int:
    """
    Грубая оценка времени задачи в минутах.
    В реальности модель уточняет это в ответе.
    """
    name_lower = task_name.lower()

    # По ключевым словам
    if any(w in name_lower for w in ["отчёт", "отчет", "презентация", "документ"]):
        base = 120
    elif any(w in name_lower for w in ["письмо", "email", "ответить"]):
        base = 20
    elif any(w in name_lower for w in ["созвон", "встреча", "звонок"]):
        base = 60
    elif any(w in name_lower for w in ["почистить", "убрать", "помыть"]):
        base = 30
    elif any(w in name_lower for w in ["разобраться", "изучить", "прочитать"]):
        base = 45
    else:
        base = 40

    # Корректировка под фазу
    if phase == "Спад":
        base = int(base * 1.5)
    elif phase == "Подъём":
        base = int(base * 0.8)

    return base


async def check_active_task(app: Application):
    """
    Вызывается планировщиком каждые 30 минут.
    Алекс сам решает — заглядывать или нет.
    """
    try:
        task = get_active_task()
        if not task:
            return

        no_ping = get_state(KEY_NO_PING_REQUESTED, False)
        check_time_str = get_state(KEY_TASK_CHECK_TIME)

        if not check_time_str:
            return

        check_time = datetime.fromisoformat(check_time_str)
        now = datetime.now(TIMEZONE)

        # Ещё не время
        if now < check_time:
            return

        # Проверяем антисаботаж
        if no_ping:
            sabotage_count = get_state(KEY_SABOTAGE_COUNT, 0)
            patterns = notion.get_patterns()

            # Ищем паттерн саботажа
            is_sabotage = sabotage_count >= 2 or any(
                "саботаж" in p.get("name", "").lower() or
                "не пингуй" in p.get("trigger", "").lower()
                for p in patterns
            )

            if not is_sabotage:
                return  # уважаем просьбу не пинговать

        # Алекс заглядывает
        started_at = task.get("started_at", "")
        task_name = task.get("name", "")
        estimated = task.get("estimated_minutes", 40)

        extra = (
            f"Активная задача: «{task_name}», началась в {started_at}, "
            f"ожидаемое время: {estimated} мин.\n"
            f"{'Полина просила не пинговать, но ты решил заглянуть — она в паттерне саботажа.' if no_ping else ''}\n"
            f"Загляни — спроси как дела с задачей. Один короткий вопрос."
        )

        text = ask_alex_system(extra)
        await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=text)

        # Следующая проверка — через час
        next_check = now + timedelta(hours=1)
        set_state(KEY_TASK_CHECK_TIME, next_check.isoformat())

    except Exception as e:
        logger.error(f"check_active_task error: {e}")


async def handle_task_stuck(update: Update, message: str):
    """Полина говорит что застряла — коучинг по затыку"""
    task = get_active_task()
    task_info = f"Задача: «{task['name']}»" if task else ""

    extra = (
        f"{task_info}\n"
        f"Полина говорит: «{message}»\n\n"
        f"Она застряла. Не паникуй, не читай лекций. "
        f"Задай один вопрос — где именно застряла? "
        f"На каком конкретном шаге? Потом поможем с этим местом."
    )

    reply = ask_alex(message, force_smart=True, extra_instruction=extra)
    await update.message.reply_text(reply)


async def handle_no_ping_request(update: Update, message: str):
    """Полина просит не пинговать"""
    task = get_active_task()
    if not task:
        reply = ask_alex(message)
        await update.message.reply_text(reply)
        return

    # Увеличиваем счётчик антисаботажа
    count = get_state(KEY_SABOTAGE_COUNT, 0)
    set_state(KEY_SABOTAGE_COUNT, count + 1)
    set_state(KEY_NO_PING_REQUESTED, True)

    patterns = notion.get_patterns()
    phase = notion.get_cyclothymia_phase()

    # Проверяем — это реально нужно или саботаж?
    is_likely_sabotage = count >= 1 or phase == "Спад"

    extra = (
        f"Полина просит не пинговать. Задача: «{task['name']}».\n"
        f"Это {'похоже на саботаж — она так делала раньше' if is_likely_sabotage else 'возможно, она в потоке'}.\n\n"
        f"{'Скажи что уважаешь просьбу, но заглянешь один раз через час — просто проверить. Без агрессии.' if is_likely_sabotage else 'Окей, скажи что не будешь мешать.'}"
    )

    reply = ask_alex(message, force_smart=False, extra_instruction=extra)
    await update.message.reply_text(reply)


# ───────────────────────────────────────────
# АФИША МИНСКА
# ───────────────────────────────────────────

async def suggest_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ищет ивенты в Минске под текущее состояние"""
    try:
        phase = notion.get_cyclothymia_phase()
        mode = get_day_mode()

        # Определяем тип ивента под состояние
        if phase == "Спад" or mode == "кризисный":
            vibe = "тихое, уютное, минимум людей — кино, кафе, выставка"
            energy = "низкой энергии"
        elif phase == "Подъём":
            vibe = "активное, шумное, много движа — маркет, концерт, фестиваль"
            energy = "высокой энергии"
        else:
            vibe = "среднее — лекция, выставка, небольшое мероприятие"
            energy = "средней энергии"

        await update.message.reply_text("Смотрю что есть в Минске...")

        # Поиск через веб (используем Groq с web search или просто просим модель)
        extra = (
            f"Полина хочет куда-то выйти. Фаза: {phase}, настроение {energy}.\n"
            f"Подходящий формат: {vibe}.\n\n"
            f"Предложи 2-3 варианта куда сходить в Минске сегодня вечером. "
            f"Если не знаешь актуальных ивентов — предложи конкретные места где всегда что-то есть: "
            f"НЦСИ, Корпус, Песочница, Октябрьская, кинотеатр Центральный. "
            f"По-алексовски — с характером, не как справочник."
        )

        reply = ask_alex(
            "Куда пойти сегодня вечером?",
            force_smart=True,
            extra_instruction=extra
        )

        # Сохраняем в Notion как событие «Отдых»
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        notion.add_event(
            name="Отдых (предложение Алекса)",
            date=today,
            category="Отдых"
        )

        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"suggest_event error: {e}")
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз")


# ───────────────────────────────────────────
# ФИЛЬТР ГИПОМАНИИ
# ───────────────────────────────────────────

async def handle_new_idea(update: Update, idea_text: str):
    """
    Полина пришла с новой идеей.
    Алекс сверяет с целями и решает — в архив на 48ч или обсуждаем.
    """
    goals = notion.get_active_goals()
    patterns = notion.get_patterns()
    phase = notion.get_cyclothymia_phase()
    impulses = notion.get_pending_impulses()

    goals_text = ", ".join(g["name"] for g in goals[:3]) if goals else "нет"

    extra = (
        f"Полина пришла с новой идеей: «{idea_text}»\n"
        f"Текущие приоритетные цели: {goals_text}\n"
        f"Фаза: {phase}\n"
        f"Уже висит {len(impulses)} идей на проверке\n\n"
        f"Оцени — эта идея в русле текущих целей или нет? "
        f"Если нет — предложи отправить на 48ч проверку и объясни почему. "
        f"Если да — обсуди. По-алексовски, без занудства."
    )

    reply = ask_alex(idea_text, force_smart=True, extra_instruction=extra)

    # Если идея не в приоритете — сохраняем в Notion
    if phase == "Подъём" or len(impulses) >= 2:
        notion.add_impulse(idea=idea_text, context=f"Фаза: {phase}")

    await update.message.reply_text(reply)
