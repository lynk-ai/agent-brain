# AGENTS.md

`brain` is a small CLI that keeps an agent's brain, a skill folder in git, whole. It follows the book "Create an agent with its own brain". It is a much smaller relative of darkmatter.

## Where things are
- `src/agent_brain/records.py`: the 4 record types, routines and agent.md, as hard-coded field specs. There is no schema language.
- `src/agent_brain/checks.py`: every check. Each returns findings, and none writes a file.
- `src/agent_brain/index.py`: the generated SKILL.md index between the markers.
- `src/agent_brain/scaffold.py`: everything that writes: init, feedback, new records, link, unlink, install.
- `src/agent_brain/hooks.py`: the git pre-commit hook and the Claude Code Stop and SessionStart hooks.
- `src/agent_brain/templates/`: what `brain init` seeds. The procedures are adapted from the book.

## Rules
- The agent judges what a piece of feedback means. The CLI writes records and links, and checks. Never add judgment to the CLI.
- The skill ships Markdown only. The CLI is installed on its own and never copied into a brain.
- Finding codes are stable. Hooks, tests and agents match on them.
- A new check comes with a test that plants a record that fails it.
- Seeded templates must pass `brain check` once agent.md and the description are filled in: no `TODO:` text and no harness names in them.

## Commands
- Test: `.venv/bin/pytest -q`
- Install for local use: `uv tool install --editable .`
