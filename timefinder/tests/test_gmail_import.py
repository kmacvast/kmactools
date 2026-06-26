"""Tests for gmail_import.py."""
from __future__ import annotations

import json
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from timefinder import gmail_import as gimport


def _write_eml(path: Path, subject: str, when: datetime) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "Bob <bob@example.com>"
    msg["Date"] = when.strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    msg.set_content(f"Body for {subject}")
    path.write_bytes(msg.as_bytes())


def test_import_eml_files(tmp_path):
    recent = datetime(2026, 6, 20, 10, 0, 0)
    old = datetime(2026, 5, 1, 10, 0, 0)
    _write_eml(tmp_path / "recent.eml", "Recent mail", recent)
    _write_eml(tmp_path / "old.eml", "Old mail", old)

    since = datetime(2026, 6, 19)
    until = datetime(2026, 6, 22, 23, 59, 59)
    files = gimport.run_gmail_backup_import(str(tmp_path / "out"), str(tmp_path), since, until, "2026-06-22")
    assert len(files) == 1
    payload = json.loads(Path(files[0]).read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["subject"] == "Recent mail"


def test_load_gmail_config_import_mode(tmp_path):
    from timefinder import gmail_messages as gmail

    config_path = tmp_path / "gmail_config.json"
    import_dir = tmp_path / "gmail_import"
    import_dir.mkdir()
    config_path.write_text(
        json.dumps({"auth": "import", "import_dir": str(import_dir)}),
        encoding="utf-8",
    )
    loaded = gmail.load_gmail_config(str(config_path))
    assert loaded["auth"] == "import"
    assert loaded["import_dir"] == str(import_dir)
