"""Unit tests for vcatalog_cyberdemo.py (mocked — no live VMS)."""

import importlib.util
import json
import os
import sys
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# vcatalog_cyberdemo.py imports pandas + vastdb; skip the suite when absent
pd = pytest.importorskip("pandas")
pytest.importorskip("vastdb")

_script_path = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-catalog", "vcatalog_cyberdemo.py"
)
_spec = importlib.util.spec_from_file_location("vcatalog_cyberdemo", _script_path)
demo = importlib.util.module_from_spec(_spec)
sys.modules["vcatalog_cyberdemo"] = demo
_spec.loader.exec_module(demo)


@pytest.fixture
def config_file(tmp_path):
    """Write a temporary catalog config and patch DEFAULT_CONFIG_PATH."""
    cfg = {
        "vast_endpoint": "http://test-vip",
        "access_key": "AKIA_TEST",
        "secret_key": "secret",
        "mount_path": str(tmp_path / "mount"),
    }
    path = tmp_path / "vast-catalog-config.json"
    path.write_text(json.dumps(cfg))
    with patch.object(demo, "DEFAULT_CONFIG_PATH", str(path)):
        yield cfg, str(tmp_path / "mount")


class TestConfig:
    def test_load_config_missing_exits(self):
        with patch.object(demo, "DEFAULT_CONFIG_PATH", "/nonexistent/config.json"):
            with pytest.raises(SystemExit):
                demo.load_vcatalog_config()

    def test_resolve_mount_path_trailing_slash(self, config_file):
        cfg, mount = config_file
        assert demo.resolve_mount_path(cfg).endswith("/")


class TestMalwareSimulator:
    def test_lock_and_zip_creates_malware_container(self, tmp_path):
        src = tmp_path / "sample.txt"
        src.write_text("payload")
        sim = demo.MalwareSimulator(str(tmp_path), max_affected=1)

        assert sim._lock_and_zip_file(str(src)) is True
        assert not src.exists()
        assert (tmp_path / "sample.txt.malware").exists()

        with zipfile.ZipFile(tmp_path / "sample.txt.malware") as zf:
            assert "sample.txt" in zf.namelist()


class TestResetEngine:
    def test_verified_safe_when_original_exists(self, config_file):
        _, mount = config_file
        os.makedirs(mount, exist_ok=True)
        original = os.path.join(mount, "restored.txt")
        with open(original, "w") as fh:
            fh.write("ok")

        row = pd.Series({"name": "restored.txt.malware", "parent_path": demo.CATALOG_PATH_PREFIX})
        engine = demo.ResetEngine(session=MagicMock(), mount_path=mount + "/")
        assert engine._restore_file(row) == "VERIFIED_SAFE"

    def test_restore_from_malware_container(self, config_file):
        _, mount = config_file
        os.makedirs(mount, exist_ok=True)
        malware = os.path.join(mount, "doc.txt.malware")
        with zipfile.ZipFile(malware, "w") as zf:
            zf.writestr("doc.txt", "content")

        row = pd.Series({"name": "doc.txt.malware", "parent_path": demo.CATALOG_PATH_PREFIX})
        engine = demo.ResetEngine(session=MagicMock(), mount_path=mount + "/")
        assert engine._restore_file(row) == "RESTORED"
        assert os.path.exists(os.path.join(mount, "doc.txt"))
        assert not os.path.exists(malware)


class TestHelpers:
    def test_clean_parent_path(self):
        raw = "/kmacs/vast-catalog/deep/nested"
        assert demo.clean_parent_path(raw) == "deep/nested"
