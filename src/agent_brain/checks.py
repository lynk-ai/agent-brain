import datetime as dt
import re
from pathlib import Path

from . import index
from .brain import Brain
from .output import BLOCK, WARN, Finding
from .records import AGENT, ID_PATTERN, LINKABLE, Kind, Record, Records, as_date, load, split_front_matter

UNFINISHED = "TODO:"
SKILL_MAX_LINES = 500
SKILL_MAX_TOKENS = 5000
DESCRIPTION_MAX = 1024
CLOSED_WITH_REASON = ("pending", "one-off", "elsewhere", "declined")

SECRET_PATTERNS = [
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("an API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a credential", re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+]{12,}")),
]
PERSONAL_PATTERNS = [
    ("an email address", re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}\b")),
    ("a phone number", re.compile(r"(?<![\w+])\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}\b|\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")),
]
CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]){3}\d{1,7}\b|\b\d{13,19}\b")
# URLs and code spans hold repository pins such as git@github.com:org/repo, which are not contact details.
URL_OR_CODE = re.compile(r"`[^`]*`|\b[a-z][a-z0-9+.-]*://\S+|\bgit@[\w.-]+:\S+")
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def run(brain: Brain, records: Records | None = None, today: dt.date | None = None) -> list[Finding]:
    records = records or load(brain)
    today = today or dt.date.today()
    findings = list(records.problems)
    findings += check_shapes(brain, records)
    findings += check_links(brain, records)
    findings += check_feedback(brain, records, today)
    findings += check_rules(brain, records, today)
    findings += check_skill(brain, records)
    findings += check_text(brain)
    # YAML reads a bare off as false.
    levels = {code: "off" if level is False else str(level) for code, level in (brain.config.get("levels") or {}).items()}
    return [Finding(f.code, f.file, f.message, f.fix, levels.get(f.code, f.level)) for f in findings if levels.get(f.code) != "off"]


def check_shapes(brain: Brain, records: Records) -> list[Finding]:
    findings: list[Finding] = []
    if records.agent is None:
        if not brain.agent_file.exists():
            findings.append(Finding("agent.missing", brain.rel(brain.agent_file), "The brain has no agent record.", "Write agent.md in the skill folder."))
    else:
        findings += check_record(brain, records.agent, AGENT)
        if records.agent.meta.get("name") != brain.name:
            findings.append(Finding("agent.name", brain.rel(records.agent.path), f"agent.md's name is not {brain.name!r}.", f"Set name: {brain.name}."))
    for record in records.all():
        if not ID_PATTERN.match(record.id):
            findings.append(Finding("record.bad_id", brain.rel(record.path), "A file name is lowercase words joined by single hyphens.", "Rename the file and the links to it."))
        findings += check_record(brain, record, record.kind)
    for folder, by_id in records.by_folder.items():
        seen: dict[str, str] = {}
        for record in by_id.values():
            name = str(record.meta.get("name", "")).strip().lower()
            if name and name in seen:
                findings.append(Finding("record.duplicate_name", brain.rel(record.path), f"{folder}/{seen[name]} has the same name.", "Give each record its own name, or join the two."))
            seen.setdefault(name, record.id)
    return findings


def check_record(brain: Brain, record: Record, kind: Kind) -> list[Finding]:
    findings: list[Finding] = []
    where = brain.rel(record.path)
    for key in record.meta:
        if key not in kind.fields:
            findings.append(Finding("record.unknown_field", where, f"{kind.name} has no field {key!r}.", f"Use only: {', '.join(kind.fields)}."))
    for key, spec in kind.fields.items():
        value = record.meta.get(key)
        empty = value is None or value == "" or value == []
        if empty:
            if spec.required:
                findings.append(Finding("record.missing_field", where, f"{key} is required.", spec.fix or f"Fill in {key}."))
            continue
        problem = value_problem(value, spec)
        if problem:
            findings.append(Finding("record.bad_value", where, f"{key} {problem}.", spec.fix or f"Fix {key}."))
    for heading in kind.sections:
        if not record.sections.get(heading):
            findings.append(Finding("record.missing_section", where, f"The body has no '## {heading}' section with text.", f"Add '## {heading}' and its text."))
    return findings


def value_problem(value, spec) -> str:
    if spec.kind in ("str", "line"):
        if not isinstance(value, str):
            return "must be text"
        if spec.kind == "line" and "\n" in value.strip():
            return "must be one line"
    elif spec.kind == "date":
        if as_date(value) is None:
            return "must be a date, YYYY-MM-DD"
    elif spec.kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return "must be a list of ids"
    elif spec.kind == "enum":
        if value not in spec.choices:
            return f"must be one of {', '.join(spec.choices)}"
    return ""


