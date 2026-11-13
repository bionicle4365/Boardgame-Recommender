---
name: task-generator
description: Discovers actionable engineering tasks from S3 telemetry, contract drift, unit test failures, and strategic opportunities in market_analysis.md, publishing deduplicated GitHub Issues via agent_backlog.py.
---

## Guidelines for Autonomous Task Generation

### 1. Live Telemetry, CI & Codebase Audits
Run the deterministic audit script to inspect contract synchronization, frontend API calls, backend handler test coverage, live unit test suites, GitHub Actions CI, S3 data lake/video/cafe health, and CloudWatch Lambda errors:
```powershell
python scripts/audit_and_generate_tasks.py --run-tests --s3 --cloudwatch --ci --publish --max-new-issues 3
```
What the deterministic audit covers:
- **Contract & Frontend API Drift (`source:data-drift`)**: Diffs [schemas_and_routes.json](file:///d:/Git/Boardgame-Recommender/docs/contracts/schemas_and_routes.json) against Terraform API Gateway routes, `TARGET_SCHEMA` in `bgg_compactor`, and frontend `fetchApi` / `fetch` endpoints in [site_ui/](file:///d:/Git/Boardgame-Recommender/site_ui/).
- **Test Suites & GitHub Actions CI (`source:test-gap`)**: Runs `pytest` and `npm --prefix site_ui test`, flags Lambda packages or `_handle_*` functions lacking unit tests in [tests/](file:///d:/Git/Boardgame-Recommender/tests/), and checks `/actions/runs?branch=main` for recent workflow failures.
- **S3 Catalog, Video & Cafe Health (`source:telemetry`)**: Verifies `catalog.parquet` freshness (`< 14` days), missing preview games in `data/active_previews_games.json`, `rules_video_url` coverage thresholds (`>= 20%` on previews with `>= 10` cataloged games), and failed venue syncs in `data/cafes_registry.json`.
- **CloudWatch Lambda Errors (`source:telemetry`)**: Scans `/aws/lambda/bgg_*` log groups over the last 24 hours for `Traceback`, `Task timed out`, and `ThrottlingException` events.

### 2. Controlled Product & Roadmap Replenishment (`source:roadmap`)
Check open roadmap tasks via `python scripts/agent_backlog.py list --status all`:
- **Replenishment Rule**: Only when **fewer than 3** open `source:roadmap` issues exist in `agent:proposed` or `agent:ready`, inspect [market_analysis.md](file:///d:/Git/Boardgame-Recommender/docs/market_analysis.md) and [cafe_edition_design.md](file:///d:/Git/Boardgame-Recommender/docs/cafe_edition_design.md) and propose **1** atomic, single-PR feature task (e.g., *Game Night Flight* 3-stage recommendations, *Teach vs. Play* complexity/weight split, or *Why Not?* exclusion reasons) via:
```powershell
python scripts/agent_backlog.py create --title "..." --objective "..." --owned-paths ... --forbidden-paths ... --acceptance ... --verify ... --priority p2 --source roadmap --domain ...
```

### 3. Noise & Safety Guardrails
- **Human Approval Gate**: All newly published or created issues start as `agent:proposed` and require human approval (`agent:ready`) before execution.
- **Daily Cap & Zero Speculative Noise**: Propose at most **3 net-new issues per daily run** (`--max-new-issues 3`). Never propose speculative refactors without a concrete bug, telemetry gap, test failure, or roadmap goal, and never create tasks that require manual AWS Console clicks.
- **Single-PR Scope & Protect Infrastructure**: Every generated task must be completable in one cohesive PR with explicit, minimal `owned_paths`, `infrastructure/` included in `forbidden_paths` unless Terraform changes are explicitly required, and runnable CLI `verification_commands` (`python -m pytest ...`, `npm --prefix site_ui test`, or `terraform -chdir=infrastructure validate`).
- **Deduplication**: Always publish through `scripts/agent_backlog.py create` so recurring runs match existing open titles rather than creating duplicates.
