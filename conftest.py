"""Test bootstrap: put the repo root and the mission-control skill dir on
sys.path so tests can import both ``scripts.*`` and the sibling-style
mission-control modules (``dispatcher``, ``claude_invocation``)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MC = ROOT / ".claude" / "skills" / "mission-control"
for _p in (str(ROOT), str(MC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
