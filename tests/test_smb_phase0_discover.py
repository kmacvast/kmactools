################################################################################
# Script Name:    test_smb_phase0_discover.py
# Description:    Mocked unit tests for smb_phase0_discover.py — config load
#                 failures, host resolution, CLI overrides, and delegation to
#                 smb.init_config/discover_metrics. No live VMS is contacted.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import os
import sys
from unittest.mock import MagicMock

import pytest

_OPSTAT_DIR = os.path.join(os.path.dirname(__file__), "..", "vast", "vast-opstat")
sys.path.insert(0, os.path.abspath(_OPSTAT_DIR))

_SCRIPT = os.path.join(_OPSTAT_DIR, "smb_phase0_discover.py")
_spec = importlib.util.spec_from_file_location("smb_phase0_discover", _SCRIPT)
p0 = importlib.util.module_from_spec(_spec)
sys.modules["smb_phase0_discover"] = p0
_spec.loader.exec_module(p0)


@pytest.fixture
def stub_smb(monkeypatch):
    monkeypatch.setattr(p0.smb, "init_config", MagicMock())
    monkeypatch.setattr(p0.smb, "discover_metrics", MagicMock(return_value=None))
    return p0.smb


def _argv(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["smb_phase0_discover.py", *args])


class TestMain:
    def test_missing_config_returns_1(self, monkeypatch, capsys):
        _argv(monkeypatch)
        monkeypatch.setattr(
            p0, "load_vast_config",
            MagicMock(side_effect=FileNotFoundError("no ~/.vastconf")),
        )
        assert p0.main() == 1
        assert "ERROR" in capsys.readouterr().out

    def test_no_host_returns_1(self, monkeypatch, capsys):
        _argv(monkeypatch)
        monkeypatch.setattr(p0, "load_vast_config", MagicMock(return_value={}))
        assert p0.main() == 1
        assert "No VMS host" in capsys.readouterr().out

    def test_happy_path_delegates(self, monkeypatch, stub_smb):
        _argv(monkeypatch)
        monkeypatch.setattr(
            p0, "load_vast_config",
            MagicMock(return_value={"vms": "lab-vms", "user": "admin", "password": "pw"}),
        )
        assert p0.main() == 0
        stub_smb.init_config.assert_called_once()
        ns = stub_smb.init_config.call_args.args[0]
        assert ns.vms == "lab-vms"
        assert ns.discover_metrics is True
        stub_smb.discover_metrics.assert_called_once()

    def test_cli_vms_override_wins(self, monkeypatch, stub_smb):
        _argv(monkeypatch, "--vms", "override-host", "--user", "svc")
        monkeypatch.setattr(
            p0, "load_vast_config",
            MagicMock(return_value={"vms": "conf-host", "password": "pw"}),
        )
        p0.main()
        ns = stub_smb.init_config.call_args.args[0]
        assert ns.vms == "override-host"
        assert ns.user == "svc"
