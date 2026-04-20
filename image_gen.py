"""
image_gen.py — генерация утренней картинки:
- фото с Unsplash по настроению
- личная фраза от Алекса через 70b
- Pillow: текст сверху поверх фото
- отправка в Telegram
"""

import logging
import os
import random
import io
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import TIMEZONE, BASE_DIR
from alex import ask_alex_system, ask_alex_smart
from notion_manager import notion

logger = logging.getLogger(__name__)

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

OUTPUT_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Размер картинки 4:5
IMG_WIDTH  = 800
IMG_HEIGHT = 1000

# Шрифт — DejaVu Bold, есть на Ubuntu по умолчанию
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ───────────────────────────────────────────
# UNSPLASH
# ───────────────────────────────────────────

MOOD_QUERIES = {
    "нежный":          ["soft morning light", "cozy pastel nature", "gentle fog landscape", "calm water reflection"],
    "дерзкий":         ["bold dramatic sky", "urban architecture contrast", "stormy ocean power", "sharp mountain peak"],
    "кинематографичный": ["cinematic moody landscape", "foggy forest road", "dark aesthetic nature", "rainy city night"],
}

PHASE_TO_STYLE = {
    "Подъём": "дерзкий",
    "Норма":  "кинематографичный",
    "Спад":   "нежный",
}

def get_unsplash_photo(query: str) -> bytes | None:
    """Скачивает фото с Unsplash, возвращает байты"""
    try:
        if not UNSPLASH_ACCESS_KEY:
            logger.error("UNSPLASH_ACCESS_KEY не задан")
            return None

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
        resp.raise_for_status()
        photo_url = resp.json()["urls"]["regular"]

        photo_resp = requests.get(photo_url, timeout=15)
        photo_resp.raise_for_status()
        return photo_resp.content

    except Exception as e:
        logger.error(f"Unsplash error: {e}")
        return None

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
        f"— Одна фраза, максимум 6-8 слов — она будет крупно напечатана на картинке\n"
        f"— Личная, под этот конкретный день\n"
        f"— Не банальная мотивашка\n"
        f"— Может быть резкой, нежной или смешной — Алекс сам чувствует что нужно\n"
        f"— Без подписи, без имени, просто фраза\n"
        f"— Только текст, никаких кавычек\n\n"
        f"Примеры стиля (не копировать, только ориентир):\n"
        f"— «Сегодня выживи. Этого достаточно»\n"
        f"— «Дохуя хочу — дохуя получу»\n"
        f"— «Сегодня самый лучший день»\n"
        f"— «ПМС день 2. Ты справишься»"
    )
    return ask_alex_smart(instruction)

# ───────────────────────────────────────────
# РЕНДЕР ЧЕРЕЗ PILLOW
# ───────────────────────────────────────────

