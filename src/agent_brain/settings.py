import json
import os
import tomllib
from pathlib import Path

from .output import BrainError, Finding

# The one thing brain saves for a person: the repository that holds their team brain.
FILE_ENV = "BRAIN_CONFIG"


def path() -> Path:
    # BRAIN_CONFIG names the file itself, so a test or a proof never touches the person's real settings.
    if os.environ.get(FILE_ENV):
        return Path(os.environ[FILE_ENV]).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config").expanduser()
    return base / "brain" / "config.toml"


def read() -> dict:
    where = path()
    if not where.is_file():
        return {}
    try:
        return tomllib.loads(where.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise BrainError(Finding("settings.unreadable", str(where), f"It is not valid TOML: {exc}.", f"Fix it, or delete it and run brain use <path>."), outcome="error")


def saved_team() -> Path | None:
    value = read().get("team")
    return Path(value) if isinstance(value, str) and value else None


def save_team(folder: Path) -> Path:
    where = path()
    data = {k: v for k, v in read().items() if k != "team"}
    where.parent.mkdir(parents=True, exist_ok=True)
    # A JSON string is a valid TOML basic string, and the file holds only plain keys.
    lines = [f"team = {json.dumps(str(folder))}"] + [f"{k} = {json.dumps(v)}" for k, v in data.items() if isinstance(v, (str, int, bool))]
    where.write_text("\n".join(lines) + "\n")
    return where
