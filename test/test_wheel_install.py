"""Verify wheel contents and imports without using the source checkout."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import venv
import zipfile

import pytest


EXPECTED_TOP_LEVEL_PACKAGES = {
    "UI", "cacheroute", "cacheroute_compat", "client", "core", "data",
    "env", "instance", "kdn_server", "model", "proxy", "scheduler",
    "scripts", "store", "test", "util",
}
REQUIRED_PACKAGE_DATA = {
    "UI/client_ui/static/app.js",
    "UI/client_ui/static/style.css",
    "UI/client_ui/templates/index.html",
    "UI/proxy_ui/static/app.js",
    "UI/proxy_ui/static/index.html",
    "UI/proxy_ui/static/style.css",
    "instance/resource_dashboard/static/app.js",
    "instance/resource_dashboard/static/index.html",
    "instance/resource_dashboard/static/style.css",
    "instance/TTFT_predictor/data/README.md",
    "instance/TTFT_predictor/data/log-bs1-rtx5090-8-llama3-70b.txt",
    "instance/TTFT_predictor/data/补录数据.txt",
    "model/model_configs.yaml",
    "proxy/metrics/ttft_benchmark_table.json",
    "proxy/metrics/data/redis_pull_table_from_image.json",
}


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory):
    repo = Path(__file__).resolve().parents[1]
    wheelhouse = tmp_path_factory.mktemp("wheelhouse")
    source = tmp_path_factory.mktemp("wheel-source") / "CacheRoute"
    shutil.copytree(
        repo,
        source,
        ignore=shutil.ignore_patterns(
            ".git", "build", "dist", "*.egg-info", "__pycache__",
            ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "wheelhouse",
        ),
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(source), "--no-deps", "--no-build-isolation", "-w", str(wheelhouse)],
        check=True,
    )
    return next(wheelhouse.glob("cacheroute-*.whl"))


def _create_isolated_environment(path: Path) -> Path:
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(path)
    return path / "bin" / "python"


def _run_outside_repo(python: Path, outside: Path, script: str) -> subprocess.CompletedProcess[str]:
    outside.mkdir()
    return subprocess.run(
        [python, "-I", "-c", script],
        cwd=outside,
        check=True,
        text=True,
        capture_output=True,
    )


def test_wheel_preserves_packages_and_runtime_data(built_wheel):
    with zipfile.ZipFile(built_wheel) as archive:
        members = set(archive.namelist())
        packaged = {
            name.partition("/")[0]
            for name in members
            if "/" in name and not name.partition("/")[0].endswith(".dist-info")
        }
    assert packaged == EXPECTED_TOP_LEVEL_PACKAGES
    assert REQUIRED_PACKAGE_DATA <= members
    assert "instance/TTFT_predictor/prompt_length_validation.log" not in members


def test_dependency_light_clean_wheel_imports(built_wheel, tmp_path):
    python = _create_isolated_environment(tmp_path / "light-venv")
    subprocess.run([python, "-m", "pip", "install", "--no-deps", str(built_wheel)], check=True)
    result = _run_outside_repo(python, tmp_path / "outside-light", """
from pathlib import Path
import sys
import cacheroute
import cacheroute.compat
import cacheroute.compat.runtime as canonical_runtime
import cacheroute.observability
import cacheroute_compat.runtime as legacy_runtime

modules = (cacheroute, cacheroute.compat, canonical_runtime,
           cacheroute.observability, legacy_runtime)
for module in modules:
    path = Path(module.__file__).resolve()
    print(f"{module.__name__}={path}")
    assert path.is_relative_to(Path(sys.prefix).resolve())
assert canonical_runtime.normalize_runtime_profile("modern") == "v1"
assert canonical_runtime.__all__ == legacy_runtime.__all__
for name in canonical_runtime.__all__:
    assert getattr(legacy_runtime, name) is getattr(canonical_runtime, name)
print("dependency-light clean-wheel imports: passed")
""")
    assert "dependency-light clean-wheel imports: passed" in result.stdout
    print(result.stdout, end="")


@pytest.mark.network
@pytest.mark.skipif(
    os.getenv("CACHEROUTE_RUN_NETWORK_TESTS") != "1",
    reason="set CACHEROUTE_RUN_NETWORK_TESTS=1 to install declared dependencies in a clean venv",
)
def test_full_public_imports_from_clean_wheel(built_wheel, tmp_path):
    python = _create_isolated_environment(tmp_path / "full-venv")
    # This deliberately installs declared dependencies. An unavailable package
    # index must fail the test rather than leaking host packages into the venv.
    install = [python, "-m", "pip", "install"]
    wheelhouse = os.getenv("CACHEROUTE_TEST_WHEELHOUSE")
    if wheelhouse:
        install.extend(["--no-index", "--find-links", wheelhouse])
    subprocess.run([*install, str(built_wheel)], check=True)
    result = _run_outside_repo(python, tmp_path / "outside-full", """
from pathlib import Path
import sys
import core
import core.runtime_compat as core_runtime
import proxy
import instance
import kdn_server
import kdn_server.domain
import cacheroute.compat.runtime as canonical_runtime
import cacheroute_compat.runtime as legacy_runtime
from core.runtime_compat import normalize_runtime_profile
from kdn_server.domain import RuntimeProfile

modules = (core, core_runtime, proxy, instance, kdn_server, kdn_server.domain,
           canonical_runtime, legacy_runtime)
for module in modules:
    path = Path(module.__file__).resolve()
    print(f"{module.__name__}={path}")
    assert path.is_relative_to(Path(sys.prefix).resolve())
before_imports = tuple(sys.path)
import client.client
assert tuple(sys.path) == before_imports
import store.knowledge_build
assert tuple(sys.path) == before_imports
assert normalize_runtime_profile("modern") == "v1"
assert RuntimeProfile.normalize("old") is RuntimeProfile.LEGACY
assert canonical_runtime.__all__ == legacy_runtime.__all__ == core_runtime.__all__
for name in canonical_runtime.__all__:
    canonical = getattr(canonical_runtime, name)
    assert getattr(legacy_runtime, name) is canonical
    assert getattr(core_runtime, name) is canonical
print("full clean-wheel public imports: passed")
""")
    assert "full clean-wheel public imports: passed" in result.stdout
    print(result.stdout, end="")
