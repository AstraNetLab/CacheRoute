# Cache and Execution State Models

This document defines the v0.1.10 shared, serialized mechanism for cache lifecycle and execution state. It does not activate a catalog, data-plane protocol, task registry, execution graph, routing change, or scheduling/maintenance policy.

## Objects and IDs

| Object | Purpose | ID rule |
|---|---|---|
| `CacheArtifact` | A model/runtime-specific reusable cache artifact for one knowledge object and variant. | `artifact:sha256:<64 hex>` over compact, key-sorted JSON containing schema version, normalized knowledge ID, capability fingerprint, and artifact variant. The Legacy helper records a null fingerprint; it never invents compatibility data. |
| `CacheReplica` | One physical/logical placement of an Artifact, with lifecycle and health kept separate. | `replica:sha256:<64 hex>` over Artifact ID, data-plane ID, backend type, and an opaque non-secret location key. Credentials and backend-internal Redis keys must not be location identities. |
| `DataPlaneTask` | A future data-plane execution request without a finalized operation enum. | `dpt:<32 lowercase UUID4 hex>`. A restored non-empty external ID is also accepted. |
| `QueueWork` | A future schedulable work item without dependency or priority policy. | `qwork:<32 lowercase UUID4 hex>`. A restored non-empty external ID is also accepted. |

Canonical JSON uses sorted keys, compact separators, UTF-8, and schema version `"1"`. Changing any identity input changes its deterministic hash. All models reject extra fields.

## Artifact lifecycle

Wire values are `pending`, `building`, `staging`, `ready`, `failed`, `deleting`, and `deleted`.

| Current | Allowed targets |
|---|---|
| pending | building, deleting, failed |
| building | deleting, failed, staging |
| staging | deleting, failed, ready |
| ready | building, deleting, failed |
| failed | building, deleting |
| deleting | deleted, failed |
| deleted | none |

`deleted` is terminal. `failed` is retryable. `ready` is not terminal because refresh, invalidation, and deletion remain possible.

## Replica lifecycle and health

Replica wire values are `pending`, `staging`, `ready`, `failed`, `evicting`, and `deleted`.

| Current | Allowed targets |
|---|---|
| pending | evicting, failed, staging |
| staging | evicting, failed, ready |
| ready | evicting, failed, staging |
| failed | evicting, staging |
| evicting | deleted, failed |
| deleted | none |

`deleted` is terminal and `failed` is retryable. Health has the independent wire values `unknown`, `healthy`, `degraded`, and `unhealthy`. For example, a ready Replica can be degraded, and an Artifact can remain ready when one known Replica fails. These values do not prescribe maintenance action.

## Data-plane task lifecycle

Wire values are `pending`, `queued`, `leased`, `running`, `succeeded`, `failed`, `cancelled`, and `expired`.

| Current | Allowed targets |
|---|---|
| pending | cancelled, queued |
| queued | cancelled, expired, leased, running |
| leased | cancelled, expired, queued, running |
| running | cancelled, failed, succeeded |
| failed | cancelled, queued |
| succeeded | none |
| cancelled | none |
| expired | none |

`succeeded`, `cancelled`, and `expired` are terminal. `failed` is retryable and non-terminal. Retry attempt and lease policies are intentionally undefined.

## Queue work lifecycle

Wire values are `pending`, `blocked`, `ready`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, and `skipped`.

`pending` means dependency evaluation is incomplete; `blocked` waits for dependencies; `ready` is schedulable; `queued` is admitted to a concrete resource; and `running` has begun execution.

| Current | Allowed targets |
|---|---|
| pending | blocked, cancelled, ready, skipped |
| blocked | cancelled, ready, skipped |
| ready | cancelled, queued, running, skipped |
| queued | cancelled, running |
| running | cancelled, failed, succeeded |
| failed | cancelled, ready, skipped |
| succeeded | none |
| cancelled | none |
| skipped | none |

`succeeded`, `cancelled`, and `skipped` are terminal. `failed` is retryable and non-terminal. Dependency graphs, resource admission, ordering, and retry policy remain separate from this mechanism.

## Transition behavior and errors

Every same-state transition succeeds idempotently with `changed: false`. Other allowed transitions return a new model copy and `changed: true`; the original model is not mutated. Allowed targets are always sorted in machine-readable output.

An invalid transition raises `InvalidStateTransition` with a typed detail such as:

```json
{
  "code": "invalid_state_transition",
  "entity_type": "artifact",
  "entity_id": "artifact:sha256:...",
  "current_state": "ready",
  "target_state": "pending",
  "allowed_targets": ["building", "deleting", "failed"],
  "reason": "transition_not_allowed",
  "terminal": false,
  "retryable": false
}
```

A transition away from a terminal state uses `reason: "terminal_state"`.

## Legacy `kv_ready` adapter

The adapter is a read-only projection. It does not migrate SQLite, alter `mark_kv_ready`, or change `KV_database/<kid>`.

| `kv_ready` | Directory check | Artifact | Replica | Health | Warning |
|---|---|---|---|---|---|
| false | missing | pending | pending | unknown | none |
| false | exists | staging | staging | unknown | `legacy_files_without_ready_confirmation` |
| true | exists | ready | ready | healthy | none |
| true | missing | ready | failed | unhealthy | `legacy_replica_directory_missing` |
| true | not performed | ready | ready | unknown | none |

Boolean values and integer/string `0` and `1` are normalized explicitly; other values fail. The filesystem wrapper resolves the location below the configured KV root and rejects path escape. Legacy compatibility is always `unknown`, because historical rows lack the complete Instance capability fingerprint.

## Explicit non-goals

Issue #139 does not implement persistent Artifact/Replica tables, a KDN task registry, data-plane endpoints or submission protocol, leases, idempotency, a production worker, ExecutionGraph scheduling, queue priorities, retry/eviction policy, trace schema, placement, or routing. Existing Proxy queues and `kv_ready` classification remain active and unchanged. Issue #140 can build a versioned protocol and operation categories on this state contract; policy work must continue to treat lifecycle state as mechanism rather than a decision rule.
