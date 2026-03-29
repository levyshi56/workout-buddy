import logging
import time
import requests
from django.conf import settings
from .base import BaseMessagingClient

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0  # seconds

# Linq Partner API v3 base path
_API_PATH = "/api/partner/v3"


class LinqClient(BaseMessagingClient):
    """
    Sends messages via the Linq Partner API v3 (iMessage / RCS / SMS fallback).
    Docs: https://linqapp.com
    """

    def __init__(self):
        self.api_key = settings.LINQ_API_KEY
        self.base_url = settings.LINQ_BASE_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def send_message(self, phone_number: str, text: str) -> bool:
        """
        Send a text message to the given phone number via Linq v3.
        Looks up the cached chat_id from the user profile; creates a new
        chat if none exists.
        """
        chat_id = self._get_chat_id(phone_number)

        if not chat_id:
            chat_id = self._create_chat(phone_number)
            if not chat_id:
                return False

        return self._send_to_chat(chat_id, text)

    def _get_chat_id(self, phone_number: str) -> str:
        """Look up the cached Linq chat_id from MongoDB."""
        try:
            from apps.users.service import get_or_create_user
            user = get_or_create_user(phone_number)
            return user.linq_chat_id or ""
        except Exception as exc:
            logger.warning("Failed to look up chat_id for %s: %s", phone_number, exc)
            return ""

    def _create_chat(self, phone_number: str) -> str:
        """Create a new Linq chat and cache the chat_id on the user."""
        url = f"{self.base_url}{_API_PATH}/chats"
        payload = {
            "from": settings.LINQ_FROM_NUMBER,
            "to": [phone_number],
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=10)
            if resp.status_code in (200, 201):
                data = resp.json()
                chat_id = data.get("chat", {}).get("id", "")
                if chat_id:
                    # Cache on user
                    try:
                        from apps.users.service import get_or_create_user
                        user = get_or_create_user(phone_number)
                        user.linq_chat_id = chat_id
                        user.save()
                    except Exception:
                        pass
                    return chat_id
            logger.error("Linq create chat failed: %d %s", resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            logger.error("Linq create chat error: %s", exc)

        return ""

    def _send_to_chat(self, chat_id: str, text: str) -> bool:
        """Send a message to an existing Linq chat."""
        url = f"{self.base_url}{_API_PATH}/chats/{chat_id}/messages"
        payload = {
            "message": {
                "parts": [{"type": "text", "value": text}],
            }
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, headers=self._headers, timeout=10)
                if resp.status_code in (200, 201, 202):
                    return True
                if resp.status_code == 429:
                    logger.warning("Linq rate limited (attempt %d/%d)", attempt, _MAX_RETRIES)
                    time.sleep(_RETRY_BACKOFF * attempt)
                    continue
                logger.error(
                    "Linq send failed: %d %s", resp.status_code, resp.text[:200]
                )
                return False
            except requests.RequestException as exc:
                logger.error("Linq request error (attempt %d/%d): %s", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF * attempt)

        return False


# Module-level singleton
_client: LinqClient | None = None


def get_client() -> LinqClient:
    global _client
    if _client is None:
        _client = LinqClient()
    return _client
