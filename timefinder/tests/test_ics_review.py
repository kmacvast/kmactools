"""Tests for ics_review.py."""
from __future__ import annotations

from timefinder.ics_review import IcsEvent, parse_ics_file, parse_user_datetime, write_ics_file


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TimeFinder//Test//EN
BEGIN:VEVENT
UID:test-1@timefinder.local
DTSTART:20260620T100000
DTEND:20260620T110000
SUMMARY:Work Journal: Test Entry
DESCRIPTION:First line\\nSecond line
END:VEVENT
BEGIN:VEVENT
UID:test-2@timefinder.local
DTSTART:20260621T090000
DTEND:20260621T100000
SUMMARY:Another Entry
DESCRIPTION:Details here
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_file_extracts_events(tmp_path):
    path = tmp_path / "sample.ics"
    path.write_text(SAMPLE_ICS, encoding="utf-8")
    _preamble, events = parse_ics_file(str(path))
    assert len(events) == 2
    assert events[0].summary == "Work Journal: Test Entry"
    assert events[0].dtstart == "20260620T100000"
    assert "First line" in events[0].description


def test_parse_user_datetime_formats():
    assert parse_user_datetime("2026-06-20 10:00:00") == "20260620T100000"
    assert parse_user_datetime("20260620T100000") == "20260620T100000"


def test_write_ics_file_skips_removed(tmp_path):
    path = tmp_path / "out.ics"
    path.write_text(SAMPLE_ICS, encoding="utf-8")
    preamble, events = parse_ics_file(str(path))
    events[0].removed = True
    events[1].summary = "Updated Title"
    write_ics_file(str(path), preamble, events)
    text = path.read_text(encoding="utf-8")
    assert "Updated Title" in text
    assert "Work Journal: Test Entry" not in text
    assert text.count("BEGIN:VEVENT") == 1
