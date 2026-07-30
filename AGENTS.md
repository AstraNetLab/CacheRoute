# AGENTS.md

author: heyao
version-date: 26-07-30

## 1. Project Overview

This repository implements a CacheRoute-style scheduling system for LLM serving experiments.

The system currently revolves around the following roles:

- **Scheduler**: the central control plane that selects target Proxy/KDN resources and builds requests.
- **Proxy**: executes or forwards requests, maintains runtime load information, and interacts with the scheduler.
- **KDN**: manages knowledge-related assets such as text chunks, KVCache, embeddings, and resource status.
- **Client / Perf Client**: generates workloads for testing and benchmarking.

The project is actively evolving. The current focus is not “general cleanup”, but **supporting research-driven scheduling strategies and controlled experiments**.

Codex should optimize for:
- correctness,
- incremental change,
- observability,
- reproducible experiments,
- and preserving existing behavior unless explicitly asked to change it.

### 1.2 Architecture Overview

Typical task flow:

client
  ↓
scheduler
  ↓
proxy
  ↓
instance
  ↓
vLLM engine

KDN provides knowledge resources used during scheduling
and request preparation.

Scheduler maintains resource pools for:
- proxies
- KDN nodes

### 1.3 CacheRoute Strategy Development Area

The current compatibility implementations of scheduling strategies are under:

`scheduler/strategy/`
`proxy/strategy/`

Strategies must not modify core scheduler logic.
They should operate through the existing selection interfaces.
Compatibility-preserving fixes may continue in these root modules. New reusable
strategy code belongs to `cacheroute.routing` once its focused migration phase
is approved; do not create empty target packages in anticipation of that work.

Example strategies include:
- round_robin
- load_based
- knowledge_aware
- hybrid_injection_policy

---

## 2. Current Research Direction

This repository is being extended for **strategy development under different task injection modes**.

The main task modes currently relevant are:

- **text**: send text directly for normal computation / recomputation.
- **kvcache**: inject KVCache-related information into the workflow.
- **hybrid**: mixed mode, e.g. alternating or ratio-based combinations of text and kvcache tasks.

The near-term research goal is to support **decision-making between KVCache injection and text-recomputation dynamically**, based on:
- queue state,
- network cost,
- compute cost,
- and resource availability.

When modifying code, prefer solutions that help future policy design, especially:
- measurable timing breakdowns,
- explicit request metadata,
- stable task typing,
- and resource-state visibility.

---

## 3. Engineering Priorities

When making changes, follow these priorities in order:

1. **Do not break the existing experiment flow.**
2. **Prefer incremental modifications over broad refactors.**
3. **Preserve existing public behavior unless the task explicitly requires changes.**
4. **Expose useful logs / debug status for validation.**
5. **Keep code easy to reason about for later paper-oriented modeling.**

Do **not** do the following unless explicitly requested:
- rewrite large modules,
- rename core concepts casually,
- move many files at once,
- introduce new abstractions without clear payoff,
- silently change request field semantics,
- remove debug outputs that are useful for experiments.

---

## 4. Expected Coding Style

### General
- Use **small, local, incremental patches**.
- Keep the original project structure unless there is a strong reason not to.
- Prefer **clear active-voice comments** over decorative comments.
- Avoid clever but opaque designs.

### Python style
- Preserve the repository’s existing style where possible.
- Add type hints when they improve clarity, but do not over-engineer typing.
- Keep functions focused and readable.
- Avoid introducing unnecessary framework-level indirection.

### Logging / Observability
- Add logs only when they help validate runtime behavior.
- Prefer logs that answer questions like:
  - which task was selected,
  - which injection type was used,
  - how long each phase took,
  - which proxy/KDN was chosen,
  - what resource/load snapshot was used.

Avoid noisy per-step logs unless explicitly requested. Favor **task-level summary logs**.

---

## 5. Change Strategy for Codex

When implementing a request, Codex should usually follow this workflow:

