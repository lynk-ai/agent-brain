import os
from pathlib import Path

# The harnesses brain installs into, detects and hooks.
NAMES = {"claude": "Claude Code", "codex": "Codex", "cursor": "Cursor"}
# Every harness an agent.md may name as its default. Grok Bot runs agents but has no skills folder, hooks or load adapter.
KNOWN = {**NAMES, "grokbot": "Grok Bot"}
# Each harness marks the commands it runs with its own environment variables.
MARKERS = {"claude": ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID"), "codex": ("CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_SESSION_ID"), "cursor": ("CURSOR_AGENT", "CURSOR_TRACE_ID")}
# Claude Code reads its own skills folder; Codex and Cursor read the neutral Agent Skills one.
PROJECT_SKILLS = {"claude": Path(".claude/skills"), "codex": Path(".agents/skills"), "cursor": Path(".agents/skills")}
USER_SKILLS = {"claude": Path("~/.claude/skills"), "codex": Path("~/.agents/skills"), "cursor": Path("~/.agents/skills")}


def detect(environ=None) -> str | None:
    env = os.environ if environ is None else environ
    # A harness started from Claude Code may inherit its variables, so the more specific ones win.
    for name in ("codex", "cursor", "claude"):
        if any(env.get(k) for k in MARKERS[name]):
            return name
    return None


def others(chosen: list[str]) -> list[str]:
    return [h for h in NAMES if h not in chosen]
