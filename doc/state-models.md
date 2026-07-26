# Cache lifecycle and task state models

Issue #139 defines immutable, schema-version `"1"` mechanism contracts for CacheArtifact, CacheReplica, DataPlaneTask, and QueueWork. Policy engines may consume these objects, but policy is outside this contract.

## Wire values and purposes

| Object | Purpose | Values |
|---|---|---|
| Artifact | capability-specific knowledge materialization | `pending`, `building`, `staging`, `ready`, `failed`, `deleting`, `deleted` |
| Replica | data-plane placement of an Artifact | `pending`, `staging`, `ready`, `failed`, `evicting`, `deleted` |
| Replica health | observation independent of lifecycle | `unknown`, `healthy`, `degraded`, `unhealthy` |
| DataPlaneTask | data creation, movement, or removal work | `pending`, `queued`, `leased`, `running`, `succeeded`, `failed`, `cancelled`, `expired` |
| QueueWork | scheduler-local work | `pending`, `blocked`, `ready`, `queued`, `running`, `succeeded`, `failed`, `cancelled`, `skipped` |

## Complete transitions

| Lifecycle | Source | Targets |
|---|---|---|
| Artifact | pending | building, failed, deleting |
| Artifact | building | staging, failed, deleting |
| Artifact | staging | ready, failed, deleting |
| Artifact | ready | building, failed, deleting |
| Artifact | failed | building, deleting |
| Artifact | deleting | deleted, failed |
| Artifact | deleted | none |
| Replica | pending | staging, failed, evicting |
| Replica | staging | ready, failed, evicting |
| Replica | ready | staging, failed, evicting |
| Replica | failed | staging, evicting |
| Replica | evicting | deleted, failed |
| Replica | deleted | none |
| DataPlaneTask | pending | queued, cancelled |
| DataPlaneTask | queued | leased, running, cancelled, expired |
| DataPlaneTask | leased | running, queued, cancelled, expired |
| DataPlaneTask | running | succeeded, failed, cancelled |
| DataPlaneTask | failed | queued, cancelled |
| DataPlaneTask | succeeded, cancelled, expired | none |
| QueueWork | pending | blocked, ready, cancelled, skipped |
| QueueWork | blocked | ready, cancelled, skipped |
| QueueWork | ready | queued, running, cancelled, skipped |
| QueueWork | queued | running, cancelled |
| QueueWork | running | succeeded, failed, cancelled |
| QueueWork | failed | ready, cancelled, skipped |
| QueueWork | succeeded, cancelled, skipped | none |

Same-state transitions are idempotent. Terminal states are Artifact `deleted`, Replica `deleted`, DataPlaneTask `succeeded`/`cancelled`/`expired`, and QueueWork `succeeded`/`cancelled`/`skipped`. Every `failed` state is retryable and non-terminal.

Invalid transitions expose typed detail:

```json
{"code":"invalid_state_transition","entity_type":"cache_artifact","entity_id":"artifact:...","current_state":"deleted","target_state":"pending","allowed_targets":[],"reason":"terminal_state","terminal":true,"retryable":false}
```

## Stable IDs

Artifact IDs have format `artifact:sha256:<64 lowercase hex>` and hash canonical schema version, normalized knowledge ID, nullable capability fingerprint, and Artifact variant. The Legacy helper uses a null capability fingerprint. Replica IDs have format `replica:sha256:<64 lowercase hex>` and hash Artifact ID, nullable data-plane ID, nullable backend type, and nullable opaque non-secret location key. Generated IDs are `dpt:<32 lowercase UUID4 hex>` and `qwork:<32 lowercase UUID4 hex>`; restored non-empty IDs are accepted. Credentials, passwords, secret URLs, and raw Redis keys are not identity inputs.

## Legacy mapping

Compatibility is always `unknown`: Legacy metadata cannot establish capability compatibility. When checked, only `<kv_root>/<kid>` is authoritative; `kv_rel_dir` is validated metadata.

| kv_ready | Runtime directory | Artifact | Replica | Health | Warning |
|---|---|---|---|---|---|
| false | missing | pending | pending | unknown | none |
| false | exists | staging | staging | unknown | `legacy_files_without_ready_confirmation` |
| true | exists | ready | ready | healthy | none |
| true | missing | ready | failed | unhealthy | `legacy_replica_directory_missing` |
| true | not checked | ready | ready | unknown | none |

Non-empty `kv_rel_dir` unequal to `kid` adds `legacy_kv_rel_dir_mismatch`. Mapping changes neither SQLite nor files.

## Boundary and non-goals

This is lifecycle mechanism, not scheduling policy. Issue #139 does not add issue #140 protocol APIs, a persistent Artifact catalog, ExecutionGraph scheduling, routing/injection changes, database tables, or final operation and resource-class enums.
