from abc import ABC, abstractmethod


class BaseMessagingClient(ABC):
    """Abstract messaging interface. Swap out for Telegram, WhatsApp, etc."""

    @abstractmethod
    def send_message(self, phone_number: str, text: str) -> bool:
        """Send a text message to the given phone number. Returns True on success."""
        ...
