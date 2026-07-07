################################################################################
# Script Name:    test_audit_vast_viewer.py
# Description:    Import-smoke + CLI-parse tests for audit_vast_viewer.py. The
#                 auditor is a live subprocess harness, so coverage here guards
#                 against import/syntax regressions and verifies the argparse
#                 surface. vastpy + urllib3 are stubbed; no live VMS is contacted.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import os
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("vastpy", MagicMock())
sys.modules.setdefault("urllib3", MagicMock())

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-viewer", "audit_vast_viewer.py"
)
_spec = importlib.util.spec_from_file_location("audit_vast_viewer", _SCRIPT)
ava = importlib.util.module_from_spec(_spec)
sys.modules["audit_vast_viewer"] = ava
_spec.loader.exec_module(ava)


def test_public_callables_present():
    assert callable(ava.get_client)
    assert callable(ava.run_cmd)
    assert callable(ava.main)


def test_get_client_uses_config(tmp_path, monkeypatch):
    conf = tmp_path / "viewer.conf"
    conf.write_text(
        '{"vast_server": "h", "vast_user": "u", "vast_passwd": "p"}', encoding="utf-8"
    )
    monkeypatch.setattr(ava, "CONFIG_FILE", conf)
    factory = MagicMock()
    monkeypatch.setattr(ava, "VASTClient", factory)
    ava.get_client()
    assert factory.call_args.kwargs["address"] == "h"


def test_init_failure_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["audit_vast_viewer.py"])
    monkeypatch.setattr(ava, "get_client", MagicMock(side_effect=RuntimeError("boom")))
    ava.main()
    assert "FAILED TO INITIALIZE AUDIT" in capsys.readouterr().out
