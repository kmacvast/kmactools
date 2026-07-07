################################################################################
# Script Name:    test_show_ad_configs.py
# Description:    Mocked unit tests for show_ad_configs.py — AD config retrieval
#                 via the schema-less client and main() env-var handling. vastpy +
#                 urllib3 stubbed, VASTClient mocked; no live VMS is contacted.
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
    os.path.dirname(__file__), "..", "vast", "identity", "show_ad_configs.py"
)
_spec = importlib.util.spec_from_file_location("show_ad_configs", _SCRIPT)
sad = importlib.util.module_from_spec(_spec)
sys.modules["show_ad_configs"] = sad
_spec.loader.exec_module(sad)


class TestListActiveDirectoryConfigs:
    def test_returns_client_payload(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.activedirectory.get.return_value = [{"id": 1, "domain_name": "x"}]
        factory = MagicMock(return_value=fake_client)
        monkeypatch.setattr(sad, "VASTClient", factory)

        result = sad.list_active_directory_configs("vms.lab", "tok")

        assert result == [{"id": 1, "domain_name": "x"}]
        assert factory.call_args.kwargs == {"address": "vms.lab", "token": "tok"}


class TestMain:
    def test_missing_token_prints_usage(self, monkeypatch, capsys):
        monkeypatch.delenv("VMS_TOKEN", raising=False)
        sad.main()
        assert "VMS_TOKEN environment variable is required" in capsys.readouterr().out

    def test_lists_configs(self, monkeypatch, capsys):
        monkeypatch.setenv("VMS_TOKEN", "tok")
        monkeypatch.setenv("VMS_ADDRESS", "vms.lab")
        monkeypatch.setattr(
            sad, "list_active_directory_configs",
            lambda addr, tok: [{"id": 9, "domain_name": "corp", "state": "READY"}],
        )
        sad.main()
        out = capsys.readouterr().out
        assert "Found 1 Active Directory configuration" in out
        assert "corp" in out

    def test_empty_configs_message(self, monkeypatch, capsys):
        monkeypatch.setenv("VMS_TOKEN", "tok")
        monkeypatch.setattr(sad, "list_active_directory_configs", lambda a, t: [])
        sad.main()
        assert "No Active Directory configurations found." in capsys.readouterr().out
