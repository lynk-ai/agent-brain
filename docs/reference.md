# brain reference

The [README](../README.md) explains what `brain` is and walks through it. This page holds the exact behavior: every command and flag, the output, the files, the configuration, `brain load`, the hooks and the formats. The finding codes are in [findings.md](findings.md).

## Common options and output

Every command takes:

- `--project <folder>`: the brain's folder, its installed skill folder, or a folder inside it. It goes before or after the command. Without it, `brain` uses the current folder.
- `--json`: print one JSON object in place of the text.

### Text output

```text
<outcome>: <headline>
  <lines>
  <level> <file>[:<line>]: <message> Fix: <fix> [<code>]
Next: <command>  (<why>)
```

`<outcome>` is `ok`, `failed`, `refused` or `error`. `<level>` is `block` or `warn`. The `Next:` line names the next command to run, when there is one.

### JSON output

```json
{
  "command": "check",
  "outcome": "failed",
  "ok": false,
  "headline": "1 block and 0 warn findings in support-writer.",
  "findings": [{"code": "feedback.undecided", "file": "...", "message": "...", "fix": "...", "level": "block"}],
  "value": null,
  "next": {"command": "brain check", "why": "after you apply each Fix"}
}
```

`value` holds the command's data, such as the agent and command for `brain load`, or the counts for `brain status`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | ok. Warnings alone exit 0. |
| 3 | failed or refused: a block finding, or a command that refused to act. |
| 2 | error: a usage error, or a command that could not run. |
| 130 | stopped with Ctrl-C. |

`brain hook stop` and `brain hook start`, which the harness hooks run, always exit 0. `brain load` replaces itself with the harness, so its exit code is the harness's. It prints its status to stderr.

## Commands

### brain init

```text
brain init <name> [--path <folder>] [--display-name <name>] [--no-seed] [--no-git] [--team]
```

Creates a brain in `<folder>` (default `./<name>`): brain.yaml, the skill folder `<name>/` with SKILL.md, agent.md and `references/`, 7 seeded procedures, 2 topics (`upkeep`, `working-with-others`) and the `nightly-dream` routine. It runs `git init` in the folder when it is outside a repository, and installs the pre-commit hook. The name is lowercase letters, digits and single hyphens, at most 64 characters.

- `--display-name`: what the agent is called, such as Mila. Default: the name.
- `--no-seed`: no procedures, topics or routine. The brain then needs its own take-feedback procedure.
- `--no-git`: no `git init` and no pre-commit hook.
- `--team`: create a team brain: brain.yaml with `agents: []`, the team skill, `lanes.md` and one topic. It takes no `--no-seed` or `--display-name`.

In a repository whose team brain sets `domain:`, it notes the name an agent brain there should have.

### brain feedback add

```text
brain feedback add --name <one sentence> --from <person> --kind <kind> --source <where> [--did <what the agent did>]
                   [--text <words>] [--context <text>] [--date YYYY-MM-DD] [--id <file name>] [--intake-of brain:<agent>/<id>]
```

Writes a feedback record at `disposition: new`, in `references/feedback/<id>.md`.

- `--name`, `--from`, `--kind` and `--source` are required in an agent brain.
- `--kind`: `correction`, `preference`, `approval`, `incident` or `praise`.
- `--did`: what the agent had done. Required for a correction or an incident.
- `--text`: the words as said. Read from stdin when left out.
- `--date`: default today. A date in the future is refused.
- `--id`: the file name. Default `<date>-<words of the name>`.
- `--intake-of`: in a team brain, required. It names the agent's record that points to the team, and that record fills every field not given.

It refuses text that looks like a secret or contact details.

### brain feedback set

```text
brain feedback set <id> pending|one-off|elsewhere|declined --reason "<why>" [--to <kind>:<name>]
```

Closes feedback with a reason, which goes into its Context section with the date.

