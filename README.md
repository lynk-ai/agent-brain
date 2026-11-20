# agent-brain

`brain` keeps an agent's brain whole, and a team's brain. The brain is a skill folder in git. Its SKILL.md indexes the active rules and procedures, grouped by topic. Each rule and procedure links the feedback it came from, and that feedback stays in `references/` as evidence. The agent judges what a piece of feedback means. `brain` writes the records, keeps the links two-way, generates the index, and refuses a brain that is not whole.

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
brain install --project brains/help-center-writer        # the skill, for the harness running this command
brain hooks install --project brains/help-center-writer  # the pre-commit hook, and that harness's hooks
```

```text
brains/help-center-writer/
  brain.yaml                 format, name, team, warning periods, harness names the skill may not use
  help-center-writer/        THE SKILL: what a harness loads (install links to it)
    SKILL.md                 hand-written shell, the agent's job and limits from agent.md, and the rules index (both generated)
    agent.md                 job, lane (only with no team), anti-jobs, decider, roles, voice
    references/
      feedback/  rules/  procedures/  topics/  routines/
  harness/                   harness details, outside the skill
  reports/                   the dream's reports, outside the skill
```

## Create a team brain

A team brain holds what a team of agents shares: who is on the team, who owns which work, the policies every agent follows, and the routines the team runs. It lives in the same repository as its agents' brains. Each agent keeps its own brain, and every agent on a team must have one.

```sh
brain init acme-support --team --path brains/acme-support
brain team add brains/triage --project brains/acme-support
brain team add brains/writer --project brains/acme-support
brain check --all
```

```text
brains/acme-support/
  brain.yaml                 format: 2, kind: team, name, warning periods
  acme-support/              THE TEAM SKILL
    SKILL.md                 hand-written shell, and the roster and active policies (generated)
    references/
      agents/<agent>.md      name and source: the agent brain's folder, from the repository's top folder
      lanes.md               one table row per piece of work, with exactly one owner agent
      policies/  routines/  feedback/  topics/
  reports/
