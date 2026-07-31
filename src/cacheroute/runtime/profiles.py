"""Canonical runtime profile selection."""
from __future__ import annotations

from enum import Enum

from cacheroute.compat.runtime import normalize_runtime_profile


class RuntimeProfile(str, Enum):
    V1 = "v1"
    LEGACY = "legacy"
    TEST_MOCK = "test/mock"
    AUTO = "auto"  # accepted only by resolve_startup

    @classmethod
    def normalize(cls, value: "RuntimeProfile | str") -> "RuntimeProfile":
        return cls(normalize_runtime_profile(value.value if isinstance(value, cls) else value))

    @classmethod
    def resolve_startup(
        cls,
        value: "RuntimeProfile | str | None" = None,
        *,
        v1_available: bool = True,
    ) -> "RuntimeProfile":
        normalized = cls(normalize_runtime_profile(value))
        if normalized is cls.AUTO:
            return cls.V1 if v1_available else cls.LEGACY
        return normalized

    resolve_auto = resolve_startup


__all__ = ["RuntimeProfile"]
