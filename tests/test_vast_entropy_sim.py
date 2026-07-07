################################################################################
# Script Name:    test_vast_entropy_sim.py
# Description:    Pure unit tests for vast-entropy-sim.py log generators — verifies
#                 both high- and low-compressibility lines are valid JSON with the
#                 expected schema, and that the low-comp payload carries genuinely
#                 higher-entropy fields. No filesystem writers/processes started.
#
# Author:         KMac kmac@vastdata.com
# Version:        1.0.0
################################################################################

import importlib.util
import json
import os
import sys

_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "vast", "vast-du", "vast-entropy-sim.py"
)
_spec = importlib.util.spec_from_file_location("vast_entropy_sim", _SCRIPT)
sim = importlib.util.module_from_spec(_spec)
sys.modules["vast_entropy_sim"] = sim
_spec.loader.exec_module(sim)


class TestHighCompLine:
    def test_valid_json_with_expected_keys(self):
        obj = json.loads(sim.generate_high_comp_line())
        assert set(obj) == {"timestamp", "level", "component", "message", "region"}

    def test_message_is_the_fixed_repetitive_string(self):
        obj = json.loads(sim.generate_high_comp_line())
        assert obj["message"] == (
            "Standard repetitive operational log message for routine maintenance."
        )

    def test_level_from_known_set(self):
        obj = json.loads(sim.generate_high_comp_line())
        assert obj["level"] in {"INFO", "DEBUG", "WARN"}


class TestLowCompLine:
    def test_valid_json_with_expected_keys(self):
        obj = json.loads(sim.generate_low_comp_line())
        assert set(obj) == {"timestamp", "session", "entropy", "metric"}

    def test_entropy_is_64_hex_chars(self):
        obj = json.loads(sim.generate_low_comp_line())
        assert len(obj["entropy"]) == 64
        int(obj["entropy"], 16)  # raises if not valid hex

    def test_sessions_are_unique(self):
        a = json.loads(sim.generate_low_comp_line())["session"]
        b = json.loads(sim.generate_low_comp_line())["session"]
        assert a != b
