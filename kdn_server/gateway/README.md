# LMCache Gateway architecture

[Back to the KDN architecture](../README.md) · [Wire contracts](../contracts/README.md) · [Shared domain](../domain/README.md) · [CPU-only workflows](../../test/kdn/README.md)

The Gateway package is the orchestration boundary between stable CacheRoute contracts and transport-specific LMCache capability surfaces. It does not move physical KV payloads.

## Gateway vocabulary

[`profiles.py`](profiles.py) defines adapter kinds: `mp_http_api`, `mp_coordinator`, `mp_sdk`, `mp_metrics_events`, optional `mp_l2_plugin`, `legacy_redis`, `mock`, and `unknown_future`. A transport kind says *how an adapter is reached*; it is separate from `LMCacheCompatibilityProfile`, which says *whether logical cache artifacts and operations are compatible*.

## LMCacheCompatibilityProfile

A compatibility profile may identify LMCache version/build, configuration, key/hash scheme, layout, serde, chunk size, and connector profile. It never contains credentials, authorization data, or connection secrets.

## CapabilitySnapshot

[`capabilities.py`](capabilities.py) defines an immutable startup/discovery snapshot containing the Runtime Profile, ordered composed adapter bindings, compatibility profile, endpoint generation, loaded adapters and tiers, provenance, and tri-state capabilities.

> **`UNKNOWN` is never treated as `SUPPORTED`.**

Capability groups cover logical lookup/observation, range coverage, object listing/deletion, prefetch and operation lifecycle, pin/unpin, tier capacity and maintenance, metrics/events, batching, leases, asynchronous completion, and cancellation. Runtime isolation permits MP/future bindings for v1, `legacy_redis` only for Legacy, and `mock` only for test/mock.

## Negotiation and capability gating

[`GatewayAdapterBase`](base.py) applies the shared flow:

```text
request
  -> Runtime/Profile/Endpoint validation
  -> endpoint-generation validation
  -> capability gate
  -> dedicated structured response
```

An incompatible target returns `INCOMPATIBLE`; an old generation returns `STALE`; an unknown or unsupported capability returns `UNSUPPORTED`. Response construction preserves request and correlation identity.

## LMCacheGateway Protocol

[`protocol.py`](protocol.py) is the stable boundary future adapters implement. It covers capability discovery, artifact and token lookup, cache observation, logical operation submission, status, cancellation, endpoint discovery, tier/adapter summary, and maintenance status. Upper layers depend on this Protocol and dedicated response contracts—not transport routes, module paths, or private response shapes.

## Current adapters

### MockGateway

[`mock.py`](mock.py) is deterministic and CPU-only. It provides fixture-based artifact, observation, token, endpoint, and summary results; independent token/range capabilities; idempotent task identity; asynchronous state simulation; cancellation; and structured stale, incompatible, unsupported, conflict, and fallback outcomes. It performs no network, Redis, filesystem, GPU, vLLM, or LMCache I/O.

### LegacyCacheAdapter

[`legacy.py`](legacy.py) is an explicit read-only boundary. Generation `0` represents unknown Legacy generation. It adds no v1 functionality: Legacy writes are unsupported and v1 calls are incompatible. The adapter performs no real Redis or filesystem I/O.

## Factory

[`factory.py`](factory.py) first verifies that the requested transport appears in the snapshot's adapter bindings. It constructs only Mock and Legacy adapters today. Production transport kinds are representable for negotiation but intentionally raise `NotImplementedError` at construction.

## Adding a production adapter later

1. Implement `LMCacheGateway`.
2. Keep route names, module paths, and private API differences inside the adapter.
3. Produce an immutable `CapabilitySnapshot` at startup.
4. Preserve request and correlation metadata.
5. Negotiate Runtime/Profile/Endpoint/Generation.
6. Gate every operation by an explicitly supported capability.
7. Return dedicated response types.
8. Never expose credentials or physical KV payloads.
9. Add CPU-only contract tests and separate integration tests.
10. Version any change to existing wire values or semantics.
