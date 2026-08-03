# Versioned KDN service contracts

[Back to the KDN architecture](../README.md) · [Shared domain vocabulary](../domain/README.md) · [Gateway architecture](../gateway/README.md) · [Executable workflows](../../test/kdn/README.md)

The contracts package is the storage-neutral public wire layer. Common and
error definitions are canonically owned by `cacheroute.contracts.v1`;
[`common.py`](common.py) and [`errors.py`](errors.py) are temporary forwarding
modules and must not acquire new validators, enums, constants, or contract
implementation logic. [`knowledge.py`](knowledge.py) and
[`cache_service.py`](cache_service.py) remain transitional implementations.
During migration, `kdn_server.contracts` remains a supported compatibility
import surface through [`__init__.py`](__init__.py).

## Contract versions and evolution

- `KDN_CONTRACT_VERSION = "kdn.v1"`
- `GATEWAY_CONTRACT_VERSION = "lmcache-gateway.v1"`

Enum wire values and existing field meanings are stable. Unsupported versions are rejected explicitly. Additive evolution should use compatible optional fields when semantics remain unchanged; otherwise introduce a new contract version. Never silently reinterpret a persisted field.

## Common envelope

Every versioned message carries a resolved `runtime_profile`, `request_id`, optional `correlation_id`, and timezone-aware UTC timestamp. Models are frozen Pydantic models with `extra="forbid"`, and validation rejects startup-only `auto`. Unknown fields therefore cannot smuggle backend-specific or sensitive state across the boundary.

Gateway-targeted requests and responses additionally require a non-empty `compatibility_profile_id`, canonical `endpoint_id`, and endpoint generation. The target makes negotiation reproducible:

- Runtime/Profile/Endpoint mismatch → `incompatible`;
- generation mismatch → `stale`;
- unknown or unsupported capability → `unsupported`.

Legacy may use generation `0` for unknown; v1 and test/mock require a positive generation.

## Knowledge Service families

[`knowledge.py`](knowledge.py) defines storage-neutral contracts to register, update, and resolve knowledge; list compatible artifacts; query artifact compatibility; and report request outcomes. These are contracts only—this package does not register HTTP routes or prescribe a database.

## Cache Service families

[`cache_service.py`](cache_service.py) defines dedicated request and response families for artifact lookup, cache observation, token lookup, prefetch, pin/unpin, clear, rebuild, operation status and cancellation, endpoint discovery, tier/adapter summaries, and maintenance status.

Dedicated responses validate their expected success payload, target provenance, observation freshness, operation provenance, intent-specific operation type, and terminal cancellation no-op semantics. The outcome vocabulary is `success`, `unsupported`, `incompatible`, `stale`, `partial`, `failed`, `cancelled`, `text_fallback`, and `idempotency_conflict`. Every non-success response carries a matching safe `ContractErrorDetail`.

## Token contracts

`TokenInput` accepts exactly one of an immutable tuple of token IDs or an opaque `TokenReference`. `TokenCoverage.whole_request_hit` represents whole-request hit/miss independently from `covered_ranges`; exact ranges are exposed only when `range_coverage` is explicitly supported. This layer does not implement LMCache hashing, chunk keys, token databases, serialization, or block allocation.

## Security and storage neutrality

Contracts prohibit credentials, API keys, authorization headers, raw Redis keys, KV bytes, tensors, device pointers, physical chunk/block indexes, and private serialized LMCache objects. Structured errors contain stable codes and safe messages—not backend exceptions.

## Minimal examples

```python
from kdn_server.contracts import LookupArtifactRequest, LookupTokensRequest, TokenInput

TARGET = {
    "runtime_profile": "test/mock",
    "compatibility_profile_id": "example-compatible-v1",
    "endpoint_id": "endpoint_" + "1" * 32,
    "endpoint_generation": 1,
}
artifact_request = LookupArtifactRequest(
    **TARGET,
    artifact_id="artifact_" + "2" * 32,
)
token_request = LookupTokensRequest(
    **TARGET,
    tokens=TokenInput(token_ids=(11, 12, 13)),
)
```

Inspect outcomes without parsing backend-specific payloads:

```python
response = gateway.lookup_tokens(token_request)
if response.outcome.value == "text_fallback":
    assert response.error.fallback_eligible
```

For complete, executable Mock and Legacy sequences, continue to the [CPU-only workflow guide](../../test/kdn/README.md).
