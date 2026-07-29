"""Verify compatibility imports from an installed wheel, not the source tree."""

from pathlib import Path
import subprocess
import sys
import venv
import zipfile


EXPECTED_TOP_LEVEL_PACKAGES = {
    "UI", "cacheroute", "cacheroute_compat", "client", "core", "data",
    "env", "instance", "kdn_server", "model", "proxy",
    "scheduler", "scripts", "store", "test", "util",
}
EXPECTED_PACKAGE_INITIALIZERS = {
    "UI/__init__.py", "client/__init__.py", "core/__init__.py", "data/__init__.py",
    "instance/__init__.py", "instance/TPOT_predictor/__init__.py",
    "instance/TTFT_predictor/__init__.py", "instance/pclient/__init__.py",
    "kdn_server/__init__.py", "kdn_server/contracts/__init__.py",
    "kdn_server/domain/__init__.py", "kdn_server/gateway/__init__.py",
    "model/__init__.py", "proxy/__init__.py", "proxy/metrics/__init__.py",
    "proxy/queue/__init__.py", "proxy/sclient/__init__.py",
    "proxy/strategy/__init__.py", "scheduler/__init__.py",
    "scheduler/knowledge/__init__.py", "scheduler/resource/__init__.py",
    "scheduler/strategy/__init__.py", "store/__init__.py", "util/__init__.py",
    "cacheroute/__init__.py", "cacheroute/compat/__init__.py",
    "cacheroute/observability/__init__.py", "cacheroute_compat/__init__.py",
}


def test_wheel_contains_dependency_light_compatibility_package(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    environment = tmp_path / "venv"
    outside = tmp_path / "outside"
    wheelhouse.mkdir()
    outside.mkdir()

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(repo), "--no-deps", "--no-build-isolation", "-w", str(wheelhouse)],
        check=True,
    )
    wheel = next(wheelhouse.glob("cacheroute-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
        packaged = {
            name.partition("/")[0]
            for name in archive.namelist()
            if "/" in name and not name.partition("/")[0].endswith(".dist-info")
        }
    assert packaged == EXPECTED_TOP_LEVEL_PACKAGES
    assert EXPECTED_PACKAGE_INITIALIZERS <= members
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / "bin" / "python"
    subprocess.run([python, "-m", "pip", "install", "--no-deps", str(wheel)], check=True)
    script = """
import core
import proxy
import instance
import cacheroute
import cacheroute.compat
import cacheroute.compat.runtime as canonical_runtime
import cacheroute_compat.runtime as legacy_runtime
import core.runtime_compat as core_runtime
from core.runtime_compat import normalize_runtime_profile
from kdn_server.domain import RuntimeProfile

assert normalize_runtime_profile('modern') == 'v1'
assert RuntimeProfile.normalize('old') is RuntimeProfile.LEGACY
assert canonical_runtime.__all__ == legacy_runtime.__all__ == core_runtime.__all__
for name in canonical_runtime.__all__:
    canonical = getattr(canonical_runtime, name)
    assert getattr(legacy_runtime, name) is canonical
    assert getattr(core_runtime, name) is canonical
print('installed public import surface: passed')
"""
    subprocess.run([python, "-I", "-c", script], cwd=outside, check=True)
