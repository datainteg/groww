---
description: Performs ultra-granular per-function deep analysis for security audit context building.
argument-hint: [task / files / context]
---

Launch the **function-analyzer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "function-analyzer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the function-analyzer to do before launching it.

> Agent purpose: Performs ultra-granular per-function deep analysis for security audit context building. Use when analyzing dense functions, data-flow chains, cryptographic implementations, or state machines.
