from abc import ABC, abstractmethod
from typing import TypedDict, Any


class CoachAction(TypedDict):
    type: str   # start_rest | advance_set | log_weight | end_session | update_memory | none
    params: dict[str, Any]


class CoachResponse(TypedDict):
    message: str
    action: CoachAction


class BaseLLMProvider(ABC):
    """
    Abstract LLM interface. Swap OpenAI for Claude, Gemini, etc.
    by implementing a new provider.
    """

    @abstractmethod
    def get_coach_response(self, context: dict, message: str) -> CoachResponse:
        """
        Given a context dict (user memory, session state, history)
        and the user's latest message, return a CoachResponse with:
          - message: text to send back to the user
          - action: structured action for the engine to dispatch
        """
        ...
