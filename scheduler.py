"""
scheduler.py — все запланированные задачи
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from config import TIMEZONE, EVENING_HOUR, EVENING_MINUTE, NIGHT_HOUR, NIGHT_MINUTE
from cache import get_wake_time, set_night_mode
from notion_manager import notion

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


# ───────────────────────────────────────────
# УТРО
# ───────────────────────────────────────────

async def job_alarm_1(app: Application):
    """Первый будильник — мягкое пробуждение"""
    from morning import send_alarm
    await send_alarm(app, attempt=1)


async def job_alarm_2(app: Application):
    """Второй будильник — настойчиво"""
    from morning import send_alarm
    await send_alarm(app, attempt=2)


async def job_alarm_3(app: Application):
    """Третий будильник — финальное предупреждение"""
    from morning import send_alarm
    await send_alarm(app, attempt=3)


async def job_social_nudge(app: Application):
    """Если нет фото к +30 мин — пинг контакту"""
    from morning import check_photo_and_nudge
    await check_photo_and_nudge(app)


# ───────────────────────────────────────────
# ДЕНЬ
# ───────────────────────────────────────────

async def job_task_check(app: Application):
    """Проверка активной задачи — Алекс заглядывает сам"""
    from day import check_active_task
    await check_active_task(app)


async def job_refresh_notion(app: Application):
    """Обновление кэша Notion каждые 15 минут"""
    notion.refresh_all_caches()
    logger.info("Notion cache refreshed")


async def job_proactive_check(app: Application):
    """
    Проактивный мыслитель — запускается каждые 2 часа с 11 до 21.
    Анализирует ситуацию и сам решает — писать Полине или нет.

    Пишет если одновременно:
    1. Прошло больше 2 часов с последнего сообщения от Полины
    2. Есть активные задачи ИЛИ невыполненные привычки
    """
    try:
        from cache import get_history, get_active_task, get_state
        from alex import ask_alex_smart

        now = datetime.now(TIMEZONE)

        # Проверяем когда было последнее сообщение от Полины
        history = get_history(limit=20)
        last_user_time = None
        for msg in reversed(history):
            if msg["role"] == "user":
                # Время не хранится в истории напрямую — проверяем через БД
                break

        # Получаем время последнего сообщения пользователя из БД
        from cache import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM messages WHERE role = 'user' ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if row:
            last_user_time = datetime.fromisoformat(row["created_at"])
            # Убираем timezone info для сравнения если нужно
            if last_user_time.tzinfo is None:
                last_user_time = TIMEZONE.localize(last_user_time)
            silence_hours = (now - last_user_time).total_seconds() / 3600
        else:
            # Никогда не писала — молчим
            return

        # Условие 1: прошло больше 2 часов
        if silence_hours < 2:
            return

        # Условие 2: есть активные задачи или невыполненные привычки
        active_task = get_active_task()
        habits = notion.get_habits()
        pending_habits = [h for h in habits if not h.get("done_today")]
        goals = notion.get_active_goals()

        has_something_pending = active_task or pending_habits or goals

        if not has_something_pending:
            logger.info("Proactive check: nothing pending, staying silent")
            return

        # Собираем контекст для решения
        phase = notion.get_cyclothymia_phase()
        moods = notion.get_recent_mood(days=1)
        score = moods[0]["score"] if moods and moods[0]["score"] else 5

        active_task_name = active_task.get("name") if active_task else None
        pending_habit_names = [h["name"] for h in pending_habits[:3]]
        goal_names = [g["name"] for g in goals[:2]]

        silence_str = f"{int(silence_hours)} час{'а' if 2 <= int(silence_hours) <= 4 else 'ов'}"

        extra = (
            f"Полина молчит уже {silence_str}. Сейчас {now.strftime('%H:%M')}.\n"
            f"Фаза: {phase}, настроение утром: {score}/10\n"
            f"{'Активная задача: ' + active_task_name if active_task_name else 'Активной задачи нет'}\n"
            f"{'Привычки не выполнены: ' + ', '.join(pending_habit_names) if pending_habit_names else 'Привычки выполнены'}\n"
            f"{'Активные цели: ' + ', '.join(goal_names) if goal_names else ''}\n\n"
            f"Ты Алекс — сам реши стоит ли написать Полине прямо сейчас.\n"
            f"Если она явно занята делом — лучше не мешать.\n"
            f"Если похоже что она завязла, забыла или саботирует — напиши один короткий вопрос.\n"
            f"Это должно звучать естественно, не как напоминалка из приложения.\n"
            f"Если решил не писать — ответь только словом: МОЛЧУ\n"
            f"Если решил написать — напиши само сообщение."
        )

        response = ask_alex_smart(extra)

        # Если модель решила молчать — не отправляем
        if response.strip().upper().startswith("МОЛЧУ"):
            logger.info("Proactive check: Alex decided to stay silent")
            return

        await app.bot.send_message(chat_id=app.bot_data.get("user_id", 0) or _get_user_id(), text=response)
        logger.info(f"Proactive message sent after {silence_str} of silence")

    except Exception as e:
        logger.error(f"job_proactive_check error: {e}")


def _get_user_id() -> int:
    """Получает USER_TELEGRAM_ID из конфига"""
    from config import USER_TELEGRAM_ID
    return USER_TELEGRAM_ID


# ───────────────────────────────────────────
# ВЕЧЕР И НОЧЬ
# ───────────────────────────────────────────

async def job_evening(app: Application):
    """Вечерний ритуал"""
    from evening import send_evening_ritual
    await send_evening_ritual(app)


async def job_night(app: Application):
    """Ночной вышибала"""
    set_night_mode(True)
    from evening import send_night_message
    await send_night_message(app)


# ───────────────────────────────────────────
# РЕТРОСПЕКТИВА
# ───────────────────────────────────────────

async def job_sunday_debrief(app: Application):
    """Воскресный дебрифинг — каждое воскресенье в 19:00"""
    from evening import send_weekly_debrief
    await send_weekly_debrief(app)


# ───────────────────────────────────────────
# НАСТРОЙКА БУДИЛЬНИКОВ
# ───────────────────────────────────────────

def schedule_alarms(app: Application):
    """
    Устанавливает три будильника на основе сохранённого времени подъёма.
    Вызывается при старте и каждый раз когда меняется время.
    """
    wake = get_wake_time()
    h, m = wake["hour"], wake["minute"]

    def add_minutes(hour, minute, delta):
        total = hour * 60 + minute + delta
        return total // 60 % 24, total % 60

    h2, m2 = add_minutes(h, m, 10)
    h3, m3 = add_minutes(h, m, 20)
    h_nudge, m_nudge = add_minutes(h, m, 30)

    for job_id in ["alarm_1", "alarm_2", "alarm_3", "social_nudge"]:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    scheduler.add_job(
        job_alarm_1, CronTrigger(hour=h, minute=m, timezone=TIMEZONE),
        id="alarm_1", args=[app], replace_existing=True
    )
    scheduler.add_job(
        job_alarm_2, CronTrigger(hour=h2, minute=m2, timezone=TIMEZONE),
        id="alarm_2", args=[app], replace_existing=True
    )
    scheduler.add_job(
        job_alarm_3, CronTrigger(hour=h3, minute=m3, timezone=TIMEZONE),
        id="alarm_3", args=[app], replace_existing=True
    )
    scheduler.add_job(
        job_social_nudge, CronTrigger(hour=h_nudge, minute=m_nudge, timezone=TIMEZONE),
        id="social_nudge", args=[app], replace_existing=True
    )

    logger.info(f"Будильники: {h:02d}:{m:02d} / {h2:02d}:{m2:02d} / {h3:02d}:{m3:02d}")


def setup_scheduler(app: Application):
    """
    Настраивает все задачи и запускает планировщик.
    Вызывается из main.py при старте.
    """
    schedule_alarms(app)

    # Проверка активной задачи каждые 30 минут с 10 до 22
    scheduler.add_job(
        job_task_check,
        CronTrigger(hour="10-22", minute="*/30", timezone=TIMEZONE),
        id="task_check", args=[app], replace_existing=True
    )

    # Обновление кэша Notion каждые 15 минут
    scheduler.add_job(
        job_refresh_notion,
        CronTrigger(minute="*/15", timezone=TIMEZONE),
        id="refresh_notion", args=[app], replace_existing=True
    )

    # Проактивный мыслитель — каждые 2 часа с 11 до 21
    scheduler.add_job(
        job_proactive_check,
        CronTrigger(hour="11-21", minute="0", second="0", timezone=TIMEZONE),
        id="proactive_check", args=[app], replace_existing=True
    )

    # Вечерний ритуал
    scheduler.add_job(
        job_evening,
        CronTrigger(hour=EVENING_HOUR, minute=EVENING_MINUTE, timezone=TIMEZONE),
        id="evening", args=[app], replace_existing=True
    )

    # Ночной вышибала
    scheduler.add_job(
        job_night,
        CronTrigger(hour=NIGHT_HOUR, minute=NIGHT_MINUTE, timezone=TIMEZONE),
        id="night", args=[app], replace_existing=True
    )

    # Воскресный дебрифинг — каждое воскресенье в 19:00
    scheduler.add_job(
        job_sunday_debrief,
        CronTrigger(day_of_week="sun", hour=19, minute=0, timezone=TIMEZONE),
        id="sunday_debrief", args=[app], replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler запущен")
