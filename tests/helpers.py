"""Gemeinsame Testdaten."""
from app import db

# Erfundener Wettkampf am 27.6.2027, 12-h-Wochen
SETTINGS = {**db.DEFAULT_SETTINGS, "goal_name": "Ironman Kuckuckshausen", "goal_date": "2027-06-27", "week_hours": 12,
            "setup_done": True}
