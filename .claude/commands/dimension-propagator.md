---
description: Propagates dimensional annotations through arithmetic and call chains, reporting mismatches found during propagation
argument-hint: [task / files / context]
---

Launch the **dimension-propagator** subagent to handle the request below.

Use the Agent tool with `subagent_type: "dimension-propagator"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the dimension-propagator to do before launching it.

> Agent purpose: Propagates dimensional annotations through arithmetic and call chains, reporting mismatches found during propagation
