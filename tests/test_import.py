import datetime as dt
from pathlib import Path

from agent_brain import checks
from agent_brain.importer import import_darkmatter


def doc(path: Path, meta: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{meta.strip()}\n---\n{body}")


def darkmatter_brain(root: Path) -> Path:
    src = root / "lynk-x-playbook"
    (src / "darkmatter.yaml").parent.mkdir(parents=True)
    (src / "darkmatter.yaml").write_text("name: x\n")
    (src / "schema").mkdir()
    doc(src / "plugins/lynk-x-playbook/skills/lynk-x-playbook/SKILL.md", 'name: lynk-x-playbook\ndescription: "How Zoe writes X posts for Lynk."',
        "# Lynk X playbook\n\nLynk-only rules for Zoe.\n\n## Active rules\n\n<!-- darkmatter:inline -->\n[x](../idx.md)\n")
    doc(src / "wiki/topics/voice.md", "name: Voice\ndescription: How posts sound.\nfeedback: [short-posts]", "## Scope\n\nTone.\n")
    doc(src / "wiki/feedback/short-posts.md",
        "name: Keep posts short\ndescription: d\ndate: 2026-10-01\nkind: correction\nsource: review\nwhat_i_did: Wrote 400 words.\ntopics: [voice]\nrules: [keep-posts-short]\none_off: false",
        "## Feedback\n\nToo long.\n\n## Context\n\nSee @wiki/rules/keep-posts-short.md and @brains/library/wiki/chapters/x.md.\n")
    doc(src / "wiki/feedback/typo.md", "name: A typo\ndescription: one slip\ndate: 2026-10-02\nkind: preference\nsource: chat\none_off: true", "## Feedback\n\nTypo.\n")
    doc(src / "wiki/rules/keep-posts-short.md",
        "name: Keep each post under 280 characters\ndescription: Count before posting.\nstatus: active\ntopics: [voice]\nfeedback: [short-posts]\nscope: Every post.",
        "## Rule\n\nUnder 280.\n\n## Why\n\nToo long on 2026-10-01.\n\n## How to apply\n\nDo count. Don't pad.\n")
    doc(src / "wiki/procedures/run-the-dream.md",
        "name: Run the team dream\ndescription: d\ntrigger: nightly\noutputs: a report\nrules: [keep-posts-short]\nfeedback: []", "## Steps\n\n1. Run.\n")
    doc(root / "agents/zoe.md", "name: Zoe\ndescription: Writes X posts\njob: Writes X posts for Lynk\nanti_jobs: [never posts]\nowns: [X]\nexternal_skills: [x-book]\nbrains: [lynk-x-playbook, lynk-team-roster]",
        "## Voice\n\nShort and dry.\n")
    return src


def test_import_moves_records_links_and_reports_gaps(tmp_path):
    src = darkmatter_brain(tmp_path)
    brain, report = import_darkmatter(src, tmp_path / "out" / "lynk-x-playbook", agent_doc=tmp_path / "agents/zoe.md", renames={"run-the-dream": "run-the-team-dream"})
    assert report.counts == {"feedback": 2, "rules": 1, "procedures": 8, "topics": 3}
    text = brain.skill_file.read_text()
    assert "You are Zoe." in text and "How Zoe writes X posts" in text and "Keep each post under 280 characters" in text
    fb = (brain.references / "feedback/short-posts.md").read_text()
    assert "kept_in: [rules/keep-posts-short]" in fb and "references/rules/keep-posts-short.md" in fb
    assert any("@brains/library/wiki/chapters/x.md" in g for g in report.gaps)
    assert "disposition: one-off" in (brain.references / "feedback/typo.md").read_text()
    assert (brain.references / "procedures/run-the-team-dream.md").exists() and (brain.references / "procedures/run-the-dream.md").exists()
    agent = (brain.agent_file).read_text()
    assert "display_name: Zoe" in agent and "lynk-team-roster" in agent and "Short and dry." in agent
    assert any("feedback/short-posts: description, topics" in d for d in report.dropped)
    assert checks.blocking(checks.run(brain)) == []


def test_sibling_paths_follow_the_new_layout(tmp_path):
    src = darkmatter_brain(tmp_path)
    rule = src / "wiki/rules/keep-posts-short.md"
    rule.write_text(rule.read_text().replace("Do count.", "Do count, as @brains/lynk-email-playbook/wiki/rules/a-rule.md says."))
    brain, report = import_darkmatter(src, tmp_path / "out" / "x", agent_doc=tmp_path / "agents/zoe.md", siblings=["lynk-*-playbook"])
    assert "@brains/lynk-email-playbook/lynk-email-playbook/references/rules/a-rule.md" in (brain.references / "rules/keep-posts-short.md").read_text()
    assert not any("lynk-email-playbook" in g for g in report.gaps)