1. **Read the relevant files first.**
2. **Infer the minimum viable change set.**
3. **Modify only the files needed for that change.**
4. **Explain the patch in a file-by-file manner.**
5. **State how to verify the change.**
6. **Call out assumptions explicitly if code context is incomplete.**

For non-trivial changes, the preferred response format is:

- **What to change**
- **Why this is the minimal correct change**
- **Exact code patch**
- **How to validate**
- **What may break / edge cases**

---

## 6. Validation Expectations

Every meaningful code change should be easy to validate.

Codex should prefer adding or preserving validation hooks such as:
- debug endpoints,
- CLI-visible status,
- task-level timing output,
- resource pool snapshots,
- counters for success/failure events,
- explicit request field dumps in controlled logs.

When proposing changes, always include:
- where to run,
- what to send,
- what output is expected,
- what would indicate failure.

Do not stop at “the code compiles”. Runtime validation matters.

---

## 7. Important Domain Conventions

### 7.1 Injection type
A request may carry an `Injection_type` field.
If absent, default behavior should remain compatible with the current system expectation (currently usually `kvcache`, unless the target code path says otherwise).

Supported modes may include:
- `kvcache`
- `text`
- `hybrid`

Do not hard-code new mode semantics in many places. Centralize branching logic where practical.

### 7.2 Hybrid mode
Hybrid mode may be ratio-driven rather than a fixed pattern.
For example:
- 2 KVCache + 1 text
- 3 KVCache + 1 text

When implementing hybrid logic, favor parameterized behavior over one-off hardcoding.

### 7.3 Timing model relevance
Some timing fields are not just operational metrics; they are research data.
Preserve or improve the ability to separate:
- proxy queue time,
- waiting time,
- knowledge acquisition time,
- network-related delay,
- actual compute/prefill time.

Avoid collapsing these phases if they are currently distinguishable.

### 7.4 Resource pools
Scheduler decisions may depend on resource pools rather than transient heartbeat payloads alone.
If a load metric is already maintained in a pool object, prefer reading from the maintained state instead of reconstructing it elsewhere.

---

## 8. KDN / Knowledge-Related Expectations

KDN-related data may include:
- text registration,
- KVCache readiness,
- embeddings,
- status fields such as `kv_ready`,
- knowledge identifiers (`kid`),
- and resource visibility from scheduler/CLI.

When changing KDN paths:
- do not assume registration means all derived states are already consistent,
- do not silently skip re-registration logic if the experimental workflow requires overwrite/refresh,
- keep status observability available for debugging.

If a change affects knowledge registration or scheduler-KDN interaction, include explicit validation steps.

---

## 9. Performance Experiment Expectations

This codebase is used for controlled experiments, not only production-style serving.

Therefore, Codex should prefer features that support:
- reproducible workload generation,
- JSON-driven workloads,
- concise per-task performance summaries,
- average / min / max statistics when useful,
- and low-friction experimentation across injection modes.

For client-side or perf tooling:
- avoid burying important metrics in overly verbose logs,
- prefer one-line-per-task summaries plus aggregate statistics.

---

## 10. Backward Compatibility Rules

Unless explicitly requested otherwise:

- keep existing request formats working,
- keep existing CLI/debug workflows usable,
- keep current default values stable,
- avoid changing field names already used by scheduler/proxy/client,
- and avoid changing wire semantics without documenting them.

If a backward-incompatible change is unavoidable, clearly mark:
- old behavior,
- new behavior,
- migration points,
- and the minimal files that must be updated together.

---

## 11. What Codex Should Do When Context Is Incomplete

If the requested change depends on files or symbols not yet inspected:

- do not invent repository structure,
- do not fabricate function names,
- do not pretend a patch is exact if it is only conceptual.

Instead:
- say which file(s) must be inspected,
- give a likely patch location,
- and separate **confirmed changes** from **assumption-based suggestions**.

Accuracy is more important than sounding complete.

---

## 12. Preferred Response Style for This Repository

When assisting with code changes in this repo, prefer:

