import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent_brain import adapters, checks, index, scaffold, team
from agent_brain.brain import find
from agent_brain.cli import main
from agent_brain.records import load, write_record

from test_team import agent_without_routines, finish_team

PEOPLE = {
    "triage": ("Tara", "Sorts support tickets by urgency"),
    "writer": ("Wes", "Drafts replies to support tickets"),
    "reviewer": ("Rey", "Reviews drafted replies before they go out"),
}


def set_agent(repo: Path, name: str, **meta) -> None:
    agent = find(repo / "brains" / name)
    record = load(agent).agent
    record.meta.update(meta)
    write_record(record)
    index.write(agent, load(agent), repo)


def set_team_config(crew, text: str) -> None:
    path = crew.root / "brain.yaml"
    path.write_text(path.read_text() + text)


@pytest.fixture
def crew(repo: Path, monkeypatch, tmp_path_factory):
    # Every test reads and writes its own settings file, never the person's.
    monkeypatch.setenv("BRAIN_CONFIG", str(tmp_path_factory.mktemp("settings") / "config.toml"))
    made = scaffold.init_team(repo / "brains" / "acme-support", "acme-support")
    finish_team(made)
    for name, (display, job) in PEOPLE.items():
        agent = agent_without_routines(repo, name)
        text = agent.agent_file.read_text().replace("help-center article drafts", f"{name} work for support tickets")
        agent.agent_file.write_text(text)
        team.add(find(made.root), agent.root)
        set_agent(repo, name, display_name=display, job=job, loads={"brain": name, "books": [], "skills": ["acme-support"]})
    crew = find(made.root)
    index.write(crew, load(crew), repo)
    return crew


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def dry(capsys, crew, *argv):
    return run(capsys, "load", *argv, "--dry-run", "--no-fetch", "--project", str(crew.root))


def test_the_team_brain_with_loads_passes_its_checks(crew, repo):
    for brain in [crew, *(find(repo / "brains" / n) for n in PEOPLE)]:
        assert [f.code for f in checks.blocking(checks.run(find(brain.root)))] == [], brain.name


def test_claude_adapter_builds_the_exact_command():
    built = adapters.command("claude", [Path("/r/brains/sivan"), Path("/r/brains/team")], "You are Sivan.", ["--model", "opus"])
    assert built == ["claude", "--plugin-dir", "/r/brains/sivan", "--plugin-dir", "/r/brains/team", "--append-system-prompt", "You are Sivan.", "--model", "opus"]


def test_codex_adapter_builds_the_exact_command():
    built = adapters.command("codex", [Path("/r/brains/sivan")], 'You are Sivan.\nRead "/r/SKILL.md".', [])
    assert built == ["codex", "-c", 'developer_instructions="You are Sivan.\\nRead \\"/r/SKILL.md\\"."']


def test_cursor_has_no_adapter_yet():
    with pytest.raises(Exception) as caught:
        adapters.command("cursor", [], "x", [])
    assert caught.value.finding.code == "load.no_adapter"


def test_load_matches_the_display_name_and_builds_the_claude_command(crew, repo, capsys):
    code, out = dry(capsys, crew, "tara", "--json")
    data = json.loads(out)
    assert code == 0 and data["value"]["agent"]["name"] == "triage"
    triage, acme = repo / "brains" / "triage", repo / "brains" / "acme-support"
    instruction = (
        "You are Tara. Before your first answer, read these skills in this order and follow them:\n"
        f"{triage.resolve()}/triage/SKILL.md\n{acme.resolve()}/acme-support/SKILL.md"
    )
    assert data["value"]["command"] == ["claude", "--plugin-dir", str(triage.resolve()), "--plugin-dir", str(acme.resolve()), "--append-system-prompt", instruction]
    assert data["findings"] == []


def test_load_matches_the_brain_name_then_a_word_of_the_job(crew, capsys):
    code, out = dry(capsys, crew, "Writer", "--json")
    assert code == 0 and json.loads(out)["value"]["agent"]["display_name"] == "Wes"
    code, out = dry(capsys, crew, "urgency", "--json")
    assert code == 0 and json.loads(out)["value"]["agent"]["name"] == "triage"


def test_an_ambiguous_match_lists_the_agents_and_exits_2(crew, capsys):
    code, out = dry(capsys, crew, "replies")
    assert code == 2 and "[load.ambiguous]" in out
    assert "Wes" in out and "Rey" in out and "Tara" not in out


def test_no_match_says_not_on_the_team_and_lists_the_roster(crew, capsys):
    code, out = dry(capsys, crew, "sivan")
    assert code == 2 and "not on the team" in out and "[load.not_on_team]" in out
    assert all(display in out for display, _ in PEOPLE.values())


def test_a_missing_skill_warns_in_load_and_blocks_in_check(crew, repo, capsys):
    set_agent(repo, "writer", loads={"brain": "writer", "skills": ["acme-support", "style-guide"]})
    code, out = dry(capsys, crew, "wes")
    assert code == 0 and "warn brains/writer/writer/agent.md: writer loads style-guide" in out and "[load.not_provided]" in out
    assert "style-guide" not in out.split("command:")[1].split("\n")[1]
    blocks = checks.blocking(checks.run(find(crew.root)))
    assert [f.code for f in blocks] == ["load.not_provided"]


def test_a_known_gap_only_warns(crew, repo, capsys):
    set_agent(repo, "writer", loads={"brain": "writer", "skills": ["acme-support", "style-guide"]})
    set_team_config(crew, "known_gaps: [style-guide]\n")
    crew = find(crew.root)
    findings = checks.run(crew)
    assert checks.blocking(findings) == []
    assert [f.code for f in findings if f.code.startswith("load.")] == ["load.known_gap"]
    code, out = dry(capsys, crew, "wes")
    assert code == 0 and "[load.known_gap]" in out


