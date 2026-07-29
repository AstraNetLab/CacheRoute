"""Tests for the dependency-light canonical package namespace."""

import subprocess
import sys
from pathlib import Path


PROHIBITED_MODULES = (
    "core", "proxy", "instance", "scheduler", "kdn_server",
    "fastapi", "redis", "numpy", "torch", "vllm", "lmcache",
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


def test_pytest_collects_source_namespace_without_editable_install(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "--collect-only", "-q",
         str(repo / "test" / "test_source_checkout_imports.py")],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "1 test collected" in result.stdout
