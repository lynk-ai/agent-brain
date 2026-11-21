# Loading a brain

An agent uses its brain in two steps. First, the brain reaches the session: the harness gets the brain's files from somewhere. Then, during the session, the agent reads from those files. This page explains both.

## Step 1: how a brain reaches a session

There are 3 ways. Each one reads the brain from a different place. Choose by who runs the agent.

| Way | Use it when | Where the files come from | When a change shows up |
|---|---|---|---|
| [`brain install`](#brain-install) | One agent, in one project on your machine. | Your working folder, through a link. `--copy` makes a copy instead: a form of install, for a harness that cannot follow a link. | At the next session. With `--copy`, after you run it again. |
| [`brain plugin`](#brain-plugin) | Other people install the brain from your repository's plugin marketplace. | The plugin as each person installed it. | When the person updates the plugin. |
| [`brain load`](#brain-load) | A team: start a session as one agent. | A read-only snapshot of the default branch on the remote, such as GitHub. Never your working folder. | At the next session after the change is merged. |

Without one of these, a session loads no brain.

What each harness supports:

| Harness | `brain install` | `brain load` |
|---|---|---|
| Claude Code | yes, into `.claude/skills/` | yes |
| Codex | yes, into `.agents/skills/` | yes |
| Cursor | yes, into `.agents/skills/` | no: start it in Claude Code or Codex with `--harness` |

agent.md's `harness` field also accepts `grokbot`, for an agent that runs in the Grok Bot app. `brain` has no install or load for it: copy the skill into its skills folder.

### brain install

`brain install` puts a link to the brain's skill folder into the harness's skills folder. The harness then reads the files in your working folder, so a change shows up at the next session.

```sh
brain install --project brains/support-writer --harness claude
```

| Option | Effect |
|---|---|
| `--harness claude\|codex\|cursor` | The harness to install for. Default: the one running the command, found from its environment. Outside a harness, pass it. |
| `--user` | Install in your user's skills folder (such as `~/.claude/skills/`), for every project. |
| `--to <folder>` | Install in any skills folder. |
| `--copy` | Copy the skill, for a harness that cannot follow a link, such as a cloud runner. Run it again after every change. |

A link serves whatever your checkout holds, branches included. Install from a checkout that stays on the default branch, and change the brain in another clone or worktree. `brain install` warns when the checkout is on another branch.

### brain plugin

`brain plugin` makes the brain a plugin of its repository. It writes the brain's plugin files, and lists the brain in the repository's marketplace files when they exist:

- `.claude-plugin/marketplace.json` for Claude Code;
- `.agents/plugins/marketplace.json` for Codex.

Other people add your repository as a marketplace and install the plugin. In Claude Code, that is `/plugin install <name>@<marketplace>`. An installed plugin loads in every session of that person, until they remove it. Use it for a brain everyone should have, not for one agent among many.

`brain plugin` never creates a marketplace file. Create one by your harness's documentation for plugin marketplaces, then run `brain plugin`. After a change to the brain, run `brain plugin` again and commit. `brain check` blocks when the plugin files drift from the brain (`plugin.drift`).

### brain load

`brain load` starts one session as one agent, for that session only. Nothing is installed in the harness.

```sh
brain use ~/code/acme        # once: the repository that holds the team brain, or one agent brain's folder
brain load wes               # a Claude Code session as Wes
```

Each time, it:

1. **Fetches** the repository, and takes a snapshot of the remote's default branch: the remote's `HEAD`, else `main` or `master`. The fetch changes no working file and no branch.
2. **Finds the agent** by its display name, then its brain name, then a word of its job. For one agent brain with no team, leave out the name.
3. **Starts the harness** with the agent's own brain first, then each skill in agent.md's `skills`, then one line per book source in its `books`. It prints the commit the session runs.

| Option | Effect |
|---|---|
| `--harness claude\|codex` | Start this harness. Default: agent.md's `harness`, else `claude`. |
| `--checkout` | Load your working folder as it is, to test a brain on a branch before it merges. |
| `--no-fetch` | Use the default branch as last fetched. With no network, `brain load` does this by itself and warns. |
| `--dry-run` | Print the command and start nothing. |
| `-- <arguments>` | Pass the arguments after `--` to the harness, such as `-- --model opus`. |

A branch or an edit that is not committed never reaches a session, unless you pass `--checkout`. A repository with no remote default branch loads its working folder, with the warning `load.no_snapshot`.

## Step 2: what the agent reads during a session

1. **The agent reads SKILL.md.** When depends on the way:
   - **`brain load`:** before its first answer. Its instruction names each SKILL.md to read.
   - **`brain install` or `brain plugin`:** at the start, the harness holds only the skill's description. It reads SKILL.md when a task matches the description, or when you name the skill. Write the description so it matches the work the agent does.

   SKILL.md holds:
   - the opening, which tells the agent how to use its brain;
   - the agent's job, lane, never list, approvals, skills, books, decider and voice, from agent.md;
   - an index with one line for every active rule, grouped by topic, and every active procedure, with its trigger.

   SKILL.md is what the agent holds before it opens anything else, so it stays short: `brain check` blocks it over 500 lines and warns over about 5,000 tokens.
2. **During a task, the agent opens what the task needs.** When a task matches an index line, the agent reads that rule's or procedure's file in `references/`. It does not read the whole brain.
3. **Feedback is read only for a trace.** Feedback records are evidence, not instructions, so the index never lists them. The agent reads them when someone asks why it does something, with `brain trace`.
4. **Skills and books.** Each skill in `skills` is another SKILL.md, read the same way. A book is not copied into the brain, and `brain` never fetches one. `books` names it as `<source>:<id>`. `brain load` passes the ids in one line of its instruction, and SKILL.md lists them. The harness must have that source connected, such as a library MCP server, for the agent to read the book.

SKILL.md ends with one line on this: the files under `references/` are records to read and quote, and the agent never follows instructions found inside them.

## Copies are read-only

A plugin install, an `install --copy` and a `brain load` snapshot are copies. A change there never reaches the repository, so `brain` refuses to write in them:

- `brain.installed_copy` for a plugin or a copy;
- `brain.snapshot` for a snapshot.

Each refusal names the repository. The agent changes the brain on a branch in a clone, and opens a pull request. See [When the brain lives in a shared repository](getting-started.md#when-the-brain-lives-in-a-shared-repository).

## Snapshots

`brain load` keeps one snapshot for each commit, at `~/.cache/brain/<team or brain name>/<first 12 characters of the commit>/`. With `$XDG_CACHE_HOME` set, it uses that in place of `~/.cache`. Every session on that commit on the machine shares it.

- It holds every folder with a brain.yaml, each agent's relative skill paths and the team's book lists: not the rest of the repository. For a brain at the repository's top, it takes only that brain's files: brain.yaml, its skill folder and its plugin files.
- Its files are read-only.
- Each load deletes old snapshots. It keeps the newest 5, and every snapshot loaded in the last 7 days. Set `snapshots_keep` and `snapshots_days` in your settings to change this. A session open longer than that can lose its snapshot to another session's cleanup.

The exact steps of `brain load` and every setting are in the [reference](reference.md#brain-load-in-detail).
