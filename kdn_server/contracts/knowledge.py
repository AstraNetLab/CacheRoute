"""Storage-neutral Knowledge Service request and response contracts."""
from typing import Literal

from pydantic import Field

from kdn_server.domain import CacheArtifact
from .common import VersionedMessage
from .errors import ContractError, OutcomeCode


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

RegisterKnowledgeResponse = KnowledgeResponse
UpdateKnowledgeResponse = KnowledgeResponse
ResolveKnowledgeResponse = KnowledgeResponse
ListCompatibleArtifactsResponse = KnowledgeResponse
QueryArtifactCompatibilityResponse = KnowledgeResponse
ReportRequestOutcomeResponse = KnowledgeResponse
