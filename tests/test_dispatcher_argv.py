"""Behavioural proof that the classic dispatch path feeds the prompt via
stdin, not argv. We patch ``subprocess.Popen`` and assert the prompt never
lands in the argv list and is delivered on stdin instead.

(The streaming path is pre-existing and non-functional; its argv-leak fix is
deferred to a separate redesign — see the follow-up loop.)
"""

import subprocess

import dispatcher

SECRET = "PROMPT-WITH-SECRET-xyzzy-credentials"


class _FakeStdin:
    def __init__(self):
        self.captured_input = None

    def close(self):
        pass


class _FakeClassicProc:
    def __init__(self):
        self.pid = 4242
        self.returncode = 0
        self.stdin = _FakeStdin()

    def communicate(self, input=None, timeout=None):
        self.stdin.captured_input = input
        return ("ok summary", "")

    def kill(self):
        pass


def test_classic_prompt_via_stdin_not_argv(monkeypatch):
    monkeypatch.setattr(dispatcher, "_mark_child_pid", lambda pid: None)
    monkeypatch.setattr(dispatcher, "_unmark_child_pid", lambda pid: None)
    monkeypatch.setattr(dispatcher, "_build_env", lambda model: {})
    monkeypatch.setattr(dispatcher, "_task_timeout", lambda: 60)
    monkeypatch.setattr(dispatcher, "_claude_bin", lambda: "/usr/bin/claude")

    captured = {}

    def fake_popen(cmd, **kwargs):
        proc = _FakeClassicProc()
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(dispatcher.subprocess, "Popen", fake_popen)

    ok, _summary, _elapsed = dispatcher._execute_classic(
        {"id": 1}, SECRET, "claude-sonnet-4-6"
    )

    assert ok is True
    assert SECRET not in captured["cmd"]                       # not in argv
    assert captured["kwargs"].get("stdin") is subprocess.PIPE  # stdin wired up
    assert captured["proc"].stdin.captured_input == SECRET     # prompt via stdin
