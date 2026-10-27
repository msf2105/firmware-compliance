#!/usr/bin/env python3
"""
mock_snow.py — play the CAB for mock ServiceNow change records.

Used with SNOW_MODE=mock (or -e snow_mode=mock) so the full open -> CAB
approve -> apply -> close flow can be rehearsed without a ServiceNow instance.
Records live in workflow/reports/mock_snow/<CHG>.json.

Usage:
    mock_snow.py list
    mock_snow.py show    CHG0123456
    mock_snow.py approve CHG0123456
    mock_snow.py reject  CHG0123456
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parent.parent / "reports" / "mock_snow"


def _load(number: str) -> dict:
    path = MOCK_DIR / f"{number}.json"
    if not path.exists():
        sys.exit(f"No mock change {number} in {MOCK_DIR}")
    return json.loads(path.read_text())


def _save(rec: dict) -> None:
    (MOCK_DIR / f"{rec['number']}.json").write_text(json.dumps(rec, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["list", "show", "approve", "reject"])
    p.add_argument("number", nargs="?")
    a = p.parse_args()

    if a.action == "list":
        for f in sorted(MOCK_DIR.glob("CHG*.json")):
            r = json.loads(f.read_text())
            print(f"{r['number']}  state={r['state']:<10} approval={r['approval']:<10} {r['short_description']}")
        return

    if not a.number:
        sys.exit("A change number is required for this action.")
    rec = _load(a.number)

    if a.action == "show":
        print(json.dumps(rec, indent=2))
        return

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    if a.action == "approve":
        rec.update(approval="approved", state="scheduled")
        rec["work_notes"].append(f"{stamp} CAB approved (mock).")
    else:
        rec.update(approval="rejected", state="canceled")
        rec["work_notes"].append(f"{stamp} CAB rejected (mock).")
    _save(rec)
    print(f"{rec['number']} -> approval={rec['approval']} state={rec['state']}")


if __name__ == "__main__":
    main()
