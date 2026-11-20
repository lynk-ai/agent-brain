import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import settings, team
from .scaffold import git_root
from .brain import Brain, find
from .output import BrainError, Finding
from .records import load as load_records

DEFAULT_HARNESS = "claude"


@dataclass(frozen=True)
class Member:
    name: str
    display_name: str
    job: str
    brain: Brain | None
    meta: dict

    def row(self) -> dict:
        return {"display_name": self.display_name, "name": self.name, "job": self.job, "source": str(self.brain.root) if self.brain else None}


def locate(start: Path, walk_without_git: bool) -> Brain | None:
    start = start.expanduser().resolve()
    try:
        here = find(start)
    except BrainError:
        here = None
    repo = team.repo_root(here) if here else None
    repo = repo or git_root(start)
    if here is not None and here.is_team:
        return here
    if here is not None and here.team:
        crew = team.find_team(repo, here.team)
        if crew is not None:
            return crew
    if repo is None and not walk_without_git:
        # The current folder outside any repository may be a home folder, which is too big to walk.
        return None
    crews = [b for b in team.brains_in(repo or start) if b.is_team]
    if len(crews) > 1:
        names = ", ".join(str(b.root) for b in crews)
        raise BrainError(Finding("team.many", str(repo or start), f"More than one team brain is here: {names}.", "Pass --project with one of them, or save it: brain team use <folder>."), outcome="error")
    return crews[0] if crews else None


def resolve_team(project: Path | None) -> tuple[Brain, str]:
    # --project wins, then the current folder, then the saved path.
    if project is not None:
        crew = locate(project, walk_without_git=True)
        if crew is None:
            raise BrainError(Finding("team.not_found", str(project), "No team brain in this folder, above it, or in its repository.", "Pass --project with the repository that holds the team brain."), outcome="error")
        return crew, "--project"
    crew = locate(Path.cwd(), walk_without_git=False)
    if crew is not None:
        return crew, "the current folder"
    saved = settings.saved_team()
    if saved is None:
        raise BrainError(Finding("team.not_saved", str(Path.cwd()), "No team brain here, and no saved path.", "Run brain team use <the repository that holds the team brain>, or pass --project."), outcome="error")
    crew = locate(saved, walk_without_git=True)
    if crew is None:
        raise BrainError(Finding("team.not_found", str(saved), f"The saved path {saved} holds no team brain now.", "Run brain team use <the repository that holds the team brain>."), outcome="error")
    return crew, f"the saved path ({settings.path()})"


def members_of(crew: Brain) -> list[Member]:
    repo = team.repo_root(crew) or crew.root.parent
    found = []
    for name, source in sorted(team.roster(load_records(crew)).items()):
        agent = team.brain_at(repo, source) if source else None
        record = load_records(agent).agent if agent is not None and not agent.is_team else None
        meta = record.meta if record is not None else {}
        display = meta.get("display_name")
        job = meta.get("job")
        found.append(Member(name, display if isinstance(display, str) and display else name, " ".join(job.split()) if isinstance(job, str) else "", agent if record is not None else None, meta))
    return found


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def match(members: list[Member], who: str) -> list[Member]:
    key = who.strip().lower()
    tiers = (lambda m: m.display_name.lower() == key, lambda m: m.name.lower() == key, lambda m: key in words(m.job))
    for tier in tiers:
        hits = [m for m in members if tier(m)]
        if hits:
            return hits
    return []


def roster_lines(members: list[Member]) -> list[str]:
    width_display = max((len(m.display_name) for m in members), default=0)
    width_name = max((len(m.name) for m in members), default=0)
    return [f"  {m.display_name:<{width_display}}   {m.name:<{width_name}}   {m.job}".rstrip() for m in members]


@dataclass(frozen=True)
class Freshness:
    behind: int = 0
    fetch_error: str = ""
    upstream: bool = True


def freshness(repo: Path, fetch: bool = True) -> Freshness:
    error = ""
    if fetch:
        fetched = subprocess.run(["git", "-C", str(repo), "fetch", "--quiet"], capture_output=True, text=True)
        if fetched.returncode != 0:
            error = (fetched.stderr.strip().splitlines() or ["no network"])[-1]
    count = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "HEAD..@{upstream}"], capture_output=True, text=True)
    if count.returncode != 0:
        return Freshness(0, error, upstream=False)
    return Freshness(int(count.stdout.strip() or 0), error)


def books_by_source(books: tuple[str, ...]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for entry in books:
        source, _, bid = entry.rpartition(":")
        if source and bid:
            grouped.setdefault(source, []).append(bid)
    return grouped


def outside(folders: list[Path], here: Path) -> list[Path]:
    top = (git_root(here) or here).resolve()
    return [f for f in folders if not f.is_relative_to(top)]


def instruction(display_name: str, skill_files: list[Path], books: tuple[str, ...]) -> str:
    # One fixed template. The agent's own SKILL.md holds who it is; this only says which files to read.
    lines = [f"You are {display_name}. Before your first answer, read these skills in this order and follow them:", *(str(p) for p in skill_files)]
    lines += [f"Your books from {source}: {', '.join(ids)}." for source, ids in books_by_source(books).items()]
    return "\n".join(lines)
