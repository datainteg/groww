---
description: Discovers dimensional vocabulary for codebases by analyzing naming conventions and protocol patterns
argument-hint: [task / files / context]
---

Launch the **dimension-discoverer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "dimension-discoverer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the dimension-discoverer to do before launching it.

> Agent purpose: Discovers dimensional vocabulary for codebases by analyzing naming conventions and protocol patterns
