"""Shared pytest helpers for TimeFinder tests."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

TIMEFINDER_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(TIMEFINDER_ROOT.parent))


def ts_at(year: int, month: int, day: int, hour: int = 10, minute: int = 0, second: int = 0) -> str:
    """Build a Slack-style ts string in local time."""
    dt = datetime(year, month, day, hour, minute, second)
    return f"{dt.timestamp():.6f}"


def load_fixture_messages(name: str) -> list:
    """Load a fixture message list JSON file."""
    path = FIXTURES_DIR / name
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_slack_backup(tmp_path: Path, channel: str, date_str: str, messages: list) -> Path:
    """Write messages to a properly named slack backup file."""
    path = tmp_path / f"slack_{channel}_{date_str}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(messages, handle, indent=2)
    return path
