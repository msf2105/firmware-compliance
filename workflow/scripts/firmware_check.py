#!/usr/bin/env python3
"""
firmware_check.py — determine whether each device is running the latest firmware.
===================================================================================
Reads golden_versions.yml (Ansible vars), queries each platform's version source
for the latest known release, compares the *running* version against both the
latest available AND the golden target, and produces a JSON report.

Can also be called from Ansible via `script:` or `command:` to set host facts.

Usage:
    firmware_check.py --platform ios --running "17.09.04" --golden "17.09.05"
    firmware_check.py --inventory-json '{"core-sw01":{"platform":"ios","running":"17.09.04"}}'
    firmware_check.py --yaml ~/eve-lab/firmware-compliance/vars/golden_versions.yml

Exit codes:
    0  — all checked devices are on the latest version
    2  — at least one device is behind (DRIFT)
    1  — tool error (bad args, missing file, etc.)

Michael Fields — Jul 2026
"""

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path

# Allow import of version_sources when script is run standalone
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

import yaml
from version_sources import VersionSourceFactory


def parse_golden_versions(path: str) -> dict:
    """Load the golden_versions.yml file."""
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    return data.get("golden_versions", {})


def evaluate_device(platform: str, running: str, golden: str, source=None) -> dict:
    """
    Compare running version against discovered latest and golden target.
    Returns a dict with all fields needed for reporting.
    """
    if source is None:
        source = VersionSourceFactory.create(platform, fallback_golden=golden)

    latest = None
    if source:
        try:
            latest = source.discover_latest()
        except Exception as e:
            latest = f"ERROR:{e}"

    # Use golden as effective "latest" if discovery isn't wired yet
    effective_latest = latest if latest and not str(latest).startswith("ERROR") else golden

    # Determine compliance: is running == latest?
    is_latest = False
    is_compliant = False
    comparison = "unknown"

    if source:
        try:
            cmp = source.version_compare(running, effective_latest)
            if cmp == 0:
                comparison = "equal"
                is_latest = True
            elif cmp < 0:
                comparison = "behind"
            else:
                comparison = "ahead"
            cmp_golden = source.version_compare(running, golden)
            is_compliant = (cmp_golden == 0)
        except Exception:
            # fallback to string compare
            is_latest = (running.strip() == effective_latest.strip())
            is_compliant = (running.strip() == golden.strip())
            comparison = "equal" if is_latest else "behind"
    else:
        is_latest = (running.strip() == effective_latest.strip())
        is_compliant = (running.strip() == golden.strip())
        comparison = "equal" if is_latest else "behind"

    return {
        "platform": platform,
        "running": running,
        "golden": golden,
        "latest_discovered": latest,
        "effective_latest": effective_latest,
        "is_latest": is_latest,
        "is_compliant": is_compliant,
        "comparison": comparison,
        "status": "OK" if is_latest else "DRIFT",
        "status_compliant": "OK" if is_compliant else "DRIFT",
    }


def print_report(results: list) -> int:
    """Print a human-readable table and return 0 if all OK, 2 if any DRIFT."""
    header = f"{'Host':<18} {'Platform':<8} {'Running':<16} {'Latest':<16} {'Status':<8} {'Golden Status':<6}"
    print(header)
    print("=" * len(header))
    any_drift = False
    for r in results:
        status = r["status"]
        golden_status = r["status_compliant"]
        if status == "DRIFT":
            any_drift = True
        line = f"{r.get('host','?'):<18} {r['platform']:<8} {r['running']:<16} {r['effective_latest']:<16} {status:<8} {golden_status:<6}"
        print(line)
    print("=" * len(header))
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"Summary: {ok}/{total} hosts on latest version.")
    return 2 if any_drift else 0


