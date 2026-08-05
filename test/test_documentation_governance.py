"""Focused documentation-governance checks for the developer handbook."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "doc" / "developer-handbook"
APPROVED = [
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
]
STATUSES = ["Historical", "Current", "Transitional", "Target / Accepted", "Proposed", "Deprecated"]
BASE_README_INTRO_SHA256 = "e77ec9521e6e6112261d3d8231da15f635a051b8c6e6f437ec1513a542121aff"


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _readme_intro(text: str) -> str:
    return text.split("## Why CacheRoute?", 1)[0]


def test_all_approved_handbook_files_exist_and_readme_links_every_chapter():
    assert sorted(p.name for p in HANDBOOK.iterdir() if p.is_file()) == sorted(APPROVED)
    landing = _text("doc/developer-handbook/README.md")
    for name in APPROVED[1:]:
        assert f"]({name})" in landing, name


def test_root_readme_and_agents_link_handbook_and_same_pr_rule():
    assert "doc/developer-handbook/README.md" in _text("README.md")
    agents = _text("AGENTS.md")
    assert "doc/developer-handbook/README.md" in agents
    assert "update the relevant handbook chapter in the same PR" in agents


def _markdown_links(path: Path):
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
        target = (match.group(1) or "").strip()
        if not target or target.startswith(('#', 'http://', 'https://', 'mailto:')):
            continue
        yield target


def _assert_links_resolve(path: Path):
    for raw in _markdown_links(path):
        target = unquote(urlsplit(raw).path)
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        assert resolved.exists(), f"{path.relative_to(ROOT)} links to missing target {raw} -> {resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved}"


def test_repository_local_markdown_links_resolve_for_governed_files():
    for path in [*HANDBOOK.glob("*.md"), ROOT / "README.md", ROOT / "AGENTS.md"]:
        _assert_links_resolve(path)


def test_configured_packages_are_represented_in_package_map():
    configured = tomllib.loads(_text("pyproject.toml"))["tool"]["setuptools"]["packages"]
    package_map = _text("doc/developer-handbook/package-and-module-map.md")
    missing = [package for package in configured if f"`{package}`" not in package_map and package not in package_map]
    assert not missing


def _explicit_nonempty_all_modules():
    modules = []
    for path in sorted((ROOT / "src" / "cacheroute").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                if isinstance(node.value, (ast.List, ast.Tuple)) and node.value.elts:
                    module = ".".join(path.with_suffix("").relative_to(ROOT / "src").parts)
                    if module.endswith(".__init__"):
                        module = module.rsplit(".__init__", 1)[0]
                    modules.append(module)
    return modules


def test_explicit_public_all_modules_are_represented_in_api_catalog():
    catalog = _text("doc/developer-handbook/public-api-and-data-models.md")
    missing = [module for module in _explicit_nonempty_all_modules() if f"`{module}`" not in catalog]
    assert not missing


def test_status_vocabulary_defined_and_absent_targets_not_current():
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in HANDBOOK.glob("*.md"))
    for status in STATUSES:
        assert status in _text("doc/developer-handbook/README.md")
    for absent in ("cacheroute.knowledge", "cacheroute.integrations", "cacheroute.services", "cacheroute.plugins", "cacheroute.entrypoints"):
        assert absent in all_text
        assert not re.search(rf"`{re.escape(absent)}`[^\n|]*(?:\|[^\n|]*)*\|\s*Current\s*(?:\||$)", all_text)


def test_pr_183_observability_is_current_not_proposed_or_in_review():
    arch = _text("doc/developer-handbook/architecture-and-evolution.md")
    assert "PR #183 behavior is implemented and documented as Current" in arch
    forbidden = ["PR #183 behavior is Proposed", "PR #183 behavior is In review", "Once merged"]
    assert not any(item in arch for item in forbidden)


def test_handbook_docs_are_repository_only_not_runtime_packages():
    pyproject = _text("pyproject.toml")
    assert "doc.developer-handbook" not in pyproject
    assert '"doc"' not in pyproject


def test_root_readme_intro_unchanged_and_only_approved_additions():
    current = _text("README.md")
    normalized_intro = _readme_intro(current).replace('  <a href="doc/developer-handbook/README.md">Developer Handbook</a> •\n', '')
    assert hashlib.sha256(normalized_intro.encode()).hexdigest() == BASE_README_INTRO_SHA256
    base = subprocess.run(["git", "show", "HEAD:README.md"], cwd=ROOT, check=True, text=True, capture_output=True).stdout
    diff = subprocess.run(["git", "diff", "--unified=0", "HEAD", "--", "README.md"], cwd=ROOT, check=True, text=True, capture_output=True).stdout
    assert diff.count('+  <a href="doc/developer-handbook/README.md">Developer Handbook</a> •') == 1
    assert diff.count('| [`doc/developer-handbook/README.md`](doc/developer-handbook/README.md) | Developer and maintenance handbook') == 1
    removed = [line for line in diff.splitlines() if line.startswith('-') and not line.startswith('---')]
    assert removed == []
    assert "doc/developer-handbook/README.md" not in base
