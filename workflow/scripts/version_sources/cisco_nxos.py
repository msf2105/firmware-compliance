# cisco_nxos.py — Cisco NX-OS version source.
# ---------------------------------------------------------------------------
# Uses the Cisco Support API Software Suggestion API. Falls back to golden.
# Env vars: CISCO_CLIENT_ID, CISCO_CLIENT_SECRET
# Product ID: configured in golden_versions.yml under nxos.cisco_pid

import re
from typing import Optional
from .base import VendorVersionSource
from .cisco_support_api import CiscoSupportAPIClient


class CiscoNXOSVersionSource(VendorVersionSource):
    platform = "nxos"

    def __init__(self, fallback_golden: Optional[str] = None, product_id: Optional[str] = None):
        self._latest: Optional[str] = None
        self._fallback = fallback_golden
        self._product_id = product_id
        self._api = CiscoSupportAPIClient()

    def discover_latest(self) -> Optional[str]:
        if self._latest is not None:
            return self._latest
        if self._product_id and self._api.is_available():
            try:
                discovered = self._api.get_latest_version(self._product_id)
                if discovered and not discovered.startswith("ERROR"):
                    self._latest = discovered
                    return self._latest
            except Exception:
                pass
        self._latest = self._fallback
        return self._latest

    def version_compare(self, a: str, b: str) -> int:
        a, b = self.normalize(a), self.normalize(b)
        # Parse: major.minor(sub)
        # e.g. "10.3(5a)" -> (10, 3, 5, 'a')
        def parse(v: str):
            m = re.match(r"(\d+)\.(\d+)\((\d+)([a-zA-Z]?)\)", v)
            if m:
                major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
                suffix = m.group(4).lower() or ""
                return (major, minor, patch, suffix)
            # fallback to generic dotted
            return self._extract_numeric_parts(v)

        pa = parse(a)
        pb = parse(b)
        for x, y in zip(pa, pb):
            sx, sy = str(x), str(y)
            if sx != sy:
                return -1 if sx < sy else 1
        if len(pa) != len(pb):
            return -1 if len(pa) < len(pb) else 1
        return 0

    def normalize(self, v: str) -> str:
        return self._cisco_style_normalize(v)