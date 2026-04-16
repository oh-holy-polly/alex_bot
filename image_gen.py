"""
image_gen.py — генерация утренней картинки:
  - фото с Unsplash по настроению
  - личная фраза от Алекса через 70b
  - HTML-шаблон + playwright скриншот
  - отправка в Telegram
"""

import logging
import os
import random
import asyncio
from datetime import datetime

import requests
from playwright.async_api import async_playwright

from config import TIMEZONE, BASE_DIR
from alex import ask_alex_system
from notion_manager import notion

logger = logging.getLogger(__name__)

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR    = os.path.join(BASE_DIR, "temp")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ───────────────────────────────────────────
# UNSPLASH
# ───────────────────────────────────────────

# Теги под настроение
MOOD_QUERIES = {
    "нежный":        ["soft morning", "cozy room", "morning light", "calm nature"],
    "дерзкий":       ["bold architecture", "dramatic sky", "urban energy", "power nature"],
    "кинематографичный": ["cinematic landscape", "moody film", "dark aesthetic", "foggy forest"],
}

PHASE_TO_STYLE = {
    "Подъём": "дерзкий",
    "Норма":  "кинематографичный",
    "Спад":   "нежный",
}


def get_unsplash_photo(query: str) -> str | None:
    """Возвращает URL фото с Unsplash"""
    try:
        if not UNSPLASH_ACCESS_KEY:
            # Fallback — случайное фото без API
            return f"https://source.unsplash.com/800x1200/?{query.replace(' ', ',')}"

        resp = requests.get(
            "https://api.unsplash.com/photos/random",
            params={
                "query": query,
                "orientation": "portrait",
                "content_filter": "high",
            },
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10
        )
        data = resp.json()
        return data["urls"]["regular"]
    except Exception as e:
        logger.error(f"Unsplash error: {e}")
        return f"https://source.unsplash.com/800x1200/?{query.replace(' ', ',')}"


# ───────────────────────────────────────────
# ГЕНЕРАЦИЯ ФРАЗЫ
# ───────────────────────────────────────────

def generate_morning_phrase(phase: str, score: int, cycle_phase: str) -> str:
    """Генерирует личную утреннюю фразу через Алекса"""
    now = datetime.now(TIMEZONE)
    day_name = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]

    instruction = (
        f"Сгенерируй одну утреннюю фразу для Полины.\n"
        f"Сегодня {day_name}, настроение {score}/10, фаза: {phase}, цикл: {cycle_phase}.\n\n"
        f"Правила:\n"
        f"— Одна фраза, максимум две строки\n"
        f"— Личная, под этот конкретный день\n"
        f"— Не банальная мотивашка\n"
        f"— Может быть резкой, нежной или смешной — Алекс сам чувствует что нужно\n"
        f"— Без подписи, без имени, просто фраза\n\n"
        f"Примеры стиля (не копировать, только ориентир):\n"
        f"— «Сегодня среда, ПМС день 2, впереди три встречи. Выживи. Это уже победа»\n"
        f"— «Дохуя хочу — дохуя получу»\n"
        f"— «Сегодня самый лучший день»"
    )
    return ask_alex_system(instruction)


# ───────────────────────────────────────────
# HTML ШАБЛОНЫ
# ───────────────────────────────────────────

