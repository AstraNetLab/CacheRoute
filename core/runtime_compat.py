"""Compatibility re-export for the dependency-light runtime profile helpers."""
from runtime_compat import (
    RUNTIME_PROFILE_AUTO,
    RUNTIME_PROFILE_LEGACY,
    RUNTIME_PROFILE_TEST_MOCK,
    RUNTIME_PROFILE_V1,
    SUPPORTED_RUNTIME_PROFILES,
    classify_lmcache_redis_key,
    filter_supported_keys,
    normalize_runtime_profile,
    resolve_scan_match,
)

__all__ = [name for name in globals() if not name.startswith("_")]
