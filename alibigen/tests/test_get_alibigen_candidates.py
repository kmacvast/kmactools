"""Tests for get_alibigen_candidates.py."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from alibigen import get_alibigen_candidates as cal
from alibigen.tests.conftest import FIXTURES_DIR, load_fixture_messages, ts_at, write_slack_backup


REFERENCE_DATE = datetime(2026, 6, 22, 23, 59, 59)
DATE_STR = "2026-06-22"


def materialize_fixture(name: str, mapping: dict[str, str]) -> list:
    """Replace TS placeholders in fixture messages with concrete timestamps."""
    raw = json.dumps(load_fixture_messages(name))
    for placeholder, value in mapping.items():
        raw = raw.replace(placeholder, value)
    return json.loads(raw)


@pytest.fixture
def user_map():
    with open(FIXTURES_DIR / "slack_users.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def populated_input_dir(tmp_path, user_map):
    smb = materialize_fixture(
        "meaningful_apple_smb_thread.json",
        {
            "TS_PARENT": ts_at(2026, 6, 20, 10, 0),
            "TS_REPLY1": ts_at(2026, 6, 20, 10, 20),
            "TS_REPLY2": ts_at(2026, 6, 20, 10, 45),
            "TS_REPLY3": ts_at(2026, 6, 20, 11, 5),
        },
    )
    vectordb = materialize_fixture(
        "meaningful_vectordb_thread.json",
        {
            "TS_V1": ts_at(2026, 6, 21, 9, 0),
            "TS_V2": ts_at(2026, 6, 21, 9, 30),
            "TS_V3": ts_at(2026, 6, 21, 10, 0),
        },
    )
    banter = materialize_fixture(
        "trivial_banter.json",
        {
            "TS_T1": ts_at(2026, 6, 21, 14, 0),
            "TS_T2": ts_at(2026, 6, 21, 14, 5),
            "TS_T3": ts_at(2026, 6, 21, 14, 10),
            "TS_T4": ts_at(2026, 6, 21, 14, 15),
        },
    )
    confirmation = materialize_fixture(
        "short_meaningful_confirmation.json",
        {
            "TS_C1": ts_at(2026, 6, 19, 16, 0),
            "TS_C2": ts_at(2026, 6, 19, 16, 10),
            "TS_C3": ts_at(2026, 6, 19, 16, 12),
        },
    )
    secret = materialize_fixture("secret_redaction.json", {"TS_S1": ts_at(2026, 6, 18, 11, 0)})

    write_slack_backup(tmp_path, "orion-378849-macos-houdini", DATE_STR, smb)
    write_slack_backup(tmp_path, "apple-ai-vectordb-opp", DATE_STR, vectordb)
    write_slack_backup(tmp_path, "bman", DATE_STR, banter)
    write_slack_backup(tmp_path, "apple-openldap", DATE_STR, confirmation)
    write_slack_backup(tmp_path, "secrets", DATE_STR, secret)

    user_map_path = tmp_path / "slack_users.json"
    with open(user_map_path, "w", encoding="utf-8") as handle:
        json.dump(user_map, handle)
    return tmp_path, user_map_path


def test_parse_slack_timestamp():
    parsed = cal.parse_slack_timestamp("1781895454.799119")
    assert isinstance(parsed, datetime)


def test_redact_obvious_secrets():
    text = "api_key=supersecret123 token=xoxb-1234567890-abcdefghij"
    redacted = cal.redact_text(text)
    assert "supersecret123" not in redacted
    assert "xoxb-" not in redacted
    assert "REDACTED" in redacted


def test_load_user_name_map_missing(tmp_path):
    assert cal.load_user_name_map(str(tmp_path / "missing.json")) == {}


def test_resolve_user_with_and_without_map():
    assert cal.resolve_user("U111", {"U111": "kmac"}) == "kmac"
    assert cal.resolve_user("U999", {"U111": "kmac"}) == "U999"


def test_parse_channel_from_filename():
    parsed = cal.parse_channel_from_filename("/tmp/slack_apple-openldap_2026-06-22.json")
    assert parsed == ("apple-openldap", "2026-06-22")


def test_group_explicit_thread(user_map):
    messages = cal.load_slack_files(
        str(Path(__file__).resolve().parent / "fixtures"),
        lookback_days=30,
        reference_date=REFERENCE_DATE,
        name_map=user_map,
    )
    assert messages == []


def test_group_thread_and_cluster(user_map, populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    messages = cal.load_slack_files(str(input_dir), 7, REFERENCE_DATE, name_map)
    messages = cal.dedupe_messages(messages)
    groups = cal.group_messages(messages, cluster_window_minutes=60)

    thread_groups = [group for group in groups if group.thread_ts]
    assert any(len(group.messages) >= 3 for group in thread_groups)


def test_filter_trivial_and_keep_meaningful(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    candidates, excluded = cal.process_slack_backups(
        input_dir=str(input_dir),
        lookback_days=7,
        reference_date=REFERENCE_DATE,
        name_map=name_map,
        cluster_window_minutes=60,
        min_confidence=0.65,
        min_duration=15,
        max_duration=120,
    )
    titles = [candidate["title"] for candidate in candidates]
    assert any("Houdini" in title or "Vector DB" in title or "OpenLDAP" in title for title in titles)
    assert all(candidate["status"] == "pending_review" for candidate in candidates)
    assert any(item["exclusion_reason"] for item in excluded)


def test_short_confirmation_kept_in_meaningful_thread(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    candidates, _ = cal.process_slack_backups(
        input_dir=str(input_dir),
        lookback_days=7,
        reference_date=REFERENCE_DATE,
        name_map=name_map,
        cluster_window_minutes=60,
        min_confidence=0.65,
        min_duration=15,
        max_duration=120,
    )
    openldap = [candidate for candidate in candidates if "OpenLDAP" in candidate["title"]]
    assert openldap
    assert openldap[0]["message_count"] >= 3


def test_deterministic_candidate_ids(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    first, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.65, 15, 120
    )
    second, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.65, 15, 120
    )
    assert [item["id"] for item in first] == [item["id"] for item in second]


def test_write_json_markdown_ics_outputs(populated_input_dir, tmp_path):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    candidates, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.65, 15, 120
    )
    json_path = tmp_path / "calendar_candidates.json"
    md_path = tmp_path / "calendar_candidates.md"
    ics_path = tmp_path / "calendar_candidates.ics"

    cal.write_json_output(candidates, str(json_path))
    cal.write_markdown_output(candidates, str(md_path))
    cal.write_ics_output(candidates, str(ics_path))

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == len(candidates)
    assert "BEGIN:VCALENDAR" in ics_path.read_text(encoding="utf-8")
    assert "# Calendar Candidates" in md_path.read_text(encoding="utf-8")


def test_dedupe_across_channels(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))

    duplicate = materialize_fixture(
        "meaningful_apple_smb_thread.json",
        {
            "TS_PARENT": ts_at(2026, 6, 20, 10, 5),
            "TS_REPLY1": ts_at(2026, 6, 20, 10, 25),
            "TS_REPLY2": ts_at(2026, 6, 20, 10, 50),
            "TS_REPLY3": ts_at(2026, 6, 20, 11, 10),
        },
    )
    write_slack_backup(input_dir, "team_fred", DATE_STR, duplicate)

    candidates, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.65, 15, 120
    )
    houdini_like = [
        candidate
        for candidate in candidates
        if "Houdini" in candidate["title"] or "SMB" in " ".join(candidate["keywords"])
    ]
    assert len(houdini_like) <= 2


def test_dedupe_messages_keeps_newest_snapshot(tmp_path, user_map):
    older = [{"user": "U111", "ts": ts_at(2026, 6, 20, 10), "text": "old snapshot"}]
    newer = [{"user": "U111", "ts": ts_at(2026, 6, 20, 10), "text": "new snapshot"}]
    write_slack_backup(tmp_path, "apple-openldap", "2026-06-18", older)
    write_slack_backup(tmp_path, "apple-openldap", DATE_STR, newer)

    messages = cal.load_slack_files(str(tmp_path), 7, REFERENCE_DATE, user_map)
    deduped = cal.dedupe_messages(messages)
    assert len(deduped) == 1
    assert deduped[0].text == "new snapshot"


def test_malformed_json_is_skipped(tmp_path, user_map):
    bad_path = tmp_path / "slack_broken-channel_2026-06-22.json"
    bad_path.write_text("{not valid", encoding="utf-8")
    messages = cal.load_slack_files(str(tmp_path), 7, REFERENCE_DATE, user_map)
    assert messages == []


def test_cli_date_override(populated_input_dir, tmp_path):
    input_dir, user_map_path = populated_input_dir
    output_dir = tmp_path / "out"
    exit_code = cal.main(
        [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--user-map",
            str(user_map_path),
            "--date",
            DATE_STR,
            "--no-ics",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "calendar_candidates.json").exists()
    assert (output_dir / "calendar_candidates.md").exists()
    assert not (output_dir / "calendar_candidates.ics").exists()


def test_dry_run(populated_input_dir, capsys):
    input_dir, user_map_path = populated_input_dir
    exit_code = cal.main(
        [
            "--input-dir",
            str(input_dir),
            "--user-map",
            str(user_map_path),
            "--date",
            DATE_STR,
            "--dry-run",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Dry run" in captured.out


def test_include_trivial_debug_output(populated_input_dir, tmp_path):
    input_dir, user_map_path = populated_input_dir
    output_dir = tmp_path / "out"
    cal.main(
        [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--user-map",
            str(user_map_path),
            "--date",
            DATE_STR,
            "--include-trivial-debug",
            "--no-ics",
        ]
    )
    debug = json.loads((output_dir / "trivial_excluded.json").read_text(encoding="utf-8"))
    assert debug["excluded_count"] >= 1


def test_evidence_uses_display_names(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    candidates, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.65, 15, 120
    )
    users = {item["user"] for candidate in candidates for item in candidate["evidence"]}
    assert "kmac" in users or "seb" in users


def test_secret_redaction_in_evidence(populated_input_dir):
    input_dir, user_map_path = populated_input_dir
    name_map = cal.load_user_name_map(str(user_map_path))
    candidates, _ = cal.process_slack_backups(
        str(input_dir), 7, REFERENCE_DATE, name_map, 60, 0.50, 15, 120
    )
    combined = json.dumps(candidates)
    assert "supersecret123" not in combined
    assert "xoxb-" not in combined
