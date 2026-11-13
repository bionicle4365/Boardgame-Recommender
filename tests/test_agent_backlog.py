import io
import json
import os
import sys
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts import agent_backlog


def _mock_http_response(payload, status=200):
    raw = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = raw
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_validate_task_spec_defaults_and_normalization():
    spec = agent_backlog.validate_task_spec(
        {
            "owned_paths": [r"bgg_recommender\scoring.py", "tests/test_bgg_recommender.py"],
            "acceptance_criteria": ["Returns top 10 similar games"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
        }
    )
    assert spec["owned_paths"] == ["bgg_recommender/scoring.py", "tests/test_bgg_recommender.py"]
    assert spec["forbidden_paths"] == ["infrastructure/"]
    assert spec["acceptance_criteria"] == ["Returns top 10 similar games"]
    assert spec["verification_commands"] == ["python -m pytest tests/test_bgg_recommender.py"]


def test_validate_task_spec_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="owned_paths"):
        agent_backlog.validate_task_spec(
            {"owned_paths": [], "acceptance_criteria": ["x"], "verification_commands": ["pytest"]}
        )
    with pytest.raises(ValueError, match="acceptance_criteria"):
        agent_backlog.validate_task_spec(
            {"owned_paths": ["a.py"], "acceptance_criteria": [], "verification_commands": ["pytest"]}
        )
    with pytest.raises(ValueError, match="verification_commands"):
        agent_backlog.validate_task_spec(
            {"owned_paths": ["a.py"], "acceptance_criteria": ["x"], "verification_commands": []}
        )


