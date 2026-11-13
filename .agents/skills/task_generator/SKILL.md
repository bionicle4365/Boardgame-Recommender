---
name: task-generator
description: Discovers actionable engineering tasks from S3 telemetry, contract drift, unit test failures, and strategic opportunities in market_analysis.md, publishing deduplicated GitHub Issues via agent_backlog.py.
---

## Guidelines for Autonomous Task Generation

### 1. Gather Live Signals
Run the deterministic audit script to inspect contract synchronization, unit test suites, and S3 data lake health:
```powershell
python scripts/audit_and_generate_tasks.py --run-tests --s3 --json
```
To automatically publish discovered tasks as deduplicated GitHub Issues (`agent:proposed`, awaiting human approval):
```powershell
python scripts/audit_and_generate_tasks.py --run-tests --s3 --publish
```

### 2. Decompose Strategic Opportunities
When generating new feature tasks from [market_analysis.md](file:///d:/Git/Boardgame-Recommender/docs/market_analysis.md) or user goals, first check existing open issues to avoid duplicating work:
```powershell
python scripts/agent_backlog.py list --status all
```
Then create atomic single-PR issues via:
```powershell
python scripts/agent_backlog.py create --title "..." --objective "..." --owned-paths ... --forbidden-paths ... --acceptance ... --verify ... --priority p2 --source roadmap --domain ...
```

### 3. Task Sizing & Safety Guardrails
- **Single-PR Scope**: Every generated task must be completable in one cohesive PR with explicit, minimal `owned_paths` and `forbidden_paths`.
- **Protect Infrastructure**: Include `infrastructure/` in `forbidden_paths` unless the task explicitly requires Terraform changes.
- **Deterministic Verification**: Every task must specify at least one runnable CLI command in `verification_commands` (`python -m pytest ...`, `npm --prefix site_ui test`, or `terraform -chdir=infrastructure validate`)—never rely on manual UI inspection.
- **Deduplication**: Always publish through `scripts/agent_backlog.py create` so recurring scheduled generator runs match open titles instead of creating duplicate issues.
