"""Deprecated forwarding package for :mod:`cacheroute.compat`.

This import path is retained for Phase A compatibility and is scheduled for
removal in CacheRoute 0.3.0. New code should import :mod:`cacheroute.compat`.
"""

from cacheroute.compat import *  # noqa: F401,F403
from cacheroute.compat import __all__
