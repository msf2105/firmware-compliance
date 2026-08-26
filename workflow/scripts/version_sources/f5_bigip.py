# f5_bigip.py — F5 BIG-IP version source.
# ---------------------------------------------------------------------------
# BIG-IP versions look like "17.1.1.3" or "16.1.4.1".

import re
from typing import Optional
from .base import VendorVersionSource


class F5BIGIPVersionSource(VendorVersionSource):
    platform = "f5"

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
        na = self._extract_numeric_parts(a)
        nb = self._extract_numeric_parts(b)
        for x, y in zip(na, nb):
            if x != y:
                return -1 if x < y else 1
        if len(na) != len(nb):
            return -1 if len(na) < len(nb) else 1
        sa = re.search(r"([a-zA-Z].*)", a)
        sb = re.search(r"([a-zA-Z].*)", b)
        if sa and not sb:
            return 1
        if sb and not sa:
            return -1
        if sa and sb:
            if sa.group(1).lower() != sb.group(1).lower():
                return 1 if sa.group(1).lower() > sb.group(1).lower() else -1
        return 0

    def normalize(self, v: str) -> str:
        return self._cisco_style_normalize(v)
