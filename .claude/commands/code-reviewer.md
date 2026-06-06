---
description: You need to conduct comprehensive code reviews focusing on code quality, security vulnerabilities, and best practices.
argument-hint: [task / files / context]
---

Launch the **code-reviewer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "code-reviewer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the code-reviewer to do before launching it.

> Agent purpose: Use this agent when you need to conduct comprehensive code reviews focusing on code quality, security vulnerabilities, and best practices.
