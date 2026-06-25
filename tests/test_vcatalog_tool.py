#!/usr/bin/env python3
"""Unit tests for vcatalog_tool.py — fully mocked, no live network or VMS."""

import importlib.util
import io
import json
import os
import sys
import unittest
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow as pa

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


class TestStreamingAccumulators(unittest.TestCase):
    def test_capacity_accumulator_batch(self):
        acc = tool.CapacityAccumulator()
        batch = pa.record_batch({
            "size": pa.array([8000, 100], type=pa.int64()),
            "used": pa.array([4096, 100], type=pa.int64()),
            "element_type": pa.array(["FILE", "DIR"]),
        })
        acc.ingest_batch(batch)
        self.assertEqual(acc.file_count, 1)
        self.assertEqual(acc.total_logical, 8000)
        self.assertEqual(acc.total_physical, 4096)

    def test_security_owner_accumulator_batch(self):
        acc = tool.SecurityOwnerAccumulator()
        batch = pa.record_batch({
            "size": pa.array([100, 200], type=pa.int64()),
            "uid": pa.array([1000, 1000], type=pa.int64()),
            "owner_name": pa.array(["alice", "alice"]),
            "nfs_mode_bits": pa.array([0o666, 0o644], type=pa.int64()),
            "element_type": pa.array(["FILE", "FILE"]),
            "name": pa.array(["open.txt", "closed.txt"]),
            "parent_path": pa.array(["/kmacs/vast-catalog/a", "/kmacs/vast-catalog/b"]),
        })
        acc.ingest_batch(batch)
        self.assertEqual(acc.file_count, 2)
        self.assertEqual(acc.owner_counts["alice"], 2)
        self.assertEqual(acc.exposed_count, 1)
        self.assertEqual(len(acc.exposed_samples), 1)

    def test_cold_files_accumulator_batch(self):
        old_ms = int((datetime.now() - timedelta(days=400)).timestamp() * 1000)
        recent_ms = int((datetime.now() - timedelta(days=10)).timestamp() * 1000)
        cutoff_ms = int((datetime.now().timestamp() - (365 * 86400)) * 1000)
        acc = tool.ColdFilesAccumulator()
        batch = pa.record_batch({
            "size": pa.array([200, 300, 100], type=pa.int64()),
            "mtime": pa.array([old_ms, recent_ms, recent_ms], type=pa.int64()),
            "extension": pa.array(["txt", "log", "dat"]),
            "name": pa.array(["cold.bin", "scrap.log", "active.dat"]),
            "element_type": pa.array(["FILE", "FILE", "FILE"]),
        })
        acc.ingest_batch(batch, cutoff_ms)
        self.assertEqual(acc.total_files, 3)
        self.assertEqual(acc.cold_count, 1)
        self.assertEqual(acc.scrap_count, 1)
        self.assertEqual(acc.waste_count, 2)


class TestIterateCatalogBatches(unittest.TestCase):
    @patch.object(tool, "connect_catalog")
    def test_stop_iteration_end_of_stream(self, mock_connect):
        batch = pa.record_batch({"size": pa.array([1], type=pa.int64())})
        reader = MagicMock()
        reader.read_next_batch.side_effect = [batch, StopIteration()]

        mock_tx = MagicMock()
        mock_tx.catalog.return_value.select.return_value = reader
        mock_session = MagicMock()
        mock_session.transaction.return_value.__enter__.return_value = mock_tx
        mock_connect.return_value = mock_session

        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        batches = list(tool.iterate_catalog_batches(ctx, ["size"]))
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].num_rows, 1)


