"""Compatibility exports for canonical v1 Knowledge Service contracts."""

from typing import Literal

from pydantic import Field, model_validator

from cacheroute.cache import CacheArtifact
from cacheroute.contracts.v1.common import VersionedMessage
from cacheroute.contracts.v1.errors import ContractError, OutcomeCode
from cacheroute.contracts.v1.knowledge import (
    KnowledgeDescriptor, KnowledgeResponse, ListCompatibleArtifactsRequest,
    ListCompatibleArtifactsResponse, QueryArtifactCompatibilityRequest,
    QueryArtifactCompatibilityResponse, RegisterKnowledgeRequest,
    RegisterKnowledgeResponse, ReportRequestOutcomeRequest,
    ReportRequestOutcomeResponse, ResolveKnowledgeRequest, ResolveKnowledgeResponse,
    UpdateKnowledgeRequest, UpdateKnowledgeResponse,
)

__all__ = [
    "Literal", "Field", "model_validator", "CacheArtifact", "VersionedMessage",
    "ContractError", "OutcomeCode", "KnowledgeDescriptor", "KnowledgeResponse",
    "RegisterKnowledgeRequest", "RegisterKnowledgeResponse", "UpdateKnowledgeRequest",
    "UpdateKnowledgeResponse", "ResolveKnowledgeRequest", "ResolveKnowledgeResponse",
    "ListCompatibleArtifactsRequest", "ListCompatibleArtifactsResponse",
    "QueryArtifactCompatibilityRequest", "QueryArtifactCompatibilityResponse",
    "ReportRequestOutcomeRequest", "ReportRequestOutcomeResponse",
]
