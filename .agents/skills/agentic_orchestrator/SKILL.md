---
name: agentic-orchestrator
description: Coordinates agentic flows across multiple specialized expert skills (AWS, BGG API, Data Engineering, Recommender System, Site UI) to deliver cohesive end-to-end modifications. Use this skill when coordinating complex multi-component features or cross-domain refactoring.
---

## Guidelines for Task Orchestration

### GitHub Issues Backlog Integration
Autonomous tasks are discovered via [task-generator](file:///d:/Git/Boardgame-Recommender/.agents/skills/task_generator/SKILL.md) ([audit_and_generate_tasks.py](file:///d:/Git/Boardgame-Recommender/scripts/audit_and_generate_tasks.py)), queued as GitHub Issues via [agent_backlog.py](file:///d:/Git/Boardgame-Recommender/scripts/agent_backlog.py), and gated by [verify_task.py](file:///d:/Git/Boardgame-Recommender/scripts/verify_task.py):
- **Generate tasks**: `python scripts/audit_and_generate_tasks.py --run-tests --s3 --publish` (creates issues as `agent:proposed` awaiting human approval)
- **List proposed issues**: `python scripts/agent_backlog.py list --status proposed`
- **Approve issue**: `python scripts/agent_backlog.py approve <issue_number>` (transitions `agent:proposed` -> `agent:ready`)
- **Discover approved work**: `python scripts/agent_backlog.py list --status ready` (or `python scripts/agent_backlog.py next --json`; agents must only claim `agent:ready` issues)
- **Claim next task & branch**: `python scripts/agent_backlog.py next --claim --agent <agent_name> --checkout` (creates/checks out `agent/issue-<issue_number>`; never work on, push to, or merge into `main`)
- **Verify task**: `python scripts/verify_task.py --issue <issue_number>` (enforces active `agent/...` branch, path boundaries, and domain tests)
- **Complete task & open PR**: `python scripts/agent_backlog.py complete <issue_number> --pr agent/issue-<issue_number> --push --open-pr --summary "..."` (pushes only `agent/issue-<issue_number>` and opens a PR to `main` without merging)

### Domain Identification
When a request or issue is received, identify which domains (`BGG API`, `AWS Architecture`, `Site UI`, `Recommender System`, `Data Engineering`) are involved:
- **Scraper updates**: `BGG API Expert` + `Data Expert` + `AWS Architecture Expert` (if Lambda/ECS schedules or SQS queues change).
- **Recommendation tuning**: `Recommender System Expert` + `Data Expert` (for schemas) + `BGG API Expert` (if inline profiles change).
- **Cafe Edition & Venue features**: `Site UI Expert` + `AWS Architecture Expert` (`bgg-cafes` DynamoDB, API Gateway, S3) + `bgg_preferences_handler.py` + `Data Expert` (`collection.parquet` cafe partition).
- **Table Voting & Game Night Sessions**: `Site UI Expert` + `Recommender System Expert` (`sessions.py`) + `AWS Architecture Expert` (`bgg-game-night-sessions` DynamoDB).
- **Convention Previews**: `BGG API Expert` (`bgg_preview_refresh`) + `Recommender System Expert` + `Site UI Expert`.
- **New UI features**: `Site UI Expert` + `AWS Architecture Expert` (if new API endpoints or Cognito checks are needed).

### Execution Modes

#### Mode A: Single-Domain Task (Plan -> Execute)
1. Load the relevant domain skill and inspect [schemas_and_routes.json](file:///d:/Git/Boardgame-Recommender/docs/contracts/schemas_and_routes.json).
2. Lock `owned_paths`, `forbidden_paths`, verification commands, and explicit `"Re-plan if"` triggers in the plan before handing off to execution.
3. Verify changes with `python scripts/verify_task.py` before marking the issue complete.

#### Mode B: Multi-Domain Feature / Milestone (Parallel Swarm)
1. **Lock Cross-Domain Contract First**: Update [schemas_and_routes.json](file:///d:/Git/Boardgame-Recommender/docs/contracts/schemas_and_routes.json) during planning or before workers diverge so backend, infra, and UI agree on exact routes, fields, and auth requirements.
2. **Spawn Isolated Workers (`workspace: "share"`)**: Assign non-overlapping `owned_paths` per domain (`infra-worker` -> `infrastructure/`, `backend-worker` -> `bgg_*/` + `tests/`, `frontend-worker` -> `site_ui/`). Never assign two authors to the same file.
3. **Dedicated Verifier**: Spawn a read-only verifier loaded with `autonomous-verifier` (`workspace: "inherit"`) to run `python scripts/verify_task.py` and audit diffs against the contract and acceptance criteria before landing work and running `agent_backlog.py complete`.
