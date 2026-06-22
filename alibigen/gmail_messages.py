"""Gmail message fetch helpers for AlibiGen."""
from __future__ import annotations

import email
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.alibigen_cache/gmail_config.json")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.alibigen_cache")


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
    """Convert an IMAP folder name to a filesystem-safe slug."""
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


def load_gmail_config(config_path=DEFAULT_CONFIG_PATH):
    """Load Gmail IMAP credentials and folder list."""
    logging.info("Loading Gmail configuration from: %s", config_path)
    if not os.path.exists(config_path):
        msg = f"Gmail configuration not found at {config_path}"
        logging.error(msg)
        raise FileNotFoundError(msg)

    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    email_address = config.get("email")
    app_password = config.get("app_password")
    folders = config.get("folders") or ["INBOX"]

    if not email_address or not app_password:
        raise ValueError("Gmail config requires email and app_password.")

    return email_address, app_password, folders


def fetch_gmail_folder(imap, folder: str, since_dt: datetime) -> list[dict]:
    """Fetch messages from one Gmail folder since since_dt."""
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

    logging.info("Fetched %d Gmail messages from %s.", len(messages), folder)
    return messages


def run_gmail_backup(
    output_dir=DEFAULT_OUTPUT_DIR,
    config_path=DEFAULT_CONFIG_PATH,
    lookback_days=7,
    reference_date=None,
    imap_class=imaplib.IMAP4_SSL,
):
    """Fetch Gmail messages for configured folders and write JSON backup files."""
    email_address, app_password, folders = load_gmail_config(config_path)
    os.makedirs(output_dir, exist_ok=True)

    now = reference_date or datetime.now()
    since_dt = now - timedelta(days=lookback_days)
    date_str = now.strftime("%Y-%m-%d")
    created_files = []

    imap = imap_class("imap.gmail.com")
    try:
        imap.login(email_address, app_password)
        for folder in folders:
            logging.info("Backing up Gmail folder %s", folder)
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

    return created_files
