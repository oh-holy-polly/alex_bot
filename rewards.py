"""
rewards.py — система наград:
  - ежедневные титулы (генерирует 70b, уникальные)
  - артефакты в коллекцию Notion (раз в неделю)
  - Алекс сходит с ума (редко и неожиданно)
  - визуализация цели (за большие победы)
"""

import logging
import random
from datetime import datetime, timedelta

from config import TIMEZONE
from cache import get_state, set_state
from alex import ask_alex_system
from notion_manager import notion

logger = logging.getLogger(__name__)

# Ключи состояния наград
KEY_LAST_TITLE    = "last_title_date"
KEY_LAST_ARTIFACT = "last_artifact_date"
KEY_LAST_CRAZY    = "last_crazy_date"
KEY_TITLES_COUNT  = "titles_total_count"
KEY_WIN_STREAK    = "win_streak"


# ───────────────────────────────────────────
# ДЕТЕКТОР ПОБЕД
# ───────────────────────────────────────────

class WinType:
    SMALL   = "small"    # маленькая победа — ежедневное
    MEDIUM  = "medium"   # средняя — паттерн нескольких дней
    BIG     = "big"      # большая — закрыла важную цель


def detect_win(context: str) -> str:
    """Определяет размер победы по контексту"""
    context_lower = context.lower()

    big_keywords = [
        "закрыла проект", "сдала", "накопила", "долго", "наконец",
        "месяц", "неделю", "цель достигнута", "выполнила цель"
    ]
    medium_keywords = [
        "несколько дней", "третий день", "подряд", "снова сделала",
        "отчёт", "встреча прошла", "сложное"
    ]

    if any(w in context_lower for w in big_keywords):
        return WinType.BIG
    elif any(w in context_lower for w in medium_keywords):
        return WinType.MEDIUM
    return WinType.SMALL


# ───────────────────────────────────────────
# УРОВЕНЬ 1 — ЕЖЕДНЕВНЫЙ ТИТУЛ
# ───────────────────────────────────────────

async def give_title(win_context: str) -> str:
    """
    Генерирует уникальный титул для Полины.
    Вызывается после любой победы в течение дня.
    """
    try:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        last_title = get_state(KEY_LAST_TITLE, "")

        # Один титул в день максимум
        if last_title == today:
            return ""

        count = get_state(KEY_TITLES_COUNT, 0) + 1
        set_state(KEY_TITLES_COUNT, count)
        set_state(KEY_LAST_TITLE, today)

        instruction = (
            f"Придумай уникальный абсурдный титул для Полины за эту победу: «{win_context}»\n\n"
            f"Правила:\n"
            f"— Титул должен быть смешным и абсурдным\n"
            f"— Очень конкретным — про эту победу, не общий\n"
            f"— Формат: «Официальный титул: [название]»\n"
            f"— Примеры стиля: «Победительница Отчёта Который Никто Не Хотел Писать», "
            f"«Чемпион По Выживанию В Среду После Созвона»\n"
            f"— Это уже {count}-й титул за всё время\n"
            f"— Никогда не повторяй предыдущие"
        )

        title = ask_alex_system(instruction)
        logger.info(f"Title given: {title[:50]}")
        return title

    except Exception as e:
        logger.error(f"give_title error: {e}")
        return ""


# ───────────────────────────────────────────
# УРОВЕНЬ 2 — АРТЕФАКТ В КОЛЛЕКЦИЮ
# ───────────────────────────────────────────

# Артефакты привязаны к паттернам побед
ARTIFACT_TEMPLATES = [
    ("привычк", "витамин",   "💊 Бронзовая таблетка",    "За первые 7 дней витаминов"),
    ("привычк", "вода",      "💧 Хрустальный стакан",    "За 7 дней гидрации"),
    ("привычк", "витамин",   "✨ Золотая таблетка",       "За 30 дней витаминов подряд"),
    ("утро",    "встала",    "🌅 Медаль раннего подъёма", "За 5 утр без войны с будильником"),
    ("цикл",    "пмс",       "🏅 Медаль выживания",       "За выживание в ПМС без катастроф"),
    ("задач",   "отчёт",     "📄 Бронзовый отчёт",       "За сданный отчёт через не хочу"),
    ("спад",    "вышла",     "🌱 Росток",                 "За выход из спада"),
    ("неделю",  "подряд",    "⚡️ Недельный заряд",        "За продуктивную неделю"),
]


async def maybe_give_artifact(win_context: str, app=None) -> str:
    """
    Проверяет — заслужила ли Полина артефакт.
    Артефакт даётся раз в неделю примерно, за паттерн побед.
    """
    try:
        now = datetime.now(TIMEZONE)
        last_str = get_state(KEY_LAST_ARTIFACT, "")

        if last_str:
            last = datetime.fromisoformat(last_str)
            if now - last < timedelta(days=5):
                return ""  # слишком рано

        # Ищем подходящий артефакт
        context_lower = win_context.lower()
        artifact = None

        for keyword1, keyword2, name, description in ARTIFACT_TEMPLATES:
            if keyword1 in context_lower or keyword2 in context_lower:
                artifact = (name, description)
                break

        if not artifact:
            # Случайный если не нашли подходящий
            a = random.choice(ARTIFACT_TEMPLATES)
            artifact = (a[2], a[3])

        name, description = artifact
        set_state(KEY_LAST_ARTIFACT, now.isoformat())

        # Сохраняем в Notion архив
        notion.add_to_archive(
            title=f"Артефакт: {name}",
            content=f"{description}\nПолучен: {now.strftime('%d.%m.%Y')}",
            tags=["артефакт", "награда"]
        )

        # Алекс объявляет артефакт
        announcement = ask_alex_system(
            f"Полина только что получила артефакт в коллекцию: {name} — {description}. "
            f"Объяви это коротко и по-алексовски. Намекни что это теперь в её коллекции навсегда."
        )

        logger.info(f"Artifact given: {name}")
        return announcement

    except Exception as e:
        logger.error(f"maybe_give_artifact error: {e}")
        return ""


