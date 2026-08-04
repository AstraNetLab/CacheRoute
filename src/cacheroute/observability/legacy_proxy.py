"""Pure allow-list projection of the current free-form Proxy trace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from cacheroute.runtime import RuntimeProfile
from .v1 import TraceComponent, TraceMeasurement, TraceProvenance, TraceStage, TraceStageName, TraceStageState, TraceValueKind

_TIMESTAMPS = {
    "proxy_enqueue_ms": TraceStageName.PROXY_PREPARE_QUEUE,
    "ready_enqueue_ms": TraceStageName.PROXY_READY_QUEUE,
    "forward_start_ms": TraceStageName.VLLM_PREFILL,
    "first_token_ms": TraceStageName.FIRST_TOKEN,
    "forward_end_ms": TraceStageName.COMPLETION,
    "kv_inject_start_ms": TraceStageName.LEGACY_INJECT,
    "kv_inject_end_ms": TraceStageName.LEGACY_INJECT,
}
_DURATIONS = {
    "actual_prepare_total_ms": TraceStageName.PROXY_PREPARE_QUEUE,
    "actual_ready_queue_ms": TraceStageName.PROXY_READY_QUEUE,
    "actual_vllm_internal_ms": TraceStageName.VLLM_PREFILL,
    "actual_total_ms": TraceStageName.COMPLETION,
    "predict_total_ms": TraceStageName.COMPLETION,
    "predict_know_prepare_ms": TraceStageName.PROXY_PREPARE_QUEUE,
    "predict_decode_ms": TraceStageName.DECODE,
}
_SCALARS = {"injection_mode": TraceStageName.RUNTIME_PROFILE_RESOLUTION, "kvcache_actual_path": TraceStageName.FALLBACK, "text_actual_path": TraceStageName.FALLBACK}


def project_legacy_proxy_trace(source: Mapping[str, Any], *, captured_at: datetime | None = None) -> tuple[TraceStage, ...]:
    """Project known safe scalars only; never retain or mutate ``source``."""
    stamp = captured_at or datetime.now(timezone.utc)
    provenance = TraceProvenance(source_component=TraceComponent.LEGACY_ADAPTER,
        runtime_profile=RuntimeProfile.LEGACY, captured_at=stamp, legacy_projected=True)
    grouped: dict[TraceStageName, list[TraceMeasurement]] = {}
    for key, stage in _TIMESTAMPS.items():
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            try: timestamp = datetime.fromtimestamp(value / 1000, timezone.utc)
            except (ValueError, OverflowError, OSError): continue
            grouped.setdefault(stage, []).append(TraceMeasurement(code=key, value_kind=TraceValueKind.LEGACY_PROJECTED, timestamp=timestamp))
    for key, stage in _DURATIONS.items():
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            grouped.setdefault(stage, []).append(TraceMeasurement(code=key, value_kind=TraceValueKind.LEGACY_PROJECTED, duration_ns=int(value * 1_000_000)))
    for key, stage in _SCALARS.items():
        value = source.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            try: measurement = TraceMeasurement(code=key, value_kind=TraceValueKind.LEGACY_PROJECTED, scalar=value)
            except ValueError: continue
            grouped.setdefault(stage, []).append(measurement)
    return tuple(TraceStage(stage_id=f"legacy_{index}", sequence=index, name=name,
        state=TraceStageState.SKIPPED, provenance=provenance,
        skip_reason="legacy_projection_has_no_lifecycle", measurements=tuple(values))
        for index, (name, values) in enumerate(grouped.items()))


__all__ = ["project_legacy_proxy_trace"]
