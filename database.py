import sqlite3
from contextlib import contextmanager
from datetime import datetime


class Database:
    def __init__(self, db_name="deadtext.db"):
        self.db_name = db_name
        self.init_database()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        try:
            yield conn
        finally:
            conn.close()

    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create players table with all necessary fields
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    game_state TEXT NOT NULL,
                    health INTEGER NOT NULL,
                    food INTEGER NOT NULL,
                    water INTEGER NOT NULL,
                    weapons TEXT NOT NULL,
                    current_day INTEGER NOT NULL,
                    difficulty TEXT NOT NULL,
                    location TEXT NOT NULL,
                    inventory TEXT NOT NULL,
                    game_active BOOLEAN NOT NULL DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create rate_limits table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    chat_id INTEGER PRIMARY KEY,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_reset DATETIME NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES players(chat_id)
                )
            """
            )

            # Create index on game_active for faster queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_game_active 
                ON players(game_active)
                """
            )

            # Create game_history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS game_history (
                    chat_id INTEGER,
                    username TEXT NOT NULL,
                    game_id INTEGER,
                    result TEXT,
                    survived_days INTEGER NOT NULL,
                    difficulty TEXT NOT NULL,
                    final_location TEXT NOT NULL,
                    final_state TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, game_id)
                )
            """
            )

            # Create trigger to update last_updated timestamp
            cursor.execute(
                """
                CREATE TRIGGER IF NOT EXISTS update_player_timestamp 
                AFTER UPDATE ON players
                BEGIN
                    UPDATE players SET last_updated = CURRENT_TIMESTAMP 
                    WHERE chat_id = NEW.chat_id;
                END;
                """
            )

            conn.commit()

    def cleanup_inactive_games(self, hours=24):
        """Move inactive games to history and clean up players table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find inactive games
            cursor.execute(
                """
                SELECT chat_id, username, game_state, current_day, difficulty, location
                FROM players
                WHERE game_active = 1 
                AND datetime(last_updated) < datetime('now', '-' || ? || ' hours')
                """,
                (hours,)
            )
            inactive_games = cursor.fetchall()
            
            # Move to history and mark as inactive
            for game in inactive_games:
                chat_id, username, game_state, days, difficulty, location = game
                
                # Get next game_id for this chat_id
                cursor.execute(
                    "SELECT COALESCE(MAX(game_id), 0) + 1 FROM game_history WHERE chat_id = ?",
                    (chat_id,)
                )
                game_id = cursor.fetchone()[0]
                
                # Add to history
                cursor.execute(
                    """
                    INSERT INTO game_history 
                    (chat_id, username, game_id, result, survived_days, difficulty, final_location, final_state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chat_id,
                        username,
                        game_id,
                        "Game abandoned due to inactivity",
                        days,
                        difficulty,
                        location,
                        game_state
                    )
                )
                
                # Mark game as inactive
                cursor.execute(
                    "UPDATE players SET game_active = 0 WHERE chat_id = ?",
                    (chat_id,)
                )
            
            conn.commit()

    def check_rate_limit(self, chat_id: int) -> tuple[bool, int, datetime]:
        """Check if user has exceeded rate limit.
        Returns (is_allowed, remaining_messages, reset_time)"""
        from config import GameConfig

        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current rate limit info
            cursor.execute(
                """
                SELECT message_count, last_reset
                FROM rate_limits
                WHERE chat_id = ?
                """,
                (chat_id,)
            )
            row = cursor.fetchone()
            
            now = datetime.utcnow()
            next_reset = GameConfig.get_next_reset_time()
            
            # If no record exists or it's past reset time, create/reset the counter
            if not row or datetime.fromisoformat(row[1]) < now.replace(
                hour=GameConfig.RATE_LIMIT_RESET_HOUR,
                minute=0,
                second=0,
                microsecond=0
            ):
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO rate_limits (chat_id, message_count, last_reset)
                    VALUES (?, 1, ?)
                    """,
                    (chat_id, now.isoformat())
                )
                conn.commit()
                return True, GameConfig.MAX_MESSAGES_PER_DAY - 1, next_reset
            
            # Check if user has exceeded limit
            message_count = row[0]
            if message_count >= GameConfig.MAX_MESSAGES_PER_DAY:
                return False, 0, next_reset
            
            # Increment message count
            cursor.execute(
                """
                UPDATE rate_limits
                SET message_count = message_count + 1
                WHERE chat_id = ?
                """,
                (chat_id,)
            )
            conn.commit()
            
            remaining = GameConfig.MAX_MESSAGES_PER_DAY - (message_count + 1)
            return True, remaining, next_reset

    def reset_rate_limits(self):
        """Reset all rate limits. Should be called daily at reset time."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM rate_limits")
            conn.commit()
