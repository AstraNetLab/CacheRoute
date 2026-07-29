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
CANONICAL_PACKAGES = {
    "cacheroute", "cacheroute.compat", "cacheroute.observability",
    "cacheroute_compat",
}
GENERATED_PACKAGE_EXCLUDES = [
    "src", "src.*", "build", "build.*", "dist", "dist.*", "wheelhouse",
    "wheelhouse.*", ".venv", ".venv.*", "*.egg-info", "*.egg-info.*",
    ".pytest_cache", ".pytest_cache.*", "__pycache__", "__pycache__.*",
    "*.__pycache__", "*.__pycache__.*",
    ".mypy_cache", ".mypy_cache.*", ".ruff_cache", ".ruff_cache.*",
    "tests", "tests.*", "docs", "docs.*",
]


def test_no_unreviewed_functional_root_directories():
    tracked = {
        path.relative_to(ROOT).parts[0]
        for path in _tracked_files() if len(path.relative_to(ROOT).parts) > 1
    }
    assert tracked <= ALLOWED_TOP_LEVEL_DIRECTORIES


def test_transitional_explicit_packages_match_root_discovery():
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    configured = set(configuration["tool"]["setuptools"]["packages"])
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
    for relative in ("src/cacheroute_compat/__init__.py", "src/cacheroute_compat/runtime.py"):
        module = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        functional = [
            node for node in module.body
            if not isinstance(node, ast.ImportFrom)
            and not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        assert functional == []


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
