"""Built-in demo posts and canned Jev answers for offline shadow runs."""
from __future__ import annotations

import json
from typing import Any

import httpx

DEMO_POSTS: list[dict[str, str]] = [
    {
        "id": "demo-ignore-1",
        "url": "https://x.com/random_user/status/1001",
        "author": "random_user",
        "text": "My cat just knocked over a plant and I cannot even.",
    },
    {
        "id": "demo-save-1",
        "url": "https://x.com/quant_research/status/1002",
        "author": "quant_research",
        "text": (
            "New paper on walk-forward backtesting for FX and XAUUSD. "
            "Code and tick data notes included."
        ),
    },
    {
        "id": "demo-research-1",
        "url": "https://x.com/alpha_claims/status/1003",
        "author": "alpha_claims",
        "text": (
            "Our US100 strategy printed 47% last month with a Sharpe of 4.1. "
            "Full equity curve in the thread."
        ),
    },
    {
        "id": "demo-reply-1",
        "url": "https://x.com/agent_builder/status/1004",
        "author": "agent_builder",
        "text": (
            "Been wiring Grok Bot with Jev as a System One gate so the agent "
            "classifies before any computer-use step."
        ),
    },
    {
        "id": "demo-scam-1",
        "url": "https://x.com/btc_double/status/1005",
        "author": "btc_double",
        "text": (
            "Send 0.2 BTC to this wallet and we send 0.4 BTC back. "
            "Limited giveaway for the first 50 people."
        ),
    },
    {
        "id": "demo-ad-1",
        "url": "https://x.com/fx_academy/status/1006",
        "author": "fx_academy",
        "text": (
            "Enroll in our $999 Forex signals membership. "
            "Guaranteed profits this week only."
        ),
    },
]

FOMO_DEMO_POSTS: list[dict[str, Any]] = [
    {
        "id": "demo-fomo-trap-1",
        "url": "https://x.com/stealth_degen/status/2001",
        "author": "stealth_degen",
        "fomo": True,
        "ca": "So1anaHoneypot111111111111111111111111111",
        "liq": "800",
        "deployer": "known_rug_wallet",
        "text": (
            "Stealth launch no socials. CA dropping now, ape this before the KOL call. "
            "Honeypot? nah trust me bro, 100x."
        ),
    },
    {
        "id": "demo-fomo-cluster-1",
        "url": "https://x.com/fomo_feed/status/2002",
        "author": "fomo_feed",
        "fomo": True,
        "cluster_hint": "one linked wallet island, 14 bundled snipers",
        "text": (
            "FOMO app just printed this memecoin. Copy-trade the bundle. "
            "Same cluster buying every call, you are late if you wait."
        ),
    },
    {
        "id": "demo-fomo-research-1",
        "url": "https://x.com/ca_watcher/status/2003",
        "author": "ca_watcher",
        "fomo": True,
        "ca": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "text": (
            "New CA on the FOMO feed. No obvious trap in the post. "
            "Check deployer, liq, and bubble map before anyone sizes."
        ),
    },
]


def mock_answers_for_post(post_id: str) -> dict[str, Any]:
    """Deterministic canned Jev answers for offline --demo / --mock-api."""
    catalog: dict[str, dict[str, Any]] = {
        "demo-ignore-1": _choice_pack(
            content="emotion_opinion",
            next_action="IGNORE",
            risk="low",
            relevance=0.08,
        ),
        "demo-save-1": _choice_pack(
            content="useful_information",
            next_action="SAVE",
            risk="low",
            relevance=0.96,
        ),
        "demo-research-1": _choice_pack(
            content="useful_information",
            next_action="RESEARCH",
            risk="medium",
            relevance=0.91,
        ),
        "demo-reply-1": _choice_pack(
            content="useful_information",
            next_action="PREPARE_REPLY",
            risk="low",
            relevance=0.97,
        ),
        "demo-scam-1": _choice_pack(
            content="possible_scam",
            next_action="PREPARE_REPLY",
            risk="high",
            relevance=0.4,
        ),
        "demo-ad-1": _choice_pack(
            content="advertisement",
            next_action="IGNORE",
            risk="medium",
            relevance=0.35,
            next_confidence=0.5,
        ),
        "demo-fomo-trap-1": _fomo_case(
            content="advertisement",
            next_action="PREPARE_REPLY",
            risk="medium",
            relevance=0.7,
            is_fomo=0.96,
            cluster=0.4,
            trap=0.97,
            kol=0.88,
            farm="high",
            fomo_next="SKIP",
        ),
        "demo-fomo-cluster-1": _fomo_case(
            content="advertisement",
            next_action="PREPARE_REPLY",
            risk="medium",
            relevance=0.55,
            is_fomo=0.94,
            cluster=0.93,
            trap=0.12,
            kol=0.35,
            farm="medium",
            fomo_next="WATCH_CLUSTER",
        ),
        "demo-fomo-research-1": _fomo_case(
            content="useful_information",
            next_action="RESEARCH",
            risk="low",
            relevance=0.8,
            is_fomo=0.9,
            cluster=0.2,
            trap=0.08,
            kol=0.1,
            farm="low",
            fomo_next="RESEARCH_CA",
        ),
    }
    return catalog.get(post_id, _choice_pack("emotion_opinion", "IGNORE", "low", 0.2))


