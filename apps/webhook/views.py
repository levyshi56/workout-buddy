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

    # Linq payload shape (adjust to actual Linq webhook schema)
    phone_number = body.get("from") or body.get("sender") or body.get("phone_number", "")
    message_text = body.get("body") or body.get("text") or body.get("message", "")

    if not phone_number:
        logger.warning("Webhook received with no phone_number: %s", body)
        return JsonResponse({"error": "missing phone_number"}, status=400)

    if not message_text:
        # Could be a media-only message — acknowledge but skip
        logger.info("Webhook received with no text body from %s", phone_number)
        return JsonResponse({"status": "ok", "note": "no text body"})

    logger.info("Inbound message from %s: %r", phone_number, message_text[:80])

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
    Adjust header name / signing scheme to match actual Linq docs.
    """
    signature_header = request.META.get("HTTP_X_LINQ_SIGNATURE", "")
    if not signature_header:
        return False

    secret = settings.LINQ_WEBHOOK_SECRET.encode()
    expected = hmac.new(secret, request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
