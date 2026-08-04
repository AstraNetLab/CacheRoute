from copy import deepcopy
from datetime import datetime, timezone

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
