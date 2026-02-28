"""Dashboard backend package.

Ensures the repository root is importable so the dashboard backend can reuse
the existing ``briefbot`` package even when launched from inside
``dashboard/backend`` with a local ``--app-dir``.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
