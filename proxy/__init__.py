"""Public Proxy application, loaded lazily for lightweight resource tooling."""
from importlib import import_module


def __getattr__(name):
    if name != "proxy":
        raise AttributeError(name)
    value = import_module(".proxy", __name__).proxy
    globals()[name] = value
    return value

