"""Google Calendar sync for TimeFinder."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from timefinder.candidates import format_ics_datetime
from timefinder.google_auth import build_google_service
from timefinder.ics_review import parse_ics_file


def _parse_ics_datetime(value: str) -> datetime:
    digits = value.strip()[:15]
    return datetime.strptime(digits, "%Y%m%dT%H%M%S")


def events_from_ics(path: str) -> list[dict[str, Any]]:
    """Extract calendar events from an ICS file."""
    _preamble, ics_events = parse_ics_file(path)
    events = []
    for item in ics_events:
        if item.removed or not item.dtstart or not item.dtend:
            continue
        events.append(
            {
                "title": item.summary or "Work Journal Entry",
                "start_time": _parse_ics_datetime(item.dtstart).isoformat(timespec="seconds"),
                "end_time": _parse_ics_datetime(item.dtend).isoformat(timespec="seconds"),
                "summary": item.description or "",
            }
        )
    return events


def events_from_json(path: str, approved_only: bool = True) -> list[dict[str, Any]]:
    """Extract calendar events from TimeFinder candidate JSON."""
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    candidates = payload.get("candidates", payload if isinstance(payload, list) else [])
    events = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        status = candidate.get("status", "pending_review")
        if approved_only and status not in {"approved", "pending_review"}:
            continue
        if approved_only and status == "pending_review":
            continue
        if "start_time" not in candidate or "end_time" not in candidate:
            continue
        events.append(
            {
                "title": candidate.get("title", "Work Journal Entry"),
                "start_time": candidate["start_time"],
                "end_time": candidate["end_time"],
                "summary": candidate.get("summary", ""),
            }
        )
    return events


def load_sync_events(path: str) -> list[dict[str, Any]]:
    """Load events to sync from JSON or ICS input."""
    expanded = str(Path(path).expanduser())
    suffix = Path(expanded).suffix.lower()
    if suffix == ".json":
        return events_from_json(expanded, approved_only=True)
    if suffix in {".ics", ".ical"}:
        return events_from_ics(expanded)
    raise ValueError(f"Unsupported sync input format: {suffix}")


def to_google_event_body(event: dict[str, Any]) -> dict[str, Any]:
    """Convert internal event dict to Google Calendar API body."""
    start_dt = datetime.fromisoformat(event["start_time"])
    end_dt = datetime.fromisoformat(event["end_time"])
    return {
        "summary": event["title"],
        "description": event.get("summary", ""),
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }


def run_sync_google(path: str, calendar_id: str = "primary") -> int:
    """Sync approved events to Google Calendar."""
    try:
        events = load_sync_events(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error loading sync input: {exc}")
        return 1

    if not events:
        print("No approved events found to sync.")
        return 1

    try:
        service = build_google_service("calendar", "v3")
    except (ImportError, FileNotFoundError, RuntimeError) as exc:
        print(exc)
        return 1

    created = 0
    for event in events:
        body = to_google_event_body(event)
        service.events().insert(calendarId=calendar_id, body=body).execute()
        created += 1
        print(f"  Created: {event['title']} ({event['start_time']})")

    print(f"Synced {created} events to Google Calendar ({calendar_id}).")
    return 0
