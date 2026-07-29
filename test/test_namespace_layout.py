"""Tests for the dependency-light canonical package namespace."""

import subprocess
import sys


def test_canonical_namespace_import_is_dependency_light():
    script = """
import sys
import cacheroute
import cacheroute.observability

for name in ('fastapi', 'redis', 'numpy', 'torch', 'vllm', 'lmcache'):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-I", "-c", script], check=True)
