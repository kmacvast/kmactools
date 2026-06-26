"""Interactive ICS calendar review wizard for TimeFinder."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from timefinder.candidates import format_ics_datetime, ics_escape


@dataclass
class IcsEvent:
    """Parsed VEVENT block from an ICS file."""

    uid: str = ""
    summary: str = ""
    dtstart: str = ""
    dtend: str = ""
    description: str = ""
    extra_lines: list[str] = field(default_factory=list)
    removed: bool = False

    def display_block(self, index: int, total: int) -> None:
        """Print a human-readable event summary."""
        print("\n" + "=" * 60)
        print(f"Entry {index + 1} of {total}")
        print("=" * 60)
        print(f"  SUMMARY     : {self.summary or '(none)'}")
        print(f"  DTSTART     : {self._format_dt(self.dtstart)}")
        print(f"  DTEND       : {self._format_dt(self.dtend)}")
        print(f"  DESCRIPTION : {self._truncate(self.description)}")

    @staticmethod
    def _truncate(text: str, limit: int = 200) -> str:
        cleaned = text.replace("\\n", "\n").replace("\\,", ",")
        if len(cleaned) <= limit:
            return cleaned or "(none)"
        return cleaned[: limit - 3] + "..."

    @staticmethod
    def _format_dt(raw: str) -> str:
        if not raw:
            return "(none)"
        digits = raw.strip()[:15]
        if len(digits) >= 15 and digits[8] == "T":
            try:
                parsed = datetime.strptime(digits, "%Y%m%dT%H%M%S")
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        return raw


def unfold_ics_lines(content: str) -> list[str]:
    """Unfold RFC 5545 line continuations."""
    raw_lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in raw_lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def parse_ics_property(line: str) -> tuple[str, str, str]:
    """Parse an ICS property line into name, params, and value."""
    if ":" not in line:
        return line, "", ""
    head, value = line.split(":", 1)
    if ";" in head:
        name, params = head.split(";", 1)
        return name.upper(), params, value
    return head.upper(), "", value


def parse_ics_file(path: str) -> tuple[list[str], list[IcsEvent]]:
    """Parse an ICS file into preamble lines and VEVENT objects."""
    text = Path(path).expanduser().read_text(encoding="utf-8")
    lines = unfold_ics_lines(text)

    preamble: list[str] = []
    events: list[IcsEvent] = []
    in_event = False
    current: IcsEvent | None = None

    for line in lines:
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            in_event = True
            current = IcsEvent()
            continue
        if upper == "END:VEVENT":
            if current is not None:
                events.append(current)
            in_event = False
            current = None
            continue

        if in_event and current is not None:
            name, _params, value = parse_ics_property(line)
            if name == "UID":
                current.uid = value
            elif name == "SUMMARY":
                current.summary = _unescape_ics(value)
            elif name == "DTSTART":
                current.dtstart = value
            elif name == "DTEND":
                current.dtend = value
            elif name == "DESCRIPTION":
                current.description = _unescape_ics(value)
            else:
                current.extra_lines.append(line)
        else:
            preamble.append(line)

    return preamble, events


def _unescape_ics(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_user_datetime(text: str) -> str:
    """Parse user datetime input into ICS compact format."""
    text = text.strip()
    if re.fullmatch(r"\d{8}T\d{6}", text):
        return text
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y%m%dT%H%M%S")
        except ValueError:
            continue
    raise ValueError(f"Could not parse datetime: {text!r}")


def prompt_choice() -> str:
    """Prompt user for approve/remove/modify/skip."""
    while True:
        choice = input("[A]pprove, [R]emove, [M]odify, [S]kip: ").strip().lower()
        if choice in {"a", "approve", "r", "remove", "m", "modify", "s", "skip"}:
            return choice[0]
        print("Invalid choice. Enter A, R, M, or S.")


def prompt_modify(event: IcsEvent) -> None:
    """Interactively modify event fields."""
    new_summary = input(f"Title/Summary [{event.summary}]: ").strip()
    if new_summary:
        event.summary = new_summary

    new_start = input(f"Start time [{event._format_dt(event.dtstart)}]: ").strip()
    if new_start:
        event.dtstart = parse_user_datetime(new_start)

    new_end = input(f"End time [{event._format_dt(event.dtend)}]: ").strip()
    if new_end:
        event.dtend = parse_user_datetime(new_end)


def write_ics_file(path: str, preamble: list[str], events: list[IcsEvent]) -> None:
    """Write ICS file from preamble and events."""
    lines: list[str] = []
    for line in preamble:
        if line.strip().upper() == "END:VCALENDAR":
            continue
        lines.append(line)

    if not any(line.strip().upper() == "BEGIN:VCALENDAR" for line in lines):
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TimeFinder//Review//EN"] + lines

    for event in events:
        if event.removed:
            continue
        lines.append("BEGIN:VEVENT")
        if event.uid:
            lines.append(f"UID:{event.uid}")
        else:
            lines.append(f"UID:timefinder-{format_ics_datetime(datetime.now())}@timefinder.local")
        lines.append(f"DTSTAMP:{format_ics_datetime(datetime.now())}")
        if event.dtstart:
            lines.append(f"DTSTART:{event.dtstart}")
        if event.dtend:
            lines.append(f"DTEND:{event.dtend}")
        if event.summary:
            lines.append(f"SUMMARY:{ics_escape(event.summary)}")
        if event.description:
            lines.append(f"DESCRIPTION:{ics_escape(event.description)}")
        lines.extend(event.extra_lines)
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    Path(path).expanduser().write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_ics_review(path: str, input_fn=input, output_fn=print) -> int:
    """Run interactive ICS review loop; write file atomically at end."""
    expanded = str(Path(path).expanduser())
    if not Path(expanded).is_file():
        output_fn(f"Error: ICS file not found: {expanded}")
        return 1

    preamble, events = parse_ics_file(expanded)
    if not events:
        output_fn("No VEVENT entries found in file.")
        return 1

    output_fn(f"Reviewing {len(events)} calendar entries in {expanded}")
    for index, event in enumerate(events):
        event.display_block(index, len(events))
        choice = prompt_choice()
        if choice == "a":
            continue
        if choice == "r":
            event.removed = True
        elif choice == "m":
            prompt_modify(event)
        elif choice == "s":
            continue

    kept = sum(1 for event in events if not event.removed)
    confirm = input_fn(f"\nSave {kept} entries to {expanded}? (y/n): ").strip().lower()
    if confirm not in {"y", "yes"}:
        output_fn("Review canceled. No changes written.")
        return 0

    write_ics_file(expanded, preamble, events)
    output_fn(f"Saved {kept} entries to {expanded}")
    return 0
