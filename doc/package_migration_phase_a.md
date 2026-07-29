# Phase A package migration audit

This audit records the repository state reviewed for Issue #157 Phase A and
separates that complete inventory from the two dependency-light packages moved
by PR #158. It is maintained alongside later namespace migration phases.

## Scope and status

PR #158 migrates only `cacheroute_compat` to `cacheroute.compat`, establishes
the lightweight `cacheroute` namespace, and reserves
`cacheroute.observability`. It does **not** migrate application packages or the
actual observability implementation being developed in PR #156. Consequently,
the observability acceptance criterion is not complete and neither #157 nor
#141 is closed by this phase.

PR #156 must rebase onto PR #158 and move its `cacheroute_observability`
implementation, tests, demo, README, imports, and links into
`src/cacheroute/observability`. A permanent root `cacheroute_observability`
package must not be retained.

## Complete top-level directory inventory

Classification reflects directories tracked at the Phase A baseline. Generated
`.git`, `.pytest_cache`, and `__pycache__` directories are not architecture.

| Directory | Classification | Packaged before Phase A? | Phase A action |
|---|---|---:|---|
| `.assets` | Documentation assets | No | Unchanged |
| `.github` | Repository/CI metadata | No | Unchanged |
| `UI` | Runtime UI package | Yes | Preserved at root |
| `cacheroute_compat` | Dependency-light compatibility implementation | Yes | Moved to `src/cacheroute/compat` |
| `client` | Runtime client package | Yes | Preserved at root |
| `core` | Shared application runtime package | Yes | Preserved at root |
| `data` | Packaged data helper package | Yes | Preserved at root |
| `doc` | Documentation | No | This audit added here |
| `env` | Environment, Docker, and deployment tooling | No | Unchanged |
| `instance` | Runtime Instance package | Yes | Preserved at root |
| `kdn_server` | Runtime KDN package | Yes | Preserved at root |
| `log` | Experiment log artifacts | No | Unchanged |
| `model` | Runtime model package | Yes | Preserved at root |
| `proxy` | Runtime Proxy package | Yes | Preserved at root |
| `scheduler` | Runtime Scheduler package | Yes | Preserved at root |
| `scripts` | Repository scripts | No | Unchanged |
| `src` | Canonical Python source root | No (new) | Hosts migrated packages |
| `store` | Runtime storage package | Yes | Preserved at root |
| `test` | Tests and demo launchers | Excluded | Updated validation only |
| `util` | Runtime utility package | Yes | Preserved at root |

There are no baseline top-level `component` or `storage` Python directories;
the corresponding current concepts live in component packages and `store`.

## Complete packaged runtime inventory

The pre-PR namespace-aware setuptools discovery (`where = ["."]`) discovered the following
packages. The transitional explicit package list preserves every entry and adds
the four entries marked **new**:

```text
UI, UI.client_ui, UI.client_ui.static, UI.client_ui.templates, UI.kdn_ui,
UI.proxy_ui, UI.proxy_ui.static
client, client.taskset
core
data, data.CacheRoute_dataset, data.CacheRoute_dataset.knowledge_document
doc, doc.blog, doc.integrations
env, env.config, env.docker, env.docker.cu130, env.docker.cu130.scripts
instance, instance.TPOT_predictor, instance.TTFT_predictor,
instance.TTFT_predictor.data, instance.pclient, instance.resource_agent,
instance.resource_agent.src, instance.resource_dashboard,
instance.resource_dashboard.static
kdn_server, kdn_server.KV_database, kdn_server.contracts, kdn_server.domain,
kdn_server.gateway, kdn_server.sclient, kdn_server.text_database,
kdn_server.text_database.blocks, kdn_server.util
log, log.scheduler
model
proxy, proxy.metrics, proxy.metrics.data, proxy.queue, proxy.resource,
proxy.sclient, proxy.strategy
scheduler, scheduler.knowledge, scheduler.resource, scheduler.strategy
scripts
store
test, test.kdn
util
cacheroute                         (new)
cacheroute.compat                  (new canonical implementation)
cacheroute.observability           (new namespace only)
cacheroute_compat                  (moved deprecated shim)
```

Archive inspection (ignoring the `.dist-info` directory) produced these exact
top-level Python package directories:

