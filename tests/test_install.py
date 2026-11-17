import json
import subprocess

import pytest

from agent_brain import hooks, plugin, scaffold
from agent_brain.brain import find, require_writable
from agent_brain.output import BrainError

from conftest import add_correction


def with_remote(repo):
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "git@github.com:acme/brains.git"], check=True)


def test_plugin_writes_plugin_json_source_and_marketplace_entry(repo, brain):
    with_remote(repo)
    market = repo / ".claude-plugin" / "marketplace.json"
    market.parent.mkdir()
    market.write_text(json.dumps({"name": "acme", "plugins": [{"name": "other", "source": "./x"}]}))
    plugin.write(brain)
    data = json.loads((brain.root / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "help-center-writer" and data["skills"] == "./"
    entries = {p["name"]: p for p in json.loads(market.read_text())["plugins"]}
    assert entries["help-center-writer"]["source"] == "./brains/hcw" and "other" in entries
    assert find(brain.root).config["source"] == {"repo": "https://github.com/acme/brains", "path": "brains/hcw"}
    assert [f for f in __import__("agent_brain").checks.run(find(brain.root)) if f.code == "plugin.drift"] == []


def test_a_changed_description_makes_the_plugin_drift(repo, brain):
    plugin.write(brain)
    brain.skill_file.write_text(brain.skill_file.read_text().replace("Use when drafting", "Use when writing"))
    from agent_brain import checks

    assert "plugin.drift" in [f.code for f in checks.run(brain)]


def test_a_copy_is_read_only_and_names_the_clone(repo, brain, tmp_path):
    with_remote(repo)
    plugin.write(brain)
    target, _ = plugin.install(find(brain.root), None, tmp_path / "skills", copy=True)
    copy = find(target)
    assert copy.copy and copy.name == "help-center-writer"
    with pytest.raises(BrainError) as exc:
        require_writable(copy)
    assert exc.value.finding.code == "brain.installed_copy"
    assert "git clone https://github.com/acme/brains" in exc.value.finding.fix
    plugin.install(find(brain.root), None, tmp_path / "skills", copy=True)


def test_a_plugin_cache_copy_outside_git_is_read_only(repo, brain, tmp_path_factory):
    import shutil

    with_remote(repo)
    plugin.write(brain)
    cache = tmp_path_factory.mktemp("plugin-cache") / "hcw"
    shutil.copytree(brain.root, cache)
    with pytest.raises(BrainError):
        require_writable(find(cache))
    require_writable(find(brain.root))


def test_install_warns_off_the_default_branch(repo, brain, tmp_path):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", "--allow-empty"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "lesson"], check=True)
    _, warnings = plugin.install(brain, None, tmp_path / "skills", copy=False)
    assert warnings and "lesson" in warnings[0]


@pytest.mark.parametrize("host,file,event", [("codex", ".codex/hooks.json", "Stop"), ("cursor", ".cursor/hooks.json", "stop")])
def test_codex_and_cursor_hooks(brain, tmp_path, host, file, event):
    work = tmp_path / "work"
    (work / file).parent.mkdir(parents=True)
    (work / file).parent.joinpath(".gitignore").write_text("other\n")
    hooks.install_host(host, work, brain.root)
    hooks.install_host(host, work, brain.root)
    data = json.loads((work / file).read_text())
    entries = data["hooks"][event]
    assert len(entries) == 1
    assert (work / file).parent.joinpath(".gitignore").read_text() == f"other\nhooks.json\n"
    add_correction(brain)
    if host == "cursor":
        assert "followup_message" in hooks.stop({"status": "completed", "loop_count": 0}, [brain], host)
        assert hooks.stop({"status": "completed", "loop_count": 1}, [brain], host) is None
    else:
        assert hooks.stop({"stop_hook_active": False}, [brain], host)["decision"] == "block"


def test_team_init_seeds_no_routine(repo):
    brain = scaffold.init(repo / "t", "team-agent", team=True)
    assert not list((brain.references / "routines").glob("*.md"))
    assert (brain.references / "procedures" / "run-the-dream.md").exists()
