"""
notion_manager.py — все операции с Notion + умная подгрузка в кэш
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pytz
from notion_client import Client

from config import NOTION_TOKEN, NOTION_DATABASES, TIMEZONE
from cache import set_cache, get_cache

logger = logging.getLogger(__name__)


class NotionManager:
    def __init__(self):
        self.client = Client(auth=NOTION_TOKEN)
        self.db = NOTION_DATABASES

    # ───────────────────────────────────────────
    # HELPERS
    # ───────────────────────────────────────────

    def _title(self, page: dict, field: str = "Название") -> str:
        try:
            return page["properties"][field]["title"][0]["text"]["content"]
        except (KeyError, IndexError):
            return ""

    def _text(self, page: dict, field: str) -> str:
        try:
            return page["properties"][field]["rich_text"][0]["text"]["content"]
        except (KeyError, IndexError):
            return ""

    def _select(self, page: dict, field: str) -> str:
        try:
            return page["properties"][field]["select"]["name"]
        except (KeyError, TypeError):
            return ""

    def _date(self, page: dict, field: str = "Дата") -> str:
        try:
            return page["properties"][field]["date"]["start"]
        except (KeyError, TypeError):
            return ""

    def _number(self, page: dict, field: str) -> Optional[float]:
        try:
            return page["properties"][field]["number"]
        except (KeyError, TypeError):
            return None

    # ───────────────────────────────────────────
    # СОСТОЯНИЕ / НАСТРОЕНИЕ
    # ───────────────────────────────────────────

    def log_mood(
        self,
        score: int,
        phase: str = "Норма",
        energy: str = "Средняя",
        dreams: str = "",
        cycle_day: int = None
    ) -> Optional[str]:
        """Записывает запись состояния"""
        try:
            now = datetime.now(TIMEZONE)
            props = {
                "Запись": {"title": [{"text": {"content": f"Запись {now.strftime('%d.%m %H:%M')}"}}]},
                "Дата":   {"date": {"start": now.isoformat()}},
                "Настроение": {"number": score},
                "Фаза":   {"select": {"name": phase}},
                "Энергия": {"select": {"name": energy}},
            }
            if dreams:
                props["Сны"] = {"rich_text": [{"text": {"content": dreams}}]}
            if cycle_day is not None:
                props["День цикла"] = {"number": cycle_day}

            resp = self.client.pages.create(
                parent={"database_id": self.db["mood"]},
                properties=props
            )
            invalidate_and_refresh = ["recent_mood", "cycle_phase"]
            for key in invalidate_and_refresh:
                set_cache(key, None)  # сбросим чтобы перечитать
            logger.info(f"Mood logged: {score}/10")
            return resp["id"]
        except Exception as e:
            logger.error(f"log_mood error: {e}")
            return None

    def get_recent_mood(self, days: int = 3) -> List[Dict]:
        """Последние записи настроения — с кэшем"""
        cached = get_cache("recent_mood")
        if cached is not None:
            return cached

        try:
            resp = self.client.databases.query(
                database_id=self.db["mood"],
                filter={"property": "Дата", "date": {"past_week": {}}},
                sorts=[{"property": "Дата", "direction": "descending"}],
                page_size=7
            )
            moods = []
            for p in resp["results"]:
                moods.append({
                    "id":    p["id"],
                    "date":  self._date(p),
                    "score": self._number(p, "Настроение"),
                    "phase": self._select(p, "Фаза"),
                    "energy": self._select(p, "Энергия"),
                    "dreams": self._text(p, "Сны"),
                    "cycle_day": self._number(p, "День цикла"),
                })
            set_cache("recent_mood", moods)
            return moods
        except Exception as e:
            logger.error(f"get_recent_mood error: {e}")
            return []

    def get_cyclothymia_phase(self) -> str:
        """Определяет текущую фазу циклотимии по последним записям"""
        moods = self.get_recent_mood(days=3)
        if not moods:
            return "Норма"
        scores = [m["score"] for m in moods if m["score"] is not None]
        if not scores:
            return "Норма"
        avg = sum(scores) / len(scores)
        if avg >= 7:
            return "Подъём"
        elif avg <= 3:
            return "Спад"
        return "Норма"

    def get_cycle_phase(self) -> Dict:
        """Фаза менструального цикла из последней записи"""
        cached = get_cache("cycle_phase")
        if cached is not None:
            return cached

        moods = self.get_recent_mood()
        result = {"phase": "", "day": None}
        for m in moods:
            if m.get("cycle_day"):
                day = m["cycle_day"]
                if day and day >= 1:
                    if day <= 5:
                        phase = "Менструация"
                    elif day <= 13:
                        phase = "Фолликулярная"
                    elif day <= 16:
                        phase = "Овуляция"
                    elif day <= 28:
                        phase = "Лютеиновая / ПМС" if day >= 22 else "Лютеиновая"
                    else:
                        phase = "Неизвестно"
                    result = {"phase": phase, "day": day}
                    break

        set_cache("cycle_phase", result)
        return result

    # ───────────────────────────────────────────
    # СОБЫТИЯ И ПРОЕКТЫ
    # ───────────────────────────────────────────

    def get_today_events(self) -> List[Dict]:
        """События на сегодня — с кэшем"""
        cached = get_cache("today_events")
        if cached is not None:
            return cached

        try:
            today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            resp = self.client.databases.query(
                database_id=self.db["events"],
                filter={"property": "Дата", "date": {"equals": today}},
                sorts=[{"property": "Дата", "direction": "ascending"}]
            )
            events = []
            for p in resp["results"]:
                events.append({
                    "id":       p["id"],
                    "name":     self._title(p),
                    "date":     self._date(p),
                    "status":   self._select(p, "Статус"),
                    "category": self._select(p, "Категория"),
                    "energy":   self._select(p, "Энергозатратность"),
                    "plan_time": self._number(p, "План времени"),
                })
            set_cache("today_events", events)
            return events
        except Exception as e:
            logger.error(f"get_today_events error: {e}")
            return []

    def get_upcoming_events(self, days_ahead: int = 3) -> List[Dict]:
        """Ближайшие события"""
        cached = get_cache("upcoming_events")
        if cached is not None:
            return cached

        try:
            now = datetime.now(TIMEZONE)
            until = (now + timedelta(days=days_ahead)).isoformat()
            resp = self.client.databases.query(
                database_id=self.db["events"],
                filter={
                    "and": [
                        {"property": "Дата", "date": {"on_or_after": now.isoformat()}},
                        {"property": "Дата", "date": {"before": until}},
                    ]
                },
                sorts=[{"property": "Дата", "direction": "ascending"}]
            )
            events = [{"id": p["id"], "name": self._title(p), "date": self._date(p)} for p in resp["results"]]
            set_cache("upcoming_events", events)
            return events
        except Exception as e:
            logger.error(f"get_upcoming_events error: {e}")
            return []

    def add_event(self, name: str, date: str, category: str = "", plan_time: int = None) -> Optional[str]:
        """Добавляет событие / задачу"""
        try:
            props = {
                "Название": {"title": [{"text": {"content": name}}]},
                "Дата": {"date": {"start": date}},
                "Статус": {"status": {"name": "Планирование"}},
            }
            if category:
                props["Категория"] = {"select": {"name": category}}
            if plan_time:
                props["План времени"] = {"number": plan_time}

            resp = self.client.pages.create(
                parent={"database_id": self.db["events"]},
                properties=props
            )
            set_cache("today_events", None)
            return resp["id"]
        except Exception as e:
            logger.error(f"add_event error: {e}")
            return None

    # ───────────────────────────────────────────
    # ЦЕЛИ
    # ───────────────────────────────────────────

    def get_active_goals(self) -> List[Dict]:
        cached = get_cache("active_goals")
        if cached is not None:
            return cached

        try:
            resp = self.client.databases.query(
                database_id=self.db["goals"],
                filter={"property": "Статус цели", "status": {"does_not_equal": "Выполнено"}},
                page_size=10
            )
            goals = []
            for p in resp["results"]:
                goals.append({
                    "id":       p["id"],
                    "name":     self._title(p, "Цель"),
                    "priority": self._select(p, "Приоритет"),
                    "deadline": self._date(p, "Дедлайн"),
                    "status":   self._select(p, "Статус цели"),
                })
            set_cache("active_goals", goals)
            return goals
        except Exception as e:
            logger.error(f"get_active_goals error: {e}")
            return []

    # ───────────────────────────────────────────
    # ПРИВЫЧКИ
    # ───────────────────────────────────────────

    def get_habits(self) -> List[Dict]:
        cached = get_cache("habits")
        if cached is not None:
            return cached

        try:
            resp = self.client.databases.query(
                database_id=self.db["habits"],
                page_size=20
            )
            today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            habits = []
            for p in resp["results"]:
                last_done = self._date(p, "Последний раз")
                habits.append({
                    "id":          p["id"],
                    "name":        self._title(p, "Привычка"),
                    "frequency":   self._select(p, "Частота"),
                    "energy":      self._select(p, "Уровень энергии"),
                    "last_done":   last_done,
                    "done_today":  last_done.startswith(today) if last_done else False,
                })
            set_cache("habits", habits)
            return habits
        except Exception as e:
            logger.error(f"get_habits error: {e}")
            return []

    def add_habit(self, name: str, frequency: str = "Ежедневно", energy: str = "Средняя") -> Optional[str]:
        try:
            resp = self.client.pages.create(
                parent={"database_id": self.db["habits"]},
                properties={
                    "Привычка": {"title": [{"text": {"content": name}}]},
                    "Частота":  {"select": {"name": frequency}},
                    "Уровень энергии": {"select": {"name": energy}},
                }
            )
            set_cache("habits", None)
            return resp["id"]
        except Exception as e:
            logger.error(f"add_habit error: {e}")
            return None

    def mark_habit_done(self, habit_id: str) -> bool:
        """Отмечает привычку выполненной (обновляет Последний раз)"""
        try:
            today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            self.client.pages.update(
                page_id=habit_id,
                properties={"Последний раз": {"date": {"start": today}}}
            )
            set_cache("habits", None)
            return True
        except Exception as e:
            logger.error(f"mark_habit_done error: {e}")
            return False

    # ───────────────────────────────────────────
    # ПАТТЕРНЫ
    # ───────────────────────────────────────────

    def get_patterns(self) -> List[Dict]:
        cached = get_cache("patterns")
        if cached is not None:
            return cached

        try:
            resp = self.client.databases.query(
                database_id=self.db["patterns"],
                page_size=20
            )
            patterns = []
            for p in resp["results"]:
                patterns.append({
                    "id":      p["id"],
                    "name":    self._title(p, "Название паттерна"),
                    "trigger": self._text(p, "Триггер"),
                    "signals": self._text(p, "Сигналы"),
                })
            set_cache("patterns", patterns)
            return patterns
        except Exception as e:
            logger.error(f"get_patterns error: {e}")
            return []

    def add_pattern(self, name: str, trigger: str = "", signals: str = "") -> Optional[str]:
        try:
            resp = self.client.pages.create(
                parent={"database_id": self.db["patterns"]},
                properties={
                    "Название паттерна": {"title": [{"text": {"content": name}}]},
                    "Триггер": {"rich_text": [{"text": {"content": trigger}}]},
                    "Сигналы": {"rich_text": [{"text": {"content": signals}}]},
                }
            )
            set_cache("patterns", None)
            return resp["id"]
        except Exception as e:
            logger.error(f"add_pattern error: {e}")
            return None

    # ───────────────────────────────────────────
    # ИДЕИ И ИМПУЛЬСЫ
    # ───────────────────────────────────────────

    def add_impulse(self, idea: str, context: str = "") -> Optional[str]:
        """Добавляет идею на 48ч фильтр"""
        try:
            resp = self.client.pages.create(
                parent={"database_id": self.db["ideas"]},
                properties={
                    "Идея":    {"title": [{"text": {"content": idea}}]},
                    "Статус":  {"select": {"name": "На проверке (48ч)"}},
                    "Контекст": {"rich_text": [{"text": {"content": context}}]},
                }
            )
            logger.info(f"Impulse added: {idea}")
            return resp["id"]
        except Exception as e:
            logger.error(f"add_impulse error: {e}")
            return None

    def get_pending_impulses(self) -> List[Dict]:
        try:
            resp = self.client.databases.query(
                database_id=self.db["ideas"],
                filter={"property": "Статус", "select": {"equals": "На проверке (48ч)"}},
            )
            return [
                {"id": p["id"], "idea": self._title(p, "Идея"), "context": self._text(p, "Контекст")}
                for p in resp["results"]
            ]
        except Exception as e:
            logger.error(f"get_pending_impulses error: {e}")
            return []

    # ───────────────────────────────────────────
    # АРХИВ ЗНАНИЙ
    # ───────────────────────────────────────────

    def add_to_archive(self, title: str, content: str, tags: List[str] = None) -> Optional[str]:
        try:
            props = {
                "Название": {"title": [{"text": {"content": title}}]},
                "Ссылка/контент": {"rich_text": [{"text": {"content": content}}]},
            }
            if tags:
                props["Теги"] = {"multi_select": [{"name": t} for t in tags]}
            resp = self.client.pages.create(
                parent={"database_id": self.db["archive"]},
                properties=props
            )
            return resp["id"]
        except Exception as e:
            logger.error(f"add_to_archive error: {e}")
            return None

    def search_archive(self, query: str) -> List[Dict]:
        try:
            resp = self.client.databases.query(
                database_id=self.db["archive"],
                filter={"or": [
                    {"property": "Название", "rich_text": {"contains": query}},
                    {"property": "Ссылка/контент", "rich_text": {"contains": query}},
                ]}
            )
            return [
                {"id": p["id"], "title": self._title(p), "content": self._text(p, "Ссылка/контент")}
                for p in resp["results"]
            ]
        except Exception as e:
            logger.error(f"search_archive error: {e}")
            return []

    def get_random_task_from_archive(self, tags: List[str] = None) -> Optional[Dict]:
        """Достаёт случайное задание из архива (для банка заданий)"""
        try:
            filter_obj = {"property": "Теги", "multi_select": {"contains": "задание"}}
            if tags:
                filter_obj = {"or": [
                    {"property": "Теги", "multi_select": {"contains": t}} for t in tags
                ]}
            resp = self.client.databases.query(
                database_id=self.db["archive"],
                filter=filter_obj,
                page_size=50
            )
            if not resp["results"]:
                return None
            page = random.choice(resp["results"])
            return {"title": self._title(page), "content": self._text(page, "Ссылка/контент")}
        except Exception as e:
            logger.error(f"get_random_task_from_archive error: {e}")
            return None

    # ───────────────────────────────────────────
    # ЛЮДИ
    # ───────────────────────────────────────────

    def get_close_contacts(self) -> List[Dict]:
        try:
            resp = self.client.databases.query(
                database_id=self.db["people"],
                page_size=50
            )
            contacts = []
            for p in resp["results"]:
                role = self._select(p, "Роль")
                if role in ("Близкие", "SOS-контакт"):
                    contacts.append({
                        "id":   p["id"],
                        "name": self._title(p, "Имя"),
                        "role": role,
                        "context": self._text(p, "Контекст"),
                    })
            return contacts
        except Exception as e:
            logger.error(f"get_close_contacts error: {e}")
            return []

    def get_random_contact(self) -> Optional[Dict]:
        contacts = self.get_close_contacts()
        return random.choice(contacts) if contacts else None

    # ───────────────────────────────────────────
    # ПОЛНЫЙ КОНТЕКСТ ДЛЯ БРИФИНГА
    # ───────────────────────────────────────────

    def refresh_all_caches(self):
        """
        Обновляет все кэши разом.
        Вызывается раз в 15 минут через планировщик.
        """
        self.get_recent_mood()
        self.get_cycle_phase()
        self.get_today_events()
        self.get_upcoming_events()
        self.get_active_goals()
        self.get_habits()
        self.get_patterns()
        logger.info("All Notion caches refreshed")

    def get_briefing_context(self) -> str:
        """
        Собирает компактный текстовый контекст для утреннего брифинга.
        Передаётся в ask_alex как extra_instruction.
        """
        lines = ["Данные для утреннего брифинга:"]

        events = self.get_today_events()
        if events:
            lines.append(f"События сегодня: {', '.join(e['name'] for e in events)}")
        else:
            lines.append("События сегодня: нет")

        goals = self.get_active_goals()
        if goals:
            top = [g["name"] for g in goals if g["priority"] == "Высокий"][:2]
            other = [g["name"] for g in goals if g["priority"] != "Высокий"][:2]
            if top:
                lines.append(f"Приоритетные цели: {', '.join(top)}")
            if other:
                lines.append(f"Другие цели: {', '.join(other)}")

        habits = self.get_habits()
        pending = [h["name"] for h in habits if not h["done_today"]]
        if pending:
            lines.append(f"Привычки на сегодня: {', '.join(pending[:4])}")

        impulses = self.get_pending_impulses()
        if impulses:
            lines.append(f"Идеи на проверке (48ч): {len(impulses)} шт")

        patterns = self.get_patterns()
        if patterns:
            lines.append(f"Паттерны: {'; '.join(p['name'] for p in patterns[:2])}")

        lines.append("\nСделай утренний брифинг: выбери режим дня, предложи с чего начать и почему.")
        return "\n".join(lines)


# Глобальный экземпляр — импортируем везде
notion = NotionManager()
