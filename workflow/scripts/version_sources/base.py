# base.py — abstract base class + shared utilities for vendor version lookups.
# ---------------------------------------------------------------------------
# Each vendor subclass implements discover_latest() and version_compare().
# The framework compares running vs discovered latest vs golden.
#
# Shared infrastructure in this module:
#   * HTTPClient  — urllib wrapper with timeout, retries, JSON parsing
#   * EnvCreds    — reads credentials from environment variables
#   * FileCache   — simple JSON file cache with TTL (avoids hammering vendor APIs)
#
# Credential convention (all read from env, never stored in repo):
#   Cisco Support API:  CISCO_CLIENT_ID / CISCO_CLIENT_SECRET  (OAuth2)
#   Palo Alto:          device API key (already managed by Ansible role)
#   F5:                 device creds (already managed by Ansible role)

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


class HTTPClient:
    """Minimal HTTP client wrapper around urllib with timeout, retries, JSON."""

    def __init__(self, timeout: int = 30, max_retries: int = 2, retry_delay: float = 2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]], str]:
        """
        Execute an HTTP request. Returns (status_code, parsed_json_or_None, raw_body).
        Retries on 5xx and connection errors.
        """
        if params:
            qs = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{qs}"

        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    status = resp.status
                    parsed = None
                    try:
                        parsed = json.loads(body)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    return status, parsed, body
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                if 500 <= e.code < 600 and attempt < self.max_retries:
                    last_error = f"HTTP {e.code}: {body[:200]}"
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                return e.code, None, body
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                return 0, None, last_error
        return 0, None, last_error

    def get(self, url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None):
        return self.request("GET", url, headers=headers, params=params)

    def post(self, url: str, headers: Optional[Dict] = None, data: Optional[bytes] = None):
        return self.request("POST", url, headers=headers, data=data)


class EnvCreds:
    """Read credentials from environment variables."""

    @staticmethod
    def get(key: str, required: bool = False) -> Optional[str]:
        val = os.environ.get(key)
        if not val and required:
            raise ValueError(f"Required env var {key} is not set")
        return val

    @staticmethod
    def get_cisco_oauth_creds() -> Tuple[Optional[str], Optional[str]]:
        """Cisco Support API uses OAuth2 client credentials."""
        return EnvCreds.get("CISCO_CLIENT_ID"), EnvCreds.get("CISCO_CLIENT_SECRET")


class FileCache:
    """Simple JSON file cache with TTL. Stores one entry per key."""

    def __init__(self, cache_dir: str = os.path.expanduser("~/.cache/firmware-compliance"), ttl: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Any]:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                entry = json.load(f)
            if time.time() - entry.get("ts", 0) > self.ttl:
                return None
            return entry.get("data")
        except (json.JSONDecodeError, IOError):
            return None

    def set(self, key: str, data: Any) -> None:
        path = self.cache_dir / f"{key}.json"
        try:
            with open(path, "w") as f:
                json.dump({"ts": time.time(), "data": data}, f)
        except IOError:
            pass


class VendorVersionSource(ABC):
    """One per supported vendor. Implement discover_latest() and version_compare()."""

    platform: str = ""  # e.g. "ios", "nxos", "panos", "f5"

    def __init__(self, fallback_golden: Optional[str] = None):
        self._latest: Optional[str] = None
        self._fallback = fallback_golden
        self._http = HTTPClient()
        self._cache = FileCache()

    @abstractmethod
    def discover_latest(self) -> Optional[str]:
        """Fetch (or return cached) latest recommended release string. None = unknown."""
        ...

    @abstractmethod
    def version_compare(self, a: str, b: str) -> int:
        """Return -1/0/+1 if a < b / a == b / a > b.  Handles vendor formatting."""
        ...

    @abstractmethod
    def normalize(self, v: str) -> str:
        """Canonicalise for display; e.g. strip build noise, fix spacing."""
        ...

    # ------------------------------------------------------------------
    # Helpers shared across most Cisco-like vendors
    # ------------------------------------------------------------------

    def _extract_numeric_parts(self, v: str) -> Tuple[int, ...]:
        """Pull out all contiguous digits as an ordered tuple of ints."""
        parts = re.findall(r"\d+", v)
        return tuple(int(p) for p in parts)

    def _cisco_style_compare(self, a: str, b: str) -> int:
        """Compare version strings by numeric segments left-to-right."""
        pa = self._extract_numeric_parts(a)
        pb = self._extract_numeric_parts(b)
        for x, y in zip(pa, pb):
            if x != y:
                return -1 if x < y else 1
        # e.g. "10.3(5)" vs "10.3(5a)" — more segments = newer
        if len(pa) != len(pb):
            return -1 if len(pa) < len(pb) else 1
        return 0

    def _cisco_style_normalize(self, v: str) -> str:
        """Trim whitespace, collapse internal spaces."""
        v = v.strip()
        v = re.sub(r"\s+", " ", v)
        return v

    def _generic_numeric_compare(self, a: str, b: str) -> int:
        pa = self._extract_numeric_parts(a)
        pb = self._extract_numeric_parts(b)
        for x, y in zip(pa, pb):
            if x != y:
                return -1 if x < y else 1
        if len(pa) != len(pb):
            return -1 if len(pa) < len(pb) else 1
        return 0