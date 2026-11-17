import datetime as dt

import yaml

from agent_brain import checks, index, scaffold
from agent_brain.brain import find
from agent_brain.records import load, read_record, write_record, RULE, FEEDBACK

from conftest import add_correction, codes, make_rule


def set_meta(path, **changes):
    kind = RULE if "/rules/" in str(path) else FEEDBACK
    record = read_record(kind, path)
    record.meta.update(changes)
    write_record(record)


def test_a_new_brain_blocks_until_its_placeholders_are_filled(repo):
    brain = scaffold.init(repo / "b", "writer")
    assert set(codes(brain)) == {"record.unfinished"}


def test_a_filled_brain_passes(brain):
    assert codes(brain) == []


def test_new_feedback_blocks_until_it_is_decided(brain):
    fid = add_correction(brain)
    assert codes(brain) == ["feedback.undecided"]
    scaffold.set_disposition(brain, fid, "one-off", "a single slip")
    assert codes(brain) == []


def test_a_new_rule_links_its_feedback_both_ways(brain):
    fid = make_rule(brain)
    records = load(brain)
    assert records.get(f"feedback/{fid}").meta["kept_in"] == ["rules/check-ui-against-current-release"]
    assert records.get(f"feedback/{fid}").meta["disposition"] == "kept"
    assert records.get("rules/check-ui-against-current-release").meta["feedback"] == [fid]
    assert codes(brain) == []


def test_a_one_way_link_blocks(brain):
    fid = make_rule(brain)
    set_meta(brain.references / "feedback" / f"{fid}.md", kept_in=[])
    found = codes(brain)
    assert "link.one_way" in found
    assert "feedback.kept_without_record" in found


def test_a_rule_without_feedback_blocks(brain):
    fid = make_rule(brain)
    scaffold.unlink(brain, fid, "rules/check-ui-against-current-release")
    found = codes(brain)
    assert "record.missing_field" in found
    assert "feedback.undecided" in found


def test_a_closed_feedback_needs_a_reason(brain):
    fid = add_correction(brain)
    set_meta(brain.references / "feedback" / f"{fid}.md", disposition="declined")
    assert "feedback.no_reason" in codes(brain)


def test_an_activated_rule_makes_the_index_stale_until_reindexed(brain):
    make_rule(brain)
    set_meta(brain.references / "rules" / "check-ui-against-current-release.md", status="active")
    assert codes(brain) == ["skill.index_stale"]
    index.write(brain, load(brain))
    assert codes(brain) == []
    assert "rules/check-ui-against-current-release" in brain.skill_file.read_text()


def test_a_retired_rule_leaves_the_index(brain):
    make_rule(brain)
    rule = brain.references / "rules" / "check-ui-against-current-release.md"
    set_meta(rule, status="active")
    index.write(brain, load(brain))
    set_meta(rule, status="retired")
    assert codes(brain) == ["skill.index_stale"]
    index.write(brain, load(brain))
    assert "check-ui-against-current-release" not in brain.skill_file.read_text()


def test_a_hand_edited_index_blocks(brain):
    text = brain.skill_file.read_text().replace("## Rules", "## Rules\n\n- **Something I made up.**")
    brain.skill_file.write_text(text)
    assert codes(brain) == ["skill.index_stale"]


def test_skill_md_may_not_link_feedback(brain):
    brain.skill_file.write_text(brain.skill_file.read_text() + "\nSee references/feedback/x.md\n")
    assert "skill.lists_feedback" in codes(brain)


def test_unknown_fields_and_missing_sections_block(brain):
    make_rule(brain)
    path = brain.references / "rules" / "check-ui-against-current-release.md"
    set_meta(path, owner="me")
    path.write_text(path.read_text().replace("## Why", "## Reason"))
    found = codes(brain)
    assert "record.unknown_field" in found
    assert "record.missing_section" in found


def test_secrets_contact_details_and_harness_names_block(brain):
    procedure = brain.references / "procedures" / "hand-off.md"
    procedure.write_text(procedure.read_text() + "\nMail bob@example.com or call +1 415 555 0100. Key AKIAABCDEFGHIJKLMNOP. See .claude/skills.\n")
    found = codes(brain)
    assert found.count("data.personal") == 2
    assert "data.secret" in found
    assert "core.harness_name" in found


def test_dates_are_not_phone_or_card_numbers(brain):
    procedure = brain.references / "procedures" / "hand-off.md"
    procedure.write_text(procedure.read_text() + "\nOn 2026-03-04 2026-03-05 and 2026-11-17.\n")
    assert codes(brain) == []


def test_pending_too_long_and_stale_rules_warn(brain):
    record = scaffold.add_feedback(brain, name="Maybe shorter titles", words="Shorter?", source_role="editor", kind="preference", source="chat")
    scaffold.set_disposition(brain, record.id, "pending", "wait for a second time")
    make_rule(brain)
    set_meta(brain.references / "rules" / "check-ui-against-current-release.md", status="active", rests_on="release notes", checked=dt.date(2026, 1, 1))
    index.write(brain, load(brain))
    findings = checks.run(brain, today=dt.date.today() + dt.timedelta(days=30))
    warns = {f.code for f in findings if f.level == "warn"}
    assert warns == {"feedback.pending_too_long", "rule.stale"}
    assert checks.blocking(findings) == []


