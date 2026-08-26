# cisco_iosxr.py — Cisco IOS-XR version source.
# ---------------------------------------------------------------------------
# Uses the Cisco Support API Software Suggestion API. Falls back to golden.
# Env vars: CISCO_CLIENT_ID, CISCO_CLIENT_SECRET
# Product ID: configured in golden_versions.yml under iosxr.cisco_pid

import re
from typing import Optional
from .base import VendorVersionSource
from .cisco_support_api import CiscoSupportAPIClient


class CiscoIOSXRVersionSource(VendorVersionSource):
    platform = "iosxr"

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