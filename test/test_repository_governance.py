"""Repository checks that keep the Phase A migration reviewable."""

import ast
from fnmatch import fnmatchcase
import os
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TOP_LEVEL_DIRECTORIES = {
    ".assets", ".git", ".github", ".pytest_cache", "UI", "__pycache__",
    "client", "core", "data", "doc", "env", "instance", "kdn_server",
    "log", "model", "proxy", "scheduler", "scripts", "src", "store",
    "test", "util",
}
LEGACY_REFERENCE_ALLOWLIST = {
    Path("core/README.md"),
    Path("doc/package_migration_phase_a.md"),
    Path("pyproject.toml"),
    Path("src/cacheroute_compat/__init__.py"),
    Path("src/cacheroute_compat/runtime.py"),
    Path("test/test_repository_governance.py"),
    Path("test/test_runtime_compat.py"),
    Path("test/test_wheel_install.py"),
}
OBSERVABILITY_REFERENCE_ALLOWLIST = {
    Path("doc/package_migration_phase_a.md"),
    Path("test/test_repository_governance.py"),
}
KDN_CONTRACT_COMPATIBILITY_ALLOWLIST = {
    Path("kdn_server/contracts/__init__.py"),
    Path("kdn_server/contracts/knowledge.py"),
    Path("kdn_server/contracts/cache_service.py"),
    Path("test/test_contract_foundation.py"),
    Path("test/test_contract_service_migration.py"),
    Path("test/test_repository_governance.py"),
    Path("test/test_wheel_install.py"),
}
CANONICAL_PACKAGES = {
    "cacheroute", "cacheroute.compat", "cacheroute.observability",
    "cacheroute.runtime", "cacheroute.topology", "cacheroute.cache",
    "cacheroute.routing", "cacheroute.contracts", "cacheroute.contracts.v1",
    "cacheroute_compat",
}
REPOSITORY_ONLY_PACKAGE_PREFIXES = {
    "doc", "env", "log", "scripts", "test",
}
SOURCE_BOOTSTRAP_ENTRYPOINTS = {
    Path("client/client.py"),
    Path("client/kv_timing_sender.py"),
    Path("kdn_server/kdn_register_cli.py"),
    Path("scheduler/scheduler_cli.py"),
    Path("scripts/validate_v1_kdn_roundtrip.py"),
    Path("store/knowledge_build.py"),
    Path("test/demo_client.py"),
    Path("test/demo_instance.py"),
    Path("test/demo_kdn.py"),
    Path("test/demo_proxy.py"),
    Path("test/demo_scheduler.py"),
    Path("util/kdn_build_kv.py"),
}
GUARDED_SOURCE_BOOTSTRAP_MODULES = {
    Path("client/client.py"),
    Path("client/kv_timing_sender.py"),
    Path("kdn_server/kdn_register_cli.py"),
    Path("scheduler/scheduler_cli.py"),
    Path("scripts/validate_v1_kdn_roundtrip.py"),
    Path("store/knowledge_build.py"),
    Path("util/kdn_build_kv.py"),
}
SYS_PATH_ALLOWLIST = SOURCE_BOOTSTRAP_ENTRYPOINTS | {
    Path("conftest.py"),
    Path("test/test_demo_instance_ui.py"),
    Path("test/test_namespace_layout.py"),
    Path("test/test_repository_governance.py"),
    Path("test/test_wheel_install.py"),
}
GENERATED_PACKAGE_EXCLUDES = [
    "src", "src.*", "build", "build.*", "dist", "dist.*", "wheelhouse",
    "wheelhouse.*", ".venv", ".venv.*", "*.egg-info", "*.egg-info.*",
    ".pytest_cache", ".pytest_cache.*", "__pycache__", "__pycache__.*",
    "*.__pycache__", "*.__pycache__.*",
    ".mypy_cache", ".mypy_cache.*", ".ruff_cache", ".ruff_cache.*",
    "tests", "tests.*", "docs", "docs.*",
    *REPOSITORY_ONLY_PACKAGE_PREFIXES,
    *(f"{prefix}.*" for prefix in REPOSITORY_ONLY_PACKAGE_PREFIXES),
]


def _has_package_prefix(package, prefixes):
    return any(package == prefix or package.startswith(f"{prefix}.") for prefix in prefixes)


def test_no_unreviewed_functional_root_directories():
    tracked = {
        path.relative_to(ROOT).parts[0]
        for path in _tracked_files() if len(path.relative_to(ROOT).parts) > 1
    }
    assert tracked <= ALLOWED_TOP_LEVEL_DIRECTORIES


def test_transitional_explicit_packages_match_root_discovery():
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    configured = set(configuration["tool"]["setuptools"]["packages"])
    assert not any(
        _has_package_prefix(package, REPOSITORY_ONLY_PACKAGE_PREFIXES)
        for package in configured
    )
    discovered_root = _discover_root_namespace_packages()
    assert CANONICAL_PACKAGES <= configured
    assert configured - CANONICAL_PACKAGES == discovered_root


def _discover_root_namespace_packages():
    packages = set()
    for directory, child_directories, _files in os.walk(ROOT):
        relative = Path(directory).relative_to(ROOT)
        if relative == Path("."):
            child_directories[:] = [name for name in child_directories if not name.startswith(".")]
            continue
        package = ".".join(relative.parts)
        if any(fnmatchcase(package, pattern) for pattern in GENERATED_PACKAGE_EXCLUDES):
            child_directories[:] = []
            continue
        if not any(part.startswith(".") for part in relative.parts):
            packages.add(package)
    return packages