def test_find_follows_an_installed_symlink(brain, tmp_path):
    from agent_brain import plugin

    link, _ = plugin.install(brain, None, tmp_path / "skills", copy=False)
    assert find(link).root == brain.root
    assert plugin.install(brain, None, tmp_path / "skills", copy=False)[0] == link


def test_pending_counts_from_when_it_was_set_pending(brain):
    record = scaffold.add_feedback(brain, name="Old note", words="Shorter?", source_role="editor", kind="preference", source="chat", date=dt.date(2025, 1, 1))
    scaffold.set_disposition(brain, record.id, "pending", "wait for a second time")
    assert not [f for f in checks.run(brain) if f.code == "feedback.pending_too_long"]


def test_write_keeps_dates_as_dates(brain):
    fid = add_correction(brain)
    text = (brain.references / "feedback" / f"{fid}.md").read_text()
    meta = yaml.safe_load(text.split("---\n")[1])
    assert isinstance(meta["date"], dt.date)


def test_future_feedback_dates_block(brain):
    fid = add_correction(brain)
    scaffold.set_disposition(brain, fid, "one-off", "a slip")
    set_meta(brain.references / "feedback" / f"{fid}.md", date=dt.date(2030, 1, 1))
    assert "feedback.future_date" in codes(brain)


def test_repository_pins_and_code_are_not_contact_details(brain):
    procedure = brain.references / "procedures" / "hand-off.md"
    procedure.write_text(procedure.read_text() + "\nPin `darkmatter.git@v0.7.4` from git+ssh://git@github.com/lynk-ai/darkmatter.git and git@github.com:lynk-ai/x.git.\n")
    assert codes(brain) == []
    assert checks.scan_sensitive("install git+ssh://git@github.com/org/repo.git@v1.2.3") == []
    assert checks.scan_sensitive("write to bob@example.com") == ["an email address"]


def test_a_broken_link_in_the_skill_blocks(brain):
    procedure = brain.references / "procedures" / "hand-off.md"
    procedure.write_text(procedure.read_text() + "\nSee [the rule](../rules/missing.md), [ok](take-feedback.md) and [web](https://example.org).\n")
    found = [f for f in checks.run(brain) if f.code == "link.broken"]
    assert len(found) == 1 and "missing.md" in found[0].message


def test_brain_yaml_levels_change_or_turn_off_a_check(brain):
    procedure = brain.references / "procedures" / "hand-off.md"
    procedure.write_text(procedure.read_text() + "\nThe project's CLAUDE.md file.\n")
    assert codes(brain) == ["core.harness_name"]
    config = brain.root / "brain.yaml"
    config.write_text(config.read_text() + "levels:\n  core.harness_name: warn\n")
    assert codes(find(brain.root)) == []
    config.write_text(config.read_text().replace("core.harness_name: warn", "core.harness_name: off"))
    assert all(f.code != "core.harness_name" for f in checks.run(find(brain.root)))


def test_set_status_rewrites_the_index_and_retiring_needs_a_reason(brain):
    import pytest
    from agent_brain.output import BrainError

    make_rule(brain)
    scaffold.set_status(brain, "rules/check-ui-against-current-release", "active", "")
    assert "rules/check-ui-against-current-release" in brain.skill_file.read_text()
    with pytest.raises(BrainError):
        scaffold.set_status(brain, "rules/check-ui-against-current-release", "retired", "")
    record = scaffold.set_status(brain, "rules/check-ui-against-current-release", "retired", "made drafts worse")
    assert "made drafts worse" in record.body
    assert "check-ui-against-current-release" not in brain.skill_file.read_text()
    assert codes(brain) == []


def test_new_takes_several_topics_rules_and_feedback_and_checks_them(brain):
    import pytest
    from agent_brain.output import BrainError

    first = add_correction(brain, "First lesson about screens")
    second = add_correction(brain, "Second lesson about screens")
    make_rule(brain, feedback_id=first)
    scaffold.new_record(brain, "topics", "style", {"name": "Style", "description": "How articles read."}, body="## Scope\n\nTone.\n")
    body = "## Steps\n\n1. Compare each screen.\n"
    record = scaffold.new_record(
        brain, "procedures", "review-screens", {"name": "Review screens", "description": "d", "trigger": "t", "outputs": "o"},
        feedback_ids=[second], topics=["accuracy", "style"], rules=["check-ui-against-current-release"], body=body,
    )
    assert record.meta["topics"] == ["accuracy", "style"]
    assert record.meta["rules"] == ["check-ui-against-current-release"]
    assert codes(brain) == []
    with pytest.raises(BrainError):
        scaffold.new_record(brain, "rules", "x-rule", {}, topics=["nope"])


def test_no_seed_brain_warns_without_take_feedback(repo):
    brain = scaffold.init(repo / "bare", "bare-agent", seed=False, display_name="Mila")
    assert "You are Mila." in brain.skill_file.read_text()
    assert not list((brain.references / "procedures").glob("*.md"))
    assert "procedure.no_take_feedback" in [f.code for f in checks.run(brain)]
