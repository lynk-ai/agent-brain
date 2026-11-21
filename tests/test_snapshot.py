import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from agent_brain import snapshot
from test_load import crew, run, set_agent  # noqa: F401

COMMIT = ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q")


def git(folder, *args) -> str:
    return subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def cache(tmp_path_factory, monkeypatch) -> Path:
    folder = tmp_path_factory.mktemp("cache")
    monkeypatch.setenv("XDG_CACHE_HOME", str(folder))
    return folder / "brain" / "acme-support"


@pytest.fixture
def clone(crew, repo, cache, tmp_path_factory) -> Path:
    # The team's repository pushed to a remote, and a person's clone of it, as brain load meets it.
    git(repo, "add", "-A")
    git(repo, *COMMIT, "-m", "team")
    remote = tmp_path_factory.mktemp("remote") / "acme.git"
    git(repo, "clone", "-q", "--bare", str(repo), str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    folder = tmp_path_factory.mktemp("clone") / "acme"
    git(repo, "clone", "-q", str(remote), str(folder))
    return folder


def load(capsys, clone, *argv):
    code, out = run(capsys, "load", *argv, "--dry-run", "--json", "--project", str(clone / "brains" / "acme-support"))
    return code, json.loads(out)


def head(folder) -> str:
    return git(folder, "rev-parse", "HEAD")


def test_load_reads_a_snapshot_of_the_default_branch_and_names_its_commit(clone, cache, capsys):
    code, data = load(capsys, clone, "tara")
    folder = cache / head(clone)[:12]
    assert code == 0 and data["findings"] == []
    assert data["value"]["command"][:5] == ["claude", "--plugin-dir", str((folder / "brains" / "triage").resolve()), "--plugin-dir", str((folder / "brains" / "acme-support").resolve())]
    assert data["value"]["snapshot"] == {"ref": f"origin/{git(clone, 'branch', '--show-current')}", "commit": head(clone), "folder": str(folder)}
    assert (folder / ".brain-snapshot.yaml").is_file() and not os.access(folder / "brains" / "triage" / "triage" / "agent.md", os.W_OK)


def test_an_edit_not_committed_and_another_branch_never_reach_the_session(clone, cache, capsys):
    agent = clone / "brains" / "triage" / "triage" / "agent.md"
    git(clone, "switch", "-q", "-c", "draft")
    agent.write_text(agent.read_text().replace("display_name: Tara", "display_name: Tamar"))
    git(clone, *COMMIT, "-am", "rename on a branch")
    agent.write_text(agent.read_text() + "\nNot committed.\n")
    code, data = load(capsys, clone, "tara")
    assert code == 0 and data["value"]["agent"]["display_name"] == "Tara"
    loaded = Path(data["value"]["command"][2]) / "triage" / "agent.md"
    assert "Tamar" not in loaded.read_text() and "Not committed." not in loaded.read_text()


def test_a_merge_on_the_remote_reaches_the_next_load_and_no_fetch_keeps_the_last_one(clone, repo, cache, capsys):
    set_agent(repo, "triage", job="Sorts support tickets and escalations by urgency")
    git(repo, *COMMIT, "-am", "escalations")
    git(repo, "push", "-q", "origin", f"HEAD:{git(clone, 'branch', '--show-current')}")
    code, data = load(capsys, clone, "escalations", "--no-fetch")
    assert code == 2 and data["findings"][0]["code"] == "load.not_on_team"
    code, data = load(capsys, clone, "escalations")
    assert code == 0 and data["value"]["agent"]["name"] == "triage"
    assert str(cache / head(repo)[:12]) in data["value"]["command"][2]


def test_brain_refuses_to_write_in_a_snapshot_and_says_where_to_change_it(clone, cache, capsys):
    load(capsys, clone, "tara")
    triage = cache / head(clone)[:12] / "brains" / "triage"
    code, out = run(capsys, "feedback", "add", "--project", str(triage), "--name", "Good", "--from", "editor", "--kind", "praise", "--source", "review", "--text", "Good.")
    assert code != 0 and "[brain.snapshot]" in out and "on a branch" in out


def test_a_path_load_and_the_book_lists_are_in_the_snapshot(crew, repo, cache, tmp_path_factory, capsys):
    style = repo / "skills" / "style"
    style.mkdir(parents=True)
    (style / "SKILL.md").write_text("---\nname: style\ndescription: House style.\n---\nWrite plainly.\n")
    (repo / "books.txt").write_text("plain-words\n")
    (crew.root / "brain.yaml").write_text((crew.root / "brain.yaml").read_text() + "books:\n  lib: books.txt\n")
    set_agent(repo, "triage", skills=["acme-support", "./skills/style"], books=["lib:plain-words"])
    git(repo, "add", "-A")
    git(repo, *COMMIT, "-m", "team")
    remote = tmp_path_factory.mktemp("remote") / "acme.git"
    git(repo, "clone", "-q", "--bare", str(repo), str(remote))
    clone = tmp_path_factory.mktemp("clone") / "acme"
    git(repo, "clone", "-q", str(remote), str(clone))
    code, data = load(capsys, clone, "tara")
    folder = cache / head(clone)[:12]
    assert code == 0 and data["findings"] == []
    assert f"{(folder / 'skills' / 'style').resolve()}/SKILL.md" in data["value"]["instruction"]
    assert (folder / "books.txt").is_file()


def test_with_no_remote_the_working_folder_loads_with_a_warning(crew, repo, cache, capsys):
    code, out = run(capsys, "load", "tara", "--dry-run", "--json", "--project", str(crew.root))
    data = json.loads(out)
    assert code == 0 and [f["code"] for f in data["findings"]] == ["load.no_snapshot"]
    assert data["value"]["command"][2] == str((repo / "brains" / "triage").resolve())


def test_prune_keeps_the_newest_and_the_recent_snapshots(cache, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("BRAIN_CONFIG", str(tmp_path_factory.mktemp("settings") / "config.toml"))
    cache.mkdir(parents=True)
    now, day = time.time(), 86400
    # h is the current one. e and f fall outside the newest 5 but were used in the last 7 days.
    ages = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 20, "i": 30, "h": 0.5}
    for name, days in ages.items():
        (cache / name).mkdir()
        snapshot.used(cache / name).touch()
        os.utime(snapshot.used(cache / name), (now - days * day, now - days * day))
    snapshot.lock(cache / "i")
    removed = snapshot.prune(cache, cache / "h")
    assert sorted(p.name for p in removed) == ["g", "i"]
    assert sorted(p.name for p in cache.iterdir() if p.is_dir()) == ["a", "b", "c", "d", "e", "f", "h"]


def test_a_brain_at_the_repository_top_loads_from_its_snapshot(tmp_path_factory, cache, capsys, monkeypatch):
    from conftest import fill
    from agent_brain import scaffold

    monkeypatch.setenv("BRAIN_CONFIG", str(tmp_path_factory.mktemp("settings") / "config.toml"))
    top = tmp_path_factory.mktemp("solo") / "solo"
    brain = scaffold.init(top, "solo")
    fill(brain)
    (top / "src").mkdir()
    (top / "src" / "app.py").write_text("print('the rest of the repository')\n")
    git(top, "add", "-A")
    git(top, *COMMIT, "-m", "solo")
    remote = tmp_path_factory.mktemp("remote") / "solo.git"
    git(top, "clone", "-q", "--bare", str(top), str(remote))
    clone = tmp_path_factory.mktemp("clone") / "solo"
    git(top, "clone", "-q", str(remote), str(clone))
    code, out = run(capsys, "load", "--dry-run", "--json", "--project", str(clone))
    data = json.loads(out)
    assert code == 0, out
    assert data["value"]["snapshot"]["commit"] == head(clone)
    folder = cache.parent / "solo" / head(clone)[:12]
    assert data["value"]["command"][2] == str(folder.resolve())
    assert (folder / "solo" / "SKILL.md").is_file() and not (folder / "src").exists()
