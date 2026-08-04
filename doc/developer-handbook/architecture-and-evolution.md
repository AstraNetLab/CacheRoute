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
