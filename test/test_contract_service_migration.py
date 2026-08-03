"""Focused ownership and compatibility checks for KDN v1 service contracts."""

import ast
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from cacheroute.cache import CacheArtifact
import cacheroute.contracts.v1 as canonical_package
import cacheroute.contracts.v1.cache_service as canonical_cache
import cacheroute.contracts.v1.knowledge as canonical_knowledge
import kdn_server.contracts as legacy_package
import kdn_server.contracts.cache_service as legacy_cache
import kdn_server.contracts.knowledge as legacy_knowledge
from kdn_server.contracts.cache_service import (
    CacheArtifact as LegacyCacheArtifact,
    CacheOperationType as LegacyCacheOperationType,
    OutcomeCode as LegacyCacheOutcomeCode,
    TokenInput as LegacyTokenInput,
)
from kdn_server.contracts.knowledge import (
    CacheArtifact as LegacyKnowledgeCacheArtifact,
    ContractError as LegacyKnowledgeContractError,
    OutcomeCode as LegacyKnowledgeOutcomeCode,
    VersionedMessage as LegacyKnowledgeVersionedMessage,
)
from cacheroute.contracts.v1.errors import ContractErrorDetail, OutcomeCode

ROOT = Path(__file__).resolve().parents[1]


def _public(module):
    return {name: getattr(module, name) for name in module.__all__}


def test_canonical_and_legacy_module_identity_and_ownership():
    for canonical, legacy in (
        (canonical_knowledge, legacy_knowledge),
        (canonical_cache, legacy_cache),
    ):
        for name, value in _public(canonical).items():
            assert getattr(legacy, name) is value
            assert getattr(canonical_package, name) is value
            assert getattr(legacy_package, name) is value
            if isinstance(value, type):
                assert value.__module__ == canonical.__name__
    assert canonical_cache.TierLevel.__module__ == canonical_cache.__name__


def test_legacy_auxiliary_direct_imports_preserve_identity():
    assert LegacyCacheArtifact is CacheArtifact
    assert LegacyCacheOperationType is canonical_cache.CacheOperationType
    assert LegacyTokenInput is canonical_package.TokenInput
    assert LegacyCacheOutcomeCode is OutcomeCode
    assert LegacyKnowledgeCacheArtifact is CacheArtifact
    assert LegacyKnowledgeVersionedMessage is canonical_package.VersionedMessage
    assert LegacyKnowledgeContractError is canonical_package.ContractError
    assert LegacyKnowledgeOutcomeCode is OutcomeCode


def test_legacy_star_imports_preserve_the_historical_surface():
    knowledge_namespace = {}
    cache_namespace = {}
    exec("from kdn_server.contracts.knowledge import *", knowledge_namespace)
    exec("from kdn_server.contracts.cache_service import *", cache_namespace)
    historical_knowledge = {
        "Literal", "Field", "model_validator", "CacheArtifact", "VersionedMessage",
        "ContractError", "OutcomeCode",
    }
    historical_cache = {
        "datetime", "timedelta", "Enum", "ClassVar", "AwareDatetime", "Field",
        "field_validator", "model_validator", "RuntimeProfile", "CacheArtifact",
        "CacheOperationState", "CacheOperationTask", "CacheOperationType",
        "CacheReplicaObservation", "LMCacheEndpoint", "ContractModel",
        "GatewayTargetedRequest", "SupportState", "TokenInput", "VersionedMessage",
        "utc_now", "ContractErrorDetail", "OutcomeCode",
    }
    assert historical_knowledge <= knowledge_namespace.keys()
    assert historical_cache <= cache_namespace.keys()
    assert knowledge_namespace["CacheArtifact"] is CacheArtifact
    assert knowledge_namespace["OutcomeCode"] is OutcomeCode
    assert cache_namespace["CacheOperationType"] is canonical_cache.CacheOperationType
    assert cache_namespace["TokenInput"] is canonical_package.TokenInput


def test_response_aliases_remain_identical_objects():
    for name in (
        "RegisterKnowledgeResponse", "UpdateKnowledgeResponse",
        "ResolveKnowledgeResponse", "ListCompatibleArtifactsResponse",
        "QueryArtifactCompatibilityResponse", "ReportRequestOutcomeResponse",
    ):
        assert getattr(canonical_knowledge, name) is canonical_knowledge.KnowledgeResponse


def _artifact():
    return CacheArtifact(
        knowledge_id="knowledge", model_profile="model",
        tokenizer_profile="tokenizer", cache_data_profile="layout",
        compatibility_profile_id="compatible", runtime_profile="v1",
    )


