"""Exercise application imports from outside an uninstalled source checkout."""

import os
from pathlib import Path
import subprocess
import sys

import cacheroute.compat
from core.runtime_compat import normalize_runtime_profile
from kdn_server.domain import RuntimeProfile
import kdn_server.kv_builder


def _assert_source_imports():
    repo = Path(__file__).resolve().parents[1]
    assert Path(cacheroute.compat.__file__).resolve().is_relative_to(repo / "src")
    assert normalize_runtime_profile("modern") == "v1"
    assert RuntimeProfile.normalize("old") is RuntimeProfile.LEGACY
    assert Path(kdn_server.kv_builder.__file__).resolve().is_relative_to(repo)


def test_application_imports_from_outside_source_checkout(tmp_path):
    if os.getenv("CACHEROUTE_SOURCE_CHECKOUT_CHILD") == "1":
        _assert_source_imports()
        print(f"cacheroute.compat={Path(cacheroute.compat.__file__).resolve()}")
        print(f"kdn_server.kv_builder={Path(kdn_server.kv_builder.__file__).resolve()}")
        return

    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["CACHEROUTE_SOURCE_CHECKOUT_CHILD"] = "1"
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "-q", "-s", str(Path(__file__).resolve())],
        cwd=tmp_path,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "2 passed" in result.stdout
    assert "src/cacheroute/compat/__init__.py" in result.stdout
    assert "kdn_server/kv_builder.py" in result.stdout
    print(result.stdout, end="")
    _assert_source_imports()


def test_direct_kdn_builder_entrypoint_bootstraps_source_checkout(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-I", str(repo / "util" / "kdn_build_kv.py"), "--help"],
        cwd=tmp_path,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "--kv-root" in result.stdout
