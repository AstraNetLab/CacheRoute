"""Focused ownership and compatibility checks for KDN v1 service contracts."""

import ast
from enum import Enum
from pathlib import Path
import subprocess
import sys

import cacheroute.contracts.v1 as canonical_package
import cacheroute.contracts.v1.cache_service as canonical_cache
import cacheroute.contracts.v1.knowledge as canonical_knowledge
import kdn_server.contracts as legacy_package
import kdn_server.contracts.cache_service as legacy_cache
import kdn_server.contracts.knowledge as legacy_knowledge

ROOT = Path(__file__).resolve().parents[1]


def _public(module):
    return {name: getattr(module, name) for name in module.__all__}


def test_canonical_and_legacy_module_identity_and_ownership():
    for canonical, legacy in (
        (canonical_knowledge, legacy_knowledge),
        (canonical_cache, legacy_cache),
    ):
        assert canonical.__all__ == legacy.__all__
        for name, value in _public(canonical).items():
            assert getattr(legacy, name) is value
            assert getattr(canonical_package, name) is value
            assert getattr(legacy_package, name) is value
            if isinstance(value, type):
                assert value.__module__ == canonical.__name__


def test_response_aliases_remain_identical_objects():
    for name in (
        "RegisterKnowledgeResponse", "UpdateKnowledgeResponse",
        "ResolveKnowledgeResponse", "ListCompatibleArtifactsResponse",
        "QueryArtifactCompatibilityResponse", "ReportRequestOutcomeResponse",
    ):
        assert getattr(canonical_knowledge, name) is canonical_knowledge.KnowledgeResponse


def test_mapping_and_complete_package_exports_preserve_identity():
    assert legacy_cache.INTENT_OPERATION_TYPES is canonical_cache.INTENT_OPERATION_TYPES
    expected = set(canonical_knowledge.__all__) | set(canonical_cache.__all__)
    assert expected <= set(canonical_package.__all__)
    assert expected <= set(legacy_package.__all__)


def test_legacy_service_modules_are_import_only_shims():
    allowed = (ast.Expr, ast.ImportFrom)
    for relative in (
        "kdn_server/contracts/knowledge.py",
        "kdn_server/contracts/cache_service.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        assert all(isinstance(node, allowed) for node in tree.body)
        assert not any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body)


def test_canonical_imports_are_dependency_isolated_in_fresh_process():
    script = r'''
import sys
import cacheroute.contracts.v1
import cacheroute.contracts.v1.knowledge
import cacheroute.contracts.v1.cache_service
for forbidden in (
    "kdn_server", "scheduler", "proxy", "instance", "client", "store", "model",
    "UI", "fastapi", "redis", "numpy", "torch", "sentence_transformers",
    "vllm", "lmcache",
):
    assert forbidden not in sys.modules, forbidden
'''
    subprocess.run([sys.executable, "-I", "-c", script], cwd=ROOT.parent, check=True)