def test_format_and_parse_task_spec_round_trip():
    body = agent_backlog.format_task_body(
        objective="Implement Jaccard similarity helper",
        spec={
            "owned_paths": ["bgg_recommender/scoring.py", "tests/test_bgg_recommender.py"],
            "forbidden_paths": ["infrastructure/", "site_ui/"],
            "acceptance_criteria": ["Returns top N sorted matches"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
        },
    )
    parsed = agent_backlog.parse_task_spec(body)
    assert parsed["owned_paths"] == ["bgg_recommender/scoring.py", "tests/test_bgg_recommender.py"]
    assert parsed["forbidden_paths"] == ["infrastructure/", "site_ui/"]
    assert parsed["acceptance_criteria"] == ["Returns top N sorted matches"]
    assert parsed["verification_commands"] == ["python -m pytest tests/test_bgg_recommender.py"]


def test_parse_task_spec_markdown_form_fallback():
    form_body = """### Objective
Add similar route

### Owned Paths
bgg_recommender/bgg_recommender.py
tests/test_bgg_recommender.py

### Forbidden Paths
infrastructure/

### Acceptance Criteria
- Returns HTTP 200 for valid game_id

### Verification Commands
`python -m pytest tests/test_bgg_recommender.py`
"""
    parsed = agent_backlog.parse_task_spec(form_body)
    assert parsed["owned_paths"] == ["bgg_recommender/bgg_recommender.py", "tests/test_bgg_recommender.py"]
    assert parsed["forbidden_paths"] == ["infrastructure/"]
    assert parsed["acceptance_criteria"] == ["Returns HTTP 200 for valid game_id"]
    assert parsed["verification_commands"] == ["python -m pytest tests/test_bgg_recommender.py"]


def test_github_request_sends_auth_and_wraps_http_error():
    with patch("urllib.request.urlopen", return_value=_mock_http_response({"ok": True})) as mock_open:
        res = agent_backlog.github_request(
            "POST",
            "/labels",
            payload={"name": "agent:ready"},
            repo="owner/repo",
            token="secret-token",
        )
        assert res == {"ok": True}
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://api.github.com/repos/owner/repo/labels"
        assert req.get_method() == "POST"
        assert req.get_header("Authorization") == "Bearer secret-token"

    err = urllib.error.HTTPError(
        url="https://api.github.com/repos/owner/repo/issues",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(b'{"message":"Forbidden"}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="HTTP 403"):
            agent_backlog.github_request("GET", "/issues", repo="owner/repo", token="secret-token")


def test_create_task_issue_deduplicates_open_issues():
    existing_issue = {"number": 12, "title": "Add Similar Games Endpoint", "html_url": "https://example.com/12"}
    with patch.object(agent_backlog, "github_request", return_value=[existing_issue]) as mock_req:
        res = agent_backlog.create_task_issue(
            title="  add similar games endpoint ",
            objective="Objective",
            owned_paths=["bgg_recommender/scoring.py"],
            acceptance_criteria=["Works"],
            verification_commands=["python -m pytest"],
            repo="owner/repo",
            token="tok",
        )
        assert res["deduplicated"] is True
        assert res["issue"]["number"] == 12
        assert mock_req.call_count == 1


def test_create_task_issue_creates_with_standard_labels():
    def fake_req(method, path, payload=None, repo=None, token=None):
        if method == "GET" and path.startswith("/issues?"):
            return []
        if method == "POST" and path == "/issues":
            return {"number": 1, "title": payload["title"], "labels": payload["labels"], "html_url": "https://example.com/1"}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        res = agent_backlog.create_task_issue(
            title="New Task",
            objective="Implement feature",
            owned_paths=["bgg_recommender/scoring.py"],
            acceptance_criteria=["Passes pytest"],
            verification_commands=["python -m pytest"],
            priority="p1",
            source="roadmap",
            domains=["recommender"],
            repo="owner/repo",
            token="tok",
        )
        assert res["deduplicated"] is False
        assert res["issue"]["labels"] == ["agent:proposed", "priority:p1", "source:roadmap", "domain:recommender"]


def test_list_task_issues_sorts_by_priority_and_filters_prs():
    raw_items = [
        {"number": 3, "title": "Low", "labels": [{"name": "priority:p3"}]},
        {"number": 2, "title": "PR item", "labels": [{"name": "priority:p1"}], "pull_request": {}},
        {"number": 5, "title": "High", "labels": [{"name": "priority:p1"}]},
        {"number": 4, "title": "Med", "labels": [{"name": "priority:p2"}]},
    ]
    with patch.object(agent_backlog, "github_request", return_value=raw_items):
        issues = agent_backlog.list_task_issues(status="ready", repo="owner/repo", token="tok")
        assert [i["number"] for i in issues] == [5, 4, 3]


def test_claim_and_complete_transition_labels_and_post_comments():
    calls = []

    def fake_req(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/7":
            return {
                "number": 7,
                "labels": [{"name": "agent:ready"}, {"name": "priority:p1"}],
            }
        if method == "PATCH" and path == "/issues/7":
            return {"number": 7, "html_url": "https://example.com/7", "state": payload.get("state", "open"), "labels": payload["labels"]}
        if method == "POST" and path == "/issues/7/comments":
            return {"id": 99}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        claimed = agent_backlog.claim_task_issue(7, agent_name="worker-1", branch="agent/7", repo="owner/repo", token="tok")
        assert claimed["labels"] == ["priority:p1", "agent:in-progress"]
        assert any(c[0] == "POST" and "worker-1" in c[2]["body"] for c in calls)

    calls.clear()
    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        completed = agent_backlog.complete_task_issue(
            7, summary="All checks pass", pr="agent/7", close=True, repo="owner/repo", token="tok"
        )
        assert completed["labels"] == ["priority:p1", "agent:review"]
        assert completed["state"] == "closed"
        assert any(c[0] == "POST" and "All checks pass" in c[2]["body"] for c in calls)


def test_approve_and_claim_guard_workflow():
    state = {"labels": ["agent:proposed", "priority:p1"], "comments": []}

    def fake_req(method, path, payload=None, repo=None, token=None):
        if method == "GET" and path == "/issues/10":
            return {
                "number": 10,
                "labels": [{"name": lbl} for lbl in state["labels"]],
            }
        if method == "PATCH" and path == "/issues/10":
            state["labels"] = list(payload["labels"])
            return {"number": 10, "html_url": "https://example.com/10", "labels": state["labels"]}
        if method == "POST" and path == "/issues/10/comments":
            state["comments"].append(payload["body"])
            return {"id": len(state["comments"])}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        with pytest.raises(ValueError, match="not approved for execution"):
            agent_backlog.claim_task_issue(10, agent_name="worker-1", repo="owner/repo", token="tok")

        approved = agent_backlog.approve_task_issue(10, repo="owner/repo", token="tok")
        assert approved["labels"] == ["priority:p1", "agent:ready"]
        assert any("agent:ready" in c for c in state["comments"])

        claimed = agent_backlog.claim_task_issue(10, agent_name="worker-1", branch="agent/10", repo="owner/repo", token="tok")
        assert claimed["labels"] == ["priority:p1", "agent:in-progress"]


def test_init_repo_enables_issues_and_creates_missing_labels():
    created_labels = []

    def fake_req(method, path, payload=None, repo=None, token=None):
        if method == "PATCH" and path == "":
            assert payload == {"has_issues": True}
            return {"has_issues": True}
        if method == "GET" and path.startswith("/labels"):
            return [
                {"name": "agent:ready", "color": "0E8A16", "description": agent_backlog.STANDARD_LABELS["agent:ready"][1]}
            ]
        if method == "POST" and path == "/labels":
            created_labels.append(payload["name"])
            return payload
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        res = agent_backlog.init_repo(repo="owner/repo", token="tok")
        assert res["has_issues"] is True
        assert res["labels_created"] == len(agent_backlog.STANDARD_LABELS) - 1
        assert "agent:ready" not in created_labels


def test_get_next_ready_issue_returns_top_priority_with_branch():
    with patch.object(agent_backlog, "github_request", return_value=[]):
        assert agent_backlog.get_next_ready_issue(repo="owner/repo", token="tok") is None

    spec_body = agent_backlog.format_task_body(
        objective="Implement /similar",
        spec={
            "owned_paths": ["bgg_recommender/bgg_recommender.py"],
            "acceptance_criteria": ["Returns top 10"],
            "verification_commands": ["python -m pytest"],
        },
    )
    list_items = [
        {"number": 9, "title": "Low priority", "labels": [{"name": "agent:ready"}, {"name": "priority:p3"}]},
        {"number": 5, "title": "High priority", "labels": [{"name": "agent:ready"}, {"name": "priority:p1"}]},
    ]

    def fake_req(method, path, payload=None, repo=None, token=None):
        if method == "GET" and path.startswith("/issues?"):
            return list_items
        if method == "GET" and path == "/issues/5":
            return {
                "number": 5,
                "title": "High priority",
                "state": "open",
                "html_url": "https://example.com/5",
                "labels": [{"name": "agent:ready"}, {"name": "priority:p1"}],
                "body": spec_body,
            }
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        task = agent_backlog.get_next_ready_issue(repo="owner/repo", token="tok")
        assert task is not None
        assert task["number"] == 5
        assert task["branch"] == "agent/issue-5"
        assert task["spec"]["owned_paths"] == ["bgg_recommender/bgg_recommender.py"]


def test_complete_task_issue_with_open_pr_creates_github_pr():
    calls = []

    def fake_req(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/7":
            return {
                "number": 7,
                "title": "Fix iframe src test",
                "labels": [{"name": "agent:in-progress"}, {"name": "priority:p1"}],
            }
        if method == "PATCH" and path == "/issues/7":
            return {"number": 7, "html_url": "https://example.com/7", "state": "open", "labels": payload["labels"]}
        if method == "GET" and path.startswith("/pulls?"):
            return []
        if method == "POST" and path == "/pulls":
            assert payload["head"] == "agent/issue-7"
            assert payload["base"] == "main"
            assert "Closes #7" in payload["body"]
            return {"number": 42, "html_url": "https://example.com/pull/42"}
        if method == "POST" and path == "/issues/7/comments":
            return {"id": 101}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_req):
        completed = agent_backlog.complete_task_issue(
            7,
            summary="Verified unit test fix",
            pr="agent/issue-7",
            open_pr=True,
            repo="owner/repo",
            token="tok",
        )
        assert completed["labels"] == ["priority:p1", "agent:review"]
        assert completed["pull_request"]["html_url"] == "https://example.com/pull/42"
        comment_calls = [c for c in calls if c[0] == "POST" and c[1] == "/issues/7/comments"]
        assert len(comment_calls) == 1
        assert "https://example.com/pull/42" in comment_calls[0][2]["body"]


def test_validate_and_push_agent_branch_blocks_main():
    for bad in ("main", "master", "feature/foo", ""):
        with pytest.raises(ValueError, match="agent/"):
            agent_backlog.validate_agent_branch(bad)

    assert agent_backlog.validate_agent_branch(" agent/issue-7 ") == "agent/issue-7"

    with pytest.raises(ValueError, match="agent/"):
        agent_backlog.claim_task_issue(7, agent_name="worker-1", branch="main", repo="owner/repo", token="tok")

    with pytest.raises(ValueError, match="agent/"):
        agent_backlog.create_or_get_pull_request(
            7, head_branch="main", base_branch="main", repo="owner/repo", token="tok"
        )

    with pytest.raises(ValueError, match="target 'main'"):
        agent_backlog.create_or_get_pull_request(
            7, head_branch="agent/issue-7", base_branch="master", repo="owner/repo", token="tok"
        )

    with patch.object(agent_backlog, "get_current_git_branch", return_value="main"), \
         patch("subprocess.run") as mock_run:
        with pytest.raises(ValueError, match="protected branch 'main'"):
            agent_backlog.push_task_branch("agent/issue-7")
        mock_run.assert_not_called()

    with patch.object(agent_backlog, "get_current_git_branch", return_value="agent/issue-7"), \
         patch("subprocess.run") as mock_run:
        pushed = agent_backlog.push_task_branch("agent/issue-7")
        assert pushed == "agent/issue-7"
        mock_run.assert_called_once_with(
            ["git", "push", "-u", "origin", "agent/issue-7:agent/issue-7"],
            check=True,
        )


def test_block_task_issue_and_prepare_task_branch_guard():
    # Dirty working tree blocks in-place checkout
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=" M scripts/agent_backlog.py\n")):
        with pytest.raises(RuntimeError, match="uncommitted changes"):
            agent_backlog.prepare_task_branch("agent/issue-19")

    # Clean tree fetches origin/main and checks out branch from origin/main
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # git status --porcelain
            MagicMock(returncode=0, stdout=""),  # git fetch origin main
            MagicMock(returncode=0, stdout="abc123\n"),  # git rev-parse origin/main
            MagicMock(returncode=0, stdout=""),  # git checkout -B agent/issue-19 origin/main
        ]
        branch = agent_backlog.prepare_task_branch("agent/issue-19")
        assert branch == "agent/issue-19"
        assert mock_run.call_args_list[-1].args[0] == [
            "git",
            "checkout",
            "-B",
            "agent/issue-19",
            "origin/main",
        ]

    # block_task_issue sets agent:blocked and posts reason comment
    calls = []

    def fake_gh(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET":
            return {"number": 19, "labels": [{"name": "agent:in-progress"}, {"name": "priority:p2"}]}
        if method == "PATCH":
            return {"number": 19, "labels": [{"name": lbl} for lbl in payload["labels"]]}
        return {"id": 99}

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        updated = agent_backlog.block_task_issue(19, reason="Tests failed after 3 attempts", repo="o/r", token="tok")

    assert [lbl["name"] for lbl in updated["labels"]] == ["priority:p2", "agent:blocked"]
    assert calls[1][0] == "PATCH"
    assert calls[2][0] == "POST"
    assert calls[2][1] == "/issues/19/comments"
    assert "Tests failed after 3 attempts" in calls[2][2]["body"]
