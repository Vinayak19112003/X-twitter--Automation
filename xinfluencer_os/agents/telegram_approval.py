"""
Telegram approval stub.

Prepared public actions (draft replies, later bookmarks, etc.) are meant to go
to Telegram for a human to approve before any X mutation.

This module is log-only. It does not send Telegram messages. A future
implementation can replace `queue_for_approval` with a live Bot API call
without changing the Jev gate.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def queue_for_approval(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a prepared action for later human approval.

    Returns a receipt. Never posts to X and never sends Telegram.
    """
    receipt = {
        "channel": "telegram_stub",
        "status": "queued_locally",
        "live_send": False,
        "payload_keys": sorted(payload.keys()),
    }
    logger.info(
        "Telegram approval stub queued payload (live_send=false): %s",
        json.dumps(receipt, sort_keys=True),
    )
    return receipt