class TestSearchSchemaMapping(unittest.TestCase):
    def test_run_search_uses_catalog_schema_columns(self):
        import inspect
        src = inspect.getsource(tool.run_search)
        filter_src = inspect.getsource(tool._apply_client_search_filters)
        self.assertIn("group_owner_name", src)
        self.assertNotIn('"group_name"', src)
        self.assertIn("timedelta(minutes=int(args.mmin))", src)
        self.assertNotIn("now_ns", src)
        self.assertIn('df["size"] > df["used"]', filter_src)
        self.assertNotIn("ibis_col.size > ibis_col.used", src)
        self.assertIn('ibis_col.phandle["handle_id"]', src)
        self.assertNotIn("file_id", src)
        stream_src = inspect.getsource(tool.stream_search_dataframe)
        self.assertIn("stream_search_dataframe", src)
        self.assertIn("iterate_catalog_batches", stream_src)


class TestStreamSearch(unittest.TestCase):
    @patch.object(tool, "iterate_catalog_batches")
    def test_sparse_search_stops_at_limit(self, mock_iter):
        batches = [
            pa.record_batch({
                "name": pa.array([f"f{idx}" for idx in range(10)]),
                "parent_path": pa.array(["/kmacs/vast-catalog/a"] * 10),
                "size": pa.array([5000] * 10, type=pa.int64()),
                "used": pa.array([4096] * 10, type=pa.int64()),
                "extension": pa.array(["txt"] * 10),
                "element_type": pa.array(["FILE"] * 10),
                "owner_name": pa.array(["alice"] * 10),
                "group_owner_name": pa.array(["staff"] * 10),
                "mtime": pa.array([datetime.now()] * 10),
            })
            for _ in range(20)
        ]
        mock_iter.return_value = iter(batches)

        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        args = argparse.Namespace(sparse=True, limit=5)
        projection = ["name", "parent_path", "size", "used", "extension", "element_type",
                      "owner_name", "group_owner_name", "mtime"]

        df, early_exit = tool.stream_search_dataframe(ctx, projection, None, args)
        self.assertTrue(early_exit)
        self.assertEqual(len(df), 5)
        self.assertEqual(mock_iter.call_count, 1)


class TestParallelCatalogAggregate(unittest.TestCase):
    @patch.object(tool, "iterate_catalog_batches")
    def test_parallel_capacity_merge(self, mock_iter):
        batch_a = pa.record_batch({
            "size": pa.array([5000], type=pa.int64()),
            "used": pa.array([4096], type=pa.int64()),
            "element_type": pa.array(["FILE"]),
        })
        batch_b = pa.record_batch({
            "size": pa.array([2000], type=pa.int64()),
            "used": pa.array([1024], type=pa.int64()),
            "element_type": pa.array(["FILE"]),
        })
        mock_iter.return_value = iter([batch_a, batch_b])
        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        acc = tool.CapacityAccumulator()
        result = tool._parallel_catalog_aggregate(
            ctx,
            ["size", "used", "element_type"],
            acc,
            tool.CapacityAccumulator.fold_batch,
            tool.CapacityAccumulator.merge_fold,
            workers=2,
        )
        self.assertIs(result, acc)
        self.assertEqual(acc.file_count, 2)
        self.assertEqual(acc.total_logical, 7000)
        self.assertEqual(acc.total_physical, 5120)


class TestUpdateQuotasBrief(unittest.TestCase):
    @patch.object(tool, "_vastpy_cli")
    @patch.object(tool, "time")
    def test_brief_mode_skips_registration_steps(self, mock_time, mock_cli):
        mock_cli.return_value = MagicMock(stdout="used_inodes|0.1|/kmacs/vast-catalog/ws1\n")
        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.run_update_quotas(ctx, brief=True, vms_password="secret")
        self.assertEqual(rc, 0)
        get_calls = [c for c in mock_cli.call_args_list if len(c.args) >= 2 and c.args[1] == "get"]
        post_calls = [c for c in mock_cli.call_args_list if len(c.args) >= 2 and c.args[1] == "post"]
        self.assertEqual(len(get_calls), 1)
        self.assertGreater(len(post_calls), 0)
        self.assertIn("QUOTA ALLOCATION MATRIX", buf.getvalue())


