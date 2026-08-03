# CacheRoute package architecture RFC

> Status: Accepted; implementation in progress.

This document records the accepted target Python package architecture and the
focused migration sequence used to reach it.

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

`crates/` is reserved for independently built native components. Placing the
Resource Agent there remains a proposal until a focused migration Issue approves
it; this RFC alone does not authorize adding or moving it.

## Package responsibilities

### `contracts`

Versioned, JSON-serializable cross-process contracts only.

`contracts` owns wire schemas and enums, not service request handlers or framework adapters.

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

Observability exporters may implement reviewed plugin protocols, but canonical
observability contracts remain in this domain package.

### `integrations`

External-system adapters:

- `integrations.vllm`
- `integrations.lmcache`
- `integrations.redis`
- `integrations.embeddings`

Domain packages must not import integrations.

Integrations implement domain-owned ports; they do not define canonical domain
models or move external SDK semantics into domain packages. A port belongs with
the domain that owns its semantics.

### `services`

Deployable process implementations:

- `services.scheduler`
- `services.proxy`
- `services.instance`
- `services.kdn`

Services use contracts and domain capabilities. They must not import another service's internal implementation.

Services own process-specific state, request handlers, and framework adapters.

### `entrypoints`

CLI, construction and dependency injection, Uvicorn application factories,
development orchestration, settings composition, and process lifecycle.

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

Use Python entry points or explicit module paths. Plugins are limited to reviewed,
stable extension protocols; do not pluginize every internal strategy.

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

## Current layout versus target ownership

The repository still runs from root Python packages and repository-support
directories that predate this RFC. They are transitional, not alternative
permanent architecture. Existing behavior fixes should remain in the current
owner until a focused migration is approved; this table does not authorize
speculative target packages or file moves.

This mapping was audited against the current tree and the
[Phase A inventory](../package_migration_phase_a.md). Where one root package
mixes responsibilities, the final file-level destination requires a focused
migration audit rather than an invented one-to-one replacement.

| Current path | Current role | Target owner/package | Migration phase | Interim rule |
|---|---|---|---|---|
| `core` | Shared request, configuration, forwarding, tokenizer, model-calculation, and runtime-compatibility code | Split by proven semantics among `cacheroute.contracts`, `cacheroute.runtime`, relevant domains, and temporary `cacheroute.compat`; exact file ownership requires a focused audit | Phase 2, with compatibility cleanup in Phase 6 | Keep compatibility fixes in `core`; do not reproduce it as `cacheroute.core`. |
| `data` | Installed package containing dataset and knowledge-document material, YAML knowledge/configuration inputs, and a Python package marker; a focused audit must determine whether Python helpers are present or later added | Co-locate runtime package data with the canonical consuming package after a consumer and package-data audit; move proven reusable knowledge-domain Python behavior to `cacheroute.knowledge`; keep research datasets and repository artifacts outside the final wheel | Packaging audit in Phase 1; proven semantic Python movement in the applicable Phase 2 migration | Preserve current imports and data paths. Do not move or delete datasets without auditing runtime consumers, Docker/config paths, tests, package data, and documentation. Do not create `cacheroute.data`. |
| `doc` | Repository documentation currently listed with `doc.blog` and `doc.integrations` as transitional installed namespaces; it is not runtime Python architecture | Remain under repository `doc/`; remove `doc`, `doc.blog`, `doc.integrations`, and any other documentation namespace from the installed package list | Phase 1 packaging cleanup | Preserve Markdown links and explicitly exclude repository-only documentation subdirectories from namespace discovery where needed. Do not add `__init__.py`, package documentation in the final wheel, or solve discovery mismatches by adding documentation packages to `pyproject.toml`. |
| `scheduler` | Scheduler process, resource/knowledge registries, and selection strategies | `cacheroute.services.scheduler` for process state; `cacheroute.topology`, `cacheroute.knowledge`, and `cacheroute.routing` for reusable domain behavior | Phase 4 after prerequisite domain work | Preserve the root service and strategy interfaces until a Scheduler-specific migration PR audits all references. |
| `proxy` | Proxy process, queue state, resource reporting, metrics, and strategies | `cacheroute.services.proxy` for process state; `cacheroute.routing`, `cacheroute.topology`, and `cacheroute.observability` for proven reusable semantics | Phase 4 after prerequisite domain work | Apply compatible fixes at root; separate reusable policy only in an approved Proxy migration. |
| `instance` | Instance service, vLLM-facing control, prediction tools, Resource Agent, and dashboards | `cacheroute.services.instance` plus `cacheroute.integrations.vllm`; predictor, dashboard, and native-agent ownership requires focused audits | Phases 3–5 | Keep the root service intact; `crates/` placement for the Resource Agent remains only a proposal. |
| `kdn_server` | KDN service, contracts, domain models, gateways, databases, and CLI | `cacheroute.services.kdn`, `cacheroute.contracts.v1`, `cacheroute.runtime`, `cacheroute.knowledge`, `cacheroute.cache`, and reviewed integration adapters | Phases 2–4 | Preserve current wire behavior and root imports; migrate each responsibility only after its dependencies and references are audited. |
| `client` | Interactive client, performance workload client, task sets, and request tools | Production CLI/construction may belong to `cacheroute.entrypoints`; reusable or example ownership is not yet proven and requires a focused audit | Phase 1 or Phase 5, subject to audit | Keep `client/client.py` and `client/perf_client.py` working; do not pre-emptively package them as a service. |
| `store` | Knowledge-base construction, storage interfaces, and embedding helpers | Likely `cacheroute.knowledge` ports and `cacheroute.integrations.embeddings`, but file-level ownership requires a focused audit | Phases 2–3 | Maintain current imports and behavior until storage semantics and adapter boundaries are proven. |
| `model` | Model configuration and embedding implementation | `cacheroute.runtime` for runtime identity/configuration and `cacheroute.integrations.embeddings` for external implementation; exact split requires audit | Phases 2–3 | Keep runtime configuration data with its current consumer until package-data and references are audited. |
| `util` | Cross-cutting address, flag, timer, and KDN helper scripts | Each helper's owning domain, integration, entrypoint, or repository `scripts/`; no single target package | Relevant focused phase | Do not create a utility dumping ground; leave helpers in place until ownership is demonstrated. |
| `UI` | Client, KDN, and Proxy web assets and Python packages | Co-locate each asset set with the `cacheroute.services.*` package that serves it; client UI ownership requires audit | Phase 5 | Preserve current asset paths and package data until each serving application migrates. |
| `test` | Test suite and transitional demo launchers | Repository `tests/` and, where reviewed, `examples/` or `cacheroute.entrypoints.dev` | Phase 5 and final cleanup | Tests and demos remain outside the canonical wheel architecture; existing launchers may receive compatibility fixes. |
| `scripts` | Repository validation and operational scripts | Remain repository `scripts/`; production lifecycle behavior may move to `cacheroute.entrypoints` only after audit | Phase 1 or relevant focused phase | Do not install scripts as Python packages; preserve operational paths until replacements are validated. |
| `env` | Deployment configuration, Docker support, environment checks, and setup tools | Repository `env/`, not a Python wheel package; any runtime entrypoint extraction requires audit | Phase 1 or Phase 5 as applicable | Keep deployment files at root and out of the final wheel. |
| `log` | Checked-in experiment log material | Repository artifacts outside the wheel; long-term retention/location requires a focused data-governance audit | Phase 6 cleanup or separate audit | Do not import or package logs as application code; do not move research artifacts without review. |

