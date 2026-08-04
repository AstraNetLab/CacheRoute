"""Structural governance checks for the maintained developer handbook."""

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HANDBOOK = ROOT / "doc" / "developer-handbook"
CHAPTERS = {
    "README.md", "architecture-and-evolution.md", "package-and-module-map.md",
    "public-api-and-data-models.md", "runtime-flows.md",
    "configuration-and-interfaces.md", "compatibility-and-migrations.md",
    "development-and-validation.md", "documentation-governance.md", "glossary.md",
}
STATUSES = {"Historical", "Current", "Transitional", "Target / Accepted", "In review", "Proposed", "Deprecated"}
LINK_RE = re.compile(r"(?<!!)\[[^]]*\]\(([^)]+)\)")
API_HEADING_RE = re.compile(r"^## API: `([^`]+)`$", re.MULTILINE)
ABSENT_TARGETS = {"knowledge", "integrations", "services", "plugins", "entrypoints"}
REQUIRED_CONFIG_SECTIONS = {
    "Runtime profiles and injection modes", "Environment variables",
    "Service hosts and ports", "CLI flags", "HTTP and debug endpoints",
    "Request fields", "SSE metadata", "Feature switches and packaging/runtime options",
}
REQUIRED_API_ENTRIES = {
    "cacheroute.runtime", "cacheroute.runtime.state", "cacheroute.topology",
    "cacheroute.cache", "cacheroute.routing", "cacheroute.contracts",
    "cacheroute.contracts.v1", "cacheroute.contracts.v1.common",
    "cacheroute.contracts.v1.errors", "cacheroute.contracts.v1.knowledge",
    "cacheroute.contracts.v1.cache_service", "cacheroute.compat",
    "cacheroute.compat.runtime", "cacheroute_compat", "cacheroute_compat.runtime",
    "KDN contract forwarding modules", "cacheroute.observability",
    "cacheroute.observability.v1",
}


def _markdown_files():
    return [ROOT / "README.md", ROOT / "AGENTS.md", *sorted(HANDBOOK.glob("*.md"))]


