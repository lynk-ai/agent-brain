# agent-brain

**Agents forget corrections.** You fix an agent today, and tomorrow it makes the same mistake, because the fix lived in one chat.

`brain` gives each agent a brain that keeps what it learned. Every correction becomes a rule the agent loads in every session. Every rule traces back to who taught it, when and why. A check refuses a brain that drifts: a rule with no source, a correction nobody decided, or a link that points nowhere.

It is for anyone who runs coding agents, such as Claude Code, Codex or Cursor, alone or as a team. The brain is plain Markdown in git, so you review it like code, and it works in any harness.

## What you get

- **An agent that learns.** A correction becomes a rule once, and every later session follows it.
- **A trail for every rule.** `brain trace` shows who taught a rule, their exact words and the date.
- **A brain that stays whole.** `brain check` runs on every commit and at the end of every agent turn, and blocks a broken brain.
- **Teams of agents.** Each agent keeps its own brain. A team brain holds who owns which work and the policies everyone follows. `brain load` starts any agent from the team's merged brain.

## How it works

```text
a person corrects the agent
  -> the agent records it, in the person's own words          brain feedback add
  -> it becomes a rule or a procedure, linked to that record   brain new rule
  -> the decider approves, and the rule goes active            brain set-status
  -> SKILL.md lists it, so every session loads it               (brain set-status rewrites it)
  -> a check keeps every link and decision whole                brain check
```

You edit `agent.md`, the agent's record. `brain` writes `SKILL.md`, the file the agent's harness loads, from agent.md and the active rules. The agent reads SKILL.md when its work calls for the skill, or at the start of a session that `brain load` starts. It opens a rule's file only when a task needs it.

## Quick start

You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/) and git.

```sh
uv tool install 'agent-brain @ git+https://github.com/lynk-ai/agent-brain@v0.5.1'
brain init support-writer --display-name Mila --path brains/support-writer
# fill in brains/support-writer/support-writer/agent.md and the description in SKILL.md
brain index --project brains/support-writer
brain check --project brains/support-writer
brain install --project brains/support-writer --harness claude
brain hooks install --project brains/support-writer --harness claude
```

The next Claude Code session in this project can use Mila's brain, and checks it at the end of every turn. [Getting started](docs/getting-started.md) walks through every step, then teaches the agent its first rule.

## Documentation

| Page | Read it to |
|---|---|
| [Concepts](docs/concepts.md) | Learn the words, what you edit, what `brain` writes, and when a change reaches the agent. |
| [Getting started](docs/getting-started.md) | Build one agent's brain end to end, and turn a correction into a rule. |
| [Loading a brain](docs/loading.md) | Choose how a brain reaches a session, where it is read from, and what the agent reads during the session. |
| [Teams](docs/teams.md) | Run a team of agents: the team brain, lanes, team feedback and `brain load`. |
| [Checks](docs/checks.md) | Know when the checks run, what to do when one fails, and how to run them in CI. |
| [Reference](docs/reference.md) | Look up every command and flag, the files and their fields, the configuration, the output and exit codes. |
| [Finding codes](docs/findings.md) | Look up a finding's code: its level, its message and its fix. |

## Install and upgrade brain

```sh
uv tool install 'agent-brain @ git+https://github.com/lynk-ai/agent-brain@v0.5.1'
brain version
```

```text
ok: brain 0.5.1, Python 3.12.15.
```

Each release of the `brain` tool is a git tag. To upgrade, run the same command with the new tag and `--force`. A release that changes the file format needs every machine that checks or loads the brain to upgrade together: see [Format and upgrades](docs/reference.md#format-and-upgrades).

## Develop

```sh
uv run pytest -q
python tools/findings_doc.py    # after changing a finding: rewrites docs/findings.md
```

The tests also fail when `docs/findings.md` differs from the code, or when a command or flag is missing from `docs/reference.md`.
