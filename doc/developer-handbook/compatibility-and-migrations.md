# Compatibility and migrations

[Back to handbook](README.md). Do not remove these paths in a documentation PR.

| Old import/path | Canonical import/owner | Status | Shim/adapter | Identity / wire requirement | Tests | Removal condition | Checkout / wheel behavior |
|---|---|---|---|---|---|---|---|
| `cacheroute_compat[.runtime]` | `cacheroute.compat[.runtime]` | Deprecated | star-forwarding package | Same `__all__` and object identity | [`test_runtime_compat.py`](../../test/test_runtime_compat.py), [`test_wheel_install.py`](../../test/test_wheel_install.py) | CacheRoute 0.3.0 milestone stated by shim | Explicitly packaged; works in both. |
| `core.runtime_compat` | `cacheroute.compat.runtime` | Transitional | forwarding compatibility module | Normalization and constants remain compatible | [`test_runtime_compat.py`](../../test/test_runtime_compat.py) | Focused caller migration and audit | Root package explicitly installed. |
| `kdn_server.domain[.models]` | runtime/topology/cache/routing models | Transitional | re-export module | Canonical class identity required | [`test_domain_state_migration.py`](../../test/test_domain_state_migration.py), [`test_wheel_install.py`](../../test/test_wheel_install.py) | Service migration milestone, complete references | Explicitly packaged. |
| `kdn_server.contracts.common/errors/knowledge/cache_service` | `cacheroute.contracts.v1.*` | Transitional | forwarding modules | Canonical identity, `__all__`, field and wire equality | [`test_contract_service_migration.py`](../../test/test_contract_service_migration.py) | KDN migration plus caller audit | Explicitly packaged. |
| Legacy Runtime Profile / Redis `vllm@*` | compatibility adapter; canonical domain stays logical | Transitional | profile/key-layout adapter | Legacy values remain explicit; `auto` resolves before persistence | [`test_runtime_compat.py`](../../test/test_runtime_compat.py) | Approved runtime migration, not implied deprecation | Available in checkout/wheel. |
| direct source scripts | installed packages / future entrypoints | Transitional | guarded source-checkout bootstrap at approved boundaries | Must not mutate normal package import paths | [`test_source_checkout_imports.py`](../../test/test_source_checkout_imports.py), [`test_repository_governance.py`](../../test/test_repository_governance.py) | Replacement entrypoint validated | Selected scripts work outside checkout cwd. |

## Packaging and reference audit

`pyproject.toml` explicitly maps `cacheroute` and `cacheroute_compat`, then lists
canonical and transitional packages. Editable and wheel installs must preserve
imports while repository-only `doc`, `env`, `scripts`, `log`, and `test` remain
absent. Isolated wheel tests verify package contents, object identity, imports
outside the checkout, and package data. Source-checkout bootstraps are restricted
to test/entrypoint boundaries; normal imports must not modify `sys.path`.

Every migration must audit ordinary imports; dynamic/module/class strings;
Uvicorn targets; subprocess and `python3 -m` commands; Docker/Compose/CI/config
paths; fixtures, monkeypatch and mock targets; explicit package lists; editable
and isolated wheel installs; and local Markdown links. The architecture RFC
requires a focused Issue before moving a directory or service. Compatibility
means preserving object identity where forwarding is promised and preserving
fields, defaults, enums, serialization and wire values across old/canonical
paths—not merely making both imports succeed.
