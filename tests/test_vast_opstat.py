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


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


opstat = _load_module("vast_opstat", _OPSTAT_SCRIPT)
nfs_v3 = _load_module("vast_opstat_nfs_v3", _NFS_V3_SCRIPT)

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

    def test_block_nvme_over_tcp_not_implemented(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--block", "--nvme-over-tcp", *BASE_ARGS])
        assert "NVMe-oTCP statistics are not implemented yet" in str(exc.value)

    def test_smb_not_implemented(self):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--smb", *BASE_ARGS])
        assert "SMB statistics are not implemented yet" in str(exc.value)

    def test_tool_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            opstat.parse_args(["--nfs", "--version=3.0", *BASE_ARGS, "--tool-version"])
        assert exc.value.code == 0
        assert opstat.VERSION in capsys.readouterr().out


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