def check_links(brain: Brain, records: Records) -> list[Finding]:
    findings: list[Finding] = []
    feedback = records.by_folder["feedback"]
    topics = records.by_folder["topics"]
    rules = records.by_folder["rules"]
    procedures = records.by_folder["procedures"]

    for fb in feedback.values():
        where = brain.rel(fb.path)
        for target_ref in as_list(fb.meta.get("kept_in")):
            if target_ref == "agent":
                continue
            folder = target_ref.partition("/")[0]
            target = records.get(target_ref)
            if folder not in LINKABLE or target is None:
                findings.append(Finding("link.unresolved", where, f"kept_in names {target_ref!r}, which does not exist.", "Name rules/<id>, procedures/<id> or agent."))
            elif fb.id not in as_list(target.meta.get("feedback")):
                findings.append(Finding("link.one_way", where, f"kept_in names {target_ref}, but {target_ref} does not list this feedback.", f"Run brain link {fb.id} {target_ref}."))

    for record in [*rules.values(), *procedures.values()]:
        where = brain.rel(record.path)
        for fid in as_list(record.meta.get("feedback")):
            fb = feedback.get(fid)
            if fb is None:
                findings.append(Finding("link.unresolved", where, f"feedback names {fid!r}, which does not exist.", "Name a file from references/feedback/ without .md."))
            elif record.ref not in as_list(fb.meta.get("kept_in")):
                findings.append(Finding("link.one_way", where, f"It lists feedback {fid}, but that feedback's kept_in does not name {record.ref}.", f"Run brain link {fid} {record.ref}."))
        for tid in as_list(record.meta.get("topics")):
            if tid not in topics:
                findings.append(Finding("link.unresolved", where, f"topics names {tid!r}, which does not exist.", f"Run brain new topic {tid}, or fix the id."))

    for procedure in procedures.values():
        for rid in as_list(procedure.meta.get("rules")):
            if rid not in rules:
                findings.append(Finding("link.unresolved", brain.rel(procedure.path), f"rules names {rid!r}, which does not exist.", "Name a file from references/rules/ without .md."))

    for routine in records.by_folder["routines"].values():
        pid = routine.meta.get("procedure")
        if isinstance(pid, str) and pid and pid not in procedures:
            findings.append(Finding("link.unresolved", brain.rel(routine.path), f"procedure names {pid!r}, which does not exist.", "Name a file from references/procedures/ without .md."))
    return findings


def check_feedback(brain: Brain, records: Records, today: dt.date) -> list[Finding]:
    findings: list[Finding] = []
    for fb in records.by_folder["feedback"].values():
        where = brain.rel(fb.path)
        disposition = fb.meta.get("disposition")
        kept_in = as_list(fb.meta.get("kept_in"))
        if disposition == "kept" and not kept_in:
            findings.append(Finding("feedback.kept_without_record", where, "It is kept, but kept_in names no record.", f"Run brain link {fb.id} rules/<id>, or brain new rule <id> --feedback {fb.id}."))
        if disposition != "kept" and kept_in:
            findings.append(Finding("feedback.linked_not_kept", where, f"It is {disposition}, but kept_in names records.", f"Run brain unlink {fb.id} <record> for each record, or link it with brain link."))
        if disposition == "new":
            findings.append(
                Finding("feedback.undecided", where, "Nobody decided it yet.", f"Decide it in this turn: brain link {fb.id} <record>, brain new rule <id> --feedback {fb.id}, or brain feedback set {fb.id} <disposition> --reason.")
            )
        if disposition in CLOSED_WITH_REASON and not fb.sections.get("Context"):
            findings.append(Finding("feedback.no_reason", where, f"It is {disposition}, with no reason.", f"Run brain feedback set {fb.id} {disposition} --reason \"<why>\"."))
        if fb.meta.get("kind") in ("correction", "incident") and not fb.meta.get("what_agent_did"):
            findings.append(Finding("record.missing_field", where, "what_agent_did is required for a correction or an incident.", "Write what the agent had done."))
        date = as_date(fb.meta.get("date"))
        if date and date > today:
            findings.append(Finding("feedback.future_date", where, f"Its date {date} is in the future.", "Set the date the feedback was given."))
        since = pending_since(fb.sections.get("Context", "")) or date
        if disposition == "pending" and since and (today - since).days > brain.config["pending_days"]:
            findings.append(
                Finding("feedback.pending_too_long", where, f"It is pending for {(today - since).days} days.", "Decide it: brain link, or brain feedback set <id> <disposition> --reason.", WARN)
            )
    return findings


def check_rules(brain: Brain, records: Records, today: dt.date) -> list[Finding]:
    findings: list[Finding] = []
    for rule in records.by_folder["rules"].values():
        if rule.meta.get("status") != "active":
            continue
        checked = as_date(rule.meta.get("checked"))
        if rule.meta.get("rests_on") and checked is None:
            findings.append(Finding("rule.unchecked", brain.rel(rule.path), "It rests on a source, with no checked date.", "Check it against the source and set checked: YYYY-MM-DD.", WARN))
        elif checked and (today - checked).days > brain.config["checked_days"]:
            findings.append(Finding("rule.stale", brain.rel(rule.path), f"Last checked {(today - checked).days} days ago.", "Check it against rests_on and update checked.", WARN))
    return findings


