"""
Gamification Module v11.0 for Alex Bot
Pinterest-style achievement cards with Pollinations AI + Pillow
"""

import logging
from datetime import datetime, timedelta
import pytz
from typing import Dict, List, Optional, Any, Tuple
import json
import os
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
TIMEZONE = pytz.timezone("Europe/Minsk")

# Achievements database (stored locally, can be synced to Notion)
ACHIEVEMENTS_FILE = 'achievements.json'
STREAKS_FILE = 'streaks.json'
CARDS_CACHE_DIR = 'achievement_cards'

# Create cache directory if it doesn't exist
os.makedirs(CARDS_CACHE_DIR, exist_ok=True)

def load_achievements():
    """Load achievements from file"""
    if os.path.exists(ACHIEVEMENTS_FILE):
        with open(ACHIEVEMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "unlocked": [],
        "progress": {}
    }

def save_achievements(achievements):
    """Save achievements to file"""
    with open(ACHIEVEMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(achievements, f, ensure_ascii=False, indent=4)

def load_streaks():
    """Load streaks from file"""
    if os.path.exists(STREAKS_FILE):
        with open(STREAKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "focus_streak": 0,
        "last_focus_date": None,
        "habit_streaks": {}
    }

def save_streaks(streaks):
    """Save streaks to file"""
    with open(STREAKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(streaks, f, ensure_ascii=False, indent=4)

# --- Achievement Definitions with Stylish Emojis --- #
ACHIEVEMENT_DEFINITIONS = {
    "early_bird": {
        "name": "Ранняя пташка",
        "description": "Проснулась до 11:00",
        "emoji": "☀️",
        "points": 10,
        "rarity": "common",
        "motivation": "Красотка, ты проснулась до 11! ☀️ Это уже половина победы. Держи темп!",
        "color_scheme": ("FFF8DC", "FFE4B5", "DEB887")  # Cream to tan gradient
    },
    "hydration_hero": {
        "name": "Герой гидратации",
        "description": "Выпила воду в утренний ритуал",
        "emoji": "☕️",
        "points": 5,
        "rarity": "common",
        "motivation": "Вода — это жизнь, Полина! ☕️ Продолжай в том же духе.",
        "color_scheme": ("E0F2F7", "B3E5FC", "81D4FA")  # Light blue gradient
    },
    "window_watcher": {
        "name": "Наблюдатель окна",
        "description": "Посмотрела в окно с утра",
        "emoji": "🌿",
        "points": 5,
        "rarity": "common",
        "motivation": "Мир снаружи тебя ждет, Поля! 🌿 Хорошее начало.",
        "color_scheme": ("F1F8E9", "C8E6C9", "A5D6A7")  # Light green gradient
    },
    "shoe_warrior": {
        "name": "Воин кроссовок",
        "description": "Надела кроссовки и готова к действию",
        "emoji": "⚡️",
        "points": 5,
        "rarity": "common",
        "motivation": "Кроссовки надеты, мир не готов! ⚡️ Давай!",
        "color_scheme": ("FCE4EC", "F8BBD0", "F48FB1")  # Light pink gradient
    },
    "morning_ritual_master": {
        "name": "Мастер утреннего ритуала",
        "description": "Выполнила все 3 утренних ритуала подряд",
        "emoji": "✨",
        "points": 25,
        "rarity": "rare",
        "motivation": "Полина, ты королева! ✨ Все 3 ритуала выполнены. Это красиво.",
        "color_scheme": ("FFF9C4", "FFF59D", "FFF176")  # Golden gradient
    },
    "task_slayer": {
        "name": "Убийца задач",
        "description": "Завершила 3 задачи за день",
        "emoji": "🔥",
        "points": 30,
        "rarity": "rare",
        "motivation": "3 задачи за день? 🔥 Ты просто легенда, Поля!",
        "color_scheme": ("FFEBEE", "FFCDD2", "EF9A9A")  # Red gradient
    },
    "focus_master": {
        "name": "Мастер фокуса",
        "description": "7-дневный стрик фокуса",
        "emoji": "🧠",
        "points": 50,
        "rarity": "epic",
        "motivation": "7 дней фокуса! 🧠 Ты неостановима, Полина!",
        "color_scheme": ("F3E5F5", "E1BEE7", "CE93D8")  # Purple gradient
    },
    "mood_tracker": {
        "name": "Трекер настроения",
        "description": "Логировала настроение 7 дней подряд",
        "emoji": "🌝",
        "points": 40,
        "rarity": "epic",
        "motivation": "Неделя отслеживания! 🌝 Ты знаешь себя, Поля.",
        "color_scheme": ("ECE0F3", "D9C9E8", "C4B3DD")  # Lavender gradient
    },
    "impulse_warrior": {
        "name": "Воин импульса",
        "description": "Прошла 48-часовой фильтр импульса без покупки",
        "emoji": "🛡️",
        "points": 35,
        "rarity": "rare",
        "motivation": "Ты устояла перед импульсом! 🛡️ Я горжусь, Полина.",
        "color_scheme": ("E8F5E9", "C8E6C9", "A5D6A7")  # Green gradient
    },
    "dream_analyst": {
        "name": "Аналитик снов",
        "description": "Записала и проанализировала 5 снов",
        "emoji": "🌸",
        "points": 25,
        "rarity": "rare",
        "motivation": "5 снов проанализировано! 🌸 Твой подсознательный мир раскрывается.",
        "color_scheme": ("FCE4EC", "F8BBD0", "F48FB1")  # Pink gradient
    },
    "cyclothymia_navigator": {
        "name": "Навигатор циклотимии",
        "description": "Успешно прошла через спад и вернулась в норму",
        "emoji": "🌚",
        "points": 60,
        "rarity": "legendary",
        "motivation": "Ты прошла через спад и вышла сильнее! 🌚 Легенда, Полина!",
        "color_scheme": ("F5F5F5", "E0E0E0", "BDBDBD")  # Gray gradient
    },
    "brain_dump_master": {
        "name": "Мастер выгрузки мозга",
        "description": "Сделала 5 выгрузок мозга (voice messages)",
        "emoji": "🫶🏻",
        "points": 30,
        "rarity": "rare",
        "motivation": "5 выгрузок мозга! 🫶🏻 Ты честна с собой, Поля.",
        "color_scheme": ("FFE0B2", "FFCC80", "FFB74D")  # Orange gradient
    },
    "week_warrior": {
        "name": "Боец недели",
        "description": "Прошла неделю без критических провалов",
        "emoji": "👏🏻",
        "points": 100,
        "rarity": "legendary",
        "motivation": "Неделя без провалов! 👏🏻 Ты просто невероятна, Полина!",
        "color_scheme": ("FFF9C4", "FFF59D", "FFF176")  # Golden gradient
    }
}

# --- Pollinations AI Integration --- #
def generate_abstract_background(color_scheme: Tuple[str, str, str], style: str = "grainy") -> Optional[Image.Image]:
    """Generate abstract aesthetic background using Pollinations AI"""
    try:
        # Create a prompt for aesthetic abstract background
        prompt = f"""
        Aesthetic abstract background, {style} texture, gradient from #{color_scheme[0]} to #{color_scheme[1]} to #{color_scheme[2]},
        minimalist design, organic shapes, high resolution, clean, modern, no text, no people.
        Trending on Pinterest, interior design aesthetic, calm and sophisticated.
        """
        
        # Use Pollinations API (free, no key required)
        url = "https://image.pollinations.ai/prompt/" + prompt.replace(" ", "%20")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Open image from response
        img = Image.open(BytesIO(response.content))
        
        # Resize to standard achievement card size (1080x1350 for Instagram/Pinterest)
        img = img.resize((1080, 1350), Image.Resampling.LANCZOS)
        
        logger.info(f"Generated background successfully")
        return img
        
    except Exception as e:
        logger.error(f"Pollinations API error: {e}")
        # Fallback: create a simple gradient background
        return create_fallback_gradient(color_scheme)

def create_fallback_gradient(color_scheme: Tuple[str, str, str]) -> Image.Image:
    """Create a simple gradient background as fallback"""
    try:
        width, height = 1080, 1350
        img = Image.new('RGB', (width, height))
        pixels = img.load()
        
        # Parse hex colors
        color1 = tuple(int(color_scheme[0][i:i+2], 16) for i in (0, 2, 4))
        color2 = tuple(int(color_scheme[2][i:i+2], 16) for i in (0, 2, 4))
        
        # Create gradient
        for y in range(height):
            ratio = y / height
            r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
            g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
            b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
            
            for x in range(width):
                pixels[x, y] = (r, g, b)
        
        return img
    except Exception as e:
        logger.error(f"Fallback gradient error: {e}")
        return Image.new('RGB', (1080, 1350), color=(200, 200, 200))

# --- Achievement Card Generation --- #
def generate_achievement_card(achievement_id: str, user_id: str, progress: Optional[Dict] = None) -> Optional[str]:
    """Generate a beautiful achievement card image"""
    
    if achievement_id not in ACHIEVEMENT_DEFINITIONS:
        return None
    
    achievement = ACHIEVEMENT_DEFINITIONS[achievement_id]
    
    try:
        # Generate or get background
        background = generate_abstract_background(achievement["color_scheme"])
        
        # Create a copy to draw on
        card = background.copy()
        draw = ImageDraw.Draw(card, 'RGBA')
        
        # Try to load a nice font (fallback to default if not available)
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 50)
            info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            info_font = ImageFont.load_default()
        
        # Draw semi-transparent overlay for text readability
        overlay = Image.new('RGBA', card.size, (0, 0, 0, 80))
        card = Image.alpha_composite(card.convert('RGBA'), overlay).convert('RGB')
        draw = ImageDraw.Draw(card)
        
        # Draw emoji (large, centered top)
        emoji_y = 150
        draw.text((540, emoji_y), achievement["emoji"], font=title_font, fill=(255, 255, 255), anchor="mm")
        
        # Draw achievement name (centered)
        name_y = 400
        draw.text((540, name_y), achievement["name"], font=title_font, fill=(255, 255, 255), anchor="mm")
        
        # Draw description (centered)
        desc_y = 550
        draw.text((540, desc_y), achievement["description"], font=subtitle_font, fill=(220, 220, 220), anchor="mm")
        
        # Draw points and date (bottom)
        date_str = datetime.now(TIMEZONE).strftime("%d.%m.%Y")
        points_text = f"+{achievement['points']} ОЧКОВ"
        
        draw.text((540, 1200), points_text, font=info_font, fill=(255, 255, 255), anchor="mm")
        draw.text((540, 1280), date_str, font=info_font, fill=(200, 200, 200), anchor="mm")
        
        # Save card
        card_path = os.path.join(CARDS_CACHE_DIR, f"{achievement_id}_{user_id}_{datetime.now().timestamp()}.png")
        card.save(card_path, 'PNG')
        
        logger.info(f"Achievement card generated: {card_path}")
        return card_path
        
    except Exception as e:
        logger.error(f"Card generation error: {e}")
        return None

# --- Achievement Logic --- #
def check_early_bird(user_id: str) -> Optional[Dict[str, Any]]:
    """Check if user woke up early"""
    current_hour = datetime.now(TIMEZONE).hour
    if current_hour < 11:
        return {
            "achievement_id": "early_bird",
            "unlocked": True,
            "message": "☀️ Ранняя пташка! Проснулась до 11:00. +10 очков!"
        }
    return None

def check_morning_ritual_completion(water: bool, window: bool, shoes: bool) -> Optional[Dict[str, Any]]:
    """Check if all morning rituals are completed"""
    if water and window and shoes:
        return {
            "achievement_id": "morning_ritual_master",
            "unlocked": True,
            "message": "✨ Мастер утреннего ритуала! Все 3 ритуала выполнены. +25 очков!"
        }
    return None

def check_focus_streak(streaks: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Check if focus streak milestone is reached"""
    current_streak = streaks.get("focus_streak", 0)
    if current_streak == 7:
        return {
            "achievement_id": "focus_master",
            "unlocked": True,
            "message": "🧠 Мастер фокуса! 7-дневный стрик! +50 очков!"
        }
    elif current_streak == 14:
        return {
            "achievement_id": "focus_master_extended",
            "unlocked": True,
            "message": "🧠🔥 ЛЕГЕНДА ФОКУСА! 14 дней подряд! +100 очков!"
        }
    return None

def update_focus_streak(streaks: Dict[str, Any]) -> Dict[str, Any]:
    """Update focus streak based on daily activity"""
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    last_focus_date = streaks.get("last_focus_date")
    
    if last_focus_date == today:
        return streaks
    
    yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if last_focus_date == yesterday:
        streaks["focus_streak"] += 1
    else:
        streaks["focus_streak"] = 1
    
    streaks["last_focus_date"] = today
    return streaks

def get_motivation_message(achievement_id: str, current_streak: int = 0) -> str:
    """Get personalized motivation message"""
    if achievement_id not in ACHIEVEMENT_DEFINITIONS:
        return "Отлично, Полина! 😏"
    
    achievement = ACHIEVEMENT_DEFINITIONS[achievement_id]
    motivation = achievement.get("motivation", "Хорошая работа, Полина!")
    
    # Add streak info if applicable
    if current_streak > 0 and achievement_id in ["focus_master", "mood_tracker"]:
        if current_streak == 7:
            motivation += f" Еще 7 дней до следующего уровня! 🔥"
        elif current_streak < 7:
            days_left = 7 - current_streak
            motivation += f" Еще {days_left} дн{'ей' if days_left != 1 else 'ь'} до Мастера! 💪"
    
    return motivation

def unlock_achievement(user_id: str, achievement_id: str) -> Tuple[bool, Optional[str], str]:
    """Unlock an achievement and generate card"""
    achievements = load_achievements()
    
    if achievement_id in achievements["unlocked"]:
        logger.info(f"Achievement {achievement_id} already unlocked for {user_id}")
        return False, None, "Это достижение уже разблокировано! 😏"
    
    # Generate card
    card_path = generate_achievement_card(achievement_id, user_id)
    
    achievements["unlocked"].append(achievement_id)
    achievements["progress"][achievement_id] = {
        "unlocked_at": datetime.now(TIMEZONE).isoformat(),
        "points": ACHIEVEMENT_DEFINITIONS.get(achievement_id, {}).get("points", 0),
        "card_path": card_path
    }
    
    save_achievements(achievements)
    
    motivation = get_motivation_message(achievement_id)
    logger.info(f"Achievement {achievement_id} unlocked for {user_id}")
    
    return True, card_path, motivation

def get_total_points(user_id: str) -> int:
    """Calculate total points from all achievements"""
    achievements = load_achievements()
    total_points = 0
    
    for achievement_id in achievements["unlocked"]:
        points = ACHIEVEMENT_DEFINITIONS.get(achievement_id, {}).get("points", 0)
        total_points += points
    
    return total_points

def get_achievements_summary(user_id: str) -> str:
    """Get a summary of all achievements"""
    achievements = load_achievements()
    streaks = load_streaks()
    
    total_points = get_total_points(user_id)
    unlocked_count = len(achievements["unlocked"])
    total_achievements = len(ACHIEVEMENT_DEFINITIONS)
    
    summary = f"""
╔═══════════════════════════╗
║ 🏆 ТВОИ ДОСТИЖЕНИЯ
╠═══════════════════════════╣
║ Разблокировано: {unlocked_count}/{total_achievements}
║ Всего очков: {total_points}
║ Стрик фокуса: {streaks.get("focus_streak", 0)} дней
║
║ Последние достижения:
"""
    
    for achievement_id in achievements["unlocked"][-3:]:
        achievement = ACHIEVEMENT_DEFINITIONS.get(achievement_id, {})
        summary += f"║ {achievement.get('emoji', '🎯')} {achievement.get('name', 'Unknown')}\n"
    
    summary += "╚═══════════════════════════╝"
    
    return summary

def get_streak_display(streaks: Dict[str, Any]) -> str:
    """Generate a visual display of current streaks"""
    focus_streak = streaks.get("focus_streak", 0)
    
    # Create a visual streak bar with stylish emojis
    filled = "🔥" * min(focus_streak, 14)
    empty = "⬜" * max(0, 7 - focus_streak)
    
    display = f"""
╔═══════════════════════════╗
║ ⚡️ СТРИК ФОКУСА
╠═══════════════════════════╣
║ {filled}{empty}
║ Дней подряд: {focus_streak}/7
║
║ Цель: 7 дней = 👏🏻 Боец недели
╚═══════════════════════════╝
"""
    return display

# --- Habit Streak Tracking --- #
def update_habit_streak(habit_name: str, completed: bool) -> Dict[str, Any]:
    """Update streak for a specific habit"""
    streaks = load_streaks()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    
    if habit_name not in streaks["habit_streaks"]:
        streaks["habit_streaks"][habit_name] = {
            "current_streak": 0,
            "best_streak": 0,
            "last_completed": None
        }
    
    habit = streaks["habit_streaks"][habit_name]
    
    if completed:
        yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        
        if habit["last_completed"] == today:
            pass
        elif habit["last_completed"] == yesterday:
            habit["current_streak"] += 1
        else:
            habit["current_streak"] = 1
        
        habit["last_completed"] = today
        
        if habit["current_streak"] > habit["best_streak"]:
            habit["best_streak"] = habit["current_streak"]
    else:
        if habit["last_completed"] != today:
            habit["current_streak"] = 0
    
    save_streaks(streaks)
    return habit

def get_habit_streaks_display() -> str:
    """Get visual display of all habit streaks"""
    streaks = load_streaks()
    
    if not streaks["habit_streaks"]:
        return "Нет отслеживаемых привычек. Давай начнем! 🚀"
    
    display = "╔═══════════════════════════╗\n"
    display += "║ 📋 ПРИВЫЧКИ\n"
    display += "╠═══════════════════════════╣\n"
    
    for habit_name, habit_data in streaks["habit_streaks"].items():
        current = habit_data["current_streak"]
        best = habit_data["best_streak"]
        
        filled = "🔥" * min(current, 7)
        empty = "⬜" * max(0, 7 - current)
        
        display += f"║ {habit_name}\n"
        display += f"║ {filled}{empty} {current} дн.\n"
        display += f"║ Лучший: {best} дн.\n"
        display += "║\n"
    
    display += "╚═══════════════════════════╝"
    
    return display
