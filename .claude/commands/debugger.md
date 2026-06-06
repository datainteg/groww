---
description: You need to diagnose and fix bugs, identify root causes of failures, or analyze error logs and stack traces to resolve issues.
argument-hint: [task / files / context]
---

Launch the **debugger** subagent to handle the request below.

Use the Agent tool with `subagent_type: "debugger"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the debugger to do before launching it.

> Agent purpose: Use this agent when you need to diagnose and fix bugs, identify root causes of failures, or analyze error logs and stack traces to resolve issues.
