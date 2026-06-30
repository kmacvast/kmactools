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
_NVME_TCP_SCRIPT = os.path.join(_OPSTAT_DIR, "nvme_tcp.py")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


opstat = _load_module("vast_opstat", _OPSTAT_SCRIPT)
nfs_v3 = _load_module("vast_opstat_nfs_v3", _NFS_V3_SCRIPT)
nvme_tcp = _load_module("vast_opstat_nvme_tcp", _NVME_TCP_SCRIPT)

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
        "nfs": True,
        "block": False,
        "smb": False,
        "nvme_over_tcp": False,
        "protocol_version": "3.0",
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
            opstat.parse_args(["--nfs", "--version=4.1", *BASE_ARGS])
        assert "not implemented yet" in str(exc.value)

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

    def test_smb_not_implemented(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--smb", *BASE_ARGS])
        assert "SMB statistics are not implemented yet" in str(exc.value)

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


class TestDispatch:
    def test_dispatch_routes_to_nfs_v3(self):
        args = opstat.parse_args(["--nfs", "--version=3.0", *BASE_ARGS])
        with patch.object(opstat.nfs_v3, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)

    def test_dispatch_routes_to_nvme_tcp(self):
        args = opstat.parse_args(["--block", "--nvme-over-tcp", *BASE_ARGS])
        with patch.object(opstat.nvme_tcp, "run", return_value=0) as run_mock:
            assert opstat.dispatch(args) == 0
        run_mock.assert_called_once_with(args)


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
