---
description: Conducting comprehensive security audits, compliance assessments, or risk evaluations across systems, infrastructure, and processes.
argument-hint: [task / files / context]
---

Launch the **security-auditor** subagent to handle the request below.

Use the Agent tool with `subagent_type: "security-auditor"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the security-auditor to do before launching it.

> Agent purpose: Use this agent when conducting comprehensive security audits, compliance assessments, or risk evaluations across systems, infrastructure, and processes. Invoke when you need systematic vulnerability analysis, compliance gap identification, or evidence-based security findings.