- concrete edits,
- exact insertion points,
- minimal diffs,
- explicit reasoning,
- and validation commands/examples.

Avoid:
- generic architecture lectures,
- unnecessary abstraction proposals,
- large speculative rewrites,
- or answers that ignore the current code state.

The user typically prefers **incremental, directly actionable code guidance**.

---

## 13. If You Add New Code

No new functional top-level directory may be added without a dedicated architecture Issue. Fix existing behavior in its current owning component hierarchy. New cross-component contracts and domain capabilities must follow the approved `cacheroute.*` ownership list in Section 18 and remain dependency-light and side-effect-free. Do not create speculative or empty target packages before their focused implementation or migration work is approved.

When introducing a new helper, field, or branch:
- keep naming consistent with existing repository terms,
- add comments for non-obvious logic,
- avoid spreading one new concept across many files unless necessary,
- and ensure logs/debug outputs make the new behavior observable.

If adding config/arguments:
- use existing configuration style where possible,
- document defaults,
- and make the feature easy to disable.

---

## 14. Key Files / Entry Points

The exact current paths below are important transitional compatibility locations. Prefer editing existing behavior in place instead of introducing parallel logic; they are not permanent package-placement guidance.

- `scheduler/...`: request building, scheduling decisions, resource selection
- `proxy/...`: request execution path, runtime load updates, queue behavior
- `kdn_server/...`: knowledge registration, status fields, embedding / KVCache readiness
- `instance/...`: interact layer between proxy and vLLM engine.
- `client/client.py`: single-request testing path
- `client/perf_client.py`: workload generation and benchmark execution
- `test/demo_kdn.py`, `test/demo_scheduler.py`, `test/demo_proxy.py`, `test/demo_instance.py`, `test/demo_client.py`: transitional test/demo launchers only; do not place business logic here

Existing Scheduler, Proxy, Instance, and KDN service code remains in
`scheduler/`, `proxy/`, `instance/`, and `kdn_server/` until separate, focused
migration PRs are approved. Section 18 governs all new package placement and
all migration decisions.

---

## 15. Do Not Disturb Without Explicit Request

Unless explicitly requested, do not redesign:
- scheduler/proxy/KDN role boundaries
- existing request wire format
- client/perf_client invocation style
- current CLI/debug interfaces
- default injection behavior

---

## 16. Preferred Patch Delivery Format

For code assistance, prefer:
1. exact target file
2. exact function/class location
3. minimal patch
4. explanation of why this location is correct
5. validation steps

Do not provide only high-level pseudocode when the code context is already available.

---

## 17. Summary

This repository is a research-driven scheduling/serving system under active iteration.

The most helpful contributions are:
- precise incremental patches,
- stable semantics,
- strong observability,
- and implementation choices that support future scheduling strategy research.

When in doubt, choose:
**minimal change + clear validation + preserved compatibility**.

---

## 18. Target Package Architecture and Placement Rules

This section is authoritative for all new package placement and migration work. It takes precedence over older current-layout examples in Sections 1–17. Existing root packages such as `scheduler/`, `proxy/`, `instance/`, and `kdn_server/` are transitional compatibility locations until their separate reviewed migration phases are complete.

The governing architecture is:

- Issue #159: package architecture RFC;
- Issue #157: migration Epic;
- `doc/architecture/package-architecture-rfc.md`: maintained repository architecture document.

Do not begin a broad package move unless the relevant phase of #157 has an approved, focused Issue and a complete reference audit.

Use this decision rule:

- **Existing behavior fix**: edit the current owning module with the smallest compatible patch.
- **New cross-component contract/domain capability**: place it according to the approved `cacheroute.*` ownership boundaries below.
- **Directory or service migration**: require a focused Issue and complete reference audit before moving files.

These rules do not authorize speculative target directories or placeholder
packages. Create a canonical package only as part of its approved, substantive
implementation or focused migration work.

### 18.1 Canonical Python namespace

