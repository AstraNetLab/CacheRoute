"""Gateway construction boundary; production transports are intentionally absent."""
from .legacy import LegacyCacheAdapter
from .mock import MockGateway
from .profiles import GatewayTransportKind


def create_gateway(transport_kind, capabilities, **fixtures):
    kind = GatewayTransportKind(transport_kind)
    if kind is GatewayTransportKind.MOCK:
        return MockGateway(capabilities, **fixtures)
    if kind is GatewayTransportKind.LEGACY_REDIS:
        return LegacyCacheAdapter(capabilities, **fixtures)
    raise NotImplementedError(f"production gateway transport {kind.value!r} is not implemented")
