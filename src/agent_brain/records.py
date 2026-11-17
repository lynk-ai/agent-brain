import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .brain import Brain
from .output import Finding

ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SECTION_PATTERN = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Field:
    kind: str = "str"  # str | line | date | list | enum | any
    required: bool = True
    choices: tuple[str, ...] = ()
    fix: str = ""


@dataclass(frozen=True)
class Kind:
    name: str
    folder: str
    fields: dict[str, Field]
    sections: tuple[str, ...] = ()
    optional_sections: tuple[str, ...] = ()


STATUS = ("proposed", "active", "retired")

FEEDBACK = Kind(
    "feedback",
    "feedback",
    {
        "name": Field("line"),
        "date": Field("date"),
        "from": Field("line", fix="Name the person who gave it, by name or role."),
        "kind": Field("enum", choices=("correction", "preference", "approval", "incident", "praise")),
        "source": Field("line"),
        "what_agent_did": Field("str", required=False),
        "disposition": Field("enum", choices=("new", "pending", "kept", "one-off", "elsewhere", "declined")),
        "kept_in": Field("list", required=False),
    },
    sections=("Feedback",),
    optional_sections=("Context",),
)

RULE = Kind(
    "rule",
    "rules",
    {
        "name": Field("line", fix="Write the rule as one imperative sentence."),
        "description": Field("line"),
        "status": Field("enum", choices=STATUS),
        "strength": Field("enum", choices=("default", "hard")),
        "scope": Field("str"),
        "feedback": Field("list", fix="Link the feedback it came from: brain link <feedback> rules/<id>."),
        "topics": Field("list", fix="Label it with at least one topic from references/topics/."),
        "rests_on": Field("str", required=False),
        "checked": Field("date", required=False),
    },
    sections=("Rule", "Why", "How to apply"),
)

PROCEDURE = Kind(
    "procedure",
    "procedures",
    {
        "name": Field("line"),
        "description": Field("line"),
        "status": Field("enum", choices=STATUS),
        "trigger": Field("str"),
        "outputs": Field("str"),
        "rules": Field("list", required=False),
        "feedback": Field("list", required=False),
        "topics": Field("list", required=False),
    },
    sections=("Steps",),
    optional_sections=("Context",),
)

TOPIC = Kind(
    "topic",
    "topics",
    {"name": Field("line"), "description": Field("line")},
    sections=("Scope",),
)

ROUTINE = Kind(
    "routine",
    "routines",
    {
        "name": Field("line"),
        "description": Field("line"),
        "trigger": Field("str"),
        "owner": Field("line"),
        "procedure": Field("line", fix="Name a procedure id from references/procedures/."),
        "inputs": Field("list", required=False),
        "receiver": Field("line"),
        "when_nothing_new": Field("str"),
        "status": Field("enum", choices=("active", "paused")),
    },
)

AGENT = Kind(
    "agent",
    "",
    {
        "name": Field("line"),
        "display_name": Field("line", required=False),
        "description": Field("line"),
        "job": Field("str"),
        "lane": Field("list"),
        "anti_jobs": Field("list"),
        "needs_approval": Field("list", required=False),
        "data": Field("list", required=False),
        "tools": Field("list", required=False),
        "loads": Field("any", required=False),
        "decider": Field("line"),
        "roles": Field("any", required=False),
        "enforce_in_harness": Field("list", required=False),
    },
    sections=("Voice",),
)

KINDS = {k.folder: k for k in (FEEDBACK, RULE, PROCEDURE, TOPIC, ROUTINE)}
# Feedback.kept_in and the CLI name a record as <folder>/<id>; only these may hold feedback.
LINKABLE = ("rules", "procedures")


@dataclass
class Record:
    kind: Kind
    id: str
    path: Path
    meta: dict
    body: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.kind.folder}/{self.id}"


def split_front_matter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    meta = yaml.safe_load(text[4:end]) or {}
    return (meta if isinstance(meta, dict) else None), text[end + 5 :]


def parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(SECTION_PATTERN.finditer(body))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[match.end() : end].strip()
    return sections


def read_record(kind: Kind, path: Path) -> Record:
    meta, body = split_front_matter(path.read_text())
    if meta is None:
        raise ValueError("no YAML front matter between --- lines")
    return Record(kind, path.stem, path, meta, body, parse_sections(body))


def write_record(record: Record) -> None:
    front = yaml.safe_dump(record.meta, sort_keys=False, allow_unicode=True, width=1000, default_flow_style=None)
    body = record.body.lstrip("\n") if record.body.strip() else ""
    record.path.write_text(f"---\n{front}---\n{body}")


@dataclass
class Records:
    by_folder: dict[str, dict[str, Record]]
    agent: Record | None
    problems: list[Finding]

    def get(self, ref: str) -> Record | None:
        folder, _, rid = ref.partition("/")
        return self.by_folder.get(folder, {}).get(rid)

    def all(self) -> list[Record]:
        return [r for records in self.by_folder.values() for r in records.values()]


def load(brain: Brain) -> Records:
    problems: list[Finding] = []
    by_folder: dict[str, dict[str, Record]] = {folder: {} for folder in KINDS}
    if brain.references.is_dir():
        for entry in sorted(brain.references.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.name not in KINDS or not entry.is_dir():
                problems.append(
                    Finding("record.unknown_type", brain.rel(entry), "references/ holds only feedback, rules, procedures, topics and routines.", "Move or delete it.")
                )
                continue
            kind = KINDS[entry.name]
            for path in sorted(entry.iterdir()):
                if path.name.startswith("."):
                    continue
                if path.suffix != ".md" or not path.is_file():
                    problems.append(Finding("record.not_markdown", brain.rel(path), "A record is one .md file.", "Move or delete it."))
                    continue
                try:
                    by_folder[kind.folder][path.stem] = read_record(kind, path)
                except (ValueError, yaml.YAMLError) as exc:
                    problems.append(Finding("record.unreadable", brain.rel(path), f"Cannot read it: {exc}.", "Start the file with YAML front matter between --- lines."))
    agent = None
    if brain.agent_file.is_file():
        try:
            agent = read_record(AGENT, brain.agent_file)
        except (ValueError, yaml.YAMLError) as exc:
            problems.append(Finding("record.unreadable", brain.rel(brain.agent_file), f"Cannot read it: {exc}.", "Start the file with YAML front matter between --- lines."))
    return Records(by_folder, agent, problems)


def as_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def slug(text: str, words: int = 6) -> str:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(parts[:words]) or "record"
