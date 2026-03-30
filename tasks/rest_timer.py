"""
Rest timer Celery tasks.

When the LLM prescribes a rest period, the conversation engine enqueues
send_rest_over with a countdown. If the user replies before it fires, the
engine revokes the task so we don't double-message.

Race condition guard (TDD constraint #1):
Before sending, we compare the timer's enqueue time with
last_user_message_at on the active session. If the user messaged after
we enqueued the timer, we skip the message.
"""
import logging
from datetime import datetime, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def send_rest_over(self, phone_number: str, enqueued_at_iso: str):
    """
    Fires after the rest period. Sends a follow-up prompt if the user
    hasn't already replied since the timer was enqueued.
    """
    # Import here to avoid circular imports at module load time
    from apps.users.service import get_or_create_user
    from apps.messaging.linq_client import get_client

    enqueued_at = datetime.fromisoformat(enqueued_at_iso).replace(tzinfo=timezone.utc)

    user = get_or_create_user(phone_number)
    if not user.active_session:
        logger.info("rest_timer: no active session for %s, skipping", phone_number)
        return

    last_msg = user.active_session.last_user_message_at
    if last_msg and last_msg.replace(tzinfo=timezone.utc) > enqueued_at:
        logger.info(
            "rest_timer: user %s replied after timer was set, skipping rest-over message",
            phone_number,
        )
        return

    rest_message = "Rest's up. Ready for the next set?"
    user.add_message("assistant", rest_message)
    user.save()

    client = get_client()
    client.send_message(phone_number, rest_message)


@shared_task(bind=True, max_retries=0)
def process_debounced_message(self, phone_number: str, message: str):
    """
    Processes a user message after the debounce window (2s).
    The conversation engine enqueues this instead of processing inline,
    so rapid back-to-back messages get collapsed into one LLM call.
    """
    from apps.conversation.engine import ConversationEngine

    engine = ConversationEngine()
    engine.process(phone_number, message)
