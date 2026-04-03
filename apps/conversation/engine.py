"""
Conversation Engine — the core orchestrator.

Message flow per inbound text:
1. Load user from MongoDB
2. Update last_user_message_at (guard for rest timer race)
3. Revoke any pending rest timer task (user is actively texting)
4. Debounce: revoke previous debounce task, enqueue new one with 2s delay
   → Actual LLM processing happens in tasks.rest_timer.process_debounced_message
5. Return immediately (webhook responds 200 fast)

The debounced task calls _run() which does:
1. Acquire per-user Redis lock (prevent concurrent processing, TDD constraint #4)
2. Build LLM context
3. Call LLM with timeout guard (TDD constraint #5)
4. Dispatch structured action
5. Send reply via Linq
6. Release lock
"""
import logging
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 2
_LOCK_TIMEOUT = 30  # seconds
_RESET_KEYWORDS = {"nevins"}


class ConversationEngine:

    def enqueue(self, phone_number: str, message: str) -> None:
        """
        Called by the webhook. Debounces the message and enqueues
        process_debounced_message after 2s. Revokes the previous
        debounce task if one is pending.
        """
        if message.strip().lower() in _RESET_KEYWORDS:
            self._handle_reset(phone_number)
            return

        from apps.users.service import get_or_create_user, update_last_message_time
        from tasks.rest_timer import process_debounced_message

        user = get_or_create_user(phone_number)
        update_last_message_time(user)
        user.reload()  # refresh after update

        # Revoke any pending rest timer so we don't double-send
        self._revoke_rest_timer(user)

        # Debounce: revoke previous debounce task, re-enqueue with fresh 2s window
        self._revoke_debounce_task(user)

        task = process_debounced_message.apply_async(
            args=[phone_number, message],
            countdown=_DEBOUNCE_SECONDS,
        )

        if user.active_session is None:
            from apps.users.models import ActiveSession
            user.active_session = ActiveSession()

        user.active_session.debounce_task_id = task.id
        user.save()

    def process(self, phone_number: str, message: str) -> None:
        """
        Called by the debounced Celery task. Acquires a per-user lock,
        runs the full LLM loop, and sends the reply.
        """
        lock_key = f"conv_lock:{phone_number}"
        lock = self._get_redis_lock(lock_key)

        if not lock.acquire(blocking=True, blocking_timeout=_LOCK_TIMEOUT):
            logger.warning("Could not acquire lock for %s, dropping message", phone_number)
            return

        try:
            self._run(phone_number, message)
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _run(self, phone_number: str, message: str) -> None:
        from apps.users.service import get_or_create_user
        from apps.conversation.skills import TOOL_DEFINITIONS
        from apps.llm.openai_provider import get_provider, SYSTEM_PROMPT
        from apps.messaging.linq_client import get_client

        user = get_or_create_user(phone_number)

        # Save inbound user message
        user.add_message("user", message)
        user.save()

        # Build messages: system prompt + conversation history
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in user.conversation_history:
            messages.append({"role": msg.role, "content": msg.content})

        # Run the tool-use loop
        provider = get_provider()
        reply_text = provider.run_coach_loop(user, messages, TOOL_DEFINITIONS)

        # Send the coach's reply
        client = get_client()
        client.send_message(phone_number, reply_text)

        # Save outbound bot reply to history
        user.reload()
        user.add_message("assistant", reply_text)
        user.save()

    def _handle_reset(self, phone_number: str) -> None:
        """Delete the user's profile entirely so the next message starts fresh."""
        from apps.users.service import get_or_create_user
        from apps.messaging.linq_client import get_client

        user = get_or_create_user(phone_number)
        self._revoke_rest_timer(user)
        self._revoke_debounce_task(user)
        user.delete()

        client = get_client()
        client.send_message(phone_number, "All clear! I've forgotten everything. Text me when you're ready to start fresh.")
        logger.info("full reset: deleted profile for %s", phone_number)

    def _revoke_rest_timer(self, user) -> None:
        if user.active_session and user.active_session.rest_timer_task_id:
            task_id = user.active_session.rest_timer_task_id
            try:
                from workout_buddy.celery import app as celery_app
                celery_app.control.revoke(task_id, terminate=True)
                logger.info("revoked rest timer task %s", task_id)
            except Exception as exc:
                logger.warning("failed to revoke rest timer %s: %s", task_id, exc)
            user.active_session.rest_timer_task_id = ""
            user.save()

    def _revoke_debounce_task(self, user) -> None:
        if user.active_session and user.active_session.debounce_task_id:
            task_id = user.active_session.debounce_task_id
            try:
                from workout_buddy.celery import app as celery_app
                celery_app.control.revoke(task_id, terminate=True)
            except Exception:
                pass
            user.active_session.debounce_task_id = ""
            user.save()

    def _get_redis_lock(self, lock_key: str):
        """Returns a Redis lock object for per-user serialization."""
        import redis
        redis_client = redis.from_url(settings.REDIS_URL)
        return redis_client.lock(lock_key, timeout=_LOCK_TIMEOUT)
