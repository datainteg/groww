---
description: Scans repo for files with dimensional arithmetic to scope discovery
argument-hint: [task / files / context]
---

Launch the **arithmetic-scanner** subagent to handle the request below.

Use the Agent tool with `subagent_type: "arithmetic-scanner"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the arithmetic-scanner to do before launching it.

> Agent purpose: Scans repo for files with dimensional arithmetic to scope discovery
