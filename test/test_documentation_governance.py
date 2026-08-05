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


def _is_local_markdown_target(target: str) -> bool:
    return bool(target) and not target.startswith(("#", "http://", "https://", "mailto:"))


def _markdown_links(path: Path):
    text = path.read_text(encoding="utf-8")
    reference_targets: dict[str, str] = {}
    for match in re.finditer(r"(?m)^\s{0,3}\[([^\]]+)\]:\s+(\S+)", text):
        label = match.group(1).strip().casefold()
        target = match.group(2).strip()
        reference_targets[label] = target
        if _is_local_markdown_target(target):
            yield target

    # Inline links and image links: [text](target), ![alt](target).
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        target = (match.group(1) or "").strip()
        if _is_local_markdown_target(target):
            yield target

    # Reference-style links and images: [text][label], ![alt][label].
    for match in re.finditer(r"!?\[[^\]]+\]\[([^\]]+)\]", text):
        label = (match.group(1) or "").strip().casefold()
        target = reference_targets.get(label)
        if target and _is_local_markdown_target(target):
            yield target


def _assert_links_resolve(path: Path):
    for raw in _markdown_links(path):
        target = unquote(urlsplit(raw).path)
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        assert resolved.exists(), f"{path.relative_to(ROOT)} links to missing target {raw} -> {resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved}"


def _tracked_markdown_files():
    result = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, check=True, text=True, capture_output=True)
    return [ROOT / line for line in result.stdout.splitlines() if line]


def test_repository_local_markdown_links_resolve_for_tracked_docs():
    for path in _tracked_markdown_files():
        _assert_links_resolve(path)


def test_configured_packages_are_represented_in_package_map():
    configured = tomllib.loads(_text("pyproject.toml"))["tool"]["setuptools"]["packages"]
    package_map = _text("doc/developer-handbook/package-and-module-map.md")
    table, inventory = package_map.split("## Explicitly configured package coverage", 1)
    canonical = {package for package in configured if package == "cacheroute" or package.startswith("cacheroute.") or package == "cacheroute_compat"}
    missing_canonical_rows = [package for package in canonical if re.search(rf"^\| [^\n]*`{re.escape(package)}`", table, re.MULTILINE) is None]
    missing_inventory = [package for package in configured if f"`{package}`" not in inventory]
    assert not missing_canonical_rows
    assert not missing_inventory


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


def test_explicit_public_all_modules_have_dedicated_api_catalog_entry():
    catalog = _text("doc/developer-handbook/public-api-and-data-models.md")
    missing = []
    for module in _explicit_nonempty_all_modules():
        dedicated_header = f"### `{module}`" in catalog
        dedicated_row = re.search(rf"^\| `{re.escape(module)}` \|", catalog, re.MULTILINE) is not None
        if not (dedicated_header or dedicated_row):
            missing.append(module)
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



def test_handbook_contains_no_repository_external_machine_paths():
    forbidden = ("/workspace/", "/llm-stack/", "/home/", "/Users/")
    offenders = {
        path.relative_to(ROOT): token
        for path in HANDBOOK.glob("*.md")
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    }
    assert not offenders

def test_root_readme_intro_unchanged_and_only_approved_additions():
    current = _text("README.md")
    target = "doc/developer-handbook/README.md"
    nav_link = f'<a href="{target}">Developer Handbook</a>'
    table_row = f'| [`{target}`]({target}) | Developer and maintenance handbook for public surfaces, architecture status, runtime flows, compatibility, and validation governance. |'

    normalized_intro = _readme_intro(current).replace(f'  {nav_link} •\n', '')
    assert hashlib.sha256(normalized_intro.encode()).hexdigest() == BASE_README_INTRO_SHA256

    top_nav_match = re.search(r'<p align="center">\n(?P<nav>.*?<a href="#documentation">Docs</a>\n)</p>', current, re.DOTALL)
    if top_nav_match is None:
        top_nav_match = re.search(r'<p align="center">\n(?P<nav>.*?)</p>', current, re.DOTALL)
    assert top_nav_match is not None
    top_nav = top_nav_match.group("nav")
    assert top_nav.count(nav_link) == 1
    assert current.count(table_row) == 1
    assert current.count(f'<a href="{target}">Developer Handbook</a>') == 1
    assert current.count(f'[`{target}`]({target})') == 1

    # The root README must stay a high-level overview. The handbook content
    # itself lives under doc/developer-handbook, so the root README should not
    # grow a prose section that duplicates governance details.
    assert "## Developer Handbook" not in current
    assert "# CacheRoute Developer and Maintenance Handbook" not in current
    assert current.count("same PR") == 0
