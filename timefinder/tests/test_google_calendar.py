"""Tests for google_calendar.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from timefinder import google_calendar as gcal


def test_events_from_json_filters_approved_only(tmp_path):
    payload = {
        "candidates": [
            {
                "status": "approved",
                "title": "Approved Entry",
                "start_time": "2026-06-20T10:00:00",
                "end_time": "2026-06-20T11:00:00",
                "summary": "Work done",
            },
            {
                "status": "pending_review",
                "title": "Pending Entry",
                "start_time": "2026-06-21T09:00:00",
                "end_time": "2026-06-21T10:00:00",
                "summary": "Not yet",
            },
        ]
    }
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    events = gcal.events_from_json(str(path), approved_only=True)
    assert len(events) == 1
    assert events[0]["title"] == "Approved Entry"


def test_to_google_event_body():
    body = gcal.to_google_event_body(
        {
            "title": "Work Journal: Test",
            "start_time": "2026-06-20T10:00:00",
            "end_time": "2026-06-20T11:00:00",
            "summary": "Details",
        }
    )
    assert body["summary"] == "Work Journal: Test"
    assert body["start"]["dateTime"] == "2026-06-20T10:00:00"


def test_run_sync_google_inserts_events(tmp_path):
    payload = {
        "candidates": [
            {
                "status": "approved",
                "title": "Sync Me",
                "start_time": "2026-06-20T10:00:00",
                "end_time": "2026-06-20T11:00:00",
                "summary": "Synced",
            }
        ]
    }
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    mock_service = MagicMock()
    mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt1"}

    with patch.object(gcal, "build_calendar_service", return_value=mock_service):
        assert gcal.run_sync_google(str(path)) == 0

    mock_service.events.return_value.insert.assert_called_once()
