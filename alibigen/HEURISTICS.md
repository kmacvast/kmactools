# AlibiGen Candidate Selection Heuristics

This document describes the deterministic pipeline inside `get_alibigen_candidates.py`. The script converts local Slack backup JSON into proposed work-journal calendar entries using **rules only** — no LLMs, no network calls, no external APIs.

For setup and day-to-day usage, see [README.md](README.md).

---

## Overview

`get_alibigen_candidates.py` is a **100% local, privacy-first, rule-based engine**. It:

1. Reads Slack message backups from `~/.alibigen_cache/slack_*.json`
2. Normalizes and deduplicates messages within the `--lookback-days` window
3. Groups messages into conversation clusters
4. Scores each cluster for work meaningfulness
5. Generates calendar candidate records for clusters above `--min-confidence`
6. Merges duplicate workstreams that appear across channels
7. Writes review files (`calendar_candidates.json`, `.md`, `.ics`)

Every run with the same input files and `--date` produces identical output.

### End-to-end pipeline

```
load_slack_files
  → dedupe_messages
  → group_messages
  → score_group_meaningfulness   (per group)
  → generate_candidate_entry     (passing groups only)
  → dedupe_candidates
  → write outputs
```

---

## Phase 0: Load and deduplicate (pre-filter)

Before any scoring, messages are loaded and normalized:

- **Source files:** `slack_{channel}_{YYYY-MM-DD}.json` in `--input-dir`
- **Lookback window:** messages with timestamps `>= reference_date - lookback_days`
- **Normalization:** each message becomes a `NormalizedMessage` with timestamp, user, text, channel, thread metadata, and flags for files/links/code blocks
- **User names:** resolved via `--user-map` (`slack_users.json`) when available

**Message deduplication:** if the same `(channel, ts)` appears in multiple dated backup snapshots, the copy from the **newest backup date** is kept.

This phase does not filter trivial content — it only prepares a clean timeline.

---

## Phase 1: The noise filter

Trivial chatter is detected by `is_trivial_text()` using `TRIVIAL_RE`:

```regex
^(lol|thanks|thank you|yep|yeah|yes|ok|okay|sounds good|sg|manana|
  👍|👌|🙏|nice|cool|got it|will do|done|np|no problem)[.!\s]*$
```

(case-insensitive; trailing punctuation/whitespace allowed)

Additional trivial rules:

- Empty or whitespace-only text
- Very short replies: `y`, `k`, `ok` (≤ 3 characters)

### Important: groups are scored, not individual messages

The noise filter is applied **inside `score_group_meaningfulness()` at the group level**:

| Group composition | Result |
|-------------------|--------|
| All messages trivial | **Rejected** (`all trivial messages`, score forced to 0.0) |
| Mix of trivial + substantive | **Kept** — "yep" or "thanks" inside a real thread does not disqualify the group |
| Single short non-trivial message, no work signals | **Rejected** with exclusion reason `single short message without work signals` |

Substantive messages are those that fail `is_trivial_text()`. Trivial-only groups never become candidates regardless of score.

---

## Phase 2: Conversation clustering

`group_messages()` builds `MessageGroup` clusters in two passes.

### Pass 1 — Slack threads

Messages with a `thread_ts` field are grouped by `(channel, thread_ts)`. This includes:

- Thread parents (`ts == thread_ts`)
- Thread replies (`thread_ts` points to the parent)

Each thread becomes one group regardless of reply span duration.

### Pass 2 — Non-threaded orphans

Messages not assigned in Pass 1 are grouped **per channel** using a greedy time window:

- Default window: **`--cluster-window-minutes`** (60 minutes)
- Messages sorted by timestamp
- A new cluster starts when the gap from the **first message in the current cluster** exceeds the window

Orphans in the same channel within the window become one group even without explicit Slack threading.

### What clustering does not do

- **No cross-channel clustering** at this stage — that happens in Phase 4 after candidates are generated
- **No semantic grouping** — grouping is structural (threads) or temporal (time window) only

---

## Phase 3: Weighted heuristic scoring

Each `MessageGroup` receives a confidence score from `score_group_meaningfulness()`. Points are additive; the final score is clamped to **`0.0 – 1.0`**.

### Scoring table

| Signal | Points | Condition |
|--------|--------|-----------|
| Multi-participant | **+0.15** | ≥ 2 distinct participants (display names) |
| Active thread | **+0.15** | `thread_ts` set and ≥ 3 messages in group |
| Parent with replies | **+0.15** | Any message has `reply_count >= 2` (when thread body not fully present) |
| Files, links, or code | **+0.10** | Any message has attachments/files, URL/attachment, or ` ``` ` code block |
| Work keywords | **+0.10 each, max +0.30** | Matches from `WORK_KEYWORDS` (up to 3 hits counted) |
| Entity / ticket IDs | **+0.15** | Matches `ENTITY_RE` (e.g. `PROJ-123`, `#12345`, `orion-378849`, `apple-openldap`) |
| Project/customer channel | **+0.10** | Channel name contains: `apple`, `orion`, `team`, `support`, `eng`, `rca`, `opp`, or `project` |
| Sustained conversation | **+0.10** | Span ≥ 15 minutes **and** ≥ 3 non-trivial messages |
| All trivial (penalty) | **−0.40** | Every message matches trivial filter → group rejected |

### Work keyword list (`WORK_KEYWORDS`)

