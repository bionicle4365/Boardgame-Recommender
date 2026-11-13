import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts import agent_backlog, audit_and_generate_tasks


def test_audit_contract_drift_clean_and_mismatch(tmp_path):
    # Clean repository should have zero contract drift
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assert audit_and_generate_tasks.audit_contract_drift(repo_root=repo_root) == []

    # Simulate drift in a temporary repo layout
    (tmp_path / "docs" / "contracts").mkdir(parents=True)
    (tmp_path / "infrastructure" / "apigateway").mkdir(parents=True)
    (tmp_path / "bgg_compactor").mkdir(parents=True)

    (tmp_path / "docs" / "contracts" / "schemas_and_routes.json").write_text(
        json.dumps(
            {
                "api_routes": [{"method": "GET", "path": "/recommendations"}],
                "parquet_schemas": {"catalog": {"columns": [{"name": "id", "type": "string"}]}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "infrastructure" / "apigateway" / "main.tf").write_text(
        'resource "aws_apigatewayv2_route" "a" {\n  route_key = "GET /recommendations"\n}\n'
        'resource "aws_apigatewayv2_route" "b" {\n  route_key = "GET /similar"\n}\n',
        encoding="utf-8",
    )
    (tmp_path / "bgg_compactor" / "combine_raw_to_single_file.py").write_text(
        "TARGET_SCHEMA = pa.schema([\n    ('id', pa.string()),\n    ('name', pa.string())\n])\n",
        encoding="utf-8",
    )

    tasks = audit_and_generate_tasks.audit_contract_drift(repo_root=str(tmp_path))
    assert len(tasks) == 1
    task = tasks[0]
    assert task["source"] == "data-drift"
    assert task["priority"] == "p1"
    assert "GET" in task["objective"] and "/similar" in task["objective"]
    assert "name" in task["objective"]
    agent_backlog.validate_task_spec(task)


def test_audit_test_suites_detects_vitest_failure():
    def fake_run(cmd, **kwargs):
        if "pytest" in cmd:
            return MagicMock(returncode=0, stdout="267 passed", stderr="")
        if "site_ui" in cmd:
            return MagicMock(
                returncode=1,
                stdout="FAIL tests/test_utils.test.js > openRulesVideoModal falls back gracefully",
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with patch("subprocess.run", side_effect=fake_run):
        tasks = audit_and_generate_tasks.audit_test_suites(repo_root=repo_root, run_tests=True)

    assert len(tasks) == 1
    task = tasks[0]
    assert task["source"] == "test-gap"
    assert task["priority"] == "p1"
    assert task["domains"] == ["site-ui"]
    assert "site_ui/tests/test_utils.test.js" in task["owned_paths"]
    assert task["verification_commands"] == ["npm --prefix site_ui test"]
    agent_backlog.validate_task_spec(task)


def test_audit_s3_preview_coverage_detects_missing_preview_games():
    table = pa.table({"id": pa.array(["13", "266192"], type=pa.string())})
    buf = io.BytesIO()
    pq.write_table(table, buf)
    parquet_bytes = buf.getvalue()

    preview_payload = json.dumps({"paxunplugged2026": ["13", "999999"]}).encode("utf-8")

    fake_s3 = MagicMock()
    fake_s3.head_object.return_value = {
        "LastModified": datetime.now(timezone.utc) - timedelta(days=2)
    }

    def fake_get_object(Bucket, Key):
        body = MagicMock()
        if Key == "data/active_previews_games.json":
            body.read.return_value = preview_payload
        elif Key == "data/boardgames_combined/catalog.parquet":
            body.read.return_value = parquet_bytes
        else:
            raise AssertionError(f"Unexpected S3 key: {Key}")
        return {"Body": body}

    fake_s3.get_object.side_effect = fake_get_object

    with patch("boto3.client", return_value=fake_s3):
        tasks = audit_and_generate_tasks.audit_s3_preview_coverage(bucket="boardgame-app")

    assert len(tasks) == 1
    task = tasks[0]
    assert task["source"] == "telemetry"
    assert task["priority"] == "p2"
    assert "paxunplugged2026" in task["objective"]
    assert "999999" in task["objective"]
    assert "bgg_preview_refresh/bgg_preview_refresh.py" in task["owned_paths"]
    agent_backlog.validate_task_spec(task)


def test_publish_discovered_tasks_calls_backlog_create():
    sample_task = {
        "title": "Sample Task",
        "objective": "Do work",
        "owned_paths": ["bgg_preview_refresh/bgg_preview_refresh.py"],
        "forbidden_paths": ["site_ui/"],
        "acceptance_criteria": ["Works"],
        "verification_commands": ["python -m pytest tests/test_bgg_preview_refresh.py"],
        "priority": "p2",
        "source": "telemetry",
        "domains": ["bgg-api"],
    }

    with patch.object(
        audit_and_generate_tasks.agent_backlog,
        "create_task_issue",
        return_value={"deduplicated": False, "issue": {"number": 3, "title": "Sample Task", "html_url": "https://example.com/3"}},
    ) as mock_create:
        results = audit_and_generate_tasks.publish_discovered_tasks([sample_task], repo="owner/repo")

    assert len(results) == 1
    assert results[0]["issue"]["number"] == 3
    mock_create.assert_called_once()
