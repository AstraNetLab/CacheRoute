# Glossary

| Term | Definition | Status |
|---|---|---|
| Runtime Profile | Canonical runtime compatibility selector: `legacy`, `v1`, `test/mock`, with `auto` startup-only. | Current |
| legacy | Compatibility runtime for pre-v1 behavior and projections. | Transitional |
| v1 | Canonical dependency-light contract/runtime profile. | Current |
| test/mock | Runtime profile for tests or mock adapters. | Current |
| KDN | Knowledge Delivery Network service that manages knowledge and KVCache-related assets. | Current / Transitional |
| knowledge ID | Stable identifier for registered knowledge content, often called `kid` in legacy paths. | Current |
| artifact ID | Canonical `artifact_<32 hex>` cache artifact identifier. | Current |
| endpoint ID and endpoint generation | Canonical endpoint identity `endpoint_<32 hex>` plus generation; generation zero is Legacy-only where allowed. | Current |
| compatibility profile | Identifier describing model/tokenizer/cache compatibility for safe reuse. | Current |
| CacheOperationTask and task ID | Cache operation model and `cacheop_<32 hex>` task identifier. | Current |
| trace ID | `trace_<32 hex>` observability trace identifier. | Current |
| request ID | Request identifier; Scheduler owns the authoritative internal request ID for Scheduler-to-Proxy propagation. | Current |
| correlation ID | Optional cross-request correlation label. | Current |
| stage ID | Safe identifier for a trace stage. | Current |
| operation ID | Cache operation identifier, usually `cacheop_<32 hex>`. | Current |
| injection mode | Request mode such as `text`, `kvcache`, or `hybrid`. | Current |
| predicted | Value kind representing model-estimated data. | Current |
| desired | Value kind representing intended state. | Current |
| observed | Value kind representing observed runtime state. | Current |
| measured | Value kind representing measured data. | Current |
| actual | Value kind representing actual chosen path or result. | Current |
| inferred | Value kind representing inferred data. | Current |
| legacy_projected | Value kind or flag for data projected from legacy sources. | Transitional |
| public | Supported surface documented for external or cross-component use. | Current |
| canonical | Long-term owner under approved package architecture. | Target / Accepted or Current |
| transitional | Current compatibility implementation retained during migration. | Transitional |
| compatibility | Behavior kept to preserve imports, wire values, or operational workflows. | Transitional |
| deprecated | Supported only until an approved removal milestone. | Deprecated |
| proposed | Not accepted or not implemented current behavior. | Proposed |
