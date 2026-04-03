from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """
    Abstract LLM interface. Swap OpenAI for Claude, Gemini, etc.
    by implementing a new provider.
    """

    @abstractmethod
    def run_coach_loop(self, user, messages: list[dict], tools: list[dict]) -> str:
        """
        Run the tool-use loop until the model produces a final text response.
        Executes tool calls against the user object as they come in.
        Returns the final text message string to send to the user.
        """
        ...
