# Getting started

This page builds one agent's brain end to end, then turns a correction into a rule the agent follows. It takes about 10 minutes. The words are explained in [Concepts](concepts.md).

## 1. Install

You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/) and git.

```sh
uv tool install 'agent-brain @ git+https://github.com/lynk-ai/agent-brain@v0.5.1'
brain version
```

## 2. Create the brain

Run it inside a git repository. Outside one, `brain init` runs `git init` in the new folder.

```sh
brain init support-writer --display-name Mila --path brains/support-writer
```

It writes:

- `brain.yaml`;
- the skill folder `support-writer/`, with `agent.md` and a `SKILL.md` whose description is a `TODO:`;
- 7 seeded procedures, such as *Take a piece of feedback*, 2 topics and a nightly dream routine;
- a git pre-commit hook that runs the checks on every commit.

## 3. Fill in agent.md and the description

`brain check` blocks until every `TODO:` is gone:

```text
failed: 12 block and 0 warn findings in support-writer.
  block support-writer/SKILL.md:3: It still has a TODO: placeholder. Fix: Replace the placeholder with the real text. [record.unfinished]
```

Fill in `brains/support-writer/support-writer/agent.md`. These are the fields that matter first. The [reference](reference.md#agentmd) lists all of them.

```yaml
---
name: support-writer
display_name: Mila
description: Drafts replies to customer support tickets for the support lead.
job: Drafts replies to support tickets, for the support lead to review and send.
lane:
  - reply drafts for support tickets
anti_jobs:
  - never sends a reply to a customer
decider: support lead
harness: claude
skills: []
books: []
---
## Voice

Short, warm sentences. Name the customer's problem in the first line.
```

Then write the `description` in `SKILL.md`'s front matter. The harness reads it to decide when to load the skill: say what the agent does, then when to use it.

```yaml
description: "Mila's rules and procedures for drafting support replies. Use when drafting or reviewing a reply to a support ticket."
```

## 4. Build the skill and check it

```sh
brain index --project brains/support-writer
brain check --project brains/support-writer
```

```text
ok: support-writer: every check passed, 0 warnings.
```

`brain index` copied agent.md into SKILL.md. Run it again after every edit to agent.md.

## 5. Get it to the agent

For one agent in one project, link the skill into the harness's skills folder, and install the hooks that check the brain at the end of every turn:

```sh
brain install --project brains/support-writer --harness claude
brain hooks install --project brains/support-writer --harness claude
```

Start a new Claude Code session in this project and ask: "Use the support-writer skill: what must you never do?" The answer quotes the never list from agent.md. Claude Code loads an installed skill when a task matches its description, so naming the skill makes the test certain. For other ways to get a brain to an agent, see [Loading a brain](loading.md).

## 6. Teach the agent its first rule

The support lead reviews a draft and says: "Don't promise dates for refunds. Finance sets them." The agent follows its procedure *Take a piece of feedback*.

**Record it, in the same turn,** with the words as said:

```sh
brain feedback add --project brains/support-writer \
  --name "Never promise a refund date" --from "support lead" --kind correction \
  --source "review of ticket 4121" --did "Wrote that the refund arrives in 3 days" \
  --text "Don't promise dates for refunds. Finance sets them."
```

```text
ok: Feedback 2026-11-21-never-promise-a-refund-date written. Decide it in this turn.
```

The record's id is its date and the words of its name. Until it is decided, `brain check` blocks with `feedback.undecided`.

**Turn it into a rule.** Write the rule's sections in a file, `rule.md`:

```markdown
## Rule

Never promise a date for a refund in a reply. Say that finance confirms the date.

## Why

The support lead, on ticket 4121: "Don't promise dates for refunds. Finance sets them." A promised date that slips makes a second complaint.

## How to apply

1. When a reply mentions a refund, leave out any date or number of days.
2. Write that finance confirms the date by email.
```

```sh
brain new rule no-refund-dates --project brains/support-writer \
  --name "Never promise a refund date." \
  --description "A reply never names a date or number of days for a refund; finance confirms it." \
  --scope "Every reply that mentions a refund." \
  --topic working-with-others --feedback 2026-11-21-never-promise-a-refund-date --body-file rule.md
```

The rule starts as `proposed`, linked to the feedback both ways, and the feedback is marked `kept`.

**The decider approves, and the rule goes active.** On your machine, the support lead tells the agent "approved", and the agent runs:

```sh
brain set-status rules/no-refund-dates active --project brains/support-writer
```

SKILL.md's index lists it, so every session loads it:

```text
## Rules

### Working with others

- **Never promise a refund date.** A reply never names a date or number of days for a refund; finance confirms it. [rules/no-refund-dates](references/rules/no-refund-dates.md)
```

**Trace it** when someone asks why the agent does something:

```sh
brain trace rules/no-refund-dates --project brains/support-writer
```

```text
ok: rules/no-refund-dates.
  rules/no-refund-dates: Never promise a refund date. (active)
    from feedback 2026-11-21-never-promise-a-refund-date: 2026-11-21, support lead: "Don't promise dates for refunds. Finance sets them."
    topic working-with-others: Working with others
```

## Other ways to decide feedback

Not every piece of feedback becomes a new rule:

- **An active rule already says it:** `brain link <feedback> rules/<id>`. The rule failed once, so tell the decider.
- **A one-time request with no lasting lesson:** `brain feedback set <feedback> one-off --reason "<why>"`.
- **The lesson belongs in another brain, a plugin, a book or a doc:** `brain feedback set <feedback> elsewhere --to brain:<name> --reason "<why>"`.
- **Not sure yet:** `brain feedback set <feedback> pending --reason "<what is unclear>"`. It warns after 14 days.
- **Not a real correction:** `brain feedback set <feedback> declined --reason "<why>"`.

## When the brain lives in a shared repository

If the agent's sessions start from a copy, the agent cannot write there. This covers a plugin install, an `install --copy`, and a `brain load` session on a team. `brain` refuses with `brain.installed_copy` or `brain.snapshot` and names the repository. The agent then:

1. works in a clone of the repository, on a branch;
2. runs the same commands with `--project <clone>/brains/<name>`;
3. commits, and opens a pull request.

The decider approves by merging it. The next session after the merge loads the new rule.

## Next

- [Loading a brain](loading.md): every way a brain reaches a session.
- [Teams](teams.md): more agents, with shared lanes and policies.
- [Checks](checks.md): the hooks, failed checks and CI.
