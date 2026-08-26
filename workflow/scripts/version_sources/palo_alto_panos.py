# palo_alto_panos.py — Palo Alto PAN-OS version source.
# ---------------------------------------------------------------------------
# PAN-OS versions look like "11.1.4-h7" — hotfix suffix after dash.

import re
from typing import Optional
from .base import VendorVersionSource


class PaloAltoPANOSVersionSource(VendorVersionSource):
    platform = "panos"

    def __init__(self, fallback_golden: Optional[str] = None):
        self._latest: Optional[str] = None
        self._fallback = fallback_golden

    def discover_latest(self) -> Optional[str]:
        if self._latest is not None:
            return self._latest
        self._latest = self._fallback
        return self._latest

    def version_compare(self, a: str, b: str) -> int:
        a, b = self.normalize(a), self.normalize(b)
        # Split on dash: "11.1.4-h7" -> ([11,1,4], "h7")
        def parse(v: str):
            parts = v.split("-", 1)
            nums = self._extract_numeric_parts(parts[0])
            hotfix = parts[1] if len(parts) > 1 else ""
            return (nums, hotfix)
        pa, pb = parse(a), parse(b)
        # compare numeric tuples
        for x, y in zip(pa[0], pb[0]):
            if x != y:
                return -1 if x < y else 1
        if len(pa[0]) != len(pb[0]):
            return -1 if len(pa[0]) < len(pb[0]) else 1
        # compare hotfix suffixes (e.g. "" vs "h7", "h7" vs "h8")
        if pa[1] != pb[1]:
            # empty < non-empty; if both non-empty strip h and compare int
            ha, hb = pa[1], pb[1]
            if not ha and not hb:
                return 0
            if not ha:
                return -1
            if not hb:
                return 1
            # strip leading letter(s)
            na = int(re.sub(r"[^0-9]", "", ha))
            nb = int(re.sub(r"[^0-9]", "", hb))
            if na != nb:
                return -1 if na < nb else 1
        return 0

    def normalize(self, v: str) -> str:
        return self._cisco_style_normalize(v)
