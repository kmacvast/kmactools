"""Shared Google OAuth helpers for TimeFinder Gmail and Calendar."""
from __future__ import annotations

import json
import os
from pathlib import Path

CACHE_DIR = os.path.expanduser("~/.timefinder_cache")
TOKEN_PATH = os.path.join(CACHE_DIR, "google_token.json")
CLIENT_SECRET_PATH = os.path.join(CACHE_DIR, "google_client_secret.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def _require_google_libs():
    """Import Google API libraries or raise a clear error."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Google integration requires google-auth, google-auth-oauthlib, "
            "and google-api-python-client. Install with: "
            "pip install google-auth google-auth-oauthlib google-api-python-client"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def run_setup_google_auth() -> int:
    """Run browser OAuth flow and persist token (Gmail read + Calendar write)."""
    _Request, _Credentials, InstalledAppFlow, _build = _require_google_libs()

    secret_path = Path(CLIENT_SECRET_PATH)
    if not secret_path.is_file():
        print(
            f"Error: OAuth client secret not found at {CLIENT_SECRET_PATH}\n"
            "Download credentials from Google Cloud Console (Desktop app) and save as "
            "google_client_secret.json in ~/.timefinder_cache/\n"
            "Enable Gmail API and Google Calendar API on the project. "
            "See timefinder/SETUP_macOS.md (Step 4B) for Workspace setup."
        )
        return 1

    os.makedirs(CACHE_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0)
    Path(TOKEN_PATH).write_text(json.dumps(json.loads(creds.to_json()), indent=2) + "\n", encoding="utf-8")
    print(f"Google OAuth token saved to {TOKEN_PATH}")
    print("Scopes granted: Gmail (read-only), Google Calendar (events)")
    return 0


def load_credentials():
    """Load stored Google OAuth credentials, refreshing if expired."""
    Request, Credentials, _InstalledAppFlow, _build = _require_google_libs()
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
        raise RuntimeError(
            "Google credentials invalid or missing required scopes. Run --setup-google-auth again."
        )
    return creds


def build_google_service(api: str, version: str):
    """Build a Google API service client."""
    _Request, _Credentials, _InstalledAppFlow, build = _require_google_libs()
    creds = load_credentials()
    return build(api, version, credentials=creds)


def has_google_token() -> bool:
    """Return True if a Google OAuth token file exists."""
    return Path(TOKEN_PATH).is_file()
