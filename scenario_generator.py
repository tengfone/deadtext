import json
from typing import Dict, Optional
import logging
import datetime
import random


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
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('telegram').setLevel(logging.WARNING)
        self.logger = logging.getLogger("DeadText")
        self.logger.info("ScenarioGenerator initialized")

    def _format_telegram_markdown(self, text: str) -> str:
        """Format text with Telegram markdown v2 styling."""
        # Split text into sections
        sections = text.split("[")
        if len(sections) <= 1:
            return text

        formatted_text = sections[0]  # Keep any text before first section
        for section in sections[1:]:
            if "]" not in section:
                formatted_text += "[" + section
                continue

            header, content = section.split("]", 1)
            # Format section header in bold
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
    ) -> str:
        self.logger.info(
            f"Generating scenario for {username} - Day: {day}, Location: {location}, Difficulty: {difficulty}"
        )

        # Get player context
        health = context.get('health', 100)
        food = context.get('food', 0)
        water = context.get('water', 0)
        weapons = context.get('weapons', [])
        
        # Determine scenario difficulty factors
        resource_scarcity = "scarce" if food < 5 or water < 5 else "moderate"
        health_status = "critical" if health < 30 else "injured" if health < 70 else "healthy"
        armed_status = "unarmed" if not weapons else "armed"
        
        # Generate appropriate atmosphere based on context
        atmosphere_factors = []
        if day > 20:
            atmosphere_factors.append("The extended isolation has taken its toll on the city.")
        if health_status == "critical":
            atmosphere_factors.append("Your wounds make every movement painful.")
        if resource_scarcity == "scarce":
            atmosphere_factors.append("Your stomach growls, reminding you of your dwindling supplies.")
        
        atmosphere = " ".join(atmosphere_factors) if atmosphere_factors else f"The {difficulty.lower()} streets of {location} remain dangerous as ever."

        # Generate situation based on context
        situations = {
            "critical_health": [
                "A medical clinic is visible in the distance, but zombies patrol the area.",
                "You spot a pharmacy across the street, its windows broken but contents potentially intact.",
            ],
            "low_resources": [
                "A supermarket's back entrance appears unguarded, but strange noises echo from within.",
                "An abandoned food truck sits in the alley, possibly still containing supplies.",
            ],
            "armed": [
                "The sound of gunfire in the distance suggests other survivors nearby.",
                "A military checkpoint lies ahead, potentially holding valuable equipment.",
            ],
            "unarmed": [
                "A sporting goods store might have something to defend yourself with.",
                "A police station looms nearby, possibly containing weapons.",
            ],
            "default": [
                "A residential area stretches before you, houses waiting to be explored.",
                "The city's commercial district offers various buildings to search.",
            ]
        }

        # Choose appropriate situation
        if health_status == "critical":
            situation = random.choice(situations["critical_health"])
        elif resource_scarcity == "scarce":
            situation = random.choice(situations["low_resources"])
        elif armed_status == "armed" and random.random() < 0.3:
            situation = random.choice(situations["armed"])
        elif armed_status == "unarmed":
            situation = random.choice(situations["unarmed"])
        else:
            situation = random.choice(situations["default"])

        # Generate contextual choices
        choices = []
        
        # Always offer a safe option
        choices.append("1. (Safe) - Observe the area carefully and plan your next move")
        
        # Add contextual risky options
        if "clinic" in situation.lower() or "pharmacy" in situation.lower():
            choices.append("2. (Risky) - Try to find medical supplies")
        elif "supermarket" in situation.lower() or "food" in situation.lower():
            choices.append("2. (Risky) - Search for food and water")
        elif "military" in situation.lower() or "police" in situation.lower():
            choices.append("2. (Risky) - Look for weapons or ammunition")
        else:
            choices.append("2. (Risky) - Explore the area for supplies")

        # Add desperate options based on context
        if health_status == "critical":
            choices.append("3. (Desperate) - Make a dash for medical supplies despite the danger")
        elif resource_scarcity == "scarce":
            choices.append("3. (Desperate) - Take dangerous risks to find food")
        elif armed_status == "unarmed":
            choices.append("3. (Desperate) - Search for weapons at any cost")
        else:
            choices.append("3. (Desperate) - Take a dangerous gamble that might pay off")

        # Format the scenario
        scenario = f"""[ATMOSPHERE]
{atmosphere}

[SITUATION]
{situation}

[CHOICES]
{chr(10).join(choices)}"""

        # Format the response with Telegram markdown
        formatted_result = self._format_telegram_markdown(scenario)
        # Special formatting for choices
        if "[CHOICES]" in scenario:
            choices_section = scenario.split("[CHOICES]")[1]
            formatted_choices = self._format_choices(choices_section)
            formatted_result = formatted_result.replace(
                choices_section, "\n" + formatted_choices
            )

        return formatted_result

    async def process_action(
        self, username: str, user_input: str, current_scenario: str, player_state: dict
    ) -> dict:
        self.logger.info(f"User {username} action: {user_input}")
        self.logger.debug(f"Current scenario: {current_scenario}")

        # Analyze the action using natural language understanding
        action_analysis = {
            "action_type": "CUSTOM",  # Default to custom action
            "description": user_input,
            "confidence": 90,
            "effects": [],
            "risks": [],
            "is_valid": True,
            "feedback": ""
        }

        # Identify key themes in the action
        lower_input = user_input.lower()
        lower_scenario = current_scenario.lower()
        
        # Validate action against scenario context
        invalid_actions = []
        
        # Check for crafting without materials
        if any(word in lower_input for word in ["craft", "make", "build", "create"]):
            if "workshop" not in lower_scenario and "tools" not in lower_scenario:
                invalid_actions.append("You don't have the tools or workspace to craft items here.")
                action_analysis["is_valid"] = False
        
        # Check for using non-existent items
        if "gun" in lower_input or "shoot" in lower_input:
            if not any(weapon for weapon in player_state.get("weapons", []) if "gun" in weapon.lower() or "pistol" in weapon.lower()):
                invalid_actions.append("You don't have any firearms in your possession.")
                action_analysis["is_valid"] = False
        
        # Check for interacting with non-existent objects
        if "door" in lower_input and "door" not in lower_scenario:
            invalid_actions.append("There is no door in your current location.")
            action_analysis["is_valid"] = False
        
        if "window" in lower_input and "window" not in lower_scenario:
            invalid_actions.append("There are no windows in your current location.")
            action_analysis["is_valid"] = False
        
        # Check for searching empty areas
        if "search" in lower_input and "empty" in lower_scenario:
            invalid_actions.append("This area appears to be completely empty.")
            action_analysis["is_valid"] = False

        if not action_analysis["is_valid"]:
            feedback = "\n".join(invalid_actions)
            action_analysis["feedback"] = f"❌ That's not possible right now:\n{feedback}\n\nTry something else that fits your current situation."
            return action_analysis

        # If action is valid, process it normally
        if any(word in lower_input for word in ["fight", "attack", "shoot", "kill", "defend"]):
            if "zombie" in lower_scenario or "threat" in lower_scenario:
                action_analysis["action_type"] = "COMBAT"
                action_analysis["risks"].append("Could attract more zombies")
                action_analysis["risks"].append("Might get injured")
                if "gun" in lower_input or "shoot" in lower_input:
                    action_analysis["effects"].append("Uses ammunition")
            else:
                action_analysis["is_valid"] = False
                action_analysis["feedback"] = "❌ There are no immediate threats to fight here. Try exploring or looking around first."
                return action_analysis
            
        elif any(word in lower_input for word in ["sneak", "hide", "quiet", "stealth"]):
            action_analysis["action_type"] = "STEALTH"
            action_analysis["effects"].append("Moves quietly")
            action_analysis["risks"].append("Might get cornered")
            
        elif any(word in lower_input for word in ["search", "look", "explore", "find"]):
            action_analysis["action_type"] = "EXPLORE"
            action_analysis["effects"].append("Might find supplies")
            action_analysis["risks"].append("Could encounter zombies")
            
        elif any(word in lower_input for word in ["rest", "sleep", "wait", "heal"]):
            if "safe" in lower_scenario or "quiet" in lower_scenario:
                action_analysis["action_type"] = "REST"
                action_analysis["effects"].append("Recovers health")
                action_analysis["effects"].append("Uses food and water")
            else:
                action_analysis["is_valid"] = False
                action_analysis["feedback"] = "❌ It's not safe to rest here. Find a more secure location first."
                return action_analysis
            
        elif any(word in lower_input for word in ["run", "move", "go", "climb", "jump"]):
            action_analysis["action_type"] = "MOVE"
            action_analysis["effects"].append("Changes location")
            action_analysis["risks"].append("Uses stamina")

        # Add player state context
        action_analysis["player_context"] = {
            "health": player_state.get("health", 100),
            "food": player_state.get("food", 0),
            "water": player_state.get("water", 0),
            "weapons": player_state.get("weapons", [])
        }

        return {
            **action_analysis,
            "formatted_action": self._format_user_action(username, user_input)
        }

    async def generate_outcome(
        self,
        username: str,
        action_type: str,
        action_description: str,
        current_scenario: str,
        player_state: dict,
    ) -> str:
        self.logger.info(
            f"Generating outcome for {username}'s action: {action_type} - {action_description}"
        )

        # Get player context
        health = player_state.get('health', 100)
        food = player_state.get('food', 0)
        water = player_state.get('water', 0)
        weapons = player_state.get('weapons', [])
        
        # Determine context factors
        health_status = "critical" if health < 30 else "injured" if health < 70 else "healthy"
        armed_status = "unarmed" if not weapons else "armed"
        has_gun = any(w.lower() in ['gun', 'pistol', 'rifle'] for w in weapons)
        
        # Create outcome pools based on action type and context
        outcomes = {
            "COMBAT": {
                "success": [
                    "Your quick thinking and combat experience pay off as you handle the threat.",
                    "The fight is intense but brief, ending in your favor.",
                    "Your training kicks in, and you dispatch the threats efficiently.",
                ],
                "failure": [
                    "The situation proves more dangerous than anticipated.",
                    "You're forced to retreat after taking some hits.",
                    "The fight doesn't go as planned, leaving you wounded.",
                ],
                "critical": [
                    "Despite your injuries, you manage to survive the encounter.",
                    "Your weakened state makes the fight extremely dangerous.",
                ],
                "gun": [
                    "The gunshot echoes through the streets, effective but loud.",
                    "Your aim is true, but the noise will attract attention.",
                ]
            },
            "STEALTH": {
                "success": [
                    "You move like a shadow, avoiding detection.",
                    "Your careful movements keep you hidden from danger.",
                    "Patience and timing allow you to slip by unnoticed.",
                ],
                "failure": [
                    "A small noise gives away your position.",
                    "The path isn't as clear as you thought.",
                    "Staying hidden proves more challenging than expected.",
                ]
            },
            "EXPLORE": {
                "success": [
                    "Your thorough search reveals valuable supplies.",
                    "Patience pays off as you discover hidden resources.",
                    "The risk was worth it - you find useful items.",
                ],
                "failure": [
                    "The area has been picked clean already.",
                    "Your search yields nothing of value.",
                    "Others have clearly been here before you.",
                ]
            },
            "REST": {
                "success": [
                    "You find a moment of peace to recover your strength.",
                    "The brief respite helps you regain your energy.",
                    "A safe spot allows you to tend to your needs.",
                ],
                "failure": [
                    "Your rest is interrupted by distant noises.",
                    "The area isn't as safe as you thought.",
                    "Constant vigilance makes true rest difficult.",
                ]
            },
            "MOVE": {
                "success": [
                    "You navigate the dangerous streets successfully.",
                    "The path ahead clears as you move carefully.",
                    "Your route proves safer than expected.",
                ],
                "failure": [
                    "The way forward is more treacherous than it appeared.",
                    "New dangers emerge as you move through the area.",
                    "The route forces you to take unexpected detours.",
                ]
            }
        }

        # Select appropriate outcome text
        success_chance = 0.7  # Base success chance
        if health_status == "critical":
            success_chance -= 0.3
        elif health_status == "injured":
            success_chance -= 0.1
        
        if armed_status == "armed":
            success_chance += 0.1

        # Determine outcome success and get text
        is_success = random.random() < success_chance
        outcome_pool = outcomes.get(action_type, outcomes["MOVE"])
        
        if health_status == "critical" and "critical" in outcome_pool:
            outcome_text = random.choice(outcome_pool["critical"])
        elif has_gun and action_type == "COMBAT" and "gun" in outcome_pool:
            outcome_text = random.choice(outcome_pool["gun"])
        else:
            outcome_text = random.choice(outcome_pool["success" if is_success else "failure"])

        # Generate status effects based on outcome
        status_effects = []
        if action_type == "COMBAT":
            if has_gun:
                status_effects.append("Used ammunition")
            if not is_success:
                status_effects.append("Sustained injuries")
        elif action_type == "EXPLORE" and is_success:
            status_effects.append("Found supplies")
        elif action_type == "REST" and is_success:
            status_effects.append("Recovered some health")
            status_effects.append("Used supplies")

        # Generate next situation based on outcome
        next_situations = {
            "COMBAT": {
                "success": [
                    "The immediate threat is gone, but stay alert.",
                    "Victory is yours, but others may have heard the fight.",
                ],
                "failure": [
                    "You need to find a safe place to recover.",
                    "That was too close - time to be more careful.",
                ]
            },
            "STEALTH": {
                "success": ["You've avoided detection, but for how long?"],
                "failure": ["You need to find another way around."]
            },
            "EXPLORE": {
                "success": ["There might be more to find in the area."],
                "failure": ["Time to move on to somewhere else."]
            },
            "REST": {
                "success": ["You feel better, but danger never rests."],
                "failure": ["You need to find a safer spot."]
            },
            "MOVE": {
                "success": ["What dangers await in this new area?"],
                "failure": ["The path ahead looks treacherous."]
            }
        }

        next_situation = random.choice(
            next_situations.get(action_type, next_situations["MOVE"])[
                "success" if is_success else "failure"
            ]
        )

        result = f"""[OUTCOME]
{outcome_text}

[STATUS]
{' | '.join(status_effects) if status_effects else 'No significant changes'}

[NEXT]
{next_situation}"""

        return self._format_telegram_markdown(result)

    def get_fallback_response(self, username: str) -> str:
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
