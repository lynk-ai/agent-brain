import json
import shutil
import subprocess
from pathlib import Path

import yaml

from .brain import COPY_MARKER, CONFIG_FILE, Brain
from .output import BrainError, Finding
from .records import split_front_matter

PLUGIN_FILE = Path(".claude-plugin") / "plugin.json"
MARKETPLACE_FILE = Path(".claude-plugin") / "marketplace.json"
# Codex reads a plugin.json at the plugin's root and its own marketplace under .agents/plugins/.
CODEX_PLUGIN_FILE = Path("plugin.json")
CODEX_MARKETPLACE_FILE = Path(".agents") / "plugins" / "marketplace.json"
# Claude Code reads its own folder. Codex and Cursor read the neutral Agent Skills folder, and Cursor reads both.
HARNESS_SKILLS = {"claude": Path("~/.claude/skills"), "codex": Path("~/.agents/skills"), "cursor": Path("~/.agents/skills"), "agents": Path("~/.agents/skills")}


def git(folder: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def skill_meta(brain: Brain) -> dict:
    meta, _ = split_front_matter(brain.skill_file.read_text()) if brain.skill_file.is_file() else (None, "")
    return meta or {}


def https_url(remote: str) -> str:
    if remote.startswith("git@") and ":" in remote:
        host, _, path = remote[4:].partition(":")
        remote = f"https://{host}/{path}"
    return remote.removesuffix(".git")


def source_of(brain: Brain) -> dict | None:
    top = git(brain.root, "rev-parse", "--show-toplevel")
    remote = git(brain.root, "remote", "get-url", "origin")
    if not top or not remote:
        return None
    path = brain.root.resolve().relative_to(Path(top).resolve())
    return {"repo": https_url(remote), "path": str(path)}


def ensure_source(brain: Brain) -> dict | None:
    source = brain.config.get("source") or source_of(brain)
    config_path = brain.root / CONFIG_FILE
    if source and "source" not in yaml.safe_load(config_path.read_text()):
        # Appended, not re-dumped, so the file keeps its comments.
        text = config_path.read_text().rstrip("\n")
        config_path.write_text(f"{text}\n# Where the brain lives, so an installed copy can send changes back to it.\nsource:\n  repo: {source['repo']}\n  path: {source['path']}\n")
    return source


def marketplace_of(brain: Brain) -> Path | None:
    top = git(brain.root, "rev-parse", "--show-toplevel")
    if top and (Path(top) / MARKETPLACE_FILE).is_file():
        return Path(top) / MARKETPLACE_FILE
    return None


def codex_marketplace_of(brain: Brain) -> Path | None:
    top = git(brain.root, "rev-parse", "--show-toplevel")
    if top and (Path(top) / CODEX_MARKETPLACE_FILE).is_file():
        return Path(top) / CODEX_MARKETPLACE_FILE
    return None


def plugin_entry(brain: Brain, marketplace: Path) -> dict:
    meta = skill_meta(brain)
    rel = brain.root.resolve().relative_to(marketplace.parent.parent.resolve())
    return {"name": brain.name, "source": f"./{rel}", "description": meta.get("description", "")}


def write(brain: Brain) -> list[str]:
    meta = skill_meta(brain)
    if not meta.get("description"):
        raise BrainError(Finding("skill.description", brain.rel(brain.skill_file), "SKILL.md has no description.", "Write the description first."))
    lines = []
    for relative in (PLUGIN_FILE, CODEX_PLUGIN_FILE):
        plugin_path = brain.root / relative
        plugin_path.parent.mkdir(exist_ok=True)
        plugin = json.loads(plugin_path.read_text()) if plugin_path.is_file() else {}
        plugin.update({"name": brain.name, "description": meta["description"], "skills": "./"})
        plugin_path.write_text(json.dumps(plugin, indent=2) + "\n")
        lines.append(f"  plugin: {plugin_path}")
    source = ensure_source(brain)
    lines.append(f"  source: {source['repo']} {source['path']}" if source else "  source: none (no git remote named origin)")
    codex = codex_marketplace_of(brain)
    if codex is not None:
        data = json.loads(codex.read_text())
        rel = f"./{brain.root.resolve().relative_to(codex.parent.parent.parent.resolve())}"
        for existing in data.setdefault("plugins", []):
            if existing.get("name") == brain.name:
                existing.setdefault("source", {})["path"] = rel
                break
        else:
            data["plugins"].append({"name": brain.name, "source": {"source": "local", "path": rel}})
        codex.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        lines.append(f"  Codex marketplace: {codex}")
    marketplace = marketplace_of(brain)
    if marketplace is None:
        lines.append(f"  marketplace: none found at the repository's {MARKETPLACE_FILE}; nothing listed")
        return lines
    data = json.loads(marketplace.read_text())
    plugins = data.setdefault("plugins", [])
    entry = plugin_entry(brain, marketplace)
    for existing in plugins:
        if existing.get("name") == brain.name:
            existing.update(entry)
            break
    else:
        plugins.append(entry)
    marketplace.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    lines.append(f"  marketplace: {marketplace}")
    return lines


def drift(brain: Brain) -> list[Finding]:
    findings = []
    plugin_path = brain.root / PLUGIN_FILE
    if not plugin_path.is_file():
        return findings
    meta = skill_meta(brain)
    for relative in (PLUGIN_FILE, CODEX_PLUGIN_FILE):
        path = brain.root / relative
        plugin = json.loads(path.read_text()) if path.is_file() else {}
        if plugin.get("name") != brain.name or plugin.get("description") != meta.get("description") or plugin.get("skills") != "./":
            findings.append(Finding("plugin.drift", brain.rel(path), f"{relative} does not match the brain's name, description or skill folder.", "Run brain plugin."))
    codex = codex_marketplace_of(brain)
    if codex is not None:
        rel = f"./{brain.root.resolve().relative_to(codex.parent.parent.parent.resolve())}"
        listed = next((p for p in json.loads(codex.read_text()).get("plugins", []) if p.get("name") == brain.name), None)
        if listed is not None and (listed.get("source") or {}).get("path") != rel:
            findings.append(Finding("plugin.drift", str(codex), f"The Codex marketplace entry for {brain.name} does not point at the brain.", "Run brain plugin."))
    marketplace = marketplace_of(brain)
    if marketplace is not None:
        listed = next((p for p in json.loads(marketplace.read_text()).get("plugins", []) if p.get("name") == brain.name), None)
        expected = plugin_entry(brain, marketplace)
        if listed is None or listed.get("source") != expected["source"] or listed.get("description") != expected["description"]:
            findings.append(Finding("plugin.drift", str(marketplace), f"The marketplace entry for {brain.name} does not match the brain.", "Run brain plugin."))
    return findings


def install(brain: Brain, harness: str | None, to: Path | None, copy: bool) -> tuple[Path, list[str]]:
    if bool(harness) == bool(to):
        raise BrainError(Finding("install.where", "install", "Name one place: --harness or --to.", f"Use --harness {'|'.join(HARNESS_SKILLS)}, or --to <skills folder>."), outcome="error")
    folder = (HARNESS_SKILLS[harness] if harness else to).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / brain.name
    warnings = []
    if copy:
        if target.exists() or target.is_symlink():
            if not (target / COPY_MARKER).is_file():
                raise BrainError(Finding("install.exists", str(target), "Something that is not a copy of this brain is already there.", "Remove it, or choose another place."))
            shutil.rmtree(target)
        shutil.copytree(brain.skill_dir, target)
        marker = {"name": brain.name, "commit": git(brain.root, "rev-parse", "HEAD"), "config": {k: v for k, v in brain.config.items()}}
        (target / COPY_MARKER).write_text(yaml.safe_dump(marker, sort_keys=False))
        warnings.append("  This is a copy: run brain install --copy again to update it, and give feedback in a clone of the brain's repository.")
        return target, warnings
    if target.is_symlink() and target.resolve() == brain.skill_dir.resolve():
        pass
    elif target.exists() or target.is_symlink():
        raise BrainError(Finding("install.exists", str(target), "Something else is already there.", "Remove it, or choose another place."))
    else:
        target.symlink_to(brain.skill_dir.resolve(), target_is_directory=True)
    branch = git(brain.root, "rev-parse", "--abbrev-ref", "HEAD")
    default = (git(brain.root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or "origin/main").removeprefix("origin/")
    if branch and branch != default:
        warnings.append(f"  warning: the checkout is on {branch}, not {default}. The link loads its unmerged changes. Install from a checkout that stays on {default}, and change the brain in a worktree.")
    return target, warnings