class TestShowCapacityMocked(unittest.TestCase):
    @patch.object(tool, "iterate_catalog_batches")
    def test_capacity_report_renders(self, mock_iter):
        batch = pa.record_batch({
            "size": pa.array([5000, 2_000_000], type=pa.int64()),
            "used": pa.array([4096, 1_000_000], type=pa.int64()),
            "element_type": pa.array(["FILE", "FILE"]),
        })
        mock_iter.return_value = iter([batch])
        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms", vms_user="admin",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.run_show_capacity(ctx)
        self.assertEqual(rc, 0)
        self.assertIn("CAPACITY PROFILE", buf.getvalue())
        self.assertIn("2", buf.getvalue())  # two files profiled


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


class TestTranslatePathEngine(unittest.TestCase):
    MOUNT = "/mnt/kmacs-root/vast-catalog"
    PREFIX = "/kmacs/vast-catalog"
    BUCKET = "kmacs-vast-catalog-test-bucket"

    def test_posix_to_catalog(self):
        posix = f"{self.MOUNT}/workspace_1/image.JPEG"
        coords = tool.translate_path_coordinates(posix, self.MOUNT, self.PREFIX, self.BUCKET)
        self.assertEqual(coords.catalog_path, f"{self.PREFIX}/workspace_1/image.JPEG")

    def test_catalog_to_posix(self):
        logical = f"{self.PREFIX}/workspace_1/image.JPEG"
        coords = tool.translate_path_coordinates(logical, self.MOUNT, self.PREFIX, self.BUCKET)
        self.assertEqual(coords.nfs_path, f"{self.MOUNT}/workspace_1/image.JPEG")


class TestVmsCredentials(unittest.TestCase):
    @patch.object(tool, "load_vast_config")
    def test_resolve_vms_credentials_prefers_vastconf(self, mock_load):
        mock_load.return_value = {
            "vms": "vms.lab.example",
            "user": "admin",
            "password": "from-vastconf",
            "tenant": "default",
        }
        ctx = tool.ToolContext(
            config={"vms_address": "wrong.host", "vms_user": "wrong", "token": "stale"},
            config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="wrong.host", vms_user="wrong",
        )
        creds = tool.resolve_vms_credentials(ctx)
        self.assertEqual(creds["address"], "vms.lab.example")
        self.assertEqual(creds["user"], "admin")
        self.assertEqual(creds["password"], "from-vastconf")
        self.assertIsNone(creds["token"])
        self.assertIsNone(creds["tenant"])

    @patch.object(tool, "load_vast_config", side_effect=FileNotFoundError("missing"))
    def test_resolve_vms_credentials_falls_back_to_catalog(self, mock_load):
        ctx = tool.ToolContext(
            config={"vms_address": "vms.catalog", "vms_user": "admin", "vms_password": "secret"},
            config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/test", bucket_name="b", vms_address="vms.catalog", vms_user="admin",
        )
        creds = tool.resolve_vms_credentials(ctx)
        self.assertEqual(creds["address"], "vms.catalog")
        self.assertEqual(creds["password"], "secret")


