"""
Unit tests for the Jev decision gate.

All HTTP is mocked. These tests must pass without TYPESAFE_API_KEY and must
never touch live X mutation APIs.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agents.jev_client import JevCallResult, JevClient, JevResponse, JevSettings
from agents.jev_decision_gate import (
    PostInput,
    evaluate_post,
    route_result,
    should_perform_x_action,
    should_skip_posting,
)
from agents.jev_demo import build_mock_transport, mock_answers_for_post


def _settings(**overrides) -> JevSettings:
    base = dict(
        api_key="test-key-not-real",
        model="jev-latest",
        confidence_threshold=0.85,
        shadow_mode=True,
        allow_save=False,
    )
    base.update(overrides)
    return JevSettings(**base)


def _post(pid: str = "p1", text: str = "hello") -> PostInput:
    return PostInput(
        id=pid,
        url=f"https://x.com/u/status/{pid}",
        author="u",
        author_name="User",
        text=text,
    )


def _answers(
    *,
    content: str = "useful_information",
    next_action: str = "IGNORE",
    risk: str = "low",
    relevance: float = 0.9,
    content_confidence: float = 0.95,
    next_confidence: float = 0.95,
    risk_confidence: float = 0.95,
) -> dict:
    risk_index = {"low": 0, "medium": 1, "high": 2}[risk]
    return {
        "content_type": {
            "type": "choice",
            "choice": content,
            "confidence": content_confidence,
            "probabilities": {content: 0.9},
        },
        "relevance": {"type": "noul", "noul": relevance},
        "interaction_risk": {
            "type": "score",
            "score": float(risk_index),
            "confidence": risk_confidence,
            "legend": {"0": "low", "1": "medium", "2": "high"},
            "probabilities": {str(risk_index): 0.9},
        },
        "next_action": {
            "type": "choice",
            "choice": next_action,
            "confidence": next_confidence,
            "probabilities": {next_action: 0.9},
        },
    }


def _ok_result(answers: dict, latency: float = 12.0) -> JevCallResult:
    return JevCallResult(
        ok=True,
        response=JevResponse(model="jev-1.13.0", answers=answers),
        latency_ms=latency,
        status_code=200,
        attempts=1,
    )


def _route(answers: dict, **setting_kw) -> str:
    decision = route_result(
        _post(),
        _ok_result(answers),
        _settings(**setting_kw),
        "2026-09-20T00:00:00+00:00",
    )
    return decision.final_routed_action


def _transport_from_sequence(sequence: list, calls: list | None = None) -> httpx.MockTransport:
    remaining = list(sequence)

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        item = remaining.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def test_ignore_high_confidence():
    assert _route(_answers(next_action="IGNORE")) == "IGNORE"


def test_save_logged_but_not_executed_in_shadow(tmp_path: Path):
    client = JevClient(
        _settings(allow_save=False),
        transport=_fixed_answers_transport(_answers(next_action="SAVE")),
    )
    decision = evaluate_post(
        _post("save1", "Walk-forward backtesting notes for XAUUSD."),
        client=client,
        settings=_settings(allow_save=False, shadow_mode=True),
        generate_draft=False,
        log_dir=tmp_path,
        draft_fn=lambda p: "should not run",
    )
    assert decision.final_routed_action == "SAVE"
    assert decision.save_permitted is False
    assert decision.draft_reply is None
    assert should_perform_x_action("bookmark", decision) is False
    assert should_skip_posting(decision) is True


def test_research_flags_stub_without_external_calls(tmp_path: Path):
    client = JevClient(
        _settings(),
        transport=_fixed_answers_transport(_answers(next_action="RESEARCH", risk="medium")),
    )
    decision = evaluate_post(
        _post("r1", "US100 strategy Sharpe 4.1 last month."),
        client=client,
        settings=_settings(),
        generate_draft=False,
        run_research=True,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "RESEARCH"
    assert decision.research_ticket is not None
    assert decision.research_ticket["external_calls"] is False
    assert decision.research_ticket["ran"] is True


def test_prepare_reply_drafts_but_never_posts(tmp_path: Path):
    client = JevClient(
        _settings(),
        transport=_fixed_answers_transport(_answers(next_action="PREPARE_REPLY")),
    )
    decision = evaluate_post(
        _post("reply1", "Wiring Jev in front of Grok Bot computer-use."),
        client=client,
        settings=_settings(shadow_mode=True),
        generate_draft=True,
        log_dir=tmp_path,
        draft_fn=lambda p: "Local method-first note, not a public post.",
    )
    assert decision.final_routed_action == "PREPARE_REPLY"
    assert decision.draft_reply is not None
    assert "—" not in decision.draft_reply
    assert decision.telegram_receipt["live_send"] is False
    assert should_skip_posting(decision) is True
    assert should_perform_x_action("reply", decision) is False
    assert should_perform_x_action("repost", decision) is False


def test_scam_routes_to_review_even_if_jev_wants_reply():
    answers = _answers(
        content="possible_scam",
        next_action="PREPARE_REPLY",
        risk="low",
    )
    decision = route_result(_post(), _ok_result(answers), _settings(), "t")
    assert decision.final_routed_action == "REVIEW"
    assert decision.reason == "scam_or_high_risk"


def test_high_interaction_risk_routes_to_review():
    answers = _answers(next_action="SAVE", risk="high")
    assert _route(answers) == "REVIEW"


def test_low_confidence_routes_to_review():
    answers = _answers(next_action="IGNORE", next_confidence=0.4)
    decision = route_result(_post(), _ok_result(answers), _settings(), "t")
    assert decision.final_routed_action == "REVIEW"
    assert decision.reason.startswith("low_confidence")


def test_retry_on_429(tmp_path: Path):
    calls: list[httpx.Request] = []
    slept: list[float] = []
    body = {"model": "jev-latest", "answers": _answers(next_action="IGNORE")}
    transport = _transport_from_sequence(
        [(429, {"error": "rate limited"}), (200, body)],
        calls=calls,
    )
    client = JevClient(
        _settings(),
        transport=transport,
        sleeper=slept.append,
        max_retries=3,
    )
    decision = evaluate_post(
        _post(),
        client=client,
        settings=_settings(),
        generate_draft=False,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "IGNORE"
    assert len(calls) == 2
    assert slept  # backoff ran
    assert decision.attempts == 2


def test_retry_on_529_then_success(tmp_path: Path):
    body = {"model": "jev-latest", "answers": _answers(next_action="SAVE")}
    transport = _transport_from_sequence([(529, {"error": "overloaded"}), (200, body)])
    client = JevClient(_settings(), transport=transport, sleeper=lambda _d: None)
    decision = evaluate_post(
        _post("s1"),
        client=client,
        settings=_settings(),
        generate_draft=False,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "SAVE"


def test_invalid_json_handling(tmp_path: Path):
    transport = _transport_from_sequence([(200, "this is not json {{{")])
    client = JevClient(_settings(), transport=transport)
    decision = evaluate_post(
        _post(),
        client=client,
        settings=_settings(),
        generate_draft=False,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "REVIEW"
    assert decision.errors
    assert "Invalid JSON" in decision.errors[0]


def test_invalid_schema_handling(tmp_path: Path):
    transport = _transport_from_sequence([(200, {"model": "jev-latest", "answers": "nope"})])
    client = JevClient(_settings(), transport=transport)
    decision = evaluate_post(
        _post(),
        client=client,
        settings=_settings(),
        generate_draft=False,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "REVIEW"
    assert any("schema" in err.lower() or "validation" in err.lower() for err in decision.errors)


def test_missing_api_key_fail_closed(tmp_path: Path):
    client = JevClient(_settings(api_key=""))
    decision = evaluate_post(
        _post(),
        client=client,
        settings=_settings(api_key=""),
        generate_draft=False,
        log_dir=tmp_path,
    )
    assert decision.final_routed_action == "REVIEW"
    assert "TYPESAFE_API_KEY" in decision.errors[0]


def test_jsonl_log_fields(tmp_path: Path):
    client = JevClient(
        _settings(),
        transport=_fixed_answers_transport(_answers(next_action="IGNORE")),
    )
    decision = evaluate_post(
        _post("log1", "off-topic cat video"),
        client=client,
        settings=_settings(),
        generate_draft=False,
        log_dir=tmp_path,
    )
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    for key in (
        "post_id",
        "url",
        "author",
        "text",
        "answers",
        "probabilities",
        "confidence",
        "recommended_action",
        "final_routed_action",
        "api_latency_ms",
        "errors",
        "timestamp",
    ):
        assert key in record
    assert record["post_id"] == "log1"
    assert record["final_routed_action"] == "IGNORE"
    assert "test-key-not-real" not in json.dumps(record)
    assert decision.timestamp


def test_demo_mock_transport_covers_expected_routes():
    expected = {
        "demo-ignore-1": "IGNORE",
        "demo-save-1": "SAVE",
        "demo-research-1": "RESEARCH",
        "demo-reply-1": "PREPARE_REPLY",
        "demo-scam-1": "REVIEW",
        "demo-ad-1": "REVIEW",
    }
    for post_id, routed in expected.items():
        result = JevCallResult(
            ok=True,
            response=JevResponse(model="jev-latest", answers=mock_answers_for_post(post_id)),
            latency_ms=1.0,
        )
        decision = route_result(_post(post_id), result, _settings(), "t")
        assert decision.final_routed_action == routed, post_id


def test_shadow_cli_demo_mock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    from xinfluencer_os.scripts.shadow_jev import run

    report = tmp_path / "report.json"
    logs = tmp_path / "logs"
    rc = run(
        [
            "--demo",
            "--mock-api",
            "--limit",
            "6",
            "--report-out",
            str(report),
            "--log-dir",
            str(logs),
        ]
    )
    assert rc == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["x_mutations"] is False
    assert data["api_source"] == "mock"
    assert data["count"] == 6
    assert data["counts_by_action"]["REVIEW"] >= 1
    assert data["counts_by_action"]["PREPARE_REPLY"] == 1


def test_build_questions_match_contract():
    from agents.jev_decision_gate import build_questions

    q = build_questions()
    assert q["content_type"]["type"] == "choice"
    assert set(q["content_type"]["criteria"]) == {
        "useful_information",
        "emotion_opinion",
        "advertisement",
        "possible_scam",
    }
    assert q["relevance"]["type"] == "noul"
    assert q["interaction_risk"]["type"] == "score"
    assert q["interaction_risk"]["criteria"] == ["low", "medium", "high"]
    assert set(q["next_action"]["criteria"]) == {"IGNORE", "SAVE", "RESEARCH", "PREPARE_REPLY"}


def _fixed_answers_transport(answers: dict) -> httpx.MockTransport:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "jev-latest", "answers": answers})

    return httpx.MockTransport(handler)


def test_mock_transport_helper_roundtrip():
    transport = build_mock_transport()
    client = JevClient(_settings(), transport=transport)
    result = client.classify({"post_id": "demo-reply-1"}, {"dummy": {"type": "noul", "instructions": "x"}})
    assert result.ok
    assert result.response.answers["next_action"].choice == "PREPARE_REPLY"
