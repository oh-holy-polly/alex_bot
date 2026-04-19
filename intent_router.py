"""
intent_router.py — гибкий роутинг сообщений через Groq tool use.

Определяет что Полина хочет сделать и выполняет нужные действия в Notion.
Не заменяет alex.py — работает параллельно с ним.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from groq import Groq
from config import GROQ_API_KEY, MODEL_FAST, MODEL_SMART, TIMEZONE
from notion_manager import notion

logger = logging.getLogger(__name__)
groq_client = Groq(api_key=GROQ_API_KEY)

# ───────────────────────────────────────────
# ИНСТРУМЕНТЫ (то что модель может вызвать)
# ───────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Создать новое событие или задачу в Notion. Используй когда Полина говорит что надо что-то сделать, куда-то сходить, с кем-то встретиться.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Название события или задачи"
                    },
                    "date": {
                        "type": "string",
                        "description": "Дата в формате YYYY-MM-DD. Если не указана — не передавай это поле."
                    },
                    "time": {
                        "type": "string",
                        "description": "Время в формате HH:MM. Если не указано — не передавай это поле."
                    },
                    "category": {
                        "type": "string",
                        "description": "Категория события. Одно из: Работа, Здоровье, Личное, Учёба, Социальное. Угадай по контексту."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": "Изменить существующее событие — дату, время или статус. Используй когда Полина говорит 'перенеси', 'измени', 'сдвинь', 'отмени'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {
                        "type": "string",
                        "description": "Название события которое ищем — как Полина его назвала"
                    },
                    "new_date": {
                        "type": "string",
                        "description": "Новая дата YYYY-MM-DD если меняется"
                    },
                    "new_time": {
                        "type": "string",
                        "description": "Новое время HH:MM если меняется"
                    },
                    "new_status": {
                        "type": "string",
                        "description": "Новый статус если меняется. Одно из: Планирование, В процессе, Выполнено, Отменено"
                    }
                },
                "required": ["search_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Удалить событие или задачу. Используй когда Полина говорит 'удали', 'убери', 'не нужно'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {
                        "type": "string",
                        "description": "Название события которое ищем"
                    }
                },
                "required": ["search_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_habit",
            "description": "Добавить новую привычку. Используй когда Полина говорит что хочет начать что-то делать регулярно.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Название привычки"
                    },
                    "frequency": {
                        "type": "string",
                        "description": "Частота. Одно из: Ежедневно, Несколько раз в неделю, Еженедельно. Угадай по контексту, по умолчанию Ежедневно."
                    },
                    "energy": {
                        "type": "string",
                        "description": "Уровень энергии. Одно из: Низкая, Средняя, Высокая. Угадай по контексту, по умолчанию Средняя."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_archive",
            "description": "Сохранить что-то в архив знаний — фильм, рецепт, упражнение, заметку, ссылку, любой контент для хранения.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Название или заголовок"
                    },
                    "content": {
                        "type": "string",
                        "description": "Содержимое, ссылка или описание"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Теги для категоризации. Например: фильм, рецепт, упражнение, заметка, ссылка, книга"
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_idea",
            "description": "Сохранить идею или импульс на 48-часовой фильтр. Используй когда Полина говорит об идее, хочет что-то попробовать, что-то её вдохновило.",
            "parameters": {
                "type": "object",
                "properties": {
                    "idea": {
                        "type": "string",
                        "description": "Суть идеи"
                    },
                    "context": {
                        "type": "string",
                        "description": "Контекст или детали если есть"
                    }
                },
                "required": ["idea"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "just_chat",
            "description": "Просто разговор с Алексом — никаких действий в Notion не нужно.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

# ───────────────────────────────────────────
# КЛАССИФИКАТОР ИНТЕНТОВ
# ───────────────────────────────────────────

def classify_intent(user_message: str) -> list[dict]:
    """
    Определяет что Полина хочет сделать.
    Возвращает список вызовов инструментов (может быть несколько).
    Если ничего — возвращает [{"name": "just_chat"}].
    """
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    day_of_week = datetime.now(TIMEZONE).strftime("%A")

    system = f"""Ты определяешь намерения в сообщениях Полины.
Сегодня: {today} ({day_of_week}).

