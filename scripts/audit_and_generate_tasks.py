#!/usr/bin/env python3
"""Autonomous audit and GitHub Issue task generator for Boardgame-Recommender."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


LAMBDA_PACKAGES: Dict[str, List[str]] = {
    "bgg_api_proxy": ["test_bgg_api_proxy.py"],
    "bgg_compactor": ["test_combine_raw_to_single_file.py"],
    "bgg_game_data_scraper": ["test_bgg_game_data_scraper.py"],
    "bgg_game_scraper": ["test_bgg_game_scraper.py"],
    "bgg_preferences": [
        "test_bgg_preferences_handler.py",
        "test_cafe_management.py",
        "test_cafe_onboarding.py",
        "test_cafe_sync.py",
    ],
    "bgg_preview_refresh": ["test_bgg_preview_refresh.py"],
    "bgg_recommender": [
        "test_bgg_recommender.py",
        "test_cache_utils.py",
        "test_game_night_sessions.py",
        "test_narration.py",
    ],
    "bgg_taste_analytics": ["test_bgg_taste_analytics.py"],
    "bgg_user_data_scraper": ["test_bgg_user_data_scraper.py"],
}


def _make_task(
    *,
    title: str,
    objective: str,
    owned_paths: List[str],
    forbidden_paths: List[str],
    acceptance_criteria: List[str],
    verification_commands: List[str],
    priority: str,
    source: str,
    domains: List[str],
) -> Dict[str, Any]:
    """Build and validate a structured task specification dictionary."""
    validated = agent_backlog.validate_task_spec(
        {
            "owned_paths": owned_paths,
            "forbidden_paths": forbidden_paths,
            "acceptance_criteria": acceptance_criteria,
            "verification_commands": verification_commands,
        }
    )
    return {
        "title": title,
        "objective": objective,
        "owned_paths": validated["owned_paths"],
        "forbidden_paths": validated["forbidden_paths"],
        "acceptance_criteria": validated["acceptance_criteria"],
        "verification_commands": validated["verification_commands"],
        "priority": priority,
        "source": source,
        "domains": domains,
    }


def _parse_apigw_routes(apigw_tf_text: str) -> Set[Tuple[str, str]]:
    """Extract `(METHOD, /path)` tuples from API Gateway `route_key` declarations."""
    routes: Set[Tuple[str, str]] = set()
    for match in re.finditer(r'route_key\s*=\s*"([A-Z]+)\s+([^"]+)"', apigw_tf_text):
        routes.add((match.group(1).strip().upper(), match.group(2).strip()))
    return routes


def _parse_compactor_schema_columns(compactor_text: str) -> List[str]:
    """Extract ordered column names from `TARGET_SCHEMA = pa.schema([...])`."""
    schema_match = re.search(
        r"TARGET_SCHEMA\s*=\s*pa\.schema\(\[(.*?)\]\s*\)",
        compactor_text,
        re.DOTALL,
    )
    if not schema_match:
        return []
    return re.findall(r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*pa\.", schema_match.group(1))


def audit_contract_drift(repo_root: str = ".") -> List[Dict[str, Any]]:
    """Compare `docs/contracts/schemas_and_routes.json` against Terraform routes and `TARGET_SCHEMA`."""
    contract_path = os.path.join(repo_root, "docs", "contracts", "schemas_and_routes.json")
    apigw_path = os.path.join(repo_root, "infrastructure", "apigateway", "main.tf")
    compactor_path = os.path.join(repo_root, "bgg_compactor", "combine_raw_to_single_file.py")

    if not (os.path.exists(contract_path) and os.path.exists(apigw_path) and os.path.exists(compactor_path)):
        return []

    with open(contract_path, "r", encoding="utf-8") as f:
        contract = json.load(f)
    with open(apigw_path, "r", encoding="utf-8") as f:
        tf_routes = _parse_apigw_routes(f.read())
    with open(compactor_path, "r", encoding="utf-8") as f:
        compactor_cols = _parse_compactor_schema_columns(f.read())

    contract_routes = {
        (str(r.get("method", "")).upper(), str(r.get("path", "")))
        for r in contract.get("api_routes", [])
    }
    contract_cols = [
        str(col.get("name", ""))
        for col in contract.get("parquet_schemas", {}).get("catalog", {}).get("columns", [])
    ]

    issues_found: List[str] = []
    missing_routes = sorted(tf_routes - contract_routes)
    extra_routes = sorted(contract_routes - tf_routes)
    if missing_routes:
        issues_found.append(f"Routes in Terraform missing from contract: {missing_routes}")
    if extra_routes:
        issues_found.append(f"Routes in contract missing from Terraform: {extra_routes}")

    if compactor_cols != contract_cols:
        missing_cols = [c for c in compactor_cols if c not in contract_cols]
        extra_cols = [c for c in contract_cols if c not in compactor_cols]
        issues_found.append(
            f"Catalog schema mismatch (missing_in_contract={missing_cols}, extra_in_contract={extra_cols})"
        )

    if not issues_found:
        return []

    return [
        _make_task(
            title="Synchronize docs/contracts/schemas_and_routes.json with API Gateway and catalog schema",
            objective=(
                "Contract drift detected between docs/contracts/schemas_and_routes.json and "
                "source-of-truth definitions:\n- " + "\n- ".join(issues_found)
            ),
            owned_paths=["docs/contracts/schemas_and_routes.json"],
            forbidden_paths=["infrastructure/", "site_ui/"],
            acceptance_criteria=[
                "api_routes in docs/contracts/schemas_and_routes.json exactly matches route_key entries in infrastructure/apigateway/main.tf",
                "parquet_schemas.catalog.columns matches TARGET_SCHEMA in bgg_compactor/combine_raw_to_single_file.py",
            ],
            verification_commands=["python -m pytest tests/test_audit_and_generate_tasks.py -v"],
            priority="p1",
            source="data-drift",
            domains=["data", "aws-infra"],
        )
    ]


def _extract_failing_vitest_files(output: str) -> List[str]:
    """Parse failing Vitest test file names from Vitest CLI output."""
    matches = re.findall(r"(tests/[A-Za-z0-9_.-]+\.test\.js)", output or "")
    seen: Set[str] = set()
    ordered: List[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def audit_test_suites(repo_root: str = ".", run_tests: bool = False) -> List[Dict[str, Any]]:
    """Audit backend package test coverage and optionally run pytest + Vitest for failures."""
    tasks: List[Dict[str, Any]] = []
    tests_dir = os.path.join(repo_root, "tests")

    for pkg, expected_files in LAMBDA_PACKAGES.items():
        pkg_dir = os.path.join(repo_root, pkg)
        if not os.path.isdir(pkg_dir):
            continue
        has_test = any(os.path.exists(os.path.join(tests_dir, tf)) for tf in expected_files)
        if not has_test:
            target_test = expected_files[0]
            tasks.append(
                _make_task(
                    title=f"Add baseline unit test coverage for {pkg}",
                    objective=f"Package `{pkg}/` has no matching unit test file in `tests/`.",
                    owned_paths=[f"tests/{target_test}"],
                    forbidden_paths=["infrastructure/", "site_ui/"],
                    acceptance_criteria=[
                        f"Add deterministic unit tests covering the core handler in {pkg}/",
                        f"python -m pytest tests/{target_test} exits 0",
                    ],
                    verification_commands=[f"python -m pytest tests/{target_test} -v"],
                    priority="p2",
                    source="test-gap",
                    domains=["recommender" if "recommender" in pkg else "data"],
                )
            )

    if not run_tests:
        return tasks

    py_proc = subprocess.run(
        "python -m pytest -q",
        shell=True,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if py_proc.returncode != 0:
        combined = f"{py_proc.stdout}\n{py_proc.stderr}"
        failed_files = sorted(set(re.findall(r"(tests/test_[A-Za-z0-9_]+\.py)", combined)))
        owned = failed_files if failed_files else ["tests/"]
        tasks.append(
            _make_task(
                title="Fix failing backend pytest unit test suite",
                objective=(
                    "Live `python -m pytest -q` failed with exit code "
                    f"{py_proc.returncode}.\n\nExcerpt:\n{combined[-1200:]}"
                ),
                owned_paths=owned,
                forbidden_paths=["infrastructure/", "site_ui/"],
                acceptance_criteria=[
                    "Resolve all failing assertions in the backend test suite",
                    "python -m pytest exits 0",
                ],
                verification_commands=["python -m pytest -v"],
                priority="p1",
                source="test-gap",
                domains=["recommender"],
            )
        )

    ui_proc = subprocess.run(
        "npm --prefix site_ui test",
        shell=True,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if ui_proc.returncode != 0:
        combined_ui = f"{ui_proc.stdout}\n{ui_proc.stderr}"
        if "test_utils.test.js" in combined_ui and "openRulesVideoModal" in combined_ui:
            tasks.append(
                _make_task(
                    title="Fix failing frontend unit test in site_ui/tests/test_utils.test.js (openRulesVideoModal iframe src reset)",
                    objective=(
                        "Vitest reported a failure in `site_ui/tests/test_utils.test.js` -> "
                        "`openRulesVideoModal falls back gracefully to YouTube search when no video URL exists` "
                        "(JSDOM resolves `iframe.src = ''` to `http://localhost:3000/`)."
                    ),
                    owned_paths=["site_ui/assets/js/utils.js", "site_ui/tests/test_utils.test.js"],
                    forbidden_paths=["infrastructure/", "bgg_recommender/"],
                    acceptance_criteria=[
                        "Ensure openRulesVideoModal clears the iframe src attribute cleanly when rules_video_url is null or missing",
                        "All Vitest unit tests in site_ui/tests/ pass with exit code 0",
                    ],
                    verification_commands=["npm --prefix site_ui test"],
                    priority="p1",
                    source="test-gap",
                    domains=["site-ui"],
                )
            )
        else:
            failing_files = _extract_failing_vitest_files(combined_ui)
            owned_ui = [f"site_ui/{f}" for f in failing_files] if failing_files else ["site_ui/tests/", "site_ui/assets/js/"]
            tasks.append(
                _make_task(
                    title="Fix failing frontend Vitest unit tests in site_ui/tests/",
                    objective=(
                        f"Live `npm --prefix site_ui test` exited with {ui_proc.returncode}.\n\n"
                        f"Excerpt:\n{combined_ui[-1200:]}"
                    ),
                    owned_paths=owned_ui,
                    forbidden_paths=["infrastructure/", "bgg_recommender/"],
                    acceptance_criteria=[
                        "Fix the failing Vitest test(s) without weakening behavioral coverage",
                        "npm --prefix site_ui test exits 0",
                    ],
                    verification_commands=["npm --prefix site_ui test"],
                    priority="p1",
                    source="test-gap",
                    domains=["site-ui"],
                )
            )

    return tasks


def audit_s3_preview_coverage(
    bucket: str = "boardgame-app",
    max_catalog_age_days: int = 14,
) -> List[Dict[str, Any]]:
    """Inspect S3 `catalog.parquet` freshness and active convention preview ID coverage."""
    import boto3
    import pyarrow.parquet as pq

    tasks: List[Dict[str, Any]] = []
    s3 = boto3.client("s3", region_name="us-east-1")

    head = s3.head_object(Bucket=bucket, Key="data/boardgames_combined/catalog.parquet")
    last_modified = head.get("LastModified")
    if isinstance(last_modified, datetime):
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - last_modified).days
        if age_days > max_catalog_age_days:
            tasks.append(
                _make_task(
                    title="Investigate stale catalog.parquet compaction in S3",
                    objective=(
                        f"s3://{bucket}/data/boardgames_combined/catalog.parquet was last modified "
                        f"{age_days} days ago (threshold: {max_catalog_age_days} days)."
                    ),
                    owned_paths=[
                        "bgg_compactor/combine_raw_to_single_file.py",
                        "tests/test_combine_raw_to_single_file.py",
                    ],
                    forbidden_paths=["site_ui/"],
                    acceptance_criteria=[
                        "Verify weekly EventBridge compaction pipeline and resolve any compaction failure or schema issue",
                        "All compactor unit tests pass",
                    ],
                    verification_commands=["python -m pytest tests/test_combine_raw_to_single_file.py -v"],
                    priority="p1",
                    source="telemetry",
                    domains=["data"],
                )
            )

    preview_obj = s3.get_object(Bucket=bucket, Key="data/active_previews_games.json")
    preview_games = json.loads(preview_obj["Body"].read().decode("utf-8"))

    catalog_obj = s3.get_object(Bucket=bucket, Key="data/boardgames_combined/catalog.parquet")
    catalog_bytes = catalog_obj["Body"].read()
    table = pq.read_table(io.BytesIO(catalog_bytes), columns=["id"])
    catalog_ids = {str(gid).strip() for gid in table.column("id").to_pylist() if gid is not None}

    missing_summary: List[str] = []
    total_missing = 0
    for conv_id, game_ids in sorted(preview_games.items()):
        missing_ids = [str(gid) for gid in game_ids if str(gid).strip() not in catalog_ids]
        if missing_ids:
            total_missing += len(missing_ids)
            missing_summary.append(
                f"{conv_id}: {len(missing_ids)}/{len(game_ids)} missing (sample: {missing_ids[:5]})"
            )

    if total_missing > 0:
        tasks.append(
            _make_task(
                title="Enqueue missing convention preview game IDs for scraping in bgg_preview_refresh",
                objective=(
                    f"Found {total_missing} active convention preview game ID(s) missing from "
                    f"s3://{bucket}/data/boardgames_combined/catalog.parquet:\n- "
                    + "\n- ".join(missing_summary)
                    + "\n\nUpdate bgg_preview_refresh/bgg_preview_refresh.py so newly discovered or "
                    "uncataloged preview game IDs can be enqueued to GAME_SQS_QUEUE_URL for ingestion."
                ),
                owned_paths=[
                    "bgg_preview_refresh/bgg_preview_refresh.py",
                    "tests/test_bgg_preview_refresh.py",
                ],
                forbidden_paths=["site_ui/"],
                acceptance_criteria=[
                    "When GAME_SQS_QUEUE_URL is set in environment, bgg_preview_refresh enqueues newly discovered preview game IDs in batches so they are scraped into the catalog",
                    "Unit tests in tests/test_bgg_preview_refresh.py cover SQS batch enqueueing and graceful no-op when GAME_SQS_QUEUE_URL is unset",
                ],
                verification_commands=["python -m pytest tests/test_bgg_preview_refresh.py -v"],
                priority="p2",
                source="telemetry",
                domains=["bgg-api", "data"],
            )
        )

    return tasks


def collect_all_tasks(
    repo_root: str = ".",
    run_tests: bool = False,
    check_s3: bool = False,
    bucket: str = "boardgame-app",
    max_catalog_age_days: int = 14,
) -> List[Dict[str, Any]]:
    """Run enabled audits and return all discovered structured task specs."""
    tasks: List[Dict[str, Any]] = []
    tasks.extend(audit_contract_drift(repo_root=repo_root))
    tasks.extend(audit_test_suites(repo_root=repo_root, run_tests=run_tests))
    if check_s3:
        tasks.extend(audit_s3_preview_coverage(bucket=bucket, max_catalog_age_days=max_catalog_age_days))
    return tasks


def publish_discovered_tasks(
    tasks: List[Dict[str, Any]],
    repo: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Publish discovered tasks as deduplicated GitHub Issues via `agent_backlog.create_task_issue`."""
    results: List[Dict[str, Any]] = []
    for task in tasks:
        res = agent_backlog.create_task_issue(
            title=task["title"],
            objective=task["objective"],
            owned_paths=task["owned_paths"],
            forbidden_paths=task["forbidden_paths"],
            acceptance_criteria=task["acceptance_criteria"],
            verification_commands=task["verification_commands"],
            priority=task.get("priority", "p2"),
            source=task.get("source", "telemetry"),
            domains=task.get("domains", []),
            repo=repo,
        )
        results.append(res)
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit system health/gaps and generate GitHub Issue tasks")
    parser.add_argument("--repo-root", default=".", help="Path to repository root")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--bucket", default="boardgame-app", help="S3 data lake bucket name")
    parser.add_argument("--max-catalog-age-days", type=int, default=14)
    parser.add_argument("--run-tests", action="store_true", help="Run live pytest and Vitest suites")
    parser.add_argument("--s3", action="store_true", help="Audit S3 catalog freshness and preview coverage")
    parser.add_argument("--publish", action="store_true", help="Create deduplicated GitHub Issues for discovered tasks")
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    tasks = collect_all_tasks(
        repo_root=args.repo_root,
        run_tests=args.run_tests,
        check_s3=args.s3,
        bucket=args.bucket,
        max_catalog_age_days=args.max_catalog_age_days,
    )

    published: List[Dict[str, Any]] = []
    if args.publish and tasks:
        published = publish_discovered_tasks(tasks, repo=args.repo)

    if args.json:
        print(json.dumps({"tasks": tasks, "published": published}, indent=2))
    else:
        print(f"Discovered {len(tasks)} task(s):")
        for idx, t in enumerate(tasks, 1):
            print(f"  {idx}. [{t['priority']} | {t['source']}] {t['title']}")
        if published:
            print("\nGitHub Issue sync results:")
            for item in published:
                issue = item["issue"]
                verb = "Matched existing" if item["deduplicated"] else "Created"
                print(f"  - {verb}: #{issue['number']} {issue['title']} ({issue['html_url']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