```

- `brain team add <path>` lists the agent, moves its `lane` rows from agent.md into lanes.md, moves each routine into the team brain as `<agent>-<id>`, named "<name> (<agent>)", and sets `team: <team>` in its brain.yaml. Commit both brains in one commit.
- An agent brain with `team:` holds no routine and no `lane`. Its SKILL.md copies its lane rows from the team's lanes.md. `brain index` on the team rewrites each agent's copy.
- A team routine runs a procedure in an agent's brain: `procedure: <agent>:<procedure-id>`. The team has no procedures of its own.
- A policy is a rule for the whole team, in `policies/`, with sections Policy, Why and How to apply. Its `feedback` is optional.

### Team feedback

The agent that hears feedback records it in its own brain, in the same turn. If the fix is a lane, a team policy or a routine, or the agent is in doubt, it points the record to the team: `brain feedback set <id> elsewhere --to brain:<team> --reason "<why>"`. If the fix is in another agent's brain, it points there: `--to brain:<agent>`. On a team, `brain:` names only the team or an agent on its roster.

The team's central agent takes each pointer in: `brain feedback add --intake-of brain:<agent>/<id> --project <team brain>` writes a team feedback record with `intake_of` set. It copies the person's words, who said them, where (`source`), the kind and the date from the agent's record. It then decides it like any feedback, and links it to the policy, routine or lanes it changes: `brain link <id> policies/<id>|routines/<id>|lanes`. Whoever can merge the team brain's repository decides. `brain check` on the team warns when a pointer waits more than `intake_days` (14) with no intake.

## Commands

| Command | What it does |
|---|---|
| `brain init <name>` | Creates the brain, its seeded procedures and topic, the dream routine and the pre-commit hook. `--display-name Mila` names the agent. `--no-seed` seeds no procedures. `--team` creates a team brain. |
| `brain feedback add` | Writes a feedback record at `disposition: new`. `--id` sets its file name. Refuses a future date, a correction or incident without `--did`, and text that looks like a secret or contact details. In a team brain, `--intake-of brain:<agent>/<id>` is required, and the agent's record fills what is not given. |
| `brain feedback set <id> <disposition> --reason` | Closes feedback as pending, one-off, elsewhere or declined, with the reason in Context. Elsewhere also takes `--to <kind>:<name>` (brain, plugin, book or doc), written to `kept_in`. |
| `brain feedback list [--pending]` | Lists feedback. |
| `brain new rule\|procedure\|topic\|routine <id>` | Writes a record at `status: proposed`. `--feedback`, `--topic` and `--rule` repeat and must exist. `--body-file <file or ->` gives its sections. In a team brain: `policy`, `routine` (`--owner`, `--procedure <agent>:<id>`) or `topic`. An agent brain in a team refuses `routine`. |
| `brain set-status <ref> proposed\|active\|paused\|retired` | Sets the status of a rule, procedure, policy or routine, and rewrites the index. A rule, procedure or policy is proposed, active or retired; a routine is active, paused or retired. Retiring needs `--reason`, which goes into Why, or Context for a procedure or routine. |
| `brain link <feedback> <rules/id\|procedures/id\|agent>` | Links both ways and marks the feedback kept. In a team brain: `policies/<id>`, `routines/<id>` or `lanes`. |
| `brain unlink <feedback> <record>` | Removes the link both ways. Feedback with no link left goes back to new. |
| `brain index` | Rewrites SKILL.md's generated blocks: the agent's job, lane, never list, approvals, roles, decider and voice from agent.md, then the index of active rules and procedures. In a team brain: the roster and the active policies, then each agent's lanes. |
| `brain check [--all] [--staged]` | Runs every check. `--all` checks every brain under the folder. `--staged` checks what git has staged. |
| `brain trace <ref>` | Shows a record, the feedback behind it and what uses it. |
| `brain status` | Counts, new and pending feedback, and proposed records. The dream starts here. |
| `brain install [--harness claude\|codex\|cursor] [--user]` or `--to <folder>` | Links the skill into the project's skills folder of the harness running the command (Claude Code: `.claude/skills`, Codex and Cursor: `.agents/skills`), or another harness, or the user's folder. `--copy` copies it, for a harness that cannot follow a link. Lists the other harnesses it supports, so the agent asks the person about them. Warns when the checkout is not on the default branch. |
| `brain plugin` | Writes the brain's `.claude-plugin/plugin.json`, its `source` in brain.yaml, and its line in the repository's `.claude-plugin/marketplace.json`. A team brain ships the same way. |
| `brain team add <path>` | In a team brain: lists the agent brain at `<path>` and moves its lanes and routines into the team. |
| `brain team remove <agent> --routine <id>=back\|retire\|<agent>` | In a team brain: takes the agent off the roster. Its lane rows go back to its agent.md. Each routine it owns needs one `--routine` choice. `back` returns it with its agent prefix and name suffix removed, and its status kept. |
| `brain hooks install [--harness claude\|codex\|cursor] [--dir <folder>]` | Installs the pre-commit hook, and the Stop hook (and SessionStart for Claude Code and Codex) of the harness running the command, or of each `--harness`. Lists the other harnesses it supports, so the agent asks the person about them. |

Every command takes `--project`, before or after the command (the brain's folder, its installed skill folder, or a folder inside it) and `--json`. The first line of the output is `<outcome>: <headline>`. Each finding is `<file>: <message> Fix: <fix> [<code>]`. The last line is `Next: <command>  (<why>)`. Exit codes: 0 ok, 3 failed or refused, 2 error.

## What `brain check` blocks

- Feedback that nobody decided (`new`), and pending, one-off, elsewhere or declined feedback with no reason.
- Kept feedback that names no record, elsewhere feedback that does not say where, and a rule with no feedback.
- A link that does not resolve, or that points only one way.
- A record with a missing or unknown field, a bad value, a missing body section, a bad file name or a duplicate name.
- A SKILL.md agent block or index that differs from what `brain index` writes. A retired or proposed record is never in the index.
- A SKILL.md whose front matter is not valid YAML (`skill.front_matter`).
- A SKILL.md that links feedback, has no description or one over 1,024 characters, has more than 500 lines, or whose name is not its folder's.
- A `TODO:` placeholder, a secret, contact details or a card number, a Markdown link that does not resolve, and a harness name from `brain.yaml` anywhere in the skill. URLs and code spans are not scanned for contact details.
- Feedback dated in the future.

In a team brain it also blocks: an agent entry whose source is not an agent brain in the repository with `team:` set to this team, a lanes.md owner not on the roster, the same work twice, a routine whose owner is not on the roster or whose procedure does not resolve, and team feedback whose `intake_of` does not resolve to an agent's record that points here. In an agent brain with `team:`, it blocks a routine, a `lane`, a team that is not in the repository or does not list the agent, and a `brain:` pointer outside the team.

It warns on a brain.yaml with no `format` (a format 1 brain: add `format: 2`), a brain with no take-feedback procedure, feedback pending past `pending_days`, an active rule not checked against its source within `checked_days`, and a SKILL.md over about 5,000 tokens. In a team brain it warns on an agent with no lane, a routine whose owner owns no lane or does not run its procedure, and a pointer to the team with no intake after `intake_days`.

A brain can change a check's level in `brain.yaml`:

```yaml
levels:
  core.harness_name: warn   # block, warn or off
