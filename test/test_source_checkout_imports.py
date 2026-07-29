"""Source-checkout import sentinel loaded through the root pytest configuration."""

from pathlib import Path

import cacheroute.compat


def test_canonical_compatibility_resolves_from_src():
    repo = Path(__file__).resolve().parents[1]
    assert Path(cacheroute.compat.__file__).resolve().is_relative_to(repo / "src")