def test_legacy_compatibility_references_are_narrowly_allowlisted():
    references = _files_containing("cacheroute_compat")
    assert references <= LEGACY_REFERENCE_ALLOWLIST


def test_observability_legacy_references_are_narrowly_allowlisted():
    assert not (ROOT / "cacheroute_observability").exists()
    references = _files_containing("cacheroute_observability")
    assert references <= OBSERVABILITY_REFERENCE_ALLOWLIST


def test_legacy_kdn_contract_ownership_references_are_narrowly_allowlisted():
    legacy_modules = {
        "kdn_server.contracts", "kdn_server.contracts.knowledge",
        "kdn_server.contracts.cache_service",
    }
    references = set()
    for path in _tracked_files():
        relative = path.relative_to(ROOT)
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        stale = any(
            isinstance(node, ast.ImportFrom)
            and node.module in legacy_modules
            or isinstance(node, ast.Import)
            and any(alias.name in legacy_modules for alias in node.names)
            or isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and any(module in node.value for module in legacy_modules)
            for node in ast.walk(tree)
        )
        if stale:
            references.add(relative)
    assert references <= KDN_CONTRACT_COMPATIBILITY_ALLOWLIST


def _files_containing(needle):
    references = set()
    for path in _tracked_files():
        try:
            if needle in path.read_text(encoding="utf-8"):
                references.add(path.relative_to(ROOT))
        except UnicodeDecodeError:
            continue
    return references


def _tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True,
    )
    return tuple(
        ROOT / raw.decode() for raw in result.stdout.split(b"\0") if raw
    )


def test_legacy_shim_contains_imports_only():
    for relative in (
        "src/cacheroute_compat/__init__.py", "src/cacheroute_compat/runtime.py",
        "kdn_server/contracts/common.py", "kdn_server/contracts/errors.py",
        "kdn_server/contracts/knowledge.py", "kdn_server/contracts/cache_service.py",
    ):
        module = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        functional = [
            node for node in module.body
            if not isinstance(node, ast.ImportFrom)
            and not (
                isinstance(node, ast.Assign)
                and all(
                    isinstance(target, ast.Name) and target.id == "__all__"
                    for target in node.targets
                )
            )
            and not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        assert functional == []


def test_migrated_contract_implementations_are_canonical_only():
    domain = (ROOT / "kdn_server/domain/models.py").read_text(encoding="utf-8")
    assert "class RuntimeProfile" not in domain
    tree = ast.parse(domain)
    assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)
    for relative in (
        "kdn_server/contracts/common.py", "kdn_server/contracts/errors.py",
        "kdn_server/contracts/knowledge.py", "kdn_server/contracts/cache_service.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)


def test_canonical_service_contract_dependencies_are_allowed():
    allowed = {
        "__future__", "datetime", "enum", "typing", "pydantic",
        "cacheroute.runtime", "cacheroute.topology", "cacheroute.cache",
        "cacheroute.contracts.v1.common", "cacheroute.contracts.v1.errors",
    }
    for relative in (
        "src/cacheroute/contracts/v1/knowledge.py",
        "src/cacheroute/contracts/v1/cache_service.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports = {
            node.module for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert imports <= allowed


def test_runtime_package_init_remains_dependency_free():
    tree = ast.parse((ROOT / "src/cacheroute/runtime/__init__.py").read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }
    assert imports == {"profiles"}


def test_source_bootstraps_stay_at_test_and_entrypoint_boundaries():
    config_tree = ast.parse((ROOT / "core/config.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(
        alias.name == "sys" for alias in node.names
    ) for node in config_tree.body)
    assert "sys.path" not in (ROOT / "core/config.py").read_text(encoding="utf-8")

    files_with_sys_path = {
        path.relative_to(ROOT) for path in _tracked_files()
        if path.suffix == ".py" and "sys.path" in path.read_text(encoding="utf-8")
    }
    assert files_with_sys_path <= SYS_PATH_ALLOWLIST

    project_roots = {"core", "kdn_server", "proxy", "instance", "scheduler", "cacheroute"}
    for relative in GUARDED_SOURCE_BOOTSTRAP_MODULES:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        bootstrap_index = next(
            index for index, node in enumerate(tree.body)
            if isinstance(node, ast.FunctionDef) and node.name == "_bootstrap_source_checkout"
        )
        guard_index = next(
            index for index, node in enumerate(tree.body)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__package__"
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_bootstrap_source_checkout"
                for child in ast.walk(node)
            )
        )
        project_import_indexes = [
            index for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in project_roots
            or isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] in project_roots for alias in node.names
            )
        ]
        assert bootstrap_index < guard_index < min(project_import_indexes)
        function = tree.body[bootstrap_index]
        assert any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
            and node.attr == "path"
            for node in ast.walk(function)
        )


def test_local_markdown_links_resolve():
    missing = []
    inline_pattern = re.compile(r"!?\[[^]]*]\(([^)]+)\)")
    reference_pattern = re.compile(r"^\s*\[[^]]+]\s*:\s*(\S+)", re.MULTILINE)
    fence_pattern = re.compile(r"^\s*```.*?^\s*```\s*$", re.MULTILINE | re.DOTALL)
    for markdown in (path for path in _tracked_files() if path.suffix == ".md"):
        text = fence_pattern.sub("", markdown.read_text(encoding="utf-8"))
        targets = inline_pattern.findall(text) + reference_pattern.findall(text)
        for raw_target in targets:
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            if local and not (markdown.parent / local).resolve().exists():
                missing.append(f"{markdown.relative_to(ROOT)} -> {target}")
    assert missing == []
