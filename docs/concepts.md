# Concepts

This page explains what a brain is made of, what you edit and what `brain` writes, who approves a change, and when a change reaches the agent. Read it once before [Getting started](getting-started.md).

## Words

| Word | Meaning |
|---|---|
| **Brain** | One agent's folder: `brain.yaml`, plus a skill folder with `SKILL.md`, `agent.md` and `references/`. |
| **Skill** | The folder a harness loads, such as `brains/support-writer/support-writer/`. |
| **Harness** | The app that runs the agent, such as Claude Code, Codex or Cursor. |
| **Feedback** | A record of what a person said about the agent's work, in their own words. Each one must be decided: kept in a rule or procedure, or closed with a reason. |
| **Rule** | A lesson the agent follows, with its reason and the feedback it came from. |
| **Procedure** | Steps the agent runs the same way each time, such as *Take a piece of feedback*. |
| **Topic** | A label that groups rules in the index. |
| **Routine** | A procedure that runs on a schedule or a trigger, such as the nightly dream. |
| **Dream** | The nightly routine: the agent checks and tidies its own brain, and proposes changes for approval. |
| **Decider** | The person or role who approves changes to the brain. |
| **Status** | A rule or procedure is `proposed`, `active` or `retired`. Only active ones are in the index. |
| **Team brain** | What a team of agents shares: the roster, the lanes, the policies and the routines. |
| **Lane** | A piece of work with exactly one owner agent. |
| **Policy** | A rule for the whole team. |
| **Snapshot** | The read-only copy of the repository's default branch that `brain load` starts a session from. |
| **Disposition** | What became of a feedback record: `new`, `pending`, `kept` (in a rule or procedure), `one-off`, `elsewhere` or `declined`. |
| **Pointer** | A feedback record set to `elsewhere`, with `--to brain:<name>`: it points the lesson to another brain, such as the team's. |
| **Intake** | The team brain's copy of a pointer, written by the team's central agent. |
| **Central agent** | The agent that keeps the team brain: it takes in pointers and changes policies, routines and lanes. A team names it in `lanes.md`, as the owner of the team brain's upkeep. |

## What a brain is made of

```text
brains/support-writer/            the brain
  brain.yaml                      format, name, team, settings
  support-writer/                 the skill: what the harness loads
    SKILL.md                      written by brain; you write only its description
    agent.md                      the agent's record; you edit it
    references/
      feedback/                   what people said, in their words: the evidence
      rules/                      the lessons, each linked to its feedback
      procedures/                 the steps the agent runs, such as Take a piece of feedback
      topics/                     the labels that group rules
      routines/                   procedures on a schedule, such as the nightly dream
```

A team brain has the same shape, with `policies/`, `routines/`, `feedback/`, `topics/` and `lanes.md` in `references/`, and the roster in its brain.yaml. See [Teams](teams.md).

## What you edit, and what brain writes

**You edit `agent.md`.** It is the agent's record: its job, what it owns, what it must never do, what needs approval, its harness, the skills and books it loads, its decider and its voice. `brain init` writes it with `TODO:` placeholders, and you fill them in.

**You add records with `brain` commands:** `brain feedback add`, `brain new rule`, `brain link` and `brain set-status`. Each command writes the Markdown file and keeps every link two-way. You can edit a record's text by hand afterwards.

**`brain` writes `SKILL.md`.** It is the file the harness loads: an opening, the agent's job and limits copied from agent.md, and an index of the active rules and procedures. You write only its front matter's `description`.

**There are two descriptions, for two readers:**

- `description` in **SKILL.md**'s front matter is the trigger. The harness reads it to decide when to load the skill. Say what the agent does, then when to use it, in the words its users say, in at most 1,024 characters.
- `description` in **agent.md** is one line for people: what the agent does, and for whom. A team's roster shows the agent's `job`, and falls back to this line.

| You change | You run | SKILL.md |
|---|---|---|
| `agent.md` | `brain index` | rewritten |
| A new rule or procedure | `brain new ...` | unchanged: a new rule or procedure starts as `proposed` |
| A rule or procedure goes active or retired | `brain set-status ...` | rewritten |
| An agent joins or leaves a team | `brain team add` or `brain team remove` | rewritten, for the team and the agent |
| SKILL.md's description | nothing | it is the hand-written part |

If you forget `brain index`, the check catches it: `brain check`, the commit hook and the harness's Stop hook block with `skill.agent_stale` or `skill.index_stale` until you run it. Text written by hand anywhere else in SKILL.md blocks with `skill.hand_written`: move it into agent.md, a rule or a procedure, then run `brain index --replace`.

## Who approves a change

The agent records feedback and proposes rules. For an agent brain, the **decider** named in agent.md approves them. For a team brain, whoever can merge the team brain's repository approves. A rule goes active only on the decider's word. That is the agent's procedure and your review: `brain` does not enforce it. How that word arrives depends on how you work:

- **One agent, on your machine:** you tell the agent "approved", and it runs `brain set-status <rule> active`.
- **A brain in a repository with pull requests:** the agent makes the change on a branch and opens a pull request. The decider approves by merging it. The seeded procedure *Change the brain* says this.

Feedback itself never waits for approval: the agent records it in the same turn it hears it.

## When a change reaches the agent

There is no separate build. `SKILL.md` sits next to `agent.md` in the repository, and `brain` rewrites it in place. What counts as the release depends on how the brain reaches the agent's sessions. [Loading a brain](loading.md) explains each way.

| How the brain reaches the session | What makes the change live | The agent sees the change |
|---|---|---|
| `brain install`, linked | nothing: the session reads your folder | at its next session |
| `brain install --copy`, a copy | running `brain install --copy` again | at its next session after that |
| `brain load` | merging the change to the default branch | at its next session after the merge |
| `brain plugin` | running `brain plugin`, committing and merging, then each user updating the plugin | after the user updates |

A session reads SKILL.md once it starts using the skill, so a change made during a session shows at the next one.

## What brain refuses, and why

`brain check` blocks a brain that is not whole, so a broken brain cannot reach an agent:

- feedback nobody decided, or closed with no reason;
- a rule with no feedback behind it;
- a link that points nowhere, or only one way;
- a SKILL.md that differs from what `brain index` writes;
- a `TODO:` placeholder, a secret or contact details.

The full list is in the [reference](reference.md#what-brain-check-checks), and every code is in [findings.md](findings.md).

One limit: a script cannot see feedback that the agent never wrote down. The seeded procedure *Take a piece of feedback* tells the agent to record each correction in the same turn. It comes first in every index.
