Closes #<issue_number>

## Summary
<!-- Concise explanation of what changed and why. -->

## Changes Made
<!-- Key files modified/added and architectural highlights. -->
- 

## Examples
<!-- Sample API request/response JSON, CLI usage, or before/after behavior. -->

## Verification & Test Results
<!-- Commands executed (`python scripts/verify_task.py --issue <issue_number>`, `pytest`, `npm --prefix site_ui test`, `terraform validate`) and observed results. -->
- [ ] `python scripts/verify_task.py --issue <issue_number>`

## Screenshots
<!-- For `site_ui/` changes, attach desktop/mobile screenshots (or let PR CI `ui-screenshots` post them from the `screenshots` orphan branch). -->
_No UI changes in this PR._

## Review Checklist
- [ ] Branch isolated on `agent/issue-<issue_number>` (never committed/pushed directly to `main`)
- [ ] Changes stay strictly within `owned_paths` and avoid `forbidden_paths`
- [ ] Contracts in `docs/contracts/schemas_and_routes.json` remain synchronized
- [ ] All automated unit tests pass without skipped or relaxed assertions
