import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__, checks, harness, hooks, index, plugin, scaffold, team
from .brain import find, find_all, require_writable
from .output import BLOCK, BrainError, Finding, Result, render_json, render_text
from .records import KINDS, load

DESCRIPTION = "Keep an agent's brain, or a team's brain, a skill in git, whole: feedback, rules, procedures, policies and topics, linked and checked."


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 0
    args.json = bool(getattr(args, "json", False) or args.top_json)
    try:
        args.project = merge_project(getattr(args, "project", None), args.top_project)
        result = args.handler(args)
    except BrainError as exc:
        result = Result(args.command, exc.outcome, exc.finding.message, [exc.finding], next=exc.next)
    except KeyboardInterrupt:
        return 130
    if result is None:
        return 0
    print(render_json(result) if args.json else render_text(result))
    return result.exit_code


def merge_project(after: Path | None, before: Path | None) -> Path | None:
    # A subparser rebuilds its namespace, so the options given before the command arrive under their own names.
    if after and before and after.resolve() != before.resolve():
        raise BrainError(Finding("cli.two_projects", "--project", f"--project is given twice: {before} and {after}.", "Pass --project once."), outcome="error")
    return after or before


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=argparse.SUPPRESS, help="the brain's folder, its installed skill folder, or a folder inside it")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print one JSON object")

    parser = argparse.ArgumentParser(prog="brain", description=DESCRIPTION)
    parser.add_argument("--project", dest="top_project", type=Path, help="the brain's folder, its installed skill folder, or a folder inside it")
    parser.add_argument("--json", dest="top_json", action="store_true", help="print one JSON object")
    sub = parser.add_subparsers(title="commands", metavar="<command>")

    def command(name, handler, help_text, **kwargs):
        p = sub.add_parser(name, help=help_text, description=help_text, parents=[common], **kwargs)
        p.set_defaults(handler=handler, command=name)
        return p

    p = command("init", cmd_init, "Create a brain: brain.yaml, the skill folder, agent.md and the seeded procedures. With --team, create a team brain.")
    p.add_argument("name", help="the agent's or the team's name: lowercase words joined by hyphens")
    p.add_argument("--path", type=Path, help="the folder to create; default ./<name>")
    p.add_argument("--no-git", action="store_true", help="do not run git init or install the pre-commit hook")
    p.add_argument("--no-seed", action="store_true", help="seed no procedures, topic or routine; the brain then needs its own take-feedback")
    p.add_argument("--display-name", default="", help="what the agent is called, such as Mila; default the brain's name")
    p.add_argument("--team", action="store_true", help="create a team brain: the roster, lanes, policies and routines of a team of agent brains")

    p = command("feedback", None, "Add, decide and list feedback.")
    fsub = p.add_subparsers(title="feedback commands", metavar="<action>")
    fp = fsub.add_parser("add", help="Write a feedback record, undecided, in the same turn.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_add, command="feedback add")
    fp.add_argument("--name", default="", help="the feedback in one sentence; in a team brain, default the agent's record's")
    fp.add_argument("--from", dest="source_role", default="", help="the person who gave it, by name or role; in a team brain, default the agent's record's")
    fp.add_argument("--kind", default="", choices=("", *KINDS["feedback"].fields["kind"].choices), help="in a team brain, default the agent's record's")
    fp.add_argument("--source", required=True, help="where it was said; in a team brain, brain:<agent>/<feedback-id>, the record that points here")
    fp.add_argument("--did", default="", help="what the agent had done; required for a correction or an incident")
    fp.add_argument("--text", help="the words as said; read from stdin when omitted")
    fp.add_argument("--context", default="", help="the draft, the ticket, or other context")
    fp.add_argument("--date", type=dt.date.fromisoformat, help="YYYY-MM-DD; default today")
    fp.add_argument("--id", default="", help="the file name without .md; default <date>-<words of the name>")
    fp = fsub.add_parser("set", help="Set a disposition other than kept, with its reason.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_set, command="feedback set")
    fp.add_argument("id")
    fp.add_argument("disposition", choices=("pending", "one-off", "elsewhere", "declined"))
    fp.add_argument("--reason", default="")
    fp.add_argument("--to", action="append", default=[], metavar="KIND:NAME", help="for elsewhere: where the lesson lives, as brain:, plugin:, book: or doc:<path>; repeat for more")
    fp = fsub.add_parser("list", help="List feedback.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_list, command="feedback list")
    fp.add_argument("--pending", action="store_true", help="only feedback that is new or pending")

    p = command("new", cmd_new, "Write a record skeleton at status proposed: a rule, procedure, topic or routine, or in a team brain a policy, routine or topic.")
    p.add_argument("kind", choices=("rule", "procedure", "topic", "routine", "policy"))
    p.add_argument("id", help="the file name without .md: lowercase words joined by hyphens")
    for flag in ("name", "description", "scope", "trigger", "outputs", "procedure", "receiver", "owner"):
        p.add_argument(f"--{flag}")
    p.add_argument("--topic", action="append", default=[], help="a topic id; repeat for more")
    p.add_argument("--rule", action="append", default=[], help="a rule id a procedure follows; repeat for more")
    p.add_argument("--feedback", action="append", default=[], help="a feedback id to link both ways; repeat for more")
    p.add_argument("--body-file", type=Path, help="the record's body (its ## sections), or - for stdin")

    p = command("set-status", cmd_set_status, "Set a rule's or procedure's status, write the reason, and rewrite the index.")
    p.add_argument("ref", help="rules/<id> or procedures/<id>; in a team brain policies/<id>")
    p.add_argument("status", choices=("proposed", "active", "retired"))
    p.add_argument("--reason", default="", help="required for retired; added to the rule's Why")

    p = command("link", cmd_link, "Link a feedback to the record it became, both ways, and mark it kept.")
    p.add_argument("feedback")
    p.add_argument("target", help="rules/<id>, procedures/<id> or agent; in a team brain policies/<id>, routines/<id> or lanes")
    p = command("unlink", cmd_unlink, "Remove a link both ways. Feedback with no link left goes back to new.")
    p.add_argument("feedback")
    p.add_argument("target")

    command("index", cmd_index, "Rewrite the SKILL.md index from the active rules and procedures.")
    p = command("check", cmd_check, "Run every check. Exit 3 on any block finding.")
    p.add_argument("--all", action="store_true", help="check every brain under --project, or under this folder")
    p.add_argument("--staged", action="store_true", help="check what git has staged in the repository, not the working tree")
    p = command("trace", cmd_trace, "Show a record, the feedback behind it, and what links to it.")
    p.add_argument("ref", help="rules/<id>, procedures/<id>, feedback/<id>, or a bare id")
    command("status", cmd_status, "Counts, pending feedback and proposed records: what the dream starts from.")
    p = command("install", cmd_install, "Install the skill in a harness: a link to this checkout, or a copy.")
    p.add_argument("--harness", choices=tuple(harness.NAMES), help="the harness to install in; default the one running this command")
    p.add_argument("--user", action="store_true", help="install in the harness's skills folder for the user, not for this project")
    p.add_argument("--to", type=Path, help="install in this skills folder")
    p.add_argument("--copy", action="store_true", help="copy the skill, for a harness that cannot follow a link; feedback then goes to a clone")
    command("plugin", cmd_plugin, "Write the brain's plugin.json and its line in the repository's marketplace.")

    p = command("hooks", None, "Install the checks into git and the harness.")
    hsub = p.add_subparsers(title="hooks commands", metavar="<action>")
    hp = hsub.add_parser("install", help="Install the pre-commit hook, and the Claude Code Stop and SessionStart hooks.", parents=[common])
    hp.set_defaults(handler=cmd_hooks_install, command="hooks install")
    hp.add_argument("--repo", type=Path, help="the git repository's top folder; default the brain's repository")
    hp.add_argument("--harness", action="append", choices=tuple(harness.NAMES), default=[], help="a harness to install hooks for; repeat for more; default the one running this command")
    hp.add_argument("--dir", type=Path, help="the project folder where the agent's sessions start; default this repository")
    hp.add_argument("--claude", type=Path, help="the project folder where the agent's Claude Code sessions start")
    hp.add_argument("--codex", type=Path, help="the project folder where the agent's Codex sessions start")
    hp.add_argument("--cursor", type=Path, help="the project folder where the agent's Cursor sessions start")
    hp.add_argument("--no-git", action="store_true", help="skip the pre-commit hook")

    p = command("hook", None, "Run by an installed hook. Not for direct use.")
    hsub = p.add_subparsers(title="hook events", metavar="<event>")
    for event, handler in (("stop", cmd_hook_stop), ("start", cmd_hook_start)):
        hp = hsub.add_parser(event, parents=[common])
        hp.set_defaults(handler=handler, command=f"hook {event}")
        hp.add_argument("--host", choices=tuple(hooks.HOSTS), default="claude")

    p = command("team", None, "Join an agent brain to a team brain, or take it out. Run it in the team brain.")
    tsub = p.add_subparsers(title="team commands", metavar="<action>")
    tp = tsub.add_parser("add", help="Add an agent brain to the roster, and move its lane and routines into the team brain.", parents=[common])
    tp.set_defaults(handler=cmd_team_add, command="team add")
    tp.add_argument("path", type=Path, help="the agent brain's folder, in the team brain's repository")
    tp = tsub.add_parser("remove", help="Take an agent off the roster: its lane rows go back to its agent.md, and each routine it owns goes where --routine says.", parents=[common])
    tp.set_defaults(handler=cmd_team_remove, command="team remove")
    tp.add_argument("agent", help="the agent's name on the roster")
    tp.add_argument("--routine", action="append", default=[], metavar="ID=CHOICE", help="for each routine the agent owns: <id>=back, <id>=retire or <id>=<another agent>; repeat for more")

    command("version", cmd_version, "Print the version.")
    return parser


def cmd_init(args) -> Result:
    folder = (args.path or Path.cwd() / args.name).resolve()
    if args.team:
        if args.no_seed or args.display_name:
            raise BrainError(Finding("init.team_options", "--team", "A team brain seeds no procedures and has no display name.", "Leave out --no-seed and --display-name."), outcome="error")
        brain = scaffold.init_team(folder, args.name, git=not args.no_git)
    else:
        brain = scaffold.init(folder, args.name, git=not args.no_git, seed=not args.no_seed, display_name=args.display_name)
    lines = [f"  created {folder}", f"  the skill: {brain.skill_dir}"]
    if not args.no_git:
        repo = scaffold.git_root(folder)
        if repo:
            try:
                lines.append(f"  pre-commit hook: {hooks.install_git(repo)}")
            except BrainError as exc:
                lines.append(f"  pre-commit hook not installed: {exc.finding.message} {exc.finding.fix}")
    findings = checks.run(brain)
    lines.append(f"  {len(checks.blocking(findings))} TODO: placeholders and other block findings to fill in; run brain check.")
    return Result(
        "init", "ok", f"Brain {args.name} created.", lines=lines, value={"root": str(brain.root), "skill": str(brain.skill_dir)},
        next=(f"brain check --project {folder}", "fill the SKILL.md description until it passes, then run brain team add <agent folder>" if args.team else "fill agent.md and the SKILL.md description until it passes"),
    )


def cmd_feedback_add(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    words = args.text if args.text is not None else ("" if brain.is_team and sys.stdin.isatty() else sys.stdin.read())
    if not brain.is_team:
        missing = [flag for flag, value in (("--name", args.name), ("--from", args.source_role), ("--kind", args.kind)) if not value]
        if missing:
            raise BrainError(Finding("feedback.missing", " ".join(missing), f"{', '.join(missing)} is required.", "Pass it."), outcome="error")
    record = scaffold.add_feedback(
        brain, name=args.name, words=words, source_role=args.source_role, kind=args.kind, source=args.source, did=args.did, context=args.context, date=args.date, rid=args.id
    )
    return Result(
        "feedback add", "ok", f"Feedback {record.id} written. Decide it in this turn.", value={"id": record.id, "path": brain.rel(record.path)},
        next=(f"brain link {record.id} rules/<id>  or  brain new rule <id> --feedback {record.id}  or  brain feedback set {record.id} <disposition> --reason", "decide it, as Take a piece of feedback says"),
    )


def cmd_feedback_set(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    record = scaffold.set_disposition(brain, args.id, args.disposition, args.reason, args.to)
    return Result("feedback set", "ok", f"Feedback {record.id} is {args.disposition}.", value={"id": record.id}, next=("brain check", "confirm the brain is whole"))


def cmd_feedback_list(args) -> Result:
    brain = find(args.project)
    rows = []
    for fb in sorted(load(brain).by_folder["feedback"].values(), key=lambda r: r.id):
        disposition = fb.meta.get("disposition")
        if args.pending and disposition not in ("new", "pending"):
            continue
        rows.append({"id": fb.id, "disposition": disposition, "kind": fb.meta.get("kind"), "from": fb.meta.get("from"), "name": fb.meta.get("name"), "kept_in": fb.meta.get("kept_in") or []})
    lines = [f"  {r['id']}  {r['disposition']}  {r['kind']}  {r['from']}: {r['name']}" for r in rows]
    return Result("feedback list", "ok", f"{len(rows)} feedback.", lines=lines, value=rows)


def cmd_new(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    folder = {"rule": "rules", "procedure": "procedures", "topic": "topics", "routine": "routines", "policy": "policies"}[args.kind]
    values = {k: getattr(args, k) for k in ("name", "description", "scope", "trigger", "outputs", "procedure", "receiver", "owner")}
    body = None
    if args.body_file:
        body = sys.stdin.read() if str(args.body_file) == "-" else args.body_file.read_text()
    record = scaffold.new_record(brain, folder, args.id, values, feedback_ids=args.feedback, topics=args.topic, rules=args.rule, body=body)
    linked = f", linked to {', '.join(args.feedback)}" if args.feedback else ""
    return Result(
        "new", "ok", f"{record.ref} written{linked}.", value={"ref": record.ref, "path": brain.rel(record.path)},
        next=("brain check", f"replace each TODO: placeholder in {brain.rel(record.path)}"),
    )


def cmd_link(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    fb, target = scaffold.link(brain, args.feedback, args.target)
    active = target is not None and target.meta.get("status") == "active"
    return Result(
        "link", "ok", f"{fb.id} is kept in {args.target}.",
        next=("brain index" if active else "brain check", "the active record's index row may need its new words" if active else "confirm the brain is whole"),
    )


def cmd_set_status(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    record = scaffold.set_status(brain, args.ref, args.status, args.reason)
    return Result("set-status", "ok", f"{record.ref} is {args.status}; the index is rewritten.", next=("brain check", "confirm the brain is whole"))


def cmd_unlink(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    fb = scaffold.unlink(brain, args.feedback, args.target)
    return Result("unlink", "ok", f"{fb.id} no longer links {args.target}. It is {fb.meta['disposition']}.", next=("brain check", "confirm the brain is whole"))


def cmd_index(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    records = load(brain)
    if not brain.skill_file.is_file() or not index.write(brain, records):
        raise BrainError(Finding("skill.markers_missing", brain.rel(brain.skill_file), "SKILL.md has no index markers.", f"Add the lines {index.START} and {index.END}."))
    if brain.is_team:
        if records.lanes is None:
            team.write_lanes(brain, records, [])
        repo = team.repo_root(brain)
        index.write(brain, load(brain), repo)
        # Each member's SKILL.md copies its lanes from lanes.md, so a team index rewrites theirs too.
        names = team.reindex_members(brain, repo) if repo else []
        policies = sum(1 for r in records.by_folder["policies"].values() if r.meta.get("status") == "active")
        lines = [f"  agent SKILL.md rewritten: {', '.join(names)}"] if names else []
        return Result("index", "ok", f"SKILL.md index: {len(records.by_folder['agents'])} agents, {policies} policies.", lines=lines, next=("brain check --all", "confirm the team and its agents are whole"))
    rules = sum(1 for r in records.by_folder["rules"].values() if r.meta.get("status") == "active")
    procedures = sum(1 for r in records.by_folder["procedures"].values() if r.meta.get("status") == "active")
    return Result("index", "ok", f"SKILL.md index: {rules} rules, {procedures} procedures.", next=("brain check", "confirm the brain is whole"))


def cmd_check(args) -> Result:
    if args.staged:
        start = (args.project or Path.cwd()).resolve()
        repo = scaffold.git_root(start)
        if repo is None:
            raise BrainError(Finding("check.no_git", str(start), "--staged needs a git repository.", "Run it inside the repository, or leave out --staged."), outcome="error")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "-C", str(repo), "checkout-index", "-a", f"--prefix={tmp}/"], check=True)
            return check_brains(find_all(Path(tmp)), Path(tmp).resolve(), many=True, repo=Path(tmp).resolve())
    if args.all:
        root = (args.project or Path.cwd()).resolve()
        return check_brains(find_all(root), root, many=True)
    return check_brains([find(args.project)], None, many=False)


def check_brains(brains, root: Path | None, many: bool, repo: Path | None = None) -> Result:
    if not brains:
        return Result("check", "ok", f"No brains under {root}.", value=[])
    findings: list[Finding] = []
    for brain in brains:
        prefix = f"{brain.root.relative_to(root)}/" if many and brain.root != root else ""
        findings += [Finding(f.code, prefix + f.file, f.message, f.fix, f.level) for f in checks.run(brain, repo=repo)]
    blocks = sum(1 for f in findings if f.level == BLOCK)
    warns = len(findings) - blocks
    names = ", ".join(b.name for b in brains)
    if blocks:
        return Result("check", "failed", f"{blocks} block and {warns} warn findings in {names}.", findings, next=("brain check", "after you apply each Fix"))
    return Result("check", "ok", f"{names}: every check passed, {warns} warnings.", findings)


def cmd_trace(args) -> Result:
    brain = find(args.project)
    records = load(brain)
    ref = args.ref.removesuffix(".md")
    record = records.get(ref) if "/" in ref else next((r for r in records.all() if r.id == ref), None)
    if record is None:
        raise BrainError(Finding("record.not_found", args.ref, "No record has that id.", "Name it as rules/<id>, procedures/<id> or feedback/<id>."), outcome="error")
    lines = [f"  {record.ref}: {record.meta.get('name')} ({record.meta.get('status') or record.meta.get('disposition', '')})"]
    if record.kind.folder == "feedback":
        lines.append(f"    {record.meta.get('date')}, {record.meta.get('from')}, {record.meta.get('kind')}: {first_line(record.sections.get('Feedback', ''))}")
        for target in checks.as_list(record.meta.get("kept_in")):
            other = records.get(target)
            lines.append(f"    kept in {target}: {other.meta.get('name') if other else '(missing)'}")
    else:
        for fid in checks.as_list(record.meta.get("feedback")):
            fb = records.get(f"feedback/{fid}")
            if fb is None:
                lines.append(f"    feedback {fid}: (missing)")
                continue
            lines.append(f"    from feedback {fid}: {fb.meta.get('date')}, {fb.meta.get('from')}: \"{first_line(fb.sections.get('Feedback', ''))}\"")
        users = [p for p in (records.by_folder.get("procedures") or {}).values() if record.id in checks.as_list(p.meta.get("rules"))]
        for p in users:
            lines.append(f"    used by {p.ref}: {p.meta.get('name')}")
        for t in checks.as_list(record.meta.get("topics")):
            topic = records.get(f"topics/{t}")
            lines.append(f"    topic {t}: {topic.meta.get('name') if topic else '(missing)'}")
    return Result("trace", "ok", f"{record.ref}.", lines=lines, value={"ref": record.ref, "meta": record.meta})


def first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= 160 else line[:157] + "..."


def cmd_status(args) -> Result:
    brain = find(args.project)
    records = load(brain)
    counts = {}
    for folder, by_id in records.by_folder.items():
        key = "disposition" if folder == "feedback" else "status"
        tally: dict[str, int] = {}
        for r in by_id.values():
            label = str(r.meta.get(key) or "total")
            tally[label] = tally.get(label, 0) + 1
        counts[folder] = tally
    pending = sorted(f.id for f in records.by_folder["feedback"].values() if f.meta.get("disposition") in ("new", "pending"))
    proposed = sorted(r.ref for r in records.all() if r.kind.folder in ("rules", "procedures", "policies") and r.meta.get("status") == "proposed")
    lines = [f"  folder: {brain.root}", f"  reports: {brain.root / 'reports'}"]
    lines += [f"  {folder}: " + (", ".join(f"{n} {k}" for k, n in sorted(t.items())) or "none") for folder, t in counts.items()]
    lines += [f"  new or pending: feedback/{p}" for p in pending] + [f"  proposed: {p}" for p in proposed]
    value = {"root": str(brain.root), "reports": str(brain.root / "reports"), "counts": counts, "pending": pending, "proposed": proposed}
    return Result("status", "ok", f"Brain {brain.name}.", lines=lines, value=value)


def cmd_install(args) -> Result:
    brain = find(args.project)
    chosen = args.harness or (None if args.to else harness.detect())
    target, lines = plugin.install(brain, chosen, args.to, args.copy, user=args.user)
    kind = "a copy of" if args.copy else "a link to"
    if chosen:
        lines.insert(0, f"  harness: {harness.NAMES[chosen]}" + ("" if args.harness else " (the one running this command)"))
        rest = harness.others([chosen])
        lines.append("  other harnesses it supports: " + ", ".join(f"{harness.NAMES[h]} (brain install --harness {h})" for h in rest))
        lines.append("  Ask the person whether the brain should also run in any of them. Install there only on a yes.")
    return Result(
        "install", "ok", f"{target} is {kind} {brain.skill_dir}.", lines=lines,
        next=("start a fresh session and ask one question only the brain answers", "the answer must cite a rule or procedure by its title"),
    )


def cmd_plugin(args) -> Result:
    brain = find(args.project)
    require_writable(brain)
    lines = plugin.write(brain)
    return Result("plugin", "ok", f"Plugin {brain.name} written.", lines=lines, next=("brain check", "confirm the plugin matches the brain"))


def cmd_team_add(args) -> Result:
    crew = find(args.project)
    require_writable(crew)
    if not crew.is_team:
        raise BrainError(Finding("team.not_team", crew.rel(crew.root), f"{crew.name} is an agent brain.", "Run brain team add with --project set to the team brain."), outcome="error")
    lines = team.add(crew, args.path)
    return Result(
        "team add", "ok", f"{args.path} joined team {crew.name}.", lines=lines,
        next=("git add both brains and commit them in one commit", "the agent brain and the team brain change together"),
    )


def cmd_team_remove(args) -> Result:
    crew = find(args.project)
    require_writable(crew)
    if not crew.is_team:
        raise BrainError(Finding("team.not_team", crew.rel(crew.root), f"{crew.name} is an agent brain.", "Run brain team remove with --project set to the team brain."), outcome="error")
    choices = {}
    for pair in args.routine:
        rid, sep, choice = pair.partition("=")
        if not sep or not rid or not choice:
            raise BrainError(Finding("team.routine_choice", pair, "A routine choice is <id>=back, <id>=retire or <id>=<agent>.", "Pass --routine nightly-dream=back."), outcome="error")
        choices[rid] = choice
    lines = team.remove(crew, args.agent, choices)
    return Result(
        "team remove", "ok", f"{args.agent} left team {crew.name}.", lines=lines,
        next=("git add both brains and commit them in one commit", "the agent brain and the team brain change together"),
    )


def cmd_hooks_install(args) -> Result:
    brain = find(args.project)
    lines = []
    if not args.no_git:
        repo = (args.repo or scaffold.git_root(brain.root) or brain.root).resolve()
        lines.append(f"  pre-commit: {hooks.install_git(repo)}")
    targets = {host: getattr(args, host) for host in hooks.HOSTS if getattr(args, host)}
    folder = (args.dir or plugin.git_root_or_cwd()).resolve()
    detected = None
    if not targets and not args.harness:
        detected = harness.detect()
        if detected:
            targets[detected] = folder
    for host in args.harness:
        targets.setdefault(host, folder)
    for host, where in targets.items():
        lines.append(f"  {harness.NAMES[host]} hooks: {hooks.install_host(host, where.resolve(), brain.root)}")
    if not lines:
        raise BrainError(Finding("hooks.nothing", "hooks install", "Nothing to install: this harness is not one brain knows.", f"Pass --harness {'|'.join(harness.NAMES)}, or leave out --no-git."), outcome="error")
    rest = harness.others(list(targets))
    if detected:
        lines.insert(0, f"  harness: {harness.NAMES[detected]} (the one running this command)")
    if rest:
        lines.append("  other harnesses it supports: " + ", ".join(f"{harness.NAMES[h]} (brain hooks install --harness {h})" for h in rest))
        lines.append("  Ask the person whether the brain should also run in any of them. Install there only on a yes.")
    return Result("hooks install", "ok", "Hooks installed.", lines=lines)


def cmd_hook_stop(args) -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        out = hooks.stop(payload, find_all(resolve_project(args)), host=args.host)
    except Exception as exc:  # A broken hook must not trap the agent in its turn.
        print(f"brain hook stop: {exc}", file=sys.stderr)
        return None
    if out:
        print(json.dumps(out))
    return None


def cmd_hook_start(args) -> None:
    try:
        text = hooks.start(find_all(resolve_project(args)))
    except Exception as exc:  # A broken hook must not block the session start.
        print(f"brain hook start: {exc}", file=sys.stderr)
        return None
    if text:
        print(text)
    return None


def resolve_project(args) -> Path:
    return (args.project or Path.cwd()).resolve()


def cmd_version(args) -> Result:
    return Result("version", "ok", f"brain {__version__}, Python {sys.version.split()[0]}.")
