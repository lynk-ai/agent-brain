import json
from pathlib import Path

from .output import BrainError, Finding

# Each adapter turns the resolved brain folders and the session instruction into one harness command.
# Cursor's cursor-agent has --plugin-dir and no system prompt flag; its adapter comes later.
ADAPTERS = ("claude", "codex")


def command(harness: str, plugin_dirs: list[Path], instruction: str, extra: list[str]) -> list[str]:
    if harness == "claude":
        dirs = [arg for folder in plugin_dirs for arg in ("--plugin-dir", str(folder))]
        return ["claude", *dirs, "--append-system-prompt", instruction, *extra]
    if harness == "codex":
        # Codex has no plugin flag for one session, so the instruction's SKILL.md paths do the loading.
        # A -c value is parsed as TOML, and a JSON string is a valid TOML basic string.
        return ["codex", "-c", f"developer_instructions={json.dumps(instruction, ensure_ascii=False)}", *extra]
    raise BrainError(Finding("load.no_adapter", harness, f"brain load has no adapter for {harness} yet.", f"Pass --harness {' or --harness '.join(ADAPTERS)}."), outcome="error")
