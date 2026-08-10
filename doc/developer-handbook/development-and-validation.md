# Development and validation

Use repository-relative commands. Do not put user-specific absolute paths in PR evidence.

## Expected environments

| Environment | Expectation | Individually auditable command |
|---|---|---|
| Source checkout | Root transitional packages and `src/cacheroute` foundations import with test bootstrap paths where needed. | `python3 -m pytest -q -s test/test_source_checkout_imports.py` |
| Compile check | Python sources in `src` and `test` compile without syntax errors. | `python3 -m compileall -q src test` |
| Focused package governance | Explicit package lists, repository-only namespaces, and source bootstraps remain reviewable. | `python3 -m pytest -q test/test_repository_governance.py test/test_namespace_layout.py` |
| Editable install | The configured package set remains importable from an editable installation without changing package discovery. | `python3 -m pip install -e . --no-deps` followed by `python3 -m pytest -q test/test_namespace_layout.py` |
| Tracked-source release chain | Export only files tracked at the revision, build a direct wheel and an sdist, then build the release wheel from the unpacked sdist without `.git` metadata. | `python3 -m pytest -q -s test/test_wheel_install.py -m "not network"` |
| Non-network clean wheel | Runtime packages install from the built wheel without dependency resolution or source checkout leakage. | `python3 -m pytest -q -s test/test_wheel_install.py -m "not network"` |
| Full isolated wheel | Declared dependencies install in a clean venv when a package index or local wheelhouse is available. | `CACHEROUTE_RUN_NETWORK_TESTS=1 python3 -m pytest -q -s test/test_wheel_install.py` |
| Offline full isolated wheel | The network-marked wheel test can use a local wheelhouse instead of indexes. | `CACHEROUTE_RUN_NETWORK_TESTS=1 CACHEROUTE_TEST_WHEELHOUSE="$PWD/wheelhouse" python3 -m pytest -q -s test/test_wheel_install.py` |
| Observability contracts | Current trace models, propagation, startup, and Proxy projection behavior remain valid. | `python3 -m pytest -q test/observability` |
| Contract foundations | KDN/Gateway v1 contracts and migration shims preserve object identity and validation. | `python3 -m pytest -q test/test_contract_foundation.py test/test_contract_service_migration.py` |
| Diff hygiene | The final diff has no whitespace errors. | `git diff --check "$(git merge-base origin/main HEAD)" HEAD` |

## Release artifact boundaries

Release validation distinguishes five layers: the active source checkout, a
Git-tracked source export, the sdist made from that export, the wheel made from
the sdist, and an isolated installation of that final wheel. A raw copy of the
active worktree is not release evidence because ignored or untracked files can
mask a stale explicit package declaration. The non-network wheel test also
builds a direct tracked-source wheel as a separate check, but uses the
sdist-derived wheel for content and isolated-install assertions.
When the same test module runs from an unpacked sdist, it skips only the
checkout-specific tracked-export assertion and builds the validation wheel
directly from that Git-free sdist tree; it must not attempt to resolve `HEAD`.

For a manual release check, create a clean tracked-file export without `.git`,
run `python3 -m build --sdist --no-isolation` there, unpack the generated sdist
into a separate clean location, and build the wheel from that unpacked tree. Do
not substitute a wheel built from the original checkout for the sdist-derived
wheel.

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
git diff --check "$(git merge-base origin/main HEAD)" HEAD
```

When network or a complete local wheelhouse is available, also run:

```bash
CACHEROUTE_RUN_NETWORK_TESTS=1 python3 -m pytest -q -s test/test_wheel_install.py
```

For an offline local wheelhouse, use:

```bash
CACHEROUTE_RUN_NETWORK_TESTS=1 CACHEROUTE_TEST_WHEELHOUSE="$PWD/wheelhouse" python3 -m pytest -q -s test/test_wheel_install.py
```

## Result reporting vocabulary

Record PASSED, FAILED, ERROR, SKIPPED, DESELECTED, NOT RUN, and ENVIRONMENT-BLOCKED separately. Warnings are separate from pass/fail status. An environment-blocked command must never be reported as passed because it did not validate the intended behavior.

## Required PR evidence

Include head SHA, base SHA, changed files, chapter-by-chapter summary, source-of-truth decisions, status classifications, root README changes, runtime/API/dependency/package-discovery confirmations, exact test results, wheel filename/size/SHA-256 when built, network test status, known baseline limitations, and handbook impact.
