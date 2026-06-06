---
description: Validates dimensional consistency and detects dimensional bugs in annotated code
argument-hint: [task / files / context]
---

Launch the **dimension-validator** subagent to handle the request below.

Use the Agent tool with `subagent_type: "dimension-validator"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the dimension-validator to do before launching it.

> Agent purpose: Validates dimensional consistency and detects dimensional bugs in annotated code
