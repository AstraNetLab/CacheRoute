"""Keep repository packages importable when pytest is launched via its console script."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for source_root in (ROOT, ROOT / "src"):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
