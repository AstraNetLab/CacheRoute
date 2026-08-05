# CacheRoute Developer and Maintenance Handbook

Status: Current developer navigation for CacheRoute maintainers.

## Intended readers

This handbook is for maintainers, contributors, and review agents who need to change CacheRoute without changing undocumented public or structural behavior accidentally.

## How to use this handbook

Start here, then read the chapter that owns the surface you are changing. Keep one detailed source of truth for each topic and link to it rather than copying large maintained documents.

## Current development context

CacheRoute is in a Transitional repository state: root packages still run the historical Scheduler, Proxy, Instance, KDN, Client, UI, and utility components, while dependency-light canonical foundations live under `src/cacheroute/`. PR #183 observability propagation and Proxy-local stage collection are Current. Broader Issue #141 observability remains incomplete.

## Chapter index

- [Architecture and evolution](architecture-and-evolution.md)
- [Package and module map](package-and-module-map.md)
- [Public API and data-model catalog](public-api-and-data-models.md)
- [Runtime flows](runtime-flows.md)
- [Configuration and interfaces](configuration-and-interfaces.md)
- [Compatibility and migrations](compatibility-and-migrations.md)
- [Development and validation](development-and-validation.md)
- [Documentation governance](documentation-governance.md)
- [Glossary](glossary.md)

## Status legend

| Status | Meaning |
|---|---|
| Historical | Previously important context that should not be treated as a current target. |
| Current | Implemented in the repository and validated by source or tests. |
| Transitional | Implemented compatibility behavior that remains while migration continues. |
| Target / Accepted | Accepted direction that may not be fully implemented yet. |
| Proposed | Investigatory or roadmap material that is not accepted current behavior. |
| Deprecated | Supported only for compatibility and expected to be removed after an approved milestone. |

## Source-of-truth matrix

| Source | Scope | Authority |
|---|---|---|
| [Root README](../../README.md) | High-level project introduction, quick start, component links. | Current overview only. |
| [Package architecture RFC](../architecture/package-architecture-rfc.md) | Ownership boundaries and dependency direction. | Maintained architecture source. |
| [Observability v1](../architecture/observability-v1.md) | Maintained observability design and schema intent. | Maintained design source. |
| Developer handbook | Navigation and summarized developer reference. | Summary; link to detailed owners. |
| Component READMEs | Focused operational behavior for root components. | Current component operations where source agrees. |
| [Environment documentation](../../env/README.md) | Environment and deployment setup. | Deployment source of truth. |
| Research documents | Temporary investigation and design notes. | Non-authoritative when a maintained architecture document owns the same subject. |
| Blog documents | Historical milestones and changelog notes. | Historical context. |
| Approved GitHub Issues | Accepted but not implemented design. | Target / Accepted until source and tests implement it. |

## Quick links for common maintenance tasks

| Task | Read first |
|---|---|
| Change package ownership or dependency direction | [Package and module map](package-and-module-map.md), [Package architecture RFC](../architecture/package-architecture-rfc.md) |
| Change public models, enums, or imports | [Public API and data-model catalog](public-api-and-data-models.md) |
| Change request flow, headers, queues, or observability stages | [Runtime flows](runtime-flows.md) |
| Change CLI, environment variables, endpoints, or request fields | [Configuration and interfaces](configuration-and-interfaces.md) |
| Change shims or migration state | [Compatibility and migrations](compatibility-and-migrations.md) |
| Prepare PR evidence | [Development and validation](development-and-validation.md) |

## Update expectations

Update the relevant handbook chapter in the same PR when a documented public or structural surface changes. Keep root README changes minimal. Do not describe unmerged or absent features as Current.
