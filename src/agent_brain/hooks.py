import json
import shlex
import sys
from pathlib import Path

from . import checks
from .brain import Brain
from .output import BrainError, Finding
from .records import load

MANAGED = "# managed by brain hooks install"


def brain_command() -> str:
    # Hooks run without the user's shell PATH, so pin the interpreter or script that runs this command.
    argv0 = Path(sys.argv[0])
    if argv0.name in ("__main__.py", "-m") or argv0.suffix == ".py":
        return f"{shlex.quote(sys.executable)} -m agent_brain"
    resolved = argv0.resolve() if argv0.exists() else argv0
    return shlex.quote(str(resolved))


def install_git(repo: Path) -> Path:
    hook = repo / ".git" / "hooks" / "pre-commit"
    if not (repo / ".git").is_dir():
        raise BrainError(Finding("hooks.no_git", str(repo), "This folder is not the top of a git repository.", "Run git init, or pass --repo with the repository's top folder."), outcome="error")
    script = f"#!/bin/sh\n{MANAGED}\nexec {brain_command()} check --staged --project {shlex.quote(str(repo))}\n"
    if hook.exists() and MANAGED not in hook.read_text():
        raise BrainError(Finding("hooks.pre_commit_exists", str(hook), "A pre-commit hook that brain does not manage is already there.", f"Add this line to it: {brain_command()} check --staged --project {repo}"))
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(script)
    hook.chmod(0o755)
    return hook


def install_claude(project_dir: Path, brain_root: Path) -> Path:
    settings_dir = project_dir / ".claude"
    settings_path = settings_dir / "settings.local.json"
    settings_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    hooks = data.setdefault("hooks", {})
    command = brain_command()
    target = shlex.quote(str(brain_root))
    for event, sub in (("Stop", "stop"), ("SessionStart", "start")):
        entry_command = f"{command} hook {sub} --project {target}"
        groups = hooks.setdefault(event, [])
        # Ours is matched by its arguments, so a reinstall replaces it and leaves other hooks alone.
        for group in groups:
            group["hooks"] = [h for h in group.get("hooks", []) if not owned(h.get("command", ""), sub, target)]
        groups[:] = [g for g in groups if g.get("hooks")]
        groups.append({"hooks": [{"type": "command", "command": entry_command}]})
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    ignore = settings_dir / ".gitignore"
    if not ignore.exists():
        ignore.write_text("settings.local.json\n")
    return settings_path


def owned(command: str, sub: str, target: str) -> bool:
    return f" hook {sub} --project {target}" in command


def stop(payload: dict, brains: list[Brain]) -> dict | None:
    # A second refusal in the same turn would loop; Claude Code sets stop_hook_active on the continuation.
    if payload.get("stop_hook_active"):
        return None
    lines = []
    for brain in brains:
        found = checks.blocking(checks.run(brain))
        if found:
            # The session runs in a work folder, so name the brain's path for every command and file.
            lines.append(f"Brain {brain.name}: run every brain command below with --project {brain.root}. Files are under {brain.root}.")
            lines += [f"  {f.file}: {f.message} Fix: {f.fix} [{f.code}]" for f in found[:20]]
            if len(found) > 20:
                lines.append(f"  ...and {len(found) - 20} more. Run brain check --project {brain.root}.")
    if not lines:
        return None
    reason = "The brain has block findings. Fix them before you stop:\n" + "\n".join(lines)
    return {"decision": "block", "reason": reason}


def start(brains: list[Brain]) -> str:
    out = []
    for brain in brains:
        records = load(brain)
        pending = [f for f in records.by_folder["feedback"].values() if f.meta.get("disposition") in ("new", "pending")]
        proposed = [r for r in [*records.by_folder["rules"].values(), *records.by_folder["procedures"].values()] if r.meta.get("status") == "proposed"]
        out.append(
            f"Brain {brain.name}: {len(pending)} feedback new or pending, {len(proposed)} rules or procedures proposed. "
            f"Take every correction through Take a piece of feedback, in the same turn."
        )
    return "\n".join(out)
