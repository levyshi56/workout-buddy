"""
Linq Webhook Receiver

POST /api/webhook/linq/
  - Parses inbound message from Linq
  - Validates webhook signature
  - Enqueues message for processing (responds 200 immediately)

GET /api/health/
  - Simple health check
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def linq_webhook(request):
    # Verify Linq webhook signature if secret is configured
    if settings.LINQ_WEBHOOK_SECRET:
        if not _verify_signature(request):
            logger.warning("Invalid webhook signature from %s", request.META.get("REMOTE_ADDR"))
            return JsonResponse({"error": "invalid signature"}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    # Only process inbound messages
    if body.get("event_type") != "message.received":
        return JsonResponse({"status": "ok", "note": "ignored event"})

    # Linq v3 payload shape
    data = body.get("data", {})
    sender = data.get("sender_handle", {})
    phone_number = sender.get("handle", "")
    chat_id = data.get("chat", {}).get("id", "")
    parts = data.get("parts", [])
    message_text = next((p.get("value", "") for p in parts if p.get("type") == "text"), "")

    if not phone_number:
        logger.warning("Webhook received with no phone_number: %s", body)
        return JsonResponse({"error": "missing phone_number"}, status=400)

    if not message_text:
        # Could be a media-only message — acknowledge but skip
        logger.info("Webhook received with no text body from %s", phone_number)
        return JsonResponse({"status": "ok", "note": "no text body"})

    logger.info("Inbound message from %s: %r", phone_number, message_text[:80])

    # Cache the Linq chat_id on the user for outbound replies
    if chat_id:
        try:
            from apps.users.service import get_or_create_user
            user = get_or_create_user(phone_number)
            if user.linq_chat_id != chat_id:
                user.linq_chat_id = chat_id
                user.save()
        except Exception as exc:
            logger.warning("Failed to save linq_chat_id for %s: %s", phone_number, exc)

    # Enqueue for debounced processing — return 200 immediately
    try:
        from apps.conversation.engine import ConversationEngine
        engine = ConversationEngine()
        engine.enqueue(phone_number, message_text)
    except Exception as exc:
        logger.error("Failed to enqueue message from %s: %s", phone_number, exc)
        # Still return 200 so Linq doesn't retry indefinitely
        return JsonResponse({"status": "error", "detail": str(exc)}, status=200)

    return JsonResponse({"status": "ok"})


@require_GET
def health_check(request):
    return JsonResponse({"status": "ok"})


def _verify_signature(request) -> bool:
    """
    Verify the HMAC-SHA256 signature Linq includes in the X-Linq-Signature header.
    """
    import base64

    # Log all headers so we can see exactly what Linq sends
    sig_headers = {k: v for k, v in request.META.items() if "LINQ" in k or "SIGNATURE" in k or "SECRET" in k}
    logger.info("Linq signature headers: %s", sig_headers)

    signature_header = request.META.get("HTTP_X_LINQ_SIGNATURE", "")
    if not signature_header:
        logger.warning("No X-Linq-Signature header found")
        return False

    secret = settings.LINQ_WEBHOOK_SECRET.encode()

    # Try base64-encoded HMAC-SHA256 (Linq uses this format)
    expected_b64 = base64.b64encode(hmac.new(secret, request.body, hashlib.sha256).digest()).decode()
    if hmac.compare_digest(expected_b64, signature_header):
        return True

    # Fallback: hex digest
    expected_hex = hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected_hex, signature_header):
        return True

    logger.warning("Signature mismatch. Header: %r, Expected b64: %r, Expected hex: %r", signature_header, expected_b64, expected_hex)
    return False
