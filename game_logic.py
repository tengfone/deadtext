from typing import Tuple, Dict, Optional
import random
from config import GameConfig
from game_state import PlayerState


class GameAction:
    @staticmethod
    def search_supplies(player: PlayerState) -> Tuple[str, Dict[str, int]]:
        if player.health <= GameConfig.SEARCH_ENERGY_COST:
            return "You're too exhausted to search for supplies.", {}

        # Random supply finding logic
        found_items = {}
        success_rate = (
            0.7
            if player.difficulty == "easy"
            else 0.5 if player.difficulty == "normal" else 0.3
        )

        if random.random() < success_rate:
            found_items["food"] = random.randint(1, 3)
            found_items["water"] = random.randint(1, 3)
            if random.random() < 0.2:  # 20% chance to find a weapon
                weapons = ["Baseball Bat", "Knife", "Crowbar", "Pistol"]
                found_items["weapon"] = random.choice(weapons)

            message = (
                f"You found: {', '.join([f'{v} {k}' for k, v in found_items.items()])}"
            )
        else:
            message = "You searched but found nothing useful."

        player.health -= GameConfig.SEARCH_ENERGY_COST
        return message, found_items

    @staticmethod
    def fight_zombies(player: PlayerState) -> Tuple[str, int]:
        if player.health <= GameConfig.FIGHT_ENERGY_COST:
            return "You're too exhausted to fight!", 0

        weapon_damage = {
            "Fists": 5,
            "Baseball Bat": 15,
            "Knife": 20,
            "Crowbar": 25,
            "Pistol": 40,
        }

        best_weapon = max(player.weapons, key=lambda w: weapon_damage.get(w, 0))
        damage_dealt = weapon_damage.get(best_weapon, 5)

        # Calculate zombie damage based on difficulty
        zombie_damage = GameConfig.DIFFICULTY_LEVELS[player.difficulty]["zombie_damage"]
        player.health -= zombie_damage
        player.health -= GameConfig.FIGHT_ENERGY_COST

        return (
            f"You fought using your {best_weapon}! Dealt {damage_dealt} damage but took {zombie_damage} damage.",
            damage_dealt,
        )

    @staticmethod
    def rest(player: PlayerState) -> str:
        if player.food <= 0 or player.water <= 0:
            return "You need both food and water to rest effectively."

        player.food -= 1
        player.water -= 1
        heal_amount = GameConfig.REST_RECOVERY

        old_health = player.health
        player.health = min(player.health + heal_amount, GameConfig.MAX_HEALTH)
        actual_heal = player.health - old_health

        return f"You rest and recover {actual_heal} health."


class GameLogic:
    def __init__(self, state_manager, scenario_generator):
        self.state_manager = state_manager
        self.scenario_generator = scenario_generator

    async def process_turn(
        self,
        chat_id: int,
        action: str,
        action_description: str = "",
        current_scenario: str = "",
    ) -> str:
        player = self.state_manager.get_player_state(chat_id)
        if not player or not player.game_active:
            return "No active game found. Start a new game with /start"

        # Process action outcome
        try:
            # Get action analysis from scenario generator
            action_analysis = await self.scenario_generator.process_action(
                player.username,
                action_description,
                current_scenario,
                {
                    "health": player.health,
                    "food": player.food,
                    "water": player.water,
                    "weapons": player.weapons,
                    "difficulty": player.difficulty,
                    "day": player.current_day,
                    "location": player.location,
                    "inventory": player.inventory,
                },
            )

            # Check if action is valid
            if not action_analysis.get("is_valid", True):
                return action_analysis["feedback"]

            # Process daily resource consumption based on action intensity
            action_intensity = {
                "COMBAT": 2.0,
                "MOVE": 1.5,
                "EXPLORE": 1.2,
                "STEALTH": 1.0,
                "REST": 0.5,
                "CUSTOM": 1.0,
            }.get(action_analysis["action_type"], 1.0)

            depletion_rate = GameConfig.DIFFICULTY_LEVELS[player.difficulty][
                "resource_depletion_rate"
            ]
            resource_use = depletion_rate * action_intensity

            player.food = max(0, player.food - resource_use)
            player.water = max(0, player.water - resource_use)

            # Generate dynamic outcome
            outcome = await self.scenario_generator.generate_outcome(
                action_analysis,
                player.username,
                current_scenario,
                {
                    "health": player.health,
                    "food": player.food,
                    "water": player.water,
                    "weapons": player.weapons,
                    "location": player.location,
                    "inventory": player.inventory,
                },
            )

            # Apply resource impacts from action analysis
            if "resource_impacts" in action_analysis:
                impacts = action_analysis["resource_impacts"]
                player.health = max(
                    0,
                    min(
                        GameConfig.MAX_HEALTH, player.health + impacts.get("health", 0)
                    ),
                )
                player.food = max(0, player.food + impacts.get("food", 0))
                player.water = max(0, player.water + impacts.get("water", 0))

            # Use the formatted action from the action result
            result = action_analysis.get("formatted_action", outcome)

        except Exception as e:
            result = "An error occurred while processing your action."

        # Save state after action
        self.state_manager._save_to_db(player)

        # Check win/lose conditions
        if player.health <= 0:
            player.game_active = False
            self.state_manager._save_to_db(player)
            return f"Game Over! You died on day {player.current_day}.\n{result}"
        elif player.current_day >= GameConfig.DAYS_TO_WIN:
            player.game_active = False
            self.state_manager._save_to_db(player)
            return f"Victory! You survived for {GameConfig.DAYS_TO_WIN} days!\n{result}"

        player.current_day += 1
        self.state_manager._save_to_db(player)

        # Generate next scenario
        try:
            next_scenario = await self.scenario_generator.generate_scenario(
                player.username,
                player.current_day,
                player.location,
                player.difficulty,
                {
                    "health": player.health,
                    "food": player.food,
                    "water": player.water,
                    "weapons": player.weapons,
                    "inventory": player.inventory,
                },
            )
        except Exception as e:
            next_scenario = "You continue your survival journey..."

        return f"{result}\n\n{next_scenario}"
