from dataclasses import dataclass
from pathlib import Path

import yaml

from .output import BrainError, Finding

CONFIG_FILE = "brain.yaml"

DEFAULTS = {
    "pending_days": 14,
    "checked_days": 90,
    "harness_names": [".claude/", "CLAUDE.md", ".codex/", ".cursor/", ".agents/skills", "settings.local.json"],
}


@dataclass(frozen=True)
class Brain:
    root: Path
    config: dict

    @property
    def name(self) -> str:
        return self.config["name"]

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
    # One repository may hold many brains; each folder with a brain.yaml is one.
    brains = []
    for config_path in sorted(start.resolve().rglob(CONFIG_FILE)):
        if SKIP_DIRS.isdisjoint(config_path.relative_to(start.resolve()).parts):
            brains.append(Brain(root=config_path.parent, config=load_config(config_path)))
    return brains


def load_config(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise BrainError(Finding("brain.config", path.name, f"{CONFIG_FILE} is not valid YAML: {exc}", "Fix the YAML."), outcome="error")
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise BrainError(Finding("brain.config", path.name, f"{CONFIG_FILE} has no name.", "Add name: <agent-name>."), outcome="error")
    return {**DEFAULTS, **data}
