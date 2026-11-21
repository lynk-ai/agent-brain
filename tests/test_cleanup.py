import json

from agent_brain import checks, index, scaffold, team
from agent_brain.brain import find
from agent_brain.cli import main
from agent_brain.records import load, write_record

from conftest import fill
from test_team import acme, agent_without_routines  # noqa: F401


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def codes(brain):
    return [f.code for f in checks.blocking(checks.run(find(brain.root)))]


def test_a_new_brain_has_no_empty_harness_or_reports_folder(repo):
    brain = scaffold.init(repo / "b", "writer")
    crew = scaffold.init_team(repo / "t", "crew")
    assert not (brain.root / "harness").exists() and not (brain.root / "reports").exists()
    assert not (crew.root / "reports").exists() and not (crew.references / "agents").exists()
    dream = (brain.references / "procedures" / "run-the-dream.md").read_text()
    assert "reports/" not in dream and "dream pull request's description" in dream


def test_the_roster_is_a_list_in_the_team_brain_yaml_and_its_lines_link_no_file(acme, repo):
    assert sorted(acme.config["agents"]) == ["brains/reviewer", "brains/triage", "brains/writer"]
    assert set(team.roster(acme)) == {"reviewer", "triage", "writer"}
    text = acme.skill_file.read_text()
    assert "references/agents/" not in text and "(writer)." in text


def test_a_roster_file_left_from_format_2_blocks(acme):
    (acme.references / "agents").mkdir()
    (acme.references / "agents" / "writer.md").write_text("---\nname: writer\nsource: brains/writer\n---\n")
    assert "record.unknown_type" in codes(acme)


def test_agent_md_takes_skills_and_books_and_the_skill_lists_them(brain):
    record = load(brain).agent
    record.meta["skills"] = ["./skills/style", "support-team"]
    record.meta["books"] = ["bambooks:write-a-reply"]
    write_record(record)
    index.write(brain, load(brain))
    text = brain.skill_file.read_text()
    assert "**Your skills:**\n- ./skills/style\n- support-team" in text and "**Your books:**\n- bambooks:write-a-reply" in text
    assert codes(brain) == []


def test_loads_in_agent_md_blocks_and_says_where_to_move_it(brain):
    record = load(brain).agent
    record.meta["loads"] = {"brain": brain.name, "skills": ["support-team"]}
    write_record(record)
    found = [f for f in checks.run(find(brain.root)) if f.code == "agent.loads_removed"]
    assert found and found[0].level == "block" and "skills:" in found[0].fix


def test_hand_written_text_in_skill_md_blocks_and_stays_until_index_replace(brain, capsys):
    skill = brain.skill_file
    skill.write_text(skill.read_text().replace("Run every `brain` command", "Doreen collects the news.\n\nRun every `brain` command").replace("<!-- brain:opening:end -->", "<!-- brain:opening:end -->\n\nDoreen collects the news."))
    assert "skill.hand_written" in codes(brain)
    code, _ = run(capsys, "index", "--project", str(brain.root))
    assert code == 0 and "Doreen collects the news." in skill.read_text()
    code, _ = run(capsys, "index", "--replace", "--project", str(brain.root))
    assert code == 0 and "Doreen" not in skill.read_text() and codes(brain) == []


def test_a_new_display_name_rewrites_the_opening(brain):
    record = load(brain).agent
    record.meta["display_name"] = "Hana"
    write_record(record)
    index.write(brain, load(brain))
    assert "You are Hana." in brain.skill_file.read_text() and codes(brain) == []


def test_the_description_is_the_one_hand_written_part(brain):
    skill = brain.skill_file
    skill.write_text(skill.read_text().replace("Help-center writer's rules and procedures.", "The help-center writer's brain."))
    index.write(brain, load(brain), replace=True)
    assert "description: The help-center writer's brain." in skill.read_text() and codes(brain) == []


def test_a_member_without_the_team_domain_warns(acme):
    config = acme.root / "brain.yaml"
    config.write_text(config.read_text().replace("# domain: acme\n", "domain: acme\n"))
    found = [f for f in checks.run(find(acme.root)) if f.code == "team.name_domain"]
    assert {f.level for f in found} == {"warn"} and len(found) == 3
    assert codes(acme) == []


def test_one_agent_with_no_team_loads_alone_and_brain_use_saves_it(repo, capsys, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("BRAIN_CONFIG", str(tmp_path_factory.mktemp("settings") / "config.toml"))
    agent = agent_without_routines(repo, "solo")
    code, out = run(capsys, "load", "--dry-run", "--no-fetch", "--checkout", "--json", "--project", str(agent.root))
    data = json.loads(out)
    assert code == 0 and data["value"]["agent"]["name"] == "solo" and data["value"]["team"] is None
    assert data["value"]["command"][:3] == ["claude", "--plugin-dir", str(agent.root.resolve())]
    code, out = run(capsys, "load", "someone-else", "--dry-run", "--no-fetch", "--checkout", "--project", str(agent.root))
    assert code == 2 and "[load.not_on_team]" in out
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    monkeypatch.chdir(elsewhere)
    code, out = run(capsys, "use", str(agent.root))
    assert code == 0 and "agent brain solo" in out
    code, out = run(capsys, "load", "--dry-run", "--no-fetch", "--checkout", "--json")
    assert code == 0 and json.loads(out)["value"]["agent"]["name"] == "solo"


def test_a_team_load_still_needs_the_agent_named(acme, capsys):
    code, out = run(capsys, "load", "--dry-run", "--no-fetch", "--checkout", "--project", str(acme.root))
    assert code == 2 and "[load.no_agent]" in out
