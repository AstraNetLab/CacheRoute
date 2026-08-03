# KDN shared domain vocabulary

[Back to the KDN architecture](../README.md) · [Source: `models.py`](models.py) · [Wire contracts](../contracts/README.md)

The domain package defines immutable logical identities and lifecycle state reused by the Cache Service contracts and Gateway responses. These objects describe control-plane truth; they never contain physical KV payloads.

## RuntimeProfile

`v1`, `legacy`, and `test/mock` are resolved execution profiles. `auto` exists only for startup selection and must be resolved before any model is serialized or persisted. This prevents an ambiguous runtime choice from crossing a process boundary.

`RuntimeProfile` is canonically implemented by `cacheroute.runtime`;
`kdn_server.domain` re-exports that same object for compatibility. The remaining
cache artifact, endpoint, observation, operation, and queue models continue to
live in [`models.py`](models.py).

## CacheArtifact

A `CacheArtifact` identifies a logical cache materialization. Its canonical `artifact_id` is deterministically derived from knowledge version, model, tokenizer, ordered adapters, cache-data profile, compatibility profile, runtime profile, and schema version. It is an identity for compatibility and lookup—not a physical chunk, block, key, or storage location.

## LMCacheEndpoint

An `LMCacheEndpoint` has a stable logical endpoint identity. Its generation increases when compatibility-relevant endpoint state changes, allowing callers to distinguish current observations from facts about an older incarnation.

## CacheReplicaObservation

A replica observation is a time-bounded logical report, not an assertion that KDN owns a physical replica. It records source, confidence, Runtime Profile, compatibility profile, endpoint identity and generation, observation/projected timestamps, and expiry.

Freshness uses a closed-open interval:

```text
source_observed_at <= at < expires_at
```

Legacy projections may use endpoint generation `0` to mean that the generation is unknown. Non-Legacy observations require a positive generation.

## CacheOperationTask

A task represents logical lookup, prefetch, pin, unpin, clear, rebuild, or observation work. The main lifecycle is:

```text
pending -> running -> succeeded
                   -> retry_wait -> running
                   -> failed
pending/running/retry_wait -> cancelled
```

Terminal states do not transition further; same-state transitions are idempotent. Retry state is explicit, and v1 write operations cannot target the Legacy Gateway implicitly.

## QueueWork

`QueueWork` supplies queue lifecycle vocabulary—queued, claimed, executing, retry wait, completed, failed, and cancelled—without implementing admission, placement, or scheduling policy. It links queue work to a logical cache task while preserving independent transition validation.

## Reuse by higher layers

[Cache Service responses](../contracts/README.md) return these objects directly where appropriate. [Gateway adapters](../gateway/README.md) validate their Runtime/Profile/Endpoint/Generation provenance before returning success, so callers share one domain vocabulary instead of adapter-specific state shapes.
