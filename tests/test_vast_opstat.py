################################################################################
# Script Name:    test_vast_opstat.py
# Description:    Unit tests for vast-opstat CLI routing and NFS v3 metrics logic.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_OPSTAT_DIR = os.path.join(os.path.dirname(__file__), "..", "vast", "vast-opstat")
_OPSTAT_SCRIPT = os.path.join(_OPSTAT_DIR, "vast-opstat.py")
_NFS_V3_SCRIPT = os.path.join(_OPSTAT_DIR, "nfs_v3.py")
_NFS_V41_SCRIPT = os.path.join(_OPSTAT_DIR, "nfs_v41.py")
_NVME_TCP_SCRIPT = os.path.join(_OPSTAT_DIR, "nvme_tcp.py")
_SMB_SCRIPT = os.path.join(_OPSTAT_DIR, "smb.py")
_VAST_API_LOG_SCRIPT = os.path.join(_OPSTAT_DIR, "vast_api_log.py")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


opstat = _load_module("vast_opstat", _OPSTAT_SCRIPT)
nfs_v3 = _load_module("vast_opstat_nfs_v3", _NFS_V3_SCRIPT)
nfs_v41 = _load_module("vast_opstat_nfs_v41", _NFS_V41_SCRIPT)
nvme_tcp = _load_module("vast_opstat_nvme_tcp", _NVME_TCP_SCRIPT)
smb = _load_module("vast_opstat_smb", _SMB_SCRIPT)
vast_api_log = _load_module("vast_opstat_api_log", _VAST_API_LOG_SCRIPT)
openmetrics = nfs_v3.openmetrics

BASE_ARGS = [
    "--vms", "203.0.113.10",
    "--user", "admin",
    "--password", "secret",
    "--no-color",
]


