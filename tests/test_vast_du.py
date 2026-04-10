################################################################################
# Script Name:    test_vast_du.py
# Description:    Unit tests for vast-du.py quota queries and DRR calculation.
#                 Uses pytest-mock to simulate VAST API responses.
#
# Author:         KMac kmac@vastdata.com
# Version:        0.4.2
################################################################################

import pytest
import sys
import os
import importlib.util

# Load module from file path (directory contains hyphens)
_script_path = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-du", "vast-du.py"
)
_spec = importlib.util.spec_from_file_location("vast_du", _script_path)
vast_du = importlib.util.module_from_spec(_spec)
sys.modules["vast_du"] = vast_du
_spec.loader.exec_module(vast_du)

calculate_drr = vast_du.calculate_drr
bytes_to_gib = vast_du.bytes_to_gib
fetch_quota_for_path = vast_du.fetch_quota_for_path
run_vast_du = vast_du.run_vast_du
format_capacity_table = vast_du.format_capacity_table


class TestCalculateDRR:
    """Test cases for DRR calculation logic."""

    def test_drr_basic_calculation(self):
        """Test standard DRR calculation."""
        logical = 10 * (1024**3)   # 10 GiB
        physical = 2 * (1024**3)   # 2 GiB
        
        drr = calculate_drr(logical, physical)
        
        assert drr == 5.0

    def test_drr_no_reduction(self):
        """Test DRR when logical equals physical (no reduction)."""
        logical = 5 * (1024**3)
        physical = 5 * (1024**3)
        
        drr = calculate_drr(logical, physical)
        
        assert drr == 1.0

    def test_drr_zero_physical(self):
        """Test DRR returns 1.0 when physical is zero (avoid division by zero)."""
        drr = calculate_drr(1000, 0)
        
        assert drr == 1.0

    def test_drr_high_reduction(self):
        """Test DRR with high data reduction (10:1)."""
        logical = 100 * (1024**3)  # 100 GiB
        physical = 10 * (1024**3)  # 10 GiB
        
        drr = calculate_drr(logical, physical)
        
        assert drr == 10.0

    def test_drr_fractional(self):
        """Test DRR with fractional result."""
        logical = 7 * (1024**3)
        physical = 3 * (1024**3)
        
        drr = calculate_drr(logical, physical)
        
        assert abs(drr - 2.333333) < 0.001


class TestBytesToGiB:
    """Test byte conversion utility."""

    def test_exact_gib(self):
        """Test conversion of exact GiB value."""
        assert bytes_to_gib(1024**3) == 1.0

    def test_multiple_gib(self):
        """Test conversion of multiple GiB."""
        assert bytes_to_gib(10 * (1024**3)) == 10.0

    def test_zero_bytes(self):
        """Test conversion of zero bytes."""
        assert bytes_to_gib(0) == 0.0


class TestFetchQuotaForPath:
    """Test quota fetching with mocked VASTClient."""

    def test_fetch_quota_exact_match(self, mocker):
        """Test fetching quota when path matches exactly."""
        mock_client = mocker.MagicMock()
        mock_client.quotas.get.return_value = [
            {"path": "/data/projects", "used_capacity": 1000, "used_effective_capacity": 5000},
            {"path": "/data/other", "used_capacity": 500, "used_effective_capacity": 2000},
        ]
        
        result = fetch_quota_for_path(mock_client, "/data/projects")
        
        assert result is not None
        assert result["path"] == "/data/projects"
        mock_client.quotas.get.assert_called_once_with(path="/data/projects")

    def test_fetch_quota_trailing_slash(self, mocker):
        """Test that trailing slashes are normalized."""
        mock_client = mocker.MagicMock()
        mock_client.quotas.get.return_value = [
            {"path": "/data/projects", "used_capacity": 1000},
        ]
        
        result = fetch_quota_for_path(mock_client, "/data/projects/")
        
        assert result is not None
        mock_client.quotas.get.assert_called_once_with(path="/data/projects")

    def test_fetch_quota_not_found(self, mocker):
        """Test when no quota exists for path."""
        mock_client = mocker.MagicMock()
        mock_client.quotas.get.return_value = []
        
        result = fetch_quota_for_path(mock_client, "/nonexistent")
        
        assert result is None


class TestRunVastDu:
    """Integration tests for the main run_vast_du function."""

    @pytest.fixture
    def mock_config(self):
        """Sample VAST configuration."""
        return {
            "vms": "vast.example.com",
            "token": "test-token",
            "tenant": None,
        }

    @pytest.fixture
    def mock_quota_response(self):
        """Sample quota API response with typical VAST fields."""
        return [
            {
                "path": "/data/ml-training",
                "used_capacity": 2 * (1024**3),          # 2 GiB physical
                "used_effective_capacity": 10 * (1024**3),  # 10 GiB logical
                "hard_limit": 100 * (1024**3),
                "soft_limit": 80 * (1024**3),
            }
        ]

    def test_run_vast_du_success(self, mocker, mock_config, mock_quota_response):
        """Test successful quota query and DRR calculation."""
        mock_client_class = mocker.patch.object(vast_du, "VASTClient")
        mock_client = mock_client_class.return_value
        mock_client.quotas.get.return_value = mock_quota_response
        
        result = run_vast_du("/data/ml-training", mock_config)
        
        assert "error" not in result
        assert result["path"] == "/data/ml-training"
        assert result["logical_gib"] == 10.0
        assert result["physical_gib"] == 2.0
        assert result["drr"] == 5.0

    def test_run_vast_du_path_not_found(self, mocker, mock_config):
        """Test error handling when path has no quota."""
        mock_client_class = mocker.patch.object(vast_du, "VASTClient")
        mock_client = mock_client_class.return_value
        mock_client.quotas.get.return_value = []
        
        result = run_vast_du("/nonexistent/path", mock_config)
        
        assert "error" in result
        assert "No quota found" in result["error"]

    def test_run_vast_du_high_drr(self, mocker, mock_config):
        """Test DRR calculation with high reduction ratio."""
        mock_client_class = mocker.patch.object(vast_du, "VASTClient")
        mock_client = mock_client_class.return_value
        mock_client.quotas.get.return_value = [
            {
                "path": "/compressed",
                "used_capacity": 1 * (1024**3),
                "used_effective_capacity": 20 * (1024**3),
            }
        ]
        
        result = run_vast_du("/compressed", mock_config)
        
        assert result["drr"] == 20.0


class TestFormatCapacityTable:
    """Test table output formatting."""

    def test_table_contains_metrics(self):
        """Test that formatted table contains all required metrics."""
        output = format_capacity_table("/test/path", 10.5, 2.1, 5.0)
        
        assert "/test/path" in output
        assert "10.50 GiB" in output
        assert "2.10 GiB" in output
        assert "5.00:1" in output
        assert "Logical Capacity" in output
        assert "Physical Capacity" in output
        assert "Data Reduction Ratio" in output