- `elsewhere` needs `--to`, where the lesson lives: `brain:<name>`, `plugin:<name>`, `book:<name>` or `doc:<path>`. Repeat it for more.
- `kept` is not set here: `brain link` or `brain new ... --feedback` sets it.
- Feedback linked to records is refused until you `brain unlink` it.

### brain feedback list

```text
brain feedback list [--pending]
```

Lists the feedback. `--pending`: only new and pending feedback.

### brain new

```text
brain new rule|procedure|topic|routine|policy <id> [--name ...] [--description ...] [--scope ...] [--trigger ...] [--outputs ...]
          [--procedure ...] [--receiver ...] [--owner ...] [--topic <id>]... [--rule <id>]... [--feedback <id>]... [--body-file <file or ->]
```

Writes a record. A rule, procedure or policy starts `proposed`, a routine starts `active`, and a topic has no status. Each `--topic`, `--rule` and `--feedback` repeats and must exist. Each `--feedback` is linked both ways and marked `kept`. `--body-file` gives the body's `##` sections, or `-` for stdin. A field left out stays a `TODO:`, which `brain check` blocks until filled.

| Kind | Brain | Its fields |
|---|---|---|
| `rule` | agent | `--name`, `--description`, `--scope`, `--topic`, `--feedback`; sections Rule, Why, How to apply |
| `procedure` | agent | `--name`, `--description`, `--trigger`, `--outputs`, `--rule`, `--feedback`, `--topic`; section Steps |
| `topic` | agent or team | `--name`, `--description`; section Scope |
| `routine` | agent with no team | `--name`, `--description`, `--trigger`, `--procedure`, `--receiver`; the owner is the brain itself |
| `routine` | team | as above, plus `--owner`, an agent on the roster, and `--procedure <agent>:<procedure-id>` |
| `policy` | team | as a rule; `--feedback` is optional; sections Policy, Why, How to apply |

An agent brain on a team refuses `routine`: the team holds its routines.

### brain set-status

```text
brain set-status <ref> proposed|active|paused|retired [--reason "<why>"]
```

Sets a record's status and rewrites SKILL.md's index.

- A rule, procedure or policy is `proposed`, `active` or `retired`.
- An agent brain's routine is `active` or `paused`. A team routine is `active`, `paused` or `retired`.
- `retired` needs `--reason`. It goes into a rule's or policy's Why, or a procedure's or routine's Context.

### brain link and brain unlink

```text
brain link <feedback> rules/<id>|procedures/<id>|agent
brain unlink <feedback> <record>
```

`link` links the feedback and the record both ways and marks the feedback `kept`. In a team brain the record is `policies/<id>`, `routines/<id>` or `lanes`. `unlink` removes the link both ways. Feedback with no link left goes back to `new`.

### brain index

```text
brain index [--replace]
```

Rewrites SKILL.md from agent.md and the active records: the opening, the agent block (job, lane, never list, approvals, roles, skills, books, decider and voice) and the index of active rules and procedures. In a team brain: the roster and the active policies, then each member's lane rows. SKILL.md's front matter stays as written. Hand-written text anywhere else stays too, and blocks as `skill.hand_written`. `--replace` drops it: move it into agent.md, a rule, a procedure or the team's lanes first.

### brain check

```text
brain check [--all] [--staged]
```

Runs every check on the brain. Exit 3 on a block finding.

- `--all`: every brain under `--project`, or under the current folder.
- `--staged`: what git has staged: every brain in the staged tree, not the working files. The pre-commit hook runs this.

