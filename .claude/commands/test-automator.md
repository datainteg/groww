---
description: You need to build, implement, or enhance automated test frameworks, create test scripts, or integrate testing into CI/CD pipelines.
argument-hint: [task / files / context]
---

Launch the **test-automator** subagent to handle the request below.

Use the Agent tool with `subagent_type: "test-automator"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the test-automator to do before launching it.

> Agent purpose: Use this agent when you need to build, implement, or enhance automated test frameworks, create test scripts, or integrate testing into CI/CD pipelines.
