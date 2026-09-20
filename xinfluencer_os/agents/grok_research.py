"""
Grok Bot research stub.

When Jev routes RESEARCH, the orchestrator flags the post for a later Grok Bot
research pass. This stub does not call Perplexity, X, or any other network
service. `--run-research` still stays local: it only marks the ticket as
explicitly requested.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def flag_for_grok_research(
    post: dict[str, Any],
    *,
    run: bool = False,
    reason: str = "Jev recommended RESEARCH",
) -> dict[str, Any]:
    """Flag a post for Grok Bot research. No external services are called."""
    ticket = {
        "post_id": post.get("id") or post.get("post_id"),
        "url": post.get("url", ""),
        "reason": reason,
        "status": "queued_local" if run else "logged_only",
        "ran": bool(run),
        "external_calls": False,
        "note": (
            "Local research ticket only. On-chain checks (bubblemaps, liq, deployer, "
            "cluster) stay with Grok Bot or a human. Pass --run-research to mark as "
            "queued; this still does not call Grok, Perplexity, X, or any wallet."
        ),
    }
    logger.info(
        "Grok research stub: post_id=%s status=%s run=%s",
        ticket["post_id"],
        ticket["status"],
        run,
    )
    return ticket
