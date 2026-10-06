---
name: agentic-orchestrator
description: Coordinates agentic flows across multiple specialized expert skills (AWS, BGG API, Data Engineering, Recommender System, Site UI) to deliver cohesive end-to-end modifications. Use this skill when coordinating complex multi-component features or cross-domain refactoring.
---

## Guidelines for Task Orchestration

### Domain Identification
When a request is received, identify which domains (BGG API, AWS Architecture, Site UI, Recommender System, Data Engineering) are involved:
- **Scraper updates**: Invokes `BGG API Expert` + `Data Expert` + `AWS Architecture Expert` (if Lambda/ECS schedules or SQS queues change).
- **Recommendation tuning**: Invokes `Recommender System Expert` + `Data Expert` (for schemas) + `BGG API Expert` (if inline profiles change).
- **Cafe Edition & Venue features**: Invokes `Site UI Expert` + `AWS Architecture Expert` (`bgg-cafes` DynamoDB, API Gateway, S3) + `bgg_preferences_handler.py` + `Data Expert` (`collection.parquet` cafe partition).
- **Table Voting & Game Night Sessions**: Invokes `Site UI Expert` + `Recommender System Expert` (`sessions.py`) + `AWS Architecture Expert` (`bgg-game-night-sessions` DynamoDB).
- **Convention Previews**: Invokes `BGG API Expert` (`bgg_preview_refresh`) + `Recommender System Expert` + `Site UI Expert`.
- **New UI features**: Invokes `Site UI Expert` + `AWS Architecture Expert` (if new API endpoints or Cognito checks are needed).

### Multi-Skill Coordination
1. **Planning Phase**: Load the context of all relevant skills. Create a unified `implementation_plan.md` addressing architectural concerns first, then backend data schemas, then API/computation logic, and finally the UI layout.
2. **Sequential Execution**:
   - Update schemas & infrastructure specifications first (AWS, Terraform, Data schemas).
   - Implement backend scrapers or recommender algorithms.
   - Run backend unit tests (`pytest`).
   - Implement frontend templates, stylesheets (Vanilla CSS), and client JavaScript.
   - Run frontend unit tests (`npm test` or `npm --prefix site_ui test`). Note: Automated browser testing or visual UI verification is **not** necessary; visual verification is performed manually by the user.
3. **Traceability**: Maintain a single `task.md` tracking development progress across all files and components.
