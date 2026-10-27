# cisco_sdwan.py — Cisco Catalyst SD-WAN (vManage / SD-WAN Manager) version source.
# ---------------------------------------------------------------------------
# Covers controllers (SD-WAN Manager, Validator, Controller: 20.x trains) and
# IOS-XE SD-WAN edges (17.x trains, e.g. 17.09.05a). Version strings follow the
# IOS-XE dotted format with an optional letter suffix, so the IOS comparator
# is reused. Latest-version discovery uses the Cisco Support API when a PID is
# supplied, otherwise the golden target.

from typing import Optional
from .cisco_ios import CiscoIOSVersionSource


class CiscoSDWANVersionSource(CiscoIOSVersionSource):
    platform = "sdwan"

    def __init__(self, fallback_golden: Optional[str] = None, product_id: Optional[str] = None):
        super().__init__(fallback_golden=fallback_golden, product_id=product_id)
