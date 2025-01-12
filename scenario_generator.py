import json
from typing import Dict, Optional
import logging
import datetime
import random
from llm_handler import LLMHandler
from telegram import Message


class ScenarioGenerator:
    def __init__(self):
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler("deadtext_game.log"),
                logging.StreamHandler(),
            ],
        )
        # Filter out HTTP request logs
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)
        self.logger = logging.getLogger("DeadText")
        self.logger.info("ScenarioGenerator initialized")

        # Initialize LLM handler
        self.llm = LLMHandler()

    def _format_telegram_markdown(self, text: str) -> str:
        """Format text with Telegram markdown v2 styling."""
        sections = text.split("[")
        if len(sections) <= 1:
            return text

        formatted_text = sections[0]
        for section in sections[1:]:
            if "]" not in section:
                formatted_text += "[" + section
                continue

            header, content = section.split("]", 1)
            formatted_text += f"*{header}*\n{content.strip()}\n"

        return formatted_text.strip()

    def _format_choices(self, text: str) -> str:
        """Format choices section with special styling."""
        lines = text.split("\n")
        formatted_lines = []

        for line in lines:
            if line.strip().startswith("1. (Safe)"):
                formatted_lines.append(f"🟢 _Safe_ - {line.split('-', 1)[1].strip()}")
            elif line.strip().startswith("2. (Risky)"):
                formatted_lines.append(f"🟡 _Risky_ - {line.split('-', 1)[1].strip()}")
            elif line.strip().startswith("3. (Desperate)"):
                formatted_lines.append(
                    f"🔴 _Desperate_ - {line.split('-', 1)[1].strip()}"
                )
            else:
                formatted_lines.append(line)

        return "\n".join(formatted_lines)

    def _format_user_action(self, username: str, action: str) -> str:
        """Format user action."""
        self.logger.info(f"User {username} action: {action}")
        return ""  # Don't echo the action back to the user

    async def generate_scenario(
        self,
        username: str,
        day: int,
        location: str,
        difficulty: str,
        context: dict = None,
        message: Message = None,
    ) -> str:
        """Generate a scenario based on the current game state."""
        loading_messages = [
            "🌍 Analyzing surroundings...",
            "🧟‍♂️ Scanning for threats...",
            "📍 Evaluating location...",
            "🎯 Calculating survival options...",
            "⚔️ Assessing dangers...",
            "🎲 Determining possibilities...",
        ]

        # Prepare context for LLM
        llm_context = {
            "username": username,
            "day": day,
            "location": location,
            "difficulty": difficulty,
            "health": context.get("health", 100),
            "food": context.get("food", 0),
            "water": context.get("water", 0),
            "weapons": context.get("weapons", []),
            "inventory": context.get("inventory", {}),
        }

        try:
            scenario = await self.llm.generate_scenario(
                llm_context, loading_messages, message
            )
            if not scenario:
                self.logger.warning(
                    "Failed to generate scenario using LLM, using fallback"
                )
                return self.get_fallback_response(username)

            formatted_result = self._format_telegram_markdown(scenario)
            if "[CHOICES]" in scenario:
                choices_section = scenario.split("[CHOICES]")[1]
                formatted_choices = self._format_choices(choices_section)
                formatted_result = formatted_result.replace(
                    choices_section, "\n" + formatted_choices
                )

            return formatted_result

        except Exception as e:
            self.logger.error(f"Error generating scenario: {str(e)}")
            return self.get_fallback_response(username)

    async def generate_outcome(
        self,
        action_result: dict,
        username: str,
        current_scenario: str = None,
        player_state: dict = None,
        message: Message = None,
    ) -> str:
        """Generate a narrative outcome based on the action result."""
        if not action_result or not isinstance(action_result, dict):
            return self.get_fallback_response(username)

        action_type = action_result.get("action_type", "CUSTOM")
        description = action_result.get("description", "")
        consequences = action_result.get("consequences", [])
        risk_level = action_result.get("risk_level", 5)

        outcome = f"*[ACTION]*\n👤 *{username}* {description}\n\n"

        if risk_level <= 3:
            outcome += "🟢 *Outcome*\n"
        elif risk_level <= 7:
            outcome += "🟡 *Outcome*\n"
        else:
            outcome += "🔴 *Outcome*\n"

        if consequences:
            outcome += random.choice(consequences)
        else:
            outcome += "The situation continues to develop..."

        return outcome

    async def process_action(
        self,
        username: str,
        user_input: str,
        current_scenario: str,
        player_state: dict,
        message: Message = None,
    ) -> dict:
        """Process a player's action and return the result with narrative."""
        loading_messages = [
            "🤔 Analyzing your action...",
            "⚡ Processing decision...",
            "🎲 Calculating outcome...",
            "🔄 Determining consequences...",
            "📊 Evaluating risks...",
            "🎯 Finalizing results...",
        ]

        try:
            action_result = await self.llm.process_action(
                user_input, player_state, loading_messages, message
            )
            if not action_result:
                self.logger.warning("Failed to get action result from LLM")
                return self._get_fallback_action(username, user_input)

            outcome = await self.generate_outcome(action_result, username)
            action_result["formatted_action"] = outcome
            action_result["is_valid"] = True

            return action_result

        except Exception as e:
            self.logger.error(f"Error processing action: {str(e)}")
            return self._get_fallback_action(username, user_input)

    def _get_fallback_action(self, username: str, user_input: str) -> dict:
        """Create a fallback action result when processing fails."""
        return {
            "action_type": "CUSTOM",
            "description": user_input,
            "consequences": ["The situation remains uncertain..."],
            "risk_level": 5,
            "resource_impacts": {"health": 0, "food": -1, "water": -1},
            "is_valid": True,
            "formatted_action": self._format_user_action(username, user_input),
        }

    def get_fallback_response(self, username: str) -> str:
        """Get a fallback response when scenario generation fails."""
        self.logger.warning(f"Using fallback response for {username}")
        fallback_responses = [
            f"*EMERGENCY ALERT*\n\n👤 *{username}* finds the streets quiet, but danger lurks nearby. You must decide whether to:\n\n"
            + "🟢 _Safe_ - Find a safe place to rest\n"
            + "🟡 _Risky_ - Search for supplies\n"
            + "🔴 _Desperate_ - Prepare for confrontation",
            f"*DANGER WARNING*\n\n👤 *{username}* hears zombies in the distance. Your options are:\n\n"
            + "🟢 _Safe_ - Secure your current position\n"
            + "🟡 _Risky_ - Look for resources\n"
            + "🔴 _Desperate_ - Move to a new location",
            f"*CRITICAL SITUATION*\n\n👤 *{username}* assesses the surroundings. Choose wisely:\n\n"
            + "🟢 _Safe_ - Stay hidden and observe\n"
            + "🟡 _Risky_ - Scout the immediate area\n"
            + "🔴 _Desperate_ - Make a run for it",
        ]
        return random.choice(fallback_responses)
