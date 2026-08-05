# Architecture and evolution

## Historical root-component architecture

Status: Historical / Transitional. CacheRoute began as root runtime components: `scheduler`, `proxy`, `instance`, `kdn_server`, `client`, `core`, `store`, `model`, `UI`, and `util`. The runtime path remains Client -> Scheduler -> Proxy -> Instance -> vLLM, with KDN providing knowledge and KVCache assets.

## Current transitional repository

Status: Current / Transitional. Root runtime packages are still installed and used. Dependency-light canonical foundations also exist under `src/cacheroute/`: `runtime`, `topology`, `cache`, `routing`, `contracts`, `contracts.v1`, `observability`, `observability.v1`, and `compat`. The compatibility namespace `cacheroute_compat` forwards runtime helpers.

## Accepted target architecture

Status: Target / Accepted. The maintained ownership source is [package-architecture-rfc.md](../architecture/package-architecture-rfc.md). Accepted top-level ownership areas include `contracts`, `runtime`, `topology`, `knowledge`, `cache`, `routing`, `observability`, `integrations`, `services`, `plugins`, `entrypoints`, and `compat` under `src/cacheroute/`.

## Completed package and contract phases

Status: Current. Phase A package governance, runtime compatibility, KDN contract foundation, cache/routing/topology foundations, and observability v1 model foundations are represented by source modules and tests such as `test/test_namespace_layout.py`, `test/test_contract_foundation.py`, `test/test_contract_service_migration.py`, and `test/observability`.

## Current observability foundation and Scheduler-to-Proxy phase

Status: Current. PR #183 behavior is implemented and documented as Current:

- Scheduler owns the authoritative internal request ID.
- Scheduler overwrites the reserved trace headers before forwarding to Proxy.
- Proxy validates Scheduler headers or creates a local fallback context.
- Proxy observes prepare queue, ready queue, first response, decode, and completion stages.
- Collection remains process-local.
- No canonical trace is returned to clients.
- No trace context is propagated from Proxy to Instance.
- There is no exporter, persistence, debug registry, Gateway, LMCache, vLLM, or Instance instrumentation yet.

Broader Issue #141 remains incomplete and belongs in the roadmap, not Current behavior.

## Compatibility paths that remain necessary

Status: Transitional. Root packages remain importable. `cacheroute_compat.runtime` and `core.runtime_compat` preserve legacy runtime compatibility. KDN contract modules under `kdn_server/contracts` forward to canonical `cacheroute.contracts.v1` objects and must preserve object identity.

## Approved target packages not yet implemented

Status: Target / Accepted, not Current. The following approved ownership areas are absent in the current source tree and must not be documented as importable: `cacheroute.knowledge`, `cacheroute.integrations`, `cacheroute.services`, `cacheroute.plugins`, `cacheroute.entrypoints`, and their approved subpackages.

## Proposed future phases

Status: Proposed unless backed by source and tests. Future work includes focused service migrations, integration adapters for vLLM/LMCache/Redis/embeddings, canonical entrypoints, exporters, persistence, and broader unified observability completion.
