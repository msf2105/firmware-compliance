# cisco_support_api.py — shared Cisco Support API client for all Cisco platforms.
# ---------------------------------------------------------------------------
# The Cisco Support APIs (https://developer.cisco.com/docs/support-apis/) provide:
#   * Software Suggestion API — recommended software based on stability, longevity,
#     adoption rate. Returns suggested + available versions for a given product ID.
#   * Automated Software Distribution API — image info, download URLs, MD5 checksums
#   * PSIRT openVuln API — security advisories by software version
#
# Auth: OAuth2 client credentials grant.
#   Env vars: CISCO_CLIENT_ID, CISCO_CLIENT_SECRET
#   Token endpoint: https://id.cisco.com/oauth2/default/v1/token
#   API base: https://api.cisco.com
#
# The Software Suggestion API endpoint:
#   GET /software/suggestion/v2/suggests?product={PID}
# Returns a list of suggested releases. The first suggested release with
# classId="suggested" is the recommended version. If no suggestion, the
# latest available release is used.
#
# Product IDs (PID) are device-specific — e.g. "CSC" for Catalyst, "N5K"
# for Nexus 5000, etc. These are passed from golden_versions.yml.

import json
import os
import time
import urllib.parse
from typing import Optional, Dict, Any, List

from .base import HTTPClient, EnvCreds, FileCache


# Cisco OAuth2 token URL
_TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
# Cisco Support API base
_API_BASE = os.environ.get("CISCO_API_BASE", "https://apix.cisco.com")
# Token cache file (tokens last ~1 hour)
_TOKEN_CACHE_KEY = "cisco_oauth_token"


class CiscoSupportAPIClient:
    """Shared client for Cisco Support APIs with OAuth2 auth and caching."""

    def __init__(self):
        self._http = HTTPClient(timeout=30, max_retries=2)
        self._cache = FileCache(ttl=3600)  # 1 hour cache for version lookups
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    def _get_token(self) -> Optional[str]:
        """Obtain or return cached OAuth2 token."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        # Try cache first
        cached = self._cache.get(_TOKEN_CACHE_KEY)
        if cached and isinstance(cached, dict) and time.time() < cached.get("expiry", 0) - 60:
            self._token = cached["token"]
            self._token_expiry = cached["expiry"]
            return self._token

        client_id, client_secret = EnvCreds.get_cisco_oauth_creds()
        if not client_id or not client_secret:
            return None

        # OAuth2 client credentials grant
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("utf-8")

        status, parsed, body = self._http.post(
            _TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=data,
        )

        if status != 200 or not parsed:
            return None

        self._token = parsed.get("access_token")
        expires_in = parsed.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in

        # Cache the token
        self._cache.set(_TOKEN_CACHE_KEY, {
            "token": self._token,
            "expiry": self._token_expiry,
        })

        return self._token

    def _auth_headers(self) -> Dict[str, str]:
        token = self._get_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def get_suggested_software(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Query the Software Suggestion API for a given Cisco Product ID (PID).
        Returns the full API response dict, or None on error/no creds.
        """
        # Check cache
        cache_key = f"cisco_sw_suggest_{product_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        token = self._get_token()
        if not token:
            return None

        # v2 "suggested releases by PID (no images)" endpoint
        status, parsed, body = self._http.get(
            f"{_API_BASE}/software/suggestion/v2/suggestions/releases/productIds/"
            f"{urllib.parse.quote(product_id)}",
            headers=self._auth_headers(),
            params={"pageIndex": "1"},
        )

        if status != 200 or not parsed:
            return None

        # Cache the response
        self._cache.set(cache_key, parsed)
        return parsed

    def get_latest_version(self, product_id: str) -> Optional[str]:
        """
        Query the Software Suggestion API and extract the latest recommended version.
        Returns the version string, or None if the API is unavailable / no creds.

        The API returns a list of suggested releases. We pick the first one
        with classId="suggested" (Cisco's recommended release). If none is
        marked suggested, we fall back to the latest available release.
        """
        data = self.get_suggested_software(product_id)
        if not data:
            return None

        suggestions = []
        if isinstance(data, dict):
            # v2 shape: {"productList": [{"product": {...}, "suggestions": [...]}]}
            for prod in data.get("productList", []) or []:
                suggestions.extend(prod.get("suggestions", []) or [])
            if not suggestions:
                suggestions = data.get("suggestions", data.get("suggests", [])) or []
        elif isinstance(data, list):
            suggestions = data

        # v2 marks Cisco's pick with isSuggested == "Y"; version in releaseFormat1
        for s in suggestions:
            if isinstance(s, dict) and str(s.get("isSuggested", "")).upper() == "Y":
                v = s.get("releaseFormat1") or s.get("releaseFormat2") or s.get("release")
                if v:
                    return v

        if not suggestions:
            return None

        # Look for the Cisco-suggested release first
        for s in suggestions:
            if isinstance(s, dict):
                class_id = s.get("classId", "").lower()
                if class_id == "suggested":
                    return s.get("release", s.get("version"))

        # Fall back to the first available release (typically sorted newest-first)
        for s in suggestions:
            if isinstance(s, dict):
                version = s.get("releaseFormat1") or s.get("release") or s.get("version")
                if version:
                    return version

        return None

    def is_available(self) -> bool:
        """Check if Cisco Support API credentials are configured."""
        cid, csec = EnvCreds.get_cisco_oauth_creds()
        return bool(cid and csec)