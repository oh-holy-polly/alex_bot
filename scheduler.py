"""
scheduler.py — все запланированные задачи
"""

import logging
from datetime import datetime

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

    # Считаем время трёх будильников
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
    # Будильники (динамические)
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
