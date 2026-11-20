import datetime as dt
import subprocess
from pathlib import Path

import pytest

from agent_brain import checks, index, scaffold, team
from agent_brain.brain import find
from agent_brain.output import BrainError
from agent_brain.records import load

from conftest import add_correction, fill

AGENTS = ("triage", "writer", "reviewer")


def codes_of(brain):
    return [f.code for f in checks.blocking(checks.run(find(brain.root)))]


def agent_without_routines(repo, name):
    agent = scaffold.init(repo / "brains" / name, name)
    for routine in (agent.references / "routines").glob("*.md"):
        routine.unlink()
    fill(agent)
    return agent


def finish_team(brain) -> None:
    text = brain.skill_file.read_text().replace(brain.skill_file.read_text().split("description: ")[1].split("\n")[0], "Acme support's team of agents. Use when work crosses lanes.")
    brain.skill_file.write_text(text)
    index.write(brain, load(brain))


@pytest.fixture
def acme(repo: Path):
    # A non-Lynk team: 3 agents with no routines, each with one lane.
    crew = scaffold.init_team(repo / "brains" / "acme-support", "acme-support")
    finish_team(crew)
    for name in AGENTS:
        agent = agent_without_routines(repo, name)
        text = agent.agent_file.read_text().replace("help-center article drafts", f"{name} work for support tickets")
        agent.agent_file.write_text(text)
        index.write(agent, load(agent))
        team.add(find(crew.root), agent.root)
    return find(crew.root)


def test_a_new_team_brain_blocks_until_its_description_is_filled(repo):
    crew = scaffold.init_team(repo / "t", "acme-support")
    assert set(codes_of(crew)) == {"record.unfinished"}
    finish_team(crew)
    assert codes_of(crew) == []


def test_a_team_of_three_agents_with_no_routines_passes(acme, repo):
    for brain in [acme, *(find(repo / "brains" / n) for n in AGENTS)]:
        assert codes_of(brain) == [], brain.name
    text = acme.skill_file.read_text()
    assert "## Roster" in text and "(writer)" in text and "Lanes: writer work for support tickets." in text
    assert "## Routines" in text
    writer = find(repo / "brains" / "writer")
    assert writer.team == "acme-support" and writer.config["format"] == 2
    assert "lane" not in load(writer).agent.meta
    assert "**Team:** acme-support." in writer.skill_file.read_text()
    assert (acme.references / "agents" / "writer.md").read_text().count("source: brains/writer") == 1


def test_a_full_feedback_round_trip(acme, repo):
    writer = find(repo / "brains" / "writer")
    fid = add_correction(writer, "Hand billing tickets to triage")
    assert "feedback.undecided" in codes_of(writer)
    scaffold.set_disposition(writer, fid, "elsewhere", "a team hand-off rule", ["brain:acme-support"])
    assert codes_of(writer) == []
    late = [f for f in checks.run(acme, today=dt.date.today() + dt.timedelta(days=15)) if f.code == "intake.missing"]
    assert len(late) == 1 and late[0].level == "warn"

    intake = scaffold.add_feedback(acme, name="", words="", source_role="", kind="", source="", intake_of=f"brain:writer/{fid}")
    assert intake.meta["from"] == "editor" and "This menu was removed" in intake.body
    assert intake.meta["source"] == "review of draft 112" and intake.meta["intake_of"] == f"brain:writer/{fid}"
    assert "feedback.undecided" in codes_of(acme)
    policy = scaffold.new_record(
        acme, "policies", "hand-billing-to-triage",
        {"name": "Hand every billing ticket to triage.", "description": "Billing goes to triage first.", "scope": "Every ticket about billing."},
        feedback_ids=[intake.id], topics=["how-the-team-works"],
        body="## Policy\n\nBilling tickets go to triage.\n\n## Why\n\nA writer answered one.\n\n## How to apply\n\nDo hand it over. Don't answer it.\n",
    )
    scaffold.set_status(acme, policy.ref, "active", "")
    assert load(acme).get(f"feedback/{intake.id}").meta["kept_in"] == ["policies/hand-billing-to-triage"]
    assert "Hand every billing ticket to triage" in acme.skill_file.read_text()
    assert codes_of(acme) == [] and codes_of(writer) == []
    assert not [f for f in checks.run(acme, today=dt.date.today() + dt.timedelta(days=15)) if f.code == "intake.missing"]


