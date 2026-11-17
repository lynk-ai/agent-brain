import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import __version__, checks, hooks, index, scaffold
from .brain import find, find_all
from .output import BLOCK, BrainError, Finding, Result, render_json, render_text
from .records import KINDS, load

DESCRIPTION = "Keep one agent's brain, a skill in git, whole: feedback, rules, procedures and topics, linked and checked."


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 0
    try:
        result = args.handler(args)
    except BrainError as exc:
        result = Result(" ".join(sys.argv[1:2]) or "brain", exc.outcome, exc.finding.message, [exc.finding], next=exc.next)
    except KeyboardInterrupt:
        return 130
    if result is None:
        return 0
    print(render_json(result) if args.json else render_text(result))
    return result.exit_code


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=argparse.SUPPRESS, help="the brain's folder, its installed skill folder, or a folder inside it")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print one JSON object")

    parser = argparse.ArgumentParser(prog="brain", description=DESCRIPTION, parents=[common])
    parser.set_defaults(project=None, json=False)
    sub = parser.add_subparsers(title="commands", metavar="<command>")

    def command(name, handler, help_text, **kwargs):
        p = sub.add_parser(name, help=help_text, description=help_text, parents=[common], **kwargs)
        p.set_defaults(handler=handler)
        return p

    p = command("init", cmd_init, "Create a brain: brain.yaml, the skill folder, agent.md and the seeded procedures.")
    p.add_argument("name", help="the agent's name: lowercase words joined by hyphens")
    p.add_argument("--path", type=Path, help="the folder to create; default ./<name>")
    p.add_argument("--no-git", action="store_true", help="do not run git init or install the pre-commit hook")

    p = command("feedback", None, "Add, decide and list feedback.")
    fsub = p.add_subparsers(title="feedback commands", metavar="<action>")
    fp = fsub.add_parser("add", help="Write a feedback record, undecided, in the same turn.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_add)
    fp.add_argument("--name", required=True, help="the feedback in one sentence")
    fp.add_argument("--from", dest="source_role", required=True, help="who gave it, by role as agent.md lists teachers")
    fp.add_argument("--kind", required=True, choices=KINDS["feedback"].fields["kind"].choices)
    fp.add_argument("--source", required=True, help="where it was said")
    fp.add_argument("--did", default="", help="what the agent had done; required for a correction or an incident")
    fp.add_argument("--text", help="the words as said; read from stdin when omitted")
    fp.add_argument("--context", default="", help="the draft, the ticket, or other context")
    fp.add_argument("--date", type=dt.date.fromisoformat, help="YYYY-MM-DD; default today")
    fp = fsub.add_parser("set", help="Set a disposition other than kept, with its reason.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_set)
    fp.add_argument("id")
    fp.add_argument("disposition", choices=("pending", "one-off", "elsewhere", "declined"))
    fp.add_argument("--reason", default="")
    fp = fsub.add_parser("list", help="List feedback.", parents=[common])
    fp.set_defaults(handler=cmd_feedback_list)
    fp.add_argument("--pending", action="store_true", help="only feedback that is new or pending")

    p = command("new", cmd_new, "Write a rule, procedure, topic or routine skeleton at status proposed.")
    p.add_argument("kind", choices=("rule", "procedure", "topic", "routine"))
    p.add_argument("id", help="the file name without .md: lowercase words joined by hyphens")
    for flag in ("name", "description", "scope", "topic", "trigger", "outputs", "procedure", "receiver"):
        p.add_argument(f"--{flag}")
    p.add_argument("--feedback", default="", help="a feedback id to link both ways")

    p = command("link", cmd_link, "Link a feedback to the record it became, both ways, and mark it kept.")
    p.add_argument("feedback")
    p.add_argument("target", help="rules/<id>, procedures/<id> or agent")
    p = command("unlink", cmd_unlink, "Remove a link both ways. Feedback with no link left goes back to new.")
    p.add_argument("feedback")
    p.add_argument("target")

    command("index", cmd_index, "Rewrite the SKILL.md index from the active rules and procedures.")
    p = command("check", cmd_check, "Run every check. Exit 3 on any block finding.")
    p.add_argument("--all", action="store_true", help="check every brain under --project, or under this folder")
    p = command("trace", cmd_trace, "Show a record, the feedback behind it, and what links to it.")
    p.add_argument("ref", help="rules/<id>, procedures/<id>, feedback/<id>, or a bare id")
    command("status", cmd_status, "Counts, pending feedback and proposed records: what the dream starts from.")
    p = command("install", cmd_install, "Link the skill folder into a harness's skills folder.")
    p.add_argument("--to", type=Path, required=True, help="the skills folder, such as ~/.agents/skills")

    p = command("hooks", None, "Install the checks into git and Claude Code.")
    hsub = p.add_subparsers(title="hooks commands", metavar="<action>")
    hp = hsub.add_parser("install", help="Install the pre-commit hook, and the Claude Code Stop and SessionStart hooks.", parents=[common])
    hp.set_defaults(handler=cmd_hooks_install)
    hp.add_argument("--repo", type=Path, help="the git repository's top folder; default the brain's repository")
    hp.add_argument("--claude", type=Path, help="the project folder where the agent's Claude Code sessions start")
    hp.add_argument("--no-git", action="store_true", help="skip the pre-commit hook")

    p = command("hook", None, "Run by an installed hook. Not for direct use.")
    hsub = p.add_subparsers(title="hook events", metavar="<event>")
    for event, handler in (("stop", cmd_hook_stop), ("start", cmd_hook_start)):
        hp = hsub.add_parser(event, parents=[common])
        hp.set_defaults(handler=handler)

    command("version", cmd_version, "Print the version.")
    return parser


def cmd_init(args) -> Result:
    folder = (args.path or Path.cwd() / args.name).resolve()
    brain = scaffold.init(folder, args.name, git=not args.no_git)
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
        next=(f"brain check --project {folder}", "fill agent.md and the SKILL.md description until it passes"),
    )


def cmd_feedback_add(args) -> Result:
    brain = find(args.project)
    words = args.text if args.text is not None else sys.stdin.read()
    record = scaffold.add_feedback(
        brain, name=args.name, words=words, source_role=args.source_role, kind=args.kind, source=args.source, did=args.did, context=args.context, date=args.date
    )
    return Result(
        "feedback add", "ok", f"Feedback {record.id} written. Decide it in this turn.", value={"id": record.id, "path": brain.rel(record.path)},
        next=(f"brain link {record.id} rules/<id>  or  brain new rule <id> --feedback {record.id}  or  brain feedback set {record.id} <disposition> --reason", "decide it, as Take a piece of feedback says"),
    )


def cmd_feedback_set(args) -> Result:
    brain = find(args.project)
    record = scaffold.set_disposition(brain, args.id, args.disposition, args.reason)
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
    folder = {"rule": "rules", "procedure": "procedures", "topic": "topics", "routine": "routines"}[args.kind]
    values = {k: getattr(args, k) for k in ("name", "description", "scope", "topic", "trigger", "outputs", "procedure", "receiver")}
    record = scaffold.new_record(brain, folder, args.id, values, feedback_id=args.feedback)
    linked = f", linked to {args.feedback}" if args.feedback else ""
    return Result(
        "new", "ok", f"{record.ref} written{linked}.", value={"ref": record.ref, "path": brain.rel(record.path)},
        next=("brain check", f"replace each TODO: placeholder in {brain.rel(record.path)}"),
    )


def cmd_link(args) -> Result:
    brain = find(args.project)
    fb, target = scaffold.link(brain, args.feedback, args.target)
    active = target is not None and target.meta.get("status") == "active"
    return Result(
        "link", "ok", f"{fb.id} is kept in {args.target}.",
        next=("brain index" if active else "brain check", "the active record's index row may need its new words" if active else "confirm the brain is whole"),
    )


def cmd_unlink(args) -> Result:
    brain = find(args.project)
    fb = scaffold.unlink(brain, args.feedback, args.target)
    return Result("unlink", "ok", f"{fb.id} no longer links {args.target}. It is {fb.meta['disposition']}.", next=("brain check", "confirm the brain is whole"))


def cmd_index(args) -> Result:
    brain = find(args.project)
    records = load(brain)
    if not brain.skill_file.is_file() or not index.write(brain, records):
        raise BrainError(Finding("skill.markers_missing", brain.rel(brain.skill_file), "SKILL.md has no index markers.", f"Add the lines {index.START} and {index.END}."))
    rules = sum(1 for r in records.by_folder["rules"].values() if r.meta.get("status") == "active")
    procedures = sum(1 for r in records.by_folder["procedures"].values() if r.meta.get("status") == "active")
    return Result("index", "ok", f"SKILL.md index: {rules} rules, {procedures} procedures.", next=("brain check", "confirm the brain is whole"))


def cmd_check(args) -> Result:
    if args.all:
        root = (args.project or Path.cwd()).resolve()
        brains = find_all(root)
        if not brains:
            return Result("check", "ok", f"No brains under {root}.", value=[])
    else:
        brains = [find(args.project)]
    findings: list[Finding] = []
    for brain in brains:
        prefix = "" if not args.all else f"{brain.root.relative_to(root)}/" if brain.root != root else ""
        findings += [Finding(f.code, prefix + f.file, f.message, f.fix, f.level) for f in checks.run(brain)]
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
        users = [p for p in records.by_folder["procedures"].values() if record.id in checks.as_list(p.meta.get("rules"))]
        for p in users:
            lines.append(f"    used by {p.ref}: {p.meta.get('name')}")
        for t in checks.as_list(record.meta.get("topics")):
            lines.append(f"    topic {t}")
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
    proposed = sorted(r.ref for r in records.all() if r.kind.folder in ("rules", "procedures") and r.meta.get("status") == "proposed")
    lines = [f"  folder: {brain.root}", f"  reports: {brain.root / 'reports'}"]
    lines += [f"  {folder}: " + (", ".join(f"{n} {k}" for k, n in sorted(t.items())) or "none") for folder, t in counts.items()]
    lines += [f"  new or pending: feedback/{p}" for p in pending] + [f"  proposed: {p}" for p in proposed]
    value = {"root": str(brain.root), "reports": str(brain.root / "reports"), "counts": counts, "pending": pending, "proposed": proposed}
    return Result("status", "ok", f"Brain {brain.name}.", lines=lines, value=value)


def cmd_install(args) -> Result:
    brain = find(args.project)
    target = scaffold.install(brain, args.to)
    return Result(
        "install", "ok", f"{target} links to {brain.skill_dir}.",
        next=("start a fresh session and ask one question only the brain answers", "the answer must cite a rule or procedure by its title"),
    )


def cmd_hooks_install(args) -> Result:
    brain = find(args.project)
    lines = []
    if not args.no_git:
        repo = (args.repo or scaffold.git_root(brain.root) or brain.root).resolve()
        lines.append(f"  pre-commit: {hooks.install_git(repo)}")
    if args.claude:
        lines.append(f"  Claude Code: {hooks.install_claude(args.claude.resolve(), brain.root)}")
    if not lines:
        raise BrainError(Finding("hooks.nothing", "hooks install", "Nothing to install.", "Pass --claude <folder>, or leave out --no-git."), outcome="error")
    return Result("hooks install", "ok", "Hooks installed.", lines=lines)


def cmd_hook_stop(args) -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        out = hooks.stop(payload, find_all(resolve_project(args)))
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