def _choice_pack(
    content: str,
    next_action: str,
    risk: str,
    relevance: float,
    *,
    next_confidence: float = 0.94,
    content_confidence: float = 0.94,
    risk_confidence: float = 0.93,
) -> dict[str, Any]:
    risk_index = {"low": 0, "medium": 1, "high": 2}[risk]
    content_probs = {
        "useful_information": 0.02,
        "emotion_opinion": 0.02,
        "advertisement": 0.02,
        "possible_scam": 0.02,
    }
    content_probs[content] = 0.94
    next_probs = {
        "IGNORE": 0.02,
        "SAVE": 0.02,
        "RESEARCH": 0.02,
        "PREPARE_REPLY": 0.02,
    }
    next_probs[next_action] = max(next_confidence, 0.5)
    risk_probs = {"0": 0.02, "1": 0.02, "2": 0.02}
    risk_probs[str(risk_index)] = 0.94
    return {
        "content_type": {
            "type": "choice",
            "choice": content,
            "confidence": content_confidence,
            "probabilities": content_probs,
        },
        "relevance": {"type": "noul", "noul": relevance},
        "interaction_risk": {
            "type": "score",
            "score": float(risk_index),
            "confidence": risk_confidence,
            "legend": {"0": "low", "1": "medium", "2": "high"},
            "probabilities": risk_probs,
        },
        "next_action": {
            "type": "choice",
            "choice": next_action,
            "confidence": next_confidence,
            "probabilities": next_probs,
        },
    }


def _quiet_fomo_answers() -> dict[str, Any]:
    """Low FOMO signals so non-FOMO demo posts keep their base routes."""
    return _fomo_answers(
        is_fomo=0.05,
        cluster=0.04,
        trap=0.03,
        kol=0.04,
        farm="low",
        fomo_next="SKIP",
    )


def _fomo_answers(
    *,
    is_fomo: float,
    cluster: float,
    trap: float,
    kol: float,
    farm: str,
    fomo_next: str,
    farm_confidence: float = 0.93,
    fomo_next_confidence: float = 0.94,
) -> dict[str, Any]:
    farm_index = {"low": 0, "medium": 1, "high": 2}[farm]
    farm_probs = {"0": 0.02, "1": 0.02, "2": 0.02}
    farm_probs[str(farm_index)] = 0.94
    next_probs = {
        "SKIP": 0.02,
        "WATCH_CLUSTER": 0.02,
        "RESEARCH_CA": 0.02,
        "PREPARE_NOTE": 0.02,
    }
    next_probs[fomo_next] = max(fomo_next_confidence, 0.5)
    return {
        "is_fomo_call": {"type": "noul", "noul": is_fomo},
        "bundled_or_cluster_risk": {"type": "noul", "noul": cluster},
        "trap_flags": {"type": "noul", "noul": trap},
        "kol_farm_pattern": {"type": "noul", "noul": kol},
        "farm_risk": {
            "type": "score",
            "score": float(farm_index),
            "confidence": farm_confidence,
            "legend": {"0": "low", "1": "medium", "2": "high"},
            "probabilities": farm_probs,
        },
        "fomo_next": {
            "type": "choice",
            "choice": fomo_next,
            "confidence": fomo_next_confidence,
            "probabilities": next_probs,
        },
    }


def _fomo_case(
    *,
    content: str,
    next_action: str,
    risk: str,
    relevance: float,
    is_fomo: float,
    cluster: float,
    trap: float,
    kol: float,
    farm: str,
    fomo_next: str,
) -> dict[str, Any]:
    packed = _choice_pack(content, next_action, risk, relevance)
    packed.update(
        _fomo_answers(
            is_fomo=is_fomo,
            cluster=cluster,
            trap=trap,
            kol=kol,
            farm=farm,
            fomo_next=fomo_next,
        )
    )
    return packed


def build_mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        try:
            payload = json.loads(request.content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return httpx.Response(400, json={"error": "invalid json"})
        state = payload.get("state") or {}
        questions = payload.get("questions") or {}
        post_id = str(state.get("post_id") or "")
        answers = mock_answers_for_post(post_id)
        if "is_fomo_call" in questions and "is_fomo_call" not in answers:
            answers = dict(answers)
            answers.update(_quiet_fomo_answers())
        requested = {name: answers[name] for name in questions if name in answers}
        if not requested:
            requested = answers
        body = {
            "model": payload.get("model") or "jev-latest",
            "answers": requested,
            "usage": {"input_tokens": 42, "output_tokens": 8},
        }
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)
