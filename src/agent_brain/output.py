import json
from dataclasses import asdict, dataclass, field

BLOCK = "block"
WARN = "warn"

EXIT = {"ok": 0, "failed": 3, "refused": 3, "error": 2}


@dataclass(frozen=True)
class Finding:
    # Codes are stable: hooks, tests and agents match on them.
    code: str
    file: str
    message: str
    fix: str
    level: str = BLOCK


@dataclass
class Result:
    command: str
    outcome: str
    headline: str
    findings: list[Finding] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    value: object = None
    next: tuple[str, str] | None = None

    @property
    def exit_code(self) -> int:
        return EXIT[self.outcome]


class BrainError(Exception):
    def __init__(self, finding: Finding, outcome: str = "refused", next: tuple[str, str] | None = None):
        super().__init__(finding.message)
        self.finding = finding
        self.outcome = outcome
        self.next = next


def render_text(result: Result) -> str:
    out = [f"{result.outcome}: {result.headline}"]
    out.extend(result.lines)
    for f in result.findings:
        out.append(f"  {f.level} {f.file}: {f.message} Fix: {f.fix} [{f.code}]")
    if result.next:
        command, why = result.next
        out.append(f"Next: {command}  ({why})")
    return "\n".join(out)


def render_json(result: Result) -> str:
    data = {
        "command": result.command,
        "outcome": result.outcome,
        "ok": result.outcome == "ok",
        "headline": result.headline,
        "findings": [asdict(f) for f in result.findings],
        "value": result.value,
        "next": {"command": result.next[0], "why": result.next[1]} if result.next else None,
    }
    return json.dumps(data, indent=2, default=str)
