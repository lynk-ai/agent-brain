import os
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import settings
from .brain import CONFIG_FILE, SNAPSHOT_MARKER, Brain, load_config
from .output import BrainError, Finding

# brain load reads the team from a snapshot of the remote's default branch, so a session never loads a branch,
# an edit that is not committed, or a change half made. One snapshot per commit, shared by every session on it.
MARKER = SNAPSHOT_MARKER
KEEP = 5
DAYS = 7


@dataclass(frozen=True)
class Prepared:
    folder: Path | None
    ref: str = ""
    commit: str = ""
    fetch_error: str = ""


def git(repo: Path, *args: str) -> str | None:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base).expanduser() / "brain"


def remote_of(repo: Path) -> str | None:
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    remotes = (git(repo, "remote") or "").split()
    if upstream and "/" in upstream and upstream.split("/", 1)[0] in remotes:
        return upstream.split("/", 1)[0]
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else None


def default_ref(repo: Path) -> str | None:
    # The remote's own HEAD names its default branch; main and master are the fallbacks when it was never set.
    remote = remote_of(repo)
    if remote is None:
        return None
    head = git(repo, "symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD")
    if head:
        return head.removeprefix("refs/remotes/")
    for branch in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}"):
            return f"{remote}/{branch}"
    return None


def fetch(repo: Path) -> str:
    done = subprocess.run(["git", "-C", str(repo), "fetch", "--quiet"], capture_output=True, text=True)
    if done.returncode == 0:
        return ""
    return (done.stderr.strip().splitlines() or ["no network"])[-1]


def extract(repo: Path, commit: str, paths: list[str], into: Path) -> None:
    if not paths:
        return
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit, "--", *paths], capture_output=True)
    if archive.returncode != 0:
        raise BrainError(Finding("load.snapshot_failed", str(repo), f"git archive failed: {archive.stderr.decode(errors='replace').strip()}", "Run git -C <repo> fetch, or pass --checkout."), outcome="error")
    subprocess.run(["tar", "-x", "-C", str(into)], input=archive.stdout, check=True)


def inside(path: str) -> str | None:
    # Only a relative path inside the repository goes in the snapshot; an absolute one is read where it is.
    if not path.startswith(("./", "../")):
        return None
    clean = os.path.normpath(path)
    return None if clean.startswith("..") else clean


def extra_paths(folder: Path) -> list[str]:
    # Each agent's path loads and the team's book lists, so every agent of this commit loads from one snapshot.
    from . import team
    from .brain import find_all
    from .records import load as load_records

    wanted: list[str] = []
    for brain in find_all(folder):
        if brain.is_team:
            _, books, _ = team.team_settings(brain)
            wanted += [p for p in (inside("./" + v) for v in books.values()) if p]
            continue
        record = load_records(brain).agent if brain.agent_file.is_file() else None
        if record is None:
            continue
        for entry in team.loads_of(brain, record.meta).brains:
            path = inside(entry)
            if path:
                wanted.append(path)
    return [p for p in dict.fromkeys(wanted) if not (folder / p).exists()]


def existing(repo: Path, commit: str, paths: list[str]) -> list[str]:
    listed = git(repo, "ls-tree", "--name-only", commit, "--", *paths) if paths else ""
    return [p for p in paths if p in (listed or "").splitlines()]


def lock(folder: Path) -> None:
    for top, dirs, files in os.walk(folder):
        for name in files:
            path = Path(top) / name
            path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    for top, dirs, _ in os.walk(folder, topdown=False):
        for name in dirs:
            path = Path(top) / name
            path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    folder.chmod(folder.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def remove(folder: Path) -> None:
    for top, dirs, _ in os.walk(folder):
        Path(top).chmod(Path(top).stat().st_mode | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRUSR)
    shutil.rmtree(folder)


def build(repo: Path, ref: str, commit: str, folder: Path) -> None:
    building = folder.parent / f".building-{folder.name}-{os.getpid()}"
    if building.exists():
        remove(building)
    building.mkdir(parents=True)
    try:
        listed = git(repo, "ls-tree", "-r", "--name-only", commit) or ""
        brains = sorted({str(Path(p).parent) for p in listed.splitlines() if Path(p).name == CONFIG_FILE and str(Path(p).parent) != "."})
        extract(repo, commit, brains, building)
        extract(repo, commit, existing(repo, commit, extra_paths(building)), building)
        (building / MARKER).write_text(yaml.safe_dump({"repo": str(repo), "ref": ref, "commit": commit}, sort_keys=False))
        if folder.exists() and not (folder / MARKER).is_file():
            remove(folder)
        try:
            building.rename(folder)
        except OSError:
            if not (folder / MARKER).is_file():
                raise
            # Another session built the same commit first; its snapshot is the same.
            remove(building)
            return
        # Locked after the move: macOS refuses to move a folder it may not write.
        lock(folder)
    except BaseException:
        if building.exists():
            remove(building)
        raise


def used(folder: Path) -> Path:
    return folder.parent / f"{folder.name}.used"


def setting(name: str, default: int) -> int:
    value = settings.read().get(name)
    return value if isinstance(value, int) and value >= 0 else default


def prune(team_cache: Path, current: Path) -> list[Path]:
    # Keep the newest snapshots and every one used lately: an open session still reads its own.
    keep, days = setting("snapshots_keep", KEEP), setting("snapshots_days", DAYS)
    snapshots = [p for p in team_cache.iterdir() if p.is_dir() and not p.name.startswith(".")]
    stamp = lambda p: used(p).stat().st_mtime if used(p).exists() else p.stat().st_mtime
    snapshots.sort(key=stamp, reverse=True)
    cutoff = time.time() - days * 86400
    removed = []
    for old in snapshots[keep:]:
        if old != current and stamp(old) < cutoff:
            remove(old)
            used(old).unlink(missing_ok=True)
            removed.append(old)
    return removed


def prepare(repo: Path, team_name: str, fetch_first: bool = True) -> Prepared:
    error = fetch(repo) if fetch_first else ""
    ref = default_ref(repo)
    commit = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") if ref else None
    if not ref or not commit:
        return Prepared(None, fetch_error=error)
    team_cache = cache_root() / team_name
    team_cache.mkdir(parents=True, exist_ok=True)
    folder = team_cache / commit[:12]
    if not (folder / MARKER).is_file():
        build(repo, ref, commit, folder)
    used(folder).touch()
    prune(team_cache, folder)
    return Prepared(folder, ref, commit, error)


def marker_of(folder: Path) -> dict | None:
    for top in (folder, *folder.parents):
        path = top / MARKER
        if path.is_file():
            return yaml.safe_load(path.read_text()) or {}
    return None


def brain_in(folder: Path, rel: Path) -> Brain | None:
    root = folder / rel
    if not (root / CONFIG_FILE).is_file():
        return None
    return Brain(root=root, config=load_config(root / CONFIG_FILE))
