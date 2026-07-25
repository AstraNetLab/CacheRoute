import json

import pytest

from core.instance_capability import InstanceCapability, capability_fingerprint, compare_capabilities
from instance import capability_builder


def complete_capability(**changes):
    data = {
        "schema_version": "1",
        "model": {"identifier": "model-a", "revision": "r1"},
        "tokenizer": {"identifier": "tokenizer-a", "revision": "r1"},
        "adapters": [
            {"identifier": "adapter-a", "revision": "1", "configuration": {"rank": 8}},
            {"identifier": "adapter-b", "revision": "2", "configuration_hash": "sha256:a"},
        ],
        "kv_cache": {"layout": "paged", "schema_version": "1", "dtype": "fp16", "block_size": 16,
                     "layout_parameters": {"heads": 8}},
        "parallelism": {"tensor_parallel_size": 2, "pipeline_parallel_size": 1, "data_parallel_size": 1},
        "runtime": {"vllm_version": "1.0", "lmcache_version": "2.0",
                    "supported_cache_features": ["lookup", "transfer"]},
    }
    for path, value in changes.items():
        target = data
        parts = path.split("__")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    return InstanceCapability.model_validate(data)


def test_fingerprint_is_canonical_and_feature_order_is_set_like():
    left = complete_capability()
    raw = json.loads(left.model_dump_json())
    raw = {key: raw[key] for key in reversed(raw)}
    raw["runtime"]["supported_cache_features"] = ["transfer", "lookup", "lookup"]
    assert capability_fingerprint(left) == capability_fingerprint(raw)


@pytest.mark.parametrize("path,value", [
    ("model__identifier", "model-b"), ("tokenizer__identifier", "tokenizer-b"),
    ("kv_cache__layout", "contiguous"), ("kv_cache__dtype", "bf16"),
    ("parallelism__tensor_parallel_size", 4), ("parallelism__pipeline_parallel_size", 2),
    ("parallelism__data_parallel_size", 2),
])
def test_compatibility_fields_change_fingerprint_and_report_path(path, value):
    left, right = complete_capability(), complete_capability(**{path: value})
    assert capability_fingerprint(left) != capability_fingerprint(right)
    result = compare_capabilities(left, right)
    assert result.status == "incompatible"
    assert result.compatible is False
    assert path.replace("__", ".") in {item.field for item in result.mismatches}


def test_adapter_stack_order_is_semantically_meaningful():
    left = complete_capability()
    raw = left.model_dump()
    raw["adapters"].reverse()
    assert capability_fingerprint(left) != capability_fingerprint(raw)


def test_transient_unmodelled_data_is_rejected_not_fingerprinted():
    raw = complete_capability().model_dump()
    raw["host"] = "example.invalid"
    with pytest.raises(ValueError):
        capability_fingerprint(raw)


def test_matching_complete_capabilities_are_compatible():
    result = compare_capabilities(complete_capability(), complete_capability())
    assert result.status == "compatible"
    assert result.compatible and result.mismatches == []
    assert result.left_fingerprint == result.right_fingerprint


def test_multiple_mismatches_are_all_machine_readable():
    result = compare_capabilities(
        complete_capability(), complete_capability(model__identifier="b", kv_cache__dtype="bf16")
    )
    assert {item.field for item in result.mismatches} >= {"model.identifier", "kv_cache.dtype"}
    assert all(item.reason == "value_mismatch" for item in result.mismatches)


def test_missing_legacy_or_incomplete_capabilities_are_unknown():
    assert compare_capabilities(None, complete_capability()).status == "unknown"
    result = compare_capabilities(InstanceCapability(), InstanceCapability())
    assert result.status == "unknown"
    assert not result.compatible


def test_builder_defaults_and_environment_overrides(monkeypatch):
    monkeypatch.setenv("INSTANCE_MODEL_ID", "env-model")
    monkeypatch.setenv("INSTANCE_MODEL_REVISION", "rev")
    monkeypatch.setenv("INSTANCE_KV_BLOCK_SIZE", "32")
    monkeypatch.setenv("INSTANCE_TENSOR_PARALLEL_SIZE", "4")
    monkeypatch.setenv("INSTANCE_CACHE_FEATURES", "transfer, lookup")
    monkeypatch.setenv("INSTANCE_VLLM_VERSION", "override")
    monkeypatch.setenv("INSTANCE_ADAPTERS_JSON", '[{"identifier":"lora","configuration":{"rank":8}}]')
    capability = capability_builder.build_instance_capability()
    assert capability.model.identifier == capability.tokenizer.identifier == "env-model"
    assert capability.kv_cache.block_size == 32
    assert capability.parallelism.tensor_parallel_size == 4
    assert capability.runtime.vllm_version == "override"
    assert capability.adapters[0].identifier == "lora"


def test_builder_tolerates_missing_packages(monkeypatch):
    monkeypatch.delenv("INSTANCE_VLLM_VERSION", raising=False)
    monkeypatch.delenv("INSTANCE_LMCACHE_VERSION", raising=False)
    def missing(_name):
        raise capability_builder.metadata.PackageNotFoundError
    monkeypatch.setattr(capability_builder.metadata, "version", missing)
    capability = capability_builder.build_instance_capability()
    assert capability.runtime.vllm_version is None
    assert capability.runtime.lmcache_version is None


@pytest.mark.parametrize("raw", ["not-json", "{}"])
def test_invalid_adapter_json_has_predictable_error(monkeypatch, raw):
    monkeypatch.setenv("INSTANCE_ADAPTERS_JSON", raw)
    with pytest.raises(ValueError, match="INSTANCE_ADAPTERS_JSON"):
        capability_builder.build_instance_capability()
