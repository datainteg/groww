---
description: Adds dimensional annotations to source code at anchor points using Reserve Protocol's format
argument-hint: [task / files / context]
---

Launch the **dimension-annotator** subagent to handle the request below.

Use the Agent tool with `subagent_type: "dimension-annotator"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the dimension-annotator to do before launching it.

> Agent purpose: Adds dimensional annotations to source code at anchor points using Reserve Protocol's format
