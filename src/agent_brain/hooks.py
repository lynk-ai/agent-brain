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
    # The hook runs in whichever worktree commits, so it checks that worktree, not the one it was installed from.
    script = f'#!/bin/sh\n{MANAGED}\nexec {brain_command()} check --staged --project "$(git rev-parse --show-toplevel)"\n'
    if hook.exists() and MANAGED not in hook.read_text():
        raise BrainError(Finding("hooks.pre_commit_exists", str(hook), "A pre-commit hook that brain does not manage is already there.", f'Add this line to it: {brain_command()} check --staged --project "$(git rev-parse --show-toplevel)"'))
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(script)
    hook.chmod(0o755)
    return hook


# Each harness keeps hooks in its own file and event names. Cursor lists handlers directly; the others group them.
HOSTS = {
    "claude": {"file": Path(".claude/settings.local.json"), "events": {"stop": "Stop", "start": "SessionStart"}},
    "codex": {"file": Path(".codex/hooks.json"), "events": {"stop": "Stop", "start": "SessionStart"}},
    "cursor": {"file": Path(".cursor/hooks.json"), "events": {"stop": "stop"}},
}


def install_host(host: str, project_dir: Path, brain_root: Path) -> Path:
    spec = HOSTS[host]
    path = project_dir / spec["file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    if host == "cursor":
        data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    target = shlex.quote(str(brain_root))
    for sub, event in spec["events"].items():
        command = f"{brain_command()} hook {sub} --host {host} --project {target}"
        entries = hooks.setdefault(event, [])
        # Ours is matched by its arguments, so a reinstall replaces it and leaves other hooks alone.
        if host == "cursor":
            entries[:] = [h for h in entries if not owned(h.get("command", ""), sub, target)]
            entries.append({"command": command, "timeout": 120, "loop_limit": 2})
            continue
        for group in entries:
            group["hooks"] = [h for h in group.get("hooks", []) if not owned(h.get("command", ""), sub, target)]
        entries[:] = [g for g in entries if g.get("hooks")]
        entries.append({"hooks": [{"type": "command", "command": command, "timeout": 120}]})
    path.write_text(json.dumps(data, indent=2) + "\n")
    # The commands pin this machine's paths, so the file stays out of git.
    ignore = path.parent / ".gitignore"
    lines = ignore.read_text().splitlines() if ignore.exists() else []
    if path.name not in lines:
        ignore.write_text("\n".join([*lines, path.name]) + "\n")
    return path


def owned(command: str, sub: str, target: str) -> bool:
    return f" hook {sub} " in command and f"--project {target}" in command


def stop(payload: dict, brains: list[Brain], host: str = "claude") -> dict | None:
    # One repair per turn: a second refusal would loop. Claude Code and Codex flag the continuation, Cursor counts it.
    if host == "cursor":
        if payload.get("status", "completed") != "completed" or (payload.get("loop_count") or 0) > 0:
            return None
    elif payload.get("stop_hook_active"):
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
    return {"followup_message": reason} if host == "cursor" else {"decision": "block", "reason": reason}


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
