"""Optional Haiku skill picker for tasks that landed without an
``assigned_skill``.

Returns the picked skill name, or ``None`` if no Anthropic key is
configured / nothing matches. Costs roughly $0.0001 per call so
firing it on every untyped task is fine.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401

import logging
import os
import sqlite3

log = logging.getLogger("commandcentre.skill_router")

_PROMPT = """\
You map a task to the single most relevant skill from a list. Reply \
with ONLY the skill's exact name. If no skill is a clear fit, reply \
with an empty string.

Task title: {title}
Task description: {description}

Available skills (name — description):
{skills}
"""


def pick_skill(conn: sqlite3.Connection, title: str, description: str | None) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        log.warning("anthropic SDK missing; skill_router disabled")
        return None
    rows = conn.execute(
        "SELECT name, description FROM skills WHERE COALESCE(description,'') != ''"
    ).fetchall()
    if not rows:
        return None
    skills_block = "\n".join(
        f"- {r['name']} — {(r['description'] or '').strip()[:160]}" for r in rows
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(
                        title=title,
                        description=(description or "").strip()[:600],
                        skills=skills_block,
                    ),
                }
            ],
        )
    except Exception:  # noqa: BLE001
        log.exception("skill_router Haiku call failed")
        return None
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    candidate = "".join(parts).strip().strip("`'\"").strip()
    if not candidate:
        return None
    valid = {r["name"] for r in rows}
    if candidate not in valid:
        log.warning("skill_router returned unknown skill: %r", candidate)
        return None
    return candidate