All long-term Python implementation belongs under `src/cacheroute/`.

The approved top-level package responsibilities are:

```text
cacheroute.contracts
cacheroute.runtime
cacheroute.topology
cacheroute.knowledge
cacheroute.cache
cacheroute.routing
cacheroute.observability
cacheroute.integrations
cacheroute.services
cacheroute.plugins
cacheroute.entrypoints
cacheroute.compat
```

Do not create a generic `cacheroute.core` package. A module that cannot be assigned to one of the approved responsibilities needs an architecture decision before implementation.

Do not create new root packages such as `cacheroute_<feature>`.

### 18.2 Package ownership

#### `contracts`

Owns versioned, JSON-serializable, cross-process schemas and wire enums.

It must not import FastAPI, Redis, Torch, vLLM, LMCache, or service implementations.

#### `runtime`

Owns Runtime Profile, model/tokenizer/KV-layout identity, capability fingerprints, and shared lifecycle concepts.

#### `topology`

Owns registration, health, endpoint generation, resource snapshots, and cluster topology.

#### `knowledge`

Owns knowledge descriptors, semantic resolution, indexing abstractions, and repository ports.

#### `cache`

Owns cache artifact models, compatibility evaluation, CachePlan/FusionPlan, cache operations, and Cache Runtime ports.

It must not directly implement LMCache, Redis, or vLLM operations.

#### `routing`

Owns admission, queueing, endpoint selection, load models, and reusable routing policies.

Reusable routing code must not depend on FastAPI applications or process-global Proxy/Scheduler state.

#### `observability`

Owns dependency-light trace contracts, clocks, collectors, events, exporters, and Legacy projections.

#### `integrations`

Owns external-system-specific adapters. Initial approved subpackages are:

```text
cacheroute.integrations.vllm
cacheroute.integrations.lmcache
cacheroute.integrations.redis
cacheroute.integrations.embeddings
```

Domain packages must not import `integrations`.

#### `services`

Owns deployable process implementations:

```text
cacheroute.services.scheduler
cacheroute.services.proxy
cacheroute.services.instance
cacheroute.services.kdn
```

A service may use contracts and domain packages. It must not import another service's internal modules.

#### `entrypoints`

Owns CLI commands, Uvicorn application factories, development orchestration, settings composition, dependency injection, and process lifecycle.

The long-term command surface is:

```text
cacheroute scheduler
cacheroute proxy
cacheroute instance
cacheroute kdn
cacheroute dev
```

Direct scripts under tests are not production entrypoints. Existing demo scripts may remain only as temporary wrappers while replacement entrypoints are validated.

#### `plugins`

Owns stable extension protocols and discovery for Cache Runtime Gateways, runtime/engine connectors, and observability exporters.

Use Python entry points or explicit module paths. Do not make every internal strategy a plugin without a separate design need.

#### `compat`

Owns temporary import and wire compatibility only. It must contain no permanent business implementation. Every shim needs tests and an explicit removal milestone.

### 18.3 External integration boundaries

#### vLLM

All vLLM-specific behavior belongs in `cacheroute.integrations.vllm`.

Keep these concerns separate:

- scheduler-side external KV lookup and connector metadata;
- worker-side KV materialization;
- capability discovery;
- hit-token and remote-read observations;
- connector failure mapping and recomputation policy.

Prefer public KVConnector interfaces over private model-runner details.

#### LMCache

All LMCache-specific behavior belongs in `cacheroute.integrations.lmcache` and implements CacheRoute-owned Cache Runtime ports.

Keep these concerns separate:

- capability and profile discovery;
- lookup and operation submission;
- asynchronous operation status;
- pin, unpin, clear, prefetch, and rebuild requests;
- events and metrics;
- endpoint generation and freshness.

Do not mirror or maintain an authoritative copy of LMCache's physical L1/L2 block index.

#### Legacy Redis

Legacy Redis scan, dump, restore, and injection behavior is an adapter implementation under `cacheroute.integrations.redis`, not the canonical cache domain.

