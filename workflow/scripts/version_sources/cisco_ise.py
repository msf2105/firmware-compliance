"""Cisco ISE version source.
Uses the Cisco Support API Software Suggestion API. Falls back to golden.
Env vars: CISCO_CLIENT_ID, CISCO_CLIENT_SECRET
Product ID: configured in golden_versions.yml under ise.cisco_pid
"""
from typing import Optional
from .base import VendorVersionSource
from .cisco_support_api import CiscoSupportAPIClient


class CiscoISEVersionSource(VendorVersionSource):
    platform = "ise"

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
        return self._generic_numeric_compare(a, b)

    def normalize(self, v: str) -> str:
        return v.strip()