def render_html(photo_url: str, phrase: str, style: str) -> str:
    """Рендерит HTML для скриншота"""

    styles = {
        "нежный": {
            "font": "Georgia, serif",
            "font_size": "52px",
            "font_weight": "400",
            "color": "rgba(255,255,255,0.92)",
            "text_shadow": "0 2px 20px rgba(0,0,0,0.3)",
            "overlay": "rgba(0,0,0,0.15)",
            "position": "center",
        },
        "дерзкий": {
            "font": "'Arial Black', sans-serif",
            "font_size": "64px",
            "font_weight": "900",
            "color": "#ffffff",
            "text_shadow": "none",
            "overlay": "rgba(0,0,0,0.25)",
            "position": "center-left",
        },
        "кинематографичный": {
            "font": "'Helvetica Neue', Arial, sans-serif",
            "font_size": "44px",
            "font_weight": "300",
            "color": "rgba(255,255,255,0.88)",
            "text_shadow": "0 1px 30px rgba(0,0,0,0.5)",
            "overlay": "rgba(0,0,0,0.35)",
            "position": "bottom",
        },
    }

    s = styles.get(style, styles["кинематографичный"])

    text_align = "left" if s["position"] == "center-left" else "center"
    valign = "flex-end" if s["position"] == "bottom" else "center"
    padding = "0 48px 80px" if s["position"] == "bottom" else "0 48px"

    # Разбиваем фразу на строки для красивого отображения
    words = phrase.split()
    if len(words) > 5:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        phrase_html = f"{line1}<br>{line2}"
    else:
        phrase_html = phrase

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 800px;
    height: 1200px;
    overflow: hidden;
    font-family: {s["font"]};
  }}
  .bg {{
    position: absolute;
    inset: 0;
    background-image: url('{photo_url}');
    background-size: cover;
    background-position: center;
  }}
  .overlay {{
    position: absolute;
    inset: 0;
    background: {s["overlay"]};
  }}
  .content {{
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    justify-content: {valign};
    align-items: {text_align};
    padding: {padding};
    text-align: {text_align};
  }}
  .phrase {{
    font-size: {s["font_size"]};
    font-weight: {s["font_weight"]};
    color: {s["color"]};
    text-shadow: {s["text_shadow"]};
    line-height: 1.2;
    letter-spacing: -0.02em;
  }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="overlay"></div>
  <div class="content">
    <div class="phrase">{phrase_html}</div>
  </div>
</body>
</html>"""
    return html


# ───────────────────────────────────────────
# СКРИНШОТ ЧЕРЕЗ PLAYWRIGHT
# ───────────────────────────────────────────

async def html_to_image(html: str, output_path: str) -> bool:
    """Делает скриншот HTML страницы"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 800, "height": 1200})
            await page.set_content(html, wait_until="networkidle")
            await asyncio.sleep(1)  # ждём загрузки фото
            await page.screenshot(path=output_path, full_page=False)
            await browser.close()
        return True
    except Exception as e:
        logger.error(f"html_to_image error: {e}")
        return False


# ───────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ───────────────────────────────────────────

async def generate_morning_image() -> str | None:
    """
    Генерирует утреннюю картинку.
    Возвращает путь к файлу или None если что-то пошло не так.
    """
    try:
        # Берём контекст
        phase      = notion.get_cyclothymia_phase()
        moods      = notion.get_recent_mood(days=1)
        score      = moods[0]["score"] if moods and moods[0]["score"] else 5
        cycle      = notion.get_cycle_phase()
        cycle_phase = cycle.get("phase", "")

        # Выбираем стиль
        style = PHASE_TO_STYLE.get(phase, "кинематографичный")

        # Иногда случайный стиль для сюрприза (20% шанс)
        if random.random() < 0.2:
            style = random.choice(list(MOOD_QUERIES.keys()))

        # Фото с Unsplash
        query = random.choice(MOOD_QUERIES[style])
        photo_url = get_unsplash_photo(query)
        if not photo_url:
            return None

        # Фраза от Алекса
        phrase = generate_morning_phrase(phase, score, cycle_phase)

        # Рендерим HTML
        html = render_html(photo_url, phrase, style)

        # Скриншот
        now = datetime.now(TIMEZONE)
        output_path = os.path.join(OUTPUT_DIR, f"morning_{now.strftime('%Y%m%d_%H%M')}.png")

        success = await html_to_image(html, output_path)
        if not success:
            return None

        logger.info(f"Morning image generated: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"generate_morning_image error: {e}")
        return None


async def send_morning_image(app, fallback_text: str = ""):
    """Генерирует и отправляет утреннюю картинку"""
    from config import USER_TELEGRAM_ID
    try:
        image_path = await generate_morning_image()
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                await app.bot.send_photo(chat_id=USER_TELEGRAM_ID, photo=f)
            os.remove(image_path)  # чистим temp
        elif fallback_text:
            await app.bot.send_message(chat_id=USER_TELEGRAM_ID, text=fallback_text)
    except Exception as e:
        logger.error(f"send_morning_image error: {e}")


# ───────────────────────────────────────────
# ВИЗУАЛИЗАЦИЯ ЦЕЛИ (для наград)
# ───────────────────────────────────────────

async def generate_goal_image(goal_name: str) -> str | None:
    """
    Генерирует картинку для визуализации цели.
    Используется в системе наград за большие победы.
    """
    try:
        # Запрос под конкретную цель
        goal_queries = {
            "грузия": ["georgia tbilisi", "caucasus mountains", "tbilisi old town"],
            "путешест": ["travel adventure", "scenic road", "explore world"],
            "накопить": ["abundance prosperity", "golden hour calm", "peaceful achievement"],
        }

        query = "dream achievement success"
        goal_lower = goal_name.lower()
        for key, queries in goal_queries.items():
            if key in goal_lower:
                query = random.choice(queries)
                break

        photo_url = get_unsplash_photo(query)
        if not photo_url:
            return None

        phrase = ask_alex_system(
            f"Полина сделала что-то важное в направлении цели: «{goal_name}». "
            f"Напиши одну фразу — что она на шаг ближе. "
            f"Коротко, лично, без банальщины."
        )

        html = render_html(photo_url, phrase, "кинематографичный")
        now = datetime.now(TIMEZONE)
        output_path = os.path.join(OUTPUT_DIR, f"goal_{now.strftime('%Y%m%d_%H%M%S')}.png")

        success = await html_to_image(html, output_path)
        return output_path if success else None

    except Exception as e:
        logger.error(f"generate_goal_image error: {e}")
        return None