| Wheel | Complete top-level package list |
|---|---|
| Before PR #158 | `UI`, `cacheroute_compat`, `client`, `core`, `data`, `env`, `instance`, `kdn_server`, `model`, `proxy`, `scheduler`, `scripts`, `store`, `test`, `util` |
| After corrected PR #158 | `UI`, `cacheroute`, `cacheroute_compat`, `client`, `core`, `data`, `env`, `instance`, `kdn_server`, `model`, `proxy`, `scheduler`, `scripts`, `store`, `test`, `util` |

The baseline wheel required the unrelated invalid placeholder author email to
be removed in its temporary archived copy before current setuptools could build
it; no package-discovery setting was changed for that inspection.

### Normalized wheel member and package-data audit

After excluding `.dist-info` metadata and normalizing the intentional
`cacheroute_compat/runtime.py` relocation to `cacheroute/compat/runtime.py`, the
baseline has 155 members and the corrected Phase A wheel has 197. No normalized
member was removed. The 42 added members are:

```text
UI/client_ui/static/app.js
UI/client_ui/static/style.css
UI/client_ui/templates/index.html
UI/proxy_ui/static/app.js
UI/proxy_ui/static/index.html
UI/proxy_ui/static/style.css
cacheroute/__init__.py
cacheroute/observability/__init__.py
cacheroute_compat/__init__.py
cacheroute_compat/runtime.py
instance/TTFT_predictor/data/README.md
instance/TTFT_predictor/data/log-bs1-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs2-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs3-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs4-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs5-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs6-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs7-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/log-bs8-rtx5090-8-llama3-70b.txt
instance/TTFT_predictor/data/补录数据.txt
instance/TTFT_predictor/data/补录数据（小长度）.txt
instance/resource_dashboard/static/app.js
instance/resource_dashboard/static/index.html
instance/resource_dashboard/static/style.css
model/model_configs.yaml
proxy/metrics/data/log-bs1-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs2-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs3-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs4-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs5-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs6-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs7-rtx5090-8-llama3-70b.txt
proxy/metrics/data/log-bs8-rtx5090-8-llama3-70b.txt
proxy/metrics/data/redis_pull_table_from_image.json
proxy/metrics/redis_pull_coefficients.json
proxy/metrics/tpot_benchmark_table.json
proxy/metrics/tpot_coefficients.json
proxy/metrics/ttft_benchmark_table.json
proxy/metrics/ttft_coefficients.json
test/test_namespace_layout.py
test/test_repository_governance.py
test/test_source_checkout_imports.py
```

The baseline wheel contained zero non-Python, non-metadata members. The
corrected wheel contains 35: the UI/dashboard assets, predictor data, model
configuration, and metric tables listed above. These additions make required
runtime package data explicit; they do not replace or remove baseline data.
The generated `instance/TTFT_predictor/prompt_length_validation.log` is
explicitly excluded. At the same source head, its removal reduced the wheel
from 585,197 bytes to 584,806 bytes.

Package-data groups are limited to runtime inputs:

- `UI.client_ui` and `UI.proxy_ui`: browser JavaScript, CSS, and HTML assets;
- `instance.resource_dashboard`: dashboard JavaScript, CSS, and HTML assets;
- `instance.TTFT_predictor`: checked-in calibration tables and their data note;
- `proxy.metrics`: checked-in prediction coefficients, benchmark tables, and
  calibration inputs;
- `model`: the runtime model configuration YAML.

Generated logs, test output, temporary files, and standalone documentation are
not selected by the package-data patterns.

## Reference audit

The inventory searched all tracked repository files, including Python, TOML,
YAML, JSON, Dockerfiles, shell files, CI configuration, and Markdown. The
following categories are repository-wide; only the compatibility references
listed under “changed mapping” were modified.

