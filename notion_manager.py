"""
Notion Manager for Alex Bot v10.0
Handles all CRUD operations for 8 interconnected Notion databases
"""

import logging
from datetime import datetime
import pytz
from typing import Dict, List, Optional, Any
from notion_client import Client
import random

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Europe/Minsk")

# Database IDs
NOTION_DATABASES = {
    "people": "33aee470194180839d16c4391e9fe8e3",
    "events": "33bee47019418070bc97f6d0485b4a03",
    "mood": "33bee4701941809ea0f9da1e7d7d2abf",
    "ideas": "33bee47019418027a02fc75732722c18",
    "habits": "33bee4701941802a8716ecf293cb3ced",
    "archive": "33bee470194180bab3c7da6e50536fa6",
    "goals": "33bee4701941809380b9c4e8cbef8943",
    "patterns": "33bee4701941808683cac5052f283537",
}


class NotionManager:
    def __init__(self, notion_token: str):
        self.client = Client(auth=notion_token)
        self.databases = NOTION_DATABASES

    # ============ ЛЮДИ (People) ============
    def add_person(self, name: str, role: str = "", context: str = "") -> Optional[str]:
        """Add a new person to the People database"""
        try:
            response = self.client.pages.create(
                parent={"database_id": self.databases["people"]},
                properties={
                    "Имя": {"title": [{"text": {"content": name}}]},
                    "Роль": {"select": {"name": role}} if role else None,
                    "Контекст": {"rich_text": [{"text": {"content": context}}]} if context else None,
                }
            )
            logger.info(f"Added person: {name}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding person: {e}")
            return None

    def get_people(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent people from database"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["people"],
                sorts=[{"property": "Дата создания", "direction": "descending"}],
                page_size=limit
            )
            people = []
            for page in response["results"]:
                person = {
                    "id": page["id"],
                    "name": page["properties"].get("Имя", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "role": page["properties"].get("Роль", {}).get("select", {}).get("name", ""),
                    "context": page["properties"].get("Контекст", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                    "tags": [tag.get("name", "") for tag in page["properties"].get("Теги", {}).get("multi_select", [])],
                }
                people.append(person)
            return people
        except Exception as e:
            logger.error(f"Error getting people: {e}")
            return []
    
    def get_close_contacts(self) -> List[Dict[str, Any]]:
        """Get people tagged as 'Близкие' or 'SOS-контакт'"""
        try:
            all_people = self.get_people(limit=100)
            close_contacts = []
            
            for person in all_people:
                tags = person.get("tags", [])
                if "Близкие" in tags or "SOS-контакт" in tags:
                    close_contacts.append(person)
            
            return close_contacts
        except Exception as e:
            logger.error(f"Error getting close contacts: {e}")
            return []
    
    def get_random_contact(self) -> Optional[Dict[str, Any]]:
        """Get a random close contact for social nudge"""
        contacts = self.get_close_contacts()
        if contacts:
            return random.choice(contacts)
        return None

    # ============ СОБЫТИЯ И ПРОЕКТЫ (Events & Projects) ============
    def add_event(self, name: str, date: str, status: str = "Планирование", category: str = "", participants: List[str] = None) -> Optional[str]:
        """Add event/project to database"""
        try:
            properties = {
                "Название": {"title": [{"text": {"content": name}}]},
                "Дата": {"date": {"start": date}},
                "Статус": {"status": {"name": status}},
            }
            if category:
                properties["Категория"] = {"select": {"name": category}}
            
            response = self.client.pages.create(
                parent={"database_id": self.databases["events"]},
                properties=properties
            )
            logger.info(f"Added event: {name}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding event: {e}")
            return None

    def get_upcoming_events(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Get upcoming events"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["events"],
                filter={
                    "and": [
                        {
                            "property": "Дата",
                            "date": {
                                "on_or_after": datetime.now(TIMEZONE).isoformat()
                            }
                        },
                        {
                            "property": "Дата",
                            "date": {
                                "before": (datetime.now(TIMEZONE).timestamp() + days_ahead * 86400).__str__()
                            }
                        }
                    ]
                },
                sorts=[{"property": "Дата", "direction": "ascending"}]
            )
            events = []
            for page in response["results"]:
                event = {
                    "id": page["id"],
                    "name": page["properties"].get("Название", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "date": page["properties"].get("Дата", {}).get("date", {}).get("start", ""),
                    "status": page["properties"].get("Статус", {}).get("status", {}).get("name", ""),
                    "category": page["properties"].get("Категория", {}).get("select", {}).get("name", ""),
                }
                events.append(event)
            return events
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return []
    
    def check_busy_at_time(self, check_time: str = None) -> Optional[str]:
        """Check if user is busy at a specific time (returns event name if busy)"""
        try:
            # Get today's events
            today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            response = self.client.databases.query(
                database_id=self.databases["events"],
                filter={
                    "property": "Дата",
                    "date": {"equals": today}
                }
            )
            
            busy_keywords = ["кино", "встреча", "свидание", "концерт", "театр", "врач", "работа", "тренировка", "спортзал"]
            
            for page in response["results"]:
                event_name = page["properties"].get("Название", {}).get("title", [{}])[0].get("text", {}).get("content", "")
                if any(keyword in event_name.lower() for keyword in busy_keywords):
                    return event_name
            
            return None
        except Exception as e:
            logger.error(f"Error checking busy time: {e}")
            return None

    # ============ СОСТОЯНИЕ (Mood & Energy) ============
    def log_mood(self, mood_score: int, phase: str = "Норма", sleep_hours: float = 0, notes: str = "") -> Optional[str]:
        """Log mood entry"""
        try:
            now = datetime.now(TIMEZONE)
            response = self.client.pages.create(
                parent={"database_id": self.databases["mood"]},
                properties={
                    "Запись": {"title": [{"text": {"content": f"Запись {now.strftime('%d.%m %H:%M')}"}}]},
                    "Дата": {"date": {"start": now.isoformat()}},
                    "Настроение": {"number": mood_score},
                    "Фаза": {"select": {"name": phase}},
                    "Сны": {"rich_text": [{"text": {"content": notes}}]} if notes else None,
                }
            )
            logger.info(f"Logged mood: {mood_score}/10, phase: {phase}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error logging mood: {e}")
            return None

    def get_recent_moods(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get mood entries from last N days"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["mood"],
                filter={
                    "property": "Дата",
                    "date": {
                        "past_week": {}
                    }
                },
                sorts=[{"property": "Дата", "direction": "descending"}]
            )
            moods = []
            for page in response["results"]:
                mood = {
                    "id": page["id"],
                    "date": page["properties"].get("Дата", {}).get("date", {}).get("start", ""),
                    "score": page["properties"].get("Настроение", {}).get("number", 0),
                    "phase": page["properties"].get("Фаза", {}).get("select", {}).get("name", ""),
                    "notes": page["properties"].get("Сны", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                }
                moods.append(mood)
            return moods
        except Exception as e:
            logger.error(f"Error getting moods: {e}")
            return []

    # ============ ИДЕИ И ИМПУЛЬСЫ (Ideas & Impulses) ============
    def add_impulse_decision(self, idea: str, context: str = "") -> Optional[str]:
        """Add impulse decision for 48-hour filter"""
        try:
            response = self.client.pages.create(
                parent={"database_id": self.databases["ideas"]},
                properties={
                    "Идея": {"title": [{"text": {"content": idea}}]},
                    "Статус": {"select": {"name": "На проверке (48ч)"}},
                    "Контекст": {"rich_text": [{"text": {"content": context}}]} if context else None,
                }
            )
            logger.info(f"Added impulse decision: {idea}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding impulse: {e}")
            return None

    def get_pending_impulses(self) -> List[Dict[str, Any]]:
        """Get ideas pending 48-hour review"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["ideas"],
                filter={
                    "property": "Статус",
                    "select": {"equals": "На проверке (48ч)"}
                }
            )
            impulses = []
            for page in response["results"]:
                impulse = {
                    "id": page["id"],
                    "idea": page["properties"].get("Идея", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "context": page["properties"].get("Контекст", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                }
                impulses.append(impulse)
            return impulses
        except Exception as e:
            logger.error(f"Error getting impulses: {e}")
            return []

    # ============ ПРИВЫЧКИ (Habits) ============
    def add_habit(self, habit_name: str, frequency: str = "Ежедневно", energy_level: str = "Средняя") -> Optional[str]:
        """Add new habit"""
        try:
            response = self.client.pages.create(
                parent={"database_id": self.databases["habits"]},
                properties={
                    "Привычка": {"title": [{"text": {"content": habit_name}}]},
                    "Частота": {"select": {"name": frequency}},
                    "Уровень энергии": {"select": {"name": energy_level}},
                }
            )
            logger.info(f"Added habit: {habit_name}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding habit: {e}")
            return None

    def get_habits(self) -> List[Dict[str, Any]]:
        """Get all habits"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["habits"],
                page_size=50
            )
            habits = []
            for page in response["results"]:
                habit = {
                    "id": page["id"],
                    "name": page["properties"].get("Привычка", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "frequency": page["properties"].get("Частота", {}).get("select", {}).get("name", ""),
                    "energy_level": page["properties"].get("Уровень энергии", {}).get("select", {}).get("name", ""),
                    "last_done": page["properties"].get("Последний раз", {}).get("date", {}).get("start", ""),
                }
                habits.append(habit)
            return habits
        except Exception as e:
            logger.error(f"Error getting habits: {e}")
            return []

    # ============ АРХИВ ЗНАНИЙ (Knowledge Archive) ============
    def add_to_archive(self, title: str, content: str, tags: List[str] = None) -> Optional[str]:
        """Add item to knowledge archive"""
        try:
            properties = {
                "Название": {"title": [{"text": {"content": title}}]},
                "Ссылка/контент": {"rich_text": [{"text": {"content": content}}]},
            }
            if tags:
                properties["Теги"] = {"multi_select": [{"name": tag} for tag in tags]}
            
            response = self.client.pages.create(
                parent={"database_id": self.databases["archive"]},
                properties=properties
            )
            logger.info(f"Added to archive: {title}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding to archive: {e}")
            return None

    def search_archive(self, query: str) -> List[Dict[str, Any]]:
        """Search knowledge archive"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["archive"],
                filter={
                    "or": [
                        {
                            "property": "Название",
                            "rich_text": {"contains": query}
                        },
                        {
                            "property": "Ссылка/контент",
                            "rich_text": {"contains": query}
                        }
                    ]
                }
            )
            results = []
            for page in response["results"]:
                result = {
                    "id": page["id"],
                    "title": page["properties"].get("Название", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "content": page["properties"].get("Ссылка/контент", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                }
                results.append(result)
            return results
        except Exception as e:
            logger.error(f"Error searching archive: {e}")
            return []

    # ============ ЦЕЛИ (Goals) ============
    def add_goal(self, goal_name: str, priority: str = "Средний", deadline: str = "") -> Optional[str]:
        """Add new goal"""
        try:
            properties = {
                "Цель": {"title": [{"text": {"content": goal_name}}]},
                "Приоритет": {"select": {"name": priority}},
            }
            if deadline:
                properties["Дедлайн"] = {"date": {"start": deadline}}
            
            response = self.client.pages.create(
                parent={"database_id": self.databases["goals"]},
                properties=properties
            )
            logger.info(f"Added goal: {goal_name}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding goal: {e}")
            return None

    def get_active_goals(self) -> List[Dict[str, Any]]:
        """Get active goals"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["goals"],
                page_size=50
            )
            goals = []
            for page in response["results"]:
                goal = {
                    "id": page["id"],
                    "name": page["properties"].get("Цель", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "priority": page["properties"].get("Приоритет", {}).get("select", {}).get("name", ""),
                    "deadline": page["properties"].get("Дедлайн", {}).get("date", {}).get("start", ""),
                }
                goals.append(goal)
            return goals
        except Exception as e:
            logger.error(f"Error getting goals: {e}")
            return []

    # ============ ПАТТЕРНЫ (Patterns) ============
    def add_pattern(self, pattern_name: str, trigger: str = "", counter_action: str = "") -> Optional[str]:
        """Add behavioral pattern"""
        try:
            response = self.client.pages.create(
                parent={"database_id": self.databases["patterns"]},
                properties={
                    "Название паттерна": {"title": [{"text": {"content": pattern_name}}]},
                    "Триггер": {"rich_text": [{"text": {"content": trigger}}]} if trigger else None,
                    "Контр-действие": {"rich_text": [{"text": {"content": counter_action}}]} if counter_action else None,
                }
            )
            logger.info(f"Added pattern: {pattern_name}")
            return response["id"]
        except Exception as e:
            logger.error(f"Error adding pattern: {e}")
            return None

    def get_patterns(self) -> List[Dict[str, Any]]:
        """Get all patterns"""
        try:
            response = self.client.databases.query(
                database_id=self.databases["patterns"],
                page_size=50
            )
            patterns = []
            for page in response["results"]:
                pattern = {
                    "id": page["id"],
                    "name": page["properties"].get("Название паттерна", {}).get("title", [{}])[0].get("text", {}).get("content", ""),
                    "trigger": page["properties"].get("Триггер", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                    "counter_action": page["properties"].get("Контр-действие", {}).get("rich_text", [{}])[0].get("text", {}).get("content", ""),
                }
                patterns.append(pattern)
            return patterns
        except Exception as e:
            logger.error(f"Error getting patterns: {e}")
            return []

    # ============ CONTEXT RETRIEVAL (RAG-like) ============
    def get_full_context(self, query: str = "") -> Dict[str, Any]:
        """Get comprehensive context for AI analysis"""
        context = {
            "recent_moods": self.get_recent_moods(7),
            "upcoming_events": self.get_upcoming_events(7),
            "active_goals": self.get_active_goals(),
            "habits": self.get_habits(),
            "patterns": self.get_patterns(),
            "people": self.get_people(5),
            "pending_impulses": self.get_pending_impulses(),
        }
        
        if query:
            context["archive_search"] = self.search_archive(query)
        
        return context

    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """Format context data into a readable prompt for Groq"""
        prompt_parts = []
        
        if context.get("recent_moods"):
            moods_text = "**Недавнее настроение:**\n"
            for mood in context["recent_moods"][:3]:
                moods_text += f"- {mood["date"]}: {mood["score"]}/10 (Фаза: {mood["phase"]})\n"
            prompt_parts.append(moods_text)
        
        if context.get("upcoming_events"):
            events_text = "**Предстоящие события:**\n"
            for event in context["upcoming_events"][:3]:
                events_text += f"- {event['name']} ({event['date']}, статус: {event['status']})\n"
            prompt_parts.append(events_text)
        
        if context.get("active_goals"):
            goals_text = "**Активные цели:**\n"
            for goal in context["active_goals"][:3]:
                goals_text += f"- {goal['name']} (приоритет: {goal['priority']})\n"
            prompt_parts.append(goals_text)
        
        if context.get("patterns"):
            patterns_text = "**Известные паттерны:**\n"
            for pattern in context["patterns"][:2]:
                patterns_text += f"- {pattern['name']}: {pattern['trigger']} → {pattern['counter_action']}\n"
            prompt_parts.append(patterns_text)
        
        return "\n".join(prompt_parts)
