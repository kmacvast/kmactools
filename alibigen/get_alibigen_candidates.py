#!/usr/bin/env python3
"""Generate work-journal calendar candidates from local Slack backup JSON.

Usage:
  ./get_alibigen_candidates.py
  ./get_alibigen_candidates.py --lookback-days 7
  ./get_alibigen_candidates.py --min-confidence 0.65
  ./get_alibigen_candidates.py --date 2026-06-22
  ./get_alibigen_candidates.py --include-trivial-debug
  ./get_alibigen_candidates.py --dry-run --verbose

Outputs (default ~/.alibigen_cache/calendar_review/):
  calendar_candidates.json
  calendar_candidates.md
  calendar_candidates.ics

TODO: Google Calendar integration (pending_review -> approved -> create event)
TODO: Optional AI summarization/classification extension point
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

DEFAULT_INPUT_DIR = os.path.expanduser("~/.alibigen_cache")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.alibigen_cache/calendar_review")
DEFAULT_USER_MAP_PATH = os.path.expanduser("~/.alibigen_cache/slack_users.json")

SLACK_FILE_RE = re.compile(r"^slack_(.+)_(\d{4}-\d{2}-\d{2})\.json$")
TRIVIAL_RE = re.compile(
    r"^(lol|thanks|thank you|yep|yeah|yes|ok|okay|sounds good|sg|manana|"
    r"👍|👌|🙏|nice|cool|got it|will do|done|np|no problem)[.!\\s]*$",
    re.IGNORECASE,
)
WORK_KEYWORDS = {
    "rca", "bug", "ticket", "customer", "config", "test", "deploy", "escalation",
    "smb", "ldap", "mount", "outage", "incident", "fix", "patch", "review",
    "investigation", "troubleshoot", "follow-up", "follow up", "deliverable",
    "blocker", "action item", "decision", "root cause", "support", "engineering",
    "opportunity", "deal", "poc", "production", "staging", "rollback", "upgrade",
    "performance", "latency", "error", "failure", "houdini", "vectordb", "vector db",
}
ENTITY_RE = re.compile(
    r"\b[A-Z]{2,10}-\d+\b|#\d{4,}|orion[-_]\d+|apple[-_]\w+",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
CODE_BLOCK_RE = re.compile(r"```")
REDACT_PATTERNS = [
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]+"), "xox[REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(password|passwd|api_key|apikey|secret|token)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}\b"), "[REDACTED_BLOB]"),
]
STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is",
    "it", "this", "that", "we", "i", "you", "are", "was", "be", "at", "as", "from",
}


@dataclass
class NormalizedMessage:
    """Internal normalized Slack message."""

    ts: datetime
    ts_raw: str
    user: str
    user_display: str
    text: str
    channel: str
    source_file: str
    backup_date: str
    thread_ts: str | None = None
    reply_count: int = 0
    has_files: bool = False
    has_links: bool = False
    has_code: bool = False


@dataclass
class MessageGroup:
    """Cluster of related messages."""

    messages: list[NormalizedMessage] = field(default_factory=list)
    channel: str = ""
    thread_ts: str | None = None

    @property
    def participants(self) -> list[str]:
        seen = set()
        ordered = []
        for message in self.messages:
            name = message.user_display
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    @property
    def source_files(self) -> list[str]:
        return sorted({message.source_file for message in self.messages})

    @property
    def start(self) -> datetime:
        return min(message.ts for message in self.messages)

    @property
    def end(self) -> datetime:
        return max(message.ts for message in self.messages)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate work-journal calendar candidates from Slack backups.",
    )
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--user-map", default=DEFAULT_USER_MAP_PATH)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--cluster-window-minutes", type=int, default=60)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--min-duration", type=int, default=15)
    parser.add_argument("--max-duration", type=int, default=120)
    parser.add_argument("--date", dest="reference_date", help="Reference date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-ics", action="store_true")
    parser.add_argument("--include-trivial-debug", action="store_true")
    return parser.parse_args(argv)


def configure_logging(verbose: bool, debug: bool) -> None:
    """Configure stderr logging."""
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", stream=sys.stderr)


def parse_slack_timestamp(ts_value: str | float) -> datetime:
    """Convert Slack ts string to local datetime."""
    return datetime.fromtimestamp(float(ts_value))


def load_user_name_map(path: str) -> dict[str, str]:
    """Load optional Slack user id -> display name map."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return {}
    try:
        with open(expanded, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("Could not load user map %s: %s", expanded, exc)
    return {}


def resolve_user(user_id: str | None, name_map: dict[str, str]) -> str:
    """Resolve user id to display name when available."""
    if not user_id:
        return "unknown"
    return name_map.get(user_id, user_id)


def redact_text(text: str) -> str:
    """Redact obvious secrets from message text."""
    redacted = text
    for pattern, replacement in REDACT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def parse_channel_from_filename(filename: str) -> tuple[str, str] | None:
    """Extract channel name and backup date from a slack backup filename."""
    match = SLACK_FILE_RE.match(os.path.basename(filename))
    if not match:
        return None
    return match.group(1), match.group(2)


def is_trivial_text(text: str) -> bool:
    """Return True if message text is trivial chatter."""
    cleaned = text.strip()
    if not cleaned:
        return True
    if len(cleaned) <= 3 and cleaned.lower() in {"y", "k", "ok"}:
        return True
    return bool(TRIVIAL_RE.match(cleaned))


def normalize_message(
    raw: dict[str, Any],
    channel: str,
    source_file: str,
    backup_date: str,
    name_map: dict[str, str],
) -> NormalizedMessage | None:
    """Normalize a raw Slack message dict."""
    ts_raw = raw.get("ts")
    if not ts_raw:
        return None
    text = raw.get("text") or ""
    user_id = raw.get("user") or "unknown"
    return NormalizedMessage(
        ts=parse_slack_timestamp(ts_raw),
        ts_raw=str(ts_raw),
        user=user_id,
        user_display=resolve_user(user_id, name_map),
        text=text,
        channel=channel,
        source_file=source_file,
        backup_date=backup_date,
        thread_ts=raw.get("thread_ts"),
        reply_count=int(raw.get("reply_count") or 0),
        has_files=bool(raw.get("files")),
        has_links=bool(URL_RE.search(text) or raw.get("attachments")),
        has_code=bool(CODE_BLOCK_RE.search(text)),
    )


def load_slack_files(
    input_dir: str,
    lookback_days: int,
    reference_date: datetime,
    name_map: dict[str, str],
) -> list[NormalizedMessage]:
    """Load and normalize Slack messages within the lookback window."""
    pattern = os.path.join(os.path.expanduser(input_dir), "slack_*.json")
    cutoff = reference_date - timedelta(days=lookback_days)
    messages: list[NormalizedMessage] = []

    for path in sorted(glob.glob(pattern)):
        parsed = parse_channel_from_filename(path)
        if not parsed:
            logging.debug("Skipping unrecognized filename: %s", path)
            continue
        channel, backup_date = parsed
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw_messages = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logging.warning("Skipping malformed file %s: %s", path, exc)
            continue
        if not isinstance(raw_messages, list):
            logging.warning("Skipping non-list JSON in %s", path)
            continue

        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            normalized = normalize_message(raw, channel, path, backup_date, name_map)
            if normalized and normalized.ts >= cutoff:
                messages.append(normalized)

    return messages


def dedupe_messages(messages: list[NormalizedMessage]) -> list[NormalizedMessage]:
    """Deduplicate by channel+ts, keeping the newest backup snapshot."""
    best: dict[tuple[str, str], NormalizedMessage] = {}
    for message in messages:
        key = (message.channel, message.ts_raw)
        existing = best.get(key)
        if existing is None or message.backup_date >= existing.backup_date:
            best[key] = message
    return sorted(best.values(), key=lambda item: item.ts)


def group_messages(
    messages: list[NormalizedMessage],
    cluster_window_minutes: int,
) -> list[MessageGroup]:
    """Group messages into conversation clusters."""
    if not messages:
        return []

    assigned: set[str] = set()
    groups: list[MessageGroup] = []

    thread_buckets: dict[tuple[str, str], list[NormalizedMessage]] = {}
    for message in messages:
        if message.thread_ts:
            key = (message.channel, message.thread_ts)
            thread_buckets.setdefault(key, []).append(message)

    for (channel, thread_ts), bucket in sorted(thread_buckets.items()):
        bucket.sort(key=lambda item: item.ts)
        groups.append(MessageGroup(messages=bucket, channel=channel, thread_ts=thread_ts))
        assigned.update(message.ts_raw for message in bucket)

    orphans = [message for message in messages if message.ts_raw not in assigned]
    orphans_by_channel: dict[str, list[NormalizedMessage]] = {}
    for message in orphans:
        orphans_by_channel.setdefault(message.channel, []).append(message)

    window = timedelta(minutes=cluster_window_minutes)
    for channel, channel_messages in orphans_by_channel.items():
        channel_messages.sort(key=lambda item: item.ts)
        current: list[NormalizedMessage] = []
        cluster_start: datetime | None = None
        for message in channel_messages:
            if not current:
                current = [message]
                cluster_start = message.ts
                continue
            if message.ts - cluster_start <= window:
                current.append(message)
            else:
                groups.append(MessageGroup(messages=current, channel=channel))
                current = [message]
                cluster_start = message.ts
        if current:
            groups.append(MessageGroup(messages=current, channel=channel))

    return groups


def extract_keywords(group: MessageGroup) -> list[str]:
    """Extract notable keywords from a message group."""
    found: list[str] = []
    seen = set()
    combined = " ".join(message.text for message in group.messages).lower()
    for keyword in sorted(WORK_KEYWORDS, key=len, reverse=True):
        if keyword in combined and keyword not in seen:
            seen.add(keyword)
            found.append(keyword.title() if keyword.islower() else keyword)
    for match in ENTITY_RE.finditer(combined):
        token = match.group(0)
        if token.lower() not in seen:
            seen.add(token.lower())
            found.append(token)
    return found[:8]


def channel_to_title(channel: str) -> str:
    """Convert channel slug to a readable title fragment."""
    templates = {
        "apple-ai-vectordb-opp": "Apple Vector DB Opportunity",
        "apple-openldap": "Apple OpenLDAP Follow-up",
        "orion-378849-macos-houdini": "Apple Houdini SMB Investigation",
        "team_fred": "Internal RCA Coordination",
    }
    if channel in templates:
        return templates[channel]
    parts = re.split(r"[-_]+", channel)
    return " ".join(part.capitalize() for part in parts if part)


def is_project_channel(channel: str) -> bool:
    """Heuristic: channel name suggests work context."""
    markers = ("apple", "orion", "team", "support", "eng", "rca", "opp", "project")
    lowered = channel.lower()
    return any(marker in lowered for marker in markers)


def score_group_meaningfulness(group: MessageGroup) -> tuple[float, list[str], str | None]:
    """Score a message group for work meaningfulness."""
    if not group.messages:
        return 0.0, [], "empty group"

    texts = [message.text.strip() for message in group.messages if message.text.strip()]
    non_trivial = [text for text in texts if not is_trivial_text(text)]

    if not texts:
        return 0.0, [], "no text content"
    if len(texts) >= 1 and not non_trivial:
        return 0.0, [], "all trivial messages"

    score = 0.0
    why: list[str] = []

    participants = group.participants
    if len(participants) >= 2:
        score += 0.15
        why.append(f"Multi-participant ({len(participants)} people)")

    if group.thread_ts and len(group.messages) >= 3:
        score += 0.15
        why.append(f"Thread with {len(group.messages)} messages")
    elif any(message.reply_count >= 2 for message in group.messages):
        score += 0.15
        why.append("Parent message with multiple replies")

    if any(message.has_files or message.has_links or message.has_code for message in group.messages):
        score += 0.10
        why.append("Contains files, links, or code blocks")

    keyword_hits = extract_keywords(group)
    if keyword_hits:
        boost = min(0.30, 0.10 * min(len(keyword_hits), 3))
        score += boost
        why.append(f"Work keywords: {', '.join(keyword_hits[:3])}")

    combined = " ".join(texts)
    if ENTITY_RE.search(combined):
        score += 0.15
        why.append("Contains ticket/project/customer identifiers")

    if is_project_channel(group.channel):
        score += 0.10
        why.append(f"Project/customer channel: {group.channel}")

    span_minutes = (group.end - group.start).total_seconds() / 60
    if span_minutes >= 15 and len(non_trivial) >= 3:
        score += 0.10
        why.append("Sustained conversation over 15+ minutes")

    if len(texts) >= 1 and len(non_trivial) == 0:
        score -= 0.40
        return max(0.0, min(score, 1.0)), why, "all trivial messages"

    if len(group.messages) == 1 and len(non_trivial) == 1:
        single = non_trivial[0]
        if (
            len(single) < 40
            and not keyword_hits
            and not ENTITY_RE.search(single)
            and not any(message.has_files or message.has_links for message in group.messages)
        ):
            return score, why, "single short message without work signals"

    return max(0.0, min(score, 1.0)), why, None


def build_summary(group: MessageGroup, keywords: list[str]) -> str:
    """Build a concise summary from group content."""
    substantive = [
        redact_text(message.text.strip())
        for message in group.messages
        if message.text.strip() and not is_trivial_text(message.text)
    ]
    if substantive:
        excerpt = substantive[0]
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + "..."
        channel_title = channel_to_title(group.channel)
        return f"{channel_title}: {excerpt}"
    return f"Work activity in {channel_to_title(group.channel)} ({', '.join(keywords[:3])})"


def compute_event_times(
    group: MessageGroup,
    min_duration: int,
    max_duration: int,
) -> tuple[datetime, datetime, int]:
    """Compute calendar start/end times for a group."""
    span = group.end - group.start
    span_minutes = max(int(span.total_seconds() // 60), 0)

    if span_minutes >= min_duration:
        start = group.start
        end = group.end
    else:
        midpoint = group.start + span / 2
        half = timedelta(minutes=max(min_duration, 30) / 2)
        start = midpoint - half
        end = midpoint + half

    duration = int((end - start).total_seconds() // 60)
    if duration < min_duration:
        end = start + timedelta(minutes=min_duration)
        duration = min_duration
    if duration > max_duration:
        end = start + timedelta(minutes=max_duration)
        duration = max_duration

    return start, end, duration


def stable_candidate_id(title: str, start_time: datetime, channels: list[str], participants: list[str]) -> str:
    """Generate deterministic candidate id."""
    payload = "|".join(
        [
            title.lower().strip(),
            start_time.isoformat(timespec="seconds"),
            ",".join(sorted(channels)),
            ",".join(sorted(participants)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_evidence(group: MessageGroup, limit: int = 5) -> list[dict[str, str]]:
    """Build redacted evidence excerpts from a group."""
    evidence = []
    for message in sorted(group.messages, key=lambda item: item.ts):
        text = message.text.strip()
        if not text:
            continue
        excerpt = redact_text(text)
        if len(excerpt) > 120:
            excerpt = excerpt[:117] + "..."
        evidence.append(
            {
                "timestamp": message.ts.isoformat(timespec="seconds"),
                "channel": message.channel,
                "user": message.user_display,
                "text_excerpt": excerpt,
            }
        )
        if len(evidence) >= limit:
            break
    return evidence


def generate_candidate_entry(
    group: MessageGroup,
    confidence: float,
    why_included: list[str],
    min_duration: int,
    max_duration: int,
) -> dict[str, Any]:
    """Generate a calendar candidate dict from a scored group."""
    keywords = extract_keywords(group)
    title_core = channel_to_title(group.channel)
    if keywords:
        extra = keywords[0]
        if extra.lower() not in title_core.lower():
            title_core = f"{title_core} ({extra})"
    title = f"Work Journal: {title_core}"

    start, end, duration = compute_event_times(group, min_duration, max_duration)
    participants = group.participants
    channels = sorted({message.channel for message in group.messages})

    return {
        "id": stable_candidate_id(title, start, channels, participants),
        "status": "pending_review",
        "title": title,
        "start_time": start.isoformat(timespec="seconds"),
        "end_time": end.isoformat(timespec="seconds"),
        "duration_minutes": duration,
        "confidence": round(confidence, 2),
        "summary": build_summary(group, keywords),
        "why_included": why_included,
        "source_channels": channels,
        "source_files": group.source_files,
        "participants": participants,
        "keywords": keywords,
        "message_count": len(group.messages),
        "evidence": build_evidence(group),
        "redactions_applied": True,
    }


def tokenize_for_dedupe(text: str) -> set[str]:
    """Normalize text into tokens for similarity comparison."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in tokens if token not in STOPWORDS and len(token) > 2}


def keyword_jaccard(a: list[str], b: list[str]) -> float:
    """Compute Jaccard similarity between keyword lists."""
    set_a = tokenize_for_dedupe(" ".join(a))
    set_b = tokenize_for_dedupe(" ".join(b))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def times_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Return True if two time ranges overlap by at least 30 minutes."""
    overlap_start = max(start_a, start_b)
    overlap_end = min(end_a, end_b)
    if overlap_end <= overlap_start:
        return False
    return (overlap_end - overlap_start).total_seconds() >= 30 * 60


def merge_candidates(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """Merge two duplicate candidates into one."""
    merged = dict(primary)
    merged["source_channels"] = sorted(set(primary["source_channels"]) | set(secondary["source_channels"]))
    merged["source_files"] = sorted(set(primary["source_files"]) | set(secondary["source_files"]))
    merged["participants"] = sorted(set(primary["participants"]) | set(secondary["participants"]))
    merged["keywords"] = sorted(set(primary["keywords"]) | set(secondary["keywords"]))
    merged["message_count"] = primary["message_count"] + secondary["message_count"]
    merged["why_included"] = sorted(set(primary["why_included"]) | set(secondary["why_included"]))

    start_a = datetime.fromisoformat(primary["start_time"])
    end_a = datetime.fromisoformat(primary["end_time"])
    start_b = datetime.fromisoformat(secondary["start_time"])
    end_b = datetime.fromisoformat(secondary["end_time"])
    start = min(start_a, start_b)
    end = max(end_a, end_b)
    merged["start_time"] = start.isoformat(timespec="seconds")
    merged["end_time"] = end.isoformat(timespec="seconds")
    merged["duration_minutes"] = int((end - start).total_seconds() // 60)

    evidence = primary["evidence"] + secondary["evidence"]
    seen = set()
    unique_evidence = []
    for item in evidence:
        key = (item["timestamp"], item["text_excerpt"])
        if key in seen:
            continue
        seen.add(key)
        unique_evidence.append(item)
    merged["evidence"] = unique_evidence[:5]

    if secondary["confidence"] > primary["confidence"]:
        merged["title"] = secondary["title"]
        merged["summary"] = secondary["summary"]
        merged["confidence"] = secondary["confidence"]

    merged["id"] = stable_candidate_id(
        merged["title"],
        datetime.fromisoformat(merged["start_time"]),
        merged["source_channels"],
        merged["participants"],
    )
    return merged


def should_merge_candidates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if two candidates represent the same workstream."""
    start_a = datetime.fromisoformat(a["start_time"])
    end_a = datetime.fromisoformat(a["end_time"])
    start_b = datetime.fromisoformat(b["start_time"])
    end_b = datetime.fromisoformat(b["end_time"])

    same_day = start_a.date() == start_b.date()
    overlap = times_overlap(start_a, end_a, start_b, end_b)
    jaccard = keyword_jaccard(a["keywords"], b["keywords"])
    shared_participants = set(a["participants"]) & set(b["participants"])

    if jaccard >= 0.4 and (overlap or same_day):
        return True
    if shared_participants and (overlap or same_day) and jaccard >= 0.25:
        return True
    return False


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge overlapping cross-channel candidates."""
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda item: item["confidence"], reverse=True)
    merged: list[dict[str, Any]] = []

    for candidate in ordered:
        absorbed = False
        for index, existing in enumerate(merged):
            if should_merge_candidates(existing, candidate):
                merged[index] = merge_candidates(existing, candidate)
                absorbed = True
                break
        if not absorbed:
            merged.append(candidate)

    return sorted(merged, key=lambda item: item["start_time"])


def write_json_output(candidates: list[dict[str, Any]], path: str) -> None:
    """Write candidates JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_markdown_output(candidates: list[dict[str, Any]], path: str) -> None:
    """Write human-readable markdown review file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["# Calendar Candidates", ""]
    if not candidates:
        lines.append("_No meaningful candidates found._")
    for candidate in candidates:
        lines.extend(
            [
                f"## [{candidate['status']}] {candidate['title']}",
                "",
                f"**Time:** {candidate['start_time']} -> {candidate['end_time']}",
                f"**Duration:** {candidate['duration_minutes']} minutes",
                f"**Confidence:** {candidate['confidence']}",
                f"**Channels:** {', '.join(candidate['source_channels'])}",
                f"**Participants:** {', '.join(candidate['participants'])}",
                f"**Keywords:** {', '.join(candidate['keywords']) or 'n/a'}",
                "",
                "### Summary",
                candidate["summary"],
                "",
                "### Why included",
            ]
        )
        for reason in candidate["why_included"]:
            lines.append(f"- {reason}")
        lines.extend(["", "### Evidence"])
        for item in candidate["evidence"]:
            lines.append(
                f"- `{item['timestamp']}` **{item['channel']}** ({item['user']}): {item['text_excerpt']}"
            )
        lines.extend(["", "### Source files"])
        for source in candidate["source_files"]:
            lines.append(f"- `{source}`")
        lines.extend(["", "---", ""])
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def format_ics_datetime(dt: datetime) -> str:
    """Format datetime for ICS DTSTART/DTEND."""
    return dt.strftime("%Y%m%dT%H%M%S")


def ics_escape(text: str) -> str:
    """Escape text for ICS fields."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def write_ics_output(candidates: list[dict[str, Any]], path: str) -> None:
    """Write basic ICS calendar file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AlibiGen//Slack Calendar Candidates//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for candidate in candidates:
        uid = f"{candidate['id']}@alibigen.local"
        start = datetime.fromisoformat(candidate["start_time"])
        end = datetime.fromisoformat(candidate["end_time"])
        description = ics_escape(
            f"{candidate['summary']}\\n\\nConfidence: {candidate['confidence']}\\n"
            f"Status: {candidate['status']}"
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{format_ics_datetime(datetime.now())}",
                f"DTSTART:{format_ics_datetime(start)}",
                f"DTEND:{format_ics_datetime(end)}",
                f"SUMMARY:{ics_escape(candidate['title'])}",
                f"DESCRIPTION:{description}",
                "STATUS:TENTATIVE",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def process_slack_backups(
    input_dir: str,
    lookback_days: int,
    reference_date: datetime,
    name_map: dict[str, str],
    cluster_window_minutes: int,
    min_confidence: float,
    min_duration: int,
    max_duration: int,
    include_trivial_debug: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """End-to-end processing pipeline returning candidates and excluded groups."""
    messages = load_slack_files(input_dir, lookback_days, reference_date, name_map)
    messages = dedupe_messages(messages)
    groups = group_messages(messages, cluster_window_minutes)

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for group in groups:
        confidence, why, exclusion = score_group_meaningfulness(group)
        if exclusion and confidence < min_confidence:
            excluded.append(
                {
                    "channel": group.channel,
                    "confidence": round(confidence, 2),
                    "exclusion_reason": exclusion,
                    "message_count": len(group.messages),
                    "participants": group.participants,
                }
            )
            continue
        if confidence < min_confidence:
            excluded.append(
                {
                    "channel": group.channel,
                    "confidence": round(confidence, 2),
                    "exclusion_reason": "below min-confidence",
                    "message_count": len(group.messages),
                    "participants": group.participants,
                }
            )
            continue
        candidates.append(
            generate_candidate_entry(group, confidence, why, min_duration, max_duration)
        )

    return dedupe_candidates(candidates), excluded


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    configure_logging(args.verbose, args.debug)

    if args.reference_date:
        reference_date = datetime.strptime(args.reference_date, "%Y-%m-%d")
        reference_date = reference_date.replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    else:
        reference_date = datetime.now()

    name_map = load_user_name_map(args.user_map)
    candidates, excluded = process_slack_backups(
        input_dir=args.input_dir,
        lookback_days=args.lookback_days,
        reference_date=reference_date,
        name_map=name_map,
        cluster_window_minutes=args.cluster_window_minutes,
        min_confidence=args.min_confidence,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        include_trivial_debug=args.include_trivial_debug,
    )

    logging.info("Generated %d candidates (%d excluded)", len(candidates), len(excluded))
    if args.dry_run:
        print(f"Dry run: {len(candidates)} candidates, {len(excluded)} excluded")
        for candidate in candidates:
            print(f"  [{candidate['confidence']}] {candidate['title']} ({candidate['start_time']})")
        return 0

    output_dir = os.path.expanduser(args.output_dir)
    json_path = os.path.join(output_dir, "calendar_candidates.json")
    md_path = os.path.join(output_dir, "calendar_candidates.md")
    ics_path = os.path.join(output_dir, "calendar_candidates.ics")

    write_json_output(candidates, json_path)
    write_markdown_output(candidates, md_path)
    if not args.no_ics:
        write_ics_output(candidates, ics_path)
    if args.include_trivial_debug:
        debug_path = os.path.join(output_dir, "trivial_excluded.json")
        os.makedirs(output_dir, exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as handle:
            json.dump({"excluded_count": len(excluded), "excluded": excluded}, handle, indent=2)
            handle.write("\n")

    print(f"Wrote {len(candidates)} candidates to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
