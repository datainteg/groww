---
description: You need to evaluate system design decisions, architectural patterns, and technology choices at the macro level.
argument-hint: [task / files / context]
---

Launch the **architect-reviewer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "architect-reviewer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the architect-reviewer to do before launching it.

> Agent purpose: Use this agent when you need to evaluate system design decisions, architectural patterns, and technology choices at the macro level.
