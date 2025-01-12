import os
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram import BotCommand
from database import Database
from game_state import GameStateManager
from game_logic import GameLogic
from scenario_generator import ScenarioGenerator
from telegram_handler import TelegramHandler
import asyncio
from datetime import datetime, timedelta
from config import GameConfig

# Define conversation states
CHOOSING_DIFFICULTY, PLAYING = range(2)


async def setup_commands(application):
    """Setup bot commands that show up in the menu."""
    commands = [
        BotCommand("start", "Start a new survival game"),
        BotCommand("help", "Show game instructions and tips"),
        BotCommand("status", "Check your current status"),
        BotCommand("inventory", "View your inventory"),
        BotCommand("daily", "Check your remaining daily messages"),
        BotCommand("location", "See your current location"),
        BotCommand("stats", "View your survival statistics"),
    ]
    await application.bot.set_my_commands(commands)


async def reset_rate_limits(context):
    """Task to reset rate limits daily at midnight UTC."""
    database = context.job.data["database"]
    while True:
        now = datetime.utcnow()
        next_reset = GameConfig.get_next_reset_time()

        # Calculate time to next reset
        wait_time = (next_reset - now).total_seconds()
        print(f"[RateLimit] Next reset in {wait_time/3600:.1f} hours")

        # Wait until next reset time
        await asyncio.sleep(wait_time)

        # Reset rate limits
        print("[RateLimit] Resetting rate limits")
        database.reset_rate_limits()


def main():
    # Load environment variables
    load_dotenv()

    # Initialize components
    database = Database()
    state_manager = GameStateManager(database)
    scenario_generator = ScenarioGenerator()
    game_logic = GameLogic(state_manager, scenario_generator)

    # Clean up any inactive games
    print("Cleaning up inactive games...")
    database.cleanup_inactive_games(hours=24)

    # Initialize Telegram bot
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    application = ApplicationBuilder().token(telegram_token).build()

    # Setup commands
    asyncio.get_event_loop().run_until_complete(setup_commands(application))

    # Initialize handler
    handler = TelegramHandler(game_logic, state_manager)

    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", handler.start)],
        states={
            CHOOSING_DIFFICULTY: [
                CallbackQueryHandler(
                    handler.difficulty_callback, pattern="^difficulty_"
                )
            ],
            PLAYING: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, handler.handle_text_input
                ),
                CallbackQueryHandler(handler.handle_action, pattern="^action_"),
            ],
        },
        fallbacks=[CommandHandler("start", handler.start)],
        name="main_conversation",
        persistent=False,
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", handler.help_command))
    application.add_handler(CommandHandler("status", handler.status_command))
    application.add_handler(CommandHandler("inventory", handler.inventory_command))
    application.add_handler(CommandHandler("daily", handler.daily_command))
    application.add_handler(CommandHandler("location", handler.location_command))
    application.add_handler(CommandHandler("stats", handler.stats_command))
    application.add_handler(CallbackQueryHandler(handler.start, pattern="^start_new$"))

    # Schedule rate limit reset job
    job_queue = application.job_queue
    job_queue.run_repeating(
        reset_rate_limits,
        interval=timedelta(days=1),
        first=GameConfig.get_next_reset_time(),
        data={"database": database},
    )

    # Start the bot
    print("Starting DeadText bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
