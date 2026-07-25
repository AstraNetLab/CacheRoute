"""Public exports for CacheRoute core helpers, loaded only when requested."""
from importlib import import_module


_EXPORTS = {
    "MLAmodel": (".model_calculation", "MLAmodel"),
    "Request": (".request", "Request"), "Prompt": (".request", "Prompt"),
    "Service": (".request", "Service"), "Task": (".request", "Task"),
    "TokenizerRegistry": (".tokenizer_registry", "TokenizerRegistry"),
    "forward_request": (".fwd", "forward_request"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
