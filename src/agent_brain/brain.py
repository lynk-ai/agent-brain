import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from .output import BrainError, Finding

CONFIG_FILE = "brain.yaml"
COPY_MARKER = ".brain-source.yaml"
# brain load's snapshot of a team's default branch: read-only, and never the brain's repository.
SNAPSHOT_MARKER = ".brain-snapshot.yaml"
# The brain.yaml format this CLI writes. A brain.yaml with no format is format 1, which reads as 2.
FORMAT = 2
KINDS = ("agent", "team")

DEFAULTS = {
    "pending_days": 14,
    "checked_days": 90,
    "harness_names": [".claude/", ".codex/", ".cursor/", ".agents/skills", "settings.local.json"],
    "intake_days": 14,
}


@dataclass(frozen=True)
class Brain:
    root: Path
    config: dict
    copy: bool = False

    @property
    def name(self) -> str:
        return self.config["name"]

    @property
    def kind(self) -> str:
        return self.config.get("kind") or "agent"

    @property
    def is_team(self) -> bool:
        return self.kind == "team"

    @property
    def team(self) -> str | None:
        value = self.config.get("team")
        return value if isinstance(value, str) and value else None

    @property
    def skill_dir(self) -> Path:
        return self.root / self.name

    @property
    def references(self) -> Path:
        return self.skill_dir / "references"

    @property
    def skill_file(self) -> Path:
        return self.skill_dir / "SKILL.md"

    @property
    def agent_file(self) -> Path:
        return self.skill_dir / "agent.md"

    def rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(path)


def find(start: Path | None = None) -> Brain:
    # resolve() follows an installed symlink back to the brain's repository.
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        config_path = folder / CONFIG_FILE
        if config_path.is_file():
            return Brain(root=folder, config=load_config(config_path))
        marker = folder / COPY_MARKER
        if marker.is_file():
            data = yaml.safe_load(marker.read_text()) or {}
            return Brain(root=folder.parent, config={**DEFAULTS, **(data.get("config") or {})}, copy=True)
    raise BrainError(
        Finding(
            "brain.not_found",
            str(here),
            f"No {CONFIG_FILE} in this folder or above it.",
            "Pass --project with the brain's folder or its installed skill folder, or run brain init <name>.",
        ),
        outcome="error",
    )


SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}


def find_all(start: Path) -> list[Brain]:
    # One repository may hold many brains; each folder with a brain.yaml is one, and none sits inside another.
    brains = []
    for folder, dirs, files in os.walk(start.resolve()):
        if CONFIG_FILE in files:
            brains.append(Brain(root=Path(folder), config=load_config(Path(folder) / CONFIG_FILE)))
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
    return sorted(brains, key=lambda b: str(b.root))


def require_writable(brain: Brain) -> None:
    # An installed copy (a plugin cache or install --copy) is not the brain's repository, so a change there is lost.
    source = brain.config.get("source") or {}
    snapshot = next((top / SNAPSHOT_MARKER for top in (brain.root, *brain.root.parents) if (top / SNAPSHOT_MARKER).is_file()), None)
    if snapshot is not None:
        made = yaml.safe_load(snapshot.read_text()) or {}
        fix = f"Change the brain on a branch in its repository, {made.get('repo')}, and open a pull request. brain load --checkout loads that branch."
        raise BrainError(Finding("brain.snapshot", str(brain.skill_dir), f"This is a snapshot brain load made of {made.get('ref')} at {str(made.get('commit'))[:12]}. A change here never reaches its repository.", fix))
    if not brain.copy and (not source or in_git(brain.root)):
        return
    repo, path = source.get("repo"), source.get("path")
    fix = (
        f"Clone it: git clone {repo}, then run the same command with --project <clone>/{path}, and open a pull request."
        if repo and path
        else "Find the brain's repository, and run the command in a clone of it."
    )
    raise BrainError(Finding("brain.installed_copy", str(brain.skill_dir), f"This is an installed copy of {brain.name}. A change here never reaches its repository.", fix))


def in_git(folder: Path) -> bool:
    result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "true"


def load_config(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise BrainError(Finding("brain.config", path.name, f"{CONFIG_FILE} is not valid YAML: {exc}", "Fix the YAML."), outcome="error")
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise BrainError(Finding("brain.config", path.name, f"{CONFIG_FILE} has no name.", "Add name: <agent-name>."), outcome="error")
    version = data.get("format", 1)
    if not isinstance(version, int) or version < 1:
        raise BrainError(Finding("brain.config", path.name, f"format must be a whole number, not {version!r}.", f"Set format: {FORMAT}."), outcome="error")
    if version > FORMAT:
        raise BrainError(
            Finding("brain.format_newer", str(path), f"{CONFIG_FILE} is format {version}; this brain reads up to format {FORMAT}.", "Update brain: uv tool upgrade agent-brain."), outcome="error"
        )
    if data.get("kind", "agent") not in KINDS:
        raise BrainError(Finding("brain.config", path.name, f"kind must be agent or team, not {data.get('kind')!r}.", "Set kind: team, or leave it out for an agent brain."), outcome="error")
    if data.get("kind") == "team" and data.get("team"):
        raise BrainError(Finding("brain.config", path.name, "A team brain has no team: field.", "Remove team:."), outcome="error")
    return {**DEFAULTS, **data}