def test_an_agent_points_only_to_its_team_or_a_teammate(acme, repo):
    writer = find(repo / "brains" / "writer")
    fid = add_correction(writer)
    with pytest.raises(BrainError):
        scaffold.set_disposition(writer, fid, "elsewhere", "x", ["brain:other-team"])
    scaffold.set_disposition(writer, fid, "elsewhere", "the reviewer's lesson", ["brain:reviewer"])
    assert codes_of(writer) == []


def test_intake_of_must_resolve_and_point_here(acme, repo):
    with pytest.raises(BrainError) as exc:
        scaffold.add_feedback(acme, name="n", words="w", source_role="r", kind="praise", source="chat", intake_of="chat")
    assert exc.value.finding.code == "intake.bad_pointer"
    writer = find(repo / "brains" / "writer")
    fid = add_correction(writer)
    scaffold.set_disposition(writer, fid, "one-off", "a slip")
    with pytest.raises(BrainError) as exc:
        scaffold.add_feedback(acme, name="", words="", source_role="", kind="", source="", intake_of=f"brain:writer/{fid}")
    assert exc.value.finding.code == "intake.not_pointed"


def test_an_agent_in_a_team_may_hold_no_routine_or_lane(acme, repo):
    writer = find(repo / "brains" / "writer")
    with pytest.raises(BrainError):
        scaffold.new_record(writer, "routines", "weekly", {})
    (writer.references / "routines" / "weekly.md").write_text("---\nname: Weekly\n---\n")
    writer.agent_file.write_text(writer.agent_file.read_text().replace("anti_jobs:", "lane: [x]\nanti_jobs:"))
    found = codes_of(writer)
    assert "team.agent_has_routine" in found and "team.agent_has_lane" in found


def test_an_agent_names_a_team_that_lists_it(acme, repo):
    loner = agent_without_routines(repo, "loner")
    team.set_config_lines(loner, {"team": "acme-support"})
    assert "team.not_member" in codes_of(loner)
    team.set_config_lines(loner, {"team": "nobody"})
    assert "team.not_found" in codes_of(loner)


def test_lanes_need_one_known_owner_per_work(acme):
    lanes = acme.references / "lanes.md"
    lanes.write_text(lanes.read_text() + "| writer work for support tickets | triage |\n| refunds | finance |\n")
    found = codes_of(acme)
    assert "lanes.duplicate" in found and "lanes.unknown_owner" in found


def test_team_add_refuses_a_lane_that_would_break_the_table(acme, repo):
    other = agent_without_routines(repo, "pipe")
    other.agent_file.write_text(other.agent_file.read_text().replace("help-center article drafts", "drafts | replies"))
    with pytest.raises(BrainError) as exc:
        team.add(acme, other.root)
    assert exc.value.finding.code == "lanes.bad_work"
    assert "pipe" not in load(acme).by_folder["agents"] and codes_of(acme) == []


def test_team_add_refuses_a_lane_another_agent_owns(acme, repo):
    other = agent_without_routines(repo, "other-writer")
    other.agent_file.write_text(other.agent_file.read_text().replace("help-center article drafts", "writer work for support tickets"))
    with pytest.raises(BrainError) as exc:
        team.add(acme, other.root)
    assert exc.value.finding.code == "lanes.duplicate"
    assert "other-writer" not in load(acme).by_folder["agents"]


def test_roster_drift_blocks(acme, repo):
    writer = find(repo / "brains" / "writer")
    writer.agent_file.write_text(writer.agent_file.read_text().replace("Drafts help-center articles from product changes", "Writes replies"))
    assert codes_of(acme) == ["skill.index_stale"]
    index.write(acme, load(acme))
    assert codes_of(acme) == []


