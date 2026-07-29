"""Pure projection from the current free-form Proxy trace into safe v1 contracts."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from .enums import TraceComponent, TraceStageName, TraceStageOutcome, TraceStageState, TraceValueKind
from .models import RequestTrace, TraceContext, TraceMeasurement, TraceProvenance, TraceStage


_STAGE_KEYS: tuple[tuple[TraceStageName, tuple[str, ...]], ...] = (
    (TraceStageName.RUNTIME_PROFILE_RESOLUTION, ("proxy_recv_ms", "route_select_start_ms", "route_select_end_ms")),
    (TraceStageName.KNOWLEDGE_LOOKUP, ("kdn_fetch_start_ms", "kdn_fetch_end_ms")),
    (TraceStageName.PROXY_PREPARE_QUEUE, (
        "proxy_enqueue_ms", "prepare_queue_enqueue_ms", "prepare_dequeue_ms", "prepare_start_ms",
        "ready_enqueue_ms", "actual_prepare_ms", "actual_prepare_total_ms", "actual_know_prepare_ms",
        "prepare_buffer_wait_ms", "predict_prepare_ms", "predict_know_prepare_ms",
        "predict_prepare_queue_wait_ms", "predict_kv_transfer_ms", "predict_prepare_prefix_ms",
        "predict_kv_prepare_service_ms", "predict_prepare_initial_ms", "predict_prepare_model_ms",
        "predict_prepare_corrected_ms", "prepare_error_ms",
    )),
    (TraceStageName.INSTANCE_LMCACHE_LOAD, (
        "kv_inject_queue_enqueue_ms", "kv_inject_reserved_start_ms", "kv_inject_start_ms",
        "kv_inject_end_ms", "kv_ack_start_ms", "kv_ack_end_ms", "kdn_link_wait_start_ms",
        "kdn_link_wait_end_ms", "predict_redis_kv_load_ms",
    )),
    (TraceStageName.PROXY_READY_QUEUE, (
        "ready_dequeue_ms", "forward_wait_start_ms", "forward_wait_end_ms", "forward_start_ms",
        "actual_ready_queue_ms", "predict_queue_wait_ms",
    )),
    (TraceStageName.VLLM_PREFILL, (
        "predict_text_prefill_ms", "predict_residual_prefill_ms", "predict_prefill_service_ms",
        "predict_vllm_internal_ms", "actual_vllm_internal_ms", "actual_compute_ms",
    )),
    (TraceStageName.FIRST_TOKEN, ("pred_first_token_ts_ms", "first_token_ms", "ttft_observable")),
    (TraceStageName.DECODE, ("decode_start_ms", "decode_end_ms", "predict_decode_ms")),
    (TraceStageName.COMPLETION, ("forward_end_ms", "actual_total_ms", "predict_total_ms", "predict_error_ms")),
)

_TIMESTAMP_KEYS = {
    "proxy_recv_ms", "route_select_start_ms", "route_select_end_ms", "kdn_fetch_start_ms",
    "kdn_fetch_end_ms", "proxy_enqueue_ms", "prepare_queue_enqueue_ms", "prepare_dequeue_ms",
    "prepare_start_ms", "ready_enqueue_ms", "prepare_error_ms", "kv_inject_queue_enqueue_ms",
    "kv_inject_reserved_start_ms", "kv_inject_start_ms", "kv_inject_end_ms", "kv_ack_start_ms",
    "kv_ack_end_ms", "kdn_link_wait_start_ms", "kdn_link_wait_end_ms", "ready_dequeue_ms",
    "forward_wait_start_ms", "forward_wait_end_ms", "forward_start_ms", "pred_first_token_ts_ms",
    "first_token_ms", "decode_start_ms", "decode_end_ms", "forward_end_ms",
}
_OVERWRITTEN_PREDICTIONS = {"predict_prepare_ms", "predict_know_prepare_ms", "predict_prepare_corrected_ms"}
_CLEAR_ACTUAL_NAMES = {
    "actual_prepare_ms": "proxy_kv_ack_duration",
    "actual_prepare_total_ms": "proxy_prepare_total_duration",
    "actual_know_prepare_ms": "proxy_prepare_to_ready_duration",
    "actual_ready_queue_ms": "proxy_ready_queue_duration",
    "actual_total_ms": "proxy_enqueue_to_first_chunk_duration",
    "actual_vllm_internal_ms": "proxy_forward_to_first_chunk_duration",
    "prepare_buffer_wait_ms": "proxy_prepare_buffer_wait_duration",
}
_LEGACY_ALIAS_NAMES = {"actual_compute_ms": "proxy_forward_to_first_chunk_legacy_compute_alias"}
_KV_ACK_NUMERIC = {"payload_bytes", "network_queue_ms", "network_transfer_ms", "network_total_ms"}
_PATH_CODES = {
    "text_inject": (TraceStageOutcome.SUCCESS, "legacy_text_inject"),
    "no_rag_or_empty_knowledge": (TraceStageOutcome.SKIPPED, "legacy_no_rag_or_empty_knowledge"),
    "kv_inject": (TraceStageOutcome.SUCCESS, "legacy_kv_inject"),
    "kv_inject_failed_fallback_text": (TraceStageOutcome.TEXT_FALLBACK, "legacy_kv_inject_failed_text_fallback"),
    "no_kv_ready_fallback_text": (TraceStageOutcome.TEXT_FALLBACK, "legacy_no_kv_ready_text_fallback"),
}


def _hex_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _millis_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _measurement(key: str, value: Any, provenance: TraceProvenance) -> TraceMeasurement | None:
    if key in _TIMESTAMP_KEYS:
        timestamp = _millis_timestamp(value)
        if timestamp is None:
            return None
        kind = TraceValueKind.PREDICTED if key.startswith("pred_") else TraceValueKind.OBSERVED
        if key in {"first_token_ms", "decode_start_ms", "decode_end_ms", "kv_inject_reserved_start_ms", "kdn_link_wait_end_ms"}:
            kind = TraceValueKind.LEGACY_PROJECTED
        return TraceMeasurement(name=key.removesuffix("_ms") + "_timestamp", kind=kind,
                                provenance=provenance, timestamp=timestamp, legacy_name=key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not __import__("math").isfinite(value):
        return None
    if value < 0 and key != "predict_error_ms":
        return None
    if key in _CLEAR_ACTUAL_NAMES:
        return TraceMeasurement(name=_CLEAR_ACTUAL_NAMES[key], kind=TraceValueKind.ACTUAL,
                                provenance=provenance, duration_ns=int(value * 1_000_000), legacy_name=key)
    if key in _LEGACY_ALIAS_NAMES:
        return TraceMeasurement(name=_LEGACY_ALIAS_NAMES[key], kind=TraceValueKind.LEGACY_PROJECTED,
                                provenance=provenance, duration_ns=max(0, int(value * 1_000_000)), legacy_name=key)
    kind = TraceValueKind.PREDICTED if key.startswith("predict_") else TraceValueKind.LEGACY_PROJECTED
    if key in _OVERWRITTEN_PREDICTIONS:
        kind = TraceValueKind.LEGACY_PROJECTED
    if key == "ttft_observable":
        return TraceMeasurement(name=key, kind=TraceValueKind.OBSERVED, provenance=provenance,
                                boolean=bool(value), legacy_name=key)
    if key == "predict_error_ms":
        return TraceMeasurement(name="prediction_error_ms", kind=TraceValueKind.INFERRED,
                                provenance=provenance, safe_scalar=value, legacy_name=key)
    if key.endswith("_ms"):
        return TraceMeasurement(name=key.removesuffix("_ms") + "_duration", kind=kind,
                                provenance=provenance, duration_ns=int(value * 1_000_000), legacy_name=key)
    return None


def project_legacy_proxy_trace(
    *,
    request_id: str,
    correlation_id: str,
    legacy_request_id: int | None,
    trace: Mapping[str, Any],
    kv_ack: Mapping[str, Any] | None = None,
    exported_at: datetime,
    runtime_profile: str,
) -> RequestTrace:
    """Project allow-listed scalar fields; raw inputs never enter the result."""
    trace_id = _hex_id("trace", request_id, correlation_id, legacy_request_id)
    context = TraceContext(
        trace_id=trace_id, request_id=request_id, correlation_id=correlation_id,
        legacy_request_id=legacy_request_id, sampled=True, created_at=exported_at,
    )
    provenance = TraceProvenance(
        source_component=TraceComponent.LEGACY_ADAPTER, runtime_profile=runtime_profile,
        captured_at=exported_at, legacy=True,
    )
    stages: list[TraceStage] = []
    sequence = 0
    for stage_name, keys in _STAGE_KEYS:
        measurements = tuple(
            measurement for key in keys
            if key in trace
            for measurement in [_measurement(key, trace[key], provenance)]
            if measurement is not None
        )
        if not measurements:
            continue
        stages.append(TraceStage(
            stage_id=_hex_id("stage", trace_id, sequence, stage_name.value), sequence=sequence,
            name=stage_name, state=TraceStageState.COMPLETED, outcome=TraceStageOutcome.SUCCESS,
            provenance=provenance, measurements=measurements, started_at=exported_at,
            ended_at=exported_at, duration_ns=0,
        ))
        sequence += 1

    if kv_ack:
        measurements = []
        for key in sorted(_KV_ACK_NUMERIC):
            value = kv_ack.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                field = "bytes" if key == "payload_bytes" else "duration_ns"
                converted = int(value) if field == "bytes" else int(value * 1_000_000)
                measurements.append(TraceMeasurement(
                    name=f"legacy_kv_ack_{key}", kind=TraceValueKind.LEGACY_PROJECTED,
                    provenance=provenance, legacy_name=key, **{field: converted},
                ))
        if measurements:
            stages.append(TraceStage(
                stage_id=_hex_id("stage", trace_id, sequence, "kv_ack"), sequence=sequence,
                name=TraceStageName.INSTANCE_LMCACHE_LOAD, state=TraceStageState.COMPLETED,
                outcome=TraceStageOutcome.SUCCESS, provenance=provenance,
                measurements=tuple(measurements), started_at=exported_at, ended_at=exported_at,
                duration_ns=0, outcome_code="legacy_kv_ack",
            ))
            sequence += 1

    for path_key in ("text_actual_path", "kvcache_actual_path"):
        path_value = trace.get(path_key)
        classification = _PATH_CODES.get(path_value) if isinstance(path_value, str) else None
        if classification is None:
            continue
        outcome, code = classification
        stage_name = TraceStageName.FALLBACK if outcome is TraceStageOutcome.TEXT_FALLBACK else TraceStageName.PROXY_PREPARE_QUEUE
        stages.append(TraceStage(
            stage_id=_hex_id("stage", trace_id, sequence, path_key), sequence=sequence,
            name=stage_name, state=TraceStageState.COMPLETED, outcome=outcome,
            provenance=provenance, started_at=exported_at, ended_at=exported_at,
            duration_ns=0, outcome_code=code,
        ))
        sequence += 1

    components = (TraceComponent.LEGACY_ADAPTER,) if stages else ()
    return RequestTrace(context=context, stages=tuple(stages), exported_at=exported_at,
                        complete=True, source_components=components)


__all__ = ["project_legacy_proxy_trace"]
