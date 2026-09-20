"""
Jev decision gate for XInfluencerOS.

Jev classifies a post. This module applies routing rules in code. It never
writes replies to X and never performs X actions (like, bookmark, reply,
repost, follow, DM, delete, financial actions).

Shadow mode (default): classify + log only.
PREPARE_REPLY: draft a short reply via OpenRouter if available, else a stub.
Drafts are queued to the Telegram approval stub — they are not posted.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from agents.grok_research import flag_for_grok_research
from agents.jev_client import (
    ChoiceAnswer,
    JevCallResult,
    JevClient,
    JevSettings,
    NoulAnswer,
    ScoreAnswer,
)
from agents.jev_fomo import (
    FOMO_QUESTION_NAMES,
    FOMO_ROUTES,
    TRADE_ACTIONS,
    build_fomo_questions,
    fomo_known_fields,
    should_execute_trade,
    should_include_fomo_pack,
    stub_research_note,
)
from agents.telegram_approval import queue_for_approval

logger = logging.getLogger(__name__)

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "storage" / "jev_shadow_logs"

USER_INTERESTS: list[str] = [
    "Quantitative trading",
    "Trading research papers",
    "Backtesting",
    "Forex, XAUUSD, US100, US30 and BTC",
    "AI agents and automation",
    "Grok Bot, Jev and computer-use systems",
    "Legitimate trading or crypto giveaways",
]

CONTENT_TYPE_CRITERIA = {
    "useful_information": "Factual, actionable, or research-useful content",
    "emotion_opinion": "Emotion, opinion, rant, or personal take",
    "advertisement": "Promo, marketing, or sales pitch",
    "possible_scam": "Likely scam, phishing, fake giveaway, or social-engineering risk",
}

RELEVANCE_CRITERIA = {
    "true": "Clearly matches one or more listed interests",
    "false": "Off-topic or only tenuously related",
}

NEXT_ACTION_CRITERIA = {
    "IGNORE": "Take no action",
    "SAVE": "Worth saving/bookmarking for later",
    "RESEARCH": "Claims need verification with reliable sources",
    "PREPARE_REPLY": "Worth drafting a short natural reply (draft only; do not post)",
}

INTERACTION_RISK_CRITERIA = ["low", "medium", "high"]
RISK_LABELS = ("low", "medium", "high")

RoutedAction = str  # IGNORE | SAVE | RESEARCH | PREPARE_REPLY | REVIEW | SKIP | WATCH_CLUSTER | RESEARCH_CA | PREPARE_NOTE

BASE_QUESTION_NAMES = ("content_type", "relevance", "interaction_risk", "next_action")
BASE_CONFIDENCE_FIELDS = ("content_type", "interaction_risk", "next_action")

X_MUTATION_ACTIONS = frozenset({
    "like",
    "bookmark",
    "reply",
    "repost",
    "retweet",
    "follow",
    "dm",
    "message",
    "delete",
    "post",
    "quote",
    "financial",
    "buy",
    "ape",
    "snipe",
    "swap",
    "trade",
})


def build_questions(*, include_fomo: bool = False) -> dict[str, Any]:
    """SystemOne questions. Must match the TypeSafe request contract."""
    questions = {
        "content_type": {
            "type": "choice",
            "instructions": (
                "Is this mainly useful information, emotion/opinion, "
                "advertisement, or possible scam?"
            ),
            "criteria": dict(CONTENT_TYPE_CRITERIA),
        },
        "relevance": {
            "type": "noul",
            "instructions": "Is this relevant to the user's interests listed in state?",
            "criteria": dict(RELEVANCE_CRITERIA),
        },
        "interaction_risk": {
            "type": "score",
            "instructions": "What is the public-interaction risk of engaging with this post?",
            "criteria": list(INTERACTION_RISK_CRITERIA),
        },
        "next_action": {
            "type": "choice",
            "instructions": "What should happen next for this post?",
            "criteria": dict(NEXT_ACTION_CRITERIA),
        },
    }
    if include_fomo:
        questions.update(build_fomo_questions())
    return questions


def build_state(post: "PostInput", *, include_fomo: bool = False) -> dict[str, Any]:
    state: dict[str, Any] = {
        "post_id": post.id,
        "url": post.url,
        "author_handle": post.author,
        "author_name": post.author_name or post.author,
        "text": post.text,
        "user_interests": list(USER_INTERESTS),
    }
    if include_fomo:
        state["fomo_related"] = True
        state["known_fields"] = fomo_known_fields(post)
        state["kill_rules"] = (
            "Maran FOMO-app: agent finds, human sizes, agent never buys. "
            "On-chain checks (bubblemaps, liq, deployer) are Grok Bot / human steps."
        )
    return state


@dataclass
class PostInput:
    id: str
    url: str = ""
    author: str = ""
    author_name: str = ""
    text: str = ""
    ca: str = ""
    liq: str = ""
    deployer: str = ""
    cluster_hint: str = ""
    fomo_related: bool = False

    def as_log_author(self) -> str:
        if self.author_name and self.author and self.author_name != self.author:
            return f"{self.author_name} (@{self.author.lstrip('@')})"
        return self.author or self.author_name or ""


@dataclass
class GateDecision:
    post: PostInput
    recommended_action: str | None
    final_routed_action: str
    content_type: str | None = None
    relevance: float | None = None
    interaction_risk: str | None = None
    answers: dict[str, Any] = field(default_factory=dict)
    probabilities: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float | None] = field(default_factory=dict)
    api_latency_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""
    draft_reply: str | None = None
    research_ticket: dict[str, Any] | None = None
    telegram_receipt: dict[str, Any] | None = None
    shadow_mode: bool = True
    save_permitted: bool = False
    reason: str = ""
    model: str | None = None
    attempts: int = 0
    fomo_pack_applied: bool = False
    is_fomo_call: float | None = None
    farm_risk: str | None = None
    fomo_next: str | None = None
    research_note: str | None = None
    never_buy: bool = True

    @property
    def skip_x_mutation(self) -> bool:
        return True

    def to_log_record(self) -> dict[str, Any]:
        return {
            "post_id": self.post.id,
            "url": self.post.url,
            "author": self.post.as_log_author(),
            "text": self.post.text,
            "answers": self.answers,
            "probabilities": self.probabilities,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "final_routed_action": self.final_routed_action,
            "content_type": self.content_type,
            "relevance": self.relevance,
            "interaction_risk": self.interaction_risk,
            "api_latency_ms": self.api_latency_ms,
            "errors": self.errors,
            "timestamp": self.timestamp,
            "shadow_mode": self.shadow_mode,
            "save_permitted": self.save_permitted,
            "draft_reply": self.draft_reply,
            "research_note": self.research_note,
            "reason": self.reason,
            "model": self.model,
            "attempts": self.attempts,
            "fomo_pack_applied": self.fomo_pack_applied,
            "is_fomo_call": self.is_fomo_call,
            "farm_risk": self.farm_risk,
            "fomo_next": self.fomo_next,
            "never_buy": True,
            "ca": self.post.ca or None,
        }


def post_from_mapping(raw: dict[str, Any]) -> PostInput:
    url = str(raw.get("url") or "")
    post_id = str(raw.get("id") or _status_id_from_url(url) or "")
    handle = str(raw.get("handle") or raw.get("author_handle") or "")
    author = str(raw.get("author") or handle)
    author_name = str(raw.get("author_name") or raw.get("name") or "")
    if author.startswith("@"):
        handle = author[1:]
        author = handle
    fomo_flag = raw.get("fomo") if "fomo" in raw else raw.get("fomo_related")
    topic = str(raw.get("topic") or "").strip().lower()
    return PostInput(
        id=post_id,
        url=url,
        author=author,
        author_name=author_name or author,
        text=str(raw.get("text") or ""),
        ca=str(raw.get("ca") or raw.get("contract") or ""),
        liq=str(raw.get("liq") or raw.get("liquidity") or ""),
        deployer=str(raw.get("deployer") or ""),
        cluster_hint=str(raw.get("cluster_hint") or raw.get("cluster") or ""),
        fomo_related=bool(fomo_flag) or topic == "fomo",
    )


def evaluate_tweet(
    tweet: dict[str, Any],
    *,
    client: JevClient | None = None,
    settings: JevSettings | None = None,
    generate_draft: bool = True,
    run_research: bool = False,
    draft_fn: Callable[[PostInput], str | None] | None = None,
    log_dir: Path | None = None,
    write_log: bool = True,
) -> GateDecision:
    """Orchestrator hook: classify a feed/search tweet, never post to X."""
    return evaluate_post(
        post_from_mapping(tweet),
        client=client,
        settings=settings,
        generate_draft=generate_draft,
        run_research=run_research,
        draft_fn=draft_fn,
        log_dir=log_dir,
        write_log=write_log,
    )


def evaluate_post(
    post: PostInput,
    *,
    client: JevClient | None = None,
    settings: JevSettings | None = None,
    generate_draft: bool = True,
    run_research: bool = False,
    draft_fn: Callable[[PostInput], str | None] | None = None,
    log_dir: Path | None = None,
    write_log: bool = True,
) -> GateDecision:
    """Classify one post and apply routing rules. No X mutations. Never buys."""
    settings = settings or JevSettings.from_env()
    timestamp = datetime.now(timezone.utc).isoformat()
    client = client or JevClient(settings)
    include_fomo = should_include_fomo_pack(post, settings.fomo_mode)

    result = client.classify(
        build_state(post, include_fomo=include_fomo),
        build_questions(include_fomo=include_fomo),
    )
    decision = route_result(
        post,
        result,
        settings,
        timestamp,
        fomo_pack_applied=include_fomo,
    )

    if decision.final_routed_action in {"RESEARCH", "RESEARCH_CA", "WATCH_CLUSTER"}:
        decision.research_ticket = flag_for_grok_research(
            {"id": post.id, "url": post.url, "text": post.text, "ca": post.ca},
            run=run_research,
            reason=(
                "Jev routed RESEARCH_CA: verify CA, deployer, liq, bubble map"
                if decision.final_routed_action == "RESEARCH_CA"
                else (
                    "Jev routed WATCH_CLUSTER: wait for multi-wallet cluster confirm"
                    if decision.final_routed_action == "WATCH_CLUSTER"
                    else "Jev recommended RESEARCH"
                )
            ),
        )

    if decision.final_routed_action == "PREPARE_REPLY" and generate_draft:
        decision.draft_reply = _prepare_draft(post, draft_fn)
        decision.telegram_receipt = queue_for_approval(
            {
                "kind": "prepared_reply",
                "post_id": post.id,
                "url": post.url,
                "draft_reply": decision.draft_reply,
                "note": "Human approval required before any public X action",
            }
        )

    if decision.final_routed_action == "PREPARE_NOTE" and generate_draft:
        decision.research_note = sanitize_draft(stub_research_note(post))
        decision.telegram_receipt = queue_for_approval(
            {
                "kind": "fomo_research_note",
                "post_id": post.id,
                "url": post.url,
                "research_note": decision.research_note,
                "never_buy": True,
                "note": "Research note only. Human sizes. Agent never buys.",
            }
        )

    if write_log:
        append_shadow_log(decision.to_log_record(), log_dir=log_dir)

    return decision


def route_result(
    post: PostInput,
    result: JevCallResult,
    settings: JevSettings,
    timestamp: str,
    *,
    fomo_pack_applied: bool = False,
) -> GateDecision:
    """Apply routing rules after Jev answers. Fail closed to REVIEW. Never buys."""
    base = GateDecision(
        post=post,
        recommended_action=None,
        final_routed_action="REVIEW",
        api_latency_ms=result.latency_ms,
        timestamp=timestamp,
        shadow_mode=settings.shadow_mode,
        save_permitted=bool(settings.allow_save) and not settings.shadow_mode,
        attempts=result.attempts,
        model=result.response.model if result.response else None,
        fomo_pack_applied=fomo_pack_applied,
        never_buy=True,
    )

    if not result.ok or result.response is None:
        base.errors.append(result.error or "Jev classify failed")
        base.reason = "classify_error"
        return base

    answers = result.response.answers
    content = answers.get("content_type")
    relevance = answers.get("relevance")
    risk = answers.get("interaction_risk")
    nxt = answers.get("next_action")

    content_choice = _choice_value(content)
    next_choice = _choice_value(nxt)
    risk_label = _score_label(risk)
    relevance_noul = _noul_value(relevance)

    base.content_type = content_choice
    base.interaction_risk = risk_label
    base.relevance = relevance_noul
    base.recommended_action = next_choice
    base.answers = {name: _answer_dump(ans) for name, ans in answers.items()}
    base.probabilities = {name: _answer_probabilities(ans) for name, ans in answers.items()}
    base.confidence = {name: _answer_confidence(ans) for name, ans in answers.items()}
    base.is_fomo_call = _noul_value(answers.get("is_fomo_call"))
    base.farm_risk = _score_label(answers.get("farm_risk"))
    base.fomo_next = _choice_value(answers.get("fomo_next"))

    missing = [name for name in BASE_QUESTION_NAMES if name not in answers]
    if missing:
        base.errors.append(f"Missing Jev answers: {', '.join(missing)}")
        base.reason = "missing_answers"
        base.final_routed_action = "REVIEW"
        return base

    if content_choice == "possible_scam" or risk_label == "high":
        base.final_routed_action = "REVIEW"
        base.reason = "scam_or_high_risk"
        return base

    low_conf = _low_confidence_fields(
        answers,
        settings.confidence_threshold,
        field_names=BASE_CONFIDENCE_FIELDS,
    )
    if low_conf:
        base.final_routed_action = "REVIEW"
        base.reason = f"low_confidence:{','.join(low_conf)}"
        return base

    if fomo_pack_applied:
        fomo_decision = _route_fomo(base, answers, settings)
        if fomo_decision is not None:
            return fomo_decision

    if next_choice == "IGNORE":
        base.final_routed_action = "IGNORE"
        base.reason = "high_confidence_ignore"
        return base

    if next_choice == "SAVE":
        base.final_routed_action = "SAVE"
        base.reason = "save_logged_only" if not base.save_permitted else "save_permitted_later"
        return base

    if next_choice == "RESEARCH":
        base.final_routed_action = "RESEARCH"
        base.reason = "flag_for_grok_research"
        return base

    if next_choice == "PREPARE_REPLY":
        base.final_routed_action = "PREPARE_REPLY"
        base.reason = "draft_only_never_post"
        return base

    base.final_routed_action = "REVIEW"
    base.reason = f"unrecognized_next_action:{next_choice}"
    return base


def _route_fomo(
    base: GateDecision,
    answers: dict[str, Any],
    settings: JevSettings,
) -> GateDecision | None:
    """Maran kill rules. Returns a decision to short-circuit, or None to use base next_action."""
    missing_fomo = [name for name in FOMO_QUESTION_NAMES if name not in answers]
    if missing_fomo:
        base.errors.append(f"Missing FOMO answers: {', '.join(missing_fomo)}")
        base.reason = "missing_fomo_answers"
        base.final_routed_action = "REVIEW"
        return base

    noul_cut = settings.fomo_noul_threshold
    conf_cut = settings.confidence_threshold
    trap = _noul_value(answers.get("trap_flags"))
    kol = _noul_value(answers.get("kol_farm_pattern"))
    is_fomo = _noul_value(answers.get("is_fomo_call"))
    cluster = _noul_value(answers.get("bundled_or_cluster_risk"))
    farm_label = _score_label(answers.get("farm_risk"))
    farm_ans = answers.get("farm_risk")
    fomo_next = _choice_value(answers.get("fomo_next"))
    fomo_next_ans = answers.get("fomo_next")

    if trap is not None and trap >= noul_cut:
        if _noul_confident(trap, conf_cut):
            return _finish_fomo(base, "SKIP", "fomo_trap_flags", fomo_next)
        return _finish_fomo(base, "REVIEW", "fomo_trap_low_confidence", fomo_next)

    if farm_label == "high":
        farm_conf = _answer_confidence(farm_ans)
        if farm_conf is not None and farm_conf < conf_cut:
            return _finish_fomo(base, "REVIEW", "fomo_farm_risk_low_confidence", fomo_next)
        return _finish_fomo(base, "SKIP", "fomo_farm_risk_high", fomo_next)

    if kol is not None and kol >= noul_cut:
        if _noul_confident(kol, conf_cut):
            return _finish_fomo(base, "SKIP", "fomo_kol_farm_pattern", fomo_next)
        return _finish_fomo(base, "REVIEW", "fomo_kol_low_confidence", fomo_next)

    fomo_high = is_fomo is not None and is_fomo >= noul_cut
    cluster_high = cluster is not None and cluster >= noul_cut
    if fomo_high and cluster_high:
        routed = "SKIP" if fomo_next == "SKIP" else "WATCH_CLUSTER"
        return _finish_fomo(base, routed, "fomo_call_and_cluster", fomo_next)

    if not fomo_high:
        return None

    # FOMO candidate: prefer fomo_next. Never PREPARE_REPLY. Never buy.
    fomo_next_conf = _answer_confidence(fomo_next_ans)
    if fomo_next_conf is not None and fomo_next_conf < conf_cut:
        return _finish_fomo(base, "REVIEW", "fomo_next_low_confidence", fomo_next)

    if fomo_next in FOMO_ROUTES:
        reason = {
            "SKIP": "fomo_next_skip",
            "WATCH_CLUSTER": "fomo_watch_cluster",
            "RESEARCH_CA": "fomo_research_ca_human_onchain",
            "PREPARE_NOTE": "fomo_research_note_never_buy",
        }[fomo_next]
        return _finish_fomo(base, fomo_next, reason, fomo_next)

    return _finish_fomo(base, "REVIEW", f"unrecognized_fomo_next:{fomo_next}", fomo_next)


def _finish_fomo(
    base: GateDecision,
    routed: str,
    reason: str,
    fomo_next: str | None,
) -> GateDecision:
    base.final_routed_action = routed
    base.reason = reason
    base.fomo_next = fomo_next
    if fomo_next:
        base.recommended_action = fomo_next
    base.never_buy = True
    return base


def _noul_confident(noul: float, threshold: float) -> bool:
    return max(noul, 1.0 - noul) >= threshold


def should_perform_x_action(action: str, decision: GateDecision | None = None) -> bool:
    """Jev never performs X mutations or trades, including when shadow mode is off."""
    del decision
    if action.lower() in X_MUTATION_ACTIONS or action.lower() in TRADE_ACTIONS:
        return False
    return False


def should_skip_posting(decision: GateDecision, shadow_mode: bool | None = None) -> bool:
    """True unless a future Telegram-approved executor is wired.

    Today this is always True: PREPARE_REPLY drafts stay off X, FOMO routes never
    post or buy, REVIEW and non-reply routes never post, and shadow mode forbids
    mutations.
    """
    del shadow_mode
    if decision.final_routed_action in FOMO_ROUTES:
        return True
    if decision.final_routed_action != "PREPARE_REPLY":
        return True
    return True


def append_shadow_log(record: dict[str, Any], log_dir: Path | None = None) -> Path:
    log_dir = log_dir or DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = log_dir / f"jev_shadow_{day}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path


def summarize_decisions(decisions: Iterable[GateDecision]) -> dict[str, Any]:
    rows = list(decisions)
    counts: dict[str, int] = {}
    latencies = [d.api_latency_ms for d in rows if d.api_latency_ms is not None]
    for d in rows:
        counts[d.final_routed_action] = counts.get(d.final_routed_action, 0) + 1
    return {
        "count": len(rows),
        "counts_by_action": counts,
        "latency_ms": _latency_stats(latencies),
    }


def _latency_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "median": None, "p95": None}
    ordered = sorted(values)
    n = len(ordered)
    avg = round(sum(ordered) / n, 2)
    mid = n // 2
    median = ordered[mid] if n % 2 else round((ordered[mid - 1] + ordered[mid]) / 2.0, 2)
    p95_index = min(n - 1, max(0, int(round(0.95 * (n - 1)))))
    return {"avg": avg, "median": median, "p95": ordered[p95_index]}


def _choice_value(answer: Any) -> str | None:
    if isinstance(answer, ChoiceAnswer):
        return answer.choice
    return None


def _noul_value(answer: Any) -> float | None:
    if isinstance(answer, NoulAnswer):
        return answer.noul
    return None


def _answer_confidence(answer: Any) -> float | None:
    if isinstance(answer, (ChoiceAnswer, ScoreAnswer)):
        return answer.confidence
    if isinstance(answer, NoulAnswer):
        return max(answer.noul, 1.0 - answer.noul)
    return None


def _answer_probabilities(answer: Any) -> dict[str, float]:
    if isinstance(answer, NoulAnswer):
        return {"true": answer.noul, "false": round(1.0 - answer.noul, 6)}
    probs = getattr(answer, "probabilities", None)
    return dict(probs) if probs else {}


def _answer_dump(answer: Any) -> dict[str, Any]:
    if hasattr(answer, "model_dump"):
        return answer.model_dump()
    return {}


def _score_label(answer: Any) -> str | None:
    if not isinstance(answer, ScoreAnswer):
        return None
    if answer.probabilities:
        best_key, _ = max(answer.probabilities.items(), key=lambda item: item[1])
        labeled = _label_from_score_key(best_key, answer.legend)
        if labeled:
            return labeled
    if answer.legend:
        try:
            rounded = str(int(round(answer.score)))
            labeled = _label_from_score_key(rounded, answer.legend)
            if labeled:
                return labeled
        except (TypeError, ValueError):
            pass
    idx = int(round(answer.score))
    idx = max(0, min(idx, len(RISK_LABELS) - 1))
    return RISK_LABELS[idx]


def _label_from_score_key(key: str, legend: dict[str, str]) -> str | None:
    key_l = str(key).strip().lower()
    if key_l in RISK_LABELS:
        return key_l
    legend_val = (legend.get(str(key)) or legend.get(key_l) or "").lower()
    for label in RISK_LABELS:
        if label in legend_val.split() or legend_val == label:
            return label
    try:
        idx = int(float(key))
        if 0 <= idx < len(RISK_LABELS):
            return RISK_LABELS[idx]
    except (TypeError, ValueError):
        return None
    return None


def _low_confidence_fields(
    answers: dict[str, Any],
    threshold: float,
    field_names: tuple[str, ...] | None = None,
) -> list[str]:
    """Choice/score confidence below threshold -> REVIEW. Noul is not included."""
    names = field_names if field_names is not None else tuple(answers.keys())
    low: list[str] = []
    for name in names:
        answer = answers.get(name)
        if isinstance(answer, (ChoiceAnswer, ScoreAnswer)) and answer.confidence < threshold:
            low.append(name)
    return low


def _status_id_from_url(url: str) -> str:
    if not url:
        return ""
    path = urlparse(url).path
    match = re.search(r"/status/(\d+)", path)
    return match.group(1) if match else ""


def _prepare_draft(
    post: PostInput,
    draft_fn: Callable[[PostInput], str | None] | None,
) -> str:
    if draft_fn is not None:
        text = draft_fn(post) or ""
        return sanitize_draft(text) or _stub_draft(post)
    generated = _openrouter_draft(post)
    if generated:
        return generated
    return _stub_draft(post)


def sanitize_draft(text: str) -> str:
    cleaned = (text or "").replace("—", ", ").replace("–", "-")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _stub_draft(post: PostInput) -> str:
    snippet = (post.text or "").strip().split("\n")[0][:80]
    if snippet:
        return (
            f"Noting this for later: {snippet}. "
            "Want the actual method, not the headline."
        )
    return "Worth a closer look on the method, not the headline."


def _openrouter_draft(post: PostInput) -> str | None:
    """Draft via existing OpenRouter helper. Never posts. Failures become a stub."""
    try:
        from agents.openrouter_client import generate_reply
    except Exception as exc:  # pragma: no cover - import guard
        logger.info("OpenRouter client unavailable (%s); using draft stub", exc.__class__.__name__)
        return None

    try:
        reply, error = generate_reply(post.text)
    except Exception as exc:
        logger.info("OpenRouter draft failed (%s); using draft stub", exc.__class__.__name__)
        return None

    if error or not reply:
        logger.info("OpenRouter draft skipped: %s", error or "empty reply")
        return None
    return sanitize_draft(reply)
