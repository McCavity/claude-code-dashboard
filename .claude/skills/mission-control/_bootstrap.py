"""sys.path bootstrap shared by every Mission Control module.

The skill files live under ``.claude/skills/mission-control/`` so they
look like a Claude Code skill in the project tree, but they need to
import from the top-level ``scripts/`` package (db.py, _helpers.py).
This module finds the install root by walking up from ``__file__``
until it hits a directory containing ``scripts/db.py`` and prepends
that to ``sys.path`` exactly once.

Importing this module is enough — there is no callable surface.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _install_root() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        if (ancestor / "scripts" / "db.py").exists():
            return ancestor
    # Fallback: assume two levels up from .claude/skills/mission-control/.
    return here.parents[3]


_root = _install_root()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
