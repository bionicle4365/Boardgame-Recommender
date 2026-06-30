---
name: Agentic Orchestrator
description: Coordinates agentic flows across multiple specialized expert skills to deliver cohesive end-to-end modifications.
---

## Guidelines for Task Orchestration

### Domain Identification
When a request is received, identify which domains (BGG API, AWS Architecture, Site UI, Recommender System, Data Engineering) are involved:
- **Scraper updates**: Invokes `BGG API Expert` + `Data Expert` + `AWS Architecture Expert` (if Lambda/ECS schedules change).
- **Recommendation tuning**: Invokes `Recommender System Expert` + `Data Expert` (for schemas) + `BGG API Expert` (if inline profiles change).
- **New UI features**: Invokes `Site UI Expert` + `AWS Architecture Expert` (if new API endpoints or Cognito checks are needed).

### Multi-Skill Coordination
1. **Planning Phase**: Load the context of all relevant skills. Create a unified `implementation_plan.md` addressing architectural concerns first, then backend data schemas, then API/computation logic, and finally the UI layout.
2. **Sequential Execution**:
   - Update schemas & infrastructure specifications first (AWS, Terraform, Data schemas).
   - Implement backend scrapers or recommender algorithms.
   - Run unit tests to verify backend changes (`pytest`).
   - Implement frontend templates and stylesheets (Vanilla CSS).
   - Verify frontend changes locally via Jekyll.
3. **Traceability**: Maintain a single `task.md` tracking development progress across all files and components.