def test_a_book_not_in_the_list_warns_and_an_unlisted_source_is_skipped(crew, repo, capsys):
    (repo / "tools").mkdir()
    (repo / "tools" / "books.txt").write_text("# book ids\nwrite-a-reply\n")
    set_team_config(crew, "books: {bambooks: tools/books.txt}\n")
    set_agent(repo, "writer", loads={"brain": "writer", "skills": ["acme-support"], "books": ["bambooks:write-a-reply", "bambooks:gone-book", "other:a-book"]})
    crew = find(crew.root)
    findings = checks.run(crew)
    assert checks.blocking(findings) == []
    unlisted = [f for f in findings if f.code == "load.book_unlisted"]
    assert len(unlisted) == 1 and "bambooks:gone-book" in unlisted[0].message
    assert [f.file for f in findings if f.code == "load.no_book_list"] == ["brain.yaml"]
    code, out = dry(capsys, crew, "wes", "--json")
    data = json.loads(out)
    assert [f["code"] for f in data["findings"]] == ["load.book_unlisted"]
    assert data["value"]["instruction"].endswith("Your books are in the Bambooks library: write-a-reply, gone-book.\nYour books from other: a-book.")


def test_a_bad_book_entry_and_a_bad_team_setting_block_check(crew, repo):
    set_agent(repo, "writer", loads={"brain": "writer", "skills": ["acme-support"], "books": ["no-source"]})
    set_team_config(crew, "known_gaps: style-guide\n")
    assert sorted(f.code for f in checks.blocking(checks.run(find(crew.root)))) == ["brain.config", "load.bad_book"]


def test_the_agent_md_harness_is_checked_and_picks_the_adapter(crew, repo, capsys):
    set_agent(repo, "writer", harness="codex")
    code, out = dry(capsys, crew, "wes", "--json")
    assert code == 0 and json.loads(out)["value"]["command"][:2] == ["codex", "-c"]
    code, out = dry(capsys, crew, "wes", "--harness", "claude", "--json")
    assert json.loads(out)["value"]["command"][0] == "claude"
    set_agent(repo, "writer", harness="vim")
    writer = find(repo / "brains" / "writer")
    assert "record.bad_value" in [f.code for f in checks.blocking(checks.run(writer))]


def test_arguments_after_the_separator_go_to_the_harness(crew, capsys):
    code, out = run(capsys, "load", "rey", "--dry-run", "--no-fetch", "--json", "--project", str(crew.root), "--", "--model", "opus", "--dry-run")
    assert code == 0 and json.loads(out)["value"]["command"][-3:] == ["--model", "opus", "--dry-run"]


def test_team_use_saves_the_path_and_team_lists_from_any_folder(crew, repo, capsys, monkeypatch, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    monkeypatch.chdir(elsewhere)
    code, out = run(capsys, "team")
    assert code == 2 and "[team.not_saved]" in out
    code, out = run(capsys, "team", "use", str(repo))
    assert code == 0 and "team acme-support" in out
    code, out = run(capsys, "team", "use")
    assert code == 0 and str(repo.resolve()) in out
    code, out = run(capsys, "team")
    assert code == 0 and "Tara   triage     Sorts support tickets by urgency" in out
    code, out = run(capsys, "team", "--json")
    data = json.loads(out)
    assert [a["display_name"] for a in data["value"]["agents"]] == ["Rey", "Tara", "Wes"]
    assert data["value"]["from"].startswith("the saved path")


def test_the_current_folder_wins_over_the_saved_path(crew, repo, capsys, monkeypatch, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    scaffold.init_team(other / "brains" / "other-team", "other-team")
    run(capsys, "team", "use", str(other))
    monkeypatch.chdir(repo / "brains" / "writer")
    code, out = run(capsys, "team", "--json")
    assert json.loads(out)["value"]["team"] == "acme-support"
    code, out = run(capsys, "team", "--project", str(other), "--json")
    assert json.loads(out)["value"]["team"] == "other-team"


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


@pytest.fixture
def behind(crew, repo, tmp_path_factory):
    # A clone that is 1 commit behind its upstream.
    for args in (("add", "-A"), ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "team")):
        git(repo, *args)
    remote = tmp_path_factory.mktemp("remote") / "acme.git"
    git(repo, "clone", "-q", "--bare", str(repo), str(remote))
    clone = tmp_path_factory.mktemp("clone") / "acme"
    git(repo, "clone", "-q", str(remote), str(clone))
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "later")
    git(repo, "push", "-q", str(remote), "HEAD:" + subprocess.run(["git", "-C", str(clone), "branch", "--show-current"], capture_output=True, text=True).stdout.strip())
    return clone


def test_a_checkout_behind_its_upstream_asks_before_it_starts(behind, capsys, monkeypatch):
    project = str(behind / "brains" / "acme-support")
    code, out = run(capsys, "load", "tara", "--dry-run", "--project", project)
    assert code == 0 and "1 commit behind" in out and "[load.behind]" in out
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    code, out = run(capsys, "load", "tara", "--project", project)
    assert code == 3 and "nothing started" in out
    started = []
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda question: "y")
    monkeypatch.setattr("agent_brain.cli.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("agent_brain.cli.os.execvp", lambda file, argv: started.append(argv))
    run(capsys, "load", "tara", "--project", project)
    assert started and started[0][0] == "claude"
    assert started[0][2] == str((behind / "brains" / "triage").resolve())
