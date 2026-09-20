# XInfluencerOS

Multi-agent X automation for GhostReply. Agents research trends, draft content, and operate a browser. **Live X posting is not enabled by this Jev integration.**

## Architecture

```
post / tweet
    -> Jev (TypeSafe SystemOne)   classify only
    -> decision gate (this repo)  route in code
    -> Grok Bot / OpenRouter      research stub or draft reply
    -> Telegram approval stub     human gate
    -> X browser operator         NOT called by Jev; future approved actions only
```

- **Jev classifies.** It never writes replies and never performs X actions (like, bookmark, reply, repost, follow, DM, delete).
- **The gate routes.** High-risk, scam, and low-confidence answers become `REVIEW`. `PREPARE_REPLY` drafts a reply and queues it for Telegram approval. It does not post.
- **Shadow mode is the default** (`JEV_SHADOW_MODE=true`): classify + log only. No X mutations.
- Prepared public actions are intended to go to **Telegram for approval**. The current Telegram module is a log-only stub. Live Telegram send is not implemented here.

## Jev shadow CLI

Runs without touching X. Uses canned TypeSafe responses when `TYPESAFE_API_KEY` is unset.

From the repo root:

```bash
python -m xinfluencer_os.scripts.shadow_jev --demo
python -m xinfluencer_os.scripts.shadow_jev --demo --limit 2
python -m xinfluencer_os.scripts.shadow_jev --input posts.json --limit 20
```

From `xinfluencer_os/`:

```bash
python scripts/shadow_jev.py --demo --mock-api
python main.py --shadow-jev --demo
```

`--input` expects a JSON array:

```json
[
  {
    "id": "123",
    "url": "https://x.com/handle/status/123",
    "author": "handle",
    "text": "Post text"
  }
]
```

Flags:

| Flag | Default | Meaning |
|---|---|---|
| `--limit` | 20 | Max posts to classify |
| `--demo` | on if no `--input` | Built-in sample posts (no X API) |
| `--input` | | JSON file of posts |
| `--mock-api` | implied without API key | Canned TypeSafe answers, no network |
| `--live` | off | Require `TYPESAFE_API_KEY` and call TypeSafe |
| `--run-research` | off | Mark RESEARCH tickets locally; still no external research calls |
| `--report-out` | `storage/jev_shadow_report_sample.json` | Summary JSON |

JSONL logs: `xinfluencer_os/storage/jev_shadow_logs/jev_shadow_YYYY-MM-DD.jsonl`

Fields: `post_id`, `url`, `author`, `text`, `answers`, `probabilities`, `confidence`, `recommended_action`, `final_routed_action`, `api_latency_ms`, `errors`, `timestamp`.

## Environment variables

Copy `.env.example` to `.env`. Never commit real keys.

```ini
TYPESAFE_API_KEY=
TYPESAFE_MODEL=jev-latest
JEV_CONFIDENCE_THRESHOLD=0.85
JEV_SHADOW_MODE=true
JEV_ALLOW_SAVE=false
```

`TYPESAFE_API_KEY` is read from the environment only. The client never hardcodes it and never logs it.

Live smoke (optional, needs a real key):

```bash
export TYPESAFE_API_KEY=your_key_here
python -m xinfluencer_os.scripts.shadow_jev --demo --live --limit 2
```

## Routing rules (applied in code after Jev answers)

| Condition | Routed action | Side effects |
|---|---|---|
| `content_type=possible_scam` or `interaction_risk=high` | `REVIEW` | Human only |
| Choice/score confidence `< JEV_CONFIDENCE_THRESHOLD` | `REVIEW` | Human only |
| High-confidence `IGNORE` | `IGNORE` | None |
| `SAVE` | `SAVE` | Logged. Bookmark on X is never performed. `JEV_ALLOW_SAVE` only records that a later saver may be allowed |
| `RESEARCH` | `RESEARCH` | Grok Bot stub, log only. `--run-research` still does not call external services |
| `PREPARE_REPLY` | `PREPARE_REPLY` | Draft via OpenRouter if available, else a stub. **Never posted.** Queued to Telegram stub |

Orchestrator hook (`main.py`): every feed/search tweet is classified **before** reply generation. If the route is not `PREPARE_REPLY`, if shadow mode is on, or if the route is `REVIEW`, posting is skipped. Auto-post paths stay disabled.

## Tests

```bash
python -m pytest xinfluencer_os/tests
```

Unit tests mock HTTP. They pass without `TYPESAFE_API_KEY` and never call X.

## Live X actions

Live like / bookmark / reply / repost / follow / DM / delete require an **explicit future approval** path (Telegram human-in-the-loop, then `BrowserOperator`). This PR does not turn that on.
