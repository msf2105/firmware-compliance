# version_sources/__init__.py — registry of all vendor-specific sources.

from typing import Dict, Optional
from .base import VendorVersionSource
from .cisco_ios import CiscoIOSVersionSource
from .cisco_iosxr import CiscoIOSXRVersionSource
from .cisco_nxos import CiscoNXOSVersionSource
from .cisco_asa import CiscoASAVersionSource
from .cisco_aci import CiscoACIVersionSource
from .cisco_dnac import CiscoDNACVersionSource
from .cisco_ise import CiscoISEVersionSource
from .cisco_ucs import CiscoUCSVersionSource
from .palo_alto_panos import PaloAltoPANOSVersionSource
from .f5_bigip import F5BIGIPVersionSource


# Map platform name -> (source class, golden_version_key in golden_versions.yml)
# Add new platforms here as you write sources.
_PLATFORM_REGISTRY: Dict[str, type] = {
    "ios": CiscoIOSVersionSource,
    "iosxr": CiscoIOSXRVersionSource,
    "nxos": CiscoNXOSVersionSource,
    "asa": CiscoASAVersionSource,
    "aci": CiscoACIVersionSource,
    "dnac": CiscoDNACVersionSource,
    "ise": CiscoISEVersionSource,
    "ucs": CiscoUCSVersionSource,
    "panos": PaloAltoPANOSVersionSource,
    "f5": F5BIGIPVersionSource,
}


class VersionSourceFactory:
    """Creates a VendorVersionSource for a given platform with an optional fallback."""

    @classmethod
    def create(
        cls,
        platform: str,
        fallback_golden: Optional[str] = None,
        product_id: Optional[str] = None,
        latest_override: Optional[str] = None,
    ) -> Optional[VendorVersionSource]:
        """
        Create a version source for a platform.

        Args:
            platform: Platform name (ios, nxos, panos, f5, etc.)
            fallback_golden: Golden version string to fall back to if API unavailable.
            product_id: Cisco Product ID (PID) for the Software Suggestion API.
            latest_override: Pre-discovered latest version (e.g. from a device-local
                API query by the Ansible role). When set, discover_latest() returns
                this instead of querying a cloud API.
        """
        klass = _PLATFORM_REGISTRY.get(platform)
        if not klass:
            return None

        # Cisco platforms accept product_id
        if product_id:
            return klass(fallback_golden=fallback_golden, product_id=product_id)

        # Non-Cisco / override case — pass latest_override via fallback
        if latest_override:
            source = klass(fallback_golden=fallback_golden)
            source._latest = latest_override  # type: ignore[attr-defined]
            return source

        return klass(fallback_golden=fallback_golden)

    @classmethod
    def supported_platforms(cls) -> list:
        return list(_PLATFORM_REGISTRY.keys())
