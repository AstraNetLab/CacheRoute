"""Safe structured outcomes shared by KDN facade and gateways."""
from enum import Enum

from pydantic import Field, field_validator

from .common import ContractModel, KDN_CONTRACT_VERSION


class OutcomeCode(str, Enum):
    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE = "incompatible"
    STALE = "stale"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TEXT_FALLBACK = "text_fallback"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


class ContractErrorDetail(ContractModel):
    """Stable safe failure detail; backend exceptions never cross the wire."""
    code: OutcomeCode
    message: str = Field(min_length=1)
    contract_version: str = KDN_CONTRACT_VERSION
    retryable: bool = False
    fallback_eligible: bool = False

    @field_validator("contract_version")
    @classmethod
    def exact_version(cls, value):
        if value != KDN_CONTRACT_VERSION:
            raise ValueError("unsupported error contract version")
        return value


ContractError = ContractErrorDetail
