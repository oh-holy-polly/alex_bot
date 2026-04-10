import os
from notion_client import Client
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotionManager:
    def __init__(self):
        self.notion = Client(auth=os.getenv("NOTION_TOKEN"))
        self.db_ids = {
            "people": os.getenv("NOTION_DATABASE_ID_PEOPLE"),
            "events_projects": os.getenv("NOTION_DATABASE_ID_EVENTS_PROJECTS"),
            "state": os.getenv("NOTION_DATABASE_ID_STATE"),
            "ideas_impulses": os.getenv("NOTION_DATABASE_ID_IDEAS_IMPULSES"),
            "habits": os.getenv("NOTION_DATABASE_ID_HABITS"),
            "knowledge_archive": os.getenv("NOTION_DATABASE_ID_KNOWLEDGE_ARCHIVE"),
            "goals": os.getenv("NOTION_DATABASE_ID_GOALS"),
            "patterns": os.getenv("NOTION_DATABASE_ID_PATTERNS"),
            "interventions": os.getenv("NOTION_DATABASE_ID_INTERVENTIONS"),
        }

    def _get_db_properties(self, db_id):
        try:
            response = self.notion.databases.retrieve(database_id=db_id)
            properties = {}
            for prop_name, prop_data in response["properties"].items():
                properties[prop_name] = {"id": prop_data["id"], "type": prop_data["type"]}
                if prop_data["type"] == "relation":
                    properties[prop_name]["relation_db_id"] = prop_data["relation"]["database_id"]
            return properties
        except Exception as e:
            logger.error(f"Error retrieving database properties for {db_id}: {e}")
            return None

    def _get_page_property(self, page_id, property_id, property_type):
        try:
            response = self.notion.pages.properties.retrieve(page_id=page_id, property_id=property_id)
            if property_type == "title":
                return response["results"][0]["title"]["plain_text"] if response["results"] else ""
            elif property_type == "rich_text":
                return response["results"][0]["rich_text"]["plain_text"] if response["results"] else ""
            elif property_type == "number":
                return response["number"]
            elif property_type == "select":
                return response["select"]["name"] if response["select"] else ""
            elif property_type == "multi_select":
                return [item["name"] for item in response["multi_select"]] if response["multi_select"] else []
            elif property_type == "date":
                return response["date"]["start"] if response["date"] else ""
            elif property_type == "relation":
                return [item["id"] for item in response["results"]] if response["results"] else []
            elif property_type == "status":
                return response["status"]["name"] if response["status"] else ""
            return str(response)
        except Exception as e:
            logger.error(f"Error getting page property {property_id} for page {page_id}: {e}")
            return None

    def get_full_context(self):
        context = {}
        for db_name, db_id in self.db_ids.items():
            if not db_id: continue
            try:
                response = self.notion.databases.query(database_id=db_id, page_size=5) # Limit to 5 recent entries for context
                items = []
                for page in response["results"]:
                    item_data = {"id": page["id"]}
                    for prop_name, prop_value in page["properties"].items():
                        item_data[prop_name] = self._parse_property_value(prop_value)
                    items.append(item_data)
                context[db_name] = items
            except Exception as e:
                logger.error(f"Error querying database {db_name} ({db_id}): {e}")
        return context

    def _parse_property_value(self, prop_value):
        prop_type = prop_value["type"]
        if prop_type == "title":
            return prop_value["title"][0]["plain_text"] if prop_value["title"] else ""
        elif prop_type == "rich_text":
            return prop_value["rich_text"][0]["plain_text"] if prop_value["rich_text"] else ""
        elif prop_type == "number":
            return prop_value["number"]
        elif prop_type == "select":
            return prop_value["select"]["name"] if prop_value["select"] else ""
        elif prop_type == "multi_select":
            return [item["name"] for item in prop_value["multi_select"]] if prop_value["multi_select"] else []
        elif prop_type == "date":
            return prop_value["date"]["start"] if prop_value["date"] else ""
        elif prop_type == "relation":
            return [item["id"] for item in prop_value["relation"]] if prop_value["relation"] else []
        elif prop_type == "status":
            return prop_value["status"]["name"] if prop_value["status"] else ""
        elif prop_type == "checkbox":
            return prop_value["checkbox"]
        elif prop_type == "url":
            return prop_value["url"]
        elif prop_type == "email":
            return prop_value["email"]
        elif prop_type == "phone_number":
            return prop_value["phone_number"]
        return None

    def get_latest_mood(self):
        # This function will be expanded to analyze mood based on the new 'State' database structure
        # For now, it's a placeholder.
        return "neutral"

    def get_daily_plan(self):
        # This function will be expanded to fetch daily plan from 'Events and Projects' database
        # For now, it's a placeholder.
        return []

    def get_goals(self):
        # This function will be expanded to fetch goals from 'Goals' database
        # For now, it's a placeholder.
        return []

    def get_interventions_for_pattern(self, pattern_id):
        # This function will be expanded to fetch interventions based on patterns
        # For now, it's a placeholder.
        return []

    def record_mood(self, mood_data):
        # This function will be expanded to record mood in 'State' database
        # For now, it's a placeholder.
        pass

    def record_dream(self, dream_text):
        # This function will be expanded to record dreams in 'State' database
        # For now, it's a placeholder.
        pass

    def record_event(self, event_data):
        # This function will be expanded to record events in 'Events and Projects' database
        # For now, it's a placeholder.
        pass

    def update_task_status(self, task_id, status):
        # This function will be expanded to update task status in 'Events and Projects' database
        # For now, it's a placeholder.
        pass

    def get_random_photo_task(self):
        # This function will be expanded to fetch random photo tasks from a Notion database
        # For now, it's a placeholder.
        return {"task": "Сфоткай свои кроссовки", "expected_object": "кроссовки"}

    def get_personal_events(self, date, mood):
        # This function will be expanded to fetch personalized events from 'Event Finder' database
        # For now, it's a placeholder.
        return []

    def get_people_context(self, person_name):
        # This function will be expanded to fetch context about people from 'People' database
        # For now, it's a placeholder.
        return ""
