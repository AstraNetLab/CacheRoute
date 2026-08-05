"""Service startup configuration for dependency-light observability helpers."""
from __future__ import annotations

from dataclasses import dataclass

from cacheroute.runtime import RuntimeProfile
from .propagation import parse_sample_rate


@dataclass(frozen=True)
class ObservabilityStartupConfig:
    runtime_profile: RuntimeProfile
    trace_sample_rate: float


def resolve_observability_startup(
    runtime_profile: RuntimeProfile | str | None = None,
    trace_sample_rate: str | float | None = None,
    *,
    v1_available: bool = False,
) -> ObservabilityStartupConfig:
    """Resolve startup-only observability metadata once for a service lifespan.

    Current Scheduler and Proxy service paths do not have a production v1 data
    path, so callers pass ``v1_available=False`` and ``auto`` resolves to
    ``legacy`` before any context can be persisted or propagated.
    """
    return ObservabilityStartupConfig(
        runtime_profile=RuntimeProfile.resolve_startup(runtime_profile if runtime_profile is not None else RuntimeProfile.LEGACY.value, v1_available=v1_available),
        trace_sample_rate=parse_sample_rate(trace_sample_rate),
    )


__all__ = ["ObservabilityStartupConfig", "resolve_observability_startup"]
