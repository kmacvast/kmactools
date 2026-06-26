"""Google Calendar OAuth and sync for TimeFinder."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from timefinder.candidates import format_ics_datetime
from timefinder.ics_review import parse_ics_file

CACHE_DIR = os.path.expanduser("~/.timefinder_cache")
TOKEN_PATH = os.path.join(CACHE_DIR, "google_token.json")
CLIENT_SECRET_PATH = os.path.join(CACHE_DIR, "google_client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _require_google_libs():
    """Import Google API libraries or raise a clear error."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Google Calendar sync requires google-auth, google-auth-oauthlib, "
            "and google-api-python-client. Install with: "
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def run_setup_google_auth() -> int:
    """Run browser OAuth flow and persist token."""
    Request, Credentials, InstalledAppFlow, _build = _require_google_libs()

    secret_path = Path(CLIENT_SECRET_PATH)
    if not secret_path.is_file():
        print(
            f"Error: OAuth client secret not found at {CLIENT_SECRET_PATH}\n"
            "Download credentials from Google Cloud Console (Desktop app) and save as "
            "google_client_secret.json in ~/.timefinder_cache/"
        )
        return 1

    os.makedirs(CACHE_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_data = json.loads(creds.to_json())
    secret_path.parent.joinpath("google_token.json").write_text(
        json.dumps(token_data, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Google OAuth token saved to {TOKEN_PATH}")
    return 0


def load_credentials():
    """Load stored Google OAuth credentials."""
    Request, Credentials, InstalledAppFlow, _build = _require_google_libs()
    token_path = Path(TOKEN_PATH)
    if not token_path.is_file():
        raise FileNotFoundError(
            f"Google token not found at {TOKEN_PATH}. Run --setup-google-auth first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(json.dumps(json.loads(creds.to_json()), indent=2) + "\n", encoding="utf-8")
    if not creds or not creds.valid:
        raise RuntimeError("Google credentials invalid. Run --setup-google-auth again.")
    return creds


def build_calendar_service():
    """Build Google Calendar v3 service."""
    _Request, _Credentials, _InstalledAppFlow, build = _require_google_libs()
    creds = load_credentials()
    return build("calendar", "v3", credentials=creds)


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
        service = build_calendar_service()
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
