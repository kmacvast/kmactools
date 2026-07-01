"""Gmail message fetch helpers for TimeFinder."""
from __future__ import annotations

import base64
import email
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.timefinder_cache/gmail_config.json")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.timefinder_cache")
DEFAULT_IMPORT_DIR = os.path.expanduser("~/.timefinder_cache/gmail_import")

# IMAP folder names -> Gmail API system label IDs
IMAP_FOLDER_TO_LABEL = {
    "INBOX": "INBOX",
    "[Gmail]/Sent Mail": "SENT",
    "[Gmail]/Drafts": "DRAFT",
    "[Gmail]/All Mail": "ALL",
    "[Gmail]/Starred": "STARRED",
    "[Gmail]/Important": "IMPORTANT",
    "[Gmail]/Trash": "TRASH",
    "[Gmail]/Spam": "SPAM",
}


def decode_mime_header(value: str | None) -> str:
    """Decode a MIME-encoded email header value."""
    if not value:
        return ""
    parts = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return " ".join(parts).strip()


def extract_body_excerpt(msg: email.message.Message, limit: int = 500) -> str:
    """Extract a plain-text excerpt from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    return text.strip()[:limit]
        return ""
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()[:limit]


def folder_to_slug(folder: str) -> str:
    """Convert an IMAP folder or Gmail label to a filesystem-safe slug."""
    slug = folder.lower()
    slug = slug.replace("[gmail]/", "")
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_") or "folder"


def since_imap_date(dt: datetime) -> str:
    """Format a datetime for IMAP SINCE queries."""
    return dt.strftime("%d-%b-%Y")


def normalize_gmail_message(msg_id: str, folder: str, raw_bytes: bytes) -> dict:
    """Normalize a raw IMAP message into a JSON-serializable dict."""
    msg = email.message_from_bytes(raw_bytes)
    date_header = msg.get("Date")
    try:
        parsed_date = parsedate_to_datetime(date_header) if date_header else None
    except (TypeError, ValueError, OverflowError):
        parsed_date = None

    return {
        "id": msg_id,
        "folder": folder,
        "thread_id": msg.get("Thread-Index") or msg.get("In-Reply-To") or msg.get("Message-ID") or msg_id,
        "from": decode_mime_header(msg.get("From")),
        "to": decode_mime_header(msg.get("To")),
        "subject": decode_mime_header(msg.get("Subject")),
        "date": parsed_date.isoformat(timespec="seconds") if parsed_date else None,
        "snippet": extract_body_excerpt(msg, limit=200),
        "body_excerpt": extract_body_excerpt(msg, limit=500),
    }


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []
    return {item.get("name", ""): item.get("value", "") for item in headers if item.get("name")}


def _decode_api_body_data(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def extract_body_from_api_payload(payload: dict[str, Any], limit: int = 500) -> str:
    """Extract plain-text body from a Gmail API message payload."""
    if not payload:
        return ""
    body = payload.get("body") or {}
    if body.get("data") and payload.get("mimeType", "").startswith("text/plain"):
        return _decode_api_body_data(body["data"]).strip()[:limit]
    for part in payload.get("parts") or []:
        mime = part.get("mimeType", "")
        if mime == "text/plain" and part.get("body", {}).get("data"):
            return _decode_api_body_data(part["body"]["data"]).strip()[:limit]
    for part in payload.get("parts") or []:
        nested = extract_body_from_api_payload(part, limit=limit)
        if nested:
            return nested
    return ""


def normalize_gmail_api_message(msg: dict[str, Any], label: str) -> dict:
    """Normalize a Gmail API message resource into backup JSON shape."""
    headers = _header_map(msg.get("payload") or {})
    internal_ms = msg.get("internalDate")
    parsed_date = None
    if internal_ms:
        try:
            parsed_date = datetime.fromtimestamp(int(internal_ms) / 1000)
        except (TypeError, ValueError, OverflowError):
            parsed_date = None
    if parsed_date is None and headers.get("Date"):
        try:
            parsed_date = parsedate_to_datetime(headers["Date"])
        except (TypeError, ValueError, OverflowError):
            parsed_date = None

    body = extract_body_from_api_payload(msg.get("payload") or {}, limit=500)
    snippet = (msg.get("snippet") or body[:200]).strip()

    return {
        "id": msg.get("id", ""),
        "folder": label,
        "thread_id": msg.get("threadId") or headers.get("Message-ID") or msg.get("id", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": parsed_date.isoformat(timespec="seconds") if parsed_date else None,
        "snippet": snippet[:200],
        "body_excerpt": body[:500],
    }


def resolve_label_id(name: str) -> str:
    """Map config folder/label name to a Gmail API label ID."""
    return IMAP_FOLDER_TO_LABEL.get(name, name)


def has_import_sources(import_dir: str = DEFAULT_IMPORT_DIR) -> bool:
    """Return True if the import directory contains .eml or .mbox files."""
    from timefinder.gmail_import import discover_import_sources

    return bool(discover_import_sources(import_dir))


def _infer_auth_mode(
    explicit_auth: str,
    app_password: str,
    import_dir: str,
) -> str | None:
    """Infer Gmail auth mode without selecting OAuth when no token exists."""
    from timefinder.google_auth import has_google_token

    if explicit_auth in {"oauth", "imap", "import"}:
        auth = explicit_auth
    elif app_password:
        auth = "imap"
    elif has_import_sources(import_dir):
        auth = "import"
    elif has_google_token():
        auth = "oauth"
    else:
        return None

    if auth == "oauth" and not has_google_token():
        if has_import_sources(import_dir):
            return "import"
        return None
    if auth == "import" and not has_import_sources(import_dir):
        return None
    return auth


def _build_gmail_config(raw: dict[str, Any], *, required: bool = True) -> dict[str, Any]:
    """Build a normalized Gmail config dict from raw JSON."""
    email_address = raw.get("email", "")
    app_password = raw.get("app_password", "")
    explicit_auth = str(raw.get("auth", "")).lower().strip()
    import_dir = os.path.expanduser(raw.get("import_dir") or DEFAULT_IMPORT_DIR)
    labels = raw.get("labels") or raw.get("folders") or ["INBOX"]

    if explicit_auth and explicit_auth not in {"oauth", "imap", "import"}:
        raise ValueError(f"Unsupported gmail auth mode: {explicit_auth!r}. Use 'import', 'imap', or 'oauth'.")

    auth = _infer_auth_mode(explicit_auth, app_password, import_dir)
    if auth is None:
        if required:
            raise ValueError(
                "Gmail is not configured for gather. Use \"auth\": \"import\" with Takeout files, "
                "IMAP app_password, or OAuth with a saved token. See timefinder/SETUP_macOS.md Step 4."
            )
        return {}

    if auth == "import":
        return {"auth": "import", "email": email_address, "import_dir": import_dir}

    if auth == "imap":
        if not email_address or not app_password:
            raise ValueError("IMAP auth requires email and app_password in gmail_config.json.")
        return {
            "auth": "imap",
            "email": email_address,
            "folders": labels,
            "app_password": app_password,
        }

    return {
        "auth": "oauth",
        "email": email_address,
        "labels": [resolve_label_id(label) for label in labels],
    }


def resolve_gmail_gather_config(config_path=DEFAULT_CONFIG_PATH) -> dict[str, Any] | None:
    """Return Gmail config for gather, or None when Gmail should be skipped."""
    expanded = os.path.expanduser(config_path)
    if not os.path.exists(expanded):
        if has_import_sources(DEFAULT_IMPORT_DIR):
            return {"auth": "import", "email": "", "import_dir": DEFAULT_IMPORT_DIR}
        return None

    try:
        with open(expanded, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        config = _build_gmail_config(raw, required=False)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logging.warning("Gmail config unusable (%s); skipping Gmail gather.", exc)
        return None

    return config or None


def load_gmail_config(config_path=DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load Gmail configuration for IMAP, OAuth API, or local import."""
    logging.info("Loading Gmail configuration from: %s", config_path)
    expanded = os.path.expanduser(config_path)
    if not os.path.exists(expanded):
        if has_import_sources(DEFAULT_IMPORT_DIR):
            return {"auth": "import", "email": "", "import_dir": DEFAULT_IMPORT_DIR}
        msg = (
            f"Gmail configuration not found at {config_path}. "
            "See timefinder/SETUP_macOS.md Step 4 for auth options."
        )
        logging.error(msg)
        raise FileNotFoundError(msg)

    with open(expanded, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    return _build_gmail_config(raw, required=True)


def fetch_gmail_folder(imap, folder: str, since_dt: datetime) -> list[dict]:
    """Fetch messages from one Gmail folder since since_dt via IMAP."""
    status, _ = imap.select(f'"{folder}"', readonly=True)
    if status != "OK":
        raise RuntimeError(f"Could not select Gmail folder: {folder}")

    since_text = since_imap_date(since_dt)
    status, data = imap.search(None, f'(SINCE "{since_text}")')
    if status != "OK":
        raise RuntimeError(f"Gmail search failed for folder: {folder}")

    message_ids = data[0].split() if data and data[0] else []
    messages = []
    for msg_id_bytes in message_ids:
        msg_id = msg_id_bytes.decode("utf-8")
        status, fetched = imap.fetch(msg_id_bytes, "(RFC822)")
        if status != "OK" or not fetched or not fetched[0]:
            continue
        raw_bytes = fetched[0][1]
        messages.append(normalize_gmail_message(msg_id, folder, raw_bytes))

    logging.info("Fetched %d Gmail messages from %s via IMAP.", len(messages), folder)
    return messages


def fetch_gmail_label_api(service, label_id: str, since_dt: datetime) -> list[dict]:
    """Fetch messages for a Gmail label since since_dt via Gmail API."""
    query = f"after:{since_dt.strftime('%Y/%m/%d')}"
    messages: list[dict] = []
    page_token = None

    while True:
        params: dict[str, Any] = {
            "userId": "me",
            "labelIds": [label_id],
            "q": query,
            "maxResults": 100,
        }
        if page_token:
            params["pageToken"] = page_token
        response = service.users().messages().list(**params).execute()

        for item in response.get("messages") or []:
            msg_id = item.get("id")
            if not msg_id:
                continue
            full = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            messages.append(normalize_gmail_api_message(full, label_id))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    logging.info("Fetched %d Gmail messages from label %s via API.", len(messages), label_id)
    return messages


def run_gmail_backup_imap(
    output_dir: str,
    config: dict[str, Any],
    since_dt: datetime,
    date_str: str,
    imap_class=imaplib.IMAP4_SSL,
) -> list[str]:
    """Fetch Gmail via IMAP and write JSON backup files."""
    email_address = config["email"]
    app_password = config["app_password"]
    folders = config["folders"]
    created_files: list[str] = []

    imap = imap_class("imap.gmail.com")
    try:
        imap.login(email_address, app_password.replace(" ", ""))
        for folder in folders:
            logging.info("Backing up Gmail folder %s (IMAP)", folder)
            try:
                messages = fetch_gmail_folder(imap, folder, since_dt)
            except RuntimeError as exc:
                logging.error("%s", exc)
                print(f"  Gmail {folder}: {exc}")
                continue

            if not messages:
                print(f"  Gmail {folder}: no records parsed.")
                continue

            slug = folder_to_slug(folder)
            output_file = os.path.join(output_dir, f"gmail_{slug}_{date_str}.json")
            with open(output_file, "w", encoding="utf-8") as handle:
                json.dump(messages, handle, indent=4)
            print(f"  Gmail {folder}: saved {len(messages)} entries.")
            created_files.append(output_file)
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    if not created_files:
        raise RuntimeError("Gmail IMAP backup produced no messages.")
    return created_files


def run_gmail_backup_oauth(
    output_dir: str,
    config: dict[str, Any],
    since_dt: datetime,
    date_str: str,
    service=None,
) -> list[str]:
    """Fetch Gmail via OAuth Gmail API and write JSON backup files."""
    from timefinder.google_auth import build_google_service

    gmail = service or build_google_service("gmail", "v1")
    labels = config["labels"]
    created_files: list[str] = []

    for label_id in labels:
        logging.info("Backing up Gmail label %s (OAuth API)", label_id)
        try:
            messages = fetch_gmail_label_api(gmail, label_id, since_dt)
        except Exception as exc:
            logging.exception("Gmail API fetch failed for label %s", label_id)
            raise RuntimeError(f"Gmail API error for label {label_id}: {exc}") from exc

        if not messages:
            print(f"  Gmail {label_id}: no records parsed.")
            continue

        slug = folder_to_slug(label_id)
        output_file = os.path.join(output_dir, f"gmail_{slug}_{date_str}.json")
        with open(output_file, "w", encoding="utf-8") as handle:
            json.dump(messages, handle, indent=4)
        print(f"  Gmail {label_id}: saved {len(messages)} entries.")
        created_files.append(output_file)

    if not created_files:
        raise RuntimeError(
            "Gmail OAuth backup produced no messages. Check labels and lookback window."
        )
    return created_files


def run_gmail_backup(
    output_dir=DEFAULT_OUTPUT_DIR,
    config_path=DEFAULT_CONFIG_PATH,
    lookback_days=7,
    reference_date=None,
    imap_class=imaplib.IMAP4_SSL,
    gmail_service=None,
    config: dict[str, Any] | None = None,
):
    """Fetch Gmail messages and write JSON backup files."""
    from timefinder.gmail_import import run_gmail_backup_import

    cfg = config or load_gmail_config(config_path)
    os.makedirs(output_dir, exist_ok=True)

    now = reference_date or datetime.now()
    since_dt = now - timedelta(days=lookback_days)
    date_str = now.strftime("%Y-%m-%d")

    if cfg["auth"] == "import":
        print("  Using local Gmail import (.eml / .mbox — no API credentials).")
        return run_gmail_backup_import(
            output_dir, cfg["import_dir"], since_dt, now, date_str
        )

    if cfg["auth"] == "oauth":
        print("  Using Gmail API (OAuth).")
        return run_gmail_backup_oauth(output_dir, cfg, since_dt, date_str, service=gmail_service)

    print("  Using Gmail IMAP (app password).")
    return run_gmail_backup_imap(output_dir, cfg, since_dt, date_str, imap_class=imap_class)
