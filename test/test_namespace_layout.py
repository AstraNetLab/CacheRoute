"""Tests for the dependency-light canonical package namespace."""

import subprocess
import sys
from pathlib import Path

import pytest


PROHIBITED_MODULES = (
    "core", "proxy", "instance", "scheduler", "kdn_server", "client", "store", "model", "UI",
    "fastapi", "redis", "numpy", "torch", "sentence_transformers", "vllm", "lmcache",
)


def _run_isolated(import_statement, exercise=""):
    repo = Path(__file__).resolve().parents[1]
    script = f"""
import sys
import runpy
runpy.run_path({str(repo / 'conftest.py')!r})
{import_statement}
{exercise}

for name in {PROHIBITED_MODULES!r}:
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-I", "-c", script], check=True)


def test_cacheroute_import_is_dependency_light():
    _run_isolated("import cacheroute")


def test_compat_import_is_dependency_light_and_functional():
    _run_isolated(
        "import cacheroute.compat as compatibility",
        "assert compatibility.normalize_runtime_profile('modern') == 'v1'",
    )


def test_observability_import_is_dependency_light():
    _run_isolated("import cacheroute.observability")


@pytest.mark.parametrize("module", (
    "cacheroute.runtime", "cacheroute.contracts", "cacheroute.contracts.v1",
    "cacheroute.contracts.v1.common", "cacheroute.contracts.v1.errors",
))
def test_runtime_and_contract_imports_are_dependency_light(module):
    _run_isolated(f"import {module}")


def test_demo_client_bootstrap_resolves_source_namespace(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    script = f"""
from pathlib import Path
import runpy
namespace = runpy.run_path({str(repo / 'test' / 'demo_client.py')!r})
namespace['_ensure_project_root_on_syspath']()
import cacheroute.compat
path = Path(cacheroute.compat.__file__).resolve()
print(f'cacheroute.compat={{path}}')
assert path.is_relative_to({str(repo / 'src')!r})
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "src/cacheroute/compat/__init__.py" in result.stdout


def test_normal_package_imports_do_not_mutate_sys_path(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    script = f"""
import sys
import runpy
runpy.run_path({str(repo / 'conftest.py')!r})
before = tuple(sys.path)
import client.client
assert tuple(sys.path) == before
import store.knowledge_build
assert tuple(sys.path) == before
assert not any(path.endswith('/site-packages/src') for path in sys.path)
print('normal import sys.path unchanged')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == "normal import sys.path unchanged"
