---
description: Evaluates APIs, configurations, and library interfaces for misuse resistance and footgun potential.
argument-hint: [task / files / context]
---

Launch the **sharp-edges-analyzer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "sharp-edges-analyzer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the sharp-edges-analyzer to do before launching it.

> Agent purpose: Evaluates APIs, configurations, and library interfaces for misuse resistance and footgun potential. Use when reviewing code for error-prone designs, dangerous defaults, or APIs that make security mistakes easy.
