################################################################################
# Script Name:    test_vast_get_token.py
# Description:    Mocked unit tests for vast_get_token.py — config loading and the
#                 tenant-normalization / token-generation flow. vastpy + urllib3
#                 are stubbed and VASTClient is mocked; no live VMS is contacted.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("vastpy", MagicMock())
sys.modules.setdefault("urllib3", MagicMock())

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "auth", "vast_get_token.py"
)
_spec = importlib.util.spec_from_file_location("vast_get_token", _SCRIPT)
vgt = importlib.util.module_from_spec(_spec)
sys.modules["vast_get_token"] = vgt
_spec.loader.exec_module(vgt)


class TestLoadConfig:
    def test_reads_json(self, tmp_path):
        cfg = tmp_path / "conf.json"
        cfg.write_text(json.dumps({"vms": "h", "user": "admin"}), encoding="utf-8")
        assert vgt.load_config(str(cfg))["vms"] == "h"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            vgt.load_config(str(tmp_path / "nope.json"))


class TestGenerateToken:
    def _wire(self, monkeypatch, conf):
        monkeypatch.setattr(vgt, "load_config", lambda: conf)
        fake_client = MagicMock()
        fake_client.apitokens.post.return_value = {"token": "TOK-123"}
        factory = MagicMock(return_value=fake_client)
        monkeypatch.setattr(vgt, "VASTClient", factory)
        return factory, fake_client

    def test_default_tenant_normalized_to_none(self, monkeypatch):
        factory, _ = self._wire(monkeypatch, {
            "vms": "h", "user": "admin", "password": "pw", "tenant": "default",
        })
        vgt.generate_vast_token()
        assert factory.call_args.kwargs["tenant"] is None

    def test_blank_tenant_normalized_to_none(self, monkeypatch):
        factory, _ = self._wire(monkeypatch, {
            "vms": "h", "user": "admin", "password": "pw", "tenant": "  ",
        })
        vgt.generate_vast_token()
        assert factory.call_args.kwargs["tenant"] is None

    def test_real_tenant_preserved(self, monkeypatch):
        factory, _ = self._wire(monkeypatch, {
            "vms": "h", "user": "admin", "password": "pw", "tenant": "eng",
        })
        vgt.generate_vast_token()
        assert factory.call_args.kwargs["tenant"] == "eng"

    def test_token_printed(self, monkeypatch, capsys):
        self._wire(monkeypatch, {"vms": "h", "user": "admin", "password": "pw"})
        vgt.generate_vast_token()
        assert "TOK-123" in capsys.readouterr().out