def check_skill(brain: Brain, records: Records) -> list[Finding]:
    findings: list[Finding] = []
    where = brain.rel(brain.skill_file)
    if not brain.skill_dir.is_dir():
        return [Finding("skill.missing", brain.rel(brain.skill_dir), f"There is no skill folder named {brain.name}.", "The skill folder's name must equal name in brain.yaml.")]
    if not brain.skill_file.is_file():
        return [Finding("skill.missing", where, "The skill has no SKILL.md.", "Write SKILL.md with name, description and the index markers.")]
    text = brain.skill_file.read_text()
    meta, _ = split_front_matter(text)
    meta = meta or {}
    if meta.get("name") != brain.name:
        findings.append(Finding("skill.name", where, f"SKILL.md's name is not {brain.name!r}, its folder's name.", f"Set name: {brain.name}."))
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        findings.append(Finding("skill.description", where, "SKILL.md has no description.", "Write what the agent does, then when to use it, in its users' words."))
    elif len(description) > DESCRIPTION_MAX:
        findings.append(Finding("skill.description", where, f"The description has {len(description)} characters, over {DESCRIPTION_MAX}.", "Shorten it. Put the main use first."))
    lines = text.count("\n") + 1
    if lines > SKILL_MAX_LINES:
        findings.append(Finding("skill.too_long", where, f"SKILL.md has {lines} lines, over {SKILL_MAX_LINES}.", "Move the least used topics behind one link each."))
    tokens = len(text) // 4
    if tokens > SKILL_MAX_TOKENS:
        findings.append(Finding("skill.size", where, f"SKILL.md is about {tokens} tokens, over {SKILL_MAX_TOKENS}.", "Shorten rows, or move the least used topics behind one link each.", WARN))
    if "references/feedback/" in text:
        findings.append(Finding("skill.lists_feedback", where, "SKILL.md links feedback. Feedback is evidence, not an instruction.", "Remove the link. Rules and procedures link their feedback."))
    from . import plugin

    findings += plugin.drift(brain)
    if "take-feedback" not in records.by_folder["procedures"]:
        findings.append(Finding("procedure.no_take_feedback", where, "The brain has no take-feedback procedure.", "Write procedures/take-feedback.md, so every correction has one path.", WARN))
    current = index.current(text)
    if current is None:
        findings.append(Finding("skill.markers_missing", where, "SKILL.md has no index markers.", f"Add the lines {index.START} and {index.END}, then run brain index."))
    elif current != index.render(records):
        findings.append(Finding("skill.index_stale", where, "The index does not match the active rules and procedures.", "Run brain index."))
    return findings


def check_text(brain: Brain) -> list[Finding]:
    findings: list[Finding] = []
    if not brain.skill_dir.is_dir():
        return findings
    harness_names = [n for n in brain.config.get("harness_names") or [] if isinstance(n, str) and n]
    for path in sorted(brain.skill_dir.rglob("*.md")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            where = f"{brain.rel(path)}:{number}"
            for target in LINK_PATTERN.findall(line):
                if not resolves(path, target):
                    findings.append(Finding("link.broken", where, f"The link {target} does not resolve.", "Point it at a file inside the skill, or remove it."))
            if UNFINISHED in line:
                findings.append(Finding("record.unfinished", where, f"It still has a {UNFINISHED} placeholder.", "Replace the placeholder with the real text."))
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding("data.secret", where, f"It looks like {label}.", "Remove it, and rotate it if it was real."))
            prose = URL_OR_CODE.sub(" ", line)
            for label, pattern in PERSONAL_PATTERNS:
                if pattern.search(prose):
                    findings.append(Finding("data.personal", where, f"It looks like {label}.", "Replace it with a marker such as [email removed]."))
            if any(luhn(m.group()) for m in CARD_PATTERN.finditer(line)):
                findings.append(Finding("data.personal", where, "It looks like a card number.", "Replace it with [card removed]."))
            for name in harness_names:
                if name in line:
                    findings.append(Finding("core.harness_name", where, f"The core names {name!r}, a harness detail.", "Keep harness details in harness/<harness>/, outside the skill."))
    return findings


def pending_since(context: str) -> dt.date | None:
    # brain feedback set writes "<date>, pending: <reason>"; the last such line is when it was set to pending.
    dates = re.findall(r"^(\d{4}-\d{2}-\d{2}), pending:", context, re.MULTILINE)
    return as_date(dates[-1]) if dates else None


def resolves(source: Path, target: str) -> bool:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
        return True
    return (source.parent / target.split("#")[0]).exists()


def scan_sensitive(text: str) -> list[str]:
    labels = [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]
    prose = URL_OR_CODE.sub(" ", text)
    labels += [label for label, pattern in PERSONAL_PATTERNS if pattern.search(prose)]
    if any(luhn(m.group()) for m in CARD_PATTERN.finditer(text)):
        labels.append("a card number")
    return labels


def luhn(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def as_list(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def blocking(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == BLOCK]