What it blocks and warns on is under [What brain check checks](#what-brain-check-checks).

### brain trace

```text
brain trace <ref>
```

Shows a record, the feedback behind it with the person's words, its topics, and what links to it.

### brain status

```text
brain status
```

Shows the brain's folder, the count of each record by status or disposition, the new and pending feedback, and the proposed rules, procedures and policies. The dream starts here.

### brain install

```text
brain install [--harness claude|codex|cursor | --to <skills folder>] [--user] [--copy]
```

Links the skill into a harness's skills folder: `<skills folder>/<name>` points at the brain's skill folder, so the harness reads the source.

| Harness | Project folder | `--user` folder |
|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Codex | `.agents/skills/` | `~/.agents/skills/` |
| Cursor | `.agents/skills/` | `~/.agents/skills/` |

- With no `--harness` or `--to`, it uses the harness running the command, which it detects from that harness's environment variables. Run outside a harness, pass `--harness`.
- `--copy`: copy the skill, for a harness that cannot follow a link. The copy holds `.brain-source.yaml` with the brain's name, commit and config, and is read-only to `brain`. Run it again to update.
- It refuses when something that is not this brain is already there, and warns when the checkout is not on the default branch.
- It lists the other harnesses it supports, so you can install there too.

### brain plugin

```text
brain plugin
```

Makes the brain a plugin of its repository:

- writes `.claude-plugin/plugin.json` (Claude Code) and `plugin.json` (Codex) at the brain's folder, from SKILL.md's name and description;
- writes `source:` (the repository and path) into brain.yaml, so an installed copy can say where to send changes;
- adds or updates the brain's entry in `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json` at the repository's top, when they exist. It never creates a marketplace file.

It needs SKILL.md's description. Once a plugin.json exists, `brain check` blocks when it drifts from the brain (`plugin.drift`): run `brain plugin` again.

### brain hooks install

```text
brain hooks install [--harness claude|codex|cursor]... [--dir <folder>] [--claude <folder>] [--codex <folder>] [--cursor <folder>] [--repo <folder>] [--no-git]
```

Installs the git pre-commit hook and the harness hooks. See [Hooks](#hooks).

- `--harness`: a harness to install hooks for. Repeat it for more. Default: the one running the command.
- `--dir`: the project folder where the agent's sessions start. Default: this repository. `--claude`, `--codex` and `--cursor` set it for one harness.
- `--repo`: the git repository's top folder. Default: the brain's repository.
- `--no-git`: skip the pre-commit hook.

### brain team, brain team add and brain team remove

```text
brain team
brain team add <agent brain folder>
brain team remove <agent> --routine <id>=back|retire|<agent>...
```

- `brain team` lists the roster, read from the team brain at run time: display name, brain name and job.
- `brain team add`, run in a team brain: adds the agent's folder to `agents:`, moves its `lane` rows from agent.md into `lanes.md`, moves each of its routines into the team as `<agent>-<id>`, named "<name> (<agent>)", and sets `team:` in its brain.yaml. Commit both brains in one commit.
- `brain team remove`: takes the agent off the roster. Its lane rows go back to its agent.md. Each routine it owns needs one `--routine` choice: `back` returns it to the agent with its prefix and name suffix removed and its status kept, `retire` retires it, and `<agent>` gives it to another agent on the roster.

### brain use

```text
brain use [<folder>]
```

Saves the folder that `brain load` and `brain team` read from: a team brain, the repository that holds it, or one agent brain with no team. With no folder, prints the saved one. `--project` and the current folder win over it.

### brain load

```text
brain load [<who>] [--harness claude|codex] [--dry-run] [--no-fetch] [--checkout] [-- <harness arguments>]
```

Starts a coding agent session as one agent, for that session only. See [brain load in detail](#brain-load-in-detail).

- `<who>`: the agent's display name, brain name, or a word of its job, without case. Needed on a team (`load.no_agent`). Left out for one agent brain with no team.
- `--harness`: default the agent.md `harness`, else `claude`.
- `--dry-run`: print the command and start nothing.
- `--no-fetch`: load the default branch as last fetched.
- `--checkout`: load the working folder as it is, to test a brain on a branch.
- Arguments after `--` go to the harness as they are.

### brain version

Prints the version of `brain` and Python.

## Files

### brain.yaml

| Key | Brain | Default | Meaning |
|---|---|---|---|
| `format` | both | | The file format: 3 for this release. See [Format and upgrades](#format-and-upgrades). |
| `name` | both | | The brain's name, and its skill folder's name. |
| `kind` | both | `agent` | `team` for a team brain. |
| `team` | agent | | The team brain it belongs to. `brain team add` sets it. |
| `agents` | team | `[]` | The roster: each agent brain's folder, from the repository's top. |
| `domain` | team | | The word every member's name starts with, such as `acme`. A member without it warns. |
| `known_gaps` | team | `[]` | Skill names agents load that no brain provides yet: a warning, not a block. |
| `books` | team | | Each book source's list file, from the repository's top, such as `bambooks: tools/bambooks-books.txt`. One id per line. A line that starts with `#` is a comment. |
| `pending_days` | both | 14 | Feedback pending longer warns. |
| `checked_days` | both | 90 | An active rule not checked against its source for longer warns. |
| `intake_days` | team | 14 | A pointer to the team with no intake for longer warns. |
| `harness_names` | both | `.claude/`, `.codex/`, `.cursor/`, `.agents/skills`, `settings.local.json` | Harness details the skill may not name, so it works in every harness. |
| `levels` | both | | A check level per code. See [Change a check's level](#change-a-checks-level). |
| `source` | both | | The repository and path, written by `brain plugin`. |

### agent.md

Front matter, then a `## Voice` section.

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The brain's name. |
| `display_name` | | What the agent is called. |
| `description` | yes | One line: what the agent does, and for whom. |
| `job` | yes | What it produces, for whom, and where it stops short of the final action. |
| `lane` | with no team | What it owns and does itself. On a team, the lanes live in the team's `lanes.md`. |
| `anti_jobs` | yes | Actions it must never take, shown as its never list. |
| `needs_approval` | | Actions that need a person's approval first. |
| `data`, `tools` | | The data and tools it may use. |
| `skills` | | Skills it loads after its own brain: a brain's name, or a path to a skill folder starting with `./`, `../`, `/` or `~`. A relative path starts at the repository's top. |
| `books` | | Books it reads, as `<source>:<book id>`. |
| `harness` | | The harness `brain load` starts: `claude`, `codex`, `cursor` or `grokbot`. Default `claude`. |
| `decider` | yes | The role that approves changes to the brain and settles conflicts. |
| `roles` | | Roles it hands off to or consults. |
| `enforce_in_harness` | | Limits the harness itself must enforce. |

### SKILL.md

Generated by `brain index`, in this order:

1. The front matter: `name` and `description`. You write the description. It is the only hand-written part.
2. The opening, from the template, between `<!-- brain:opening:start (generated by brain index; do not edit) -->` and `<!-- brain:opening:end -->`.
3. The agent block from agent.md, between `<!-- brain:agent:start (generated from agent.md by brain index; do not edit) -->` and `<!-- brain:agent:end -->`.
4. The index of active rules, grouped by topic, and active procedures, between `<!-- brain:index:start (generated by brain index; do not edit) -->` and `<!-- brain:index:end -->`.

The markers must appear exactly as shown: `brain index` finds the blocks by them.

A team brain's SKILL.md holds the opening and the index: the roster with each agent's job and lanes, the active policies by topic, and a pointer to the routines.

### Records

One Markdown file each in `references/<kind>/`, with YAML front matter. The file name is lowercase words joined by hyphens.

| Kind | Front matter | Body sections |
|---|---|---|
| feedback | `name`, `date`, `from`, `kind`, `source`, `what_agent_did`, `disposition` (new, pending, kept, one-off, elsewhere, declined), `kept_in` | Feedback; Context |
| rule | `name`, `description`, `status`, `strength` (default or hard), `scope`, `feedback`, `topics`, `rests_on`, `checked` | Rule, Why, How to apply |
| procedure | `name`, `description`, `status`, `trigger`, `outputs`, `rules`, `feedback`, `topics` | Steps; Context |
| topic | `name`, `description` | Scope |
| routine | `name`, `description`, `trigger`, `owner`, `procedure`, `inputs`, `receiver`, `when_nothing_new`, `status` (active or paused) | |

A team brain holds feedback (each with `intake_of`), policies (a rule's fields, `feedback` optional; sections Policy, Why, How to apply), routines (`procedure: <agent>:<id>`, status active, paused or retired, and an optional `feedback`), topics, and `lanes.md`: one table, `| Work | Owner |`, under `## Lanes`, with exactly one owner per piece of work.

### Your settings

`brain use` saves the path in `~/.config/brain/config.toml` (`$XDG_CONFIG_HOME/brain/config.toml`, or the file `$BRAIN_CONFIG` names).

| Key | Default | Meaning |
|---|---|---|
| `team` | | The folder `brain use` saved. |
| `snapshots_keep` | 5 | `brain load` keeps at least this many snapshots. |
| `snapshots_days` | 7 | It also keeps every snapshot used in this many days. |

## brain load in detail

1. **Find the brain.** `--project` wins, then the current folder, then the saved path. It finds a team brain, or one agent brain with no team.
2. **Take a snapshot.** It runs `git fetch` in that repository, then loads the remote's default branch: the remote's `HEAD`, else `main` or `master`. The fetch changes no working file and no branch. With no network, it warns (`load.not_fetched`) and uses the branch as last fetched. A repository with no remote default branch loads its working folder, with `load.no_snapshot`. `--checkout` loads the working folder on purpose, and asks before it goes on when the checkout is behind its upstream (`load.behind`). An answer other than yes, or no one to answer, refuses with exit 3.
3. **Find the agent.** On a team, it matches `<who>` against the display name, then the brain name, then a word of the job. Two or more matches list them and exit 2. No match prints the roster and exits 2.
4. **Resolve what it loads.** The agent's own brain always loads first, then each of its `skills`. It runs the load checks, each as a warning.
5. **Start the harness** with one instruction: "You are <display name>. Before your first answer, read these skills in this order and follow them:", the full path of each SKILL.md, then one line per book source: "Your books from <source>: <ids>."
   - Claude Code: `claude --plugin-dir <brain folder>` for each brain, `--add-dir <folder>` for each plain skill folder outside the git repository of the folder you run it in, and `--append-system-prompt "<instruction>"`.
   - Codex: `codex -c developer_instructions="<instruction>"`. Codex has no plugin flag for one session, so the SKILL.md paths do the loading.
   - Cursor and Grok Bot have no load adapter: pass `--harness claude` or `--harness codex`, or it exits 2 with `load.no_adapter`.

### Snapshots

A snapshot is one folder for each commit, at `~/.cache/brain/<team or brain name>/<first 12 characters of the commit>/` (or under `$XDG_CACHE_HOME`). Every session on that commit on the machine shares it. It holds every folder with a brain.yaml, each agent's relative skill paths and the team's book lists, from `git archive`: not the rest of the repository. For a brain at the repository's top, it takes only that brain's files: brain.yaml, its skill folder and its plugin files.

- Its files are read-only, and `brain` refuses to write there (`brain.snapshot`). Change the brain on a branch in its repository.
- Each load deletes old snapshots, but keeps the newest `snapshots_keep` (5) and every one loaded in the last `snapshots_days` (7). A session open longer than that can lose its snapshot to another session's cleanup.

## Hooks

`brain hooks install` writes:

| Hook | File | Events |
|---|---|---|
| git pre-commit | `.git/hooks/pre-commit` | runs `brain check --staged` on what the commit holds |
| Claude Code | `.claude/settings.local.json` | Stop and SessionStart |
| Codex | `.codex/hooks.json` | Stop and SessionStart |
| Cursor | `.cursor/hooks.json` | stop |

- **Stop:** checks the brain at the end of a turn. On a block finding, it sends the agent back to fix it, at most once per turn, with up to 20 findings.
- **SessionStart:** tells the agent how much feedback waits and how many records are proposed.
- The harness hook files hold paths from your machine. `brain` adds each to a `.gitignore` next to it, so each person runs `brain hooks install` once.
- Every hook calls the `brain` that installed it, by its full path. If an upgrade moves `brain` to another path, run `brain hooks install` again.
- A pre-commit hook that `brain` did not write is left alone. It refuses (`hooks.pre_commit_exists`) and prints the line to add to yours.

## Installed copies are read-only

A plugin install, an `install --copy` and a `brain load` snapshot are copies. A change there never reaches the repository, so `brain` refuses to write (`brain.installed_copy`, `brain.snapshot`) and says how to clone the repository. Feedback then reaches the brain as a pull request.

## What brain check checks

It blocks:

- feedback that nobody decided (`new`), and pending, one-off, elsewhere or declined feedback with no reason;
- kept feedback that names no record, elsewhere feedback that does not say where, and a rule with no feedback;
- a link that does not resolve, or that points only one way;
- a record with a missing or unknown field, a bad value, a missing body section, a bad file name or a duplicate name;
- a SKILL.md opening, agent block or index that differs from what `brain index` writes, and hand-written text outside its front matter;
- a SKILL.md whose front matter is not valid YAML, that links feedback, that has no description or one over 1,024 characters, that has more than 500 lines, or whose name is not its folder's;
- a plugin.json or marketplace entry that drifts from the brain (`plugin.drift`);
- a brain.yaml older than format 3 (`brain.format_old`), and `loads` in agent.md (`agent.loads_removed`);
- a `TODO:` placeholder, a secret, contact details or a card number, a Markdown link that does not resolve, and a harness name from `harness_names` anywhere in the skill (URLs and code spans are not scanned for contact details);
- feedback dated in the future.

In a team brain it also blocks:

- a folder in `agents:` that is not an agent brain in the repository with `team:` set to this team;
- a `lanes.md` owner not on the roster, and the same work twice;
- a routine whose owner is not on the roster or whose procedure does not resolve;
- team feedback whose `intake_of` does not resolve to an agent's record that points here;
- in each agent's `skills`: a name no brain in the repository provides, unless `known_gaps` lists it, and a path that is not a folder with a SKILL.md; in its `books`: one not written `<source>:<id>`.

In an agent brain on a team, it blocks a routine, a `lane`, a team that is not in the repository or does not list the agent, and a `brain:` pointer outside the team.

It warns on:

- a brain with no take-feedback procedure;
- feedback pending past `pending_days`, an active rule not checked within `checked_days`, and a rule with `rests_on` but no `checked` date;
- a SKILL.md over about 5,000 tokens;
- on a team: a member whose name does not start with `domain`, an agent with no lane, a routine whose owner owns no lane or does not run its procedure, a pointer to the team with no intake after `intake_days`, a loaded name in `known_gaps`, a skill folder whose SKILL.md names another skill, a book not in its source's list, a book list that cannot be read, and a book source with no list.

## Change a check's level

A brain sets a code's level in brain.yaml:

```yaml
levels:
  core.harness_name: warn   # block, warn or off
```

Change a level only when the brain has a real reason the check does not fit, and write the reason in a comment. Never change one to make a failing brain pass.

## Format and upgrades

brain.yaml's `format` says which file layout a brain uses. This release reads and writes format 3: the team's roster in `agents:`, and agent.md's `skills:` and `books:`.

- An older brain blocks with `brain.format_old`. Its fix says what to move, then run `brain index --replace`.
- A newer brain is refused with `brain.format_newer`: upgrade `brain`.
- A release that changes the format says so in its tag message. Upgrade every machine that checks or loads the brain at the same time, including CI and the pre-commit hook, because a brain in the new format fails an older `brain`.

Upgrade:

```sh
uv tool install --force 'agent-brain @ git+https://github.com/lynk-ai/agent-brain@<tag>'
```
