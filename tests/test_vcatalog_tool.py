#!/usr/bin/env python3
"""Unit tests for vcatalog_tool.py — fully mocked, no live network or VMS."""

import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-catalog", "vcatalog_tool.py"
)
_spec = importlib.util.spec_from_file_location("vcatalog_tool", _SCRIPT)
tool = importlib.util.module_from_spec(_spec)
sys.modules["vcatalog_tool"] = tool
_spec.loader.exec_module(tool)


class TestFormatBytes(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(tool.format_bytes(0), "0.00 B")

    def test_kilobytes(self):
        self.assertEqual(tool.format_bytes(2048), "2.00 KB")

    def test_megabytes(self):
        self.assertIn("MB", tool.format_bytes(5 * 1024 * 1024))


class TestParseHumanSize(unittest.TestCase):
    def test_plain_bytes(self):
        self.assertEqual(tool.parse_human_size("512"), 512)

    def test_megabytes(self):
        self.assertEqual(tool.parse_human_size("10M"), 10 * 1024 * 1024)

    def test_gigabytes(self):
        self.assertEqual(tool.parse_human_size("2G"), 2 * 1024**3)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            tool.parse_human_size("not-a-size")


class TestCategorizeSize(unittest.TestCase):
    def test_tiny(self):
        self.assertIn("Tiny", tool.categorize_size(100))

    def test_large(self):
        self.assertIn("Large", tool.categorize_size(2 * 1024 * 1024))


class TestPathHelpers(unittest.TestCase):
    def test_clean_catalog_path(self):
        result = tool.clean_catalog_path("/kmacs/vast-catalog/deep/file", "/kmacs/vast-catalog")
        self.assertEqual(result, "deep/file")

    def test_nfs_path_to_s3_key(self):
        key = tool.nfs_path_to_s3_key(
            "/mnt/kmacs-root/vast-catalog/linux-2.6.11/foo.txt",
            "/mnt/kmacs-root/vast-catalog",
        )
        self.assertEqual(key, "linux-2.6.11/foo.txt")

    def test_parse_tag_pair(self):
        self.assertEqual(tool.parse_tag_pair("owner=team"), ("owner", "team"))


class TestColdFileAgeLogic(unittest.TestCase):
    def test_age_days_computation(self):
        old_ts = int((datetime.now() - timedelta(days=400)).timestamp() * 1000)
        recent_ts = int((datetime.now() - timedelta(days=10)).timestamp() * 1000)
        df = pd.DataFrame({"mtime": [old_ts, recent_ts], "size": [100, 200]})
        df["mtime_dt"] = pd.to_datetime(df["mtime"], unit="ms")
        df["age_days"] = (pd.Timestamp.now() - df["mtime_dt"]).dt.days
        cold = df[df["age_days"] > 365]
        self.assertEqual(len(cold), 1)


class TestOwnerGrouping(unittest.TestCase):
    def test_groupby_owner(self):
        df = pd.DataFrame({
            "owner_name": ["alice", "alice", "bob"],
            "name": ["a", "b", "c"],
            "size": [100, 200, 500],
        })
        summary = df.groupby("owner_name").agg(
            file_count=("name", "count"), total_bytes=("size", "sum"),
        ).reset_index()
        self.assertEqual(summary.loc[summary["owner_name"] == "bob", "file_count"].iloc[0], 1)
        self.assertEqual(summary.loc[summary["owner_name"] == "alice", "total_bytes"].iloc[0], 300)


class TestArgparseLayout(unittest.TestCase):
    def test_mutually_exclusive_modes(self):
        parser = tool.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--show-capacity", "--show-schema"])

    def test_show_capacity_parses(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--show-capacity"])
        self.assertTrue(args.show_capacity)

    def test_search_requires_filters_validated_in_main(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--search", "--ext", "txt"])
        self.assertTrue(args.search)
        self.assertEqual(args.ext, "txt")

    def test_cold_files_num_days_default(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--show-cold-files"])
        self.assertEqual(args.num_days, 365)

    def test_s3_tag_requires_target_at_runtime(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--add-s3-tag", "k=v"])
        self.assertTrue(args.add_s3_tag)
        self.assertIsNone(args.s3_target)
        with patch.object(tool, "build_context") as mock_ctx:
            mock_ctx.return_value = tool.ToolContext(
                config={}, config_path="/tmp/cfg", catalog_prefix="/k",
                mount_path="/mnt", bucket_name="b", vms_address="v", vms_user="a",
            )
            with self.assertRaises(SystemExit):
                tool.main(["--add-s3-tag", "k=v"])

    def test_global_overrides(self):
        parser = tool.build_parser()
        args = parser.parse_args([
            "--show-schema",
            "--config", "/tmp/test.json",
            "--catalog-prefix", "/custom",
            "--mount-path", "/mnt/custom",
        ])
        self.assertEqual(args.catalog_prefix, "/custom")
        self.assertEqual(args.mount_path, "/mnt/custom")


class TestBuildContext(unittest.TestCase):
    def test_context_merges_config(self):
        parser = tool.build_parser()
        with patch.object(tool, "load_config", return_value={
            "mount_path": "/mnt/from-config",
            "vast_endpoint": "http://vip",
        }):
            args = parser.parse_args(["--show-schema"])
            ctx = tool.build_context(args)
            self.assertEqual(ctx.mount_path, "/mnt/from-config")
            self.assertEqual(ctx.catalog_prefix, tool.DEFAULT_CATALOG_PREFIX)


class TestShowCapacityMocked(unittest.TestCase):
    @patch.object(tool, "fetch_catalog_df")
    def test_capacity_report_renders(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame({
            "name": ["f1", "f2"],
            "parent_path": ["/kmacs/vast-catalog/a", "/kmacs/vast-catalog/b"],
            "size": [5000, 2_000_000],
            "used": [4096, 1_000_000],
            "extension": ["txt", "dat"],
            "element_type": ["FILE", "FILE"],
        })
        parser = tool.build_parser()
        args = parser.parse_args(["--show-capacity"])
        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.run_show_capacity(ctx)
        self.assertEqual(rc, 0)
        self.assertIn("CAPACITY PROFILE", buf.getvalue())


class TestS3TagMutationMocked(unittest.TestCase):
    @patch.object(tool, "_s3_client")
    def test_add_tag(self, mock_client_fn):
        client = MagicMock()
        mock_client_fn.return_value = client
        client.get_object_tagging.return_value = {"TagSet": []}
        ctx = tool.ToolContext(
            config={"vast_endpoint": "http://x"}, config_path="/tmp/cfg",
            catalog_prefix="/kmacs/vast-catalog", mount_path="/mnt/test",
            bucket_name="test-bucket", vms_address="vms", vms_user="admin",
        )
        target = "/mnt/test/sample.tmp"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.run_s3_tag_mutation(ctx, target, "owner=team", None, None)
        self.assertEqual(rc, 0)
        client.put_object_tagging.assert_called_once()
        self.assertIn("owner=team", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
