from dataclasses import dataclass
from typing import List, Dict, Optional
import json


@dataclass
class PlayerState:
    chat_id: int
    username: str
    health: int
    food: int
    water: int
    weapons: List[str]
    current_day: int
    difficulty: str
    location: str
    inventory: Dict[str, int]
    game_active: bool = False

    def to_dict(self) -> Dict:
        return {
            "chat_id": self.chat_id,
            "username": self.username,
            "health": self.health,
            "food": self.food,
            "water": self.water,
            "weapons": self.weapons,
            "current_day": self.current_day,
            "difficulty": self.difficulty,
            "location": self.location,
            "inventory": self.inventory,
            "game_active": self.game_active,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PlayerState":
        return cls(**data)


class GameStateManager:
    def __init__(self, database):
        self.db = database
        self.active_games = {}
        self._load_active_games()  # Load saved games on startup
        
    def _load_active_games(self):
        """Load all active games from the database."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT game_state FROM players WHERE game_active = 1")
            rows = cursor.fetchall()
            
            for row in rows:
                try:
                    game_state = json.loads(row[0])
                    player = PlayerState.from_dict(game_state)
                    self.active_games[player.chat_id] = player
                    print(f"[GameStateManager] Loaded active game for user {player.username}")
                except Exception as e:
                    print(f"[GameStateManager] Error loading game state: {e}")

    def create_new_game(self, chat_id: int, username: str, difficulty: str) -> PlayerState:
        from config import GameConfig

        # End any existing game for this chat_id
        if chat_id in self.active_games:
            old_game = self.active_games[chat_id]
            old_game.game_active = False
            self._save_to_db(old_game)
            print(f"[GameStateManager] Ended previous game for user {username}")

        settings = GameConfig.DIFFICULTY_LEVELS[difficulty]
        player_state = PlayerState(
            chat_id=chat_id,
            username=username,
            health=settings["initial_health"],
            food=settings["initial_food"],
            water=settings["initial_water"],
            weapons=settings["initial_weapons"].copy(),
            current_day=1,
            difficulty=difficulty,
            location="Safe House",
            inventory={},
            game_active=True,
        )

        self.active_games[chat_id] = player_state
        self._save_to_db(player_state)
        print(f"[GameStateManager] Created new game for user {username}")
        return player_state

    def _save_to_db(self, player_state: PlayerState):
        """Save player state to database."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO players 
                (chat_id, username, game_state, health, food, water, weapons, current_day, difficulty, location, inventory, game_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    player_state.chat_id,
                    player_state.username,
                    json.dumps(player_state.to_dict()),
                    player_state.health,
                    player_state.food,
                    player_state.water,
                    json.dumps(player_state.weapons),
                    player_state.current_day,
                    player_state.difficulty,
                    player_state.location,
                    json.dumps(player_state.inventory),
                    player_state.game_active,
                ),
            )
            conn.commit()
            print(f"[GameStateManager] Saved game state for user {player_state.username}, active: {player_state.game_active}")

    def get_player_state(self, chat_id: int) -> Optional[PlayerState]:
        """Get player state from memory or database."""
        # First try memory
        if chat_id in self.active_games:
            return self.active_games[chat_id]
            
        # Then try database
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT game_state FROM players WHERE chat_id = ? AND game_active = 1",
                (chat_id,)
            )
            row = cursor.fetchone()
            
            if row:
                try:
                    game_state = json.loads(row[0])
                    player = PlayerState.from_dict(game_state)
                    self.active_games[chat_id] = player
                    return player
                except Exception as e:
                    print(f"[GameStateManager] Error loading game state: {e}")
                    
        return None
