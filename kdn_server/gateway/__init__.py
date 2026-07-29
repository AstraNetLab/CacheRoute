"""LMCache gateway contracts and dependency-free test adapters."""
from .capabilities import *
from .profiles import *
from .protocol import *
from .mock import MockGateway
from .legacy import LegacyCacheAdapter
from .factory import create_gateway
