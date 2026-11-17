---
name: Hand work off
description: Pass work outside your lane to the role that owns it, with what you know and what you did not do.
status: active
trigger: A request falls outside your lane or touches an anti-job in agent.md.
outputs: One handoff to a role, and one line to the person who asked.
topics: [upkeep]
---
## Steps

1. Compare the request with lane and anti_jobs in agent.md.
2. If it is inside your lane and touches no anti-job, do it. Stop.
3. Find the role in roles in agent.md that owns it. Name the role, never a person or an agent.
4. If no role fits, tell the decider and stop.
5. Pass the request, what you know, and what you did not do.
6. Tell the person who asked which role has it.
