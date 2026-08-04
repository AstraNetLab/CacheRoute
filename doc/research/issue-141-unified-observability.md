# Issue #141 observability research notes

The maintained Phase 4A design is documented in
[Observability v1](../architecture/observability-v1.md). These notes retain the
research conclusions relevant to later unified observability work.

The current Proxy compatibility metadata contains `trace`, `kv_ack`,
`kv_ready_kids`, `text_only_kids`, `miss_kids`, and `error`. It does not expose
the internal `ProxyTask.request_id`. Production compatibility output must remain
unchanged until a separately reviewed propagation contract exists.

Canonical `VersionedMessage` envelopes have a per-message `timestamp`.
Requests and Gateway responses are different messages and receive independent
timestamps; no shared `created_at` value should be inferred. Duration evidence
must use a monotonic clock rather than subtracting either timestamp.

Pydantic's `frozen=True` prevents field assignment but does not recursively
freeze dictionaries or lists. Canonical trace snapshots therefore use tuples
and frozen nested models and validate updates made through `model_copy`.

The implementation owner is `src/cacheroute/observability`, with stable schema
under its `v1` child. It directly reuses canonical `RuntimeProfile`,
`OutcomeCode`, error details, endpoint/Gateway profiles, and
`CacheOperationTask`/`CacheOperationType`. A root
`cacheroute_observability` package or `cacheroute.core` destination would split
ownership and is prohibited.

Legacy timings remain useful research input, but a projection must use a narrow
allow-list. Prediction fields that were overwritten or whose semantics are
ambiguous remain `legacy_projected`; they cannot be relabeled as actual. Raw
exceptions, payloads, cache bytes, adapter internals, and unknown trace keys are
not observability contract data.

Issue #182 adds the first narrow production path: authoritative internal
Scheduler headers are validated at the Proxy, where sampled prepare-queue,
ready-queue, and downstream transport stages become a process-local immutable
trace. The canonical trace still is not client metadata, Instance input, or an
authoritative account of vLLM or LMCache execution. This increment therefore
does not close the broader Issue #141 research program.
