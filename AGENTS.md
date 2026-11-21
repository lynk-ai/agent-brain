# AGENTS.md

`brain` is a small CLI that keeps an agent's brain, a skill folder in git, whole, and a team's brain. It follows the books "Create an agent with its own brain" and "Build and run an agent team".

## Where things are
- `src/agent_brain/brain.py`: brain.yaml: `format` (this CLI writes 2, reads 1 as 2, refuses newer), `kind` (agent or team), `team`.
- `src/agent_brain/records.py`: the record types as hard-coded field specs: an agent brain's (`KINDS`) and a team brain's (`TEAM_KINDS`, plus lanes.md). There is no schema language.
- `src/agent_brain/team.py`: everything that crosses brains: the team checks, the lanes table, `team add` and `team remove`.
- `src/agent_brain/snapshot.py`: `brain load`'s read-only snapshot of the team repository's default branch, one per commit in the cache folder, and its cleanup.
- `src/agent_brain/load.py`: `brain team` and `brain load`: finding the team brain, matching an agent, the freshness check and the one fixed session instruction. The load checks are in `team.py` (`check_loads`), shared with `brain check`.
- `src/agent_brain/harness.py`: `NAMES`, the harnesses brain installs into, hooks and detects, and `KNOWN`, every harness an agent.md may name (adds Grok Bot).
- `src/agent_brain/adapters.py`: the harness adapters `brain load` starts: the exact command for Claude Code and Codex.
- `src/agent_brain/settings.py`: the one user setting, the saved path of a team brain or one agent brain (`brain use`). `BRAIN_CONFIG` names another file, for tests.
- `src/agent_brain/checks.py`: every check. Each returns findings, and none writes a file.
- `src/agent_brain/index.py`: SKILL.md, generated whole: the opening, agent and index blocks between their markers. Only the front matter is hand-written.
- `src/agent_brain/scaffold.py`: everything that writes: init, feedback, new records, link, unlink, install.
- `src/agent_brain/hooks.py`: the git pre-commit hook and the Claude Code Stop and SessionStart hooks.
- `src/agent_brain/templates/`: what `brain init` seeds. The procedures are adapted from the book.

## Rules
- The agent judges what a piece of feedback means. The CLI writes records and links, and checks. Never add judgment to the CLI.
- The skill ships Markdown only. The CLI is installed on its own and never copied into a brain.
- Finding codes are stable. Hooks, tests and agents match on them.
- A new check comes with a test that plants a record that fails it.
- Seeded templates must pass `brain check` once agent.md and the description are filled in: no `TODO:` text and no harness names in them.
- A team brain and its agents' brains are in one repository. Every link between them is a path or a name checked offline, also in `check --staged`, which has no `.git`: pass the top folder as `repo`.
- A change to brain.yaml's meaning raises `FORMAT` in `brain.py`. An older format blocks in `brain check` with a fix that says what to move (`brain.format_old`).

## Commands
- Test: `.venv/bin/pytest -q`
- Install for local use: `uv tool install --editable .`
