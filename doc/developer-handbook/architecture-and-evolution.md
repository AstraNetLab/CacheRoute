# Architecture and evolution

[Back to handbook](README.md). Detailed authority: [package architecture RFC](../architecture/package-architecture-rfc.md); contribution constraints: [AGENTS.md](../../AGENTS.md).

## Three views

### Historical

CacheRoute began as component-oriented root packages (`scheduler`, `proxy`,
`instance`, `kdn_server`) plus shared `core`, `store`, `model`, `util`, clients,
and UI assets. Direct scripts and root imports formed the runtime and experiment
surface. The [engineering milestones](../blog/README.md) record context, not the
current API contract.

### Current transitional structure

The root Scheduler, Proxy, Instance, and KDN implementations still run because
moving a service safely requires an independent Issue and an audit of imports,
Uvicorn targets, subprocess commands, containers, tests, mocks, packaging, and
Markdown links. Existing behavior fixes therefore remain with their current
owner.

Packaging explicitly includes those root packages and canonical packages; it
does not use automatic discovery ([`pyproject.toml`](../../pyproject.toml)).
Completed foundation work provides **Current** `cacheroute.runtime`,
`topology`, `cache`, `routing`, `contracts.v1`, and `compat`. KDN contract and
domain paths forward to canonical objects, and `cacheroute_compat` remains a
**Deprecated** forwarding package. `cacheroute.observability` is **Current** as
an empty dependency-light namespace. Observability v1 from PR #179 is **In
review** because it is absent from this baseline; it is not a current runtime
flow.

### Accepted target

The RFC accepts one namespace under `src/cacheroute`: `contracts`, `runtime`,
`topology`, `knowledge`, `cache`, `routing`, `observability`, `integrations`,
`services`, `plugins`, `entrypoints`, and `compat`. Responsibilities and allowed
dependencies are summarized in the [package map](package-and-module-map.md).
The RFC, not this summary, is the detailed authority.

`knowledge`, `integrations`, `services`, `plugins`, and `entrypoints` do **not**
exist under `src/cacheroute` on this baseline. They are **Target / Accepted**,
not Current. Likewise, cache planning/runtime ports and most reusable routing
policies are accepted responsibilities, not proof of implementation.

## Evolution rules and phase state

Architecture guidance, explicit packaging cleanup, contract ownership, and the
dependency-light domain foundation have landed. External adapters, unified
entrypoints, and individual KDN/Scheduler/Proxy/Instance migrations remain
active or future focused work. The accepted sequence is recorded in the RFC;
GitHub Issues remain authoritative for accepted work not yet implemented.

A new functional top-level directory, service move, external integration, or
cross-component contract requires a focused architecture Issue and complete
reference audit. Do not create placeholders. Compatibility shims remain until
their stated milestone and tests permit removal. Relevant tracking context:
[#137](https://github.com/AstraNetLab/CacheRoute/issues/137),
[#157](https://github.com/AstraNetLab/CacheRoute/issues/157),
[#159](https://github.com/AstraNetLab/CacheRoute/issues/159), and
[#178](https://github.com/AstraNetLab/CacheRoute/issues/178).

## Phase summary on this baseline

| Phase view | Status | Baseline result / next boundary |
|---|---|---|
| Architecture guidance and boundaries | Current / completed foundation | Accepted RFC, AGENTS placement rules, governance and dependency checks. |
| Explicit packaging cleanup | Current / completed step | Repository-only docs/tests/env/scripts/log excluded; canonical and Transitional root runtime packages remain explicitly listed. Unified entrypoints are not yet implemented. |
| Contracts and dependency-light domain extraction | Current / completed foundation | Runtime Profile/state, topology endpoint, cache/queue models, canonical contracts v1 and identity-preserving KDN shims are present. This is model ownership, not full service wiring. |
| Observability Phase 4A / PR #179 | In review | Proposed v1 contracts, clocks, process-local collector and Legacy projection; no production instrumentation or cross-process propagation. |
| External integrations | Target / Accepted | Separate vLLM, LMCache, Redis and embeddings adapters follow domain ports; packages are absent today. |
| Service migrations | Target / Accepted future sequence | Migrate KDN, Scheduler, Proxy and Instance in separate focused PRs after prerequisite domains/integrations and full reference audits. |
| UI/orchestration/data/native review | Target / Accepted future | Co-locate owned assets, replace demo lifecycle where validated, audit package data and native Resource Agent independently. `crates/` placement remains Proposed until focused approval. |
| Transitional cleanup | Target / Accepted final | Remove root runtime packages, direct-source bootstraps, explicit transition list and expired shims only after installed-wheel and compatibility proof. |

The sequence is deliberately incremental: complete the domain/integration
prerequisites, migrate one service at a time, then remove compatibility paths.
An Issue or open PR changes status to In review/Proposed, not Current.
