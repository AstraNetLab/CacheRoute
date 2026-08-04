from copy import deepcopy
from datetime import datetime, timezone
import math

from cacheroute.observability import project_legacy_proxy_trace


def test_allowlist_projection_is_pure_safe_and_has_no_request_id():
    source = {"proxy_enqueue_ms": 1000, "predict_total_ms": 12, "actual_total_ms": 10,
              "injection_mode": "kvcache", "request_id": "not_public", "unknown": 42,
              "error": RuntimeError("secret"), "kv_ack": {"private": b"kv"}}
    original = deepcopy({key: value for key, value in source.items() if key != "error"})
    original_error = source["error"]
    stages = project_legacy_proxy_trace(source, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    dumped = str(tuple(stage.model_dump(mode="json") for stage in stages))
    assert {key: value for key, value in source.items() if key != "error"} == original
    assert source["error"] is original_error
    assert "request_id" not in dumped and "unknown" not in dumped and "secret" not in dumped and "kv_ack" not in dumped
    assert all(measurement.value_kind.value == "legacy_projected" for stage in stages for measurement in stage.measurements)


def test_current_cacheroute_meta_inventory_has_no_request_id():
    text = open("proxy/proxy.py", encoding="utf-8").read()
    body = text.split("def build_cacheroute_meta", 1)[1].split("def _sse_meta_event", 1)[0]
    assert '"request_id"' not in body
    for name in ("trace", "kv_ack", "kv_ready_kids", "text_only_kids", "miss_kids", "error"):
        assert f'"{name}"' in body


def test_projection_omits_nonfinite_overflow_and_malformed_allowlisted_values():
    source = {
        "proxy_enqueue_ms": math.nan,
        "first_token_ms": math.inf,
        "forward_end_ms": 10**1000,
        "actual_total_ms": 10**1000,
        "predict_total_ms": math.inf,
        "injection_mode": math.nan,
    }
    original = dict(source)
    assert project_legacy_proxy_trace(source, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)) == ()
    assert source == original


def test_projection_accepts_only_current_logical_scalar_vocabulary():
    accepted = {
        "injection_mode": "text", "kvcache_actual_path": "kv_inject",
        "text_actual_path": "text_inject",
    }
    projected = project_legacy_proxy_trace(accepted, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert {(m.code, m.scalar) for stage in projected for m in stage.measurements} == set(accepted.items())
    unknown = {"injection_mode": "hybrid", "kvcache_actual_path": "unknown_path", "text_actual_path": "Tell me a joke"}
    assert project_legacy_proxy_trace(unknown, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)) == ()
