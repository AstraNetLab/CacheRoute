"""Gateway construction boundary; production transports are intentionally absent."""
from .legacy import LegacyCacheAdapter
from .mock import MockGateway
from .profiles import GatewayTransportKind


def create_gateway(transport_kind, capabilities, **fixtures):
    """Construct available adapters only after validating binding membership.

    Production transports remain representable in contracts but intentionally
    have no construction or I/O implementation in this package.
    """
    kind = GatewayTransportKind(transport_kind)
    if not capabilities.supports_adapter(kind):
        raise ValueError("requested transport is not present in capability adapter bindings")
    if kind is GatewayTransportKind.MOCK:
        return MockGateway(capabilities, **fixtures)
    if kind is GatewayTransportKind.LEGACY_REDIS:
        return LegacyCacheAdapter(capabilities, **fixtures)
    raise NotImplementedError(f"production gateway transport {kind.value!r} is not implemented")
