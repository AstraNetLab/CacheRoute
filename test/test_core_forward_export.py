import inspect

from core import forward_request
from core.fwd import forward_request as direct_forward_request


def test_public_forward_request_is_direct_async_generator_export():
    assert forward_request is direct_forward_request
    assert inspect.signature(forward_request) == inspect.signature(direct_forward_request)
    assert inspect.isasyncgenfunction(forward_request)
