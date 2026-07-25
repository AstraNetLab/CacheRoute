"""Typed instance capability contract and deterministic compatibility helpers."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelCapability(CapabilityModel):
    identifier: Optional[str] = None
    revision: Optional[str] = None


class AdapterCapability(CapabilityModel):
    identifier: str
    revision: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    configuration_hash: Optional[str] = None


class KVCacheCapability(CapabilityModel):
    layout: Optional[str] = None
    schema_version: Optional[str] = None
    dtype: Optional[str] = None
    block_size: Optional[int] = Field(default=None, gt=0)
    layout_parameters: Dict[str, Any] = Field(default_factory=dict)


class ParallelismCapability(CapabilityModel):
    tensor_parallel_size: Optional[int] = Field(default=None, gt=0)
    pipeline_parallel_size: Optional[int] = Field(default=None, gt=0)
    data_parallel_size: Optional[int] = Field(default=None, gt=0)


class RuntimeCapability(CapabilityModel):
    vllm_version: Optional[str] = None
    lmcache_version: Optional[str] = None
    supported_cache_features: List[str] = Field(default_factory=list)


class InstanceCapability(CapabilityModel):
    schema_version: str = "1"
    model: ModelCapability = Field(default_factory=ModelCapability)
    tokenizer: ModelCapability = Field(default_factory=ModelCapability)
    adapters: List[AdapterCapability] = Field(default_factory=list)
    kv_cache: KVCacheCapability = Field(default_factory=KVCacheCapability)
    parallelism: ParallelismCapability = Field(default_factory=ParallelismCapability)
    runtime: RuntimeCapability = Field(default_factory=RuntimeCapability)


def canonical_capability_dict(capability: InstanceCapability | Dict[str, Any]) -> Dict[str, Any]:
    """Return compatibility data with stable set-like feature ordering.

    Pydantic validation removes ambiguity in scalar representations. ``exclude_none``
    gives absent optional values one representation, while adapter order remains intact.
    """
    value = capability if isinstance(capability, InstanceCapability) else InstanceCapability.model_validate(capability)
    data = value.model_dump(mode="json", exclude_none=True)
    features = data.get("runtime", {}).get("supported_cache_features")
    if features is not None:
        data["runtime"]["supported_cache_features"] = sorted(set(features))
    return data


def canonical_capability_json(capability: InstanceCapability | Dict[str, Any]) -> str:
    return json.dumps(
        canonical_capability_dict(capability), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def capability_fingerprint(capability: InstanceCapability | Dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_capability_json(capability).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class CompatibilityMismatch(CapabilityModel):
    field: str
    left: Any = None
    right: Any = None
    reason: Literal["value_mismatch", "missing_value"]


class CompatibilityResult(CapabilityModel):
    status: Literal["compatible", "incompatible", "unknown"]
    compatible: bool
    left_fingerprint: Optional[str] = None
    right_fingerprint: Optional[str] = None
    mismatches: List[CompatibilityMismatch] = Field(default_factory=list)


_COMPATIBILITY_PATHS = (
    "schema_version",
    "model.identifier", "model.revision",
    "tokenizer.identifier", "tokenizer.revision",
    "adapters", "kv_cache.layout", "kv_cache.schema_version", "kv_cache.dtype",
    "kv_cache.block_size", "kv_cache.layout_parameters",
    "parallelism.tensor_parallel_size", "parallelism.pipeline_parallel_size",
    "parallelism.data_parallel_size", "runtime.vllm_version", "runtime.lmcache_version",
    "runtime.supported_cache_features",
)


def _at(data: Dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def compare_capabilities(
    left: Optional[InstanceCapability | Dict[str, Any]],
    right: Optional[InstanceCapability | Dict[str, Any]],
) -> CompatibilityResult:
    """Compare capabilities without treating incomplete legacy data as compatible."""
    if left is None or right is None:
        return CompatibilityResult(status="unknown", compatible=False)
    left_model = left if isinstance(left, InstanceCapability) else InstanceCapability.model_validate(left)
    right_model = right if isinstance(right, InstanceCapability) else InstanceCapability.model_validate(right)
    left_data = canonical_capability_dict(left_model)
    right_data = canonical_capability_dict(right_model)
    mismatches: List[CompatibilityMismatch] = []
    missing = False
    for path in _COMPATIBILITY_PATHS:
        left_value, right_value = _at(left_data, path), _at(right_data, path)
        if left_value is None or right_value is None:
            missing = True
            if left_value != right_value:
                mismatches.append(CompatibilityMismatch(
                    field=path, left=left_value, right=right_value, reason="missing_value"
                ))
        elif left_value != right_value:
            mismatches.append(CompatibilityMismatch(
                field=path, left=left_value, right=right_value, reason="value_mismatch"
            ))
    left_fp, right_fp = capability_fingerprint(left_model), capability_fingerprint(right_model)
    if any(item.reason == "value_mismatch" for item in mismatches):
        status = "incompatible"
    elif missing:
        status = "unknown"
    else:
        status = "compatible"
    return CompatibilityResult(
        status=status, compatible=status == "compatible", left_fingerprint=left_fp,
        right_fingerprint=right_fp, mismatches=mismatches,
    )
