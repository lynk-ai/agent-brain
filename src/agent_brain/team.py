import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .brain import CONFIG_FILE, Brain, find_all, load_config
from .output import BrainError, Finding
from .records import LANES_FILE, Records, load

LANES_HEADER = ("Work", "Owner")
POINTER = re.compile(r"^brain:([a-z0-9]+(?:-[a-z0-9]+)*)/([a-z0-9]+(?:-[a-z0-9]+)*)$")


@dataclass(frozen=True)
class Lane:
    work: str
    owner: str
    line: int


def repo_root(brain: Brain, repo: Path | None = None) -> Path | None:
    # check --staged copies the index to a folder with no .git, so the caller names the top folder there.
    if repo is not None:
        return repo
    from .plugin import git

    top = git(brain.root, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def brain_at(repo: Path, source: str) -> Brain | None:
    folder = (repo / source).resolve()
    if not folder.is_relative_to(repo.resolve()) or not (folder / CONFIG_FILE).is_file():
        return None
    try:
        return Brain(root=folder, config=load_config(folder / CONFIG_FILE))
    except BrainError:
        return None


def brains_in(repo: Path) -> list[Brain]:
    try:
        return find_all(repo)
    except BrainError:
        return []


def find_team(repo: Path | None, name: str) -> Brain | None:
    if repo is None:
        return None
    return next((b for b in brains_in(repo) if b.is_team and b.name == name), None)


def source_of(brain: Brain, repo: Path) -> str:
    return str(brain.root.resolve().relative_to(repo.resolve()))


def roster_sources(team: Brain) -> list[str]:
    value = team.config.get("agents") or []
    return [str(v) for v in value] if isinstance(value, list) else []


def roster(team: Brain, repo: Path | None = None) -> dict[str, str]:
    # The team's brain.yaml lists each agent's folder; the agent's name is the one its own brain.yaml gives.
    repo = repo_root(team, repo) or team.root.parent
    found: dict[str, str] = {}
    for source in roster_sources(team):
        agent = brain_at(repo, source)
        found.setdefault(agent.name if agent is not None else Path(source).name, source)
    return found


def members(team: Brain, repo: Path) -> dict[str, Brain]:
    found = {}
    for name, source in roster(team, repo).items():
        agent = brain_at(repo, source) if source else None
        if agent is not None and not agent.is_team:
            found[name] = agent
    return found


def parse_lanes(records: Records, where: str) -> tuple[list[Lane], list[Finding]]:
    # lanes.md holds one Markdown table, | Work | Owner |, under ## Lanes. Each row is one piece of work.
    if records.lanes is None:
        return [], []
    lanes, problems = [], []
    lines = records.lanes.path.read_text().splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "## Lanes"), len(lines))
    rows = []
    for number, line in enumerate(lines[start + 1 :], start=start + 2):
        if line.startswith("## "):
            break
        if line.strip().startswith("|"):
            rows.append((number, line))
    if not rows:
        return [], problems
    header = [c.strip() for c in rows[0][1].strip().strip("|").split("|")]
    if tuple(header) != LANES_HEADER:
        problems.append(Finding("lanes.bad_table", where, f"The table's header is {' | '.join(header)}, not Work | Owner.", "Write the header as | Work | Owner |."))
        return [], problems
    for number, line in rows[1:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != 2 or not cells[0] or not cells[1]:
            problems.append(Finding("lanes.bad_table", f"{where}:{number}", "A row needs the work and one owner.", "Write | <work> | <agent> |."))
            continue
        lanes.append(Lane(cells[0], cells[1], number))
    return lanes, problems


def work_key(work: str) -> str:
    return " ".join(work.lower().split())


def render_lanes(lanes: list[Lane]) -> str:
    rows = [f"| {lane.work} | {lane.owner} |" for lane in lanes]
    return "\n".join(["| Work | Owner |", "|---|---|", *rows])


def write_lanes(team: Brain, records: Records, lanes: list[Lane]) -> None:
    from .records import LANES, Record, write_record

    path = team.references / LANES_FILE
    record = records.lanes or Record(LANES, "lanes", path, {"feedback": []}, "")
    intro = "Each row is one piece of work, with exactly one owner agent."
    record.body = f"## Lanes\n\n{intro}\n\n{render_lanes(lanes)}\n"
    write_record(record)


def lanes_of(brain: Brain, repo: Path | None) -> list[str]:
    crew = find_team(repo, brain.team) if brain.team else None
    if crew is None:
        return []
    lanes, _ = parse_lanes(load(crew), "")
    return [lane.work for lane in lanes if lane.owner == brain.name]


def reindex_members(crew: Brain, repo: Path) -> list[str]:
    from . import index

    done = []
    for name, agent in sorted(members(crew, repo).items()):
        if agent.team == crew.name and agent.skill_file.is_file():
            index.write(agent, load(agent), repo)
            done.append(name)
    return done


def check_member(brain: Brain, records: Records, repo: Path | None) -> list[Finding]:
    # An agent brain in a team: the team brain holds its routines and lanes.
    if not brain.team:
        return []
    findings = []
    for routine in records.by_folder["routines"].values():
        findings.append(Finding("team.agent_has_routine", brain.rel(routine.path), f"{brain.name} is in team {brain.team}, whose brain holds every routine.", f"Run brain team add {source_or_root(brain, repo)} in the team brain, which moves it."))
    if records.agent is not None and records.agent.meta.get("lane"):
        findings.append(Finding("team.agent_has_lane", brain.rel(records.agent.path), f"{brain.name} is in team {brain.team}, whose lanes.md holds every lane.", "Move each lane row into the team's lanes.md, and remove lane from agent.md."))
    team = find_team(repo, brain.team)
    if team is None:
        findings.append(Finding("team.not_found", "brain.yaml", f"team names {brain.team!r}, but no team brain of that name is in this repository.", "Fix team:, or create it with brain init <team> --team."))
    elif brain.name not in roster(team, repo):
        findings.append(Finding("team.not_member", "brain.yaml", f"team names {brain.team}, but its roster does not list {brain.name}.", f"Run brain team add {source_or_root(brain, repo)} --project {team.root}."))
    return findings


def source_or_root(brain: Brain, repo: Path | None) -> str:
    return source_of(brain, repo) if repo else str(brain.root)


def team_pointer_problem(brain: Brain, target: str, repo: Path | None) -> str:
    team = brain if brain.is_team else find_team(repo, brain.team or "")
    if team is None:
        return f"kept_in names brain:{target}, but team {brain.team} is not in this repository."
    if target == team.name or target in roster(team, repo):
        return ""
    return f"kept_in names brain:{target}, which is neither team {team.name} nor an agent on its roster."


def check_team(brain: Brain, records: Records, today, repo: Path | None) -> list[Finding]:
    findings: list[Finding] = []
    if repo is None:
        return [Finding("team.no_repository", brain.rel(brain.root), "A team brain must be in a git repository, with its agents.", "Run git init in the repository's top folder.")]
    agents: dict[str, Brain] = {}
    listed = brain.config.get("agents")
    if listed is not None and not (isinstance(listed, list) and all(isinstance(v, str) for v in listed)):
        findings.append(Finding("brain.config", "brain.yaml", "agents must be a list of agent brain folders.", "Write agents: [<folder>, <folder>], each from the repository's top folder."))
    domain = brain.config.get("domain")
    for source in roster_sources(brain):
        agent = brain_at(repo, source)
        if agent is None or agent.is_team:
            findings.append(Finding("team.source_missing", "brain.yaml", f"agents lists {source!r}, which is not an agent brain in this repository.", "Give the agent brain's folder, from the repository's top folder, or run brain team remove."))
            continue
        if agent.name in agents:
            findings.append(Finding("team.entry_name", "brain.yaml", f"agents lists two brains named {agent.name}.", "Give one of the two agents another name."))
            continue
        if agent.team != brain.name:
            findings.append(Finding("team.agent_not_in_team", "brain.yaml", f"{agent.name}'s brain.yaml does not say team: {brain.name}.", f"Run brain team add {source}."))
        if isinstance(domain, str) and domain and not agent.name.startswith(f"{domain}-"):
            findings.append(Finding("team.name_domain", "brain.yaml", f"{agent.name} does not start with the team's domain, {domain}.", f"Name it {domain}-<role>-brain, if it belongs to {domain}.", "warn"))
        agents[agent.name] = agent

    names = set(roster(brain, repo))
    where = f"{brain.rel(brain.references)}/lanes.md"
    lanes, problems = parse_lanes(records, where)
    findings += problems
    if records.lanes is None:
        findings.append(Finding("lanes.missing", where, "The team has no lanes.md.", "Run brain index, which writes an empty one, then add a row for each piece of work."))
    seen: dict[str, Lane] = {}
    for lane in lanes:
        if lane.owner not in names:
            findings.append(Finding("lanes.unknown_owner", f"{where}:{lane.line}", f"The owner {lane.owner!r} is not on the roster.", "Name an agent from agents: in the team's brain.yaml, or run brain team add."))
        key = work_key(lane.work)
        if key in seen:
            findings.append(Finding("lanes.duplicate", f"{where}:{lane.line}", f"{lane.work!r} is also on line {seen[key].line}.", "Keep one row, with its one owner."))
        seen.setdefault(key, lane)
    owners = {lane.owner for lane in lanes}
    for name in sorted(names):
        if name not in owners:
            findings.append(Finding("lanes.agent_without_lane", where, f"{name} owns no work in lanes.md.", f"Add a row with {name} as its owner, or remove the agent.", "warn"))

    for routine in records.by_folder["routines"].values():
        if routine.meta.get("status") == "retired":
            continue
        findings += check_routine(brain, routine, names, agents, owners)

    findings += check_intake(brain, records, repo)
    findings += check_open_pointers(brain, records, agents, today)
    findings += check_team_loads(brain, agents, repo)
    return findings


def check_routine(brain: Brain, routine, names: set[str], agents: dict[str, Brain], owners: set[str]) -> list[Finding]:
    findings = []
    where = brain.rel(routine.path)
    owner = routine.meta.get("owner")
    if isinstance(owner, str) and owner and owner not in names:
        findings.append(Finding("routine.unknown_owner", where, f"owner {owner!r} is not on the roster.", "Name an agent from agents: in the team's brain.yaml."))
    elif isinstance(owner, str) and owner and owner not in owners:
        findings.append(Finding("routine.owner_no_lane", where, f"owner {owner} owns no work in lanes.md.", f"Add the routine's work to lanes.md with {owner} as its owner, or give the routine to the agent that owns it.", "warn"))
    pointer = routine.meta.get("procedure")
    if not isinstance(pointer, str) or not pointer:
        return findings
    agent_name, sep, pid = pointer.partition(":")
    if not sep or not agent_name or not pid:
        findings.append(Finding("routine.bad_procedure", where, f"procedure {pointer!r} is not <agent>:<procedure-id>.", "Name the agent and its procedure, such as leo:run-the-dream."))
        return findings
    if isinstance(owner, str) and owner and owner != agent_name:
        findings.append(Finding("routine.owner_not_runner", where, f"owner is {owner}, but the procedure is {agent_name}'s.", f"Give the routine to {agent_name}, or point it to a procedure in {owner}'s brain.", "warn"))
    agent = agents.get(agent_name)
    if agent is None:
        findings.append(Finding("routine.unresolved_procedure", where, f"procedure names agent {agent_name!r}, which is not on the roster.", "Name an agent from agents: in the team's brain.yaml."))
    elif pid not in load(agent).by_folder["procedures"]:
        findings.append(Finding("routine.unresolved_procedure", where, f"procedure names {pid!r}, which is not in {agent_name}'s brain.", f"Name a file from {agent_name}'s references/procedures/ without .md."))
    return findings


def check_intake(brain: Brain, records: Records, repo: Path) -> list[Finding]:
    # Every team feedback is an intake: an agent heard it, kept it in its own brain, and pointed it here.
    findings = []
    by_name = {b.name: b for b in brains_in(repo) if not b.is_team}
    for fb in records.by_folder["feedback"].values():
        where = brain.rel(fb.path)
        source = str(fb.meta.get("intake_of") or "")
        if not source:
            continue  # record.missing_field reports it.
        match = POINTER.match(source)
        if not match:
            findings.append(Finding("intake.bad_pointer", where, f"intake_of {source!r} is not brain:<agent>/<feedback-id>.", "Name the agent's feedback record that pointed it here."))
            continue
        agent = by_name.get(match.group(1))
        heard = load(agent).by_folder["feedback"].get(match.group(2)) if agent else None
        if heard is None:
            findings.append(Finding("intake.unresolved", where, f"intake_of {source} names no feedback record in this repository.", "Name the agent's feedback record that pointed it here."))
        elif f"brain:{brain.name}" not in [str(v) for v in heard.meta.get("kept_in") or []]:
            findings.append(Finding("intake.not_pointed", where, f"{source} does not point to brain:{brain.name}.", f"In {match.group(1)}'s brain, run brain feedback set {match.group(2)} elsewhere --to brain:{brain.name} --reason \"<why>\"."))
    return findings


def check_open_pointers(brain: Brain, records: Records, agents: dict[str, Brain], today) -> list[Finding]:
    from .records import as_date

    taken = {str(fb.meta.get("intake_of")) for fb in records.by_folder["feedback"].values()}
    findings = []
    for name, agent in sorted(agents.items()):
        for fb in load(agent).by_folder["feedback"].values():
            if fb.meta.get("disposition") != "elsewhere" or f"brain:{brain.name}" not in [str(v) for v in fb.meta.get("kept_in") or []]:
                continue
            if f"brain:{name}/{fb.id}" in taken:
                continue
            since = elsewhere_since(fb.sections.get("Context", "")) or as_date(fb.meta.get("date"))
            if since and (today - since).days > brain.config["intake_days"]:
                findings.append(
                    Finding(
                        "intake.missing", f"{agent.rel(fb.path)} in {name}", f"It points to the team for {(today - since).days} days, with no intake record.",
                        f"Run brain feedback add --intake-of brain:{name}/{fb.id} in the team brain, and decide it.", "warn",
                    )
                )
    return findings


def elsewhere_since(context: str):
    from .records import as_date

    # brain feedback set writes "<date>, elsewhere: <reason>", but a person may reword it; any dated line that says elsewhere counts.
    dates = re.findall(r"^\W*(\d{4}-\d{2}-\d{2})\b.*\belsewhere\b", context, re.MULTILINE | re.IGNORECASE)
    return as_date(dates[-1]) if dates else None


# A routine's team id carries its agent's name, so two agents' seeded routines never collide, whatever the join order.
def team_routine_id(agent: str, rid: str) -> str:
    return rid if rid.startswith(f"{agent}-") else f"{agent}-{rid}"


def team_routine_name(agent: str, name: str) -> str:
    return name if name.endswith(f" ({agent})") else f"{name} ({agent})"


def agent_routine_id(agent: str, rid: str) -> str:
    return rid.removeprefix(f"{agent}-") or rid


def require_repo(team: Brain) -> Path:
    repo = repo_root(team)
    if repo is None:
        raise BrainError(Finding("team.no_repository", str(team.root), "A team brain must be in a git repository, with its agents.", "Run git init in the repository's top folder."), outcome="error")
    return repo


def set_config_lines(brain: Brain, changes: dict[str, object]) -> None:
    # Line edits, not a re-dump, so brain.yaml keeps its comments. A None value removes the key.
    path = brain.root / CONFIG_FILE
    lines = path.read_text().splitlines()
    for key, value in changes.items():
        index = next((i for i, line in enumerate(lines) if line.startswith(f"{key}:")), None)
        if value is None:
            if index is not None:
                del lines[index]
        elif index is not None:
            lines[index] = f"{key}: {value}"
        elif key == "format":
            lines.insert(0, f"{key}: {value}")
        else:
            lines.insert(next((i + 1 for i, line in enumerate(lines) if line.startswith("name:")), len(lines)), f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n")


def flow_list(values: list[str]) -> str:
    # One line, so set_config_lines keeps brain.yaml's comments.
    return "[" + ", ".join(values) + "]"


def add(team: Brain, path: Path) -> list[str]:
    from . import index
    from .brain import FORMAT
    from .records import Record, write_record

    repo = require_repo(team)
    folder = path.resolve()
    agent = brain_at(repo, str(folder.relative_to(repo.resolve()))) if folder.is_relative_to(repo.resolve()) else None
    if agent is None or agent.is_team:
        raise BrainError(Finding("team.source_missing", str(path), "It is not an agent brain in the team's repository.", "Pass the folder that holds the agent's brain.yaml, in the same repository."), outcome="error")
    if agent.team and agent.team != team.name:
        raise BrainError(Finding("team.other_team", str(path), f"{agent.name} is already in team {agent.team}. An agent brain is in one team.", f"Run brain team remove {agent.name} in {agent.team}'s brain first, or copy the brain."))
    source = source_of(agent, repo)
    records = load(team)
    on_roster = roster(team, repo)
    listed = on_roster.get(agent.name)
    if listed is not None and listed != source:
        raise BrainError(Finding("team.entry_name", str(path), f"The roster already has {agent.name}, from {listed}.", "Give one of the two agents another name."))

    agent_records = load(agent)
    lanes, problems = parse_lanes(records, "lanes.md")
    if problems:
        raise BrainError(problems[0])
    owned = {work_key(lane.work): lane for lane in lanes}
    new_lanes = []
    for work in [str(w) for w in (agent_records.agent.meta.get("lane") or [])] if agent_records.agent else []:
        if "|" in work or "\n" in work:
            raise BrainError(Finding("lanes.bad_work", str(path), f"The lane {work!r} holds a | or a line break, which would break the lanes table.", f"Reword the lane in {agent.name}'s agent.md, then run it again."))
        other = owned.get(work_key(work))
        if other is not None and other.owner != agent.name:
            raise BrainError(Finding("lanes.duplicate", str(path), f"{other.owner} already owns {work!r}.", f"Decide which agent owns it, and remove it from the other's lane before you run brain team add."))
        if other is None:
            new_lanes.append(Lane(work, agent.name, 0))
    routines = agent_records.by_folder["routines"]
    targets = {rid: team_routine_id(agent.name, rid) for rid in routines}
    for rid, target in targets.items():
        if target in records.by_folder["routines"]:
            raise BrainError(Finding("team.routine_exists", f"routines/{target}", f"The team already has a routine {target}.", f"Rename {agent.name}'s routine {rid}, then run it again."))

    lines = []
    if listed is None:
        set_config_lines(team, {"agents": flow_list([*roster_sources(team), source])})
        team = Brain(root=team.root, config=load_config(team.root / CONFIG_FILE))
        lines.append(f"  roster: {agent.name} from {source}")
    if new_lanes or records.lanes is None:
        write_lanes(team, records, [*lanes, *new_lanes])
    lines += [f"  lane: {lane.work}" for lane in new_lanes]
    from .records import TEAM_ROUTINE

    for rid, routine in routines.items():
        pointer = str(routine.meta.get("procedure") or "")
        routine.meta["procedure"] = pointer if ":" in pointer or not pointer else f"{agent.name}:{pointer}"
        target = targets[rid]
        routine.meta["name"] = team_routine_name(agent.name, str(routine.meta.get("name") or rid))
        moved = Record(TEAM_ROUTINE, target, team.references / "routines" / f"{target}.md", routine.meta, routine.body)
        moved.path.parent.mkdir(parents=True, exist_ok=True)
        write_record(moved)
        routine.path.unlink()
        lines.append(f"  routine: {target}, procedure {routine.meta['procedure']}")
    if agent_records.agent is not None and "lane" in agent_records.agent.meta:
        del agent_records.agent.meta["lane"]
        write_record(agent_records.agent)
    set_config_lines(agent, {"format": FORMAT, "team": team.name})
    index.write(team, load(team), repo)
    reindex_members(team, repo)
    return lines


def remove(crew: Brain, name: str, choices: dict[str, str]) -> list[str]:
    from . import index
    from .records import ROUTINE, Record, write_record

    repo = require_repo(crew)
    records = load(crew)
    on_roster = roster(crew, repo)
    source = on_roster.get(name)
    if source is None:
        raise BrainError(Finding("record.not_found", "brain.yaml", f"{name} is not on the roster.", f"Known: {', '.join(sorted(on_roster)) or 'none'}."), outcome="error")
    agent = brain_at(repo, source)
    if agent is None or agent.is_team:
        raise BrainError(Finding("team.source_missing", "brain.yaml", f"{name}'s folder {source} is not an agent brain in this repository.", "Fix agents: in the team's brain.yaml first, so its lanes and routines can go back."))
    routines = records.by_folder["routines"]
    owned = {rid: r for rid, r in routines.items() if r.meta.get("owner") == name and r.meta.get("status") != "retired"}
    others = sorted(rid for rid, r in routines.items() if rid not in owned and r.meta.get("status") != "retired" and str(r.meta.get("procedure") or "").startswith(f"{name}:"))
    if others:
        raise BrainError(Finding("team.procedure_in_use", f"routines/{others[0]}", f"Routines of other agents run {name}'s procedures: {', '.join(others)}.", f"Point them to another agent's procedure, or retire them, before you remove {name}."))
    unknown = sorted(set(choices) - set(owned))
    if unknown:
        raise BrainError(Finding("team.routine_choice", f"routines/{unknown[0]}", f"{name} owns no active routine {unknown[0]}.", f"Name only the routines {name} owns: {', '.join(sorted(owned)) or 'none'}."), outcome="error")
    missing = sorted(set(owned) - set(choices))
    if missing:
        raise BrainError(
            Finding("team.routine_choice", f"routines/{missing[0]}", f"{name} owns routines with no choice: {', '.join(missing)}.", "Pass --routine <id>=back, <id>=retire or <id>=<agent> for each one."), outcome="error"
        )
    agent_records = load(agent)
    moves = []
    for rid, choice in sorted(choices.items()):
        routine = owned[rid]
        _, _, pid = str(routine.meta.get("procedure") or "").partition(":")
        if choice == "back":
            if not str(routine.meta.get("procedure") or "").startswith(f"{name}:"):
                raise BrainError(Finding("team.routine_choice", f"routines/{rid}", f"It runs another agent's procedure, so it cannot go back to {name}.", f"Pass --routine {rid}=retire or {rid}=<agent>."))
            if agent_routine_id(name, rid) in agent_records.by_folder["routines"]:
                raise BrainError(Finding("team.routine_exists", f"routines/{rid}", f"{name}'s brain already has a routine {agent_routine_id(name, rid)}.", "Rename one of them first."))
        elif choice != "retire":
            if choice == name or choice not in on_roster:
                raise BrainError(Finding("team.routine_choice", f"routines/{rid}", f"{choice!r} is not another agent on the roster.", "Name back, retire or an agent from agents: in the team's brain.yaml."), outcome="error")
            other = brain_at(repo, on_roster[choice])
            if other is None or pid not in load(other).by_folder["procedures"]:
                raise BrainError(Finding("team.routine_choice", f"routines/{rid}", f"{choice}'s brain has no procedure {pid}.", f"Write procedures/{pid} in {choice}'s brain first, or retire the routine."))
        moves.append((rid, routine, choice, pid))

    lines = []
    for rid, routine, choice, pid in moves:
        if choice == "back":
            back = agent_routine_id(name, rid)
            routine.meta["procedure"] = pid
            routine.meta["name"] = str(routine.meta.get("name") or back).removesuffix(f" ({name})")
            write_record(Record(ROUTINE, back, agent.references / "routines" / f"{back}.md", routine.meta, routine.body))
            routine.path.unlink()
            lines.append(f"  routine {rid}: back to {name} as {back}")
        elif choice == "retire":
            routine.meta["status"] = "retired"
            write_record(routine)
            lines.append(f"  routine {rid}: retired")
        else:
            routine.meta.update({"owner": choice, "procedure": f"{choice}:{pid}"})
            write_record(routine)
            lines.append(f"  routine {rid}: to {choice}")
    lanes, _ = parse_lanes(records, "lanes.md")
    given = [lane.work for lane in lanes if lane.owner == name]
    write_lanes(crew, records, [lane for lane in lanes if lane.owner != name])
    if agent_records.agent is not None and given:
        agent_records.agent.meta["lane"] = [*[str(w) for w in agent_records.agent.meta.get("lane") or []], *given]
        write_record(agent_records.agent)
    lines += [f"  lane back to {name}: {work}" for work in given]
    set_config_lines(crew, {"agents": flow_list([s for s in roster_sources(crew) if s != source])})
    crew = Brain(root=crew.root, config=load_config(crew.root / CONFIG_FILE))
    set_config_lines(agent, {"team": None})
    agent = brain_at(repo, source_of(agent, repo))
    index.write(agent, load(agent), repo)
    index.write(crew, load(crew), repo)
    reindex_members(crew, repo)
    return lines


@dataclass(frozen=True)
class Loads:
    brain: str
    skills: tuple[str, ...]
    books: tuple[str, ...]

    @property
    def brains(self) -> list[str]:
        # The agent's own brain first, then its skills, each once.
        return list(dict.fromkeys([self.brain, *self.skills]))


def loads_of(agent: Brain, meta: dict) -> Loads:
    return Loads(agent.name, tuple(str(s) for s in names_in(meta.get("skills"))), tuple(str(b) for b in names_in(meta.get("books"))))


def names_in(value) -> list:
    if isinstance(value, str):
        return [value]
    return [v for v in value if v] if isinstance(value, list) else []


PATH_PREFIXES = ("./", "../", "/", "~")


@dataclass(frozen=True)
class Skill:
    name: str
    folder: Path
    # A brain ships as a plugin from its root; a plain skill folder has none.
    plugin: Path | None = None

    @property
    def skill_file(self) -> Path:
        return self.folder / "SKILL.md"


@dataclass
class LoadCheck:
    findings: list[Finding]
    resolved: list[Skill]
    unchecked: list[str]


def is_path(entry: str) -> bool:
    return entry.startswith(PATH_PREFIXES)


def skill_folder(entry: str, repo: Path) -> Path:
    # A relative path is read from the repository's top folder, wherever brain runs.
    folder = Path(entry).expanduser()
    return (folder if folder.is_absolute() else repo / folder).resolve()


def skill_name(skill_file: Path) -> str | None:
    from .records import split_front_matter

    try:
        meta, _ = split_front_matter(skill_file.read_text())
    except (OSError, ValueError, yaml.YAMLError):
        return None
    name = (meta or {}).get("name")
    return name if isinstance(name, str) else None


def team_settings(team: Brain) -> tuple[set[str], dict[str, str], list[Finding]]:
    problems = []
    gaps = team.config.get("known_gaps") or []
    if not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
        problems.append(Finding("brain.config", f"{team.name}/brain.yaml", "known_gaps must be a list of skill or brain names.", "Write known_gaps: [<name>, <name>]."))
        gaps = []
    books = team.config.get("books") or {}
    if not isinstance(books, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in books.items()):
        problems.append(Finding("brain.config", f"{team.name}/brain.yaml", "books must map each book source to its list file.", "Write books: {<source>: <list file from the repository's top folder>}."))
        books = {}
    return set(gaps), books, problems


def book_ids(path: Path) -> set[str] | None:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    return {line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")}


def check_loads(team: Brain, agent: Brain, meta: dict, repo: Path, provided: dict[str, Brain] | None = None, lists: dict | None = None) -> LoadCheck:
    # Shared by brain load, where each finding is a warning, and brain check on the team.
    provided = provided if provided is not None else {b.name: b for b in brains_in(repo)}
    lists = lists if lists is not None else {}
    gaps, sources, _ = team_settings(team)
    findings: list[Finding] = []
    where = str(agent.agent_file.resolve().relative_to(repo.resolve()))
    loads = loads_of(agent, meta)
    resolved: list[Skill] = []
    unchecked: list[str] = []
    for name in loads.brains:
        if is_path(name):
            folder = skill_folder(name, repo)
            if not (folder / "SKILL.md").is_file():
                findings.append(Finding("load.bad_path", where, f"{agent.name} loads the path {name}, which is not a folder with a SKILL.md.", "Fix the path in agent.md. A relative path starts from the repository's top folder."))
                continue
            declared = skill_name(folder / "SKILL.md")
            if declared != folder.name:
                findings.append(Finding("load.skill_name", where, f"{name}'s SKILL.md names {declared!r}, not {folder.name!r}, its folder.", "Load the folder whose name is the skill's name, or fix the SKILL.md name.", "warn"))
            resolved.append(Skill(folder.name, folder))
        elif name in provided:
            brain = provided[name]
            resolved.append(Skill(name, brain.skill_dir.resolve(), brain.root.resolve()))
        elif name in gaps:
            findings.append(Finding("load.known_gap", where, f"{agent.name} loads {name}, a known gap in {team.name}'s brain.yaml: no brain provides it yet.", f"Add its brain when it exists, then remove it from known_gaps.", "warn"))
        else:
            findings.append(Finding("load.not_provided", where, f"{agent.name} loads {name}, which no brain in this repository provides.", f"Fix the name in agent.md, load the skill by its path, add the brain, or list it under known_gaps in {team.name}'s brain.yaml."))
    for entry in loads.books:
        source, _, bid = entry.rpartition(":")
        if not source or not bid:
            findings.append(Finding("load.bad_book", where, f"The book {entry!r} is not written <source>:<book id>.", "Write it as <source>:<book id>."))
            continue
        if source not in sources:
            unchecked.append(source)
            continue
        if source not in lists:
            lists[source] = book_ids(repo / sources[source])
        if lists[source] is None:
            findings.append(Finding("load.book_list_missing", where, f"The book list for {source}, {sources[source]}, cannot be read.", f"Fix books: in {team.name}'s brain.yaml, or add the file.", "warn"))
        elif bid not in lists[source]:
            findings.append(Finding("load.book_unlisted", where, f"{agent.name} loads the book {entry}, which is not in {sources[source]}.", f"Fix the id in agent.md, or add it to {sources[source]}.", "warn"))
    return LoadCheck(findings, resolved, list(dict.fromkeys(unchecked)))


def check_team_loads(team: Brain, agents: dict[str, Brain], repo: Path) -> list[Finding]:
    provided = {b.name: b for b in brains_in(repo)}
    lists: dict = {}
    _, _, findings = team_settings(team)
    unchecked: list[str] = []
    for name, agent in sorted(agents.items()):
        agent_record = load(agent).agent
        if agent_record is None:
            continue
        result = check_loads(team, agent, agent_record.meta, repo, provided, lists)
        findings += result.findings
        unchecked += result.unchecked
    for source in dict.fromkeys(unchecked):
        findings.append(Finding("load.no_book_list", "brain.yaml", f"No book list for {source}, so its book ids are not checked.", f"Name its list file: books: {{{source}: <file from the repository's top folder>}}.", "warn"))
    return findings
