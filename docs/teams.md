# Teams

A team brain holds what a team of agents shares: who is on the team, who owns which work, the policies every agent follows, and the routines the team runs. Every agent on the team keeps its own brain. The team brain and its agents' brains live in one repository.

## What a team brain holds

```text
brains/acme-team-brain/
  brain.yaml            kind: team, the roster (agents:), the domain, settings
  acme-team-brain/      the team skill: every agent on the team loads it
    SKILL.md            written by brain: the roster and the active policies
    references/
      lanes.md          each piece of work, with exactly one owner agent
      policies/         rules for the whole team
      routines/         every scheduled job on the team, each run by one agent
      feedback/         feedback an agent pointed to the team
      topics/           labels that group the policies
```

A team brain has no procedures of its own. A team routine runs a procedure in an agent's brain, named `<agent>:<procedure-id>`. When a team policy and an agent's own rule disagree, the agent follows the team policy.

## Set up a team

**1. Create the team brain, and add each agent brain:**

```sh
brain init acme-triage-brain --display-name Tara --path brains/acme-triage-brain
brain init acme-writer-brain --display-name Wes --path brains/acme-writer-brain
# fill in each agent.md and SKILL.md description, as in Getting started
brain init acme-team-brain --team --path brains/acme-team-brain
brain team add brains/acme-triage-brain --project brains/acme-team-brain
brain team add brains/acme-writer-brain --project brains/acme-team-brain
brain check --all
```

`brain team add`:

- adds the agent's folder to `agents:` in the team's brain.yaml;
- moves the agent's `lane` rows from its agent.md into the team's `lanes.md`;
- moves the agent's routines into the team brain, as `<agent>-<id>`;
- sets `team:` in the agent's brain.yaml.

Commit both brains in one commit.

Then list the team brain in each agent's `skills` in agent.md, so its sessions load the team's lanes and policies:

```yaml
skills: [acme-team-brain]
```

Then run `brain index --project brains/<agent>` for each agent, so its SKILL.md lists the skill.

**2. Give each piece of work one owner,** in `references/lanes.md`:

```markdown
## Lanes

Each row is one piece of work, with exactly one owner agent.

| Work | Owner |
|---|---|
| reply drafts for support tickets | acme-writer-brain |
| ticket triage | acme-triage-brain |
```

Each agent's SKILL.md shows its own lane rows, so an agent knows what it owns and hands the rest to the owner. `brain check` blocks an owner not on the roster, and the same work twice.

**3. Optional: set a domain.** With `domain: acme` in the team's brain.yaml, each agent brain's name starts with it, as `acme-<role>-brain`. `brain check` warns, never blocks, on a member without it, and `brain init` in that repository says so. A name with the domain stays unique on a machine that loads skills from many sources.

**4. Write policies,** the rules for the whole team:

```sh
brain new policy hand-off-with-context --project brains/acme-team-brain --topic how-the-team-works --body-file policy.md
brain set-status policies/hand-off-with-context active --project brains/acme-team-brain
```

A policy has the sections Policy, Why and How to apply. Its feedback is optional.

## Start a session as one agent

```sh
brain use ~/code/acme          # once: save the repository that holds the team brain
brain team                     # who is on the team: display name, brain name and job
brain load wes                 # a Claude Code session as Wes
brain load wes --harness codex
brain load wes --checkout      # your working folder, to test a change before it merges
```

`brain load` starts the session from the team's merged default branch, never from your working folder, and prints the commit. The session loads the agent's own brain, then each skill in its `skills`, with the team brain among them. [Loading a brain](loading.md#brain-load) explains every option.

A `brain load` session is read-only. To change a brain, the agent works in a clone on a branch, and opens a pull request: see [When the brain lives in a shared repository](getting-started.md#when-the-brain-lives-in-a-shared-repository).

## Team feedback

Feedback about a lane, a team policy or a routine changes the team, not one agent. It still starts in the agent that heard it:

1. **The agent records it in its own brain,** in the same turn, then points it to the team:
   ```sh
   brain feedback set <id> elsewhere --to brain:acme-team-brain --reason "<why>"
   ```
   Feedback that belongs in another agent's brain points there: `--to brain:<agent>`. On a team, `brain:` names only the team or an agent on its roster.
2. **The team's central agent takes it in.** The team names this agent in `lanes.md`, as the owner of a row such as `team brain upkeep`. It writes a team feedback record that copies the person's words, who said them, where, when and the kind:
   ```sh
   brain feedback add --intake-of brain:acme-writer-brain/<id> --project brains/acme-team-brain
   ```
3. **It decides it like any feedback,** and links it to the policy, routine or lanes it changes: `brain link <id> policies/<id>`, `routines/<id>` or `lanes`.

Whoever can merge the team brain's repository approves. `brain check` on the team warns when a pointer waits more than `intake_days` (14) with no intake.

## Change the team

- **Take an agent off the team:** `brain team remove <agent> --routine <id>=back|retire|<agent>`. Its lane rows go back to its agent.md. Each routine it owns needs one choice: back to the agent, retired, or given to another agent.
- **Move work:** edit the row's owner in `lanes.md`, then run `brain index --project <team brain>`. That rewrites the team's SKILL.md and each member's lane rows.
- **Rename an agent:** rename its folder and its `name` in brain.yaml, agent.md and SKILL.md, update `agents:` and every `lanes.md` row and routine that names it, then run `brain index` on the team. `brain check --all` lists every place you missed.

The exact behavior of each command is in the [reference](reference.md#brain-team-brain-team-add-and-brain-team-remove).
