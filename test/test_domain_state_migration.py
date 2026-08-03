"""Focused migration checks for Issue #174 canonical domain state ownership."""

import ast
import os
from pathlib import Path
import subprocess
import sys

import cacheroute.cache as cache
import cacheroute.routing as routing
import cacheroute.runtime as runtime
import cacheroute.runtime.state as runtime_state
import cacheroute.topology as topology
import kdn_server.domain as legacy
import kdn_server.domain.models as legacy_models


OWNERS = {
    runtime_state.StrEnum: "cacheroute.runtime.state",
    runtime_state.Snapshot: "cacheroute.runtime.state",
    runtime_state.StateTransitionError: "cacheroute.runtime.state",
    topology.LMCacheGatewayProfile: "cacheroute.topology.lmcache",
    topology.LMCacheEndpoint: "cacheroute.topology.lmcache",
    cache.ObservationSource: "cacheroute.cache.models",
    cache.ObservationConfidence: "cacheroute.cache.models",
    cache.ObservationState: "cacheroute.cache.models",
    cache.CacheOperationType: "cacheroute.cache.models",
    cache.CacheOperationState: "cacheroute.cache.models",
    cache.CacheArtifact: "cacheroute.cache.models",
    cache.CacheReplicaObservation: "cacheroute.cache.models",
    cache.CacheOperationTask: "cacheroute.cache.models",
    routing.QueueState: "cacheroute.routing.queue",
    routing.QueueWork: "cacheroute.routing.queue",
}


def test_canonical_ownership_and_legacy_object_identity():
    for canonical, module in OWNERS.items():
        assert canonical.__module__ == module
        assert getattr(legacy, canonical.__name__) is canonical
    assert legacy_models.utc_now is runtime_state.utc_now


def test_legacy_models_is_an_import_only_shim():
    path = Path(__file__).parents[1] / "kdn_server/domain/models.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed = (ast.Expr, ast.ImportFrom, ast.Assign)
    assert all(isinstance(node, allowed) for node in tree.body)
    assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)


def test_enum_wire_values_are_unchanged():
    assert [item.value for item in topology.LMCacheGatewayProfile] == [
        "mp_http_api", "mp_coordinator", "mp_sdk", "mp_metrics_events",
        "legacy_gateway", "mock", "unknown_future",
    ]
    assert [item.value for item in cache.CacheOperationState] == [
        "pending", "running", "retry_wait", "succeeded", "failed", "cancelled",
    ]
    assert [item.value for item in routing.QueueState] == [
        "queued", "claimed", "executing", "retry_wait", "completed", "failed", "cancelled",
    ]


def test_dependency_light_fresh_process_imports():
    script = r'''
import sys
import cacheroute.runtime.state
import cacheroute.topology
import cacheroute.topology.lmcache
import cacheroute.cache
import cacheroute.cache.models
import cacheroute.routing
import cacheroute.routing.queue
for name in (
    "kdn_server", "scheduler", "proxy", "instance", "client", "store", "model", "UI",
    "fastapi", "redis", "numpy", "torch", "sentence_transformers", "vllm", "lmcache",
):
    assert name not in sys.modules, name
'''
    env = os.environ | {"PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    subprocess.run([sys.executable, "-c", script], check=True, env=env)
