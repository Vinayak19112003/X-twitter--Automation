"""
Maran-inspired FOMO-app kill rules for the Jev decision gate.

Thesis: FOMO (the app/feed) prints calls, retail apes late, KOLs/insiders farm
them. These questions are filters before sizing. Jev classifies; a human sizes;
the agent never buys and never performs X write actions.

On-chain checks (bubblemaps, liquidity, deployer) remain Grok Bot / human steps
after RESEARCH_CA or WATCH_CLUSTER. Jev only classifies.
"""
from __future__ import annotations

import re
from typing import Any

FOMO_NOUL_DEFAULT = 0.7

FOMO_NEXT_CRITERIA = {
    "SKIP": "Ignore / do not engage",
    "WATCH_CLUSTER": "Wait for multi-wallet cluster confirm before any size",
    "RESEARCH_CA": "Verify CA, deployer, liq, bubble map before acting",
    "PREPARE_NOTE": "Draft a human research note only (never a buy)",
}

FOMO_FARM_RISK_CRITERIA = ["low", "medium", "high"]

FOMO_QUESTION_NAMES = (
    "is_fomo_call",
    "bundled_or_cluster_risk",
    "trap_flags",
    "kol_farm_pattern",
    "farm_risk",
    "fomo_next",
)

FOMO_ROUTES = frozenset({"SKIP", "WATCH_CLUSTER", "RESEARCH_CA", "PREPARE_NOTE"})

TRADE_ACTIONS = frozenset({
    "buy",
    "ape",
    "snipe",
    "swap",
    "trade",
    "wallet",
    "market_buy",
    "copy_trade",
    "auto_buy",
    "financial",
})

_FOMO_HINTS = (
    r"\bfomo\b",
    r"memecoin",
    r"meme coin",
    r"\bca[:\s]",
    r"contract address",
    r"copy[\s-]?trade",
    r"\bbundled\b",
    r"\bbundle\b",
    r"honeypot",
    r"stealth launch",
    r"no socials",
    r"bubble ?maps?",
    r"\bape this\b",
    r"\baping\b",
    r"dexscreener",
    r"pump\.fun",
    r"pumpfun",
    r"dev dumped",
    r"kol call",
    r"\bshill\b",
    r"exit liquidity",
    r"wallet island",
    r"wallet cluster",
    r"low liq(?:uidity)?",
    r"\brug\b",
    r"\brugged\b",
)

_FOMO_HINT_RE = re.compile("|".join(_FOMO_HINTS), re.IGNORECASE)


def build_fomo_questions() -> dict[str, Any]:
    """Atomic SystemOne questions. Safe even when CA/liq/deployer are missing."""
    return {
        "is_fomo_call": {
            "type": "noul",
            "instructions": (
                "Is this a FOMO-app call, meme tip, CA dump, or copy-trade lure "
                "that could farm retail?"
            ),
            "criteria": {
                "true": (
                    "FOMO-app call, meme-coin tip, contract-address dump, or "
                    "copy-trade lure aimed at late retail"
                ),
                "false": "Not a FOMO, meme, or tip call, and not a retail-farming lure",
            },
        },
        "bundled_or_cluster_risk": {
            "type": "noul",
            "instructions": (
                "Does the post or context suggest bundled wallets, one linked "
                "wallet island, or a coordinated cluster that retail would be late to?"
            ),
            "criteria": {
                "true": (
                    "Bundled wallets, a single linked island, or coordinated cluster "
                    "that late retail would buy into"
                ),
                "false": "No bundled/cluster signal in the text or known_fields",
            },
        },
        "trap_flags": {
            "type": "noul",
            "instructions": (
                "Are there red flags of honeypot, known rug deployer pattern, "
                "very low liquidity trap, or no-socials stealth launch used as bait?"
            ),
            "criteria": {
                "true": (
                    "Honeypot, rug-deployer pattern, very low-liq trap, or "
                    "no-socials stealth launch used as bait"
                ),
                "false": "No honeypot, rug, stealth-bait, or low-liq trap flags",
            },
        },
        "kol_farm_pattern": {
            "type": "noul",
            "instructions": (
                "Does this match KOL/shill exit-liquidity farming (public thesis plus "
                "side-wallet dump dynamics, paid promo vibe, or blind copy lure)?"
            ),
            "criteria": {
                "true": (
                    "KOL/shill farming: public thesis with side-wallet dump, paid promo, "
                    "or blind copy-trade lure"
                ),
                "false": "Does not match KOL/shill exit-liquidity farming",
            },
        },
        "farm_risk": {
            "type": "score",
            "instructions": (
                "If someone aped this call immediately, how likely are they to get farmed?"
            ),
            "criteria": list(FOMO_FARM_RISK_CRITERIA),
        },
        "fomo_next": {
            "type": "choice",
            "instructions": (
                "What should happen next for this FOMO candidate? "
                "PREPARE_NOTE is a research note only, never a buy. "
                "Do not treat a public reply as a buy signal."
            ),
            "criteria": dict(FOMO_NEXT_CRITERIA),
        },
    }


def looks_fomo_related(post: Any) -> bool:
    """True when state is marked FOMO or text/known fields look like a FOMO call."""
    if getattr(post, "fomo_related", False):
        return True
    if any(getattr(post, field, "") for field in ("ca", "liq", "deployer", "cluster_hint")):
        return True
    blob = " ".join(
        str(part)
        for part in (
            getattr(post, "text", ""),
            getattr(post, "author", ""),
            getattr(post, "url", ""),
        )
        if part
    )
    return bool(blob and _FOMO_HINT_RE.search(blob))


def should_include_fomo_pack(post: Any, fomo_mode: bool) -> bool:
    """Include the pack when FOMO mode is on or the post looks FOMO-related."""
    return bool(fomo_mode) or looks_fomo_related(post)


def fomo_known_fields(post: Any) -> dict[str, str | None]:
    """Optional on-chain hints. Empty values stay None so Jev can ignore them."""
    def _opt(name: str) -> str | None:
        value = str(getattr(post, name, "") or "").strip()
        return value or None

    return {
        "ca": _opt("ca"),
        "liq": _opt("liq"),
        "deployer": _opt("deployer"),
        "cluster_hint": _opt("cluster_hint"),
    }


def stub_research_note(post: Any) -> str:
    """Human research note only. Never a buy order and never an X reply."""
    snippet = (getattr(post, "text", "") or "").strip().split("\n")[0][:120]
    ca = str(getattr(post, "ca", "") or "").strip()
    ca_bit = f" CA {ca}." if ca else ""
    head = snippet or "FOMO candidate"
    return (
        f"Research note only, not a buy.{ca_bit} "
        f"Verify deployer, liquidity, bubble map, and cluster before any size. "
        f"Post: {head}"
    )


def should_execute_trade(_decision: Any = None) -> bool:
    """Agent finds; human sizes; agent never buys."""
    return False
