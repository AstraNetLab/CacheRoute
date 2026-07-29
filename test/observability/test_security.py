import pytest
from pydantic import ValidationError

from cacheroute_observability import TraceContext, TraceMeasurement


@pytest.mark.parametrize("key", [
    "password", "authorization", "redis_key", "kv_bytes", "tensor",
    "device_pointer", "physical_path", "request_body", "raw_exception",
])
def test_recursive_secret_and_physical_field_rejection(now, key):
    data = {
        "trace_id": "trace_" + "1" * 32, "request_id": "r", "correlation_id": "c",
        "created_at": now, "nested": {key: "bad"},
    }
    with pytest.raises(ValidationError, match="forbidden observability field"):
        TraceContext.model_validate(data)


def test_generic_container_and_extra_rejected(provenance):
    with pytest.raises(ValidationError):
        TraceMeasurement(name="unsafe", kind="observed", provenance=provenance,
                         safe_scalar={"safe": "looking"})
    with pytest.raises(ValidationError):
        TraceMeasurement(name="unsafe", kind="observed", provenance=provenance,
                         safe_scalar="ok", prompt="secret")