Legacy wire values and behavior must remain explicit and tested during migration.

### 18.4 Dependency direction

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

Forbidden dependencies include:

- contracts importing services;
- domain packages importing FastAPI or external runtime/storage SDKs;
- service packages importing another service's internal modules;
- KDN domain logic importing LMCache or Redis directly;
- vLLM adapters importing Instance service internals;
- reusable routing policy importing Proxy application state.

When a required call appears to violate this direction, define or reuse a domain Port and inject an adapter from an entrypoint.

### 18.5 Repository and wheel layout

The long-term repository categories are:

```text
src/cacheroute/
tests/
examples/
doc/
scripts/
env/
crates/
```

`crates/` is reserved for independently built native components such as the Resource Agent and requires a focused migration review.

The final Python wheel must contain only the `cacheroute` namespace and explicitly approved temporary compatibility shims.

The following categories must not be installed as Python packages:

- tests;
- documentation;
- scripts;
- deployment configuration;
- logs;
- generated data.

Runtime package data must be stored with and declared by the package that consumes it.

The root README remains a high-level project overview. Detailed package architecture belongs under `doc/architecture/`.

### 18.6 Versioning

Version compatibility boundaries rather than the entire implementation tree.

Preferred examples:

```text
cacheroute.contracts.v1
cacheroute.integrations.vllm.connector_v1
cache artifact schema versions
observability schema versions
```

Do not place the entire project under `cacheroute.v1`.

### 18.7 Migration mapping

Use the following ownership map when planning focused migration Issues:

- `kdn_server/contracts` -> `cacheroute.contracts.v1`;
- shared KDN domain concepts -> `runtime`, `knowledge`, and `cache`;
- `kdn_server/gateway` -> `integrations.lmcache` and `integrations.redis`;
- Scheduler and Proxy reusable strategies -> `routing` once the focused migration phase is approved; existing root strategy modules remain available for compatibility-preserving fixes;
- Scheduler and Proxy registries -> `topology`;
- reusable Proxy queue policy -> `routing`, while process queue state remains in `services.proxy`;
- Instance vLLM discovery -> `integrations.vllm`;
- embedding implementation -> `integrations.embeddings`;
- UI assets -> their owning service package;
- demo launchers -> `entrypoints.dev` or `examples`;
- generic `util` helpers -> their owning domain after a focused ownership audit; do not preserve a utility dumping ground.

Until their separate service migrations are approved, Scheduler, Proxy,
Instance, and KDN implementations remain in the transitional `scheduler/`,
`proxy/`, `instance/`, and `kdn_server/` root packages.

### 18.8 Migration phases

Follow the #157 phases. Do not combine them into a repository-wide move.

1. Architecture guidance and automated boundaries.
2. Packaging cleanup and unified entrypoints.
3. Contracts and dependency-light domain extraction.
4. External integrations.
5. KDN, Scheduler, Proxy, and Instance service migrations in separate PRs.
6. UI, development orchestration, package data, and native-component review.
7. Removal of root runtime packages, direct-source bootstraps, transition package lists, and expired shims.

Before any directory migration, audit and update:

- normal and dynamic imports;
- method, class, and module strings;
- Uvicorn/FastAPI application targets;
- subprocess and `python -m` commands;
- Docker, Compose, CI, configuration, and mounted paths;
- tests, fixtures, monkeypatch, and mock targets;
- packaging, editable install, and wheel install;
- every README and Markdown relative link.

### 18.9 Architecture validation

Architecture-related changes should add or preserve checks for:

- forbidden dependency directions;
- dependency-light fresh-process imports;
- no service-to-service internal imports;
- no external SDK imports from domain packages;
- wheel top-level package allowlists;
- console entrypoint and application-factory smoke tests;
- dynamic plugin loading;
- stale import and module-string references;
- local Markdown links;
- clean editable and wheel installation.

A migration is not complete merely because imports work from the repository root. It must also work from an installed wheel outside the checkout.
