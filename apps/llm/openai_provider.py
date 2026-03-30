import json
import logging
from openai import OpenAI
from django.conf import settings
from .base import BaseLLMProvider, CoachResponse

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

## Response Format
You MUST always respond with valid JSON in this exact schema:
{
  "message": "<text to send to the user>",
  "action": {
    "type": "<action_type>",
    "params": {}
  }
}

Action types:
- "start_rest"     → params: {"seconds": 90}
- "advance_set"    → params: {}
- "log_weight"     → params: {"exercise": "Bench Press", "reps": 8, "weight": 185}
- "end_session"    → params: {"duration_minutes": 45, "summary": "..."}
- "update_memory"  → params: {"field": "injuries", "value": "tweaky left shoulder"}
- "none"           → params: {}

If no structured action is needed (e.g. casual question, onboarding chat), use "none".
If the user just finished a set, use "log_weight" then "start_rest".
If it's the final set of the session, use "end_session".

Safety disclaimer: You are not a licensed medical professional. Always encourage users to consult a doctor for injuries or medical concerns.
"""


class OpenAIProvider(BaseLLMProvider):
    """GPT-4o mini provider with structured JSON output."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-mini"
        self.timeout = 5  # seconds — hard timeout to keep responses conversational

    def get_coach_response(self, context: dict, message: str) -> CoachResponse:
        user_context_block = self._build_context_block(context)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_context_block},
        ]

        # Inject conversation history as proper role-based messages
        for hist_msg in context.get("conversation_history", []):
            messages.append({
                "role": hist_msg["role"],
                "content": hist_msg["content"],
            })

        # Current user message last
        messages.append({"role": "user", "content": f"User message: {message}"})

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=self.timeout,
            )
            raw = resp.choices[0].message.content
            parsed = json.loads(raw)
            return self._validate_response(parsed)
        except TimeoutError:
            logger.error("OpenAI timeout")
            return self._fallback_response()
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("OpenAI malformed response: %s", exc)
            # Retry once with explicit format reminder
            return self._retry_once(messages) or self._fallback_response()
        except Exception as exc:
            logger.error("OpenAI error: %s", exc)
            return self._fallback_response()

    def _build_context_block(self, context: dict) -> str:
        parts = ["## User Context"]
        if context.get("memory"):
            parts.append(f"### Memory\n{context['memory']}")
        if context.get("recent_sessions"):
            parts.append(f"### Recent Sessions\n{context['recent_sessions']}")
        if context.get("active_session"):
            parts.append(f"### Active Session\n{json.dumps(context['active_session'], indent=2)}")
        return "\n\n".join(parts)

    def _validate_response(self, parsed: dict) -> CoachResponse:
        message = parsed.get("message", "")
        action = parsed.get("action", {})
        if not isinstance(action, dict) or "type" not in action:
            action = {"type": "none", "params": {}}
        if "params" not in action:
            action["params"] = {}
        return CoachResponse(message=message, action=action)

    def _retry_once(self, messages: list) -> CoachResponse | None:
        """Retry with an explicit reminder to return valid JSON."""
        try:
            messages = messages + [
                {
                    "role": "user",
                    "content": 'Your last response was not valid JSON. Please respond ONLY with valid JSON matching the required schema.',
                }
            ]
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=self.timeout,
            )
            raw = resp.choices[0].message.content
            parsed = json.loads(raw)
            return self._validate_response(parsed)
        except Exception:
            return None

    @staticmethod
    def _fallback_response() -> CoachResponse:
        return CoachResponse(
            message="Give me a sec — let me know when you're ready.",
            action={"type": "none", "params": {}},
        )


# Module-level singleton
_provider: OpenAIProvider | None = None


def get_provider() -> OpenAIProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIProvider()
    return _provider
