"""Structural governance checks for the maintained developer handbook."""

import ast
import re
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "doc" / "developer-handbook"
CHAPTERS = {
    "README.md",
    "architecture-and-evolution.md",
    "package-and-module-map.md",
    "public-api-and-data-models.md",
    "runtime-flows.md",
    "configuration-and-interfaces.md",
    "compatibility-and-migrations.md",
    "development-and-validation.md",
    "documentation-governance.md",
    "glossary.md",
}
STATUSES = {
    "Historical", "Current", "Transitional", "Target / Accepted",
    "In review", "Proposed", "Deprecated",
}
LINK_RE = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
ABSENT_TARGETS = {"knowledge", "integrations", "services", "plugins", "entrypoints"}


def _markdown_files():
    return [ROOT / "README.md", ROOT / "AGENTS.md", *HANDBOOK.glob("*.md")]


def _explicit_nonempty_all(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                value = node.value
                if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                    return bool(value.elts)
                # Computed explicit exports (for example compat and v1 aggregation) are non-empty.
                return value is not None
    return False


def test_required_handbook_chapters_exist_and_are_linked():
    assert {path.name for path in HANDBOOK.glob("*.md")} == CHAPTERS
    landing = (HANDBOOK / "README.md").read_text(encoding="utf-8")
    for chapter in CHAPTERS - {"README.md"}:
        assert f"]({chapter})" in landing
    assert not (HANDBOOK / "__init__.py").exists()


def test_handbook_discovery_and_same_pr_governance():
    link = "doc/developer-handbook/README.md"
    assert link in (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert link in agents
    assert "same-PR handbook update" in agents
    assert "mandatory handbook-impact checklist" in agents


@pytest.mark.parametrize("markdown", _markdown_files(), ids=lambda path: str(path.relative_to(ROOT)))
def test_local_markdown_links_resolve(markdown):
    for raw in LINK_RE.findall(markdown.read_text(encoding="utf-8")):
        target = raw.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        assert (markdown.parent / target).resolve().exists(), f"{markdown}: {raw}"


def test_explicit_canonical_packages_are_in_package_map():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["setuptools"]["packages"]
    canonical = {name for name in packages if name == "cacheroute" or name.startswith("cacheroute.")}
    package_map = (HANDBOOK / "package-and-module-map.md").read_text(encoding="utf-8")
    for package in canonical:
        assert f"`{package}" in package_map or f"`{package}`" in package_map


def test_public_modules_with_explicit_all_are_catalogued():
    catalog = (HANDBOOK / "public-api-and-data-models.md").read_text(encoding="utf-8")
    source_root = ROOT / "src" / "cacheroute"
    for path in source_root.rglob("*.py"):
        if not _explicit_nonempty_all(path):
            continue
        relative = path.relative_to(ROOT / "src").with_suffix("")
        parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
        module = ".".join(parts)
        assert f"`{module}`" in catalog, module


def test_status_vocabulary_and_absent_targets_are_accurate():
    landing = (HANDBOOK / "README.md").read_text(encoding="utf-8")
    glossary = (HANDBOOK / "glossary.md").read_text(encoding="utf-8")
    for status in STATUSES:
        assert status in landing
        assert status in glossary
    package_map = (HANDBOOK / "package-and-module-map.md").read_text(encoding="utf-8")
    for package in ABSENT_TARGETS:
        assert not (ROOT / "src" / "cacheroute" / package).exists()
        rows = [line for line in package_map.splitlines() if f"`cacheroute.{package}" in line]
        assert rows and all("Target / Accepted" in row for row in rows)


def test_documentation_is_excluded_from_explicit_wheel_packages():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = config["tool"]["setuptools"]
    assert "find" not in setuptools
    assert all(not (name == "doc" or name.startswith("doc.")) for name in setuptools["packages"])
