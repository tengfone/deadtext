from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class GameConfig:
    # Rate limiting settings
    MAX_MESSAGES_PER_DAY = 50
    RATE_LIMIT_RESET_HOUR = 0  # Reset at midnight UTC

    # Difficulty settings
    DIFFICULTY_LEVELS = {
        "easy": {
            "initial_health": 100,
            "initial_food": 10,
            "initial_water": 10,
            "initial_weapons": ["Baseball Bat"],
            "zombie_damage": 10,
            "resource_depletion_rate": 0.5,
        },
        "normal": {
            "initial_health": 80,
            "initial_food": 7,
            "initial_water": 7,
            "initial_weapons": ["Knife"],
            "zombie_damage": 15,
            "resource_depletion_rate": 1.0,
        },
        "hard": {
            "initial_health": 60,
            "initial_food": 5,
            "initial_water": 5,
            "initial_weapons": ["Fists"],
            "zombie_damage": 20,
            "resource_depletion_rate": 1.5,
        },
    }

    # Game settings
    DAYS_TO_WIN = 30
    MAX_HEALTH = 100
    MAX_INVENTORY_SLOTS = 10

    # Action costs
    SEARCH_ENERGY_COST = 10
    FIGHT_ENERGY_COST = 20
    REST_RECOVERY = 15

    @staticmethod
    def get_next_reset_time() -> datetime:
        """Get the next rate limit reset time (midnight UTC)."""
        now = datetime.utcnow()
        next_reset = now.replace(
            hour=GameConfig.RATE_LIMIT_RESET_HOUR,
            minute=0,
            second=0,
            microsecond=0
        )
        if next_reset <= now:
            next_reset += timedelta(days=1)
        return next_reset
