"""The claude CLI argv builder must never carry the prompt (ps/cmdline leak)."""

from claude_invocation import classic_cmd

SECRET = "do the secret thing with token sk-ant-hunter2"


def test_classic_cmd_has_no_prompt_slot():
    cmd = classic_cmd("/usr/bin/claude", "claude-sonnet-4-6")
    assert SECRET not in cmd
    assert cmd == [
        "/usr/bin/claude", "-p", "--model", "claude-sonnet-4-6",
        "--output-format", "text",
    ]