# ───────────────────────────────────────────
# УРОВЕНЬ 3 — АЛЕКС СХОДИТ С УМА
# ───────────────────────────────────────────

CRAZY_FORMATS = [
    "стихотворение",
    "пьеса в трёх действиях (очень коротко)",
    "новостная заметка",
    "отрывок из романа",
    "официальный указ",
    "речь на церемонии вручения премии",
]


async def maybe_go_crazy(win_context: str) -> str:
    """
    Редко (раз в 2-3 недели) и неожиданно — Алекс сходит с ума.
    За что-то реально крутое.
    """
    try:
        now = datetime.now(TIMEZONE)
        last_str = get_state(KEY_LAST_CRAZY, "")

        if last_str:
            last = datetime.fromisoformat(last_str)
            if now - last < timedelta(days=14):
                return ""

        # 30% шанс срабатывания (если прошло 14+ дней)
        if random.random() > 0.3:
            return ""

        fmt = random.choice(CRAZY_FORMATS)
        set_state(KEY_LAST_CRAZY, now.isoformat())

        instruction = (
            f"Полина сделала что-то реально крутое: «{win_context}».\n\n"
            f"Напиши про это {fmt}. "
            f"Коротко (максимум 8 строк), смешно, абсурдно. "
            f"Это особый момент — Алекс сходит с ума от восхищения."
        )

        result = ask_alex_system(instruction)
        logger.info(f"Crazy reward triggered: {fmt}")
        return result

    except Exception as e:
        logger.error(f"maybe_go_crazy error: {e}")
        return ""


# ───────────────────────────────────────────
# СТРИК ПОБЕД
# ───────────────────────────────────────────

def update_win_streak() -> int:
    """Обновляет стрик побед и возвращает текущий"""
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    streak_data = get_state(KEY_WIN_STREAK, {"count": 0, "last_date": ""})

    last = streak_data.get("last_date", "")
    count = streak_data.get("count", 0)

    yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")

    if last == today:
        return count  # уже засчитано сегодня
    elif last == yesterday:
        count += 1  # стрик продолжается
    else:
        count = 1  # стрик сломан, начинаем заново

    set_state(KEY_WIN_STREAK, {"count": count, "last_date": today})
    return count


# ───────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ — вызывается из main.py
# ───────────────────────────────────────────

async def process_win(win_context: str, app=None) -> list[str]:
    """
    Обрабатывает победу и возвращает список сообщений для отправки.
    Алекс сам решает что выдать — титул, артефакт, или сойти с ума.

    win_context — описание что произошло (закрыла задачу, сделала привычку и т.д.)
    """
    messages = []
    win_type = detect_win(win_context)
    streak = update_win_streak()

    # Уровень 1 — титул (каждый день)
    title = await give_title(win_context)
    if title:
        messages.append(title)

    # Уровень 2 — артефакт (раз в неделю, за средние и большие победы)
    if win_type in (WinType.MEDIUM, WinType.BIG):
        artifact = await maybe_give_artifact(win_context, app)
        if artifact:
            messages.append(artifact)

    # Уровень 3 — Алекс сходит с ума (только за большие)
    if win_type == WinType.BIG:
        crazy = await maybe_go_crazy(win_context)
        if crazy:
            messages.append(crazy)

    # Визуализация цели (за большие победы)
    if win_type == WinType.BIG and app:
        goals = notion.get_active_goals()
        if goals:
            top_goal = goals[0]["name"]
            try:
                from image_gen import generate_goal_image
                image_path = await generate_goal_image(top_goal)
                if image_path:
                    # Передаём путь — main.py отправит как фото
                    messages.append(f"__IMAGE__:{image_path}")
            except Exception as e:
                logger.error(f"Goal image error: {e}")

    # Стрик-сообщение каждые 7 дней
    if streak > 0 and streak % 7 == 0:
        streak_msg = ask_alex_system(
            f"Полина делает что-то хорошее {streak} дней подряд. "
            f"Отметь это одной фразой — по-алексовски, без пафоса."
        )
        messages.append(streak_msg)

    return messages


# ───────────────────────────────────────────
# ХЕЛПЕР ДЛЯ main.py
# ───────────────────────────────────────────

async def send_rewards(win_context: str, app, chat_id: int):
    """Обрабатывает победу и отправляет все награды"""
    import os
    messages = await process_win(win_context, app)

    for msg in messages:
        if msg.startswith("__IMAGE__:"):
            image_path = msg.replace("__IMAGE__:", "")
            try:
                with open(image_path, "rb") as f:
                    await app.bot.send_photo(chat_id=chat_id, photo=f)
                os.remove(image_path)
            except Exception as e:
                logger.error(f"send reward image error: {e}")
        else:
            await app.bot.send_message(chat_id=chat_id, text=msg)
