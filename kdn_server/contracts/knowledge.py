"""Storage-neutral Knowledge Service request and response contracts."""
from typing import Literal

from pydantic import Field, model_validator

from cacheroute.cache import CacheArtifact
from cacheroute.contracts.v1.common import VersionedMessage
from cacheroute.contracts.v1.errors import ContractError, OutcomeCode


class KnowledgeDescriptor(VersionedMessage):
    knowledge_id: str = Field(min_length=1)
    revision: str = Field(default="1", min_length=1)
    content_reference: str | None = None

class RegisterKnowledgeRequest(KnowledgeDescriptor): pass
class UpdateKnowledgeRequest(KnowledgeDescriptor): pass
class ResolveKnowledgeRequest(VersionedMessage): knowledge_id: str = Field(min_length=1)
class ListCompatibleArtifactsRequest(VersionedMessage): knowledge_id: str = Field(min_length=1)
class QueryArtifactCompatibilityRequest(VersionedMessage): artifact: CacheArtifact
class ReportRequestOutcomeRequest(VersionedMessage):
    knowledge_id: str = Field(min_length=1)
    outcome: OutcomeCode
    operation_id: str | None = None

class KnowledgeResponse(VersionedMessage):
    outcome: OutcomeCode = OutcomeCode.SUCCESS
    knowledge_id: str | None = None
    artifact: CacheArtifact | None = None
    artifacts: tuple[CacheArtifact, ...] = ()
    compatible: bool | None = None
    error: ContractError | None = None

    @model_validator(mode="after")
    def consistent_outcome(self):
        if self.outcome is OutcomeCode.SUCCESS and self.error is not None:
            raise ValueError("successful responses cannot carry an error")
        if self.outcome is not OutcomeCode.SUCCESS and (
            self.error is None or self.error.code is not self.outcome
        ):
            raise ValueError("non-success responses require a matching error detail")
        if self.outcome is OutcomeCode.TEXT_FALLBACK and not self.error.fallback_eligible:
            raise ValueError("text fallback must be explicitly fallback eligible")
        return self

RegisterKnowledgeResponse = KnowledgeResponse
UpdateKnowledgeResponse = KnowledgeResponse
ResolveKnowledgeResponse = KnowledgeResponse
ListCompatibleArtifactsResponse = KnowledgeResponse
QueryArtifactCompatibilityResponse = KnowledgeResponse
ReportRequestOutcomeResponse = KnowledgeResponse
