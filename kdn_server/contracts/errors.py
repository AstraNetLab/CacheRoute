"""Safe structured outcomes shared by KDN facade and gateways."""
from enum import Enum

from pydantic import Field

from .common import VersionedMessage


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


class ContractError(VersionedMessage):
    code: OutcomeCode
    message: str = Field(min_length=1)
    retryable: bool = False
    fallback_eligible: bool = False


class GatewayContractException(ValueError):
    def __init__(self, error: ContractError):
        self.error = error
        super().__init__(error.message)