def _explicit_nonempty_all(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            return bool(node.value.elts)
        return node.value is not None  # computed explicit export list
    return False


def _api_sections(text: str) -> dict[str, str]:
    matches = list(API_HEADING_RE.finditer(text))
    return {
        match.group(1): text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        for index, match in enumerate(matches)
    }


def test_required_handbook_chapters_exist_and_are_linked():
    assert {path.name for path in HANDBOOK.glob("*.md")} == CHAPTERS
    landing = (HANDBOOK / "README.md").read_text(encoding="utf-8")
    assert all(f"]({chapter})" in landing for chapter in CHAPTERS - {"README.md"})
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


def test_each_explicit_canonical_package_has_a_package_map_row():
    packages = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["packages"]
    canonical = {name for name in packages if name == "cacheroute" or name.startswith("cacheroute.")}
    rows = [line for line in (HANDBOOK / "package-and-module-map.md").read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    for package in canonical:
        assert any(f"`{package}`" in row for row in rows), package


def test_each_public_module_with_explicit_all_has_an_api_entry():
    sections = _api_sections((HANDBOOK / "public-api-and-data-models.md").read_text(encoding="utf-8"))
    for path in (ROOT / "src" / "cacheroute").rglob("*.py"):
        if not _explicit_nonempty_all(path):
            continue
        relative = path.relative_to(ROOT / "src").with_suffix("")
        module = ".".join(relative.parts[:-1] if relative.name == "__init__" else relative.parts)
        assert module in sections, module


def test_required_api_entries_have_structured_status_evidence_and_reference():
    sections = _api_sections((HANDBOOK / "public-api-and-data-models.md").read_text(encoding="utf-8"))
    assert REQUIRED_API_ENTRIES <= sections.keys()
    for module in REQUIRED_API_ENTRIES:
        section = sections[module]
        assert "**Status:**" in section, module
        assert "**Exports" in section, module
        assert "**Evidence:**" in section, module
        assert "**Example" in section, module


def test_status_vocabulary_is_defined_and_absent_targets_are_never_current():
    landing = (HANDBOOK / "README.md").read_text(encoding="utf-8")
    glossary = (HANDBOOK / "glossary.md").read_text(encoding="utf-8")
    assert all(status in landing and status in glossary for status in STATUSES)
    for package in ABSENT_TARGETS:
        assert not (ROOT / "src" / "cacheroute" / package).exists()
        marker = f"`cacheroute.{package}"
        for markdown in HANDBOOK.glob("*.md"):
            text = markdown.read_text(encoding="utf-8")
            # Catch common prose/status variants without forbidding a sentence
            # that contrasts Current root code with its absent target owner.
            prohibited = (
                rf"(?:\*\*)?Current(?:\*\*)?\s+{re.escape(marker)}",
                rf"{re.escape(marker)}(?:`)?\s+(?:is|—|:)\s+(?:\*\*)?Current(?:\*\*)?",
                rf"status\s*[:=]\s*(?:\*\*)?Current(?:\*\*)?.{{0,80}}{re.escape(marker)}",
            )
            assert not any(re.search(pattern, text, re.IGNORECASE) for pattern in prohibited), (markdown, package)
            for row in text.splitlines():
                if row.startswith("|") and marker in row:
                    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
                    # Package-map status is its fourth column; other target rows must use an explicit non-Current label.
                    status_cells = cells[3:4] if markdown.name == "package-and-module-map.md" else cells
                    assert all(cell != "Current" and cell != "**Current**" for cell in status_cells), (markdown, row)


def test_current_cacheroute_meta_and_kdn_runtime_corrections_are_marked():
    text = (HANDBOOK / "configuration-and-interfaces.md").read_text(encoding="utf-8")
    meta_row = next(line for line in text.splitlines() if "cacheroute-meta-no-request-id" in line)
    assert "ProxyTask.request_id" in meta_row
    assert "does not currently emit `request_id`" in meta_row
    assert "`request_id`, `injection_mode`" not in meta_row

    error_row = next(line for line in text.splitlines() if "cacheroute-meta-error" in line)
    assert "unversioned operational string" in error_row
    assert "not `ContractErrorDetail`" in error_row

    advertise_row = next(line for line in text.splitlines() if "kdn-advertise-registration" in line)
    assert "missing Scheduler URL or either advertise host/port skips registration" in advertise_row
    assert "demo_kdn.py" in advertise_row

    efficiency_row = next(line for line in text.splitlines() if "kdn-network-efficiency" in line)
    assert "accepts a float without range rejection" in efficiency_row
    assert "clamps runtime efficiency to `[0.01, 1.0]`" in efficiency_row


def test_configuration_catalog_has_stable_sections_and_tables():
    text = (HANDBOOK / "configuration-and-interfaces.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (.+)$", text, re.MULTILINE))
    assert REQUIRED_CONFIG_SECTIONS <= headings
    for heading in REQUIRED_CONFIG_SECTIONS:
        section = text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]
        assert "|---" in section, heading
    for required in ("SCHEDULER_MODEL_PATH", "PROXY_CP_URL", "INSTANCE_RESOURCE_MONITOR_ENABLE", "KDN_NETWORK_ENABLE", "cacheroute_meta", "max_tokens"):
        assert f"`{required}`" in text


def test_endpoint_catalog_uses_complete_kdn_and_proxy_ui_paths():
    text = (HANDBOOK / "configuration-and-interfaces.md").read_text(encoding="utf-8")
    kdn_paths = {
        "/knowledge/snapshot", "/knowledge/register_text", "/knowledge/build_kv",
        "/knowledge/search/text", "/knowledge/delete", "/knowledge/purge_all",
        "/knowledge/inject_ready_kv", "/knowledge/pool_status",
    }
    proxy_ui_paths = {
        "/", "/api/config", "/api/proxy/healthz", "/api/proxy/status",
        "/api/proxy/instances", "/api/proxy/resources", "/api/proxy/topology",
        "/api/proxy/loads", "/api/scheduler/proxy",
    }
    endpoint_rows = {
        cells[0]: cells[1]
        for line in text.splitlines()
        if line.startswith("|")
        for cells in ([cell.strip() for cell in line.strip().strip("|").split("|")],)
        if len(cells) >= 2
    }
    assert all(f"`{path}`" in endpoint_rows["KDN"] for path in kdn_paths)
    assert all(f"`{path}`" in endpoint_rows["Proxy UI"] for path in proxy_ui_paths)
    assert "`/register_text`" not in endpoint_rows["KDN"]
    assert "`/status`" not in endpoint_rows["Proxy UI"]


def test_documentation_is_excluded_from_explicit_wheel_packages():
    setuptools = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
    assert "find" not in setuptools
    assert all(not (name == "doc" or name.startswith("doc.")) for name in setuptools["packages"])
