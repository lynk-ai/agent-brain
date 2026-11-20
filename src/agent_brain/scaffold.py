import datetime as dt
import subprocess
from importlib import resources
from pathlib import Path

from . import index
from .brain import CONFIG_FILE, Brain, load_config
from .checks import as_list, scan_sensitive
from .output import BrainError, Finding
from .records import FEEDBACK, ID_PATTERN, TEAM_FEEDBACK, as_date, LANES_REF, Record, Records, kinds_of, linkable_of, load, slug, write_record

TEMPLATES = resources.files("agent_brain") / "templates"
TODO = "TODO:"


def template(relative: str, name: str, display_name: str = "") -> str:
    return (TEMPLATES / relative).read_text().replace("{{display}}", display_name or name).replace("{{name}}", name)


def init(folder: Path, name: str, git: bool = True, seed: bool = True, display_name: str = "") -> Brain:
    check_new_folder(folder, name)

    skill = folder / name
    refs = skill / "references"
    for sub in ("feedback", "rules", "procedures", "topics", "routines"):
        (refs / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("reports", "harness"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
        (folder / sub / ".gitkeep").write_text("")
    (refs / "feedback" / ".gitkeep").write_text("")
    (refs / "rules" / ".gitkeep").write_text("")

    (folder / CONFIG_FILE).write_text(template("brain.yaml", name))
    (skill / "SKILL.md").write_text(template("SKILL.md", name, display_name))
    (skill / "agent.md").write_text(template("agent.md", name, display_name))
    for kind in ("procedures", "topics", "routines") if seed else ():
        for source in sorted((TEMPLATES / kind).iterdir()):
            if source.name.endswith(".md"):
                (refs / kind / source.name).write_text(template(f"{kind}/{source.name}", name))

    brain = Brain(root=folder.resolve(), config=load_config(folder / CONFIG_FILE))
    index.write(brain, load(brain))
    if git and not inside_git(folder):
        subprocess.run(["git", "init", "-q", str(folder)], check=False)
    return brain


def init_team(folder: Path, name: str, git: bool = True) -> Brain:
    check_new_folder(folder, name)
    refs = folder / name / "references"
    for sub in ("agents", "feedback", "policies", "routines", "topics"):
        (refs / sub).mkdir(parents=True, exist_ok=True)
        (refs / sub / ".gitkeep").write_text("")
    (folder / "reports").mkdir(parents=True, exist_ok=True)
    (folder / "reports" / ".gitkeep").write_text("")
    (folder / CONFIG_FILE).write_text(template("team/brain.yaml", name))
    (folder / name / "SKILL.md").write_text(template("team/SKILL.md", name))
    (refs / "lanes.md").write_text(template("team/lanes.md", name))
    (refs / "topics" / "how-the-team-works.md").write_text(template("team/topic.md", name))
    if git and not inside_git(folder):
        subprocess.run(["git", "init", "-q", str(folder)], check=False)
    brain = Brain(root=folder.resolve(), config=load_config(folder / CONFIG_FILE))
    index.write(brain, load(brain))
    return brain


def check_new_folder(folder: Path, name: str) -> None:
    if not ID_PATTERN.match(name) or len(name) > 64:
        raise BrainError(Finding("init.bad_name", name, "A brain's name is lowercase letters, digits and single hyphens, at most 64 characters.", "Choose a name such as help-center-writer."), outcome="error")
    if folder.exists() and any(folder.iterdir()):
        raise BrainError(Finding("init.not_empty", str(folder), "The folder exists and is not empty.", "Choose a new folder with --path."))


def inside_git(folder: Path) -> bool:
    result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return result.returncode == 0


def git_root(folder: Path) -> Path | None:
    result = subprocess.run(["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def refuse_sensitive(field: str, text: str) -> None:
    labels = scan_sensitive(text)
    if labels:
        raise BrainError(
            Finding("data.sensitive", field, f"It looks like it holds {', '.join(labels)}.", "Replace it with a marker such as [email removed], then run the command again."),
        )


def add_feedback(
    brain: Brain, *, name: str, words: str, source_role: str, kind: str, source: str, did: str = "", context: str = "", date: dt.date | None = None, rid: str = "",
    intake_of: str = "",
) -> Record:
    if brain.is_team:
        heard = intake_record(brain, intake_of)
        intake_of = intake_of.strip()
        source = source or str(heard.meta.get("source") or "")
        # The intake keeps the person's words as the agent recorded them, so the agent's record fills what is not given.
        words = words if words.strip() else heard.sections.get("Feedback", "")
        name = name or str(heard.meta.get("name") or "")
        source_role = source_role or str(heard.meta.get("from") or "")
        kind = kind or str(heard.meta.get("kind") or "")
        did = did or str(heard.meta.get("what_agent_did") or "")
        date = date or as_date(heard.meta.get("date"))
    date = date or dt.date.today()
    if date > dt.date.today():
        raise BrainError(Finding("feedback.future_date", date.isoformat(), "The date is in the future.", "Pass the date the feedback was given."), outcome="error")
    if kind in ("correction", "incident") and not did.strip():
        raise BrainError(Finding("feedback.no_did", "--did", f"A {kind} needs what the agent had done.", "Pass --did \"<what you had done>\"."), outcome="error")
    if rid and not ID_PATTERN.match(rid):
        raise BrainError(Finding("record.bad_id", rid, "An id is lowercase words joined by single hyphens.", "Use an id such as keep-titles-short."), outcome="error")
    if kind not in FEEDBACK.fields["kind"].choices:
        raise BrainError(Finding("feedback.kind", kind, "Unknown kind.", f"Use one of: {', '.join(FEEDBACK.fields['kind'].choices)}."), outcome="error")
    if not words.strip():
        raise BrainError(Finding("feedback.empty", "--text", "The feedback has no words.", "Pass the words as said with --text, or on stdin."), outcome="error")
    for label, text in (("--name", name), ("--text", words), ("--from", source_role), ("--source", source), ("--did", did), ("--context", context)):
        refuse_sensitive(label, text)

    folder = brain.references / "feedback"
    folder.mkdir(parents=True, exist_ok=True)
    if rid:
        if (folder / f"{rid}.md").exists():
            raise BrainError(Finding("record.exists", f"feedback/{rid}", "It already exists.", "Choose another --id."))
    else:
        base = f"{date.isoformat()}-{slug(name)}"
        rid, n = base, 2
        while (folder / f"{rid}.md").exists():
            rid, n = f"{base}-{n}", n + 1

    meta = {"name": name.strip(), "date": date, "from": source_role.strip(), "kind": kind, "source": source.strip()}
    if did.strip():
        meta["what_agent_did"] = did.strip()
    if brain.is_team:
        meta["intake_of"] = intake_of
    meta.update({"disposition": "new", "kept_in": []})
    body = f"## Feedback\n\n{words.strip()}\n"
    if context.strip():
        body += f"\n## Context\n\n{context.strip()}\n"
    record = Record(TEAM_FEEDBACK if brain.is_team else FEEDBACK, rid, folder / f"{rid}.md", meta, body)
    write_record(record)
    return record


def intake_record(brain: Brain, pointer: str) -> Record:
    from . import team

    match = team.POINTER.match(pointer.strip())
    if not match:
        raise BrainError(Finding("intake.bad_pointer", "--intake-of", "In a team brain, feedback is an intake: --intake-of is brain:<agent>/<feedback-id>.", "Pass the agent's feedback record that points to the team."), outcome="error")
    source = pointer.strip()
    repo = team.require_repo(brain)
    agent = next((b for b in team.brains_in(repo) if b.name == match.group(1) and not b.is_team), None)
    heard = load(agent).by_folder["feedback"].get(match.group(2)) if agent else None
    if heard is None:
        raise BrainError(Finding("intake.unresolved", source, f"{source} names no feedback record in this repository.", "Name the agent's feedback record that points to the team."), outcome="error")
    if f"brain:{brain.name}" not in as_list(heard.meta.get("kept_in")):
        raise BrainError(Finding("intake.not_pointed", source, f"{source} does not point to brain:{brain.name}.", f"In {agent.name}'s brain, run brain feedback set {heard.id} elsewhere --to brain:{brain.name} --reason \"<why>\"."))
    return heard


def set_disposition(brain: Brain, feedback_id: str, disposition: str, reason: str, pointers: list[str] = ()) -> Record:
    records = load(brain)
    fb = require(records, f"feedback/{feedback_id}")
    if disposition == "kept":
        raise BrainError(Finding("feedback.use_link", feedback_id, "kept needs the record it became.", f"Run brain link {feedback_id} rules/<id>."), outcome="error")
    if disposition not in FEEDBACK.fields["disposition"].choices:
        raise BrainError(Finding("feedback.disposition", disposition, "Unknown disposition.", "Use pending, one-off, elsewhere or declined."), outcome="error")
    if fb.meta.get("disposition") == "kept" and as_list(fb.meta.get("kept_in")):
        raise BrainError(Finding("feedback.linked", feedback_id, "It is linked to records.", f"Run brain unlink {feedback_id} <record> for each one first."))
    if disposition == "elsewhere" and not pointers:
        raise BrainError(Finding("feedback.elsewhere_pointer", feedback_id, "elsewhere needs where the lesson lives.", "Pass --to <kind>:<name>, with kind brain, plugin, book or doc, such as --to plugin:lynk-for-analyst."), outcome="error")
    if pointers and disposition != "elsewhere":
        raise BrainError(Finding("feedback.pointer_not_elsewhere", feedback_id, "--to is only for elsewhere.", "Leave out --to."), outcome="error")
    from .checks import pointer_problem

    for pointer in pointers:
        problem = pointer_problem(brain, pointer)
        if problem:
            raise BrainError(Finding("feedback.elsewhere_pointer", pointer, problem, "Name a place that exists."), outcome="error")
    if not reason.strip():
        raise BrainError(Finding("feedback.no_reason", feedback_id, f"{disposition} needs a reason.", "Pass --reason \"<why>\"."), outcome="error")
    refuse_sensitive("--reason", reason)
    fb.meta["disposition"] = disposition
    fb.meta["kept_in"] = list(pointers)
    fb.body = add_to_section(fb.body, "Context", f"{dt.date.today().isoformat()}, {disposition}: {reason.strip()}")
    write_record(fb)
    return fb


def add_to_section(body: str, heading: str, line: str) -> str:
    marker = f"## {heading}"
    if marker not in body:
        return f"{body.rstrip()}\n\n{marker}\n\n{line}\n"
    head, _, tail = body.partition(marker)
    rest = tail.split("\n## ", 1)
    section = rest[0].rstrip() + f"\n\n{line}\n"
    return head + marker + section + (f"\n## {rest[1]}" if len(rest) > 1 else "")


def link(brain: Brain, feedback_id: str, target_ref: str) -> tuple[Record, Record | None]:
    records = load(brain)
    fb = require(records, f"feedback/{feedback_id}")
    target = None
    if target_ref != "agent" or brain.is_team:
        target = require(records, target_ref, linkable=linkable_of(brain), agent=not brain.is_team)
        ids = as_list(target.meta.get("feedback"))
        if feedback_id not in ids:
            target.meta["feedback"] = [*ids, feedback_id]
            write_record(target)
    kept_in = as_list(fb.meta.get("kept_in"))
    if target_ref not in kept_in:
        fb.meta["kept_in"] = [*kept_in, target_ref]
    fb.meta["disposition"] = "kept"
    write_record(fb)
    return fb, target


def unlink(brain: Brain, feedback_id: str, target_ref: str) -> Record:
    records = load(brain)
    fb = require(records, f"feedback/{feedback_id}")
    if target_ref != "agent" or brain.is_team:
        target = require(records, target_ref, linkable=linkable_of(brain), agent=not brain.is_team)
        target.meta["feedback"] = [f for f in as_list(target.meta.get("feedback")) if f != feedback_id]
        write_record(target)
    fb.meta["kept_in"] = [r for r in as_list(fb.meta.get("kept_in")) if r != target_ref]
    if not fb.meta["kept_in"]:
        fb.meta["disposition"] = "new"
    write_record(fb)
    return fb


def target_names(targets: tuple[str, ...], agent: bool = False) -> str:
    names = ["lanes" if t == LANES_REF else f"{t}/<id>" for t in targets] + (["agent"] if agent else [])
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def require(records: Records, ref: str, linkable: tuple[str, ...] = (), action: str = "Feedback links only to", agent: bool = False) -> Record:
    folder = ref.partition("/")[0]
    if linkable and folder not in linkable:
        names = target_names(linkable, agent)
        raise BrainError(Finding("link.target", ref, f"{action} {names}.", f"Name the record as {names}."), outcome="error")
    record = records.get(ref)
    if record is None and ref == LANES_REF:
        raise BrainError(Finding("record.not_found", ref, "The team has no lanes.md.", "Run brain index, which writes it."), outcome="error")
    if record is None:
        known = sorted(records.by_folder.get(folder, {}))
        hint = f"Known: {', '.join(known[:10])}." if known else f"There are no {folder} yet."
        raise BrainError(Finding("record.not_found", ref, f"{ref} does not exist.", hint), outcome="error")
    return record


def new_record(
    brain: Brain, kind_folder: str, rid: str, values: dict, feedback_ids: list[str] = (), topics: list[str] = (), rules: list[str] = (), body: str | None = None
) -> Record:
    kinds = kinds_of(brain)
    if kind_folder not in kinds or kind_folder == "agents":
        where = "a team brain" if brain.is_team else "an agent brain"
        raise BrainError(Finding("new.kind", kind_folder, f"{where.capitalize()} has no {kind_folder}.", f"In {where}, write one of: {', '.join(k for k in kinds if k not in ('feedback', 'agents'))}."), outcome="error")
    if kind_folder == "routines" and brain.team:
        raise BrainError(Finding("new.routine_in_team", kind_folder, f"{brain.name} is in team {brain.team}, whose brain holds every routine.", f"Run brain new routine <id> in the {brain.team} team brain."))
    kind = kinds[kind_folder]
    if not ID_PATTERN.match(rid):
        raise BrainError(Finding("record.bad_id", rid, "An id is lowercase words joined by single hyphens.", "Use an id such as check-every-screen."), outcome="error")
    path = brain.references / kind_folder / f"{rid}.md"
    if path.exists():
        raise BrainError(Finding("record.exists", brain.rel(path), "It already exists.", "Edit it, or choose another id."))
    for label, text in {**values, "body-file": body}.items():
        if isinstance(text, str):
            refuse_sensitive(f"--{label}", text)
    if topics and kind_folder not in ("rules", "procedures", "policies"):
        raise BrainError(Finding("new.topic", "--topic", "Only rules, procedures and policies have topics.", "Leave out --topic."), outcome="error")
    if rules and kind_folder != "procedures":
        raise BrainError(Finding("new.rule", "--rule", "Only procedures list rules.", "Leave out --rule."), outcome="error")
    if feedback_ids and kind_folder not in linkable_of(brain):
        raise BrainError(Finding("new.feedback", "--feedback", f"Only {' and '.join(linkable_of(brain)[:2])} link feedback.", "Leave out --feedback."), outcome="error")
    records = load(brain)
    for fid in feedback_ids:
        require(records, f"feedback/{fid}")
    for tid in topics:
        require(records, f"topics/{tid}")
    for r in rules:
        require(records, f"rules/{r}")

    meta, skeleton = SKELETONS[kind_folder](rid, values, brain)
    if kind_folder in ("rules", "procedures", "policies"):
        meta["topics"] = list(topics)
    if kind_folder == "procedures":
        meta["rules"] = list(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = Record(kind, rid, path, meta, body if body is not None and body.strip() else skeleton)
    write_record(record)
    for fid in feedback_ids:
        link(brain, fid, record.ref)
    return record


def set_status(brain: Brain, ref: str, status: str, reason: str) -> Record:
    folders = ("policies", "routines") if brain.is_team else ("rules", "procedures", "routines")
    record = require(load(brain), ref, linkable=folders, action="set-status takes only")
    # Each kind has its own statuses: a routine is active, paused or retired, and has no proposed.
    allowed = record.kind.fields["status"].choices
    if status not in allowed:
        raise BrainError(Finding("status.value", ref, f"A {record.kind.name} has no status {status}.", f"Use one of: {', '.join(allowed)}."), outcome="error")
    if status == "retired" and not reason.strip():
        raise BrainError(Finding("status.no_reason", ref, "Retiring needs a reason.", "Pass --reason \"<what went wrong, and when>\"."), outcome="error")
    refuse_sensitive("--reason", reason)
    record.meta["status"] = status
    if reason.strip():
        heading = "Why" if record.kind.folder in ("rules", "policies") else "Context"
        record.body = add_to_section(record.body, heading, f"{dt.date.today().isoformat()}, {status}: {reason.strip()}")
    write_record(record)
    index.write(brain, load(brain))
    return record


def todo(value: str | None, what: str) -> str:
    return value.strip() if value and value.strip() else f"{TODO} {what}"


def rule_skeleton(rid, v, brain):
    meta = {
        "name": todo(v.get("name"), "the rule as one imperative sentence"),
        "description": todo(v.get("description"), "one line, enough to act on without opening the file"),
        "status": "proposed",
        "strength": "default",
        "scope": todo(v.get("scope"), "where it applies"),
        "feedback": [],
        "topics": [],
    }
    body = f"## Rule\n\n{TODO} the invariant only, no steps.\n\n## Why\n\n{TODO} what went wrong, with the dates of its feedback.\n\n## How to apply\n\n{TODO} when it fires, one do and one don't.\n"
    return meta, body


def procedure_skeleton(rid, v, brain):
    meta = {
        "name": todo(v.get("name"), "what the procedure does"),
        "description": todo(v.get("description"), "one line"),
        "status": "proposed",
        "trigger": todo(v.get("trigger"), "what starts it"),
        "outputs": todo(v.get("outputs"), "what it leaves behind, so you can check it ran"),
        "rules": [],
        "feedback": [],
        "topics": [],
    }
    body = f"## Steps\n\n1. {TODO} one action per step; write a decision as \"If this, do that.\"\n"
    return meta, body


def topic_skeleton(rid, v, brain):
    meta = {"name": todo(v.get("name"), "the subject"), "description": todo(v.get("description"), "one line")}
    return meta, f"## Scope\n\n{TODO} what belongs under this topic.\n"


def policy_skeleton(rid, v, brain):
    meta, _ = rule_skeleton(rid, v, brain)
    meta["name"] = todo(v.get("name"), "the policy as one imperative sentence")
    body = f"## Policy\n\n{TODO} the invariant only, no steps.\n\n## Why\n\n{TODO} what went wrong or what the team decided, with dates.\n\n## How to apply\n\n{TODO} when it fires, one do and one don't.\n"
    return meta, body


def routine_skeleton(rid, v, brain):
    meta = {
        "name": todo(v.get("name"), "the routine"),
        "description": todo(v.get("description"), "one line"),
        "trigger": todo(v.get("trigger"), "a time or an event"),
        "owner": todo(v.get("owner"), "the agent on the roster that runs it") if brain.is_team else brain.name,
        "procedure": todo(v.get("procedure"), "<agent>:<procedure-id> it runs" if brain.is_team else "the procedure id it runs"),
        "inputs": [],
        "receiver": todo(v.get("receiver"), "the role that gets the result"),
        "when_nothing_new": "Write the run log and send nothing.",
        "status": "active",
    }
    return meta, ""


SKELETONS = {"rules": rule_skeleton, "procedures": procedure_skeleton, "topics": topic_skeleton, "routines": routine_skeleton, "policies": policy_skeleton}

