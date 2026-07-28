"""Runtime compatibility helpers for vLLM/LMCache generations.

The compatibility layer keeps legacy CacheRoute deployments working while
allowing newer vLLM/LMCache stacks to use their current Redis key layout.
"""
from __future__ import annotations

import os
import re
from typing import Iterable, Optional

RUNTIME_PROFILE_AUTO = "auto"
RUNTIME_PROFILE_LEGACY = "legacy"
RUNTIME_PROFILE_V1 = "v1"
RUNTIME_PROFILE_TEST_MOCK = "test/mock"
SUPPORTED_RUNTIME_PROFILES = {
    RUNTIME_PROFILE_AUTO,
    RUNTIME_PROFILE_LEGACY,
    RUNTIME_PROFILE_V1,
    RUNTIME_PROFILE_TEST_MOCK,
}

_HEX_RE = re.compile(r"^[0-9a-fA-F]{32,}$")


def normalize_runtime_profile(value: Optional[str] = None) -> str:
    """Normalize a runtime profile, defaulting to the environment or ``auto``."""
    raw = value
    if raw is None:
        raw = os.getenv("CACHEROUTE_RUNTIME_PROFILE", RUNTIME_PROFILE_AUTO)
    profile = str(raw or RUNTIME_PROFILE_AUTO).strip().lower()
    aliases = {
        "old": RUNTIME_PROFILE_LEGACY,
        "v0": RUNTIME_PROFILE_LEGACY,
        "modern": RUNTIME_PROFILE_V1,
        "new": RUNTIME_PROFILE_V1,
        "current": RUNTIME_PROFILE_V1,
        "mock": RUNTIME_PROFILE_TEST_MOCK,
        "test": RUNTIME_PROFILE_TEST_MOCK,
        "test/mock": RUNTIME_PROFILE_TEST_MOCK,
    }
    profile = aliases.get(profile, profile)
    if profile not in SUPPORTED_RUNTIME_PROFILES:
        raise ValueError(
            f"unsupported CACHEROUTE_RUNTIME_PROFILE={profile!r}; "
            f"expected one of {sorted(SUPPORTED_RUNTIME_PROFILES)}"
        )
    return profile


def resolve_scan_match(profile: str, requested_match: Optional[str]) -> str:
    """Resolve the Redis SCAN pattern for a compatibility profile.

    ``vllm@*`` was the historic CacheRoute default. Unless strict ``legacy``
    mode is selected, it is treated as a compatibility sentinel rather than a
    forced pattern because older API/CLI callers may still send it implicitly.
    """
    profile = normalize_runtime_profile(profile)
    requested = str(requested_match or "").strip()

    if requested and requested.lower() != "auto":
        historic_default = requested == "vllm@*"
        if not (historic_default and profile != RUNTIME_PROFILE_LEGACY):
            return requested

    if profile == RUNTIME_PROFILE_LEGACY:
        return "vllm@*"
    return "*"


def classify_lmcache_redis_key(key: bytes) -> Optional[str]:
    """Classify supported LMCache Redis key layouts.

    Legacy CacheRoute used keys beginning with ``vllm@``. Newer LMCache
    deployments include the model identifier/path and one or more metadata
    fields before a long hexadecimal chunk hash, for example
    ``/models/llama@...@@<hash>``.
    """
    try:
        text = key.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if text.startswith("vllm@"):
        return "legacy"

    parts = text.split("@")
    if len(parts) < 4 or not parts[0]:
        return None

    # LMCache versions/connectors differ in the exact field count, but all
    # current layouts carry a long hexadecimal chunk hash after the model id.
    if any(_HEX_RE.fullmatch(part or "") for part in parts[1:]):
        return "v1"
    return None


def filter_supported_keys(
    keys: Iterable[bytes],
    profile: str,
    requested_match: Optional[str],
) -> set[bytes]:
    """Filter Redis keys when automatic discovery is active."""
    profile = normalize_runtime_profile(profile)
    scan_match = resolve_scan_match(profile, requested_match)
    key_set = set(keys)

    # An explicit non-auto pattern is authoritative; SCAN already filtered it.
    if scan_match != "*":
        return key_set

    allowed = {"legacy", "v1"}
    if profile == RUNTIME_PROFILE_LEGACY:
        allowed = {"legacy"}
    elif profile == RUNTIME_PROFILE_V1:
        allowed = {"v1"}

    return {
        key for key in key_set
        if classify_lmcache_redis_key(key) in allowed
    }
