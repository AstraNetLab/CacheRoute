"""CacheRoute v1 common contract foundation."""

from .common import (
    ContractModel, ENDPOINT_ID_PATTERN, GATEWAY_CONTRACT_VERSION,
    GatewayTargetedRequest, KDN_CONTRACT_VERSION, SupportState, TokenInput,
    TokenReference, VersionedMessage, utc_now,
)
from .errors import ContractError, ContractErrorDetail, OutcomeCode

__all__ = [
    "KDN_CONTRACT_VERSION", "GATEWAY_CONTRACT_VERSION", "ENDPOINT_ID_PATTERN",
    "SupportState", "utc_now", "ContractModel", "VersionedMessage",
    "GatewayTargetedRequest", "TokenReference", "TokenInput", "OutcomeCode",
    "ContractErrorDetail", "ContractError",
]
