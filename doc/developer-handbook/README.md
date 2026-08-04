# CacheRoute developer and maintenance handbook

This maintained manual is the stable entry point for developers, reviewers, and
Agents who change CacheRoute. It describes the checked-in implementation, its
transitional compatibility surface, and the accepted architecture without
turning proposals into facts.

## Development context

CacheRoute is migrating incrementally from installable root component packages
to responsibility-oriented packages under `src/cacheroute`. Canonical runtime,
topology, cache, routing, contracts, compatibility, and an empty observability
namespace exist today; the root services remain operational and transitional.
The accepted end state is detailed in the [package architecture RFC](../architecture/package-architecture-rfc.md).

## How to navigate

Start here, then read the chapter matching the surface you will change. Follow
source and focused-test links before relying on a statement. Component READMEs
remain the operational detail; this handbook connects them rather than copying
them.

## Chapter index

- [Architecture and evolution](architecture-and-evolution.md)
- [Package and module map](package-and-module-map.md)
- [Public API and data models](public-api-and-data-models.md)
- [Runtime flows](runtime-flows.md)
- [Configuration and interfaces](configuration-and-interfaces.md)
- [Compatibility and migrations](compatibility-and-migrations.md)
- [Development and validation](development-and-validation.md)
- [Documentation governance](documentation-governance.md)
- [Glossary](glossary.md)

## Documentation source-of-truth matrix

| Question | Detailed authority | Rule |
|---|---|---|
| Project introduction | [root README](../../README.md) | High-level project message only. |
| Accepted package architecture | [package architecture RFC](../architecture/package-architecture-rfc.md) | Accepted ownership and migration authority. |
| Developer navigation and API reference | [this handbook](README.md) | Maintained cross-component reference. |
| Component-specific operation | [Scheduler](../../scheduler/README.md), [Proxy](../../proxy/README.md), [Instance](../../instance/README.md), [KDN](../../kdn_server/README.md), and [Client](../../client/README.md) READMEs | Operational detail owned with the component. |
| Deployment and environment | [environment guide](../../env/README.md) and focused documents below `env/` | Installation and deployment truth. |
| Maintained architecture decisions | [`doc/architecture`](../architecture/) | Accepted decisions and boundaries. |
| Temporary research or unresolved investigation | `doc/research/` (when present) | Non-authoritative when superseded by maintained architecture. |
| Historical milestones | [`doc/blog`](../blog/) | Historical context, not current API authority. |
| Accepted but unimplemented work | Its GitHub Issue | Remains Issue authority until promoted into maintained documentation. |

Source plus focused tests are the implementation truth when prose disagrees.
Research notes are non-authoritative whenever a maintained architecture decision
supersedes them.

## Status legend

| Status | Meaning |
|---|---|
| **Historical** | Describes an earlier repository state, not supported current behavior. |
| **Current** | Present on the checked-in `main` implementation baseline. |
| **Transitional** | Present and supported while an accepted migration remains incomplete. |
| **Target / Accepted** | Approved architecture that may not yet be implemented. |
| **In review** | Implemented on an unmerged review branch, not current behavior. |
| **Proposed** | Suggested but not accepted or merged. |
| **Deprecated** | Supported temporarily with an approved removal direction. |

## Quick links

- Choose ownership: [package map](package-and-module-map.md)
- Use a supported import: [API catalog](public-api-and-data-models.md)
- Trace a request: [runtime flows](runtime-flows.md)
- Find a setting or endpoint: [configuration and interfaces](configuration-and-interfaces.md)
- Preserve an old import: [compatibility map](compatibility-and-migrations.md)
- Build and test: [development and validation](development-and-validation.md)
- Decide which docs to update: [documentation governance](documentation-governance.md)

## Update expectations

A PR that changes a documented API, field, default, validation rule, wire value,
configuration, endpoint, package boundary, compatibility path, runtime flow, or
validation command must update the owning chapter in the same PR. Keep one
detailed authority, link rather than duplicate, update only affected chapters,
and state handbook impact in the PR summary. See [AGENTS.md](../../AGENTS.md).
