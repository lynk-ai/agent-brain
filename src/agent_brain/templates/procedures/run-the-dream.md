---
name: Run the dream
description: Each night, check and tidy the brain, and leave every proposed change as a draft for the decider.
status: active
trigger: The nightly dream routine fires.
outputs: One report in reports/, and at most one content draft for the decider.
topics: [upkeep]
---
## Steps

Limits, word for word:
- Never delete, merge, retire or rewrite a record unattended; propose it in the draft.
- Never weaken or skip a check to make a run pass.
- Never merge the content draft.
- Never send, publish or act outside the brain; findings go in the report.
- Never propose again what the decider rejected, unless new evidence is cited.

1. Run `brain status`. It gives the brain's folder and its reports/ folder. Read the last report's cutoff. With no earlier report, run in full and say why.
2. Run `brain check`. If it cannot run, write that the brain failed tonight and stop.
3. List the feedback still pending, and the rules and procedures still proposed.
4. Read the feedback since the cutoff. If a feedback matches an active rule, count it as that rule failing and raise it to the decider. Never save it as a new rule.
5. If a feedback contradicts an active rule or another teacher, write it as a conflict for the decider, both sides quoted.
6. Find duplicate and near-duplicate rules, contradictions, and the stale rules that `brain check` warns about. Propose a merge, a decision, a check or a retirement for each, in the draft.
7. Weekly: pair each rule with the closest part of the agent's books, and propose retiring duplicates. Leave stricter rules alone.
8. Weekly: list rules that would hold for any team in this role and name no company, client or person, as candidates for the book's owner. List them; never move them.
9. For each earlier proposal, record whether it was accepted, rejected or reverted, and the reason.
10. Write reports/<date>-dream.md: the cutoff, the check result, each list above, and the draft's link. Writing nothing else is a normal outcome.