```

## Finding codes

Each finding names its code in brackets. The codes are stable: `levels:` in brain.yaml, hooks and agents match on them.

- **Brain and config:** `brain.config`, `brain.not_found`, `brain.format_missing`, `brain.format_newer`, `brain.installed_copy`, `cli.two_projects`, `check.no_git`.
- **Records:** `record.bad_id`, `record.bad_value`, `record.duplicate_name`, `record.exists`, `record.missing_field`, `record.missing_section`, `record.not_found`, `record.not_markdown`, `record.unfinished`, `record.unknown_field`, `record.unknown_type`, `record.unreadable`, `agent.missing`, `agent.name`.
- **Links:** `link.broken`, `link.one_way`, `link.target`, `link.unresolved`.
- **Feedback:** `feedback.disposition`, `feedback.elsewhere_pointer`, `feedback.empty`, `feedback.future_date`, `feedback.intake_in_agent`, `feedback.kept_without_record`, `feedback.kind`, `feedback.linked`, `feedback.linked_not_kept`, `feedback.missing`, `feedback.no_did`, `feedback.no_reason`, `feedback.pending_too_long`, `feedback.pointer_not_elsewhere`, `feedback.undecided`, `feedback.use_link`.
- **Rules, procedures and status:** `rule.stale`, `rule.unchecked`, `procedure.no_take_feedback`, `status.no_reason`, `status.value`, `new.feedback`, `new.kind`, `new.routine_in_team`, `new.rule`, `new.topic`.
- **Skill and text:** `skill.agent_markers_missing`, `skill.agent_stale`, `skill.description`, `skill.front_matter`, `skill.index_stale`, `skill.lists_feedback`, `skill.markers_missing`, `skill.missing`, `skill.name`, `skill.size`, `skill.too_long`, `core.harness_name`, `data.personal`, `data.secret`, `data.sensitive`.
- **Team:** `team.agent_has_lane`, `team.agent_has_routine`, `team.agent_not_in_team`, `team.entry_name`, `team.no_repository`, `team.not_found`, `team.not_member`, `team.not_team`, `team.other_team`, `team.procedure_in_use`, `team.routine_choice`, `team.routine_exists`, `team.source_missing`.
- **Lanes:** `lanes.agent_without_lane`, `lanes.bad_table`, `lanes.bad_work`, `lanes.duplicate`, `lanes.missing`, `lanes.unknown_owner`.
- **Team routines:** `routine.bad_procedure`, `routine.owner_no_lane`, `routine.owner_not_runner`, `routine.unknown_owner`, `routine.unresolved_procedure`.
- **Intake:** `intake.bad_pointer`, `intake.missing`, `intake.not_pointed`, `intake.unresolved`.
- **Setup:** `init.bad_name`, `init.not_empty`, `init.team_options`, `install.exists`, `install.where`, `hooks.no_git`, `hooks.nothing`, `hooks.pre_commit_exists`, `plugin.drift`.

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
