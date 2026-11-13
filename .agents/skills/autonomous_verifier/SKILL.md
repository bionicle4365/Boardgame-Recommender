---
name: autonomous-verifier
description: Verifies autonomous agent work against GitHub Issue task specifications, file ownership boundaries, contract schemas, and deterministic unit tests without editing production code directly.
---

## Guidelines for Autonomous Verification

### Role & Strict Non-Edit Rule
- You are a **read-only verifier**: inspect diffs, run checks, and report failures back to the author worker (or coordinator). Do not edit implementation files yourself.

### Verification Checklist
1. **Load Issue Spec**: Run `python scripts/agent_backlog.py get <issue_number>` to retrieve `owned_paths`, `forbidden_paths`, `acceptance_criteria`, and `verification_commands`.
2. **Run Deterministic Gate**: Execute `python scripts/verify_task.py --issue <issue_number>` to verify:
   - Active git branch is an isolated `agent/...` branch (never `main` or `master`).
   - Modified/untracked files stay strictly within `owned_paths` and never touch `forbidden_paths`.
   - Inferred domain suites (`pytest`, `npm --prefix site_ui test`, `terraform validate`) and issue `verification_commands` all exit `0`.
3. **Inspect Diff & Contracts**: Review `git diff` against every item in `acceptance_criteria` and confirm any API route or Parquet column change matches [schemas_and_routes.json](file:///d:/Git/Boardgame-Recommender/docs/contracts/schemas_and_routes.json).
4. **Report Verdict**:
   - **Pass**: Summarize the verified checks and transition the issue using `python scripts/agent_backlog.py complete <issue_number> --pr agent/issue-<issue_number> --push --open-pr --summary "<verified checks>"` (never push or merge to `main` and never merge the PR).
   - **Fail**: Report the exact failing command, boundary violation, or missing acceptance criterion to the author worker so it can fix and resubmit.
