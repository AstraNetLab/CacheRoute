# CPU-only KDN contract and Gateway workflows

[Back to the KDN architecture](../../kdn_server/README.md) · [Contract reference](../../kdn_server/contracts/README.md) · [Gateway reference](../../kdn_server/gateway/README.md) · [Domain reference](../../kdn_server/domain/README.md)

These tests validate control-plane contracts and adapter behavior without a network, Redis, filesystem cache, GPU, vLLM, or LMCache runtime.

## Test groups

- [`test_domain_models.py`](test_domain_models.py) checks canonical identities, observation freshness/provenance, Legacy projection, and task/queue transitions.
- Runtime/Profile compatibility tests cover startup resolution and explicit v1, Legacy, and test/mock isolation.
- [`test_cache_service_contracts.py`](test_cache_service_contracts.py) checks every Cache Service family, serialization, negotiation, capability gates, and dedicated response invariants.
- The same contract suite executes deterministic Mock and read-only Legacy workflows, including idempotency, lifecycle, cancellation, stale and incompatible targets, and fallback.
- Parameterized security tests prove contracts reject secrets and physical cache representations.

## Executable workflow

The authoritative executable workflow is [`test_cache_service_contracts.py`](test_cache_service_contracts.py). The following setup is a minimal interactive starting point using non-routable logical identities:

```python
from kdn_server.contracts import GetLMCacheEndpointsRequest
from kdn_server.gateway import (
    CapabilitySnapshot, GatewayAdapterBinding, LMCacheCompatibilityProfile,
    MockGateway,
)

profile = LMCacheCompatibilityProfile(
    compatibility_profile_id="example-compatible-v1",
    key_hash_profile="sha256-v1",
)
snapshot = CapabilitySnapshot(
    runtime_profile="test/mock",
    adapter_bindings=(GatewayAdapterBinding(
        transport_kind="mock", binding_id="local-fixture"),),
    compatibility_profile=profile,
    endpoint_id="endpoint_" + "1" * 32,
    endpoint_generation=1,
    source="cpu-test",
)
gateway = MockGateway(snapshot)
response = gateway.get_endpoints(
    GetLMCacheEndpointsRequest(runtime_profile="test/mock")
)
assert response.outcome.value == "success"
```

The focused tests extend this setup through the complete workflow:

| Step | Action | Expected visible result | Invariant proved |
|---:|---|---|---|
| 1 | Create `LMCacheCompatibilityProfile`. | Frozen compatibility identity. | Transport and compatibility identity remain separate. |
| 2 | Create `CapabilitySnapshot`. | Ordered bindings and tri-state capabilities validate. | Runtime/transport isolation and explicit uncertainty. |
| 3 | Construct `MockGateway`. | In-memory adapter is Protocol-compatible. | No production dependency is required. |
| 4 | Discover endpoints. | Dedicated success response with endpoint tuple. | Discovery preserves Runtime Profile and correlation. |
| 5 | Look up a fixture `CacheArtifact`. | `success` plus the compatible artifact. | Logical artifact provenance is checked. |
| 6 | Retrieve a fresh observation. | `success` only inside its TTL. | Freshness and endpoint generation are response-time facts. |
| 7 | Look up tokens with range support on/off. | Whole hit/miss remains; ranges appear only when supported. | `token_lookup` and `range_coverage` are independent. |
| 8 | Submit a prefetch intent. | A pending prefetch task. | Intent response type matches operation type. |
| 9 | Repeat the same intent/key. | The same task ID. | Equivalent submission is idempotent. |
| 10 | Reuse the key for different work. | `idempotency_conflict`. | A key cannot alias distinct logical work. |
| 11 | Transition pending → running → succeeded. | Explicit state at each step. | CPU-only asynchronous lifecycle simulation. |
| 12 | Cancel a pending task. | `cancelled` and cancelled task state. | Cancellation is an explicit terminal transition. |
| 13 | Cancel terminal work. | `success`; original terminal state is unchanged. | Cancellation is an idempotent no-op after completion. |
| 14 | Request an old generation. | `stale`. | Facts cannot cross endpoint generations. |
| 15 | Request a different profile. | `incompatible`. | Target identity is negotiated before execution. |
| 16 | Send a Legacy write. | `unsupported`. | Legacy is read-only. |
| 17 | Send v1 work to Legacy. | `incompatible`. | Runtime profiles cannot be mixed implicitly. |
| 18 | Add a secret/physical field. | Pydantic validation failure. | The wire boundary is storage-neutral and safe. |
| 19 | Construct an MP production transport. | `NotImplementedError`. | Production Gateway I/O is intentionally absent. |

Run the focused test with `-k` to inspect any invariant, for example:

```bash
python3 -m pytest -q test/kdn/test_cache_service_contracts.py -k idempotency
```

## Validation commands

Install [`requirements.txt`](../../requirements.txt) for the complete application and test dependency surface, then run from the repository root:

```bash
python3 -m pytest -q test/kdn
python3 -m pytest -q test/kdn/test_cache_service_contracts.py
python3 -m pytest -q test/test_runtime_compat.py
python3 -m pytest -q \
  test/test_instance_capability.py \
  test/test_instance_capability_registration.py

python3 -m compileall -q \
  cacheroute_compat \
  kdn_server/contracts \
  kdn_server/domain \
  kdn_server/gateway \
  test/kdn

git diff --check
```

A successful contract run reports only passed tests. Validation errors, raw backend exceptions, unexpected range data, changed task identity, or a non-structured Gateway failure indicate a contract regression.
