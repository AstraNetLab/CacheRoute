from cacheroute_observability import TraceStageName, TraceValueKind, project_legacy_proxy_trace


def _measurements(result):
    return {m.legacy_name: m for stage in result.stages for m in stage.measurements}


def test_legacy_classification_omission_and_sanitization(now):
    result = project_legacy_proxy_trace(
        request_id="req", correlation_id="corr", legacy_request_id=9,
        trace={
            "predict_total_ms": 10,
            "predict_prepare_ms": 11,
            "predict_know_prepare_ms": 12,
            "actual_vllm_internal_ms": 13,
            "actual_compute_ms": 14,
            "first_token_ms": 1760000000000,
            "decode_start_ms": 1760000000001,
            "decode_end_ms": 1760000000002,
            "kvcache_actual_path": "kv_inject_failed_fallback_text",
            "error": "Traceback secret raw exception",
            "unknown_key": {"anything": "must not copy"},
        },
        kv_ack={"payload_bytes": 42, "password": "must not copy"},
        exported_at=now, runtime_profile="legacy",
    )
    measurements = _measurements(result)
    assert measurements["predict_total_ms"].kind is TraceValueKind.PREDICTED
    assert measurements["predict_prepare_ms"].kind is TraceValueKind.LEGACY_PROJECTED
    assert measurements["predict_know_prepare_ms"].kind is TraceValueKind.LEGACY_PROJECTED
    assert measurements["actual_vllm_internal_ms"].name == "proxy_forward_to_first_chunk_duration"
    assert measurements["actual_vllm_internal_ms"].kind is TraceValueKind.ACTUAL
    assert measurements["actual_compute_ms"].kind is TraceValueKind.LEGACY_PROJECTED
    assert measurements["first_token_ms"].kind is TraceValueKind.LEGACY_PROJECTED
    assert measurements["decode_start_ms"].kind is TraceValueKind.LEGACY_PROJECTED
    assert "unknown_key" not in result.model_dump_json()
    assert "Traceback" not in result.model_dump_json()
    assert "password" not in result.model_dump_json()
    fallback = [stage for stage in result.stages if stage.name is TraceStageName.FALLBACK]
    assert fallback[0].outcome.value == "text_fallback"
    assert [stage.sequence for stage in result.stages] == list(range(len(result.stages)))


def test_projection_is_deterministic(now):
    kwargs = dict(request_id="req", correlation_id="corr", legacy_request_id=None,
                  trace={"actual_total_ms": 2, "unknown": 3}, exported_at=now,
                  runtime_profile="legacy")
    assert project_legacy_proxy_trace(**kwargs) == project_legacy_proxy_trace(**kwargs)
