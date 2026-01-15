"""Webhook delivery service."""

import hashlib
import hmac
import json
import logging
import threading
from typing import Optional

import requests
from django.utils import timezone

from accounts.models import APIKey

logger = logging.getLogger(__name__)


def trigger_webhook(
    api_key: APIKey,
    event: str,
    path: str,
    extra_data: Optional[dict] = None
) -> None:
    """
    Trigger webhook for an API key (non-blocking).

    Args:
        api_key: The APIKey instance with webhook config (may be None for session auth)
        event: Event type (file.created, file.updated, etc.)
        path: File path that changed
        extra_data: Optional additional payload data
    """
    # Guard against None (session auth has no API key)
    if not api_key:
        return

    if not api_key.webhook_url or not api_key.webhook_enabled:
        return

    # Fire and forget in background thread
    thread = threading.Thread(
        target=_deliver_webhook,
        args=(api_key.id, event, path, extra_data),
        daemon=True,
    )
    thread.start()


def _deliver_webhook(
    api_key_id: str,
    event: str,
    path: str,
    extra_data: Optional[dict] = None
) -> None:
    """
    Actually deliver the webhook (runs in background thread).

    Fetches fresh APIKey to avoid stale data and thread safety.
    """
    try:
        api_key = APIKey.objects.get(id=api_key_id)
    except APIKey.DoesNotExist:
        logger.warning(f"Webhook delivery failed: APIKey {api_key_id} not found")
        return

    if not api_key.webhook_url or not api_key.webhook_enabled:
        return

    # Build payload
    payload = {
        "event": event,
        "path": path,
        "timestamp": timezone.now().isoformat(),
        "api_key_id": str(api_key.id),
    }
    if extra_data:
        payload.update(extra_data)

    # Sign payload
    payload_bytes = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(
        api_key.webhook_secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Storm-Signature": signature,
        "X-Storm-Event": event,
    }

    try:
        response = requests.post(
            api_key.webhook_url,
            data=payload_bytes,  # Use exact bytes we signed, not re-serialized
            headers=headers,
            timeout=10,
        )

        api_key.webhook_last_triggered = timezone.now()
        api_key.webhook_last_status = "success" if response.ok else "failed"
        api_key.save(update_fields=["webhook_last_triggered", "webhook_last_status"])

        if response.ok:
            logger.debug(f"Webhook delivered: {event} {path} -> {api_key.webhook_url}")
        else:
            logger.warning(
                f"Webhook failed: {event} {path} -> {api_key.webhook_url} "
                f"(status {response.status_code})"
            )

    except requests.Timeout:
        api_key.webhook_last_triggered = timezone.now()
        api_key.webhook_last_status = "timeout"
        api_key.save(update_fields=["webhook_last_triggered", "webhook_last_status"])
        logger.warning(f"Webhook timeout: {event} {path} -> {api_key.webhook_url}")

    except requests.RequestException as e:
        api_key.webhook_last_triggered = timezone.now()
        api_key.webhook_last_status = "failed"
        api_key.save(update_fields=["webhook_last_triggered", "webhook_last_status"])
        logger.warning(f"Webhook error: {event} {path} -> {api_key.webhook_url}: {e}")
