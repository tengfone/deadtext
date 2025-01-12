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
        print("[GameLogic] Initialized with state manager and scenario generator")

    async def process_turn(
        self,
        chat_id: int,
        action: str,
        action_description: str = "",
        current_scenario: str = "",
    ) -> str:
        print(f"[GameLogic] Processing turn for chat_id: {chat_id}, action: {action_description}")
        print(f"[GameLogic] Current scenario: {current_scenario}")

        player = self.state_manager.get_player_state(chat_id)
        if not player or not player.game_active:
            print(f"[GameLogic] No active game found for chat_id: {chat_id}")
            return "No active game found. Start a new game with /start"

        print(
            f"[GameLogic] Player state before action: Health={player.health}, Food={player.food}, Water={player.water}"
        )

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
                    "day": player.current_day
                }
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
                "CUSTOM": 1.0
            }.get(action_analysis["action_type"], 1.0)

            depletion_rate = GameConfig.DIFFICULTY_LEVELS[player.difficulty]["resource_depletion_rate"]
            resource_use = depletion_rate * action_intensity
            
            player.food = max(0, player.food - resource_use)
            player.water = max(0, player.water - resource_use)
            print(f"[GameLogic] Resources after depletion: Food={player.food}, Water={player.water}")

            # Generate dynamic outcome
            outcome = await self.scenario_generator.generate_outcome(
                player.username,
                action_analysis["action_type"],
                action_description,
                current_scenario,
                {
                    "health": player.health,
                    "food": player.food,
                    "water": player.water,
                    "weapons": player.weapons
                }
            )

            # Apply action effects based on type
            if action_analysis["action_type"] == "COMBAT":
                damage_taken = random.randint(5, 15) * action_intensity
                player.health = max(0, player.health - damage_taken)
                
            elif action_analysis["action_type"] == "EXPLORE":
                if random.random() < 0.6:  # 60% chance to find supplies
                    found_food = random.randint(1, 3)
                    found_water = random.randint(1, 3)
                    player.food += found_food
                    player.water += found_water
                    
                    # Random chance to find other items
                    if random.random() < 0.3:  # 30% chance to find items
                        possible_items = {
                            "Bandages": (1, 3),
                            "Medicine": (1, 2),
                            "Ammunition": (5, 15),
                            "Tools": (1, 2)
                        }
                        found_item = random.choice(list(possible_items.keys()))
                        min_qty, max_qty = possible_items[found_item]
                        qty = random.randint(min_qty, max_qty)
                        
                        # Add to inventory
                        if found_item in player.inventory:
                            player.inventory[found_item] += qty
                        else:
                            player.inventory[found_item] = qty
                            
                    # Chance to find weapons
                    if random.random() < 0.2:  # 20% chance to find weapons
                        possible_weapons = ["Baseball Bat", "Knife", "Crowbar", "Pistol"]
                        weights = [0.4, 0.3, 0.2, 0.1]  # Rarer weapons have lower weights
                        found_weapon = random.choices(possible_weapons, weights=weights)[0]
                        if found_weapon not in player.weapons:
                            player.weapons.append(found_weapon)
                    
            elif action_analysis["action_type"] == "REST":
                if player.food > 0 and player.water > 0:
                    heal_amount = min(20, GameConfig.MAX_HEALTH - player.health)
                    player.health = min(player.health + heal_amount, GameConfig.MAX_HEALTH)
                    player.food -= 1
                    player.water -= 1
                    
            # Use items from inventory if mentioned in action
            if "use" in action_description.lower():
                for item in player.inventory:
                    if item.lower() in action_description.lower() and player.inventory[item] > 0:
                        if item == "Bandages":
                            heal_amount = 20
                            player.health = min(player.health + heal_amount, GameConfig.MAX_HEALTH)
                        elif item == "Medicine":
                            heal_amount = 40
                            player.health = min(player.health + heal_amount, GameConfig.MAX_HEALTH)
                        player.inventory[item] -= 1

            print(f"[GameLogic] Action processed: {action_analysis['action_type']}")
            result = outcome

        except Exception as e:
            print(f"[GameLogic] Error processing action: {e}")
            result = "An error occurred while processing your action."

        print(
            f"[GameLogic] Player state after action: Health={player.health}, Food={player.food}, Water={player.water}"
        )

        # Save state after action
        self.state_manager._save_to_db(player)

        # Check win/lose conditions
        if player.health <= 0:
            print(f"[GameLogic] Game Over - Player died on day {player.current_day}")
            player.game_active = False
            self.state_manager._save_to_db(player)
            return f"Game Over! You died on day {player.current_day}.\n{result}"
        elif player.current_day >= GameConfig.DAYS_TO_WIN:
            print(f"[GameLogic] Victory - Player survived {GameConfig.DAYS_TO_WIN} days")
            player.game_active = False
            self.state_manager._save_to_db(player)
            return f"Victory! You survived for {GameConfig.DAYS_TO_WIN} days!\n{result}"

        player.current_day += 1
        self.state_manager._save_to_db(player)
        print(f"[GameLogic] Saved game state for day {player.current_day}")

        # Generate next scenario
        try:
            print("[GameLogic] Generating next scenario")
            next_scenario = await self.scenario_generator.generate_scenario(
                player.username,
                player.current_day,
                player.location,
                player.difficulty,
                {
                    "health": player.health,
                    "food": player.food,
                    "water": player.water,
                    "weapons": player.weapons
                }
            )
            print(f"[GameLogic] Generated scenario: {next_scenario[:50]}...")
        except Exception as e:
            print(f"[GameLogic] Error generating scenario: {e}")
            next_scenario = "You continue your survival journey..."

        return f"{result}\n\n{next_scenario}"
