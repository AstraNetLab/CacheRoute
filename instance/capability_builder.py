"""Build instance capabilities without loading models or importing serving runtimes."""
from __future__ import annotations

import json
import os
from importlib import metadata
from typing import Any, Optional

from core import config
from core.instance_capability import (
    AdapterCapability, InstanceCapability, KVCacheCapability, ModelCapability,
    ParallelismCapability, RuntimeCapability,
)


def _optional(name: str, configured: Any = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        value = configured
    text = str(value).strip() if value is not None else ""
    return text or None


def _positive_int(name: str, configured: Any = None) -> Optional[int]:
    value = _optional(name, configured)
    if value is None:
        return None
    number = int(value)
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _package_version(distribution: str) -> Optional[str]:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _adapters() -> list[AdapterCapability]:
    raw = _optional("INSTANCE_ADAPTERS_JSON")
    if raw is None:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("INSTANCE_ADAPTERS_JSON must contain valid JSON") from exc
    if not isinstance(parsed, list):
        raise ValueError("INSTANCE_ADAPTERS_JSON must contain a JSON array")
    return [AdapterCapability.model_validate(item) for item in parsed]


def build_instance_capability() -> InstanceCapability:
    """Build with precedence: environment, CacheRoute config, detected version, null."""
    model_id = _optional("INSTANCE_MODEL_ID", getattr(config, "DEFAULT_MODEL", None))
    tokenizer_id = _optional("INSTANCE_TOKENIZER_ID", model_id)
    features = [item.strip() for item in (_optional("INSTANCE_CACHE_FEATURES") or "").split(",") if item.strip()]
    return InstanceCapability(
        model=ModelCapability(identifier=model_id, revision=_optional("INSTANCE_MODEL_REVISION")),
        tokenizer=ModelCapability(identifier=tokenizer_id, revision=_optional("INSTANCE_TOKENIZER_REVISION")),
        adapters=_adapters(),
        kv_cache=KVCacheCapability(
            layout=_optional("INSTANCE_KV_LAYOUT"), schema_version=_optional("INSTANCE_KV_SCHEMA_VERSION"),
            dtype=_optional("INSTANCE_KV_DTYPE"), block_size=_positive_int("INSTANCE_KV_BLOCK_SIZE"),
        ),
        parallelism=ParallelismCapability(
            tensor_parallel_size=_positive_int("INSTANCE_TENSOR_PARALLEL_SIZE"),
            pipeline_parallel_size=_positive_int("INSTANCE_PIPELINE_PARALLEL_SIZE"),
            data_parallel_size=_positive_int("INSTANCE_DATA_PARALLEL_SIZE"),
        ),
        runtime=RuntimeCapability(
            vllm_version=_optional("INSTANCE_VLLM_VERSION") or _package_version("vllm"),
            lmcache_version=_optional("INSTANCE_LMCACHE_VERSION") or _package_version("lmcache"),
            supported_cache_features=features,
        ),
    )
