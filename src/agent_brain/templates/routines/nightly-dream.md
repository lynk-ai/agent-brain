---
name: Nightly dream
description: Each night, checks and tidies the brain, and leaves every change as a draft for the decider.
trigger: Nightly at 03:00 in the owner's time zone.
owner: {{name}}
procedure: run-the-dream
inputs: [the brain, the last report in reports/]
receiver: decider
when_nothing_new: Write the report with nothing found, and send nothing.
status: active
---
