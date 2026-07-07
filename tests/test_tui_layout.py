"""Unit tests for vast-opstat terminal table layout helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vast", "vast-opstat"))

import nfs_v3
import nvme_tcp
import tui_layout


class TestDisplayWidth:
    def test_micro_sign_counts_as_one_column(self):
        assert tui_layout.display_width("42 µs") == tui_layout.display_width("42 us")

    def test_strips_ansi_before_measuring(self):
        colored = f"\033[32m{'hello':>10}\033[0m"
        assert tui_layout.display_width(colored) == 10

    def test_wide_characters_use_two_columns(self):
        assert tui_layout.display_width("日") == 2


class TestPadDisplay:
    def test_right_align_numeric_block(self):
        assert tui_layout.display_width(tui_layout.pad_display("512.00 KB/s", 14, ">")) == 14

    def test_truncates_long_labels(self):
        text = tui_layout.pad_display("FABRIC DISCOVERY EXTRA LONG NAME", 22, "<")
        assert tui_layout.display_width(text) == 22
        assert text.endswith("…")

    def test_unit_suffix_before_padding(self):
        cell = tui_layout.format_scaled_metric("2.50 ms", 14)
        assert tui_layout.display_width(cell) == 14
        assert cell.rstrip().endswith("ms")


class TestNfsTableAlignment:
    def test_header_and_row_share_column_widths(self):
        nfs_v3._COLOR = False
        widths = [
            nfs_v3._NFS_COL_PROC,
            nfs_v3._NFS_COL_OPS,
            nfs_v3._NFS_COL_PCT,
            nfs_v3._NFS_COL_LAT,
        ]
        header_cells = nfs_v3._table_header_cells(show_run=False, show_bw=False, show_io=False)
        data_cells = nfs_v3._rpc_row_cells({
            "label": "READDIRPLUS",
            "ops_sec": 1234.5,
            "pct": 12.3,
            "avg_us": 2500.0,
            "bw_gbs": None,
            "run_min_us": None,
            "run_max_us": None,
            "run_mean_us": None,
            "avg_io_bytes": None,
        }, show_run=False, show_bw=False, show_io=False)
        header = tui_layout.join_columns(header_cells, nfs_v3._NFS_COL_SEP)
        sep = tui_layout.display_width(nfs_v3._NFS_COL_SEP)
        expected = sum(widths) + sep * (len(widths) - 1)
        assert tui_layout.display_width(header) == expected
        for hp, dp, w in zip(header_cells, data_cells, widths):
            assert tui_layout.display_width(hp) == w
            assert tui_layout.display_width(dp) == w


class TestNvmeTableAlignment:
    def test_ops_header_and_row_share_column_widths(self):
        nvme_tcp._COLOR = False
        widths = [nvme_tcp._OPS_W[k] for k in _OPS_KEYS()]
        header = nvme_tcp._ops_table_header()
        data = nvme_tcp._table_row_cells({
            "key": "compare_and_write",
            "label": "CMP+WRITE",
            "ops_sec": 1234567.8,
            "bw_mbs": 512.0,
            "avg_us": 2500.0,
            "avg_io_bytes": 1048576,
        })
        sep = tui_layout.display_width(nvme_tcp._COL_SEP)
        expected = sum(widths) + sep * (len(widths) - 1)
        assert tui_layout.display_width(header) == expected
        assert tui_layout.display_width(data) == expected

        for key, w in zip(_OPS_KEYS(), widths):
            hp = tui_layout.pad_display(
                {"proc": "Operation", "iops": "IOPS", "throughput": "Throughput",
                 "size": "Avg Size", "latency": "Latency"}[key],
                w,
                "<" if key == "proc" else ">",
            )
            assert tui_layout.display_width(hp) == w

    def test_throughput_header_fits_column(self):
        nvme_tcp._COLOR = False
        cell = tui_layout.pad_display("Throughput", nvme_tcp._OPS_W["throughput"], ">")
        assert tui_layout.display_width(cell) == nvme_tcp._OPS_W["throughput"]


def _OPS_KEYS():
    return ("proc", "iops", "throughput", "size", "latency")


class TestSharedFormatters:
    def test_as_float_handles_none_and_junk(self):
        assert tui_layout.as_float(None) is None
        assert tui_layout.as_float("nope") is None
        assert tui_layout.as_float("3.5") == 3.5

    def test_raw_bw_conversions(self):
        assert tui_layout.raw_bw_to_mb_sec(2_000_000) == 2.0
        assert tui_layout.raw_bw_to_gb_sec(3_000_000_000) == 3.0
        assert tui_layout.raw_bw_to_mb_sec(None) is None

    def test_throughput_scales_across_units(self):
        assert tui_layout.format_throughput_mbs(2048)[0] == "2.00 GB/s"
        assert tui_layout.format_throughput_mbs(4)[0] == "4.00 MB/s"
        assert tui_layout.format_throughput_mbs(0.5)[0] == "512.00 KB/s"
        assert tui_layout.format_throughput_mbs(0)[0] == "-"

    def test_iops_precision_by_magnitude(self):
        assert tui_layout.format_iops(250000) == "250,000"
        assert tui_layout.format_iops(150.5) == "150.5"
        assert tui_layout.format_iops(5) == "5.00"
        assert tui_layout.format_iops(0) == "-"

    def test_block_size_scales(self):
        assert tui_layout.format_block_size(2 * 1024 ** 2)[0] == "2.00 MB"
        assert tui_layout.format_block_size(4096)[0] == "4.00 KB"
        assert tui_layout.format_block_size(512)[0] == "512 B"

    def test_latency_inactive_and_scaling(self):
        assert tui_layout.format_latency_us(1500, active=False)[0] == "-"
        assert tui_layout.format_latency_us(2000)[0] == "2.00 ms"

    def test_latency_glyph_follows_set_unicode(self):
        try:
            tui_layout.set_unicode(False)
            assert tui_layout.format_latency_us(250)[0] == "250 us"
            tui_layout.set_unicode(True)
            assert tui_layout.format_latency_us(250)[0] == "250 µs"
        finally:
            tui_layout.set_unicode(False)


class TestGlyphSet:
    def test_ascii_and_utf8_variants(self):
        ascii_g = tui_layout.glyph_set(False)
        utf_g = tui_layout.glyph_set(True)
        assert ascii_g["V"] == "|" and utf_g["V"] == "│"
        assert ascii_g["MUS"] == "us" and utf_g["MUS"] == "µs"

    def test_returns_independent_copies(self):
        g = tui_layout.glyph_set(True)
        g["V"] = "X"
        assert tui_layout.glyph_set(True)["V"] == "│"

    def test_engines_share_canonical_glyph_set(self):
        # All engines now source glyphs from tui_layout.glyph_set, so their
        # box/indicator characters must be identical.
        assert nfs_v3._V == nvme_tcp._V == tui_layout.glyph_set(nfs_v3._UTF8)["V"]
        assert nfs_v3._DOT == nvme_tcp._DOT
