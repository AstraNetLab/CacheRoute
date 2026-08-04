# Development and validation

[Back to handbook](README.md).

## Assumptions and installation modes

Use Python 3; package metadata supports Python 3.10 or later. The complete
application environment is in [`env/README.md`](../../env/README.md); the
lightweight wheel dependencies are in [`pyproject.toml`](../../pyproject.toml).
From a source checkout, `conftest.py` exposes `src/` to tests and guarded direct
entrypoints bootstrap only at approved boundaries. Editable installation must
retain that behavior. A wheel must build with explicit packages, install into an
isolated environment, import outside the checkout, contain required runtime
data, and exclude repository documentation/tests/configuration.

## Individually auditable commands

Run from the repository root:

```console
python3 -m compileall -q src test
python3 -m pytest -q test/test_developer_handbook.py
python3 -m pytest -q test/test_repository_governance.py
python3 -m pytest -q test/test_namespace_layout.py
python3 -m pytest -q -s test/test_source_checkout_imports.py
python3 -m pytest -q -s test/test_wheel_install.py -m "not network"
git diff --check
```

Focused contract/domain tests include `test/test_contract_foundation.py`,
`test/test_contract_service_migration.py`, `test/test_domain_state_migration.py`,
and `test/kdn/test_cache_service_contracts.py`. KDN regression tests live under
`test/kdn`; Instance capability regressions include
`test/test_instance_capability.py` and
`test/test_instance_capability_registration.py`. Architecture checks live in
`test/test_repository_governance.py`, `test/test_namespace_layout.py`, and this
handbook's dedicated test. Network tests use the `network` marker and require
`CACHEROUTE_RUN_NETWORK_TESTS=1`; `-m "not network"` intentionally deselects them.

## Reporting outcomes

Report each command separately and exactly:

- **PASSED**: exited zero and assertions completed.
- **FAILED**: exited nonzero because code/test/check failed.
- **SKIPPED**: pytest collected a test and skipped it, with count/reason.
- **DESELECTED**: marker/expression excluded a collected test.
- **NOT RUN**: command was not executed; explain why.
- **Environment-blocked**: dependency, service, hardware, credential, or network
  limitation prevented completion; never call it passed.

PR evidence should include base/final SHA, complete changed files, diff summary,
source and tests consulted, exact outcomes including skip/deselection counts,
known limitations, compatibility impact, handbook impact, and confirmation of
runtime/dependency/package-discovery changes. Runtime validation matters when a
runtime surface changes; documentation-only changes should prove structural
accuracy and wheel exclusion.
