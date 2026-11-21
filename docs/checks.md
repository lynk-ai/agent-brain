# Checks

`brain check` keeps a brain whole. This page says when it runs, how to read a finding, what to do when one fails, and how to run it in CI. The full list of what it checks is in the [reference](reference.md#what-brain-check-checks), and every code is in [findings.md](findings.md).

## When the checks run

- **By the agent.** Its procedures run `brain check` after each change.
- **On every commit.** The pre-commit hook, which `brain init` installs, runs `brain check --staged` on every brain in the staged tree. A commit with a broken brain fails.
- **At the end of each agent turn.** `brain hooks install` adds a Stop hook to the harness. On a block finding, it sends the agent back to fix it, at most once per turn, with up to 20 findings. So feedback written in a turn is decided in that turn.
- **At the start of a session.** In Claude Code and Codex, a SessionStart hook tells the agent how much feedback waits and how many records are proposed.
- **In CI,** when you add it: see [below](#run-the-checks-in-ci).

```sh
brain hooks install --project brains/support-writer --harness claude
```

| Harness | Hook file | Events |
|---|---|---|
| Claude Code | `.claude/settings.local.json` | Stop and SessionStart |
| Codex | `.codex/hooks.json` | Stop and SessionStart |
| Cursor | `.cursor/hooks.json` | stop |

The hook files hold paths from your machine, so `brain` keeps them out of git with a `.gitignore` next to each. Each person runs `brain hooks install` once.

## Read a finding

```text
failed: 1 block and 0 warn findings in support-writer.
  block support-writer/references/feedback/2026-11-21-never-promise-a-refund-date.md: Nobody decided it yet. Fix: Decide it in this turn: brain link 2026-11-21-never-promise-a-refund-date <record>, brain new rule <id> --feedback 2026-11-21-never-promise-a-refund-date, or brain feedback set 2026-11-21-never-promise-a-refund-date <disposition> --reason. [feedback.undecided]
Next: brain check  (after you apply each Fix)
```

Each finding has 5 parts: its level, the file and line, what is wrong, how to fix it, and its code in brackets.

- **block:** `brain check` fails with exit 3, and the commit fails.
- **warn:** it is reported, and nothing fails.

## When a check fails

1. Apply the fix the finding names, then run `brain check` again.
2. If the fix is not clear, look up the code in [findings.md](findings.md).
3. If a commit fails, fix the brain and commit again. Never skip the hook: a brain that fails the check would reach every agent that loads it.

These codes need one more step:

| Code | What it means | What to do |
|---|---|---|
| `skill.agent_stale`, `skill.index_stale` | SKILL.md differs from agent.md or from the active records. | Run `brain index`. |
| `skill.hand_written` | SKILL.md has hand-written text outside its front matter. | Move the text into agent.md, a rule, a procedure or the team's lanes, then run `brain index --replace`. |
| `brain.installed_copy`, `brain.snapshot` | You are in a read-only copy. | Change the brain on a branch in its repository, and open a pull request. |
| `brain.format_old` | The brain was written for an older `brain`. | Do what its fix says, then run `brain index --replace`. |
| `brain.format_newer` | Your `brain` is older than the brain. | Upgrade `brain`: see [Format and upgrades](reference.md#format-and-upgrades). |
| `plugin.drift` | The plugin files differ from the brain. | Run `brain plugin`. |

## Change a check's level

A brain can set a code's level in its brain.yaml:

```yaml
levels:
  core.harness_name: warn   # block, warn or off
```

Change a level only when the check does not fit this brain, and write the reason in a comment. Never change one to make a failing brain pass.

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
      - run: uv tool install 'agent-brain @ git+https://github.com/lynk-ai/agent-brain@v0.5.1'
      - run: brain check --all
```

Pin the same tag your team installs. Upgrade CI in the same change as your machines when a release changes the format.