def render_image(photo_bytes: bytes, phrase: str) -> Image.Image:
    """Накладывает текст сверху на фото"""

    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    img = img.resize((IMG_WIDTH, IMG_HEIGHT), Image.LANCZOS)

    draw = ImageDraw.Draw(img)

    # Тёмный градиент сверху чтобы текст читался
    gradient = Image.new("RGBA", (IMG_WIDTH, IMG_HEIGHT // 2), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(IMG_HEIGHT // 2):
        alpha = int(180 * (1 - y / (IMG_HEIGHT // 2)))
        grad_draw.line([(0, y), (IMG_WIDTH, y)], fill=(0, 0, 0, alpha))

    img = img.convert("RGBA")
    img.paste(gradient, (0, 0), gradient)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Шрифт
    font_size = 110
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except Exception:
        logger.warning("DejaVu не найден, использую дефолтный шрифт")
        font = ImageFont.load_default()

    # Разбиваем фразу на слова, каждое слово — отдельная строка
    words = phrase.upper().split()

    # Подбираем размер шрифта чтобы самое длинное слово влезало
    max_word = max(words, key=len)
    while font_size > 40:
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            break
        bbox = draw.textbbox((0, 0), max_word, font=font)
        word_width = bbox[2] - bbox[0]
        if word_width <= IMG_WIDTH - 80:
            break
        font_size -= 5

    # Считаем высоту строки
    bbox = draw.textbbox((0, 0), "A", font=font)
    line_height = (bbox[3] - bbox[1]) + 10

    # Рисуем слова сверху вниз
    y = 50
    for word in words:
        draw.text((40, y), word, font=font, fill="white")
        y += line_height

    return img

# ───────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ───────────────────────────────────────────

async def generate_morning_image() -> str | None:
    """
    Генерирует утреннюю картинку.
    Возвращает путь к файлу или None если что-то пошло не так.
    """
    try:
        phase = notion.get_cyclothymia_phase()
        moods = notion.get_recent_mood(days=1)
        score = moods[0]["score"] if moods and moods[0]["score"] else 5
        cycle = notion.get_cycle_phase()
        cycle_phase = cycle.get("phase", "")

        style = PHASE_TO_STYLE.get(phase, "кинематографичный")
        if random.random() < 0.2:
            style = random.choice(list(MOOD_QUERIES.keys()))

        query = random.choice(MOOD_QUERIES[style])
        photo_bytes = get_unsplash_photo(query)
        if not photo_bytes:
            return None

        phrase = generate_morning_phrase(phase, score, cycle_phase)
        img = render_image(photo_bytes, phrase)

        now = datetime.now(TIMEZONE)
        output_path = os.path.join(OUTPUT_DIR, f"morning_{now.strftime('%Y%m%d_%H%M')}.jpg")
        img.save(output_path, "JPEG", quality=92)

        logger.info(f"Morning image generated: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"generate_morning_image error: {e}")
        return None


async def send_morning_image(message) -> bool:
    """
    Генерирует и отправляет утреннюю картинку.
    FIX: принимает message (объект сообщения) вместо app/bot —
    это согласуется с вызовом из morning.py.
    Возвращает True если отправила, False если нет.
    """
    from config import USER_TELEGRAM_ID
    try:
        image_path = await generate_morning_image()
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                await message.bot.send_photo(chat_id=USER_TELEGRAM_ID, photo=f)
            os.remove(image_path)
            return True
        return False
    except Exception as e:
        logger.error(f"send_morning_image error: {e}")
        return False

# ───────────────────────────────────────────
# ВИЗУАЛИЗАЦИЯ ЦЕЛИ (для наград)
# ───────────────────────────────────────────

async def generate_goal_image(goal_name: str) -> str | None:
    """Генерирует картинку для визуализации цели"""
    try:
        goal_queries = {
            "грузия":    ["georgia tbilisi", "caucasus mountains", "tbilisi old town"],
            "путешест":  ["travel adventure", "scenic road", "explore world"],
            "накопить":  ["abundance prosperity", "golden hour calm", "peaceful achievement"],
        }

        query = "dream achievement success"
        goal_lower = goal_name.lower()
        for key, queries in goal_queries.items():
            if key in goal_lower:
                query = random.choice(queries)
                break

        photo_bytes = get_unsplash_photo(query)
        if not photo_bytes:
            return None

        phrase = ask_alex_smart(
            f"Полина сделала что-то важное в направлении цели: «{goal_name}». "
            f"Напиши одну фразу — что она на шаг ближе. "
            f"Максимум 6 слов, коротко, лично, без банальщины. Только текст."
        )

        img = render_image(photo_bytes, phrase)

        now = datetime.now(TIMEZONE)
        output_path = os.path.join(OUTPUT_DIR, f"goal_{now.strftime('%Y%m%d_%H%M%S')}.jpg")
        img.save(output_path, "JPEG", quality=92)

        return output_path

    except Exception as e:
        logger.error(f"generate_goal_image error: {e}")
        return None