| Reference class | Inventory result |
|---|---|
| Normal compatibility imports | `core/runtime_compat.py`, `kdn_server/domain/models.py`, `test/test_runtime_compat.py`, and `test/test_wheel_install.py` |
| Dynamic/importlib references | `instance/capability_builder.py` uses distribution metadata; no dynamic string names target either migrated package |
| `python -m` commands | Operational/docs commands occur in `README.md`, `doc/`, `env/`, component READMEs, and `test/README.md`; application commands follow documented installation, while pytest uses the centralized root `conftest.py` source bootstrap |
| Uvicorn/FastAPI module strings | `instance/TTFT_predictor/prefill_prediction_server.py`, its README/workflow, and `UI/proxy_ui/README.md`; none target the migrated package |
| Subprocess module invocations | `client/perf_client.py`, Instance dashboards, test demo launchers, resource-monitor tests, and wheel tests; only the wheel test exercises the migrated imports |
| Monkeypatch/mock target strings | Tests under `test/` and `test/kdn/`; none target the migrated implementation path |
| Docker/Compose/shell/CI | `Dockerfile`, `env/docker/cu130/`, `env/README.md`, `scripts/`, and `.github/`; no Compose file or migrated-package reference was found |
| Markdown references | `core/README.md` and `test/kdn/README.md` referenced the old implementation path and were updated; compatibility history remains explicitly marked deprecated |
| Source checkout path bootstraps | Root `conftest.py`; standalone demos in `test/`; `client/client.py`, `client/kv_timing_sender.py`, `kdn_server/kdn_register_cli.py`, `scheduler/scheduler_cli.py`, `scripts/validate_v1_kdn_roundtrip.py`, `store/knowledge_build.py`, and `util/kdn_build_kv.py` add both the repository root and `src` before project imports. `test/test_demo_instance_ui.py` has a test-only root bootstrap, while `test/demo_resource_monitor_e2e.py` uses its root path for subprocess working directories. Ordinary library modules, including `core/config.py`, do not mutate `sys.path`. Isolated wheel tests run elsewhere and do not use any source bootstrap. |

The reproducible inventory commands are:

```bash
find . -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
python3 -c "from setuptools import find_namespace_packages; print(*find_namespace_packages('.', exclude=['tests*','docs*','examples*']), sep='\n')"
rg -n --hidden -g '!.git/**' 'cacheroute_compat|cacheroute_observability'
rg -n --hidden -g '!.git/**' 'importlib|python(3)?[[:space:]]+-m|uvicorn|subprocess|monkeypatch|mock[.]patch'
```

## Changed path and entry-point mapping

| Before | After | Policy |
|---|---|---|
| `cacheroute_compat` | `cacheroute.compat` | Canonical implementation moved |
| `cacheroute_compat.runtime` | `cacheroute.compat.runtime` | Canonical import for new code |
| None | `cacheroute` | Lightweight canonical namespace |
| None | `cacheroute.observability` | Reserved namespace, implementation pending PR #156 |

No CLI, Uvicorn, FastAPI, dynamic-import, or `python -m` entry point changed.
The `cacheroute_compat` forwarding shim is scheduled for removal in CacheRoute
0.3.0. It contains imports only and is narrowly covered by compatibility tests.

## Transitional packaging design

Setuptools cannot safely discover unrelated packages from two source roots with
one declarative `find` rule. Phase A therefore uses an explicit, reviewable
package list plus targeted `package-dir` mappings for `cacheroute` and
`cacheroute_compat`. This prevents the src-layout migration from silently
dropping root packages. The final package-migration phase removes the explicit
transition and enables src-only discovery after every listed root runtime
package is migrated or intentionally deprecated through review.

## Later phases and risks

1. PR #156 performs the observability implementation migration described above.
2. Later #157 phases move each root runtime package without changing its public
   import path, then replace the transitional explicit package list.
3. CacheRoute 0.3.0 removes `cacheroute_compat` after downstream imports migrate.
4. Root runtime package initializers currently import optional application
   dependencies. The wheel tests use separate clean virtual environments: a
   no-dependency environment for lightweight namespaces and a second environment
   that installs declared dependencies before exercising the full public surface.
5. Packaging data files used by runtime modules requires review during each
   component migration; Phase A deliberately preserves the prior package list
   and runtime behavior rather than broadening that scope.

Run the network-dependent full clean-wheel validation explicitly with:

```bash
CACHEROUTE_RUN_NETWORK_TESTS=1 \
  python3 -m pytest -q test/test_wheel_install.py -m network
```

For an offline complete wheelhouse, also set
`CACHEROUTE_TEST_WHEELHOUSE=/path/to/wheelhouse`; pip then uses `--no-index` and
`--find-links`. A default skip is not release evidence: the network-marked test
must pass once against a package index or complete wheelhouse before merge.