Tests, documentation, repository scripts, deployment configuration under `env`,
logs, and generated files must not become wheel packages. UI assets are runtime
package data only when co-located with and declared by the service that serves
them.

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

Approve this RFC as the target architecture before implementation phases begin.

### Phase 1 — packaging and entrypoint boundary

Clean packaging so only canonical packages and approved compatibility shims enter the wheel. Add the unified CLI and application factories.

The first packaging-boundary step removes the repository-only `doc`, `env`,
`log`, `scripts`, and `test` namespaces (including their descendants) from the
wheel. Transitional root runtime packages remain explicitly installed until
their focused migrations; `data` remains installed pending a separate consumer
and package-data audit. This interim boundary does not authorize entrypoint or
service migration.

### Phase 2 — contracts and dependency-light domains

Move versioned contracts, Runtime Profile, lifecycle models, capability models, and topology/resource models.

The Phase 2 contract extraction gives `cacheroute.runtime` canonical ownership
of `RuntimeProfile` and `cacheroute.contracts.v1` ownership of all KDN v1 wire
contracts. The former `kdn_server.domain.RuntimeProfile` and
`kdn_server.contracts` common, error, knowledge, and cache-service module
surfaces remain temporary identity-preserving forwarding paths.

The remaining dependency-light state models now live in
`cacheroute.runtime.state`, `cacheroute.topology.lmcache`,
`cacheroute.cache.models`, and `cacheroute.routing.queue` according to their
domain ownership. `kdn_server.domain` remains an identity-preserving temporary
forwarding surface; KDN service and Gateway I/O implementations remain in their
transitional packages.

### Phase 3 — external integrations

Introduce vLLM, LMCache, Redis, and embedding integration boundaries.

### Phase 4 — services

Migrate KDN, Scheduler, Proxy, and Instance in separate reviewable PRs.

### Phase 5 — UI, development orchestration, and native components

Move UI assets to their owning service packages, replace test demos with entrypoints/examples, and review native components separately.

### Phase 6 — compatibility cleanup

Remove obsolete root runtime packages, source bootstraps, transition package lists, and expired compatibility shims.

## Architecture decision checklist

Use this checklist in every future architecture Issue and implementation PR:

- Is this a wire contract, domain model, adapter, service implementation, plugin protocol, or entrypoint?
- Which package owns the semantics?
- Does the proposed dependency follow the allowed direction?
- Does it import a framework or external SDK from a domain package?
- Is a compatibility shim required?
- What is the shim removal milestone?
- Which dynamic strings and operational paths must be audited?
- Does the clean wheel contain only approved packages?
- Can the feature import from outside the source checkout?

For a directory or service migration, the operational-path audit must cover
normal and dynamic imports; module and method strings; Uvicorn/FastAPI targets;
subprocess and `python -m` commands; Docker, Compose, CI, configuration, and
mounted paths; tests, fixtures, monkeypatch, and mock targets; packaging,
editable installs, and installed-wheel behavior; and every README and Markdown
relative link.

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
