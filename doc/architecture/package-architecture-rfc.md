# CacheRoute package architecture RFC

This document records the target Python package architecture adopted by the repository architecture RFC and Issue #157 migration epic.

## Decision

Keep one installable Python namespace under `src/cacheroute`, but organize it by architectural responsibility rather than by mechanically copying the current repository root.

The target top-level packages are:

- `cacheroute.contracts`
- `cacheroute.runtime`
- `cacheroute.topology`
- `cacheroute.knowledge`
- `cacheroute.cache`
- `cacheroute.routing`
- `cacheroute.observability`
- `cacheroute.integrations`
- `cacheroute.services`
- `cacheroute.plugins`
- `cacheroute.entrypoints`
- `cacheroute.compat`

Do not introduce a generic `cacheroute.core` dumping ground.

## Target repository layout

```text
CacheRoute/
├── src/
│   └── cacheroute/
├── tests/
├── examples/
├── doc/
├── scripts/
├── env/
├── crates/
├── pyproject.toml
├── README.md
└── AGENTS.md
```

`crates/` is reserved for independently built native components such as the Resource Agent. Adding or moving a native component still requires a focused architecture review.

## Package responsibilities

### `contracts`

Versioned, JSON-serializable cross-process contracts only.

It must not import FastAPI, Redis, Torch, vLLM, LMCache, or service implementations.

### `runtime`

Runtime Profile, model/tokenizer/KV-layout identity, capability fingerprints, and lifecycle concepts shared across components.

### `topology`

Service registration, health, resource snapshots, endpoint generation, and cluster topology.

### `knowledge`

Knowledge descriptors, semantic resolution, indexing abstractions, and knowledge repository ports.

### `cache`

Cache artifact models, CachePlan/FusionPlan, cache-operation models, compatibility evaluation, and Cache Runtime ports.

It must not directly implement LMCache, Redis, or vLLM operations.

### `routing`

Admission, queueing, endpoint selection, load models, and routing policies.

Reusable policy must not depend on FastAPI applications or process-global service state.

### `observability`

Dependency-light trace contracts, collectors, events, exporters, and Legacy projections.

### `integrations`

External-system adapters:

- `integrations.vllm`
- `integrations.lmcache`
- `integrations.redis`
- `integrations.embeddings`

Domain packages must not import integrations.

### `services`

Deployable process implementations:

- `services.scheduler`
- `services.proxy`
- `services.instance`
- `services.kdn`

Services use contracts and domain capabilities. They must not import another service's internal implementation.

### `entrypoints`

CLI, Uvicorn application factories, development orchestration, and process composition.

The long-term command surface is:

```text
cacheroute scheduler
cacheroute proxy
cacheroute instance
cacheroute kdn
cacheroute dev
```

Direct scripts under tests are not production entrypoints.

### `plugins`

Stable extension protocols and discovery for:

- Cache Runtime Gateways;
- runtime/engine connectors;
- observability exporters.

Use Python entry points or explicit module paths. Do not pluginize every internal strategy in the first phase.

### `compat`

Temporary import and wire compatibility only. No permanent implementation may live here.

## Integration boundaries

### vLLM

Create a dedicated `cacheroute.integrations.vllm` boundary.

Separate:

- scheduler-side external KV lookup and metadata;
- worker-side KV materialization;
- capability discovery;
- hit-token and remote-read observations;
- failure mapping and recomputation policy.

Do not depend on private model-runner implementation details where the public KVConnector interface is sufficient.

### LMCache

Create a dedicated `cacheroute.integrations.lmcache` boundary implementing Cache Runtime ports.

Separate:

- capability/profile discovery;
- lookup and operation submission;
- asynchronous status;
- pin/unpin/clear/prefetch operations;
- events and metrics;
- endpoint generation and freshness.

Do not mirror or maintain an authoritative copy of LMCache's physical L1/L2 block index.

### Legacy

Legacy Redis scan/dump/restore behavior is an adapter implementation, not the canonical cache domain.

Keep Legacy wire compatibility explicit and isolated.

## Dependency direction

Allowed direction:

```text
contracts
    ↓
runtime / topology / knowledge / cache / routing / observability
    ↓
service application logic

integrations implement domain ports
entrypoints wire services, integrations, settings, and lifecycle
```

Forbidden dependencies:

- contracts importing services;
- domain packages importing FastAPI or external storage/runtime SDKs;
- service packages importing another service's internal modules;
- KDN domain logic importing LMCache or Redis directly;
- vLLM adapters importing Instance service internals;
- reusable routing policy importing Proxy application state.

## Public API policy

Stable public library surfaces:

- `cacheroute.contracts.v1`
- `cacheroute.observability`
- selected domain models and ports
- documented plugin interfaces
- documented vLLM connector module path

Operational but not general-purpose public APIs:

- `cacheroute.services.*`
- `cacheroute.entrypoints.*`

`cacheroute.__init__` remains empty or metadata-only.

## Packaging policy

The final wheel must contain only the `cacheroute` namespace and explicitly approved temporary compatibility shims.

The following repository categories must not be installed as Python packages:

- tests;
- documentation;
- scripts;
- deployment configuration;
- logs;
- generated data.

Runtime package data must be owned by the package that consumes it.

## Versioning policy

Version compatibility boundaries, not the entire implementation tree.

Examples:

- `contracts.v1`
- `integrations.vllm.connector_v1`
- cache artifact schema versions
- observability schema versions

Do not place the whole project under `cacheroute.v1`.

## Migration mapping

- `kdn_server/contracts` -> `cacheroute.contracts.v1`
- shared KDN domain concepts -> `runtime`, `knowledge`, and `cache`
- `kdn_server/gateway` -> `integrations.lmcache` / `integrations.redis`
- Scheduler strategies -> `routing`
- Scheduler and Proxy registries -> `topology`
- Proxy reusable queue policy -> `routing`; process queue state remains in `services.proxy`
- Instance vLLM discovery -> `integrations.vllm`
- embedding implementation -> `integrations.embeddings`
- UI assets -> owning service package
- demo launchers -> `entrypoints.dev` or `examples`
- generic `util` -> owning domain; no permanent utility dumping ground

## Migration phases

### Phase 0 — architecture approval

Approve the RFC and make Issue #157 reference it as the target architecture.

### Phase 1 — packaging and entrypoint boundary

Clean packaging so only canonical packages and approved compatibility shims enter the wheel. Add the unified CLI and application factories.

### Phase 2 — contracts and dependency-light domains

Move versioned contracts, Runtime Profile, lifecycle models, capability models, and topology/resource models.

### Phase 3 — external integrations

Introduce vLLM, LMCache, Redis, and embedding integration boundaries.

### Phase 4 — services

Migrate KDN, Scheduler, Proxy, and Instance in separate reviewable PRs.

### Phase 5 — UI, development orchestration, and native components

Move UI assets to their owning service packages, replace test demos with entrypoints/examples, and review native components separately.

### Phase 6 — compatibility cleanup

Remove obsolete root runtime packages, source bootstraps, transition package lists, and expired compatibility shims.

## Required architecture tests

Add automated checks for:

- forbidden dependency directions;
- dependency-light import isolation;
- no service-to-service internal imports;
- no external SDK imports from domain packages;
- wheel top-level package allowlist;
- console entrypoint smoke tests;
- dynamic plugin loading;
- stale import and module-string references;
- Markdown links;
- application factory imports;
- clean editable and wheel installation.

## Non-goals

- changing routing policy behavior;
- changing cache hit semantics;
- implementing new LMCache production I/O;
- changing current wire values;
- instrumenting production observability;
- rewriting the root README;
- migrating every component in one PR.
