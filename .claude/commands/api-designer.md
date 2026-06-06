---
description: Designing new APIs, creating API specifications, or refactoring existing API architecture for scalability and developer experience.
argument-hint: [task / files / context]
---

Launch the **api-designer** subagent to handle the request below.

Use the Agent tool with `subagent_type: "api-designer"`. Pass the task verbatim, let the subagent do the work, then relay its findings concisely to the user.

**Task / context:**

$ARGUMENTS

If no task is provided above, ask the user what they want the api-designer to do before launching it.

> Agent purpose: Use this agent when designing new APIs, creating API specifications, or refactoring existing API architecture for scalability and developer experience. Invoke when you need REST/GraphQL endpoint design, OpenAPI documentation, authentication patterns, or API versioning strategies.
