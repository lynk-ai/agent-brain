import argparse
import re
import subprocess
import sys
from pathlib import Path

from agent_brain.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def commands() -> set[str]:
    found = set()

    def walk(parser, prefix):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    # hook stop and hook start run from the harness hooks; brain hooks install documents them.
                    if name != "hook":
                        found.add(" ".join([*prefix, name]))
                        walk(sub, [*prefix, name])

    walk(build_parser(), [])
    return found - {"feedback", "hooks"}


def test_findings_md_matches_the_code():
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "findings_doc.py"), "--check"])
    assert done.returncode == 0, "docs/findings.md differs from the code: run python tools/findings_doc.py"


def test_every_command_has_a_section_in_the_reference():
    headings = " ".join(re.findall(r"^### (.+)$", (ROOT / "docs" / "reference.md").read_text(), re.MULTILINE))
    missing = sorted(c for c in commands() if f"brain {c}" not in headings)
    assert missing == [], f"docs/reference.md has no ### heading for: {missing}"


def test_every_flag_is_in_the_reference():
    reference = (ROOT / "docs" / "reference.md").read_text()
    flags = set()

    def walk(parser):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    if name != "hook":
                        walk(sub)
            flags.update(f for f in action.option_strings if f.startswith("--") and f not in ("--help",))

    walk(build_parser())
    missing = sorted(f for f in flags if f not in reference)
    assert missing == [], f"docs/reference.md never names: {missing}"