```
rca, bug, ticket, customer, config, test, deploy, escalation, smb, ldap, mount,
outage, incident, fix, patch, review, investigation, troubleshoot, follow-up,
deliverable, blocker, action item, decision, root cause, support, engineering,
opportunity, deal, poc, production, staging, rollback, upgrade, performance,
latency, error, failure, houdini, vectordb, vector db
```

### Hard exclusions (regardless of partial score)

| Exclusion reason | When |
|------------------|------|
| `empty group` | No messages |
| `no text content` | All messages have empty text |
| `all trivial messages` | All messages match `TRIVIAL_RE` |
| `single short message without work signals` | Exactly 1 non-trivial message, < 40 chars, no keywords, no entity match, no files/links |

### `--min-confidence` cutoff

Default: **`0.65`**

After scoring:

```
if confidence < min_confidence → excluded (reason: "below min-confidence")
if exclusion reason set AND confidence < min_confidence → excluded with specific reason
else → generate_candidate_entry()
```

Raise `--min-confidence` (e.g. `0.70`) for fewer, higher-trust candidates. Lower it for more inclusive output.

Use `--include-trivial-debug` to write excluded groups to `trivial_excluded.json` for tuning.

---

## Phase 4: Cross-channel deduplication

After individual candidates are generated, `dedupe_candidates()` merges groups that likely describe the **same workstream** across different channels.

### Keyword Jaccard similarity

`keyword_jaccard(a, b)` compares the `keywords` lists from two candidates:

1. Join keywords into text
2. Tokenize: lowercase alphanumeric tokens, length > 2, stopwords removed
3. Compute Jaccard index: `|A ∩ B| / |A ∪ B|`

### Merge conditions (`should_merge_candidates`)

Two candidates merge if **either**:

| Rule | Requirement |
|------|-------------|
| **A** | Jaccard ≥ **0.4** AND (time overlap ≥ 30 min OR same calendar day) |
| **B** | Shared participant(s) AND Jaccard ≥ **0.25** AND (time overlap ≥ 30 min OR same calendar day) |

Time overlap requires at least **30 minutes** of shared range (`times_overlap()`).

### Merge behavior (`merge_candidates`)

When merged:

- **Union** of channels, source files, participants, keywords, and `why_included` reasons
- **Time span** expands to earliest start → latest end
- **Evidence** combined and capped at 5 excerpts
- **Title/summary/confidence** kept from the higher-confidence candidate
- New deterministic `id` computed from merged metadata

Candidates are processed in descending confidence order so stronger entries absorb weaker ones.

> **Known limitation:** merged time spans are **not** re-capped at `--max-duration`. A merged entry can exceed 120 minutes; trim manually after import if needed.

---

## Phase 5: Time normalization

`compute_event_times()` converts a message group's timestamp span into calendar start/end times.

### When the conversation span is long enough

If `(last_message - first_message) >= min_duration` (default **15 min**):

- **Start** = first message timestamp
- **End** = last message timestamp

### When the span is shorter than `min_duration`

The group is **padded** around its midpoint:

- Midpoint = halfway between first and last message
- Window = **`max(min_duration, 30)` minutes** total (default: 30-minute block)
- Start/end centered on midpoint

### Duration clamps

| Clamp | Default | Behavior |
|-------|---------|----------|
| `--min-duration` | 15 min | If computed duration is shorter, extend end time |
| `--max-duration` | 120 min | If computed duration is longer, cap end time |

No all-day events are generated.

---

## Candidate output fields

Each passing group becomes a JSON candidate with:

| Field | Source |
|-------|--------|
| `title` | `Work Journal: {channel_to_title}` + optional keyword suffix |
| `summary` | First non-trivial message excerpt (redacted) |
| `confidence` | Phase 3 score (rounded to 2 decimals) |
| `why_included` | Human-readable list of scoring signals triggered |
| `evidence` | Up to 5 redacted message excerpts |
| `keywords` | Work keyword + entity extractions |
| `id` | SHA-256 (first 16 hex chars) of title + start + channels + participants |

All candidates are written with `"status": "pending_review"`.

Channel title templates (hardcoded in `channel_to_title()`):

| Channel slug | Title fragment |
|--------------|----------------|
| `apple-ai-vectordb-opp` | Apple Vector DB Opportunity |
| `apple-openldap` | Apple OpenLDAP Follow-up |
| `orion-378849-macos-houdini` | Apple Houdini SMB Investigation |
| `team_fred` | Internal RCA Coordination |
| *(other)* | Slug split on `-`/`_`, title-cased |

---

## Tunable CLI parameters

| Flag | Default | Affects |
|------|---------|---------|
| `--lookback-days` | 7 | Input message window |
| `--cluster-window-minutes` | 60 | Phase 2 orphan clustering |
| `--min-confidence` | 0.65 | Phase 3 cutoff |
| `--min-duration` | 15 | Phase 5 padding floor |
| `--max-duration` | 120 | Phase 5 cap (per candidate, before merge) |
| `--date` | today | Reference date for lookback and determinism |

---

## Security and privacy

- Scoring and summarization run entirely on local backup files
- `redact_text()` strips obvious secrets from summaries and evidence
- Full raw messages are never written to candidate output
- No data leaves the machine during candidate generation

---

## Future extension points

The script header notes planned optional enhancements:

- AI summarization/classification (not implemented)
- Direct Google Calendar API push (not implemented; ICS import is the current path)

The scoring and grouping functions are designed as pure, testable units so new signals can be added without changing the overall pipeline shape.

---

[← Back to AlibiGen README](README.md)
