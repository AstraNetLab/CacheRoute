"""Tests for the dependency-light canonical package namespace."""

import subprocess
import sys


PROHIBITED_MODULES = (
    "core", "proxy", "instance", "scheduler", "kdn_server",
    "fastapi", "redis", "numpy", "torch", "vllm", "lmcache",
)


def _run_isolated(import_statement, exercise=""):
    script = f"""
import sys
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