def main():
    parser = argparse.ArgumentParser(
        description="Compare device running firmware versions against latest/golden."
    )
    parser.add_argument(
        "--yaml", "-y",
        help="Path to golden_versions.yml (default: ../vars/golden_versions.yml relative to script)",
    )
    parser.add_argument(
        "--platform", "-p",
        help="Platform type (ios, nxos, asa, iosxr, panos, f5, ...)",
    )
    parser.add_argument(
        "--running", "-r",
        help="Running version on the device",
    )
    parser.add_argument(
        "--host", "-H", default="unspecified",
        help="Host name for report labeling",
    )
    parser.add_argument(
        "--inventory-json", "-i",
        help="JSON string mapping host names to {platform, running, product_id?, latest_version?} dicts",
    )
    parser.add_argument(
        "--product-id", "--pid",
        help="Cisco Product ID (PID) for the Software Suggestion API lookup",
    )
    parser.add_argument(
        "--latest-version",
        help="Pre-discovered latest version (e.g. from a device-local API query). "
             "Bypasses cloud API discovery — used for PA/F5 where the Ansible role "
             "queries the device directly.",
    )
    parser.add_argument(
        "--output", "-o", default="json",
        choices=["json", "table", "ansible_facts"],
        help="Output format",
    )
    args = parser.parse_args()

    # Resolve golden_versions.yml path
    golden_path = args.yaml
    if not golden_path:
        script_dir = Path(__file__).resolve().parent
        golden_path = str(script_dir.parent / "vars" / "golden_versions.yml")
    if not os.path.exists(golden_path):
        print(f"ERROR: golden_versions.yml not found: {golden_path}", file=sys.stderr)
        sys.exit(1)

    golden_versions = parse_golden_versions(golden_path)

    # Build the list of devices to evaluate
    devices = []
    if args.inventory_json:
        try:
            inv = json.loads(args.inventory_json)
            for host, info in inv.items():
                plat = info.get("platform", "")
                runv = info.get("running", "")
                if plat and runv:
                    dev = {"host": host, "platform": plat, "running": runv}
                    if info.get("product_id"):
                        dev["product_id"] = info["product_id"]
                    if info.get("latest_version"):
                        dev["latest_version"] = info["latest_version"]
                    devices.append(dev)
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.platform and args.running:
        devices.append({"host": args.host, "platform": args.platform, "running": args.running})
    else:
        print("ERROR: supply both --platform/--running or --inventory-json", file=sys.stderr)
        sys.exit(1)

    results = []
    for dev in devices:
        plat = dev["platform"]
        # Lookup the golden version for this platform
        gv = golden_versions.get(plat, {})
        if isinstance(gv, dict):
            golden = gv.get("version", "")
        else:
            golden = str(gv)

        # Determine product_id: CLI arg > inventory dict > golden_versions.yml
        product_id = dev.get("product_id") or args.product_id
        if not product_id and isinstance(gv, dict):
            product_id = gv.get("cisco_pid")

        # Determine latest_version override: CLI arg > inventory dict
        latest_override = dev.get("latest_version") or args.latest_version

        source = VersionSourceFactory.create(
            plat,
            fallback_golden=golden,
            product_id=product_id,
            latest_override=latest_override,
        )
        result = evaluate_device(plat, dev["running"], golden, source=source)
        result["host"] = dev["host"]
        if product_id:
            result["product_id"] = product_id
        if latest_override:
            result["latest_source"] = "device-local-api"
        elif product_id:
            result["latest_source"] = "cisco-support-api"
        else:
            result["latest_source"] = "golden-fallback"
        results.append(result)

    # Output
    if args.output == "json":
        print(json.dumps(results, indent=2))
        any_drift = any(r["status"] == "DRIFT" for r in results)
        sys.exit(2 if any_drift else 0)
    elif args.output == "table":
        rc = print_report(results)
        sys.exit(rc)
    elif args.output == "ansible_facts":
        # Emit Ansible set_fact compatible JSON
        facts = {}
        for r in results:
            h = r["host"]
            facts[f"firmware_check_{h}"] = r
        print(json.dumps(facts, indent=2))
        any_drift = any(r["status"] == "DRIFT" for r in results)
        sys.exit(2 if any_drift else 0)


if __name__ == "__main__":
    main()
