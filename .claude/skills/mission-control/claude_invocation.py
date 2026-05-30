"""Pure helper for invoking the ``claude`` CLI without leaking the prompt.

The prompt is fed on **stdin**, never as a command-line argument, so it does
not appear in ``ps`` / ``/proc/<pid>/cmdline`` for other users on the host.
``classic_cmd`` therefore takes ``model`` but **not** ``prompt`` — the prompt
has no argv slot to leak into.

Only the classic (single-shot text) path is covered here. The streaming path
(``_execute_stream``) is pre-existing and currently non-functional, and moving
its prompt off argv is entangled with that redesign; see the follow-up loop.
"""

from __future__ import annotations


def classic_cmd(claude_bin: str, model: str) -> list[str]:
    """argv for classic (single-shot text) mode. Prompt is sent via stdin."""
    return [claude_bin, "-p", "--model", model, "--output-format", "text"]
