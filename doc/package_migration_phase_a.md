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

## Reference audit

The inventory searched all tracked repository files, including Python, TOML,
YAML, JSON, Dockerfiles, shell files, CI configuration, and Markdown. The
following categories are repository-wide; only the compatibility references
listed under “changed mapping” were modified.

| Reference class | Inventory result |
|---|---|
| Normal compatibility imports | `core/runtime_compat.py`, `kdn_server/domain/models.py`, `test/test_runtime_compat.py`, and `test/test_wheel_install.py` |
| Dynamic/importlib references | `instance/capability_builder.py` uses distribution metadata; no dynamic string names target either migrated package |
| `python -m` commands | Operational/docs commands occur in `README.md`, `doc/`, `env/`, component READMEs, and `test/README.md`; none target the migrated package |
| Uvicorn/FastAPI module strings | `instance/TTFT_predictor/prefill_prediction_server.py`, its README/workflow, and `UI/proxy_ui/README.md`; none target the migrated package |
| Subprocess module invocations | `client/perf_client.py`, Instance dashboards, test demo launchers, resource-monitor tests, and wheel tests; only the wheel test exercises the migrated imports |
| Monkeypatch/mock target strings | Tests under `test/` and `test/kdn/`; none target the migrated implementation path |
| Docker/Compose/shell/CI | `Dockerfile`, `env/docker/cu130/`, `env/README.md`, `scripts/`, and `.github/`; no Compose file or migrated-package reference was found |
| Markdown references | `core/README.md` and `test/kdn/README.md` referenced the old implementation path and were updated; compatibility history remains explicitly marked deprecated |

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
   dependencies. Wheel smoke tests therefore install declared dependencies;
   namespace isolation tests separately prove canonical imports remain light.
5. Packaging data files used by runtime modules requires review during each
   component migration; Phase A deliberately preserves the prior package list
   and runtime behavior rather than broadening that scope.
