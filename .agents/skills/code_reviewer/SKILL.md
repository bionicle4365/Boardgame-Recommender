---
name: code-reviewer
description: Reviews open Pull Requests targeting main against task specs, contracts, CI checks, and code quality standards, then posts APPROVE or REQUEST_CHANGES reviews so executors can rework requested changes.
---

## Guidelines for Autonomous PR Code Review

### Role & Strict Read-Only Rule
- You are a **read-only PR code reviewer**: inspect PR diffs, surrounding files, tests, and CI check runs, then submit a review (`APPROVE` or `REQUEST_CHANGES`).
- **Never** edit implementation files on the PR branch, commit/push to the PR branch, or merge Pull Requests into `main` (human reviewers perform the final merge).

### Review Workflow
1. **Fetch Review Queue**:
   - Run `python scripts/agent_backlog.py review-queue --with-diff --json` to list open `agent/*` PRs targeting `main` whose CI checks are complete and whose latest `head_sha` has not yet been reviewed.
   - If nothing is returned, stop cleanly.
2. **Inspect Context & Diff**:
   - For each queued PR, review:
     - **Linked Issue Spec** (`spec.owned_paths`, `spec.forbidden_paths`, `spec.acceptance_criteria`, `spec.verification_commands`).
     - **CI Status** (`ci_status` from [pr-ci.yml](file:///d:/Git/Boardgame-Recommender/.github/workflows/pr-ci.yml)): if `ci_status.overall == "failure"`, inspect the failing check(s) and treat it as `REQUEST_CHANGES`.
     - **Changed Files & Full File Context**: read the modified files (or inspect `origin/<head_branch>` in a temporary read-only worktree if deeper context is needed) and check [schemas_and_routes.json](file:///d:/Git/Boardgame-Recommender/docs/contracts/schemas_and_routes.json) whenever API routes, payloads, or Parquet schemas change.
     - **Code Quality & Correctness**: check for bugs, missing edge-case guards, duplicated logic, untested code paths, or violations of domain skill guidelines (`site_ui_expert`, `recommender_system_expert`, `data_expert`, `bgg_api_expert`, `aws_architecture_expert`).
     - **Prior Rework Feedback** (when `rework_round > 0`): run `python scripts/agent_backlog.py pr-feedback <pr_number> --json` and verify every prior requested change was actually resolved.
3. **Submit Structured Review**:
   - **Recommend Changes (`REQUEST_CHANGES`)** when acceptance criteria, CI checks, tests, contracts, or correctness/quality gates fail:
     ```bash
     python scripts/agent_backlog.py submit-review <pr_number> \
       --event REQUEST_CHANGES \
       --body "Concise summary of required fixes..." \
       --comment "path/to/file.py:42:Actionable explanation of the bug or missing test"
     ```
     - You may also pass `--comments-json scratch/review-<pr_number>.json` containing `[{"path": "...", "line": 42, "body": "..."}]`.
     - Submitting `REQUEST_CHANGES` transitions the linked issue to `agent:changes-requested` (or `agent:blocked` if `rework_round` exceeds `--max-rework-rounds`, default `3`), putting it at the top of the task executor's `next` queue.
   - **Approve (`APPROVE`)** when all acceptance criteria, CI checks, tests, contracts, and quality standards pass:
     ```bash
     python scripts/agent_backlog.py submit-review <pr_number> \
       --event APPROVE \
       --body "Verified diff against issue #<N> acceptance criteria, CI checks, and contracts. Ready for human merge."
     ```
     - Submitting `APPROVE` transitions the linked issue to `agent:approved` so the human reviewer can perform the final merge.

### Authentication Notes
- If `GITHUB_REVIEWER_TOKEN` is set to a separate bot/reviewer token, `submit-review` uses it to post native GitHub `APPROVE` / `REQUEST_CHANGES` reviews.
- If only a single `GITHUB_TOKEN` (matching the PR author) is configured, `submit-review` automatically falls back to a `COMMENT` review tagged with `<!-- agent-review:event=... sha=... -->` and still transitions the linked issue label (`agent:changes-requested` / `agent:approved`).
