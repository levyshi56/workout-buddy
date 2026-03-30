import logging
import time
import requests
from django.conf import settings
from .base import BaseMessagingClient

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0  # seconds


class LinqClient(BaseMessagingClient):
    """
    Sends messages via the Linq API (iMessage / RCS / SMS fallback).
    Docs: https://apidocs.linqapp.com/
    """

    def __init__(self):
        self.api_key = settings.LINQ_API_KEY
        self.base_url = settings.LINQ_BASE_URL.rstrip("/")

    def send_message(self, phone_number: str, text: str) -> bool:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "phone_number": phone_number,
            "body": text,
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code in (200, 201, 202):
                    return True
                if resp.status_code == 429:
                    # Rate limited — back off and retry
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