def test_a_roster_source_must_be_an_agent_brain_in_this_team(acme, repo):
    entry = acme.references / "agents" / "writer.md"
    entry.write_text(entry.read_text().replace("brains/writer", "brains/nowhere"))
    assert "team.source_missing" in codes_of(acme)


def test_team_routines_point_to_a_procedure_in_a_roster_agent(acme, repo):
    def routine(pointer, owner="triage"):
        path = acme.references / "routines" / "morning.md"
        path.write_text(
            f"---\nname: Morning\ndescription: d\ntrigger: 09:00\nowner: {owner}\nprocedure: {pointer}\nreceiver: lead\nwhen_nothing_new: Send nothing.\nstatus: active\n---\n"
        )

    routine("triage:hand-off")
    assert codes_of(acme) == []
    routine("hand-off")
    assert "routine.bad_procedure" in codes_of(acme)
    routine("triage:nope")
    assert "routine.unresolved_procedure" in codes_of(acme)
    routine("ghost:hand-off")
    assert "routine.unresolved_procedure" in codes_of(acme)
    routine("triage:hand-off", owner="ghost")
    assert "routine.unknown_owner" in codes_of(acme)


def test_team_add_moves_routines_under_the_agents_name(repo):
    crew = scaffold.init_team(repo / "brains" / "crew", "crew")
    finish_team(crew)
    for name in ("ana", "ben"):
        agent = scaffold.init(repo / "brains" / name, name)
        fill(agent)
        agent.agent_file.write_text(agent.agent_file.read_text().replace("help-center article drafts", f"{name}'s work"))
        lines = team.add(find(crew.root), agent.root)
    routines = load(find(crew.root)).by_folder["routines"]
    assert set(routines) == {"ana-nightly-dream", "ben-nightly-dream"}
    assert routines["ben-nightly-dream"].meta["procedure"] == "ben:run-the-dream"
    assert routines["ben-nightly-dream"].meta["name"] == "Nightly dream (ben)"
    assert any("routine: ben-nightly-dream" in line for line in lines)
    assert codes_of(crew) == [] and codes_of(find(repo / "brains" / "ben")) == []


def test_a_format_one_brain_warns_and_a_newer_one_is_refused(repo, brain):
    config = brain.root / "brain.yaml"
    config.write_text(config.read_text().replace("format: 2\n", ""))
    found = checks.run(find(brain.root))
    assert [f.code for f in found] == ["brain.format_missing"] and found[0].level == "warn"
    config.write_text("format: 3\n" + config.read_text())
    with pytest.raises(BrainError) as exc:
        find(brain.root)
    assert exc.value.finding.code == "brain.format_newer"


def test_check_staged_resolves_team_links(acme, repo, capsys):
    from agent_brain.cli import main

    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    assert main(["check", "--staged", "--project", str(repo)]) == 0, capsys.readouterr().out


def test_an_agent_skill_carries_its_lanes_from_the_team(acme, repo, capsys):
    from agent_brain.cli import main

    writer = find(repo / "brains" / "writer")
    assert "**Your lane:**\n- writer work for support tickets" in writer.skill_file.read_text()
    lanes = acme.references / "lanes.md"
    lanes.write_text(lanes.read_text() + "| style guide | writer |\n")
    assert codes_of(writer) == ["skill.agent_stale"]
    assert main(["index", "--project", str(acme.root)]) == 0
    assert "writer" in capsys.readouterr().out
    assert codes_of(writer) == [] and codes_of(acme) == []
    assert "- style guide" in writer.skill_file.read_text()


def test_routine_owner_warnings(acme):
    path = acme.references / "routines" / "morning.md"
    path.write_text("---\nname: Morning\ndescription: d\ntrigger: 09:00\nowner: writer\nprocedure: triage:hand-off\nreceiver: lead\nwhen_nothing_new: Send nothing.\nstatus: active\n---\n")
    warns = {f.code for f in checks.run(acme) if f.level == "warn"}
    assert "routine.owner_not_runner" in warns
    lanes = acme.references / "lanes.md"
    lanes.write_text(lanes.read_text().replace("| writer work for support tickets | writer |\n", ""))
    warns = {f.code for f in checks.run(acme) if f.level == "warn"}
    assert {"routine.owner_no_lane", "lanes.agent_without_lane"} <= warns


