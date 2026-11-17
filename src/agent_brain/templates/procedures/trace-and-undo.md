---
name: Trace an action and undo a lesson
description: Show which rule led to an action and who taught it, and undo a lesson that made the work worse.
status: active
trigger: Someone asks why you did something, or a lesson made your work worse.
outputs: The rule or procedure, the feedback behind it with its words, date and who gave it, and a proposed undo when one is asked for.
topics: [upkeep]
---
## Steps

1. Find the row in the index that you followed.
2. Run `brain trace <rules/id or procedures/id>`, and quote the feedback it shows: the words, the date and who said them.
3. If no row led to the action, say so. Do not invent a reason.
4. To undo a lesson, run `brain set-status <ref> retired --reason "<what went wrong>"`. Never delete the file.
5. If the feedback itself was wrong, run `brain unlink <feedback> <record>`, then `brain feedback set <feedback> declined --reason "<why>"`.
6. Run `brain check`, and propose the undo as one change for the decider.
