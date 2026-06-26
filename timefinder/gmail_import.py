"""Import Gmail messages from local .eml and .mbox files (no API credentials)."""
from __future__ import annotations

import email
import hashlib
import json
import logging
import mailbox
import os
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from timefinder.gmail_messages import folder_to_slug, normalize_gmail_message

DEFAULT_IMPORT_DIR = os.path.expanduser("~/.timefinder_cache/gmail_import")


def _parse_message_date(msg: email.message.Message) -> datetime | None:
    """Parse Date header from an email message."""
    date_header = msg.get("Date")
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header)
    except (TypeError, ValueError, OverflowError):
        return None


def _message_id_for(msg: email.message.Message, fallback: str) -> str:
    """Resolve a stable message id from headers or fallback key."""
    message_id = msg.get("Message-ID")
    if message_id:
        return message_id.strip().strip("<>")
    payload = msg.as_bytes()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"import-{digest}-{fallback}"


def _message_in_window(msg: email.message.Message, since_dt: datetime, until_dt: datetime) -> bool:
    """Return True if message date falls within the lookback window."""
    parsed = _parse_message_date(msg)
    if parsed is None:
        return True
    if parsed.tzinfo is not None:
        since_cmp = since_dt.astimezone(parsed.tzinfo) if since_dt.tzinfo else since_dt.replace(tzinfo=parsed.tzinfo)
        until_cmp = until_dt.astimezone(parsed.tzinfo) if until_dt.tzinfo else until_dt.replace(tzinfo=parsed.tzinfo)
    else:
        since_cmp = since_dt.replace(tzinfo=None)
        until_cmp = until_dt.replace(tzinfo=None)
        parsed = parsed.replace(tzinfo=None)
    return since_cmp <= parsed <= until_cmp


def normalize_import_message(msg: email.message.Message, msg_id: str, folder: str) -> dict:
    """Normalize a parsed email message into backup JSON shape."""
    return normalize_gmail_message(msg_id, folder, msg.as_bytes())


def collect_eml_messages(path: Path, folder: str, since_dt: datetime, until_dt: datetime) -> list[dict]:
    """Load and filter messages from a single .eml file."""
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw)
    if not _message_in_window(msg, since_dt, until_dt):
        return []
    msg_id = _message_id_for(msg, path.stem)
    return [normalize_import_message(msg, msg_id, folder)]


def collect_mbox_messages(path: Path, folder: str, since_dt: datetime, until_dt: datetime) -> list[dict]:
    """Load and filter messages from an .mbox file."""
    messages: list[dict] = []
    mbox = mailbox.mbox(str(path))
    try:
        for index, msg in enumerate(mbox):
            if not _message_in_window(msg, since_dt, until_dt):
                continue
            msg_id = _message_id_for(msg, f"{path.stem}-{index}")
            messages.append(normalize_import_message(msg, msg_id, folder))
    finally:
        mbox.close()
    logging.info("Imported %d messages from mbox %s", len(messages), path)
    return messages


def discover_import_sources(import_dir: str) -> list[tuple[Path, str]]:
    """Find .eml and .mbox files under import_dir with folder labels."""
    root = Path(os.path.expanduser(import_dir))
    if not root.is_dir():
        return []

    sources: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".eml", ".mbox"}:
            continue
        if path.parent == root:
            folder = path.stem if suffix == ".mbox" else "import"
        else:
            folder = path.parent.name
        sources.append((path, folder))
    return sources


def run_gmail_backup_import(
    output_dir: str,
    import_dir: str,
    since_dt: datetime,
    until_dt: datetime,
    date_str: str,
) -> list[str]:
    """Import Gmail from local .eml/.mbox files and write JSON backups."""
    sources = discover_import_sources(import_dir)
    if not sources:
        raise FileNotFoundError(
            f"No .eml or .mbox files found under {os.path.expanduser(import_dir)}. "
            "Export mail via Google Takeout or save .eml files into that directory. "
            "See timefinder/SETUP_macOS.md Step 4C."
        )

    grouped: dict[str, list[dict]] = {}
    for path, folder in sources:
        if path.suffix.lower() == ".mbox":
            batch = collect_mbox_messages(path, folder, since_dt, until_dt)
        else:
            batch = collect_eml_messages(path, folder, since_dt, until_dt)
        if batch:
            grouped.setdefault(folder, []).extend(batch)

    if not grouped:
        raise RuntimeError(
            f"No messages in lookback window found under {os.path.expanduser(import_dir)}. "
            "Export a fresh Takeout archive or add recent .eml files."
        )

    os.makedirs(output_dir, exist_ok=True)
    created_files: list[str] = []
    for folder, messages in sorted(grouped.items()):
        slug = folder_to_slug(folder)
        output_file = os.path.join(output_dir, f"gmail_{slug}_{date_str}.json")
        with open(output_file, "w", encoding="utf-8") as handle:
            json.dump(messages, handle, indent=4)
        print(f"  Gmail import/{folder}: saved {len(messages)} entries.")
        created_files.append(output_file)

    return created_files
