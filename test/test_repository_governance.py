"""Repository checks that keep the Phase A migration reviewable."""

import ast
from pathlib import Path
import re


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


def test_no_unreviewed_functional_root_directories():
    current = {
        path.name for path in ROOT.iterdir()
        if path.is_dir() and path.name != "build" and not path.name.endswith(".egg-info")
    }
    assert current <= ALLOWED_TOP_LEVEL_DIRECTORIES


def test_legacy_compatibility_references_are_narrowly_allowlisted():
    references = set()
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or "build" in path.parts
            or "__pycache__" in path.parts
            or any(part.endswith(".egg-info") for part in path.parts)
        ):
            continue
        try:
            if "cacheroute_compat" in path.read_text(encoding="utf-8"):
                references.add(path.relative_to(ROOT))
        except UnicodeDecodeError:
            continue
    assert references <= LEGACY_REFERENCE_ALLOWLIST


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
    link_pattern = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")
    for markdown in ROOT.rglob("*.md"):
        if ".git" in markdown.parts:
            continue
        for raw_target in link_pattern.findall(markdown.read_text(encoding="utf-8")):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            if local and not (markdown.parent / local).resolve().exists():
                missing.append(f"{markdown.relative_to(ROOT)} -> {target}")
    assert missing == []
