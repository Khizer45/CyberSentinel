"""IP-address pseudonymization (Security Requirements 5.1, Workflow Manual 9.2).

Raw IP addresses from uploaded flows are never stored. With ``IP_PSEUDONYMIZATION_KEY`` configured they are
replaced by a keyed HMAC-SHA256 token (stable, so repeated sources can be correlated, but not reversible without
the key). Without a key, IP context is dropped entirely.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress


def normalize_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, AttributeError):
        return None


def pseudonymize_ip(value: str, key: bytes | None) -> str | None:
    """Return ``ip_<16 hex>`` for a valid address, or ``None`` if invalid or no key is configured."""
    if not key:
        return None
    normalized = normalize_ip(value)
    if normalized is None:
        return None
    digest = hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()
    return f"ip_{digest[:16]}"
