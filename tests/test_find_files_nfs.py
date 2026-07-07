################################################################################
# Script Name:    test_find_files_nfs.py
# Description:    Mocked/pure unit tests for find_files_nfs.py — duration and
#                 path formatting, CrawlStats aggregation properties, mount
#                 resolution, scan-root discovery, and CLI guard rails. No live
#                 NFS mount or subprocess find is executed.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import os
import sys

import pytest

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-catalog", "find_files_nfs.py"
)
_spec = importlib.util.spec_from_file_location("find_files_nfs", _SCRIPT)
ffn = importlib.util.module_from_spec(_spec)
sys.modules["find_files_nfs"] = ffn
_spec.loader.exec_module(ffn)


class TestFormatDuration:
    def test_sub_second_is_ms(self):
        assert ffn._format_duration(0.25) == "250 ms"

    def test_seconds(self):
        assert ffn._format_duration(3.5) == "3.50 seconds"

    def test_minutes(self):
        assert ffn._format_duration(90) == "1m 30.00s"

    def test_hours(self):
        assert ffn._format_duration(3661).startswith("1h 1m")


class TestShortPath:
    def test_strips_mount_prefix(self):
        assert ffn._short_path("/mnt/x/a/b.malware", "/mnt/x/") == "a/b.malware"

    def test_truncates_long_tail(self):
        long = "/mnt/x/" + "d/" * 40 + "f.malware"
        out = ffn._short_path(long, "/mnt/x/", max_len=20)
        assert out.startswith("…")
        assert len(out) == 20


class TestResolveMountPath:
    def test_appends_trailing_slash(self):
        assert ffn.resolve_mount_path({"mount_path": "/mnt/x"}) == "/mnt/x/"

    def test_keeps_existing_slash(self):
        assert ffn.resolve_mount_path({"mount_path": "/mnt/x/"}) == "/mnt/x/"

    def test_falls_back_to_default(self):
        assert ffn.resolve_mount_path({}) == ffn.DEFAULT_MOUNT_PATH


class TestCrawlStats:
    def _stats(self):
        jobs = [
            ffn.JobResult("/a", None, 1.0, 5),
            ffn.JobResult("/b", None, 3.0, 0),
            ffn.JobResult("/c", None, 2.0, 0, error="boom"),
        ]
        return ffn.CrawlStats(wall_seconds=4.0, total_matches=5, jobs=jobs)

    def test_ok_and_failed_counts(self):
        s = self._stats()
        assert s.jobs_ok == 2
        assert s.jobs_failed == 1

    def test_matches_per_sec(self):
        assert self._stats().matches_per_sec == pytest.approx(1.25)

    def test_matches_per_sec_zero_wall(self):
        s = ffn.CrawlStats(wall_seconds=0.0, total_matches=5, jobs=[])
        assert s.matches_per_sec == 0.0

    def test_slowest_and_fastest(self):
        s = self._stats()
        assert s.slowest_job.elapsed == 3.0
        assert s.fastest_job.elapsed == 1.0

    def test_jobs_with_hits(self):
        assert self._stats().jobs_with_hits == 1

    def test_avg_job_seconds_empty(self):
        assert ffn.CrawlStats(0.0, 0, jobs=[]).avg_job_seconds == 0.0


class TestDiscoverScanRoots:
    def test_no_dirs_returns_mount(self, tmp_path):
        jobs = ffn.discover_scan_roots(str(tmp_path) + "/", 8)
        assert jobs == [(str(tmp_path), None)]

    def test_enough_tlds_returns_one_job_each(self, tmp_path):
        for name in ("a", "b", "c"):
            (tmp_path / name).mkdir()
        jobs = ffn.discover_scan_roots(str(tmp_path) + "/", 2)
        assert len(jobs) == 3
        assert all(depth is None for _, depth in jobs)

    def test_few_tlds_expands_subdirs(self, tmp_path):
        tld = tmp_path / "only"
        tld.mkdir()
        (tld / "sub1").mkdir()
        (tld / "sub2").mkdir()
        jobs = ffn.discover_scan_roots(str(tmp_path) + "/", 8)
        # parent capped at maxdepth=1, plus each subdir as its own full job
        assert (str(tld), 1) in jobs
        assert (str(tld / "sub1"), None) in jobs


class TestBuildFindCmd:
    def test_includes_glob_and_type(self, monkeypatch):
        monkeypatch.setattr(ffn, "_gnu_find_o3_supported", lambda: False)
        cmd = ffn._build_find_cmd("/root")
        assert cmd == ["find", "/root", "-type", "f", "-name", ffn.TARGET_GLOB]

    def test_o3_prefix_when_gnu(self, monkeypatch):
        monkeypatch.setattr(ffn, "_gnu_find_o3_supported", lambda: True)
        cmd = ffn._build_find_cmd("/root", maxdepth=1)
        assert "-O3" in cmd
        assert cmd[-2:] == ["-maxdepth", "1"]


class TestMainGuards:
    def test_bad_thread_count(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["find_files_nfs.py", "--threads", "0"])
        assert ffn.main() == 1
        assert "must be >= 1" in capsys.readouterr().out
