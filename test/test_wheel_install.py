"""Verify compatibility imports from an installed wheel, not the source tree."""

from pathlib import Path
import subprocess
import sys


def test_wheel_contains_dependency_light_compatibility_package(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    installed = tmp_path / "installed"
    outside = tmp_path / "outside"
    wheelhouse.mkdir()
    outside.mkdir()

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(repo), "--no-deps", "--no-build-isolation", "-w", str(wheelhouse)],
        check=True,
    )
    wheel = next(wheelhouse.glob("cacheroute-*.whl"))
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(installed), str(wheel)],
        check=True,
    )
    script = f"""
import sys
sys.path.insert(0, {str(installed)!r})
from core.runtime_compat import normalize_runtime_profile
from kdn_server.domain import RuntimeProfile
assert normalize_runtime_profile('modern') == 'v1'
assert RuntimeProfile.normalize('old') is RuntimeProfile.LEGACY
print('installed domain compatibility: passed')
"""
    subprocess.run([sys.executable, "-I", "-c", script], cwd=outside, check=True)
