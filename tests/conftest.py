import re
import subprocess
from pathlib import Path

import pytest

from agent_brain import checks, scaffold
from agent_brain.brain import Brain, find

AGENT_VALUES = {
    '"TODO: one line, what the agent does and for whom."': "Drafts help-center articles for the editor.",
    '"TODO: what it produces, for whom, and where it stops short of the final action."': "Drafts help-center articles from product changes, for the editor's review.",
    '"TODO: what it owns and does itself"': "help-center article drafts",
    '"TODO: an action with an effect outside the brain that it must never take, such as publish, send, pay or delete"': "never publishes an article",
    '"TODO: the role whose feedback becomes lessons"': "editor",
    '"TODO: the role that settles conflicts and approves changes to the brain"': "editor",
    "TODO: how the agent sounds, as rules a reviewer can check against a draft.": "Plain, short sentences.",
}


def fill(brain: Brain) -> None:
    text = brain.agent_file.read_text()
    for old, new in AGENT_VALUES.items():
        text = text.replace(old, new)
    brain.agent_file.write_text(text)
    skill = brain.skill_file.read_text()
    skill = re.sub(r'description: ".*"', "description: Help-center writer's rules and procedures. Use when drafting or updating a help-center article.", skill)
    brain.skill_file.write_text(skill)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


@pytest.fixture
def brain(repo: Path) -> Brain:
    scaffold.init(repo / "brains" / "hcw", "help-center-writer")
    found = find(repo / "brains" / "hcw")
    fill(found)
    return found


def codes(brain: Brain) -> list[str]:
    return [f.code for f in checks.blocking(checks.run(brain))]


def add_correction(brain: Brain, name: str = "Check screenshots against the current release") -> str:
    record = scaffold.add_feedback(
        brain, name=name, words="This menu was removed two releases ago.", source_role="editor", kind="correction", source="review of draft 112", did="Used a removed menu."
    )
    return record.id


def finish_rule(brain: Brain, rid: str) -> None:
    path = brain.references / "rules" / f"{rid}.md"
    text = path.read_text()
    text = text.replace("TODO: the invariant only, no steps.", "Every named screen matches the current release.")
    text = text.replace("TODO: what went wrong, with the dates of its feedback.", "2026-11-17: a removed menu was described.")
    text = text.replace("TODO: when it fires, one do and one don't.", "Do compare with release notes. Don't trust old screenshots.")
    path.write_text(text)


def make_rule(brain: Brain, rid: str = "check-ui-against-current-release", feedback_id: str | None = None) -> str:
    feedback_id = feedback_id or add_correction(brain)
    if not (brain.references / "topics" / "accuracy.md").exists():
        scaffold.new_record(brain, "topics", "accuracy", {"name": "Accuracy", "description": "Facts match the product."})
        topic = brain.references / "topics" / "accuracy.md"
        topic.write_text(topic.read_text().replace("TODO: what belongs under this topic.", "Facts in articles."))
    scaffold.new_record(
        brain, "rules", rid,
        {"name": f"Rule {rid}", "description": "Compare each named screen with the release notes.", "scope": "Any article that names a screen."},
        feedback_ids=[feedback_id], topics=["accuracy"],
    )
    finish_rule(brain, rid)
    return feedback_id
