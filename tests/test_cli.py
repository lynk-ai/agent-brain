import json
import subprocess
import sys

from agent_brain import hooks, scaffold
from agent_brain.brain import find_all
from agent_brain.cli import main

from conftest import add_correction, fill, make_rule


def run(capsys, *argv, stdin=None, monkeypatch=None):
    if stdin is not None:
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_feedback_add_reads_stdin_and_refuses_contact_details(brain, capsys, monkeypatch):
    project = str(brain.skill_dir)
    code, out = run(capsys, "feedback", "add", "--project", project, "--name", "Too long", "--from", "editor", "--kind", "preference", "--source", "chat", stdin="Shorter, please.", monkeypatch=monkeypatch)
    assert code == 0 and out.startswith("ok: Feedback 20")
    code, out = run(capsys, "feedback", "add", "--project", project, "--name", "x", "--from", "editor", "--kind", "praise", "--source", "chat", "--text", "write to a@b.co")
    assert code == 3 and "[data.sensitive]" in out


def test_check_exit_codes_and_json(brain, capsys):
    code, out = run(capsys, "check", "--project", str(brain.root))
    assert code == 0
    add_correction(brain)
    code, out = run(capsys, "check", "--project", str(brain.root), "--json")
    data = json.loads(out)
    assert code == 3 and data["outcome"] == "failed"
    assert data["findings"][0]["code"] == "feedback.undecided"


def test_check_all_covers_every_brain_in_one_repository(repo, brain, capsys):
    scaffold.init(repo / "brains" / "analyst", "pricing-analyst")
    assert len(find_all(repo)) == 2
    code, out = run(capsys, "check", "--all", "--project", str(repo))
    assert code == 3
    assert "brains/analyst/pricing-analyst/agent.md" in out
    assert "help-center-writer/agent.md" not in out


def test_missing_brain_is_an_error(tmp_path, capsys):
    code, out = run(capsys, "check", "--project", str(tmp_path))
    assert code == 2 and "[brain.not_found]" in out


def test_trace_shows_the_feedback_behind_a_rule(brain, capsys):
    fid = make_rule(brain)
    code, out = run(capsys, "trace", "--project", str(brain.root), "check-ui-against-current-release")
    assert code == 0
    assert fid in out and "This menu was removed two releases ago." in out


def test_stop_hook_blocks_once_per_turn(brain):
    add_correction(brain)
    out = hooks.stop({"stop_hook_active": False}, [brain])
    assert out["decision"] == "block" and "feedback.undecided" in out["reason"]
    assert hooks.stop({"stop_hook_active": True}, [brain]) is None


def test_stop_hook_is_silent_on_a_clean_brain(brain):
    assert hooks.stop({"stop_hook_active": False}, [brain]) is None


def test_claude_install_keeps_other_hooks_and_replaces_its_own(brain, tmp_path):
    work = tmp_path / "work"
    settings = work / ".claude" / "settings.local.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other-tool"}]}]}, "model": "x"}))
    hooks.install_host("claude", work, brain.root)
    hooks.install_host("claude", work, brain.root)
    data = json.loads(settings.read_text())
    stop_commands = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
    assert data["model"] == "x"
    assert stop_commands[0] == "other-tool"
    assert len(stop_commands) == 2 and stop_commands[1].endswith(f"hook stop --host claude --project {brain.root}")
    assert len(data["hooks"]["SessionStart"]) == 1


def test_pre_commit_hook_blocks_a_commit_with_undecided_feedback(repo, brain, monkeypatch):
    monkeypatch.setattr(hooks, "brain_command", lambda: f"{sys.executable} -m agent_brain")
    hooks.install_git(repo)
    add_correction(brain)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    result = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "feedback.undecided" in result.stdout + result.stderr


def test_new_rule_refuses_an_unknown_feedback(brain, capsys):
    code, out = run(capsys, "new", "rule", "x-rule", "--project", str(brain.root), "--feedback", "nope")
    assert code == 2 and "[record.not_found]" in out


def test_global_options_work_before_the_command(brain, repo, capsys):
    other = scaffold.init(repo / "brains" / "other", "other-agent")
    code, out = run(capsys, "--json", "--project", str(other.root), "status")
    assert json.loads(out)["headline"] == "Brain other-agent."
    code, out = run(capsys, "--project", str(other.root), "status", "--project", str(brain.root))
    assert code == 2 and "[cli.two_projects]" in out and out.startswith("error:")


def test_feedback_add_refuses_a_correction_without_did_and_a_future_date(brain, capsys):
    base = ["feedback", "add", "--project", str(brain.root), "--name", "n", "--from", "editor", "--source", "s", "--text", "t"]
    code, out = run(capsys, *base, "--kind", "correction")
    assert code == 2 and "[feedback.no_did]" in out
    code, out = run(capsys, *base, "--kind", "praise", "--date", "2030-01-01")
    assert code == 2 and "[feedback.future_date]" in out
    code, out = run(capsys, *base, "--kind", "praise", "--id", "keep-titles-short")
    assert code == 0 and (brain.references / "feedback" / "keep-titles-short.md").exists()


def test_staged_check_ignores_unstaged_files(repo, brain, capsys):
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    add_correction(brain)
    code, out = run(capsys, "check", "--staged", "--project", str(repo))
    assert code == 0
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    code, out = run(capsys, "check", "--staged", "--project", str(repo))
    assert code == 3 and "feedback.undecided" in out


def test_stop_hook_names_the_brain_folder_for_its_fixes(brain):
    add_correction(brain)
    reason = hooks.stop({"stop_hook_active": False}, [brain])["reason"]
    assert f"--project {brain.root}" in reason
