"""Tests for timefinder.py CLI dispatch."""
from __future__ import annotations

from unittest.mock import patch

from timefinder import timefinder


def test_cli_requires_single_action():
    assert timefinder.main([]) == 0


def test_cli_generate_candidates_dispatch():
    with patch("timefinder.timefinder.run_generate_candidates", return_value=0) as mock_run:
        assert timefinder.main(["--generate-candidates", "--dry-run"]) == 0
    mock_run.assert_called_once()


def test_cli_gather_dispatch():
    with patch("timefinder.timefinder.run_gather_messages", return_value=0) as mock_run:
        assert timefinder.main(["--gather-candidate-entries", "--slack"]) == 0
    mock_run.assert_called_once()
