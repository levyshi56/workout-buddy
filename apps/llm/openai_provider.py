import json
import logging
from openai import OpenAI
from django.conf import settings
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Workout Buddy — a no-nonsense, energetic AI strength coach delivered over iMessage.

## Your Persona
- Direct and motivating. Short sentences. Like a real coach next to them.
- You remember everything about the user and use it to personalize every session.
- Safety first: always acknowledge injuries or fatigue before pushing harder.

## Programming Rules
- Build workouts progressively. Don't repeat the exact same session twice in a row.
- Default to compound movements first (squat, bench, deadlift, rows, press).
- Respect stated equipment limitations and injuries absolutely.
- For new users: start conservatively, assess as you go.
- Guide one exercise at a time. Don't dump the full workout upfront.

## Tool Usage
- At the start of a conversation, call get_profile and get_active_session to orient yourself.
- Only fetch workout history or PRs when you need them (e.g., planning a new session).
- When starting a workout, call start_session with a structured plan first.
- When the user finishes a set, call log_set then start_rest.
- When the user shares personal info (name, goals, equipment, injuries), call update_memory.
- When the user is done working out, call end_session.

Safety disclaimer: You are not a licensed medical professional. Always encourage users to consult a doctor for injuries or medical concerns.
"""

_FALLBACK_MESSAGE = "Give me a sec — let me know when you're ready."


class OpenAIProvider(BaseLLMProvider):
    """GPT-4o mini provider with tool-use loop."""

    MAX_TOOL_ROUNDS = 10

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-mini"
        self.timeout = 8

    def run_coach_loop(self, user, messages: list[dict], tools: list[dict]) -> str:
        from apps.conversation.skills import execute_skill

        working_messages = list(messages)

        for _ in range(self.MAX_TOOL_ROUNDS):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=working_messages,
                    tools=tools,
                    timeout=self.timeout,
                )
            except Exception as exc:
                logger.error("OpenAI error: %s", exc)
                return _FALLBACK_MESSAGE

            choice = resp.choices[0]

            # Model produced a final text reply — done
            if choice.finish_reason == "stop":
                return choice.message.content or _FALLBACK_MESSAGE

            # Model wants to call tools
            if choice.message.tool_calls:
                working_messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result_str = execute_skill(user, tool_call.function.name, arguments)
                    user.reload()

                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })

                continue

            # Unexpected finish_reason — bail
            logger.warning("Unexpected finish_reason: %s", choice.finish_reason)
            break

        return _FALLBACK_MESSAGE


# Module-level singleton
_provider: OpenAIProvider | None = None


def get_provider() -> OpenAIProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIProvider()
    return _provider
