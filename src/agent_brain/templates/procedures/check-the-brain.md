---
name: Check the brain
description: Run the brain's checks and fix what they find, without weakening a check.
status: active
trigger: Any change to the brain, and each dream.
outputs: A clean check, or the findings that remain and why.
topics: [upkeep]
---
## Steps

1. Run `brain check`.
2. If it reports skill.index_stale, run `brain index`.
3. For each other block finding, apply its Fix, then run `brain check` again.
4. Never make a finding pass by weakening a check, deleting evidence or editing the index by hand.
5. If the check cannot run, the brain has failed. Say so, and change nothing else.
6. List the warn findings in the change or the dream's report.