def test_team_remove_gives_back_lanes_and_routines(repo, capsys):
    from agent_brain.cli import main

    crew = scaffold.init_team(repo / "brains" / "crew", "crew")
    finish_team(crew)
    for name in ("ana", "ben"):
        agent = scaffold.init(repo / "brains" / name, name)
        fill(agent)
        agent.agent_file.write_text(agent.agent_file.read_text().replace("help-center article drafts", f"{name}'s work"))
        team.add(find(crew.root), agent.root)
    project = ["--project", str(crew.root)]
    assert main(["team", "remove", "ana", *project]) == 2
    assert "nightly-dream" in capsys.readouterr().out
    assert main(["team", "remove", "ana", "--routine", "ana-nightly-dream=ben", *project]) == 0, capsys.readouterr().out
    capsys.readouterr()
    ana = find(repo / "brains" / "ana")
    assert ana.team is None and load(ana).agent.meta["lane"] == ["ana's work"]
    routine = load(find(crew.root)).by_folder["routines"]["ana-nightly-dream"]
    assert routine.meta["owner"] == "ben" and routine.meta["procedure"] == "ben:run-the-dream"
    assert codes_of(ana) == [] and codes_of(crew) == []
    paused = crew.references / "routines" / "ben-nightly-dream.md"
    paused.write_text(paused.read_text().replace("status: active", "status: paused"))
    assert main(["team", "remove", "ben", "--routine", "ana-nightly-dream=retire", "--routine", "ben-nightly-dream=back", *project]) == 0, capsys.readouterr().out
    ben = find(repo / "brains" / "ben")
    back = load(ben).by_folder["routines"]["nightly-dream"]
    assert back.meta["procedure"] == "run-the-dream" and back.meta["name"] == "Nightly dream" and back.meta["status"] == "paused"
    assert load(find(crew.root)).by_folder["routines"]["ana-nightly-dream"].meta["status"] == "retired"
    assert codes_of(ben) == []
    assert not load(find(crew.root)).by_folder["agents"]


def test_team_brain_kinds_are_its_own(acme, repo):
    with pytest.raises(BrainError) as exc:
        scaffold.new_record(acme, "rules", "x", {})
    assert exc.value.finding.code == "new.kind"
    writer = find(repo / "brains" / "writer")
    with pytest.raises(BrainError):
        scaffold.new_record(writer, "policies", "x", {})
    record = scaffold.new_record(acme, "routines", "weekly", {"owner": "triage", "procedure": "triage:hand-off"})
    assert record.meta["owner"] == "triage"


def test_plugin_for_a_team(acme, repo):
    import json

    from agent_brain import plugin

    market = repo / ".claude-plugin" / "marketplace.json"
    market.parent.mkdir()
    market.write_text(json.dumps({"name": "acme", "plugins": []}))
    plugin.write(acme)
    entries = {p["name"]: p for p in json.loads(market.read_text())["plugins"]}
    assert entries["acme-support"]["source"] == "./brains/acme-support"
    assert json.loads((acme.root / ".claude-plugin" / "plugin.json").read_text())["skills"] == "./"
    assert [f for f in checks.run(find(acme.root)) if f.code == "plugin.drift"] == []


