################################################################################
# Script Name:    test_vast_viewer.py
# Description:    Mocked unit tests for vast-viewer.py output formatting, config
#                 merging, and CLI guard rails. No live VMS or vastpy required —
#                 vastpy/urllib3 are stubbed so pure logic is exercised stdlib-only.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout
from unittest.mock import MagicMock

import pytest

# vast-viewer.py imports vastpy + urllib3 at module load. Stub them so the pure
# formatting/config logic can be imported and tested without those packages.
sys.modules.setdefault("vastpy", MagicMock())
sys.modules.setdefault("urllib3", MagicMock())

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-viewer", "vast-viewer.py"
)
_spec = importlib.util.spec_from_file_location("vast_viewer", _SCRIPT)
viewer = importlib.util.module_from_spec(_spec)
sys.modules["vast_viewer"] = viewer
_spec.loader.exec_module(viewer)


def _capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


class TestFormatOutput:
    def test_json_list(self):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        out = _capture(viewer.format_output, rows, "json")
        assert json.loads(out) == rows

    def test_empty_json_emits_brackets(self):
        assert _capture(viewer.format_output, [], "json").strip() == "[]"

    def test_empty_text_message(self):
        assert "No data returned." in _capture(viewer.format_output, [], "text")

    def test_csv_headers_and_rows(self):
        rows = [{"id": 1, "name": "a"}]
        out = _capture(viewer.format_output, rows, "csv")
        assert "id,name" in out.replace(" ", "")
        assert "1,a" in out.replace(" ", "")

    def test_table_renders_header_and_values(self):
        rows = [{"id": 7, "name": "lab"}]
        out = _capture(viewer.format_output, rows, "table", headers=["id", "name"])
        assert "ID" in out and "NAME" in out
        assert "7" in out and "lab" in out

    def test_dict_with_results_key_unwrapped(self):
        payload = {"results": [{"id": 3, "path": "/x"}]}
        out = _capture(viewer.format_output, payload, "table", headers=["id", "path"])
        assert "/x" in out

    def test_table_missing_key_shows_na(self):
        rows = [{"id": 1}]
        out = _capture(viewer.format_output, rows, "table", headers=["id", "name"])
        assert "N/A" in out


class TestGetConfig:
    def test_cli_overrides_and_completes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(viewer, "CONFIG_FILE", tmp_path / "nope.conf")
        args = MagicMock(server="10.0.0.5", user="admin", password="secret")
        cfg = viewer.get_config(args)
        assert cfg == {
            "vast_server": "10.0.0.5",
            "vast_user": "admin",
            "vast_passwd": "secret",
        }

    def test_missing_config_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(viewer, "CONFIG_FILE", tmp_path / "nope.conf")
        args = MagicMock(server=None, user=None, password=None)
        with pytest.raises(SystemExit) as exc:
            viewer.get_config(args)
        assert exc.value.code == 1

    def test_config_file_is_read(self, tmp_path, monkeypatch):
        conf = tmp_path / "viewer.conf"
        conf.write_text(json.dumps({
            "vast_server": "vms.lab", "vast_user": "admin", "vast_passwd": "pw",
        }), encoding="utf-8")
        monkeypatch.setattr(viewer, "CONFIG_FILE", conf)
        args = MagicMock(server=None, user=None, password=None)
        cfg = viewer.get_config(args)
        assert cfg["vast_server"] == "vms.lab"


class TestMainGuards:
    def test_no_action_prints_help_and_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["vast-viewer.py"])
        with pytest.raises(SystemExit) as exc:
            viewer.main()
        assert exc.value.code == 0

    def test_view_policy_without_id_errors(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", [
            "vast-viewer.py", "--view-policy",
            "--server", "h", "--user", "u", "--password", "p",
        ])
        monkeypatch.setattr(viewer, "CONFIG_FILE", tmp_path / "nope.conf")
        monkeypatch.setattr(viewer, "VASTClient", MagicMock())
        out = io.StringIO()
        with redirect_stdout(out), pytest.raises(SystemExit) as exc:
            viewer.main()
        assert exc.value.code == 1
        assert "requires --id" in out.getvalue()
