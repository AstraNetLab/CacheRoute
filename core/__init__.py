"""Public exports for CacheRoute core request, tokenizer, model, and forwarding helpers."""

from .model_calculation import MLAmodel
from .request import Request, Prompt, Service, Task
from .tokenizer_registry import TokenizerRegistry


def forward_request(*args, **kwargs):
    """Import the optional HTTP forwarding dependency only when it is used."""
    from .fwd import forward_request as _forward_request

    return _forward_request(*args, **kwargs)
