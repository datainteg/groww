# Open-Source Agent Manifest

Generated on 2026-06-06 after auditing this workspace. All agent and skill
definitions in `.agents` and `.claude` were copied unmodified from the
open-licensed upstream projects listed below. No custom agent definition was
created.

## Project Fit

This workspace contains:

- A Flask/Python backend using MongoDB, Redis, JWT, pandas, NumPy, technical
  indicators, Groww API integration, paper trading, and live order execution.
- A Vite/React/TypeScript frontend using React Router, Zustand, Axios,
  Tailwind CSS, and Lightweight Charts.
- Approximately 11,215 lines of Python and 6,544 lines of TypeScript/TSX.
- 71 backend route handlers and nine frontend page components.
- No automated backend or frontend test files found during the audit.
- No Git repository at the workspace root or inside `backend`/`frontend`.

The Next.js agent guide was reviewed but no Next.js-specific rules or agents
were installed because this project uses Vite and does not include `next`.

## Important Audit Findings

These findings explain the security, testing, quantitative, and review agents
selected for future development:

- Critical: `backend/groww/GrowwAPI.py` contains hardcoded Groww credentials.
  Revoke/rotate them before any further live-trading use.
- Critical: live trading paths exist and can place real orders.
- High: Flask/JWT/encryption configuration contains development fallback
  secrets, and CORS is configured permissively.
- High: Redis trade locking fails open when Redis is unavailable.
- High: there is no automated test suite despite financial calculations and
  live execution paths.
- Medium: `trading_engine.py`, `trading_engine_fixed.py`, and
  `trading_engine_backup.py` duplicate critical logic;
  `trading_engine.py` and `trading_engine_fixed.py` are byte-identical.
- Medium: financial calculations mix prices, points, percentages, quantities,
  lots, and currency values, making dimensional and property-based testing
  especially valuable.

## Sources

| Source | Revision | License | Use |
| --- | --- | --- | --- |
| https://github.com/VoltAgent/awesome-claude-code-subagents | `2f9cf8b9562dcc235cc2296bda6df82d60e800be` | MIT | Claude-compatible subagent definitions |
| https://github.com/VoltAgent/awesome-agent-skills | `0e6e58985eb75a2cf7b2cbf4bc518f1bd4ef1210` | MIT | Catalog used to select relevant open-source skills |
| https://github.com/trailofbits/skills | `d5fe2e6a7896236c3102fd5477e833623ad70298` | CC BY-SA 4.0 | Security, audit, Python, and testing skills |
| https://github.com/anthropics/skills | `da20c92503b2e8ff1cf28ca81a0df4673debdbf7` | Apache 2.0 per installed skill | Frontend design and web application testing skills |
| https://agents.md/ | Website reviewed 2026-06-06 | Open agent-instruction format | Directory and project-instruction guidance |
| https://nextjs.org/docs/app/guides/ai-agents | Page updated 2026-03-31 | Documentation | Confirmed Next.js rules are not applicable to this Vite project |

License copies for VoltAgent and Trail of Bits are under `.agents/licenses`.
Anthropic license files are included inside each installed Anthropic skill.

## Installed Agents

The same 21 upstream agent files are stored in `.agents/agents` and
`.claude/agents`.

### VoltAgent

- `api-designer`
- `architect-reviewer`
- `backend-developer`
- `code-reviewer`
- `database-optimizer`
- `debugger`
- `fintech-engineer`
- `python-pro`
- `quant-analyst`
- `react-specialist`
- `risk-manager`
- `security-auditor`
- `test-automator`
- `typescript-pro`

### Trail of Bits

- `arithmetic-scanner`
- `dimension-annotator`
- `dimension-discoverer`
- `dimension-propagator`
- `dimension-validator`
- `function-analyzer`
- `sharp-edges-analyzer`

## Installed Skills

The same nine upstream skill directories are stored in `.agents/skills` and
`.claude/skills`.

### Trail of Bits

- `audit-context-building`
- `dimensional-analysis`
- `insecure-defaults`
- `modern-python`
- `property-based-testing`
- `sharp-edges`
- `supply-chain-risk-auditor`

### Anthropic

- `frontend-design`
- `webapp-testing`

## Suggested Use

- Before live-trading changes: use `security-auditor`, `fintech-engineer`,
  `risk-manager`, `insecure-defaults`, and `sharp-edges`.
- For strategy or indicator changes: use `quant-analyst`,
  `dimensional-analysis`, and `property-based-testing`.
- For backend work: use `backend-developer`, `python-pro`, `api-designer`, and
  `database-optimizer`.
- For frontend work: use `react-specialist`, `typescript-pro`,
  `frontend-design`, and `webapp-testing`.
- Before accepting changes: use `test-automator`, `code-reviewer`, and
  `architect-reviewer`.

## Installation Verification

- All 42 installed agent copies (21 in each directory) match their upstream
  source files byte-for-byte.
- All installed skill files in both directories match their upstream source
  files byte-for-byte.
- All 53 backend Python files passed syntax parsing.
- `npm run build` currently fails on pre-existing frontend TypeScript errors,
  including API/type contract mismatches, missing Vite `ImportMeta.env`
  typing, unsupported `LineStyle.ShortDash`, and unused imports.
- No automated test files were found, so no project test suite could be run.
