"""Unit tests for the version comparison + compliance decision (pytest)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from firmware_check import evaluate_device  # noqa: E402
from version_sources import VersionSourceFactory  # noqa: E402


def _eval(platform, running, golden):
    src = VersionSourceFactory.create(platform, fallback_golden=golden)
    return evaluate_device(platform, running, golden, source=src)


def test_ios_zero_padding_is_equal():
    assert _eval("ios", "17.9.5", "17.09.05")["is_compliant"]


def test_ios_behind_needs_upgrade():
    r = _eval("ios", "17.06.04", "17.09.05")
    assert r["action_needed"] == "upgrade" and r["status_compliant"] == "DRIFT"


def test_ios_ahead_is_never_downgraded():
    r = _eval("ios", "17.12.01", "17.09.05")
    assert r["action_needed"] == "review" and r["status_compliant"] == "AHEAD"


def test_ios_letter_suffix_is_newer():
    assert _eval("ios", "17.09.04a", "17.09.04")["action_needed"] == "review"


def test_sdwan_edge_behind():
    assert _eval("sdwan", "17.09.04a", "17.12.04")["action_needed"] == "upgrade"


def test_panos_hotfix_ordering():
    assert _eval("panos", "11.1.4-h5", "11.1.4-h7")["action_needed"] == "upgrade"
    assert _eval("panos", "11.1.4-h7", "11.1.4-h7")["is_compliant"]


def test_f5_four_part_versions():
    assert _eval("f5", "16.1.4.1", "17.1.1.3")["action_needed"] == "upgrade"
    assert _eval("f5", "17.1.1.3", "17.1.1.3")["is_compliant"]


def test_catalyst_center_managed_device_suffix():
    assert _eval("dnac", "17.09.04a", "17.09.05")["action_needed"] == "upgrade"
