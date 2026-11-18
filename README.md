# agent-brain

`brain` keeps an agent's brain whole. The brain is a skill folder in git. Its SKILL.md indexes the active rules and procedures, grouped by topic. Each rule and procedure links the feedback it came from, and that feedback stays in `references/` as evidence. The agent judges what a piece of feedback means. `brain` writes the records, keeps the links two-way, generates the index, and refuses a brain that is not whole.

## Install

```sh
uv tool install git+https://github.com/lynk-ai/agent-brain
brain version
```

From a local checkout: `uv tool install --editable .`

## Create a brain

A brain is a folder with a `brain.yaml`. One repository can hold one brain or many.

```sh
brain init help-center-writer --path brains/help-center-writer
brain check --project brains/help-center-writer   # fill each TODO: it reports
brain install --project brains/help-center-writer --harness claude
brain hooks install --project brains/help-center-writer --claude ~/code/docs-site
```

```text
brains/help-center-writer/
  brain.yaml                 name, warning periods, harness names the skill may not use
  help-center-writer/        THE SKILL: what a harness loads (install links to it)
    SKILL.md                 hand-written shell, and a generated index between markers
    agent.md                 job, lane, anti-jobs, decider, roles, voice
    references/
      feedback/  rules/  procedures/  topics/  routines/
  harness/                   harness details, outside the skill
  reports/                   the dream's reports, outside the skill
```

## Commands

| Command | What it does |
|---|---|
| `brain init <name>` | Creates the brain, its seeded procedures and topic, the dream routine and the pre-commit hook. `--display-name Mila` names the agent. `--no-seed` seeds no procedures. |
| `brain feedback add` | Writes a feedback record at `disposition: new`. `--id` sets its file name. Refuses a future date, a correction or incident without `--did`, and text that looks like a secret or contact details. |
| `brain feedback set <id> <disposition> --reason` | Closes feedback as pending, one-off, elsewhere or declined, with the reason in Context. Elsewhere also takes `--to <kind>:<name>` (brain, plugin, book or doc), written to `kept_in`. |
| `brain feedback list [--pending]` | Lists feedback. |
| `brain new rule\|procedure\|topic\|routine <id>` | Writes a record at `status: proposed`. `--feedback`, `--topic` and `--rule` repeat and must exist. `--body-file <file or ->` gives its sections. |
| `brain set-status <ref> proposed\|active\|retired` | Sets the status and rewrites the index. Retiring needs `--reason`, which goes into Why. |
| `brain link <feedback> <rules/id\|procedures/id\|agent>` | Links both ways and marks the feedback kept. |
| `brain unlink <feedback> <record>` | Removes the link both ways. Feedback with no link left goes back to new. |
| `brain index` | Rewrites the SKILL.md index from the active rules and procedures. |
| `brain check [--all] [--staged]` | Runs every check. `--all` checks every brain under the folder. `--staged` checks what git has staged. |
| `brain trace <ref>` | Shows a record, the feedback behind it and what uses it. |
| `brain status` | Counts, new and pending feedback, and proposed records. The dream starts here. |
| `brain install --harness claude\|codex\|cursor\|agents` or `--to <folder>` | Links the skill into a harness's skills folder. `--copy` copies it, for a harness that cannot follow a link. Warns when the checkout is not on the default branch. |
| `brain plugin` | Writes the brain's `.claude-plugin/plugin.json`, its `source` in brain.yaml, and its line in the repository's `.claude-plugin/marketplace.json`. |
| `brain import darkmatter <brain> --into <folder>` | Imports a darkmatter agent brain. `--agent` takes the agent's doc, `--rename OLD=NEW` renames a record, `--sibling 'lynk-*-playbook'` rewrites paths into brains that move with it. Reports every dropped field and every gap. |
| `brain hooks install [--claude\|--codex\|--cursor <folder>]` | Installs the pre-commit hook, and each harness's Stop hook (and SessionStart for Claude Code and Codex). |

Every command takes `--project`, before or after the command (the brain's folder, its installed skill folder, or a folder inside it) and `--json`. The first line of the output is `<outcome>: <headline>`. Each finding is `<file>: <message> Fix: <fix> [<code>]`. The last line is `Next: <command>  (<why>)`. Exit codes: 0 ok, 3 failed or refused, 2 error.

## What `brain check` blocks

- Feedback that nobody decided (`new`), and pending, one-off, elsewhere or declined feedback with no reason.
- Kept feedback that names no record, elsewhere feedback that does not say where, and a rule with no feedback.
- A link that does not resolve, or that points only one way.
- A record with a missing or unknown field, a bad value, a missing body section, a bad file name or a duplicate name.
- A SKILL.md index that differs from what `brain index` writes. A retired or proposed record is never in the index.
- A SKILL.md that links feedback, has no description or one over 1,024 characters, has more than 500 lines, or whose name is not its folder's.
- A `TODO:` placeholder, a secret, contact details or a card number, a Markdown link that does not resolve, and a harness name from `brain.yaml` anywhere in the skill. URLs and code spans are not scanned for contact details.
- Feedback dated in the future.

It warns on a brain with no take-feedback procedure, feedback pending past `pending_days`, an active rule not checked against its source within `checked_days`, and a SKILL.md over about 5,000 tokens.

A brain can change a check's level in `brain.yaml`:

```yaml
levels:
  core.harness_name: warn   # block, warn or off
```

## When the checks run

- **The agent's procedures** run `brain check` after each change. Take a piece of feedback is the first procedure in every index.
- **The pre-commit hook** runs `brain check --staged` on what the commit holds, for every brain in the repository. A commit with a broken brain fails.
- **The Claude Code Stop hook** runs the checks at the end of each turn. On a block finding it sends the agent back to fix it, once per turn. So feedback written in a turn is decided in that turn.
- **The Claude Code SessionStart hook** tells the agent how much feedback waits and how many records are proposed.

A script cannot see feedback that the agent never wrote down. Only the take-feedback procedure covers that.

## Share a brain with a team

A brain in a repository with a Claude Code marketplace is a plugin: `brain plugin` lists it, and anyone installs it with `/plugin install <name>@<marketplace>`. In any other harness, clone the repository and run `brain install --harness <harness>`, or `--copy` where a link does not work.

An installed copy is read-only. A change there never reaches the repository, so `brain` refuses it and prints how to clone the repository. Feedback then arrives as a pull request.

## Run the checks in CI

```yaml
# .github/workflows/brains.yml
on: [push, pull_request]
jobs:
  brains:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv tool install git+https://github.com/lynk-ai/agent-brain
      - run: brain check --all
```

## Develop

```sh
uv venv && uv pip install -e . pytest
.venv/bin/pytest -q
```
