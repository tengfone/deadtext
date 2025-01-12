from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import asyncio
from datetime import datetime

CHOOSING_DIFFICULTY, PLAYING = range(2)


class TelegramHandler:
    def __init__(self, game_logic, state_manager):
        self.game_logic = game_logic
        self.state_manager = state_manager

    async def show_loading_message(self, message, loading_text="⌛ Processing..."):
        loading_msg = await message.reply_text(loading_text)
        await asyncio.sleep(1.5)  # Add a small delay for better UX
        return loading_msg

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        loading_msg = await self.show_loading_message(
            update.message, "⌛ Initializing apocalypse simulation..."
        )

        keyboard = [
            [
                InlineKeyboardButton("Easy", callback_data="difficulty_easy"),
                InlineKeyboardButton("Normal", callback_data="difficulty_normal"),
                InlineKeyboardButton("Hard", callback_data="difficulty_hard"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await loading_msg.delete()
        await update.message.reply_text(
            "🧟‍♂️ Welcome to DeadText! 🧟‍♀️\n\n"
            "The world has been overrun by zombies, and your survival depends on "
            "your choices. Choose your difficulty level to begin:",
            reply_markup=reply_markup,
        )
        return CHOOSING_DIFFICULTY

    async def difficulty_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        await query.answer()

        difficulty = query.data.split("_")[1]
        chat_id = update.effective_chat.id
        username = update.effective_user.first_name

        # Send initial loading message
        loading_msg = await query.message.reply_text(
            "⌛ *Creating your apocalypse survival story...*",
            parse_mode="Markdown"
        )

        try:
            print(
                f"[TelegramHandler] Creating new game for user {username} with difficulty {difficulty}"
            )

            # Create new game
            player = self.state_manager.create_new_game(chat_id, username, difficulty)
            print(
                f"[TelegramHandler] Game created for user {username} with initial health={player.health}"
            )

            # Prepare full player context
            player_context = {
                "health": player.health,
                "food": player.food,
                "water": player.water,
                "weapons": player.weapons,
                "inventory": player.inventory,
                "location": player.location,
                "current_day": player.current_day,
                "difficulty": player.difficulty
            }

            # Generate initial scenario
            initial_scenario = await self.game_logic.scenario_generator.generate_scenario(
                username=username,
                day=1,
                location="Safe House",
                difficulty=difficulty,
                context=player_context,
                message=loading_msg  # Pass the loading message instead of query.message
            )

            # Clean up loading message
            await loading_msg.delete()

            status_keyboard = [
                [
                    InlineKeyboardButton("📊 Status", callback_data="action_status"),
                    InlineKeyboardButton("🎒 Inventory", callback_data="action_inventory")
                ]
            ]

            # Send the game start message
            await query.message.reply_text(
                f"🎮 *Game Started!*\nDifficulty: _{difficulty}_\n\n"
                f"{initial_scenario}\n\n"
                f"❤️ Health: {player.health} | 🍗 Food: {player.food} | 💧 Water: {player.water}\n\n"
                "_What would you like to do? Describe your action..._",
                reply_markup=InlineKeyboardMarkup(status_keyboard),
                parse_mode="Markdown"
            )

            # Delete the original difficulty selection message
            await query.message.delete()
            
            return PLAYING

        except Exception as e:
            print(f"Error in difficulty_callback: {e}")
            if loading_msg:
                await loading_msg.delete()
            await query.message.reply_text(
                "❌ Sorry, there was an error starting your game. Please try again with /start",
                parse_mode="Markdown"
            )
            return ConversationHandler.END

    async def handle_text_input(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
        username = update.effective_user.first_name

        # Check rate limit before processing
        is_allowed, remaining, reset_time = self.state_manager.db.check_rate_limit(
            chat_id
        )
        if not is_allowed:
            time_to_reset = reset_time - datetime.utcnow()
            hours = time_to_reset.seconds // 3600
            minutes = (time_to_reset.seconds % 3600) // 60

            await update.message.reply_text(
                f"❌ You've reached the daily message limit (50 messages).\n"
                f"The limit will reset in {hours}h {minutes}m.\n"
                "Please try again later!"
            )
            return PLAYING

        player = self.state_manager.get_player_state(chat_id)

        if not player or not player.game_active:
            print(
                f"[TelegramHandler] User {username} attempted to play without active game"
            )
            await update.message.reply_text(
                "No active game found. Use /start to begin a new game."
            )
            return ConversationHandler.END

        user_input = update.message.text
        current_scenario = context.user_data.get("current_scenario", "")

        print(f"[TelegramHandler] Processing action from {username}: {user_input}")

        # Get player state for context
        player_state = {
            "health": player.health,
            "food": player.food,
            "water": player.water,
            "weapons": player.weapons,
            "day": player.current_day,
            "difficulty": player.difficulty,
            "location": player.location,
            "inventory": player.inventory
        }

        # Show initial loading message
        loading_msg = await update.message.reply_text(
            "🤖 *Processing your action...*",
            parse_mode="Markdown"
        )

        try:
            # Let the LLM interpret the action
            action_result = await self.game_logic.scenario_generator.process_action(
                username=username,
                user_input=user_input,
                current_scenario=current_scenario,
                player_state=player_state,
                message=loading_msg
            )

            if not action_result:
                raise ValueError("Failed to process action")

            # Generate outcome using the game logic
            result = await self.game_logic.process_turn(
                chat_id,
                action_result["action_type"].lower(),
                action_description=user_input,
                current_scenario=current_scenario,
            )

            # Store the new scenario for context
            context.user_data["current_scenario"] = result

            # Clean up loading message after processing is complete
            try:
                await loading_msg.delete()
            except Exception as e:
                print(f"Error cleaning up loading message: {e}")

            # Check if game is still active
            player = self.state_manager.get_player_state(chat_id)  # Refresh player state
            if player and player.game_active:
                # Add status keyboard
                status_keyboard = [
                    [
                        InlineKeyboardButton("📊 Status", callback_data="action_status"),
                        InlineKeyboardButton("🎒 Inventory", callback_data="action_inventory"),
                    ]
                ]

                # Make the prompt more open-ended
                await update.message.reply_text(
                    f"{result}\n\n" "_What do you do next?_",
                    reply_markup=InlineKeyboardMarkup(status_keyboard),
                    parse_mode="Markdown",
                )

                # If successful, notify user of remaining messages if running low
                if remaining < 10:
                    await update.message.reply_text(
                        f"⚠️ You have {remaining} messages remaining today. The limit resets at midnight UTC.",
                        parse_mode="Markdown"
                    )

                return PLAYING
            else:
                print(
                    f"[TelegramHandler] Game over for user {username} after {player.current_day if player else 'unknown'} days"
                )
                # Game over message
                if player:
                    final_status = (
                        f"*Final Status*\n"
                        f"Survived for: {player.current_day} days\n"
                        f"Difficulty: {player.difficulty}\n"
                        f"Final Health: {player.health}\n"
                        f"Supplies Left: {player.food} food, {player.water} water\n"
                        f"Weapons: {', '.join(player.weapons) if player.weapons else 'None'}"
                    )
                else:
                    final_status = "*Game Over*"

                keyboard = [
                    [InlineKeyboardButton("Start New Game", callback_data="start_new")]
                ]
                await update.message.reply_text(
                    f"{result}\n\n{final_status}\n\n"
                    "_Your story has ended. Ready to survive again?_",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown",
                )
                return ConversationHandler.END

        except Exception as e:
            print(f"Error processing action: {e}")
            # Clean up loading message if there's an error
            try:
                if loading_msg:
                    await loading_msg.delete()
            except Exception as cleanup_error:
                print(f"Error cleaning up loading message: {cleanup_error}")
            
            await update.message.reply_text(
                "❌ Sorry, I had trouble processing that action. Please try again.",
                parse_mode="Markdown"
            )
            return PLAYING

    async def handle_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        action = query.data.split("_")[1]
        chat_id = update.effective_chat.id
        player = self.state_manager.get_player_state(chat_id)

        if not player:
            await query.message.reply_text(
                "No active game found. Use /start to begin a new game."
            )
            return ConversationHandler.END

        status_keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="action_status"),
                InlineKeyboardButton("🎒 Inventory", callback_data="action_inventory"),
            ]
        ]

        if action == "status":
            status_text = (
                f"📊 *Status Report - Day {player.current_day}*\n\n"
                f"❤️ Health: {player.health}\n"
                f"🍗 Food: {player.food}\n"
                f"💧 Water: {player.water}\n"
                f"🔫 Weapons: {', '.join(player.weapons) if player.weapons else 'None'}\n"
                f"📍 Location: {player.location}\n"
                f"⚙️ Difficulty: {player.difficulty}"
            )

            await query.message.reply_text(
                status_text,
                reply_markup=InlineKeyboardMarkup(status_keyboard),
                parse_mode="Markdown",
            )

        elif action == "inventory":
            # Format inventory items
            inventory_items = []
            for item, quantity in player.inventory.items():
                if quantity > 0:
                    inventory_items.append(f"- {item}: {quantity}")

            weapons_list = [f"- {weapon}" for weapon in player.weapons]

            inventory_text = (
                f"🎒 *Inventory Contents*\n\n"
                f"*Supplies*:\n"
                f"- Food: {player.food}\n"
                f"- Water: {player.water}\n\n"
                f"*Weapons*:\n"
                f"{chr(10).join(weapons_list) if weapons_list else '- None'}\n\n"
                f"*Other Items*:\n"
                f"{chr(10).join(inventory_items) if inventory_items else '- None'}"
            )

            await query.message.reply_text(
                inventory_text,
                reply_markup=InlineKeyboardMarkup(status_keyboard),
                parse_mode="Markdown",
            )

        return PLAYING

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        loading_msg = await self.show_loading_message(
            update.message, "⌛ Loading help menu..."
        )

        help_text = (
            "🎮 *DeadText Commands*:\n\n"
            "/start - Start a new game\n"
            "/help - Show this help message\n"
            "/status - Check your current status\n"
            "/inventory - View your inventory\n"
            "/daily - Check remaining messages\n"
            "/location - See current location\n"
            "/stats - View survival statistics\n\n"
            "*Available Actions*:\n"
            "🔍 Search - Look for supplies (try: 'search the building')\n"
            "⚔️ Fight - Combat nearby zombies (try: 'attack the zombie')\n"
            "😴 Rest - Recover health (try: 'rest for a while')\n"
            "🏃 Move - Change location (try: 'move to the store')\n\n"
            "*Tips*:\n"
            "- Balance your resources carefully\n"
            "- Fighting without weapons is dangerous\n"
            "- Rest when your health is low\n"
            "- Survive for 30 days to win!"
        )

        await loading_msg.delete()
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        player = self.state_manager.get_player_state(chat_id)

        if not player or not player.game_active:
            await update.message.reply_text(
                "No active game found. Use /start to begin a new game."
            )
            return

        status_text = (
            f"📊 *Status Report - Day {player.current_day}*\n\n"
            f"❤️ Health: {player.health}\n"
            f"🍗 Food: {player.food}\n"
            f"💧 Water: {player.water}\n"
            f"🔫 Weapons: {', '.join(player.weapons) if player.weapons else 'None'}\n"
            f"📍 Location: {player.location}\n"
            f"⚙️ Difficulty: {player.difficulty}"
        )

        await update.message.reply_text(status_text, parse_mode="Markdown")

    async def inventory_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
        player = self.state_manager.get_player_state(chat_id)

        if not player or not player.game_active:
            await update.message.reply_text(
                "No active game found. Use /start to begin a new game."
            )
            return

        # Format inventory items
        inventory_items = []
        for item, quantity in player.inventory.items():
            if quantity > 0:
                inventory_items.append(f"- {item}: {quantity}")

        weapons_list = [f"- {weapon}" for weapon in player.weapons]

        inventory_text = (
            f"🎒 *Inventory Contents*\n\n"
            f"*Supplies*:\n"
            f"- Food: {player.food}\n"
            f"- Water: {player.water}\n\n"
            f"*Weapons*:\n"
            f"{chr(10).join(weapons_list) if weapons_list else '- None'}\n\n"
            f"*Other Items*:\n"
            f"{chr(10).join(inventory_items) if inventory_items else '- None'}"
        )

        await update.message.reply_text(inventory_text, parse_mode="Markdown")

    async def daily_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        is_allowed, remaining, reset_time = self.state_manager.db.check_rate_limit(
            chat_id
        )

        time_to_reset = reset_time - datetime.utcnow()
        hours = time_to_reset.seconds // 3600
        minutes = (time_to_reset.seconds % 3600) // 60

        daily_text = (
            f"📊 *Daily Message Status*\n\n"
            f"Messages Remaining: {remaining}/{GameConfig.MAX_MESSAGES_PER_DAY}\n"
            f"Reset in: {hours}h {minutes}m\n\n"
            f"_The limit resets at midnight UTC._"
        )

        await update.message.reply_text(daily_text, parse_mode="Markdown")

    async def location_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        chat_id = update.effective_chat.id
        player = self.state_manager.get_player_state(chat_id)

        if not player or not player.game_active:
            await update.message.reply_text(
                "No active game found. Use /start to begin a new game."
            )
            return

        location_text = (
            f"📍 *Current Location*\n\n"
            f"You are at: *{player.location}*\n\n"
            f"_Use natural language to move to a new location, for example:_\n"
            f"'move to the pharmacy' or 'sneak to the grocery store'"
        )

        await update.message.reply_text(location_text, parse_mode="Markdown")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        player = self.state_manager.get_player_state(chat_id)

        if not player or not player.game_active:
            # Get historical stats
            with self.state_manager.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) as games, 
                           MAX(survived_days) as best_run,
                           AVG(survived_days) as avg_days
                    FROM game_history 
                    WHERE chat_id = ?
                    """,
                    (chat_id,),
                )
                stats = cursor.fetchone()

            if stats and stats[0] > 0:
                stats_text = (
                    f"📊 *Survival Statistics*\n\n"
                    f"Games Played: {stats[0]}\n"
                    f"Best Run: {stats[1]} days\n"
                    f"Average Survival: {stats[2]:.1f} days\n\n"
                    f"_Use /start to begin a new game!_"
                )
            else:
                stats_text = (
                    "No game history found.\n\n"
                    "_Use /start to begin your first game!_"
                )
        else:
            stats_text = (
                f"📊 *Current Game Statistics*\n\n"
                f"Days Survived: {player.current_day}\n"
                f"Current Health: {player.health}%\n"
                f"Resources: {player.food} food, {player.water} water\n"
                f"Weapons Found: {len(player.weapons)}\n"
                f"Items Collected: {sum(player.inventory.values())}\n\n"
                f"_Keep surviving! {GameConfig.DAYS_TO_WIN - player.current_day} days left to win!_"
            )

        await update.message.reply_text(stats_text, parse_mode="Markdown")