def _connection_args(**overrides):
    values = {
        "vms": "203.0.113.10",
        "port": 443,
        "user": "admin",
        "password": "secret",
        "sample_average": None,
        "refresh": 5,
        "csv": None,
        "no_color": True,
        "discover_metrics": False,
        "log_api_calls": False,
        "nfs": True,
        "block": False,
        "smb": False,
        "nvme_over_tcp": False,
        "protocol_version": "3.0",
        "volumes": None,
        "clients": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TestCliParsing:
    def test_nfs_v3_flags_parse_and_validate(self):
        args = opstat.parse_args(["--nfs", "--version=3.0", *BASE_ARGS])
        assert args.nfs is True
        assert args.protocol_version == "3.0"
        assert args.vms == "203.0.113.10"

    def test_nfs_without_version_exits(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", *BASE_ARGS])
        assert "--version is required" in str(exc.value)

    def test_unsupported_nfs_version_exits(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", "--version=9.9", *BASE_ARGS])
        assert "Unsupported NFS version" in str(exc.value)

    def test_planned_nfs_version_exits(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", "--version=4.2", *BASE_ARGS])
        assert "not implemented yet" in str(exc.value)

    def test_nfs_v41_flags_parse_and_validate(self):
        args = opstat.parse_args(["--nfs", "--version=4.1", *BASE_ARGS])
        assert args.nfs is True
        assert args.protocol_version == "4.1"

    def test_nfs_version_shorthand_aliases(self):
        assert opstat.parse_args(["--nfs", "--version=3", *BASE_ARGS]).protocol_version == "3.0"
        assert opstat.parse_args(["--nfs", "--version=4", *BASE_ARGS]).protocol_version == "4.1"

    def test_nfs_version_3_dispatches_to_v3(self):
        args = opstat.parse_args(["--nfs", "--version=3", *BASE_ARGS])
        with patch.object(opstat.nfs_v3, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)

    def test_block_without_nvme_over_tcp_exits(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--block", *BASE_ARGS])
        assert "--block requires --nvme-over-tcp" in str(exc.value)

    def test_block_nvme_over_tcp_flags_parse(self):
        args = opstat.parse_args(["--block", "--nvme-over-tcp", *BASE_ARGS])
        assert args.block is True
        assert args.nvme_over_tcp is True

    def test_block_volume_flags_parse(self):
        args = opstat.parse_args(
            ["--block", "--nvme-over-tcp", "--volumes", "vol-a,vol-b", *BASE_ARGS]
        )
        assert args.volumes == "vol-a,vol-b"

    def test_smb_flags_parse(self):
        args = opstat.parse_args(["--smb", *BASE_ARGS])
        assert args.smb is True
        assert args.nfs is False

    def test_smb_client_flags_parse(self):
        args = opstat.parse_args(
            ["--smb", "--clients", "10.1.1.5,10.1.1.6", *BASE_ARGS]
        )
        assert args.clients == "10.1.1.5,10.1.1.6"

    def test_clients_without_smb_exits(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", "--version=3.0", "--clients", "10.0.0.1", *BASE_ARGS])
        assert "--client/--clients is only supported with --smb" in str(exc.value)

    def test_tool_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", "--version=3.0", *BASE_ARGS, "--tool-version"])
        assert exc.value.code == 0
        assert opstat.VERSION in capsys.readouterr().out

    def test_vms_port_flag_parse(self):
        args = opstat.parse_args(
            ["--nfs", "--version=3.0", "--vms-port", "8443", *BASE_ARGS]
        )
        assert args.port == 8443

    def test_port_alias_still_works(self):
        args = opstat.parse_args(
            ["--nfs", "--version=3.0", "--port", "9443", *BASE_ARGS]
        )
        assert args.port == 9443

    def test_vms_port_builds_base_url(self):
        nfs_v3.init_config(_connection_args(port=8443))
        assert nfs_v3.BASE_URL == "https://203.0.113.10:8443/api"

    def test_default_vms_port_omits_colon_in_url(self):
        nfs_v3.init_config(_connection_args(port=443))
        assert nfs_v3.BASE_URL == "https://203.0.113.10/api"

    def test_log_api_calls_flag_parse(self):
        args = opstat.parse_args(
            ["--nfs", "--version=3.0", "--log-api-calls", *BASE_ARGS]
        )
        assert args.log_api_calls is True


class TestVastApiLog:
    def setup_method(self):
        vast_api_log.close()

    def teardown_method(self):
        vast_api_log.close()

    def test_configure_writes_under_tmp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vast_api_log.os, "getpid", lambda: 99999)
        log_path = vast_api_log.configure(True, "nfs-v3", "vms.example.com", 443)
        assert log_path.startswith("/tmp/vast-opstat-api-nfs-v3-vms.example.com-443-99999.log")
        vast_api_log.log_call("GET", "https://vms.example.com/api/clusters/", None, 200, "[]", None, 12.5)
        vast_api_log.close()
        with open(log_path, encoding="utf-8") as handle:
            text = handle.read()
        assert "session start" in text
        assert "GET https://vms.example.com/api/clusters/" in text
        assert "HTTP 200" in text
        os.remove(log_path)

    def test_api_request_logs_when_enabled(self):
        vast_api_log.configure(True, "nfs-v3", "203.0.113.10", 443)
        log_path = vast_api_log.log_path()
        nfs_v3.init_config(_connection_args(log_api_calls=True))

        class FakeResp:
            status = 200

            def read(self):
                return b'[{"id": 1}]'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(nfs_v3.vast_common.urllib.request, "urlopen", return_value=FakeResp()):
            result = nfs_v3.api_request("GET", "/clusters/")

        assert result == [{"id": 1}]
        nfs_v3.vast_api_log.close()
        with open(log_path, encoding="utf-8") as handle:
            text = handle.read()
        assert "GET https://203.0.113.10/api/clusters/" in text
        os.remove(log_path)


class TestNfsV3Metrics:
    def test_metric_names_for_op_null(self):
        assert nfs_v3.metric_names_for_op("null") == {
            "rate": "NfsMetrics,nfs_null",
            "avg": None,
        }

    def test_metric_names_for_op_read(self):
        names = nfs_v3.metric_names_for_op("read")
        assert names["rate"] == "NfsMetrics,nfs_read_latency__rate"
        assert names["avg"] == "NfsMetrics,nfs_read_latency__avg"

    def test_build_rpc_prop_list_includes_all_ops(self):
        props = nfs_v3.build_rpc_prop_list()
        assert "NfsMetrics,nfs_null" in props
        assert "NfsMetrics,nfs_read_latency__rate" in props
        assert "NfsMetrics,nfs_read_latency__avg" in props
        assert "NfsMetrics,nfs_commit_latency__avg" in props

    def test_build_bw_prop_list(self):
        assert nfs_v3.build_bw_prop_list() == [
            nfs_v3.NFS_READ_BW_FQN,
            nfs_v3.NFS_WRITE_BW_FQN,
        ]

    def test_build_rows_from_results_single_sample(self):
        nfs_v3.init_config(_connection_args())
        rpc_result = {
            "prop_list": [
                "timestamp",
                "NfsMetrics,nfs_read_latency__rate",
                "NfsMetrics,nfs_read_latency__avg",
                "NfsMetrics,nfs_write_latency__rate",
                "NfsMetrics,nfs_write_latency__avg",
            ],
            "data": [["t1", 100.0, 500.0, 50.0, 2000.0]],
        }
        bw_result = {
            "prop_list": [
                "timestamp",
                nfs_v3.NFS_READ_BW_FQN,
                nfs_v3.NFS_WRITE_BW_FQN,
            ],
            "data": [["t1", 2_000_000_000.0, 1_000_000_000.0]],
        }

        rows, sample = nfs_v3.build_rows_from_results(rpc_result, bw_result)
        by_label = {row["label"]: row for row in rows}

        assert sample == "t1"
        assert by_label["READ"]["ops_sec"] == 100.0
        assert by_label["READ"]["avg_us"] == 500.0
        assert by_label["READ"]["bw_gbs"] == pytest.approx(2.0)
        assert by_label["WRITE"]["ops_sec"] == 50.0
        assert by_label["WRITE"]["bw_gbs"] == pytest.approx(1.0)
        assert by_label["READ"]["pct"] == pytest.approx(100.0 * 100.0 / 150.0)

    def test_classify_workload_read_heavy(self):
        rows = [
            {"label": "READ", "ops_sec": 900, "avg_io_bytes": 65536},
            {"label": "WRITE", "ops_sec": 50, "avg_io_bytes": None},
            {"label": "GETATTR", "ops_sec": 50, "avg_io_bytes": None},
        ]
        assert "read-heavy" in nfs_v3.classify_workload(rows)

    def test_nfs_health_label_healthy(self):
        label, _color = nfs_v3.nfs_health_label(100.0, 500.0)
        assert label == "HEALTHY"

    def test_nfs_health_label_idle(self):
        label, _color = nfs_v3.nfs_health_label(0.1, None)
        assert label == "IDLE"

    def test_compute_deltas(self):
        current = [{"label": "READ", "ops_sec": 110, "avg_us": 400, "bw_gbs": 2.0}]
        previous = [{"label": "READ", "ops_sec": 100, "avg_us": 500, "bw_gbs": 1.5}]
        deltas = nfs_v3.compute_deltas(current, previous)
        assert deltas["READ"]["ops"] == pytest.approx(10.0)
        assert deltas["READ"]["lat"] == pytest.approx(-100.0)
        assert deltas["READ"]["bw"] == pytest.approx(0.5)


class TestNfsV3ApiLayer:
    def test_get_current_cluster(self):
        nfs_v3.init_config(_connection_args())
        payload = [{"id": 7, "name": "lab-cluster", "is_local": True}]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_resp):
            cluster_id, cluster_name = nfs_v3.get_current_cluster()

        assert cluster_id == 7
        assert cluster_name == "lab-cluster"

    def test_create_monitor_uses_opstat_prefix(self):
        nfs_v3.init_config(_connection_args())
        created = {}

        def fake_api_request(method, path, payload=None):
            if method == "POST" and path == "/monitors/":
                created["name"] = payload["name"]
                return {"id": 99}
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            nfs_v3.CLUSTER_ID = 1
            monitor_id = nfs_v3.create_monitor("rpc", ["metric-a"])

        assert monitor_id == 99
        assert created["name"].startswith("adhoc_vast-opstat_rpc_")


class TestNfsDrillEndpoints:
    """Drill-down paths must be relative to BASE_URL (/api), not include /api again."""

    def test_drill_cfg_endpoints_are_single_prefix_paths(self):
        for mode, cfg in nfs_v3._DRILL_CFG.items():
            endpoint = cfg["endpoint"]
            assert endpoint.startswith("/"), mode
            assert not endpoint.startswith("/api/"), mode
            assert "//" not in endpoint.strip("/"), mode

    def test_enter_drill_mode_requests_correct_url(self):
        nfs_v3.init_config(_connection_args())
        nfs_v3.CLUSTER_ID = 1
        captured = []
        monitor_ids = iter([10])

        def fake_api_request(method, path, payload=None):
            captured.append((method, path, payload))
            if method == "GET" and path == "/cnodes/":
                return [{"id": 1, "name": "cnode-1"}]
            if method == "POST" and path == "/monitors/":
                return {"id": next(monitor_ids)}
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            nfs_v3.enter_drill_mode("cnode")

        assert captured[0][0:2] == ("GET", "/cnodes/")
        assert nfs_v3.DRILL_MODE == "cnode"
        assert nfs_v3.DRILL_ERROR is None
        assert len(nfs_v3.DRILL_MONITORS) == 1
        create_payload = captured[1][2]
        assert "aggregation" in create_payload

    def test_view_drill_monitor_omits_aggregation(self):
        nfs_v3.init_config(_connection_args())
        nfs_v3.CLUSTER_ID = 1
        payloads = []
        monitor_seq = iter([100, 101])

        def fake_api_request(method, path, payload=None):
            if method == "GET" and path == "/views/":
                return [{"id": 7, "path": "/data"}]
            if method == "GET" and path.startswith("/monitors/") and path.endswith("/query/"):
                return {
                    "prop_list": ["timestamp", "object_id", nfs_v3._VIEW_READ_IOPS],
                    "data": [["2026-07-01T00:00:00Z", 7, 1.0]],
                }
            if method == "POST" and path == "/monitors/":
                payloads.append(payload)
                return {"id": next(monitor_seq)}
            if method == "DELETE" and path.startswith("/monitors/"):
                return None
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            nfs_v3.enter_drill_mode("view")

        assert nfs_v3.DRILL_MODE == "view"
        assert len(nfs_v3.DRILL_MONITORS) == 1
        assert nfs_v3.DRILL_MONITORS[0][1] is None
        assert all("aggregation" not in p for p in payloads)
        assert payloads[0]["object_ids"] == [7]
        assert payloads[1]["object_ids"] == [7]
        assert payloads[0]["prop_list"] == nfs_v3.build_drill_rank_prop_list("view")
        assert payloads[1]["prop_list"][0].startswith("ViewMetrics,")

    def test_view_drill_entry_uses_batch_rank_and_display_monitors(self):
        nfs_v3.init_config(_connection_args())
        nfs_v3.CLUSTER_ID = 1
        views = [{"id": i, "path": f"/v{i}"} for i in range(1, 4)]
        calls = []
        monitor_seq = iter([900, 901])

        def fake_api_request(method, path, payload=None):
            calls.append((method, path))
            if method == "GET" and path == "/views/":
                return views
            if method == "POST" and path == "/monitors/":
                return {"id": next(monitor_seq)}
            if method == "GET" and path.endswith("/query/"):
                rows = [
                    ["2026-07-01T00:00:00Z", vid, 1.0, 0.0, 0.0, 0.0]
                    for vid in (1, 2, 3)
                ]
                return {
                    "prop_list": [
                        "timestamp",
                        "object_id",
                        nfs_v3._VIEW_READ_IOPS,
                        nfs_v3._VIEW_WRITE_IOPS,
                        nfs_v3._VIEW_READ_MD,
                        nfs_v3._VIEW_WRITE_MD,
                    ],
                    "data": rows,
                }
            if method == "DELETE":
                return None
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            nfs_v3.enter_drill_mode("view")

        post_calls = [c for c in calls if c[0] == "POST"]
        get_query_calls = [c for c in calls if c[0] == "GET" and c[1].endswith("/query/")]
        assert len(post_calls) == 2
        assert len(get_query_calls) == 1
        assert len(nfs_v3.DRILL_MONITORS) == 1

    def test_view_ranking_scans_all_objects_beyond_probe_limit(self):
        # Regression: active views listed past _DRILL_PROBE_LIMIT must still be
        # ranked (previously the probe pool was truncated to the first N views,
        # so a busy view listed later showed near-zero and was hidden).
        nfs_v3.init_config(_connection_args())
        nfs_v3.CLUSTER_ID = 1
        total = nfs_v3._DRILL_PROBE_LIMIT + 8
        busy_id = nfs_v3._DRILL_PROBE_LIMIT + 5   # lives in the 2nd chunk
        views = [{"id": i, "path": f"/v{i}"} for i in range(total)]
        rank_query_count = 0

        def fake_api_request(method, path, payload=None):
            nonlocal rank_query_count
            if method == "GET" and path == "/views/":
                return views
            if method == "POST" and path == "/monitors/":
                return {"id": 5000 + len(payload["object_ids"])}
            if method == "GET" and path.endswith("/query/"):
                rank_query_count += 1
                rows = [
                    ["2026-07-01T00:00:00Z", vid,
                     (100.0 if vid == busy_id else 0.0), 0.0, 0.0, 0.0]
                    for vid in range(total)
                ]
                return {
                    "prop_list": [
                        "timestamp", "object_id",
                        nfs_v3._VIEW_READ_IOPS, nfs_v3._VIEW_WRITE_IOPS,
                        nfs_v3._VIEW_READ_MD, nfs_v3._VIEW_WRITE_MD,
                    ],
                    "data": rows,
                }
            if method == "DELETE":
                return None
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            objs = [{"id": v["id"], "path": v["path"]} for v in views]
            ranked = nfs_v3._rank_drill_candidates("view", objs, nfs_v3._DRILL_CFG["view"])

        # More than one chunk was probed, and the busy view ranked first.
        assert rank_query_count >= 2
        assert ranked[0]["id"] == busy_id

    def test_fetch_drill_query_view_uses_single_batch_get(self):
        nfs_v3.init_config(_connection_args())
        nfs_v3.DRILL_MODE = "view"
        nfs_v3.DRILL_OBJECTS = [
            {"id": 1, "name": "/a"},
            {"id": 2, "name": "/b"},
        ]
        nfs_v3.DRILL_MONITORS = [(55, None)]
        calls = []

        def fake_api_request(method, path, payload=None):
            calls.append((method, path))
            return {
                "prop_list": [
                    "timestamp",
                    "object_id",
                    nfs_v3._VIEW_READ_IOPS,
                    nfs_v3._VIEW_WRITE_IOPS,
                    nfs_v3._VIEW_READ_LAT,
                    nfs_v3._VIEW_WRITE_LAT,
                    nfs_v3._VIEW_READ_BW,
                    nfs_v3._VIEW_WRITE_BW,
                ],
                "data": [
                    ["2026-07-01T00:00:00Z", 1, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    ["2026-07-01T00:00:00Z", 2, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                ],
            }

        with patch.object(nfs_v3, "api_request", side_effect=fake_api_request):
            nfs_v3.fetch_drill_query()

        assert calls == [("GET", "/monitors/55/query/")]
        assert len(nfs_v3.LAST_DRILL_ROWS) == 2

    def test_slice_result_for_object_filters_rows(self):
        result = {
            "prop_list": ["timestamp", "object_id", "metric"],
            "data": [
                ["2026-07-01T00:00:00Z", 1, 10.0],
                ["2026-07-01T00:00:00Z", 2, 20.0],
            ],
        }
        sliced = nfs_v3._slice_result_for_object(result, 2)
        assert sliced["data"] == [["2026-07-01T00:00:00Z", 2, 20.0]]

    def test_build_drill_prop_list_scopes(self):
        cnode_props = nfs_v3.build_drill_prop_list("cnode")
        view_props = nfs_v3.build_drill_prop_list("view")
        tenant_props = nfs_v3.build_drill_prop_list("tenant")
        assert nfs_v3._VIEW_READ_IOPS in view_props
        assert nfs_v3._TENANT_READ_IOPS in tenant_props
        assert any(p.startswith("NfsMetrics,") for p in cnode_props)

    def test_build_view_drill_row_from_rates(self):
        result = {
            "prop_list": [
                "timestamp",
                "object_id",
                nfs_v3._VIEW_READ_IOPS,
                nfs_v3._VIEW_WRITE_IOPS,
                nfs_v3._VIEW_READ_LAT,
                nfs_v3._VIEW_WRITE_LAT,
                nfs_v3._VIEW_READ_BW,
                nfs_v3._VIEW_WRITE_BW,
            ],
            "data": [["2026-07-01T00:00:00Z", 1, 10.0, 5.0, 100.0, 200.0, 1_000_000_000.0, 0.0]],
        }
        row = nfs_v3._build_view_drill_row(result, "/data")
        assert row["name"] == "/data"
        assert row["total_ops"] == pytest.approx(15.0)
        assert row["top_rpc"] == "READ"
        assert row["bw_gbs"] == pytest.approx(1.0)

    def test_rank_drill_candidates_sorts_by_ops(self):
        nfs_v3.init_config(_connection_args())
        cfg = nfs_v3._DRILL_CFG["view"]
        objects = [{"id": 1, "path": "/idle"}, {"id": 2, "path": "/hot"}]
        rows_by_id = {
            1: {"total_ops": 0.1},
            2: {"total_ops": 9.5},
        }
        create_calls = []

        def fake_create(name_suffix, prop_list, object_type, object_ids, **kwargs):
            create_calls.append((name_suffix, object_ids))
            return 101

        def fake_query(_mode, result, name):
            obj_id = 2 if name == "/hot" else 1
            return {"total_ops": rows_by_id[obj_id]["total_ops"]}

        with patch.object(nfs_v3, "_create_monitor_raw", side_effect=fake_create), \
             patch.object(nfs_v3, "api_request", return_value={}), \
             patch.object(nfs_v3, "_build_drill_row", side_effect=fake_query), \
             patch.object(nfs_v3, "delete_monitor"):
            ranked = nfs_v3._rank_drill_candidates("view", objects, cfg)

        assert [item["name"] for item in ranked] == ["/hot", "/idle"]
        assert len(create_calls) == 1
        assert create_calls[0][1] == [1, 2]

    def test_switch_drill_mode_sets_ops_sort_for_view(self):
        nfs_v3.init_config(_connection_args())
        nfs_v3.SORT_MODE = "rpc"
        nfs_v3.CLUSTER_ID = 1
        nfs_v3.LAST_ROWS = []
        nfs_v3.CLUSTER_NAME = "test"

        with patch.object(nfs_v3, "render_screen"), \
             patch.object(nfs_v3, "enter_drill_mode"), \
             patch.object(nfs_v3, "fetch_drill_query"):
            nfs_v3.switch_drill_mode("view")

        assert nfs_v3.SORT_MODE == "ops"

    def test_build_tenant_drill_row_from_cumulative_samples(self):
        result = {
            "prop_list": [
                "timestamp",
                "object_id",
                nfs_v3._TENANT_READ_IOPS,
                nfs_v3._TENANT_WRITE_IOPS,
                nfs_v3._TENANT_READ_LAT,
                nfs_v3._TENANT_READ_CNT,
            ],
            "data": [
                ["2026-07-01T00:10:00Z", 1, 1200.0, 600.0, 120000.0, 120.0],
                ["2026-07-01T00:00:00Z", 1, 600.0, 300.0, 60000.0, 60.0],
            ],
        }
        row = nfs_v3._build_tenant_drill_row(result, "tenant-a")
        assert row["name"] == "tenant-a"
        assert row["total_ops"] == pytest.approx(1.5)
        assert row["latency_us"] == pytest.approx(1000.0)


class TestNfsV41Metrics:
    def test_data_monitor_props_use_nfs4_common(self):
        props = nfs_v41.build_data_monitor_props()
        assert all(p.startswith("ProtoMetrics,proto_name=NFS4Common,") for p in props)
        assert nfs_v41._data_fqn("rd_iops") in props
        assert nfs_v41._data_fqn("write_latency__avg") in props

    def test_drill_endpoints_are_not_api_prefixed(self):
        for mode, cfg in nfs_v41._DRILL_CFG.items():
            assert cfg["endpoint"].startswith("/")
            assert not cfg["endpoint"].startswith("/api/"), mode

    def test_data_monitor_props_exclude_size_and_rate(self):
        props = nfs_v41.build_data_monitor_props()
        assert nfs_v41._data_fqn("read_size__avg") not in props
        assert nfs_v41._data_fqn("read_latency__rate") not in props

    def test_build_rows_from_nfs4_common_sample(self):
        data_result = {
            "prop_list": [
                "timestamp",
                nfs_v41._data_fqn("rd_iops"),
                nfs_v41._data_fqn("wr_iops"),
                nfs_v41._data_fqn("rd_bw"),
                nfs_v41._data_fqn("wr_bw"),
                nfs_v41._data_fqn("read_latency__avg"),
                nfs_v41._data_fqn("write_latency__avg"),
            ],
            "data": [["2026-07-01T00:00:00Z", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
        }
        supplement_result = {
            "prop_list": [
                "timestamp",
                nfs_v41._nfs_fqn("read", "rate"),
                nfs_v41._nfs_fqn("read", "avg"),
                nfs_v41._nfs_fqn("write", "rate"),
                nfs_v41._nfs_fqn("write", "avg"),
                nfs_v41._nfs_fqn("lookup", "rate"),
                nfs_v41._nfs_fqn("lookup", "avg"),
            ],
            "data": [["2026-07-01T00:00:00Z", 100.0, 250.0, 50.0, 500.0, 12.0, 80.0]],
        }
        bw_result = {
            "prop_list": ["timestamp", f"{nfs_v41._NFS_COMMON},rd_bw", f"{nfs_v41._NFS_COMMON},wr_bw"],
            "data": [["2026-07-01T00:00:00Z", 1_000_000_000.0, 500_000_000.0]],
        }
        meta_result = {
            "prop_list": [
                "timestamp",
                nfs_v41._data_fqn("md_iops"),
                nfs_v41._data_fqn("rd_md_iops"),
                nfs_v41._data_fqn("wr_md_iops"),
                nfs_v41._data_fqn("latency"),
            ],
            "data": [["2026-07-01T00:00:00Z", 43.0, 30.0, 13.0, 808.0]],
        }
        snapshot, sample = nfs_v41.build_rows_from_results(
            data_result, supplement_result, bw_result, meta_result,
        )
        assert sample == "2026-07-01T00:00:00Z"
        read_row = next(r for r in snapshot["data"] if r["key"] == "read")
        assert read_row["ops_sec"] == pytest.approx(100.0)
        assert read_row["avg_us"] == pytest.approx(250.0)
        assert read_row["bw_mbs"] == pytest.approx(1000.0)
        assert read_row["avg_io_bytes"] == pytest.approx(10_000_000.0)
        assert nfs_v41.METRICS_SOURCE == "NfsMetrics supplement"
        assert snapshot["meta"]["md_iops"] == pytest.approx(43.0)
        lookup_row = next(r for r in snapshot["stateful"] if r["key"] == "lookup")
        assert lookup_row["ops_sec"] == pytest.approx(12.0)
        md_row = next(r for r in snapshot["session"] if r["key"] == "md_iops")
        assert md_row["ops_sec"] == pytest.approx(43.0)
        rd_row = next(r for r in snapshot["session"] if r["key"] == "rd_md_iops")
        assert rd_row["ops_sec"] == pytest.approx(30.0)

    def test_build_rows_nfs4common_direct_mapping(self):
        data_result = {
            "prop_list": [
                "timestamp",
                nfs_v41._data_fqn("rd_iops"),
                nfs_v41._data_fqn("wr_iops"),
                nfs_v41._data_fqn("rd_bw"),
                nfs_v41._data_fqn("wr_bw"),
                nfs_v41._data_fqn("read_latency__avg"),
                nfs_v41._data_fqn("write_latency__avg"),
            ],
            "data": [["2026-07-01T00:00:00Z", 10.0, 20.0, 5_000_000.0, 10_000_000.0, 100.0, 200.0]],
        }
        snapshot, _ = nfs_v41.build_rows_from_results(data_result)
        read_row = next(r for r in snapshot["data"] if r["key"] == "read")
        assert read_row["ops_sec"] == pytest.approx(10.0)
        assert read_row["bw_mbs"] == pytest.approx(5.0)
        assert read_row["avg_io_bytes"] == pytest.approx(500_000.0)
        assert nfs_v41.METRICS_SOURCE == "NFS4Common"


class TestNfsV41StateMetrics:
    def test_state_monitor_props_pair_rate_and_avg(self):
        ops = [("open", "OPEN"), ("lock", "LOCK")]
        props = nfs_v41.build_state_monitor_props(ops)
        assert nfs_v41._nfs_fqn("open", "rate") in props
        assert nfs_v41._nfs_fqn("open", "avg") in props
        assert nfs_v41._nfs_fqn("lock", "avg") in props
        assert len(props) == 4

    def test_collect_metric_names_is_schema_agnostic(self):
        raw = {"results": [{"name": "NfsMetrics,nfs_open_latency__rate"},
                           {"name": "NfsMetrics,nfs_lock_latency__avg"}]}
        names = nfs_v41._collect_metric_names(raw)
        assert "NfsMetrics,nfs_open_latency__rate" in names
        assert "NfsMetrics,nfs_lock_latency__avg" in names

    def test_probe_returns_only_exported_ops(self, monkeypatch):
        catalog = {"data": [
            "NfsMetrics,nfs_open_latency__rate",
            "NfsMetrics,nfs_close_latency__rate",
            "NfsMetrics,nfs_lock_latency__rate",
            "NfsMetrics,nfs_locku_latency__rate",
        ]}
        monkeypatch.setattr(nfs_v41, "api_request", lambda m, p: catalog)
        available = nfs_v41.probe_available_state_ops()
        keys = {op for op, _ in available}
        assert keys == {"open", "close", "lock", "locku"}
        assert "sequence" not in keys

    def test_probe_returns_none_when_catalog_unreadable(self, monkeypatch):
        def boom(method, path):
            raise RuntimeError("403 Forbidden")
        monkeypatch.setattr(nfs_v41, "api_request", boom)
        assert nfs_v41.probe_available_state_ops() is None

    def test_build_state_rows_from_monitor(self, monkeypatch):
        monkeypatch.setattr(nfs_v41, "STATE_OPS_AVAILABLE",
                            [("open", "OPEN"), ("lock", "LOCK")])
        state_result = {
            "prop_list": [
                "timestamp",
                nfs_v41._nfs_fqn("open", "rate"),
                nfs_v41._nfs_fqn("open", "avg"),
                nfs_v41._nfs_fqn("lock", "rate"),
                nfs_v41._nfs_fqn("lock", "avg"),
            ],
            "data": [["2026-07-01T00:00:00Z", 40.0, 300.0, 10.0, 150.0]],
        }
        snapshot, _ = nfs_v41.build_rows_from_results(
            {"prop_list": ["timestamp"], "data": []},
            state_result=state_result,
        )
        open_row = next(r for r in snapshot["state"] if r["key"] == "open")
        assert open_row["ops_sec"] == pytest.approx(40.0)
        assert open_row["avg_us"] == pytest.approx(300.0)
        assert open_row["pct"] == pytest.approx(80.0)

    def test_state_rows_empty_when_no_ops_available(self, monkeypatch):
        monkeypatch.setattr(nfs_v41, "STATE_OPS_AVAILABLE", [])
        snapshot, _ = nfs_v41.build_rows_from_results(
            {"prop_list": ["timestamp"], "data": []},
        )
        assert snapshot["state"] == []

    def test_init_state_monitor_disables_on_create_failure(self, monkeypatch):
        monkeypatch.setattr(nfs_v41, "probe_available_state_ops",
                            lambda: [("open", "OPEN")])

        def boom(name, props):
            raise RuntimeError("unknown property")
        monkeypatch.setattr(nfs_v41, "create_monitor", boom)
        monkeypatch.setattr(nfs_v41, "STATE_MONITOR_ID", None)
        monkeypatch.setattr(nfs_v41, "STATE_OPS_AVAILABLE", [("x", "X")])
        nfs_v41._init_state_monitor()
        assert nfs_v41.STATE_MONITOR_ID is None
        assert nfs_v41.STATE_OPS_AVAILABLE == []

    def test_init_state_monitor_uses_full_set_when_catalog_unreadable(self, monkeypatch):
        monkeypatch.setattr(nfs_v41, "probe_available_state_ops", lambda: None)
        captured = {}

        def fake_create(name, props):
            captured["props"] = props
            return "mon-state"
        monkeypatch.setattr(nfs_v41, "create_monitor", fake_create)
        nfs_v41._init_state_monitor()
        assert nfs_v41.STATE_MONITOR_ID == "mon-state"
        assert nfs_v41.STATE_OPS_AVAILABLE == nfs_v41.STATE_PANEL_OPS

    def test_namespace_panel_uses_real_exported_ops(self):
        keys = {op for op, _ in nfs_v41.METADATA_PROXY_OPS}
        # Confirmed exported by live discovery against a real cluster.
        for expected in ("access", "setattr", "rename", "readdirplus", "commit"):
            assert expected in keys
        props = nfs_v41.build_supplement_monitor_props()
        assert nfs_v41._nfs_fqn("rename", "rate") in props
        assert f"{nfs_v41._COMMIT_WAIT_FQN}__avg" in props

    def test_sort_rows_by_ops_desc(self, monkeypatch):
        rows = [
            {"label": "A", "ops_sec": 5.0, "avg_us": 100.0},
            {"label": "B", "ops_sec": 50.0, "avg_us": 10.0},
            {"label": "C", "ops_sec": None, "avg_us": 999.0},
        ]
        monkeypatch.setattr(nfs_v41, "SORT_MODE", "ops")
        assert [r["label"] for r in nfs_v41._sort_rows(rows)] == ["B", "A", "C"]

    def test_sort_rows_by_latency_desc_none_last(self, monkeypatch):
        rows = [
            {"label": "A", "ops_sec": 5.0, "avg_us": 100.0},
            {"label": "B", "ops_sec": 50.0, "avg_us": 900.0},
            {"label": "C", "ops_sec": 1.0, "avg_us": None},
        ]
        monkeypatch.setattr(nfs_v41, "SORT_MODE", "latency")
        assert [r["label"] for r in nfs_v41._sort_rows(rows)] == ["B", "A", "C"]

    def test_sort_rows_default_preserves_order(self, monkeypatch):
        rows = [{"label": x, "ops_sec": 1.0, "avg_us": 1.0} for x in ("A", "B", "C")]
        monkeypatch.setattr(nfs_v41, "SORT_MODE", "default")
        assert [r["label"] for r in nfs_v41._sort_rows(rows)] == ["A", "B", "C"]

    def test_commit_wait_surfaced_in_meta(self):
        supplement_result = {
            "prop_list": ["timestamp", f"{nfs_v41._COMMIT_WAIT_FQN}__avg"],
            "data": [["2026-07-01T00:00:00Z", 420.0]],
        }
        snapshot, _ = nfs_v41.build_rows_from_results(
            {"prop_list": ["timestamp"], "data": []},
            supplement_result=supplement_result,
        )
        assert snapshot["meta"]["commit_wait_us"] == pytest.approx(420.0)


class TestResolveObjectName:
    def test_root_view_labeled_default(self):
        assert nfs_v3.vast_common.resolve_object_name({"path": "/"}, ("path",)) == "/ (default)"

    def test_normal_view_unchanged(self):
        assert nfs_v3.vast_common.resolve_object_name({"path": "/data"}, ("path",)) == "/data"

    def test_falls_back_to_id(self):
        assert nfs_v3.vast_common.resolve_object_name({"id": 42}, ("path", "name")) == "42"

    def test_all_engines_label_root_view(self):
        for eng in (nfs_v3, nfs_v41, nvme_tcp, smb):
            assert eng._obj_name({"path": "/"}, ("path", "name")) == "/ (default)"
            assert eng._obj_name({"path": "/x"}, ("path", "name")) == "/x"


class TestDispatch:
    def test_dispatch_routes_to_nfs_v3(self):
        args = opstat.parse_args(["--nfs", "--version=3.0", *BASE_ARGS])
        with patch.object(opstat.nfs_v3, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)

    def test_dispatch_routes_to_nfs_v41(self):
        args = opstat.parse_args(["--nfs", "--version=4.1", *BASE_ARGS])
        with patch.object(opstat.nfs_v41, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)

    def test_dispatch_routes_to_nvme_tcp(self):
        args = opstat.parse_args(["--block", "--nvme-over-tcp", *BASE_ARGS])
        with patch.object(opstat.nvme_tcp, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)

    def test_dispatch_routes_to_smb(self):
        args = opstat.parse_args(["--smb", *BASE_ARGS])
        with patch.object(opstat.smb, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)


class TestSmbModule:
    def test_configure_client_scope_parses_csv(self):
        args = SimpleNamespace(clients="10.1.1.5, 10.1.1.6")
        smb.configure_client_scope(args)
        assert smb.CLIENT_SCOPED is True
        assert smb.CLIENT_IPS == ["10.1.1.5", "10.1.1.6"]

    def test_configure_client_scope_empty(self):
        args = SimpleNamespace(clients=None)
        smb.configure_client_scope(args)
        assert smb.CLIENT_SCOPED is False
        assert smb.CLIENT_IPS == []

    def test_maybe_fetch_aux_context_throttles_rest_probes(self, mocker):
        smb.REFRESH_SECONDS = 5
        smb._LAST_AUX_FETCH_AT = 0.0
        topn = mocker.patch.object(smb, "fetch_topn_data")
        session = mocker.patch.object(smb, "fetch_session_context")

        smb._maybe_fetch_aux_context()
        assert topn.call_count == 1
        assert session.call_count == 1

        topn.reset_mock()
        session.reset_mock()
        smb._maybe_fetch_aux_context()
        assert topn.call_count == 0
        assert session.call_count == 0

        smb._maybe_fetch_aux_context(force=True)
        assert topn.call_count == 1
        assert session.call_count == 1

    def test_write_csv_snapshot_appends_rows(self, tmp_path):
        csv_path = tmp_path / "smb.csv"
        smb.init_config(_connection_args(
            smb=True, nfs=False, protocol_version=None, csv=str(csv_path),
        ))
        smb.CLUSTER_ID = 1
        smb.CLUSTER_NAME = "lab"
        smb.HEADLINE_MONITOR_ID = 99
        smb.ensure_csv_file()
        snapshot = {
            "data": [{"label": "READ", "ops_sec": 10.0, "pct": 50.0, "avg_us": 100.0,
                      "bw_mbs": 5.0, "avg_io_bytes": 4096.0}],
            "metadata": [{"label": "METADATA", "ops_sec": 20.0, "pct": 100.0,
                          "avg_us": None, "bw_mbs": None, "avg_io_bytes": None}],
        }
        smb.write_csv_snapshot(snapshot, "2026-07-06T12:00:00Z")
        lines = csv_path.read_text().strip().splitlines()
        assert len(lines) == 3
        assert "READ" in lines[1]
        assert "METADATA" in lines[2]

    def test_build_opcode_workflow_rows_maps_read_write(self):
        data = [
            {"key": "read", "label": "READ", "ops_sec": 1000.0, "avg_us": 500.0,
             "bw_mbs": 10.0, "avg_io_bytes": 4096.0, "pct": 66.0},
            {"key": "write", "label": "WRITE", "ops_sec": 500.0, "avg_us": 800.0,
             "bw_mbs": 2.0, "avg_io_bytes": 2048.0, "pct": 33.0},
        ]
        meta = {"md_iops": 2000.0, "rd_md_iops": 1200.0, "wr_md_iops": 800.0,
                "notify_rate": None, "interop_lease_break_rate": None}
        rows = smb.build_opcode_workflow_rows(data, [], [], meta, None)
        labels = [r["label"] for r in rows]
        assert "SMB2_READ" in labels
        assert "SMB2_WRITE" in labels
        assert "METADATA (total)" in labels
        assert "SMB2_QUERY_INFO" not in labels
        assert "SMB2_SESSION_SETUP" not in labels
        read_row = next(r for r in rows if r["label"] == "SMB2_READ")
        assert read_row["source"] == "MEASURED"
        assert read_row["ops_sec"] == pytest.approx(1000.0)
        md_row = next(r for r in rows if r["label"] == "METADATA (total)")
        assert md_row["source"] == "AGGREGATE"
        assert md_row["ops_sec"] == pytest.approx(2000.0)
        assert md_row["_md_rd"] == pytest.approx(1200.0)
        assert md_row["_md_wr"] == pytest.approx(800.0)

    def test_build_opcode_workflow_rows_omits_zero_data_opcodes(self):
        data = [
            {"key": "write", "label": "WRITE", "ops_sec": 296.0, "avg_us": 448.0,
             "bw_mbs": 0.076, "avg_io_bytes": 256.0, "pct": 100.0},
        ]
        meta = {"md_iops": 3577.0, "rd_md_iops": 2327.0, "wr_md_iops": 1250.0}
        rows = smb.build_opcode_workflow_rows(data, [], [], meta, None)
        labels = [r["label"] for r in rows]
        assert labels == ["SMB2_WRITE", "METADATA (total)"]

    def test_opcode_has_data_filters_empty_rows(self):
        rows = [
            {"label": "SMB2_READ", "ops_sec": 0, "avg_us": 0, "bw_mbs": 0},
            {"label": "SMB2_WRITE", "ops_sec": 10.0, "avg_us": 0, "bw_mbs": 0},
        ]
        visible = smb._visible_opcode_rows(rows)
        assert len(visible) == 1
        assert visible[0]["label"] == "SMB2_WRITE"

    def test_split_opcode_rows_authoritative_vs_derived(self):
        rows = [
            {"label": "SMB2_READ", "source": "MEASURED", "ops_sec": 100.0},
            {"label": "SMB2_WRITE", "source": "MEASURED", "ops_sec": 50.0},
            {"label": "METADATA (total)", "source": "AGGREGATE", "ops_sec": 500.0},
            {"label": "SMB2_CHANGE_NOTIFY", "source": "PROXY", "ops_sec": 3.0},
            {"label": "SMB2_LOCK", "source": "HANDLES", "ops_sec": 2.0},
        ]
        auth, derived = smb._split_opcode_rows(rows)
        assert [r["label"] for r in auth] == [
            "SMB2_READ", "SMB2_WRITE", "METADATA (total)",
        ]
        assert [r["label"] for r in derived] == ["SMB2_CHANGE_NOTIFY", "SMB2_LOCK"]
        assert smb._opcode_tier("SMBMETRICS") == "authoritative"
        assert smb._opcode_tier("SESSIONS") == "derived"

    def test_infer_likely_active_opcodes_metadata_heavy(self):
        meta = {"md_iops": 800.0}
        data = [{"key": "read", "ops_sec": 100.0}, {"key": "write", "ops_sec": 50.0}]
        hints = smb.infer_likely_active_opcodes(meta, data)
        assert "SMB2_QUERY_DIRECTORY" in hints

    def test_smb_command_props_cover_candidates(self):
        props = smb.smb_command_props()
        assert "SmbMetrics,smb_read_latency__rate" in props
        assert "SmbMetrics,smb_oplock_break_latency__avg" in props
        assert len(props) == len(smb.SMB_CMD_CANDIDATES) * 2

    def test_phase0_metric_binding_constants(self):
        assert smb.METRICS_SOURCE == "SMBCommon"
        assert smb.SMB_PER_COMMAND_EXPORTED is False

    def test_drill_endpoints_are_not_api_prefixed(self):
        for mode, cfg in smb._DRILL_CFG.items():
            assert cfg["endpoint"].startswith("/")
            assert not cfg["endpoint"].startswith("/api/"), mode

    def test_build_headline_monitor_props_use_smbcommon(self):
        props = smb.build_headline_monitor_props()
        assert all(
            p.startswith("ProtoMetrics,proto_name=SMBCommon,") or p.startswith("NfsMetrics,")
            for p in props
        )
        assert smb._common_fqn("rd_iops") in props
        assert smb._common_fqn("md_iops") in props
        assert smb._common_fqn("write_latency__rate") in props
        assert smb._common_fqn("wr_latency") in props
        assert "NfsMetrics,nfs3_smb_interop_triggered_lease_breaks" in props

    def test_write_latency_fallback_uses_rate_when_avg_zero(self):
        ts = "2026-07-06T12:00:00Z"
        result = {
            "prop_list": [
                "timestamp",
                smb._common_fqn("rd_iops"), smb._common_fqn("wr_iops"),
                smb._common_fqn("md_iops"), smb._common_fqn("rd_md_iops"),
                smb._common_fqn("wr_md_iops"),
                smb._common_fqn("write_latency__avg"),
                smb._common_fqn("write_latency__rate"),
                smb._common_fqn("wr_latency"),
            ],
            "data": [[ts, 10.0, 20.0, 5.0, 2.0, 3.0, 0.0, 2500.0, 0.0]],
        }
        snapshot, _sample = smb.build_rows_from_results(result)
        write_row = next(r for r in snapshot["data"] if r["key"] == "write")
        assert write_row["avg_us"] == pytest.approx(2500.0)

    def test_interop_session_rows_from_multi_sample_monitor(self):
        result = {
            "prop_list": [
                "timestamp",
                "NfsMetrics,nfs3_smb_interop_triggered_lease_breaks",
            ],
            "data": [
                ["2026-07-06T12:00:10Z", 10.0],
                ["2026-07-06T12:00:00Z", 0.0],
            ],
        }
        rates = smb._interop_rates_from_result(result)
        assert rates["nfs3_smb_interop_triggered_lease_breaks"] == pytest.approx(1.0)

    def test_parse_topn_ip_and_client_scope_filter(self):
        assert smb._parse_topn_ip("172.200.14.253 [default]") == "172.200.14.253"
        smb.CLIENT_SCOPED = True
        smb.CLIENT_IPS = ["172.200.14.253"]
        assert smb._client_matches_scope("172.200.14.253 [default]") is True
        assert smb._client_matches_scope("10.0.0.1 [default]") is False
        smb.CLIENT_SCOPED = False
        smb.CLIENT_IPS = []

    def test_topn_dimension_rows_filters_scoped_clients(self):
        smb.LAST_TOPN = {
            "data": {
                "client": {
                    "md_iops": [
                        {"title": "172.200.14.253 [default]", "total": 100.0},
                        {"title": "10.0.0.1 [default]", "total": 50.0},
                    ],
                },
            },
        }
        smb.CLIENT_SCOPED = True
        smb.CLIENT_IPS = ["172.200.14.253"]
        rows = smb._topn_dimension_rows("client", "md_iops")
        assert len(rows) == 1
        assert rows[0]["total"] == pytest.approx(100.0)
        smb.CLIENT_SCOPED = False
        smb.CLIENT_IPS = []
        smb.LAST_TOPN = None

    def test_build_rows_from_smbcommon_sample(self):
        ts = "2026-07-06T12:00:00Z"
        result = {
            "prop_list": [
                "timestamp",
                smb._common_fqn("iops"),
                smb._common_fqn("rd_iops"),
                smb._common_fqn("wr_iops"),
                smb._common_fqn("md_iops"),
                smb._common_fqn("rd_md_iops"),
                smb._common_fqn("wr_md_iops"),
                smb._common_fqn("rd_bw"),
                smb._common_fqn("wr_bw"),
                smb._common_fqn("read_latency__avg"),
                smb._common_fqn("write_latency__avg"),
                smb._common_fqn("read_size__avg"),
                smb._common_fqn("write_size__avg"),
            ],
            "data": [[
                ts, 5000.0, 1000.0, 500.0, 3500.0, 2000.0, 1500.0,
                2_000_000_000.0, 500_000_000.0, 800.0, 1200.0, 65536.0, 4096.0,
            ]],
        }
        snapshot, sample = smb.build_rows_from_results(result)
        assert sample == ts
        assert smb.METRICS_SOURCE == "SMBCommon"
        read_row = next(r for r in snapshot["data"] if r["key"] == "read")
        assert read_row["ops_sec"] == pytest.approx(1000.0)
        assert read_row["bw_mbs"] == pytest.approx(2000.0)
        assert read_row["avg_us"] == pytest.approx(800.0)
        md_row = next(r for r in snapshot["metadata"] if r["key"] == "md_total")
        assert md_row["ops_sec"] == pytest.approx(3500.0)
        assert snapshot["meta"]["total_iops"] == pytest.approx(5000.0)

    def test_classify_smb_workload_metadata_heavy(self):
        meta = {"total_iops": 1000.0, "md_iops": 700.0}
        data = [
            {"key": "read", "ops_sec": 200.0, "avg_io_bytes": 4096.0},
            {"key": "write", "ops_sec": 100.0, "avg_io_bytes": None},
        ]
        result = smb.classify_smb_workload(meta, data)
        assert "metadata-heavy" in result

    def test_smb_health_label_idle(self):
        label, _color = smb.smb_health_label(0.0, None)
        assert label == "IDLE"

    def test_smb_health_label_healthy(self):
        label, _color = smb.smb_health_label(5000.0, 400.0)
        assert label == "HEALTHY"

    def test_smb_workload_mix_sums_to_100_when_md_exceeds_iops(self):
        """SMBCommon,iops is data-only; md_iops must not produce >100% metadata bar."""
        meta = {"total_iops": 1000.0, "md_iops": 1500.0}
        data = [
            {"key": "read", "ops_sec": 200.0},
            {"key": "write", "ops_sec": 100.0},
        ]
        md_pct, read_pct, write_pct = smb.smb_workload_mix(meta, data)
        assert md_pct == pytest.approx(1500 / 1800 * 100)
        assert read_pct + write_pct + md_pct == pytest.approx(100.0)
        assert md_pct < 100

    def test_slice_result_object_id_coercion(self):
        result = {
            "prop_list": ["timestamp", "object_id", "metric"],
            "data": [["t1", "42", 10.0], ["t2", 42, 20.0]],
        }
        sliced = smb._slice_result_for_object(result, 42)
        assert len(sliced["data"]) == 2

    def test_rank_drill_candidates_finds_active_view_beyond_first_chunk(self):
        smb.init_config(_connection_args(smb=True, nfs=False, protocol_version=None))
        smb.CLUSTER_ID = 1
        objects = [{"id": i, "path": f"/v{i}"} for i in range(1, 41)]
        cfg = smb._DRILL_CFG["view"]
        calls = []
        monitor_ids = iter(range(100, 200))

        def fake_query(mode, slice_result, name):
            ops = 500.0 if name == "/v40" else 0.0
            return {"name": name, "total_ops": ops, "latency_us": None, "bw_gbs": None,
                    "top_rpc": "-", "top_rpc_pct": None}

        def fake_api_request(method, path, payload=None):
            calls.append((method, path))
            if method == "POST" and path == "/monitors/":
                return {"id": next(monitor_ids)}
            if method == "GET" and path.endswith("/query/"):
                ids = payload if False else payload  # noqa — use POST payload from prior call
                return {"prop_list": ["timestamp", "object_id"], "data": []}
            if method == "DELETE":
                return None
            raise AssertionError(f"Unexpected: {method} {path}")

        with patch.object(smb, "api_request", side_effect=fake_api_request), \
             patch.object(smb, "_build_drill_row", side_effect=fake_query):
            ranked = smb._rank_drill_candidates("view", objects, cfg)

        assert ranked[0]["name"] == "/v40"
        assert len([c for c in calls if c[0] == "POST"]) == 2  # 40 views → 2 chunks

    def test_build_drill_prop_list_scopes(self):
        cnode_props = smb.build_drill_prop_list("cnode")
        view_props = smb.build_drill_prop_list("view")
        tenant_props = smb.build_drill_prop_list("tenant")
        assert smb._common_fqn("rd_iops") in cnode_props
        assert smb._VIEW_READ_IOPS in view_props
        assert smb._VIEW_READ_MD_LAT in view_props
        assert smb._VIEW_QOS_FAILURES in view_props
        assert smb._TENANT_READ_IOPS in tenant_props
        assert smb._TENANT_READ_MD_LAT_SUM in tenant_props

    def test_build_view_drill_row_from_rates(self):
        result = {
            "prop_list": [
                "timestamp",
                smb._VIEW_READ_IOPS,
                smb._VIEW_WRITE_IOPS,
                smb._VIEW_READ_MD,
                smb._VIEW_WRITE_MD,
                smb._VIEW_READ_LAT,
                smb._VIEW_WRITE_LAT,
                smb._VIEW_READ_BW,
                smb._VIEW_WRITE_BW,
            ],
            "data": [["2026-07-01T00:00:00Z", 100.0, 50.0, 30.0, 20.0, 500.0, 800.0, 1e9, 5e8]],
        }
        row = smb._build_view_drill_row(result, "/share")
        assert row["name"] == "/share"
        assert row["total_ops"] == pytest.approx(200.0)
        assert row["top_rpc"] == "READ"

    def test_build_view_drill_row_skips_null_padding_row(self):
        result = {
            "prop_list": [
                "timestamp",
                smb._VIEW_READ_IOPS,
                smb._VIEW_WRITE_IOPS,
                smb._VIEW_READ_MD,
                smb._VIEW_WRITE_MD,
            ],
            "data": [
                ["2026-07-06T20:11:36Z", None, None, None, None],
                ["2026-07-06T20:11:36Z", 122.52, 462.61, 345.48, 211.98],
            ],
        }
        row = smb._build_view_drill_row(result, "/kmacs/smb/opstat")
        assert row["total_ops"] == pytest.approx(1142.59)
        assert row["top_rpc"] == "WRITE"

    def test_view_drill_entry_uses_batch_rank_and_display_monitors(self):
        smb.init_config(_connection_args(smb=True, nfs=False, protocol_version=None))
        smb.CLUSTER_ID = 1
        views = [{"id": i, "path": f"/v{i}"} for i in range(1, 4)]
        calls = []
        monitor_seq = iter([900, 901])

        def fake_api_request(method, path, payload=None):
            calls.append((method, path))
            if method == "GET" and path == "/views/":
                return views
            if method == "POST" and path == "/monitors/":
                return {"id": next(monitor_seq)}
            if method == "GET" and path.endswith("/query/"):
                return {
                    "prop_list": [
                        "timestamp",
                        "object_id",
                        smb._VIEW_READ_IOPS,
                        smb._VIEW_WRITE_IOPS,
                        smb._VIEW_READ_MD,
                        smb._VIEW_WRITE_MD,
                    ],
                    "data": [
                        ["2026-07-01T00:00:00Z", vid, float(vid), 0.0, 0.0, 0.0]
                        for vid in (1, 2, 3)
                    ],
                }
            if method == "DELETE":
                return None
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(smb, "api_request", side_effect=fake_api_request):
            smb.enter_drill_mode("view")

        post_calls = [c for c in calls if c[0] == "POST"]
        get_query_calls = [c for c in calls if c[0] == "GET" and c[1].endswith("/query/")]
        assert len(post_calls) == 2
        assert len(get_query_calls) == 1
        assert len(smb.DRILL_MONITORS) == 1

    def test_fetch_drill_query_view_uses_single_batch_get(self):
        smb.init_config(_connection_args(smb=True, nfs=False, protocol_version=None))
        smb.DRILL_MODE = "view"
        smb.DRILL_OBJECTS = [{"id": 1, "name": "/a"}, {"id": 2, "name": "/b"}]
        smb.DRILL_MONITORS = [(55, None)]
        calls = []

        def fake_api_request(method, path, payload=None):
            calls.append((method, path))
            return {
                "prop_list": [
                    "timestamp", "object_id",
                    smb._VIEW_READ_IOPS, smb._VIEW_WRITE_IOPS,
                    smb._VIEW_READ_MD, smb._VIEW_WRITE_MD,
                    smb._VIEW_READ_LAT, smb._VIEW_WRITE_LAT,
                    smb._VIEW_READ_BW, smb._VIEW_WRITE_BW,
                ],
                "data": [
                    ["2026-07-01T00:00:00Z", 1, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    ["2026-07-01T00:00:00Z", 2, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                ],
            }

        with patch.object(smb, "api_request", side_effect=fake_api_request):
            smb.fetch_drill_query()

        assert calls == [("GET", "/monitors/55/query/")]
        assert len(smb.LAST_DRILL_ROWS) == 2

    def test_build_cnode_drill_row_from_smbcommon(self):
        ts = "2026-07-06T12:00:00Z"
        result = {
            "prop_list": [
                "timestamp",
                smb._common_fqn("iops"),
                smb._common_fqn("rd_iops"),
                smb._common_fqn("wr_iops"),
                smb._common_fqn("md_iops"),
                smb._common_fqn("rd_bw"),
                smb._common_fqn("wr_bw"),
                smb._common_fqn("read_latency__avg"),
                smb._common_fqn("write_latency__avg"),
            ],
            "data": [[ts, 300.0, 100.0, 50.0, 150.0, 1e9, 5e8, 400.0, 600.0]],
        }
        row = smb._build_cnode_drill_row(result, "cnode-1")
        assert row["total_ops"] == pytest.approx(300.0)
        assert row["top_rpc"] in ("READ", "METADATA")

    def test_discover_metrics_exits_on_cluster_failure(self):
        args = _connection_args(smb=True, nfs=False, protocol_version=None, discover_metrics=True)
        with patch.object(smb, "init_config"):
            smb.ARGS = args
            with patch.object(smb, "get_current_cluster", side_effect=RuntimeError("down")):
                with pytest.raises(SystemExit) as exc:
                    smb.discover_metrics()
                assert exc.value.code == 1


class TestNvmeTcpMetrics:
    def _connection_args(self, **overrides):
        values = {
            "vms": "203.0.113.10",
            "port": 443,
            "user": "admin",
            "password": "secret",
            "sample_average": None,
            "refresh": 5,
            "csv": None,
            "no_color": True,
            "discover_metrics": False,
            "log_api_calls": False,
            "nfs": False,
            "block": True,
            "smb": False,
            "nvme_over_tcp": True,
            "protocol_version": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_metric_names_for_op_read(self):
        names = nvme_tcp.metric_names_for_op("read")
        assert names["ops"] == "BlockMetrics,read_req"
        assert names["avg"] == "BlockMetrics,read_latency__avg"

    def test_build_ops_prop_list_includes_core_ops(self):
        props = nvme_tcp.build_ops_prop_list()
        assert "BlockMetrics,read_req" in props
        assert "BlockMetrics,unmap_req" in props
        assert "BlockMetrics,discovery_req" in props

    def test_build_proto_prop_list(self):
        assert nvme_tcp.build_proto_prop_list() == [
            nvme_tcp.BLOCK_READ_BW_FQN,
            nvme_tcp.BLOCK_WRITE_BW_FQN,
            nvme_tcp.BLOCK_READ_SIZE_FQN,
            nvme_tcp.BLOCK_WRITE_SIZE_FQN,
        ]

    def test_build_rows_from_results_single_sample(self):
        nvme_tcp.init_config(self._connection_args())
        nvme_tcp.PREV_COUNTER_STATE.clear()
        nvme_tcp.DELTA_READY = False

        def _op_result(ops_fqn, ops_val, avg_fqn, avg_val, ts="t1"):
            return {
                "prop_list": ["timestamp", ops_fqn, avg_fqn],
                "data": [[ts, ops_val, avg_val]],
            }

        ops_monitor_results = [
            _op_result("BlockMetrics,read_req", 1_000_000.0, "BlockMetrics,read_latency__avg", 250.0),
            _op_result("BlockMetrics,write_req", 500_000.0, "BlockMetrics,write_latency__avg", 800.0),
            _op_result("BlockMetrics,compare_and_write_req", 0.0, "BlockMetrics,compare_and_write_latency__avg", 0.0),
            _op_result("BlockMetrics,unmap_req", 0.0, "BlockMetrics,unmap_latency__avg", 0.0),
            _op_result("BlockMetrics,write_zeros_req", 0.0, "BlockMetrics,write_zeroes_latency__avg", 0.0),
            _op_result("BlockMetrics,discovery_req", 0.0, "BlockMetrics,discovery_latency__avg", 0.0),
            {
                "prop_list": [
                    "timestamp",
                    "BlockMetrics,handle_request_latency__rate",
                    "BlockMetrics,handle_request_latency__avg",
                    "BlockMetrics,transport_free_latency__rate",
                    "BlockMetrics,transport_free_latency__avg",
                    "BlockMetrics,get_ns_list_latency__rate",
                    "BlockMetrics,get_ns_list_latency__avg",
                ],
                "data": [["t1", 300.0, 100.0, 222.0, 50.0, 0.0, 0.0]],
            },
        ]
        proto_result = {
            "prop_list": [
                "timestamp",
                nvme_tcp.BLOCK_READ_BW_FQN,
                nvme_tcp.BLOCK_WRITE_BW_FQN,
                nvme_tcp.BLOCK_READ_SIZE_FQN,
                nvme_tcp.BLOCK_WRITE_SIZE_FQN,
            ],
            "data": [["t1", 100_000_000.0, 50_000_000.0, 4096.0, 8192.0]],
        }

        t0 = 1000.0
        rows, _ = nvme_tcp.build_rows_from_results(
            ops_monitor_results, proto_result, scope="cluster", poll_time=t0,
        )
        ops_monitor_results[0]["data"][0][1] = 1_000_500.0
        ops_monitor_results[1]["data"][0][1] = 500_250.0
        rows, sample = nvme_tcp.build_rows_from_results(
            ops_monitor_results, proto_result, scope="cluster", poll_time=t0 + 5.0,
        )
        by_key = {row["key"]: row for row in rows}

        assert nvme_tcp.DELTA_READY is True
        assert by_key["read"]["ops_sec"] == pytest.approx(100.0)
        assert by_key["read"]["avg_us"] == 250.0
        assert by_key["read"]["bw_mbs"] == pytest.approx(100.0)
        assert by_key["read"]["avg_io_bytes"] == pytest.approx(1_000_000.0)
        assert by_key["write"]["ops_sec"] == pytest.approx(50.0)
        assert by_key["handle_request"]["ops_sec"] == pytest.approx(300.0)
        assert nvme_tcp.compute_data_io_iops(rows) == pytest.approx(150.0)

    def test_rate_from_counter_delta(self):
        nvme_tcp.init_config(self._connection_args())
        nvme_tcp.PREV_COUNTER_STATE.clear()
        assert nvme_tcp.rate_from_counter_delta("cluster", "read", 10_000_000, 1000.0) is None
        rate = nvme_tcp.rate_from_counter_delta("cluster", "read", 10_000_500, 1005.0)
        assert rate == pytest.approx(100.0)

    def test_avg_io_size_from_throughput(self):
        assert nvme_tcp.avg_io_size_bytes(100.0, 100.0) == pytest.approx(1_000_000.0)

    def test_scoped_metric_fqn_volume_mode(self):
        nvme_tcp.VOLUME_SCOPED = True
        ops = {key: (o, a) for key, _l, _c, o, a in nvme_tcp.active_ops()}
        assert ops["read"][0] == "VolumeMetrics,read_latency__rate"
        assert ops["read"][1] == "VolumeMetrics,read_latency__avg"
        assert ops["discovery"][0] == "BlockMetrics,discovery_req"
        assert ops["unmap"][0] == "BlockMetrics,unmap_req"
        assert nvme_tcp.build_proto_prop_list() == [
            nvme_tcp.VOLUME_READ_SIZE_FQN,
            nvme_tcp.VOLUME_WRITE_SIZE_FQN,
        ]
        nvme_tcp.VOLUME_SCOPED = False

    def test_volume_monitor_groups_split_primary_and_supplement(self):
        nvme_tcp.VOLUME_SCOPED = True
        vol_groups = nvme_tcp.build_ops_monitor_groups(ops_rows=nvme_tcp.volume_primary_ops_rows())
        cluster_groups = nvme_tcp.build_ops_monitor_groups(
            ops_rows=nvme_tcp.cluster_supplement_ops_rows(),
        )
        assert len(vol_groups) == 2
        assert len(cluster_groups) == 5
        assert "VolumeMetrics,read_latency__rate" in vol_groups[0]
        assert "BlockMetrics,handle_request_latency__rate" in cluster_groups[-1]
        nvme_tcp.VOLUME_SCOPED = False

    def test_weighted_avg_ignores_none_weights(self):
        assert nvme_tcp._weighted_avg([(None, 100.0), (50.0, 200.0)]) == pytest.approx(200.0)
        assert nvme_tcp._weighted_avg([(None, 100.0), (None, 200.0)]) is None

    def test_compute_data_io_iops_excludes_fabric(self):
        rows = [
            {"key": "read", "ops_sec": 100.0},
            {"key": "write", "ops_sec": 50.0},
            {"key": "compare_and_write", "ops_sec": 10.0},
            {"key": "handle_request", "ops_sec": 300.0},
            {"key": "transport_free", "ops_sec": 222.0},
        ]
        assert nvme_tcp.compute_data_io_iops(rows) == pytest.approx(160.0)

    def test_format_block_size_scaling(self):
        assert nvme_tcp.format_block_size(4096.0)[0] == "4.00 KB"
        assert nvme_tcp.format_block_size(131072.0)[0] == "128.00 KB"
        assert nvme_tcp.format_block_size(1048576.0)[0] == "1.00 MB"
        assert nvme_tcp.format_block_size(None)[0] == "-"

    def test_block_health_label_healthy(self):
        label, _color = nvme_tcp.block_health_label(5000.0, 400.0, 600.0)
        assert label == "HEALTHY"

    def test_block_health_label_high_latency(self):
        label, _color = nvme_tcp.block_health_label(5000.0, 2500.0, 600.0)
        assert label == "HIGH LATENCY"
        label, _color = nvme_tcp.block_health_label(5000.0, 400.0, 6000.0)
        assert label == "HIGH LATENCY"

    def test_block_workload_mix(self):
        rows = [
            {"key": "read", "ops_sec": 350.0},
            {"key": "write", "ops_sec": 550.0},
            {"key": "unmap", "ops_sec": 50.0},
            {"key": "handle_request", "ops_sec": 50.0},
        ]
        read_pct, write_pct, reclaim_pct, fabric_pct = nvme_tcp.block_workload_mix(rows)
        assert read_pct == pytest.approx(35.0)
        assert write_pct == pytest.approx(55.0)
        assert reclaim_pct == pytest.approx(5.0)
        assert fabric_pct == pytest.approx(5.0)

    def test_classify_block_workload_read_heavy(self):
        rows = [
            {"key": "read", "ops_sec": 9000, "avg_io_bytes": 1_048_576},
            {"key": "write", "ops_sec": 100, "avg_io_bytes": None},
            {"key": "unmap", "ops_sec": 10, "avg_io_bytes": None},
        ]
        result = nvme_tcp.classify_block_workload(rows)
        assert "read-heavy" in result
        assert "large-block sequential" in result

    def test_classify_block_workload_fabric_dominant(self):
        rows = [
            {"key": "read", "ops_sec": 10},
            {"key": "write", "ops_sec": 10},
            {"key": "handle_request", "ops_sec": 500},
            {"key": "transport_free", "ops_sec": 500},
        ]
        assert "fabric-overhead dominant" in nvme_tcp.classify_block_workload(rows)

    def test_classify_block_workload_reclaim_heavy(self):
        rows = [
            {"key": "read", "ops_sec": 100},
            {"key": "write", "ops_sec": 100},
            {"key": "unmap", "ops_sec": 300},
            {"key": "write_zeros", "ops_sec": 100},
        ]
        assert "space-reclamation heavy" in nvme_tcp.classify_block_workload(rows)

    def test_compute_combined_data_io_size(self):
        rows = [
            {"key": "read", "ops_sec": 1000, "avg_io_bytes": 4096},
            {"key": "write", "ops_sec": 1000, "avg_io_bytes": 8192},
        ]
        assert nvme_tcp.compute_combined_data_io_size(rows) == pytest.approx(6144.0)

    def test_build_ops_monitor_groups_are_vms_compatible(self):
        nvme_tcp.VOLUME_SCOPED = False
        groups = nvme_tcp.build_ops_monitor_groups()
        assert len(groups) == 7
        flat = nvme_tcp.build_ops_prop_list()
        assert "BlockMetrics,read_req" in flat
        assert "BlockMetrics,handle_request_latency__rate" in flat
        assert sum(len(g) for g in groups) == len(flat)

    def test_merge_monitor_query_results(self):
        merged = nvme_tcp.merge_monitor_query_results([
            {
                "prop_list": ["timestamp", "BlockMetrics,read_req", "BlockMetrics,read_latency__avg"],
                "data": [["t1", 100.0, 250.0]],
            },
            {
                "prop_list": ["timestamp", "BlockMetrics,write_req", "BlockMetrics,write_latency__avg"],
                "data": [["t1", 50.0, 900.0]],
            },
        ])
        assert "BlockMetrics,read_req" in merged["prop_list"]
        assert "BlockMetrics,write_req" in merged["prop_list"]
        assert merged["data"][0][0] == "t1"

    def test_create_monitor_uses_opstat_prefix(self):
        nvme_tcp.init_config(self._connection_args())
        created = []

        def fake_api_request(method, path, payload=None):
            if method == "POST" and path == "/monitors/":
                created.append(payload["name"])
                return {"id": len(created)}
            raise AssertionError(f"Unexpected API call: {method} {path}")

        with patch.object(nvme_tcp, "api_request", side_effect=fake_api_request):
            nvme_tcp.CLUSTER_ID = 1
            ids = nvme_tcp.create_ops_monitors("nvme", "cluster", [1])

        assert len(ids) == 7
        assert all(name.startswith("adhoc_vast-opstat_nvme_ops_") for name in created)

    def test_format_latency_us_sub_millisecond(self):
        text, us = nvme_tcp.format_latency_us(250.0)
        assert us == 250.0
        assert text.endswith("µs") or text.endswith("us")

    def test_format_latency_us_millisecond(self):
        text, us = nvme_tcp.format_latency_us(2500.0)
        assert us == 2500.0
        assert text == "2.50 ms"

    def test_format_throughput_scaling(self):
        assert nvme_tcp.format_throughput_mbs(0.5)[0] == "512.00 KB/s"
        assert nvme_tcp.format_throughput_mbs(10.0)[0] == "10.00 MB/s"
        assert nvme_tcp.format_throughput_mbs(2048.0)[0] == "2.00 GB/s"

    def test_display_names_cover_table_order(self):
        for key in nvme_tcp.TABLE_ORDER:
            assert key in nvme_tcp.DISPLAY_NAMES

    def test_resolve_volume_names_requires_exact_match(self):
        nvme_tcp.init_config(self._connection_args())
        vols = [{"id": 1, "name": "db_archive_2024"}, {"id": 2, "name": "db_live"}]
        with patch.object(nvme_tcp, "api_request", return_value=vols):
            ids, resolved = nvme_tcp.resolve_volume_names(["db_live"])
            assert ids == [2] and resolved == ["db_live"]
            with pytest.raises(RuntimeError, match="exact name required"):
                nvme_tcp.resolve_volume_names(["db"])  # substring must not auto-bind

    def test_create_ops_monitors_rolls_back_on_failure(self):
        nvme_tcp.init_config(self._connection_args())
        nvme_tcp.CLUSTER_ID = 1
        nvme_tcp.vast_common.reset_registry()
        posted, deleted = [], []
        seq = iter(range(1, 99))

        def fake_api_request(method, path, payload=None):
            if method == "POST" and path == "/monitors/":
                posted.append(payload["name"])
                if len(posted) == 2:  # fail on the 2nd group
                    raise RuntimeError("POST /monitors/ failed: HTTP 400: property_error")
                return {"id": next(seq)}
            if method == "DELETE":
                deleted.append(path)
                return None
            raise AssertionError(f"Unexpected: {method} {path}")

        with patch.object(nvme_tcp, "api_request", side_effect=fake_api_request):
            with pytest.raises(RuntimeError):
                nvme_tcp.create_ops_monitors("nvme", "cluster", [1])

        assert len(deleted) == 1  # the first, already-created monitor is cleaned up
        assert not nvme_tcp.vast_common._CREATED_MONITORS  # nothing left registered


class TestVastCommon:
    def setup_method(self):
        smb.vast_common.reset_registry()

    def test_register_and_drain_monitors(self):
        vc = smb.vast_common
        vc.register_monitor(11)
        vc.register_monitor(22)
        deleted = []
        vc.drain_monitors(deleted.append)
        assert sorted(deleted) == [11, 22]
        assert not vc._CREATED_MONITORS  # drained

    def test_select_local_cluster_prefers_flag_over_first(self):
        vc = smb.vast_common
        clusters = [{"id": 1, "name": "remote"}, {"id": 2, "name": "home", "is_local": True}]
        assert vc.select_local_cluster(clusters)["id"] == 2
        assert vc.select_local_cluster([{"id": 9}])["id"] == 9  # fallback to first
        assert vc.select_local_cluster([]) is None

    def test_flush_frame_is_single_write_without_full_erase(self, capsys):
        smb.vast_common.flush_frame("hello")
        out = capsys.readouterr().out
        assert out == "\033[Hhello\033[K\033[J"
        assert "\033[2J" not in out  # no full-screen erase → no flicker

    def test_flush_frame_erases_each_line_to_eol(self, capsys):
        # Every line must be followed by \033[K so a shorter new line cannot
        # leave stale characters from the previous frame on the right.
        smb.vast_common.flush_frame("line1\nline2\nline3")
        out = capsys.readouterr().out
        assert out == "\033[Hline1\033[K\nline2\033[K\nline3\033[K\033[J"
        assert out.count("\033[K") == 3

    def test_shared_color_helper_respects_toggle(self):
        assert smb.set_color.__module__.endswith("tui_layout")  # from tui_layout
        smb.set_color(True)
        colored = smb.c("hi", smb._BCYAN)
        assert colored.startswith(smb._BCYAN) and colored.endswith("\033[0m")
        smb.set_color(False)
        assert smb.c("hi", smb._BCYAN) == "hi"
        # every engine shares one color-enable flag (single source of truth)
        assert nvme_tcp.c("x", nvme_tcp._BBLUE) == "x"

    def test_install_signal_handlers_covers_sighup(self):
        import signal as _signal
        captured = {}

        def fake_signal(sig, handler):
            captured[sig] = handler

        with patch("signal.signal", side_effect=fake_signal):
            smb.vast_common.install_signal_handlers(lambda *a: None)
        assert _signal.SIGINT in captured
        assert _signal.SIGTERM in captured
        assert _signal.SIGHUP in captured

    def test_all_engines_share_terminal_io(self):
        # Terminal I/O now lives once in vast_common; each engine aliases it.
        vc = smb.vast_common
        for eng in (nfs_v3, nfs_v41, nvme_tcp, smb):
            assert eng.setup_keyboard is vc.setup_keyboard
            assert eng.restore_terminal is vc.restore_terminal
            assert eng.check_keypress is vc.check_keypress
            assert eng.clear_screen is vc.clear_screen

    def test_check_keypress_inactive_returns_empty(self):
        vc = smb.vast_common
        vc.restore_terminal()  # ensure disabled state
        assert vc.keyboard_enabled() is False
        assert vc.check_keypress() == ""

    def test_clear_screen_emits_erase_and_home(self, capsys):
        smb.vast_common.clear_screen()
        assert capsys.readouterr().out == "\033[2J\033[H"

    def test_setup_keyboard_noop_off_tty(self, monkeypatch):
        vc = smb.vast_common
        monkeypatch.setattr(vc.sys.stdin, "isatty", lambda: False)
        assert vc.setup_keyboard() is False
        assert vc.keyboard_enabled() is False


class TestClusterOsHeader:
    def test_os_release_from_cluster_precedence(self):
        vc = smb.vast_common
        assert vc.os_release_from_cluster({"sw_version": "5.4.3-sp4"}) == "5.4.3-sp4"
        # falls through to the next key when the preferred one is absent
        assert vc.os_release_from_cluster({"os_version": "5.3.0"}) == "5.3.0"
        assert vc.os_release_from_cluster({"release": "5.2"}) == "5.2"
        assert vc.os_release_from_cluster({"name": "no-version-here"}) is None
        assert vc.os_release_from_cluster(None) is None

    def test_get_current_cluster_os_reads_local_cluster(self):
        vc = smb.vast_common

        def fake_request(method, path):
            assert method == "GET" and path == "/clusters/"
            return [
                {"id": 1, "name": "remote", "sw_version": "9.9.9"},
                {"id": 2, "name": "home", "is_local": True, "sw_version": "5.4.3-sp4"},
            ]

        assert vc.get_current_cluster_os(fake_request) == "5.4.3-sp4"

    def test_get_current_cluster_os_is_best_effort(self):
        vc = smb.vast_common

        def boom(*_a):
            raise RuntimeError("VMS unreachable")

        # Header adornment must never crash the tool.
        assert vc.get_current_cluster_os(boom) is None

    def test_all_engines_capture_cluster_os(self, monkeypatch):
        for eng in (nfs_v3, nfs_v41, nvme_tcp, smb):
            eng.CLUSTER_OS = None
            monkeypatch.setattr(
                eng.vast_common, "get_current_cluster_os", lambda _rf: "5.4.3-sp4"
            )
            eng._capture_cluster_os()
            assert eng.CLUSTER_OS == "5.4.3-sp4"
            assert eng.format_os_release(eng.CLUSTER_OS) == "vast-os-release-5.4.3-sp4"


class _WizardScript:
    """Scripted stdin/getpass driver for exercising the wizard headlessly."""

    def __init__(self, answers, secrets=None):
        self._answers = list(answers)
        self._secrets = list(secrets or [])
        self.out = []

    def input_fn(self, _prompt=""):
        assert self._answers, "wizard requested more input than scripted"
        return self._answers.pop(0)

    def getpass_fn(self, _prompt=""):
        assert self._secrets, "wizard requested more secrets than scripted"
        return self._secrets.pop(0)

    def output_fn(self, text=""):
        self.out.append(text)


def _run_wizard(answers, secrets=None, config_loader=lambda _p: None):
    w = opstat.wizard
    script = _WizardScript(answers, secrets)
    env = {}
    argv = w.run(
        input_fn=script.input_fn,
        output_fn=script.output_fn,
        getpass_fn=script.getpass_fn,
        environ=env,
        config_loader=config_loader,
    )
    return argv, env, script


class TestWizard:
    def test_should_launch_rules(self):
        w = opstat.wizard
        assert w.should_launch([], True, True) is True
        assert w.should_launch([], False, True) is False
        assert w.should_launch(["--nfs"], True, True) is False
        assert w.should_launch(["--menu"], True, True) is True
        assert w.should_launch(["--menu"], False, True) is False
        assert w.should_launch(["--no-menu"], True, True) is False

    def test_nfs_v3_happy_path_builds_argv_and_sets_password(self):
        # protocol=NFS, version=3.0, vms, default port, default user,
        # auth=password, no advanced, start.
        argv, env, _ = _run_wizard(
            ["1", "1", "10.0.0.5", "", "", "1", "", "1"], secrets=["s3cret"]
        )
        assert argv == ["--nfs", "--version=3.0", "--vms", "10.0.0.5"]
        assert env["VAST_PASSWORD"] == "s3cret"
        # produced argv must satisfy the real validator
        parsed = opstat.parse_args(argv)
        assert parsed.nfs is True and parsed.protocol_version == "3.0"

    def test_block_scope_emits_volume_flags(self):
        argv, env, _ = _run_wizard(
            ["2", "203.0.113.9", "", "", "1", "vol1,vol2", "", "1"], secrets=["pw"]
        )
        assert argv == [
            "--block", "--nvme-over-tcp", "--vms", "203.0.113.9",
            "--volumes", "vol1,vol2",
        ]
        assert opstat.parse_args(argv).block is True

    def test_smb_token_auth_sets_env_and_cluster_scope(self):
        # protocol=SMB, vms, default port/user, auth=token, no client scope, start.
        argv, env, _ = _run_wizard(
            ["3", "smb-vms", "", "", "2", "", "", "1"], secrets=["TOK-XYZ"]
        )
        assert argv == ["--smb", "--vms", "smb-vms"]
        assert env["VAST_TOKEN"] == "TOK-XYZ"
        assert "VAST_PASSWORD" not in env

    def test_advanced_options_and_nfs41(self):
        argv, _env, _ = _run_wizard(
            [
                "1", "2",           # NFS, v4.1
                "v", "8443", "svc",  # vms, port, user
                "1",                 # auth = password
                "y",                 # configure advanced
                "2", "10m", "/tmp/out.csv", "n", "y", "n",  # refresh, avg, csv, color=no, log=yes, openmetrics=no
                "1",                 # start
            ],
            secrets=["pw"],
        )
        assert argv == [
            "--nfs", "--version=4.1", "--vms", "v",
            "--vms-port", "8443", "--user", "svc",
            "--refresh", "2", "--sample-average", "10m",
            "--csv", "/tmp/out.csv", "--no-color", "--log-api-calls",
        ]
        assert opstat.parse_args(argv).protocol_version == "4.1"

    def test_advanced_options_enable_openmetrics(self):
        argv, _env, _ = _run_wizard(
            [
                "1", "2",            # NFS, v4.1
                "v", "8443", "svc",  # vms, port, user
                "1",                 # auth = password
                "y",                 # configure advanced
                "", "", "", "y", "n",  # refresh(def), avg(none), csv(none), color=yes, log=no
                "y", "/tmp/metrics.jsonl",  # openmetrics=yes, file
                "1",                 # start
            ],
            secrets=["pw"],
        )
        assert "--export-openmetrics" in argv
        assert argv[argv.index("--openmetrics-file") + 1] == "/tmp/metrics.jsonl"

    def test_quit_returns_none(self):
        argv, env, _ = _run_wizard(["q"])
        assert argv is None
        assert env == {}

    def test_nfs42_choice_is_rejected(self):
        # choosing planned 4.2 (index 3) re-prompts; then pick 4.1.
        argv, _env, _ = _run_wizard(
            ["1", "3", "2", "h", "", "", "1", "", "1"], secrets=["pw"]
        )
        assert "--version=4.1" in argv

    def test_config_shortcut_seeds_connection(self):
        cfg = {"vms": "cfg-host", "user": "cfguser", "password": "cfgpw"}
        # load config = yes, protocol NFS, version 3.0, advanced no, start.
        argv, env, _ = _run_wizard(
            ["", "1", "1", "", "1"], config_loader=lambda _p: cfg
        )
        assert argv == [
            "--nfs", "--version=3.0", "--vms", "cfg-host", "--user", "cfguser",
        ]
        assert env["VAST_PASSWORD"] == "cfgpw"

    def test_equivalent_cli_quotes_spaces(self):
        line = opstat.wizard._equivalent_cli(["--csv", "/tmp/a b/out.csv"])
        assert '"/tmp/a b/out.csv"' in line
        assert line.startswith("vast-opstat.py")


class TestAuditRegressions:
    def test_avg_from_sum_count_deltas_handles_null_rows(self):
        # Leading null padding row must not raise (was: None - float TypeError)
        result = {
            "prop_list": ["timestamp", "S", "C"],
            "data": [
                ["2026-07-06T20:11:36Z", None, None],
                ["2026-07-06T20:11:36Z", 1000.0, 10.0],
                ["2026-07-06T20:10:36Z", 500.0, 5.0],
            ],
        }
        # Not enough info to trust a null newest row → returns None, no crash.
        assert smb._avg_from_sum_count_deltas(result, "S", "C") is None
        clean = {
            "prop_list": ["timestamp", "S", "C"],
            "data": [
                ["2026-07-06T20:11:36Z", 1000.0, 10.0],
                ["2026-07-06T20:10:36Z", 500.0, 5.0],
            ],
        }
        assert smb._avg_from_sum_count_deltas(clean, "S", "C") == pytest.approx(100.0)
        assert nfs_v3._avg_from_sum_count_deltas(clean, "S", "C") == pytest.approx(100.0)

    def test_box_row_truncates_overwide_content(self):
        line = smb.box_row("X" * 200, 40)
        assert smb.display_width(line) <= 40

    def test_classify_smb_workload_metadata_only_not_idle(self):
        meta = {"md_iops": 500.0, "total_iops": 0.0}
        data = [{"key": "read", "ops_sec": 0.0}, {"key": "write", "ops_sec": 0.0}]
        label = smb.classify_smb_workload(meta, data)
        assert "Idle" not in label

    def test_configure_client_scope_rejects_malformed(self, capsys):
        smb.configure_client_scope(SimpleNamespace(clients="10.1.1.5, bad ip, host-01"))
        assert smb.CLIENT_IPS == ["10.1.1.5", "host-01"]
        assert "malformed" in capsys.readouterr().err

    def test_delete_monitor_records_real_failure_not_404(self):
        smb.vast_common.reset_registry()
        smb.vast_common.register_monitor(7)
        with patch.object(smb, "api_request", side_effect=RuntimeError("DELETE failed: HTTP 500: boom")):
            smb.delete_monitor(7)
        assert smb.vast_common.failed_deletes() == [(7, "DELETE failed: HTTP 500: boom")]
        assert 7 not in smb.vast_common._CREATED_MONITORS
        smb.vast_common.reset_registry()
        smb.vast_common.register_monitor(8)
        with patch.object(smb, "api_request", side_effect=RuntimeError("DELETE failed: HTTP 404: gone")):
            smb.delete_monitor(8)
        assert smb.vast_common.failed_deletes() == []  # 404 is expected, not a failure

    def test_nfs41_op_metrics_single_tier_no_mixing(self):
        # NFS4Common has iops but zero latency; must NOT borrow NfsMetrics latency.
        nfs4 = {f"{nfs_v41._NFS4},rd_iops": 100.0, f"{nfs_v41._NFS4},read_latency__avg": 0.0}
        supp = {"NfsMetrics,nfs_read_latency__rate": 50.0, "NfsMetrics,nfs_read_latency__avg": 999.0}
        row = nfs_v41._op_metrics(nfs4, supp, {}, "read")
        assert row["ops_sec"] == pytest.approx(100.0)   # NFS4Common tier chosen
        assert row["avg_us"] is None                     # latency not cross-borrowed


class TestOpenMetricsExporter:
    def _read_lines(self, path):
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_configure_disabled_returns_none(self):
        assert openmetrics.configure(False, None, "nfs3", "10.0.0.1") is None
        assert openmetrics.is_enabled() is False

    def test_default_filename_uses_protocol_and_vms(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        try:
            path = openmetrics.configure(True, None, "smb", "10.0.0.50")
            assert path is not None
            base = os.path.basename(path)
            assert base.startswith("vast-opstat-openmetrics-smb-10.0.0.50-")
            assert base.endswith(".jsonl")
        finally:
            openmetrics.close()

    def test_snapshot_emits_openmetrics_schema(self, tmp_path):
        out = tmp_path / "m.jsonl"
        openmetrics.configure(True, str(out), "nfs3", "10.0.0.50")
        try:
            series = [{
                "operation": "READ", "category": "data",
                "ops_sec": 100.0, "avg_us": 250.0,
                "bw_bytes_sec": 1.0e9, "io_bytes": 1.0e7,
            }]
            openmetrics.export_snapshot(
                "cl01", None, "cl01", series, sample="2026-07-08T14:30:00Z",
            )
        finally:
            openmetrics.close()
        lines = self._read_lines(out)
        assert len(lines) == 4  # ops, latency, throughput, io_size
        by_name = {r["metric_name"]: r for r in lines}
        ops = by_name["vast.nfs3.operations"]
        assert ops["value"] == 100.0
        assert ops["unit"] == "ops/s"
        assert ops["timestamp"] == "2026-07-08T14:30:00.000Z"
        assert ops["attributes"] == {
            "cluster": "cl01", "vms": "10.0.0.50", "protocol": "nfs3",
            "operation": "READ", "category": "data",
            "drill_mode": "cluster", "target_name": "cl01",
        }
        assert by_name["vast.nfs3.latency"]["unit"] == "microseconds"
        assert by_name["vast.nfs3.throughput"]["unit"] == "bytes/s"
        assert by_name["vast.nfs3.throughput"]["value"] == 1.0e9
        assert by_name["vast.nfs3.io_size"]["unit"] == "bytes"

    def test_null_values_are_skipped(self, tmp_path):
        out = tmp_path / "m.jsonl"
        openmetrics.configure(True, str(out), "smb", "vms")
        try:
            series = [{"operation": "CLOSE", "category": "session",
                       "ops_sec": 5.0, "avg_us": None,
                       "bw_bytes_sec": None, "io_bytes": None}]
            openmetrics.export_snapshot("c", None, "c", series)
        finally:
            openmetrics.close()
        lines = self._read_lines(out)
        assert [r["metric_name"] for r in lines] == ["vast.smb.operations"]

    def test_disabled_export_is_noop(self, tmp_path):
        out = tmp_path / "none.jsonl"
        openmetrics.configure(False, str(out), "nfs3", "vms")
        openmetrics.export_snapshot("c", None, "c", [{"operation": "READ",
                                                      "ops_sec": 1.0}])
        assert not out.exists()

    def test_drill_export_uses_target_and_total(self, tmp_path):
        out = tmp_path / "d.jsonl"
        openmetrics.configure(True, str(out), "nvme_tcp", "vms")
        try:
            rows = [{"name": "vol-1", "total_iops": 42.0,
                     "latency_us": 300.0, "bw_mbs": 2.0}]
            openmetrics.export_drill("c", "volume", rows, sample="bad-ts")
        finally:
            openmetrics.close()
        lines = self._read_lines(out)
        by_name = {r["metric_name"]: r for r in lines}
        ops = by_name["vast.nvme_tcp.operations"]
        assert ops["value"] == 42.0
        assert ops["attributes"]["drill_mode"] == "volume"
        assert ops["attributes"]["target_name"] == "vol-1"
        assert ops["attributes"]["category"] == "drill"
        # bw_mbs 2.0 MB/s -> 2_000_000 bytes/s
        assert by_name["vast.nvme_tcp.throughput"]["value"] == 2_000_000.0

    def test_all_engines_expose_export_helpers(self):
        for engine in (nfs_v3, nfs_v41, smb, nvme_tcp):
            assert hasattr(engine, "_openmetrics_series")
            assert hasattr(engine, "_export_openmetrics")
            assert engine.openmetrics is openmetrics

    def test_cli_flags_parse(self):
        args = opstat.parse_args(BASE_ARGS + ["--block", "--nvme-over-tcp",
                                              "--export-openmetrics",
                                              "--openmetrics-file", "/tmp/x.jsonl"])
        assert args.export_openmetrics is True
        assert args.openmetrics_file == "/tmp/x.jsonl"
