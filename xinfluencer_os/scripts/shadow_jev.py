"""
Shadow-mode Jev classifier CLI.

Classify posts with TypeSafe SystemOne (Jev), apply local routing rules, and
write JSONL logs. Never calls live X mutation APIs (no like, bookmark, reply,
repost, follow, DM, delete).

Examples:
  python -m xinfluencer_os.scripts.shadow_jev --demo
  python -m xinfluencer_os.scripts.shadow_jev --demo --limit 2
  python -m xinfluencer_os.scripts.shadow_jev --input posts.json --limit 20
  python xinfluencer_os/scripts/shadow_jev.py --demo --mock-api

If TYPESAFE_API_KEY is unset, the CLI uses canned mock responses so the
pipeline can run offline. Pass --live to require a real API key.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Running as a script or as python -m: put xinfluencer_os on sys.path first.
_OS_ROOT = Path(__file__).resolve().parents[1]
if str(_OS_ROOT) not in sys.path:
    sys.path.insert(0, str(_OS_ROOT))

from agents.jev_client import JevClient, JevSettings
from agents.jev_decision_gate import (
    GateDecision,
    PostInput,
    evaluate_post,
    post_from_mapping,
    summarize_decisions,
)
from agents.jev_demo import DEMO_POSTS, build_mock_transport


def load_posts(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Input JSON must be an array of posts")
    posts: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Each post must be an object with id, url, author, text")
        posts.append(item)
    return posts


def build_client(args: argparse.Namespace, settings: JevSettings) -> tuple[JevClient, str]:
    if args.mock_api or (not settings.has_api_key and not args.live):
        mock_settings = settings.model_copy(update={"api_key": "mock-shadow-key"})
        return JevClient(mock_settings, transport=build_mock_transport()), "mock"
    if not settings.has_api_key:
        raise SystemExit(
            "TYPESAFE_API_KEY is not set. Export it to run live, or omit --live "
            "to use --mock-api canned responses."
        )
    return JevClient(settings), "live"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Shadow-mode Jev classifier. Logs decisions only. "
            "Never posts, likes, bookmarks, or otherwise mutates X."
        )
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo",
        action="store_true",
        help="Use built-in sample posts (offline; no X API).",
    )
    source.add_argument(
        "--input",
        type=Path,
        help="JSON file: array of posts with id, url, author, text.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Max posts to classify (default 20).")
    parser.add_argument(
        "--mock-api",
        action="store_true",
        help="Use canned TypeSafe responses (no network). Implied when no API key.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Require TYPESAFE_API_KEY and call api.typesafe.ai.",
    )
    parser.add_argument(
        "--run-research",
        action="store_true",
        help="Mark RESEARCH tickets as locally queued. Still does not call external services.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Write a summary JSON report to this path.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="JSONL log directory (default xinfluencer_os/storage/jev_shadow_logs/).",
    )
    args = parser.parse_args(argv)
    if not args.demo and args.input is None:
        args.demo = True
    return args


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = JevSettings.from_env()
    client, source = build_client(args, settings)

    raw_posts = DEMO_POSTS if args.demo else load_posts(args.input)
    posts = raw_posts[: max(0, args.limit)]

    print("=" * 60)
    print("Jev shadow classifier")
    print("=" * 60)
    print(f"source={source}  shadow={settings.shadow_mode}  model={settings.model}")
    print(f"threshold={settings.confidence_threshold}  allow_save={settings.allow_save}")
    print("X mutations: disabled (classify + log only)")
    print(f"posts={len(posts)}")
    print()

    decisions: list[GateDecision] = []
    for raw in posts:
        post: PostInput = post_from_mapping(raw)
        decision = evaluate_post(
            post,
            client=client,
            settings=settings,
            generate_draft=True,
            run_research=args.run_research,
            log_dir=args.log_dir,
            write_log=True,
            draft_fn=lambda p: (
                "Local draft stub: method over headline, no public post."
            ),
        )
        decisions.append(decision)
        preview = (post.text or "").replace("\n", " ")[:72]
        print(
            f"[{decision.final_routed_action:<13}] "
            f"jev={decision.recommended_action or '-'}  "
            f"id={post.id or '-'}  {preview}"
        )
        if decision.errors:
            print(f"    errors: {'; '.join(decision.errors)}")
        if decision.draft_reply:
            print(f"    draft (not posted): {decision.draft_reply[:100]}")

    summary = summarize_decisions(decisions)
    latency = summary["latency_ms"]
    live_available = source == "live"
    if not live_available:
        latency = {
            "avg": latency["avg"],
            "median": latency["median"],
            "p95": latency["p95"],
            "note": (
                "Placeholders from a mocked demo run. Live TypeSafe was not called. "
                "Typical live Jev latency is 70-500ms. "
                "export TYPESAFE_API_KEY=... && python -m xinfluencer_os.scripts.shadow_jev --demo --live --limit 2"
            ),
        }
    report = {
        "mode": "shadow",
        "api_source": source,
        "live_smoke": "ran" if live_available else "skipped_no_TYPESAFE_API_KEY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": summary["count"],
        "counts_by_action": summary["counts_by_action"],
        "latency_ms": latency,
        "x_mutations": False,
        "how_to_run_live": (
            "export TYPESAFE_API_KEY=your_key_here && "
            "python -m xinfluencer_os.scripts.shadow_jev --demo --live --limit 2"
        ),
    }

    print()
    print("-" * 60)
    print("Summary")
    print(json.dumps(report, indent=2))

    report_path = args.report_out
    if report_path is None:
        report_path = _OS_ROOT / "storage" / "jev_shadow_report_sample.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
