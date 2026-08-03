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
    "instance", "kdn_server", "model", "proxy", "scheduler", "store", "util",
}
FORBIDDEN_TOP_LEVEL_PACKAGES = {"doc", "env", "log", "scripts", "test"}
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
REQUIRED_CANONICAL_FOUNDATION = {
    "cacheroute/runtime/__init__.py",
    "cacheroute/runtime/profiles.py",
    "cacheroute/contracts/__init__.py",
    "cacheroute/contracts/v1/__init__.py",
    "cacheroute/contracts/v1/common.py",
    "cacheroute/contracts/v1/errors.py",
    "cacheroute/contracts/v1/knowledge.py",
    "cacheroute/contracts/v1/cache_service.py",
    "kdn_server/contracts/knowledge.py",
    "kdn_server/contracts/cache_service.py",
    "cacheroute/runtime/state.py",
    "cacheroute/topology/__init__.py",
    "cacheroute/topology/lmcache.py",
    "cacheroute/cache/__init__.py",
    "cacheroute/cache/models.py",
    "cacheroute/routing/__init__.py",
    "cacheroute/routing/queue.py",
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
    assert packaged.isdisjoint(FORBIDDEN_TOP_LEVEL_PACKAGES)
    for prefix in FORBIDDEN_TOP_LEVEL_PACKAGES:
        assert not any(
            member == prefix or member.startswith(f"{prefix}/")
            for member in members
        )
    assert REQUIRED_PACKAGE_DATA <= members
    assert REQUIRED_CANONICAL_FOUNDATION <= members
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
import cacheroute.runtime
import cacheroute.runtime.profiles as runtime_profiles
import cacheroute_compat.runtime as legacy_runtime

modules = (cacheroute, cacheroute.compat, canonical_runtime,
           cacheroute.observability, cacheroute.runtime, runtime_profiles,
           legacy_runtime)
for module in modules:
    path = Path(module.__file__).resolve()
    print(f"{module.__name__}={path}")
    assert path.is_relative_to(Path(sys.prefix).resolve())
assert canonical_runtime.normalize_runtime_profile("modern") == "v1"
assert cacheroute.runtime.RuntimeProfile is runtime_profiles.RuntimeProfile
assert runtime_profiles.RuntimeProfile.normalize("modern") is runtime_profiles.RuntimeProfile.V1
assert runtime_profiles.RuntimeProfile.resolve_startup(
    "auto", v1_available=False
) is runtime_profiles.RuntimeProfile.LEGACY
assert canonical_runtime.__all__ == legacy_runtime.__all__
for name in canonical_runtime.__all__:
    assert getattr(legacy_runtime, name) is getattr(canonical_runtime, name)
for forbidden in (
    "kdn_server", "scheduler", "proxy", "instance", "client", "store",
    "model", "UI", "pydantic", "fastapi", "redis", "numpy", "torch",
    "sentence_transformers", "vllm", "lmcache",
):
    assert forbidden not in sys.modules, forbidden
print("dependency-light clean-wheel imports: passed")
""")
    assert "dependency-light clean-wheel imports: passed" in result.stdout
    print(result.stdout, end="")


def test_repository_only_namespaces_are_not_importable_from_clean_wheel(built_wheel, tmp_path):
    python = _create_isolated_environment(tmp_path / "negative-venv")
    subprocess.run([python, "-m", "pip", "install", "--no-deps", str(built_wheel)], check=True)
    result = _run_outside_repo(python, tmp_path / "outside-negative", """
import importlib.util
from pathlib import Path
import sys

for name in ("doc", "env", "log", "scripts", "test"):
    spec = importlib.util.find_spec(name)
    if name == "test":
        # CPython may supply its own stdlib test package. It must not resolve
        # from this environment's wheel installation directory.
        if spec is not None:
            assert Path(spec.origin).resolve().is_relative_to(Path(sys.base_prefix).resolve())
            assert "site-packages" not in Path(spec.origin).parts
    else:
        assert spec is None, name
print("repository-only clean-wheel imports: absent")
""")
    assert "repository-only clean-wheel imports: absent" in result.stdout
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
import kdn_server.domain.models as legacy_domain_models
import kdn_server.contracts.common as legacy_common
import kdn_server.contracts.errors as legacy_errors
import kdn_server.contracts.knowledge as legacy_knowledge
import kdn_server.contracts.cache_service as legacy_cache_service
import cacheroute.runtime
import cacheroute.runtime.state as runtime_state
import cacheroute.topology
import cacheroute.topology.lmcache as topology_lmcache
import cacheroute.cache
import cacheroute.cache.models as cache_models
import cacheroute.routing
import cacheroute.routing.queue as routing_queue
import cacheroute.contracts
import cacheroute.contracts.v1
import cacheroute.contracts.v1.common as canonical_common
import cacheroute.contracts.v1.errors as canonical_errors
import cacheroute.contracts.v1.knowledge as canonical_knowledge
import cacheroute.contracts.v1.cache_service as canonical_cache_service
import cacheroute.compat.runtime as canonical_runtime
import cacheroute_compat.runtime as legacy_runtime
from core.runtime_compat import normalize_runtime_profile
from kdn_server.domain import RuntimeProfile

modules = (core, core_runtime, proxy, instance, kdn_server, kdn_server.domain,
           legacy_domain_models, runtime_state, cacheroute.topology,
           topology_lmcache, cacheroute.cache, cache_models,
           cacheroute.routing, routing_queue,
           cacheroute.runtime, cacheroute.contracts, cacheroute.contracts.v1,
           canonical_common, canonical_errors, canonical_knowledge,
           canonical_cache_service, legacy_common, legacy_errors,
           legacy_knowledge, legacy_cache_service,
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
assert RuntimeProfile is cacheroute.runtime.RuntimeProfile
identity_pairs = (
    (runtime_state.StrEnum, legacy_domain_models.StrEnum),
    (runtime_state.Snapshot, legacy_domain_models.Snapshot),
    (runtime_state.StateTransitionError, legacy_domain_models.StateTransitionError),
    (topology_lmcache.LMCacheGatewayProfile, legacy_domain_models.LMCacheGatewayProfile),
    (topology_lmcache.LMCacheEndpoint, legacy_domain_models.LMCacheEndpoint),
    (cache_models.ObservationSource, legacy_domain_models.ObservationSource),
    (cache_models.ObservationConfidence, legacy_domain_models.ObservationConfidence),
    (cache_models.ObservationState, legacy_domain_models.ObservationState),
    (cache_models.CacheOperationType, legacy_domain_models.CacheOperationType),
    (cache_models.CacheOperationState, legacy_domain_models.CacheOperationState),
    (cache_models.CacheArtifact, legacy_domain_models.CacheArtifact),
    (cache_models.CacheReplicaObservation, legacy_domain_models.CacheReplicaObservation),
    (cache_models.CacheOperationTask, legacy_domain_models.CacheOperationTask),
    (routing_queue.QueueState, legacy_domain_models.QueueState),
    (routing_queue.QueueWork, legacy_domain_models.QueueWork),
)
assert all(canonical is legacy for canonical, legacy in identity_pairs)
assert runtime_state.utc_now is legacy_domain_models.utc_now
assert legacy_common.VersionedMessage is canonical_common.VersionedMessage
assert legacy_common.ContractModel is canonical_common.ContractModel
assert legacy_errors.OutcomeCode is canonical_errors.OutcomeCode
assert legacy_errors.ContractError is canonical_errors.ContractError
for canonical_module, legacy_module in (
    (canonical_knowledge, legacy_knowledge),
    (canonical_cache_service, legacy_cache_service),
):
    for name in canonical_module.__all__:
        canonical = getattr(canonical_module, name)
        assert getattr(legacy_module, name) is canonical
        assert getattr(cacheroute.contracts.v1, name) is canonical
        assert getattr(__import__("kdn_server.contracts", fromlist=[name]), name) is canonical
assert legacy_cache_service.INTENT_OPERATION_TYPES is canonical_cache_service.INTENT_OPERATION_TYPES
assert canonical_runtime.__all__ == legacy_runtime.__all__ == core_runtime.__all__
for name in canonical_runtime.__all__:
    canonical = getattr(canonical_runtime, name)
    assert getattr(legacy_runtime, name) is canonical
    assert getattr(core_runtime, name) is canonical
print("full clean-wheel public imports: passed")
""")
    assert "full clean-wheel public imports: passed" in result.stdout
    print(result.stdout, end="")
