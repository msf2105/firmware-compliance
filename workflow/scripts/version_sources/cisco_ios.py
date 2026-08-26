# cisco_ios.py — Cisco IOS / IOS-XE version source.
# ---------------------------------------------------------------------------
# Uses the Cisco Support API Software Suggestion API to discover the latest
# recommended release for a given Product ID (PID). Falls back to the golden
# target if no API credentials are configured or the API is unavailable.
#
# Env vars: CISCO_CLIENT_ID, CISCO_CLIENT_SECRET (OAuth2 for Cisco Support API)
# Product ID: configured in golden_versions.yml under ios.cisco_pid

import re
from typing import Optional
from .base import VendorVersionSource
from .cisco_support_api import CiscoSupportAPIClient


class CiscoIOSVersionSource(VendorVersionSource):
    platform = "ios"

    def __init__(self, fallback_golden: Optional[str] = None, product_id: Optional[str] = None):
        self._latest: Optional[str] = None
        self._fallback = fallback_golden
        self._product_id = product_id
        self._api = CiscoSupportAPIClient()

    def discover_latest(self) -> Optional[str]:
        if self._latest is not None:
            return self._latest
        # Try the Cisco Support API if credentials are available
        if self._product_id and self._api.is_available():
            try:
                discovered = self._api.get_latest_version(self._product_id)
                if discovered and not discovered.startswith("ERROR"):
                    self._latest = discovered
                    return self._latest
            except Exception:
                pass  # fall through to golden fallback
        # Fall back to golden target
        self._latest = self._fallback
        return self._latest

    def version_compare(self, a: str, b: str) -> int:
        """IOS-XE uses dotted trains like 17.09.05 or 17.12.1.
        Treat trailing letters (e.g. 17.9.5a) as suffix — letter > no-letter."""
        a, b = self.normalize(a), self.normalize(b)
        # Extract main numeric sequence
        na = self._extract_numeric_parts(a)
        nb = self._extract_numeric_parts(b)
        for x, y in zip(na, nb):
            if x != y:
                return -1 if x < y else 1
        if len(na) != len(nb):
            return -1 if len(na) < len(nb) else 1
        # If numeric equal, compare trailing alpha suffix (e.g. 17.9.5a vs 17.9.5)
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