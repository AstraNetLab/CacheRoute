# Development and validation

Use repository-relative commands. Do not put user-specific absolute paths in PR evidence.

## Expected environments

| Environment | Expectation |
|---|---|
| Source checkout | Root transitional packages and `src/cacheroute` foundations import with test bootstrap paths where needed. |
| Editable install | Explicit packages in `pyproject.toml` remain available without changing package discovery. |
| Wheel install | Runtime packages and package data install; repository-only docs/tests/env/log/scripts remain absent. |
| Dependency-light isolation | Canonical foundations import without pulling heavy runtime SDKs such as Torch, vLLM, LMCache, Redis, or sentence-transformers. |

## Individually auditable commands

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
python3 -m pytest -q test/test_wheel_install.py -m network

git diff --check
```

The network-marked wheel test is only for environments with package indexes or a local wheelhouse. If the environment lacks network/package access, record it as ENVIRONMENT-BLOCKED, not PASSED.

## Result reporting vocabulary

Record PASSED, FAILED, ERROR, SKIPPED, DESELECTED, NOT RUN, and ENVIRONMENT-BLOCKED separately. Warnings are separate from pass/fail status. An environment-blocked command must never be reported as passed because it did not validate the intended behavior.

## Required PR evidence

Include head SHA, base SHA, changed files, chapter-by-chapter summary, source-of-truth decisions, status classifications, root README changes, runtime/API/dependency/package-discovery confirmations, exact test results, wheel result, known baseline limitations, and handbook impact.