Правила:
- Если в сообщении есть задача/событие/встреча (даже если указано время, например "в 19:00 в ресторан") — вызови create_event.
- Если Полина хочет изменить или перенести что-то существующее — вызови update_event.
- Если хочет удалить — вызови delete_event.
- Если хочет начать что-то делать регулярно — вызови add_habit.
- Если хочет сохранить фильм/рецепт/ссылку/заметку/упражнение — вызови save_to_archive.
- Если делится идеей или импульсом — вызови save_idea.
- Если это просто разговор — вызови just_chat.
- ВАЖНО: Если Полина называет время в будущем (вечернее время, обед и т.д.) — это СОБЫТИЕ (create_event), а не время подъёма на завтра.
- Можно вызвать несколько инструментов одновременно если сообщение содержит несколько намерений.
- "сегодня" = {today}, "завтра" = следующий день, "в пятницу" = ближайшая пятница и т.д.
- Если дата/время не указаны явно — не выдумывай их.
"""

    try:
        response = groq_client.chat.completions.create(
            model=MODEL_FAST,  # FIX: 8b для классификации, экономим токены 70b
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message}
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=500
        )

        message = response.choices[0].message

        if not message.tool_calls:
            return [{"name": "just_chat"}]

        result = []
        for tool_call in message.tool_calls:
            result.append({
                "name": tool_call.function.name,
                "args": json.loads(tool_call.function.arguments)
            })

        return result

    except Exception as e:
        logger.error(f"classify_intent error: {e}")
        return [{"name": "just_chat"}]


# ───────────────────────────────────────────
# ВЫПОЛНЕНИЕ ДЕЙСТВИЙ
# ───────────────────────────────────────────

def execute_intents(intents: list[dict]) -> list[str]:
    """
    Выполняет список интентов, возвращает список строк-результатов
    которые потом передаются Алексу как контекст.
    """
    results = []

    for intent in intents:
        name = intent.get("name")
        args = intent.get("args", {})

        if name == "just_chat":
            continue

        elif name == "create_event":
            result = _do_create_event(args)
            results.append(result)

        elif name == "update_event":
            result = _do_update_event(args)
            results.append(result)

        elif name == "delete_event":
            result = _do_delete_event(args)
            results.append(result)

        elif name == "add_habit":
            result = _do_add_habit(args)
            results.append(result)

        elif name == "save_to_archive":
            result = _do_save_archive(args)
            results.append(result)

        elif name == "save_idea":
            result = _do_save_idea(args)
            results.append(result)

    return results


# ───────────────────────────────────────────
# КОНКРЕТНЫЕ ДЕЙСТВИЯ
# ───────────────────────────────────────────

def _do_create_event(args: dict) -> str:
    name = args.get("name", "")
    date = args.get("date")
    time = args.get("time")
    category = args.get("category", "")

    date_iso = None
    if date:
        if time:
            date_iso = f"{date}T{time}:00"
        else:
            date_iso = date

    try:
        notion.add_event(
            name=name,
            date=date_iso or datetime.now(TIMEZONE).strftime("%Y-%m-%d"),
            category=category
        )
        if date and time:
            return f"NOTION_ACTION: записала событие «{name}» на {date} в {time}"
        elif date:
            return f"NOTION_ACTION: записала событие «{name}» на {date}, время не указано"
        else:
            return f"NOTION_ACTION: записала задачу «{name}» без конкретной даты"
    except Exception as e:
        logger.error(f"create_event error: {e}")
        return f"NOTION_ERROR: не смогла записать «{name}»"


def _do_update_event(args: dict) -> str:
    search_name = args.get("search_name", "")

    try:
        resp = notion.client.databases.query(
            database_id=notion.db["events"],
            filter={
                "property": "Название",
                "title": {"contains": search_name}
            },
            page_size=5
        )
        pages = resp.get("results", [])
    except Exception as e:
        logger.error(f"update_event search error: {e}")
        return f"NOTION_ERROR: не смогла найти «{search_name}»"

    if not pages:
        return f"NOTION_CLARIFY: не нашла событие «{search_name}» — попроси Полину уточнить название"

    if len(pages) > 1:
        names = [notion._title(p) for p in pages]
        return f"NOTION_CLARIFY: нашла несколько похожих событий: {', '.join(names)} — спроси у Полины какое именно"

    page_id = pages[0]["id"]
    real_name = notion._title(pages[0])
    props = {}

    new_date = args.get("new_date")
    new_time = args.get("new_time")
    new_status = args.get("new_status")

    if new_date or new_time:
        if new_date and new_time:
            date_iso = f"{new_date}T{new_time}:00"
        elif new_date:
            date_iso = new_date
        else:
            existing = notion._date(pages[0])
            base_date = existing[:10] if existing else datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            date_iso = f"{base_date}T{new_time}:00"
        props["Дата"] = {"date": {"start": date_iso}}

    if new_status:
        props["Статус"] = {"status": {"name": new_status}}

    if not props:
        return f"NOTION_CLARIFY: нашла «{real_name}» но непонятно что именно изменить — спроси у Полины"

    try:
        notion.client.pages.update(page_id=page_id, properties=props)
        from cache import invalidate_cache
        invalidate_cache("today_events")
        return f"NOTION_ACTION: обновила «{real_name}»"
    except Exception as e:
        logger.error(f"update_event error: {e}")
        return f"NOTION_ERROR: не смогла обновить «{real_name}»"


def _do_delete_event(args: dict) -> str:
    search_name = args.get("search_name", "")

    try:
        resp = notion.client.databases.query(
            database_id=notion.db["events"],
            filter={
                "property": "Название",
                "title": {"contains": search_name}
            },
            page_size=5
        )
        pages = resp.get("results", [])
    except Exception as e:
        logger.error(f"delete_event search error: {e}")
        return f"NOTION_ERROR: не смогла найти «{search_name}»"

    if not pages:
        return f"NOTION_CLARIFY: не нашла событие «{search_name}» — попроси Полину уточнить название"

    if len(pages) > 1:
        names = [notion._title(p) for p in pages]
        return f"NOTION_CLARIFY: нашла несколько: {', '.join(names)} — спроси какое удалять"

    page_id = pages[0]["id"]
    real_name = notion._title(pages[0])

    try:
        notion.client.pages.update(page_id=page_id, archived=True)
        from cache import invalidate_cache
        invalidate_cache("today_events")
        return f"NOTION_ACTION: удалила «{real_name}»"
    except Exception as e:
        logger.error(f"delete_event error: {e}")
        return f"NOTION_ERROR: не смогла удалить «{real_name}»"


def _do_add_habit(args: dict) -> str:
    name = args.get("name", "")
    frequency = args.get("frequency", "Ежедневно")
    energy = args.get("energy", "Средняя")

    try:
        notion.add_habit(name=name, frequency=frequency, energy=energy)
        return f"NOTION_ACTION: добавила привычку «{name}» (частота: {frequency}, энергия: {energy})"
    except Exception as e:
        logger.error(f"add_habit error: {e}")
        return f"NOTION_ERROR: не смогла добавить привычку «{name}»"


def _do_save_archive(args: dict) -> str:
    title = args.get("title", "")
    content = args.get("content", "")
    tags = args.get("tags", [])

    try:
        notion.add_to_archive(title=title, content=content, tags=tags)
        tags_str = ", ".join(tags) if tags else "без тегов"
        return f"NOTION_ACTION: сохранила в архив «{title}» [{tags_str}]"
    except Exception as e:
        logger.error(f"save_archive error: {e}")
        return f"NOTION_ERROR: не смогла сохранить «{title}»"


def _do_save_idea(args: dict) -> str:
    idea = args.get("idea", "")
    context = args.get("context", "")

    try:
        notion.add_impulse(idea=idea, context=context)
        return f"NOTION_ACTION: сохранила идею «{idea}» на 48-часовой фильтр"
    except Exception as e:
        logger.error(f"save_idea error: {e}")
        return f"NOTION_ERROR: не смогла сохранить идею «{idea}»"


# ───────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ — вызывается из main.py
# ───────────────────────────────────────────

def route_message(user_message: str) -> tuple[bool, list[str]]:
    """
    Роутит сообщение: определяет интенты и выполняет действия.

    Возвращает:
        needs_clarification (bool) — нужно ли переспросить Полину
        action_results (list[str]) — результаты для передачи Алексу как контекст
    """
    intents = classify_intent(user_message)

    # Если только just_chat — ничего не делаем
    if all(i["name"] == "just_chat" for i in intents):
        return False, []

    results = execute_intents(intents)

    # Проверяем нужно ли уточнение
    needs_clarification = any("NOTION_CLARIFY" in r for r in results)

    return needs_clarification, results