def test_team_add_from_the_command_line(repo, capsys):
    from agent_brain.cli import main

    assert main(["init", "crew", "--team", "--path", str(repo / "brains" / "crew")]) == 0
    agent = agent_without_routines(repo, "ana")
    capsys.readouterr()
    assert main(["team", "add", str(agent.root), "--project", str(repo / "brains" / "crew")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ok: ") and "roster: ana from brains/ana" in out and "one commit" in out
    assert main(["team", "add", str(agent.root), "--project", str(agent.root)]) == 2


def test_the_intake_wait_counts_from_a_reworded_elsewhere_line(acme, repo):
    writer = find(repo / "brains" / "writer")
    fid = add_correction(writer)
    scaffold.set_disposition(writer, fid, "elsewhere", "a team rule", ["brain:acme-support"])
    path = writer.references / "feedback" / f"{fid}.md"
    path.write_text(path.read_text().replace(f"{dt.date.today().isoformat()}, elsewhere:", "- 2026-01-05 Set to Elsewhere, because"))
    late = [f for f in checks.run(acme, today=dt.date(2026, 1, 25)) if f.code == "intake.missing"]
    assert len(late) == 1 and "20 days" in late[0].message


def test_index_in_an_agent_rewrites_its_team_roster(acme, repo, capsys):
    from agent_brain.cli import main

    writer = find(repo / "brains" / "writer")
    writer.agent_file.write_text(writer.agent_file.read_text().replace("Drafts help-center articles from product changes", "Writes replies"))
    assert codes_of(acme) == ["skill.index_stale"]
    assert main(["index", "--project", str(writer.root)]) == 0
    assert "team SKILL.md rewritten: acme-support" in capsys.readouterr().out
    assert codes_of(acme) == [] and codes_of(writer) == []


def test_set_status_on_a_team_routine_and_a_policy(repo, capsys):
    from agent_brain.cli import main

    assert main(["init", "acme", "--team", "--path", str(repo / "brains" / "acme")]) == 0
    agent = agent_without_routines(repo, "ana")
    project = ["--project", str(repo / "brains" / "acme")]
    assert main(["team", "add", str(agent.root), *project]) == 0
    assert main(["new", "routine", "x", "--owner", "ana", "--procedure", "ana:run-the-dream", *project]) == 0
    capsys.readouterr()
    assert main(["set-status", "routines/x", "retired", "--reason", "y", *project]) == 0, capsys.readouterr().out
    routine = load(find(repo / "brains" / "acme")).by_folder["routines"]["x"]
    assert routine.meta["status"] == "retired" and "retired: y" in routine.body
    assert main(["set-status", "routines/x", "paused", *project]) == 0
    assert main(["set-status", "routines/x", "proposed", *project]) == 2
    assert "[status.value]" in capsys.readouterr().out
    assert main(["new", "policy", "p", *project]) == 0
    assert main(["set-status", "policies/p", "active", *project]) == 0
    assert load(find(repo / "brains" / "acme")).by_folder["policies"]["p"].meta["status"] == "active"
    capsys.readouterr()
    assert main(["set-status", "rules/p", "active", *project]) == 2
    out = capsys.readouterr().out
    assert "set-status takes only policies/<id> or routines/<id>." in out and "Feedback" not in out


def test_link_unlink_and_trace_name_the_team_targets(acme, repo, capsys):
    from agent_brain.cli import main

    writer = find(repo / "brains" / "writer")
    fid = add_correction(writer)
    scaffold.set_disposition(writer, fid, "elsewhere", "a team rule", ["brain:acme-support"])
    intake = scaffold.add_feedback(acme, name="", words="", source_role="", kind="", source="", intake_of=f"brain:writer/{fid}")
    project = ["--project", str(acme.root)]
    capsys.readouterr()
    for command in (["link", intake.id, "rules/x"], ["unlink", intake.id, "procedures/x"], ["link", intake.id, "agent"]):
        assert main([*command, *project]) == 2
        out = capsys.readouterr().out
        assert "Feedback links only to policies/<id>, routines/<id> or lanes." in out and "or agent" not in out
    assert main(["link", intake.id, "lanes", *project]) == 0
    capsys.readouterr()
    assert main(["trace", "lanes", *project]) == 0
    assert f"from feedback {intake.id}" in capsys.readouterr().out
    assert main(["trace", f"feedback/{intake.id}", *project]) == 0
    assert "kept in lanes" in capsys.readouterr().out
    assert main(["trace", "rules/nope", *project]) == 2
    assert "policies/<id>, routines/<id>, feedback/<id> or lanes" in capsys.readouterr().out
    assert main(["link", fid, "x/y", "--project", str(writer.root)]) == 2
    assert "rules/<id>, procedures/<id> or agent." in capsys.readouterr().out
