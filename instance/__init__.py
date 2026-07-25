"""Public Instance exports, loaded lazily to keep helper modules lightweight."""
from importlib import import_module


def __getattr__(name):
    if name == "instance":
        value = import_module(".instance_api", __name__).instance
    elif name in {"mock_chat_stream", "mock_chat_completion", "mock_text_completion"}:
        value = getattr(import_module(".mock_resp", __name__), name)
    else:
        raise AttributeError(name)
    globals()[name] = value
    return value