class TestDRREngine(unittest.TestCase):
    def test_compute_drr_metrics_exact(self):
        drr, savings = tool.compute_drr_metrics(400, 100)
        self.assertEqual(drr, "4.00:1")
        self.assertEqual(savings, "75.00%")

    def test_data_reduction_rates_math(self):
        logical = 100 * 1024**3
        unique = 25 * 1024**3
        usable = 20 * 1024**3
        report = tool.compute_data_reduction_rates(
            "/kmacs/vast-catalog", logical, unique, usable, file_count=1,
        )
        self.assertEqual(report.global_ratio, "5.00:1")
        self.assertEqual(report.net_savings_pct, "80.00%")
        self.assertEqual(report.dedup_savings_pct, "40.00%")
        self.assertEqual(report.similarity_savings_pct, "35.00%")
        self.assertEqual(report.compression_savings_pct, "5.00%")
        self.assertEqual(report.dedup_ratio, "4.00:1")
        self.assertEqual(report.compression_ratio, "1.25:1")

    @patch.object(tool, "fetch_path_reduction_metrics")
    @patch.object(tool, "get_vastpy_client")
    def test_data_reduction_rates_dashboard(self, mock_client, mock_fetch):
        logical = 100 * 1024**3
        usable = 20 * 1024**3
        mock_fetch.return_value = {
            "path": "/kmacs/vast-catalog",
            "logical": logical,
            "unique": 25 * 1024**3,
            "usable": usable,
            "inodes": 100,
            "source": "GET /api/capacity/ + GET /api/quotas/",
        }
        ctx = tool.ToolContext(
            config={"token": "t", "vms_address": "vms"}, config_path="/tmp/cfg",
            catalog_prefix="/kmacs/vast-catalog", mount_path="/mnt/test",
            bucket_name="b", vms_address="vms", vms_user="admin",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.run_show_data_reduction_rates(ctx)
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("MULTI-FACTOR DATA REDUCTION DEEP DIVE", output)
        self.assertIn("GET /api/capacity/", output)
        self.assertIn("5.00:1", output)
        self.assertIn("80.00%", output)
        self.assertIn("40.00%", output)
        self.assertIn("35.00%", output)
        self.assertIn("5.00%", output)

    def test_parse_capacity_response_details(self):
        payload = {
            "keys": ["usable", "unique", "logical"],
            "details": [[
                "/kmacs/vast-catalog",
                {"data": [20 * 1024**3, 25 * 1024**3, 100 * 1024**3]},
            ]],
        }
        data = tool._capacity_data_vector(payload, "/kmacs/vast-catalog")
        self.assertEqual(data, [20 * 1024**3, 25 * 1024**3, 100 * 1024**3])

    def test_resolve_reduction_scan_paths(self):
        ctx = tool.ToolContext(
            config={}, config_path="/tmp/cfg", catalog_prefix="/kmacs/vast-catalog",
            mount_path="/mnt/kmacs-root/vast-catalog", bucket_name="b",
            vms_address="vms", vms_user="admin",
        )
        paths = tool.resolve_reduction_scan_paths(
            ctx, ["/mnt/kmacs-root/vast-catalog/workspace_1", "workspace_2"],
        )
        self.assertEqual(paths[0], "/kmacs/vast-catalog/workspace_1")
        self.assertEqual(paths[1], "/kmacs/vast-catalog/workspace_2")


class TestNewArgparseModes(unittest.TestCase):
    def test_translate_path_mode(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--translate-path", "/mnt/kmacs-root/vast-catalog/foo.txt"])
        self.assertEqual(args.translate_path, "/mnt/kmacs-root/vast-catalog/foo.txt")

    def test_show_data_reduction_mode(self):
        parser = tool.build_parser()
        args = parser.parse_args(["--show-data-reduction", "/kmacs/vast-catalog/workspace_1"])
        self.assertEqual(args.show_data_reduction, "/kmacs/vast-catalog/workspace_1")

    def test_show_data_reduction_rates_mode(self):
        parser = tool.build_parser()
        args = parser.parse_args([
            "--show-data-reduction-rates",
            "--directory", "/kmacs/vast-catalog/workspace_1",
        ])
        self.assertTrue(args.show_data_reduction_rates)
        self.assertEqual(args.directories, ["/kmacs/vast-catalog/workspace_1"])

    def test_about_flag_in_parser(self):
        parser = tool.build_parser()
        self.assertTrue(any(
            action.dest == "about"
            for action in parser._actions
        ))

    def test_about_exits_without_mode(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tool.main(["--about"])
        self.assertEqual(rc, 0)
        output = buf.getvalue()
        self.assertIn("VAST DATA PLATFORM GUIDE", output)
        self.assertIn("Element Store", output)
        self.assertIn("Global Data Reduction", output)
        self.assertIn("--show-capacity", output)
        self.assertIn("--sparse", output)
        self.assertIn("--about", output)


if __name__ == "__main__":
    unittest.main()
