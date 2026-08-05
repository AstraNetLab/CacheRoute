"""Service startup configuration for dependency-light observability helpers."""
from __future__ import annotations

from dataclasses import dataclass
import math

from cacheroute.runtime import RuntimeProfile
from .propagation import parse_sample_rate


@dataclass(frozen=True)
class ObservabilityStartupConfig:
    runtime_profile: RuntimeProfile
    trace_sample_rate: float
    sample_rate_warning_reason: str | None = None


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
        sample_rate_warning_reason=sample_rate_warning_reason(trace_sample_rate),
    )


def sample_rate_warning_reason(value: str | float | None) -> str | None:
    if value is None:
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "trace_sample_rate_malformed"
    if not math.isfinite(rate):
        return "trace_sample_rate_non_finite"
    if rate < 0.0:
        return "trace_sample_rate_below_zero"
    if rate > 1.0:
        return "trace_sample_rate_above_one"
    return None


__all__ = ["ObservabilityStartupConfig", "resolve_observability_startup", "sample_rate_warning_reason"]
