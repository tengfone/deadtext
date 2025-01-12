import os
import json
import httpx
import logging
import asyncio
import random
from typing import Dict, Optional, List
from telegram import Message


class LLMHandler:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set")

        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/tengfone/deadtext",
            "Content-Type": "application/json",
        }

        # Setup logging
        self.logger = logging.getLogger("DeadText.LLM")

        # Loading animation settings
        self.loading_delay = 0.8  # seconds between loading messages
        self.current_loading_message = None

    async def _show_loading_states(self, message: Message, loading_messages: List[str]):
        """Show loading messages while waiting for LLM response."""
        if not message or not loading_messages:
            return

        try:
            # Send as new message instead of editing
            self.current_loading_message = await message.reply_text(
                "🤖 *Processing...*\n\n" + loading_messages[0], parse_mode="Markdown"
            )
            current_index = 0

            while self.current_loading_message and current_index < len(
                loading_messages
            ):
                try:
                    current_index = (current_index + 1) % len(loading_messages)
                    await asyncio.sleep(self.loading_delay)
                    await self.current_loading_message.edit_text(
                        "🤖 *Processing...*\n\n" + loading_messages[current_index],
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    self.logger.warning(f"Could not update loading message: {str(e)}")
                    break

        except Exception as e:
            self.logger.error(f"Error showing loading states: {str(e)}")

    async def _cleanup_loading(self):
        """Clean up loading message."""
        if self.current_loading_message:
            try:
                await self.current_loading_message.delete()
            except Exception as e:
                self.logger.warning(f"Could not delete loading message: {str(e)}")
            finally:
                self.current_loading_message = None

    async def generate_response(
        self,
        prompt: str,
        context: Dict = None,
        max_tokens: int = 1000,
        loading_messages: List[str] = None,
        message: Message = None,
    ) -> str:
        """Generate a response using OpenRouter API."""
        loading_task = None
        try:
            # Start loading animation if message and loading_messages provided
            if message and loading_messages:
                loading_task = asyncio.create_task(
                    self._show_loading_states(message, loading_messages)
                )

            # Construct the message with context if provided
            messages = []
            if context:
                messages.append(
                    {
                        "role": "system",
                        "content": f"Current game state: {json.dumps(context)}",
                    }
                )
            messages.append({"role": "user", "content": prompt})

            # Prepare the request
            data = {
                "model": "mistralai/mistral-nemo",
                "messages": messages,
                "max_tokens": max_tokens,
                "response_format": (
                    {"type": "json_object"}
                    if prompt.endswith(
                        "return ONLY the JSON object, no additional text."
                    )
                    else None
                ),
            }

            # Remove None values from data
            data = {k: v for k, v in data.items() if v is not None}

            # Make the API call
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    self.logger.error(f"OpenRouter API error: {response.text}")
                    return None

                result = response.json()
                return result["choices"][0]["message"]["content"]

        except Exception as e:
            self.logger.error(f"Error generating LLM response: {str(e)}")
            return None
        finally:
            # Clean up loading message
            if loading_task:
                loading_task.cancel()
            await self._cleanup_loading()

    async def generate_scenario(
        self, context: Dict, loading_messages: List[str] = None, message: Message = None
    ) -> Optional[str]:
        """Generate a game scenario based on context."""
        # Format inventory for display
        inventory_items = []
        if context.get("inventory"):
            for item, quantity in context["inventory"].items():
                if quantity > 0:
                    inventory_items.append(f"{item}: {quantity}")

        prompt = f"""You are generating a scenario for a text-based zombie survival game. You MUST format your response using Markdown and EXACTLY as shown below, with section headers in square brackets.

Current context:
- Day: {context.get('day', 1)}
- Location: {context.get('location', 'unknown')}
- Player Health: {context.get('health', 100)}
- Resources: Food ({context.get('food', 0)}), Water ({context.get('water', 0)})
- Weapons: {', '.join(context.get('weapons', []))}
- Inventory: {', '.join(inventory_items) if inventory_items else 'Empty'}

Generate a response with EXACTLY these sections and formatting:

[ATMOSPHERE]
Write 2-3 sentences setting the mood and describing the environment. Focus on creating tension and atmosphere. Use *bold* for important elements.

[SITUATION]
Write 2-3 sentences describing the immediate challenge or opportunity the player faces. Make it specific and actionable. Use *bold* for key threats or opportunities.

[CHOICES]
1. (Safe) - Write a low-risk option with modest rewards
2. (Risky) - Write a medium-risk option with good rewards
3. (Desperate) - Write a high-risk option with the best rewards

Keep each section concise but immersive. Focus on survival and resource management.
DO NOT add any additional sections or change the formatting.
IMPORTANT: Make sure to use proper Markdown formatting with *asterisks* for bold text."""

        response = await self.generate_response(
            prompt, context, loading_messages=loading_messages, message=message
        )

        # Ensure proper markdown formatting
        if response:
            # Add bold formatting to section headers
            response = response.replace("[ATMOSPHERE]", "*[ATMOSPHERE]*")
            response = response.replace("[SITUATION]", "*[SITUATION]*")
            response = response.replace("[CHOICES]", "*[CHOICES]*")

            # Ensure proper line breaks
            response = response.replace("\n\n\n", "\n\n")

        return response

    async def process_action(
        self,
        action: str,
        context: Dict,
        loading_messages: List[str] = None,
        message: Message = None,
    ) -> Optional[Dict]:
        """Process a player's action and generate consequences."""
        prompt = f"""You are analyzing a player's action in a zombie survival game. Return a JSON object with the following structure:
{{
    "action_type": "COMBAT" | "STEALTH" | "EXPLORE" | "REST" | "MOVE",
    "description": "brief description of interpreted action",
    "consequences": ["list", "of", "potential", "outcomes"],
    "risk_level": number between 1-10,
    "resource_impacts": {{
        "health": number between -100 and 100,
        "food": number between -10 and 10,
        "water": number between -10 and 10
    }}
}}

Player's action: "{action}"

Current context:
- Health: {context.get('health', 100)}
- Location: {context.get('location', 'unknown')}
- Available weapons: {', '.join(context.get('weapons', []))}
- Food: {context.get('food', 0)}
- Water: {context.get('water', 0)}

Return ONLY the JSON object, no additional text."""

        try:
            # Set response_format directly in data
            data = {
                "model": "mistralai/mistral-nemo",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 1000,
            }

            # Log the request data
            # self.logger.info(f"Sending request to OpenRouter API with data: {json.dumps(data, indent=2)}")

            # Make the API call directly
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=data,
                    timeout=30.0,
                )

                if response.status_code != 200:
                    self.logger.error(f"OpenRouter API error: {response.text}")
                    return None

                result = response.json()
                # Log the full API response
                # self.logger.info(f"OpenRouter API response: {json.dumps(result, indent=2)}")

                response_text = result["choices"][0]["message"]["content"]
                # Log the extracted content
                # self.logger.info(f"Extracted content: {response_text}")

                try:
                    # Parse the response as JSON
                    action_result = json.loads(response_text)
                    # Log the parsed result
                    # self.logger.info(f"Parsed JSON result: {json.dumps(action_result, indent=2)}")

                    # Validate required fields
                    required_fields = [
                        "action_type",
                        "description",
                        "consequences",
                        "risk_level",
                        "resource_impacts",
                    ]
                    if all(field in action_result for field in required_fields):
                        return action_result
                    else:
                        missing = [f for f in required_fields if f not in action_result]
                        self.logger.error(
                            f"Missing required fields in response: {missing}"
                        )
                        return None
                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"JSON parse error: {str(e)}\nResponse was: {response_text}"
                    )
                    return None

        except Exception as e:
            self.logger.error(f"Error in process_action: {str(e)}")
            self.logger.exception("Full traceback:")
            return None
