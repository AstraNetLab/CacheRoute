import json
import subprocess
import sys
from pathlib import Path


def test_demo_succeeds_and_shows_required_data():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / "scripts/demo_observability_v1.py")],
                            cwd=root, check=True, text=True, capture_output=True)
    lines = result.stdout.splitlines()
    assert lines[-1] == "observability v1 demo: passed"
    payload = json.loads("\n".join(lines[:-1]))
    assert payload["request_trace"]["schema_version"] == "cacheroute.trace.v1"
    assert payload["request_trace"]["context"]["schema_version"] == "cacheroute.trace-context.v1"
    assert payload["stage_sequence"][:4] == [
        "runtime_profile_resolution", "gateway_request", "fallback", "gateway_request",
    ]
    assert payload["value_kinds"] == ["predicted", "actual"]
    assert payload["shared_operation_waiter_ids"] == ["req-waiter-2", "req-waiter-3"]
    legacy_json = json.dumps(payload["legacy_projection"])
    assert "raw exception" not in legacy_json
    assert "unknown_secretish_result" not in legacy_json
