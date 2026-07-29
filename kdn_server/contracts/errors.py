"""Safe structured outcomes shared by KDN facade and gateways."""
from enum import Enum

from pydantic import Field

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
    code: OutcomeCode
    message: str = Field(min_length=1)
    contract_version: str = KDN_CONTRACT_VERSION
    retryable: bool = False
    fallback_eligible: bool = False


ContractError = ContractErrorDetail


class GatewayContractException(ValueError):
    def __init__(self, error: ContractErrorDetail):
        self.error = error
        super().__init__(error.message)
