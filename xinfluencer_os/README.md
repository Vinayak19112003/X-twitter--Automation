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
python -m xinfluencer_os.scripts.shadow_jev --demo --fomo
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
| `--fomo` | off (or `JEV_FOMO_MODE`) | Maran FOMO kill-rule pack. With `--demo`, adds 3 FOMO sample posts. Never buys. |
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
JEV_FOMO_MODE=false
JEV_FOMO_NOUL_THRESHOLD=0.7
```

`JEV_FOMO_MODE` defaults to **false** so existing non-FOMO classification is unchanged. The FOMO pack is still included when a post is marked `fomo: true` or the text/known fields look like a FOMO-app call. `TYPESAFE_API_KEY` is read from the environment only. The client never hardcodes it and never logs it.

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

## Maran FOMO kill rules

Encoded from TheMaran's FOMO-app playbook: the feed prints calls, retail apes late, KOLs/insiders farm them. These are **filters before sizing**. Jev classifies. A human sizes. **The agent never buys** and never performs X write actions.

When `JEV_FOMO_MODE=true`, `--fomo` is passed, or the post looks FOMO-related, the same SystemOne request also asks:

| Question | Type | Meaning |
|---|---|---|
| `is_fomo_call` | noul | FOMO-app call, meme tip, CA dump, or copy-trade lure |
| `bundled_or_cluster_risk` | noul | Bundled wallets / one linked island / coordinated cluster |
| `trap_flags` | noul | Honeypot, rug deployer, low-liq trap, no-socials stealth bait |
| `kol_farm_pattern` | noul | KOL/shill exit-liquidity farming |
| `farm_risk` | score | If someone aped immediately, how likely they get farmed (`low`/`medium`/`high`) |
| `fomo_next` | choice | `SKIP` / `WATCH_CLUSTER` / `RESEARCH_CA` / `PREPARE_NOTE` |

Routing (after the existing scam / high-risk / low-confidence REVIEW rules):

| Condition | Routed action |
|---|---|
| `trap_flags` high and confident | `SKIP` (REVIEW if the noul is only weakly confident) |
| `farm_risk=high` | `SKIP` (REVIEW if score confidence is low) |
| `kol_farm_pattern` high and confident | `SKIP` |
| `is_fomo_call` high and `bundled_or_cluster_risk` high | `WATCH_CLUSTER` (or `SKIP` if `fomo_next` is SKIP). Never `PREPARE_REPLY` |
| FOMO candidate with confident `fomo_next` | Prefer that action. `PREPARE_NOTE` is a research note only, never a buy |

`PREPARE_REPLY` is **not** a buy signal. On-chain checks (bubblemaps, liquidity, deployer, cluster) stay with Grok Bot or a human after `RESEARCH_CA` / `WATCH_CLUSTER`. Jev only classifies.

```bash
python -m xinfluencer_os.scripts.shadow_jev --demo --fomo --mock-api
```

This integration does not execute trades or wallet actions.

Orchestrator hook (`main.py`): every feed/search tweet is classified **before** reply generation. If the route is not `PREPARE_REPLY`, if shadow mode is on, or if the route is `REVIEW`, posting is skipped. Auto-post paths stay disabled. FOMO routes never post and never buy.

## Tests

```bash
python -m pytest xinfluencer_os/tests
```

Unit tests mock HTTP. They pass without `TYPESAFE_API_KEY` and never call X.

## Live X actions

Live like / bookmark / reply / repost / follow / DM / delete require an **explicit future approval** path (Telegram human-in-the-loop, then `BrowserOperator`). This PR does not turn that on.
