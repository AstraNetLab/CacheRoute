# Development and validation

Use repository-relative commands. Do not put user-specific absolute paths in PR evidence.

## Expected environments

| Environment | Expectation | Individually auditable command |
|---|---|---|
| Source checkout | Root transitional packages and `src/cacheroute` foundations import with test bootstrap paths where needed. | `python3 -m pytest -q -s test/test_source_checkout_imports.py` |
| Compile check | Python sources in `src` and `test` compile without syntax errors. | `python3 -m compileall -q src test` |
| Focused package governance | Explicit package lists, repository-only namespaces, and source bootstraps remain reviewable. | `python3 -m pytest -q test/test_repository_governance.py test/test_namespace_layout.py` |
| Editable install | The configured package set remains importable from an editable installation without changing package discovery. | `python3 -m pip install -e . --no-deps` followed by `python3 -m pytest -q test/test_namespace_layout.py` |
| Wheel build | The project builds a wheel from the checked-out source without build isolation when `build` is installed. | `python3 -m build --no-isolation` |
| Non-network clean wheel | Runtime packages install from the built wheel without dependency resolution or source checkout leakage. | `python3 -m pytest -q -s test/test_wheel_install.py -m "not network"` |
| Full isolated wheel | Declared dependencies install in a clean venv when a package index or local wheelhouse is available. | `CACHEROUTE_RUN_NETWORK_TESTS=1 python3 -m pytest -q -s test/test_wheel_install.py` |
| Offline full isolated wheel | The network-marked wheel test can use a local wheelhouse instead of indexes. | `CACHEROUTE_RUN_NETWORK_TESTS=1 CACHEROUTE_TEST_WHEELHOUSE=/path/to/wheelhouse python3 -m pytest -q -s test/test_wheel_install.py` |
| Observability contracts | Current trace models, propagation, startup, and Proxy projection behavior remain valid. | `python3 -m pytest -q test/observability` |
| Contract foundations | KDN/Gateway v1 contracts and migration shims preserve object identity and validation. | `python3 -m pytest -q test/test_contract_foundation.py test/test_contract_service_migration.py` |
| Diff hygiene | The final diff has no whitespace errors. | `git diff --check` |

## Required final-head checklist

```bash
python3 -m compileall -q src test
python3 -m pytest -q test/test_documentation_governance.py
python3 -m pytest -q test/test_repository_governance.py
python3 -m pytest -q test/test_namespace_layout.py
python3 -m pytest -q -s test/test_source_checkout_imports.py
python3 -m pytest -q -s test/test_wheel_install.py -m "not network"
python3 -m pytest -q test/observability
python3 -m pytest -q test/test_contract_foundation.py
python3 -m pytest -q test/test_contract_service_migration.py
python3 -m build --no-isolation
git diff --check
```

When network or a complete local wheelhouse is available, also run:

```bash
CACHEROUTE_RUN_NETWORK_TESTS=1 python3 -m pytest -q -s test/test_wheel_install.py
```

For an offline local wheelhouse, use:

```bash
CACHEROUTE_RUN_NETWORK_TESTS=1 CACHEROUTE_TEST_WHEELHOUSE=/path/to/wheelhouse python3 -m pytest -q -s test/test_wheel_install.py
```

## Result reporting vocabulary

Record PASSED, FAILED, ERROR, SKIPPED, DESELECTED, NOT RUN, and ENVIRONMENT-BLOCKED separately. Warnings are separate from pass/fail status. An environment-blocked command must never be reported as passed because it did not validate the intended behavior.

## Required PR evidence

Include head SHA, base SHA, changed files, chapter-by-chapter summary, source-of-truth decisions, status classifications, root README changes, runtime/API/dependency/package-discovery confirmations, exact test results, wheel filename/size/SHA-256 when built, network test status, known baseline limitations, and handbook impact.