def test_knowledge_descriptor_defaults_freezing_and_extra_rejection():
    descriptor = canonical_knowledge.KnowledgeDescriptor(
        runtime_profile="v1", knowledge_id="knowledge",
    )
    assert descriptor.revision == "1"
    assert descriptor.content_reference is None
    assert tuple(type(descriptor).model_fields) == (
        "contract_version", "runtime_profile", "request_id", "correlation_id",
        "timestamp", "knowledge_id", "revision", "content_reference",
    )
    with pytest.raises(ValidationError, match="frozen"):
        descriptor.revision = "2"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        canonical_knowledge.KnowledgeDescriptor(
            runtime_profile="v1", knowledge_id="knowledge", secret="value",
        )
    with pytest.raises(ValidationError, match="startup-only"):
        canonical_knowledge.KnowledgeDescriptor(
            runtime_profile="auto", knowledge_id="knowledge",
        )


def test_every_knowledge_request_round_trips_through_json():
    requests = (
        canonical_knowledge.RegisterKnowledgeRequest(
            runtime_profile="v1", knowledge_id="knowledge", content_reference="ref",
        ),
        canonical_knowledge.UpdateKnowledgeRequest(
            runtime_profile="v1", knowledge_id="knowledge", revision="2",
        ),
        canonical_knowledge.ResolveKnowledgeRequest(
            runtime_profile="v1", knowledge_id="knowledge",
        ),
        canonical_knowledge.ListCompatibleArtifactsRequest(
            runtime_profile="v1", knowledge_id="knowledge",
        ),
        canonical_knowledge.QueryArtifactCompatibilityRequest(
            runtime_profile="v1", artifact=_artifact(),
        ),
        canonical_knowledge.ReportRequestOutcomeRequest(
            runtime_profile="v1", knowledge_id="knowledge",
            outcome=OutcomeCode.FAILED, operation_id="operation",
        ),
    )
    for request in requests:
        assert type(request).model_validate_json(request.model_dump_json()) == request


def test_knowledge_response_outcome_and_alias_behavior():
    success = canonical_knowledge.KnowledgeResponse(runtime_profile="v1")
    assert canonical_knowledge.KnowledgeResponse.model_validate_json(
        success.model_dump_json()
    ) == success
    with pytest.raises(ValidationError, match="successful responses cannot carry"):
        canonical_knowledge.KnowledgeResponse(
            runtime_profile="v1",
            error=ContractErrorDetail(code=OutcomeCode.FAILED, message="failed"),
        )
    with pytest.raises(ValidationError, match="matching error detail"):
        canonical_knowledge.KnowledgeResponse(
            runtime_profile="v1", outcome=OutcomeCode.FAILED,
            error=ContractErrorDetail(code=OutcomeCode.STALE, message="stale"),
        )
    failed = canonical_knowledge.KnowledgeResponse(
        runtime_profile="v1", outcome=OutcomeCode.FAILED,
        error=ContractErrorDetail(code=OutcomeCode.FAILED, message="failed"),
    )
    assert failed.error.code is failed.outcome
    with pytest.raises(ValidationError, match="fallback eligible"):
        canonical_knowledge.KnowledgeResponse(
            runtime_profile="v1", outcome=OutcomeCode.TEXT_FALLBACK,
            error=ContractErrorDetail(code=OutcomeCode.TEXT_FALLBACK, message="fallback"),
        )
    for alias_name in (
        "RegisterKnowledgeResponse", "UpdateKnowledgeResponse",
        "ResolveKnowledgeResponse", "ListCompatibleArtifactsResponse",
        "QueryArtifactCompatibilityResponse", "ReportRequestOutcomeResponse",
    ):
        response_alias = getattr(canonical_knowledge, alias_name)
        fallback = response_alias(
            runtime_profile="v1", outcome=OutcomeCode.TEXT_FALLBACK,
            error=ContractErrorDetail(
                code=OutcomeCode.TEXT_FALLBACK, message="fallback",
                fallback_eligible=True,
            ),
        )
        assert type(fallback) is canonical_knowledge.KnowledgeResponse
        assert response_alias.model_validate_json(fallback.model_dump_json()) == fallback
        with pytest.raises(ValidationError, match="matching error detail"):
            response_alias(runtime_profile="v1", outcome=OutcomeCode.FAILED)


def test_mapping_and_complete_package_exports_preserve_identity():
    assert legacy_cache.INTENT_OPERATION_TYPES is canonical_cache.INTENT_OPERATION_TYPES
    expected = set(canonical_knowledge.__all__) | set(canonical_cache.__all__)
    assert expected <= set(canonical_package.__all__)
    assert expected <= set(legacy_package.__all__)


def test_legacy_service_modules_are_import_only_shims():
    for relative in (
        "kdn_server/contracts/knowledge.py",
        "kdn_server/contracts/cache_service.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        assert all(
            isinstance(node, (ast.Expr, ast.ImportFrom))
            or isinstance(node, ast.Assign)
            and all(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
            for node in tree.body
        )
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
