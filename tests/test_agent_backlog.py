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


def test_prepare_task_worktree_normalizes_junction_paths(tmp_path):
    repo_root_fwd = str(tmp_path).replace("\\", "/")
    (tmp_path / "site_ui" / "node_modules").mkdir(parents=True)
    wt_dir = tmp_path / "scratch" / "worktrees" / "agent-issue-21"

    recorded_cmds = []

    def fake_run(cmd, **kwargs):
        recorded_cmds.append(cmd)
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return MagicMock(returncode=0, stdout=f"{repo_root_fwd}\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(agent_backlog, "_resolve_base_ref", return_value="origin/main"), \
         patch("subprocess.run", side_effect=fake_run):
        returned = agent_backlog.prepare_task_worktree("agent/issue-21", worktree_path=str(wt_dir))

    assert returned == str(wt_dir).replace("\\", "/")
    assert ["git", "worktree", "add", "-B", "agent/issue-21", str(wt_dir), "origin/main"] in recorded_cmds
    if agent_backlog.os.name == "nt":
        mklink_cmds = [c for c in recorded_cmds if isinstance(c, list) and c[:3] == ["cmd", "/c", "mklink"]]
        assert len(mklink_cmds) == 1
        assert "/" not in mklink_cmds[0][4]
        assert "/" not in mklink_cmds[0][5]


def test_reclaim_stale_in_progress_issues_reclaims_or_marks_review():
    stale_iso = "2026-11-10T00:00:00Z"
    in_progress_items = [
        {
            "number": 11,
            "title": "Stale without PR",
            "updated_at": stale_iso,
            "labels": [{"name": "agent:in-progress"}, {"name": "priority:p1"}],
        },
        {
            "number": 12,
            "title": "Stale with open PR",
            "updated_at": stale_iso,
            "labels": [{"name": "agent:in-progress"}, {"name": "priority:p2"}],
        },
    ]
    patched = {}

    def fake_gh(method, path, payload=None, repo=None, token=None):
        if method == "GET" and path.startswith("/issues?"):
            return in_progress_items
        if method == "GET" and path.startswith("/pulls?"):
            if "agent%2Fissue-12" in path:
                return [{"number": 88, "html_url": "https://example.com/pull/88"}]
            return []
        if method == "PATCH" and path.startswith("/issues/"):
            num = int(path.split("/")[-1])
            patched[num] = payload["labels"]
            return {"number": num, "labels": payload["labels"]}
        if method == "POST" and path.endswith("/comments"):
            return {"id": 1}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        reclaimed = agent_backlog.reclaim_stale_in_progress_issues(
            max_age_hours=6.0, repo="owner/repo", token="tok"
        )

    assert len(reclaimed) == 2
    assert patched[11] == ["priority:p1", "agent:ready"]
    assert patched[12] == ["priority:p2", "agent:review"]


def test_format_task_body_and_update_task_issue_preserve_rich_sections():
    body = agent_backlog.format_task_body(
        objective="Add flight recommendations",
        spec={
            "owned_paths": ["bgg_recommender/scoring.py"],
            "acceptance_criteria": ["Returns 3 courses"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
            "context": "Cafes want a 3-stage game night menu.",
            "examples": ['```json\n{"flight": {"warmup": {}}}\n```'],
            "visuals": ["![Cafe Baseline](https://raw.githubusercontent.com/o/r/screenshots/cafe.png)"],
            "implementation_notes": ["Reuse score_candidates output"],
        },
    )
    assert "## Context & Motivation" in body
    assert "## Examples" in body
    assert "## Visuals & Mockups" in body
    assert "## Implementation Notes" in body
    parsed = agent_backlog.parse_task_spec(body)
    assert parsed["owned_paths"] == ["bgg_recommender/scoring.py"]

    calls = []

    def fake_gh(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/issues/11":
            return {"number": 11, "title": "Game Night Flight", "body": body}
        if method == "PATCH" and path == "/issues/11":
            return {"number": 11, "title": "Game Night Flight", "html_url": "https://example.com/11", "body": payload["body"]}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        updated = agent_backlog.update_task_issue(
            11,
            context="Updated context with metrics",
            examples=["GET /recommendations?flight=true"],
            repo="owner/repo",
            token="tok",
        )
    assert "Updated context with metrics" in updated["body"]
    assert "GET /recommendations?flight=true" in updated["body"]


def test_upload_screenshots_creates_orphan_branch_and_format_pr_body(tmp_path):
    img = tmp_path / "cafe-desktop.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    calls = []

    def fake_gh(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/git/ref/heads/screenshots":
            raise RuntimeError("GitHub API GET ... failed with HTTP 404: Not Found")
        if method == "POST" and path == "/git/blobs":
            return {"sha": f"blob-{len(calls)}"}
        if method == "POST" and path == "/git/trees":
            assert any(e["path"] == "README.md" for e in payload["tree"])
            assert any(e["path"] == "prs/issue-11/cafe-desktop.png" for e in payload["tree"])
            return {"sha": "tree-1"}
        if method == "POST" and path == "/git/commits":
            assert payload["parents"] == []
            return {"sha": "commit-1"}
        if method == "POST" and path == "/git/refs":
            assert payload == {"ref": "refs/heads/screenshots", "sha": "commit-1"}
            return {"ref": "refs/heads/screenshots"}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        uploaded = agent_backlog.upload_screenshots(
            {str(img): "prs/issue-11/cafe-desktop.png"},
            repo="owner/repo",
            token="tok",
        )

    assert len(uploaded) == 1
    assert uploaded[0]["raw_url"] == "https://raw.githubusercontent.com/owner/repo/screenshots/prs/issue-11/cafe-desktop.png"
    assert uploaded[0]["markdown"].startswith("![Cafe Desktop](")

    pr_body = agent_backlog.format_pr_body(
        issue_number=11,
        summary="Added Game Night Flight course builder and UI toggle.",
        changed_files=["M\tbgg_recommender/scoring.py", "M\tsite_ui/cafe/index.html"],
        diff_stat=" 2 files changed, 84 insertions(+)",
        examples=['```json\n{"flight": {"warmup": {"name": "Scout"}}}\n```'],
        verification_results="| `python -m pytest` | PASS |",
        screenshots=[uploaded[0]["markdown"]],
        acceptance_criteria=["Selects 3 distinct games"],
    )
    assert "Closes #11" in pr_body
    assert "## Changes Made" in pr_body
    assert "## Examples" in pr_body
    assert "## Verification & Test Results" in pr_body
    assert "## Screenshots" in pr_body
    assert "https://raw.githubusercontent.com/owner/repo/screenshots/prs/issue-11/cafe-desktop.png" in pr_body
    assert "- [x] Selects 3 distinct games" in pr_body


def test_resolve_base_ref_fails_loudly_when_origin_fetch_fails():
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            return MagicMock(returncode=1, stdout="", stderr="fatal: could not read from remote repository")
        if cmd == ["git", "remote", "get-url", "origin"]:
            return MagicMock(returncode=0, stdout="https://github.com/owner/repo.git\n")
        raise AssertionError(f"Unexpected call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="Failed to fetch latest 'origin/main'"):
            agent_backlog._resolve_base_ref("main")


def test_prepare_task_worktree_rejects_main_checkout_and_cleans_stale_worktree(tmp_path):
    repo_root_fwd = str(tmp_path).replace("\\", "/")
    stale_wt = str(tmp_path / "scratch" / "worktrees" / "old-wt").replace("\\", "/")
    target_wt = str(tmp_path / "scratch" / "worktrees" / "agent-issue-25").replace("\\", "/")

    # Case 1: branch is checked out in the main repo itself -> RuntimeError
    def fake_run_main_conflict(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return MagicMock(returncode=0, stdout=f"{repo_root_fwd}\n")
        if cmd[:3] == ["git", "worktree", "list"]:
            return MagicMock(
                returncode=0,
                stdout=f"worktree {repo_root_fwd}\nHEAD abc\nbranch refs/heads/agent/issue-25\n\n",
            )
        return MagicMock(returncode=0, stdout="")

    with patch.object(agent_backlog, "_resolve_base_ref", return_value="origin/main"), \
         patch("subprocess.run", side_effect=fake_run_main_conflict):
        with pytest.raises(RuntimeError, match="currently checked out in the main repository"):
            agent_backlog.prepare_task_worktree("agent/issue-25", worktree_path=target_wt)

    # Case 2: branch is checked out in another stale worktree -> removed before recreating
    recorded_cmds = []

    def fake_run_stale_wt(cmd, **kwargs):
        recorded_cmds.append(cmd)
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return MagicMock(returncode=0, stdout=f"{repo_root_fwd}\n")
        if cmd[:3] == ["git", "worktree", "list"]:
            return MagicMock(
                returncode=0,
                stdout=(
                    f"worktree {repo_root_fwd}\nHEAD abc\nbranch refs/heads/main\n\n"
                    f"worktree {stale_wt}\nHEAD def\nbranch refs/heads/agent/issue-25\n\n"
                ),
            )
        return MagicMock(returncode=0, stdout="")

    with patch.object(agent_backlog, "_resolve_base_ref", return_value="origin/main"), \
         patch("subprocess.run", side_effect=fake_run_stale_wt):
        out = agent_backlog.prepare_task_worktree("agent/issue-25", worktree_path=target_wt)

    assert out == target_wt
    assert ["git", "worktree", "remove", "--force", stale_wt] in recorded_cmds
    assert ["git", "worktree", "add", "-B", "agent/issue-25", target_wt, "origin/main"] in recorded_cmds


def test_worktree_cli_create_and_remove(capsys, tmp_path):
    wt_path = str(tmp_path / "scratch" / "worktrees" / "agent-feature-proposer").replace("\\", "/")
    with patch.object(agent_backlog, "prepare_task_worktree", return_value=wt_path) as mock_prep:
        rc = agent_backlog.main(["worktree", "--branch", "agent/feature-proposer", "--json"])
    assert rc == 0
    mock_prep.assert_called_once_with("agent/feature-proposer", worktree_path=None, base_branch="main")
    payload = json.loads(capsys.readouterr().out)
    assert payload["worktree_path"] == wt_path

    with patch.object(agent_backlog, "cleanup_task_worktree", return_value=wt_path) as mock_clean:
        rc2 = agent_backlog.main(["worktree", "--branch", "agent/feature-proposer", "--remove", "--delete-branch", "--json"])
    assert rc2 == 0
    mock_clean.assert_called_once_with(worktree_path=None, branch="agent/feature-proposer", delete_branch=True)
    payload2 = json.loads(capsys.readouterr().out)
    assert payload2["removed"] is True
    assert payload2["deleted_branch"] is True


def test_prepare_worktree_and_branch_resume_existing_fetches_remote_branch(tmp_path):
    repo_root_fwd = str(tmp_path).replace("\\", "/")
    wt_dir = tmp_path / "scratch" / "worktrees" / "agent-issue-30"
    recorded_cmds = []

    def fake_run(cmd, **kwargs):
        recorded_cmds.append(cmd)
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return MagicMock(returncode=0, stdout=f"{repo_root_fwd}\n")
        return MagicMock(returncode=0, stdout="")

    with patch.object(agent_backlog, "_resolve_base_ref", return_value="origin/agent/issue-30") as mock_ref, \
         patch("subprocess.run", side_effect=fake_run):
        out = agent_backlog.prepare_task_worktree(
            "agent/issue-30", worktree_path=str(wt_dir), resume_existing=True
        )
    mock_ref.assert_called_once_with(base_branch="agent/issue-30")
    assert out == str(wt_dir).replace("\\", "/")
    assert ["git", "worktree", "add", "-B", "agent/issue-30", str(wt_dir), "origin/agent/issue-30"] in recorded_cmds

    with patch.object(agent_backlog, "_resolve_base_ref", return_value="origin/agent/issue-30") as mock_ref2, \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="")) as mock_run2:
        branch = agent_backlog.prepare_task_branch("agent/issue-30", resume_existing=True)
    assert branch == "agent/issue-30"
    mock_ref2.assert_called_once_with(base_branch="agent/issue-30")
    assert mock_run2.call_args_list[-1].args[0] == [
        "git", "checkout", "-B", "agent/issue-30", "origin/agent/issue-30"
    ]


def test_list_review_queue_filters_pending_reviewed_and_in_progress():
    prs = [
        {
            "number": 101,
            "title": "PR pending CI",
            "html_url": "https://example.com/pull/101",
            "user": {"login": "bot"},
            "head": {"ref": "agent/issue-11", "sha": "sha11"},
            "base": {"ref": "main"},
        },
        {
            "number": 102,
            "title": "PR already reviewed at head",
            "html_url": "https://example.com/pull/102",
            "user": {"login": "bot"},
            "head": {"ref": "agent/issue-12", "sha": "sha12"},
            "base": {"ref": "main"},
        },
        {
            "number": 103,
            "title": "PR ready for review",
            "html_url": "https://example.com/pull/103",
            "user": {"login": "bot"},
            "head": {"ref": "agent/issue-13", "sha": "sha13"},
            "base": {"ref": "main"},
        },
        {
            "number": 104,
            "title": "Human branch PR",
            "html_url": "https://example.com/pull/104",
            "user": {"login": "human"},
            "head": {"ref": "feature/manual", "sha": "sha14"},
            "base": {"ref": "main"},
        },
    ]

    def fake_gh(method, path, payload=None, repo=None, token=None, accept=None):
        if path.startswith("/pulls?"):
            return prs
        if path == "/issues/11":
            return {"number": 11, "title": "Issue 11", "state": "open", "labels": [{"name": "agent:review"}], "body": ""}
        if path == "/issues/12":
            return {"number": 12, "title": "Issue 12", "state": "open", "labels": [{"name": "agent:review"}], "body": ""}
        if path == "/issues/13":
            return {"number": 13, "title": "Issue 13", "state": "open", "labels": [{"name": "agent:review"}, {"name": "priority:p1"}], "body": ""}
        if path.startswith("/pulls/101/reviews"):
            return []
        if path.startswith("/pulls/102/reviews"):
            return [{"id": 1, "state": "COMMENTED", "commit_id": "sha12", "body": "<!-- agent-review:event=APPROVE sha=sha12 -->", "user": {"login": "bot"}}]
        if path.startswith("/pulls/103/reviews"):
            return []
        if path.startswith("/commits/sha11/check-runs"):
            return {"check_runs": [{"name": "PR Merge Gate", "status": "in_progress", "conclusion": None}]}
        if path.startswith("/commits/sha13/check-runs"):
            return {"check_runs": [{"name": "PR Merge Gate", "status": "completed", "conclusion": "success"}]}
        if path.startswith("/pulls/103/files"):
            return [{"filename": "scripts/agent_backlog.py", "status": "modified", "additions": 5, "deletions": 1, "patch": "@@ -1 +1 @@"}]
        if path == "/pulls/103" and accept == "application/vnd.github.v3.diff":
            return "diff --git a/scripts/agent_backlog.py b/scripts/agent_backlog.py\n"
        raise AssertionError(f"Unexpected call: {method} {path} accept={accept}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        queue = agent_backlog.list_review_queue(include_diff=True, repo="owner/repo", token="tok")

    assert [q["pr_number"] for q in queue] == [103]
    assert queue[0]["issue_number"] == 13
    assert queue[0]["ci_status"]["overall"] == "success"
    assert "diff --git" in queue[0]["diff"]


def test_submit_pr_review_transitions_issue_handles_self_review_422_and_circuit_breaker():
    posted_reviews = []
    issue_labels = ["agent:review", "priority:p1"]
    issue_comments = []

    # Case 1: Native REQUEST_CHANGES transitions issue to agent:changes-requested
    def fake_gh_native(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "GET" and path == "/pulls/50":
            return {"number": 50, "head": {"ref": "agent/issue-20", "sha": "sha20"}}
        if method == "GET" and path.startswith("/pulls/50/reviews"):
            return []
        if method == "POST" and path == "/pulls/50/reviews":
            posted_reviews.append(payload)
            return {"id": 900, **payload}
        if method == "GET" and path == "/issues/20":
            return {"number": 20, "labels": [{"name": l} for l in issue_labels]}
        if method == "PATCH" and path == "/issues/20":
            issue_labels[:] = payload["labels"]
            return {"number": 20, "labels": payload["labels"]}
        if method == "POST" and path == "/issues/20/comments":
            issue_comments.append(payload["body"])
            return {"id": 1}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh_native):
        res = agent_backlog.submit_pr_review(
            50,
            event="REQUEST_CHANGES",
            body="Missing edge-case test.",
            comments=[{"path": "bgg_recommender/scoring.py", "line": 12, "side": "RIGHT", "body": "Guard empty list"}],
            repo="owner/repo",
            token="reviewer-tok",
        )
    assert res["issue_status"] == "agent:changes-requested"
    assert res["used_marker_fallback"] is False
    assert "agent:changes-requested" in issue_labels
    assert posted_reviews[0]["event"] == "REQUEST_CHANGES"

    # Case 2: Single-PAT 422 self-review falls back to COMMENT with marker and sets agent:approved
    posted_reviews.clear()
    issue_labels[:] = ["agent:review", "priority:p1"]

    def fake_gh_self_422(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "POST" and path == "/pulls/50/reviews" and payload["event"] == "APPROVE":
            raise RuntimeError("GitHub API POST ... failed with HTTP 422: {\"errors\":[\"Can not approve your own pull request\"]}")
        return fake_gh_native(method, path, payload=payload, repo=repo, token=token, accept=accept)

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh_self_422):
        res2 = agent_backlog.submit_pr_review(
            50,
            event="APPROVE",
            body="Looks clean!",
            repo="owner/repo",
            token="same-pat",
        )
    assert res2["used_marker_fallback"] is True
    assert res2["issue_status"] == "agent:approved"
    assert "agent:approved" in issue_labels
    assert posted_reviews[0]["event"] == "COMMENT"
    assert "<!-- agent-review:event=APPROVE sha=sha20 -->" in posted_reviews[0]["body"]

    # Case 3: Circuit breaker blocks issue when exceeding max_rework_rounds
    posted_reviews.clear()
    issue_labels[:] = ["agent:review", "priority:p1"]

    def fake_gh_breaker(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "GET" and path.startswith("/pulls/50/reviews"):
            return [
                {"id": 1, "state": "CHANGES_REQUESTED", "commit_id": "s1", "user": {"login": "rev"}},
                {"id": 2, "state": "CHANGES_REQUESTED", "commit_id": "s2", "user": {"login": "rev"}},
                {"id": 3, "state": "CHANGES_REQUESTED", "commit_id": "s3", "user": {"login": "rev"}},
            ]
        return fake_gh_native(method, path, payload=payload, repo=repo, token=token, accept=accept)

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh_breaker):
        res3 = agent_backlog.submit_pr_review(
            50,
            event="REQUEST_CHANGES",
            body="Still failing unit tests.",
            max_rework_rounds=3,
            repo="owner/repo",
            token="rev-tok",
        )
    assert res3["circuit_breaker_tripped"] is True
    assert res3["issue_status"] == "agent:blocked"
    assert "agent:blocked" in issue_labels


def test_sync_pr_review_status_and_get_next_task_prioritizes_rework(capsys):
    issue_labels = ["agent:review", "priority:p2"]

    def fake_gh_sync(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "GET" and path == "/pulls/77":
            return {"number": 77, "head": {"ref": "agent/issue-31", "sha": "sha31"}}
        if method == "GET" and path == "/issues/31":
            return {"number": 31, "labels": [{"name": l} for l in issue_labels]}
        if method == "GET" and path.startswith("/pulls/77/reviews"):
            return [{"id": 1, "state": "CHANGES_REQUESTED", "commit_id": "sha31", "user": {"login": "human"}, "body": "Fix null check"}]
        if method == "PATCH" and path == "/issues/31":
            issue_labels[:] = payload["labels"]
            return {"number": 31, "labels": payload["labels"]}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh_sync):
        synced = agent_backlog.sync_pr_review_status(77, repo="owner/repo", token="tok")
    assert synced["synced"] is True
    assert synced["status"] == "agent:changes-requested"

    spec_body = agent_backlog.format_task_body(
        objective="Handle null rating",
        spec={
            "owned_paths": ["bgg_recommender/scoring.py"],
            "acceptance_criteria": ["Handles None cleanly"],
            "verification_commands": ["python -m pytest"],
        },
    )

    def fake_gh_next(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "GET" and path.startswith("/pulls?"):
            return [{"number": 77, "title": "Fix rating", "html_url": "https://example.com/pull/77", "head": {"ref": "agent/issue-31", "sha": "sha31"}, "base": {"ref": "main"}}]
        if method == "GET" and path == "/issues/31":
            return {
                "number": 31,
                "title": "Handle null rating",
                "state": "open",
                "html_url": "https://example.com/issues/31",
                "labels": [{"name": l} for l in issue_labels],
                "body": spec_body,
            }
        if method == "GET" and path == "/pulls/77":
            return {"number": 77, "title": "Fix rating", "html_url": "https://example.com/pull/77", "head": {"ref": "agent/issue-31", "sha": "sha31"}, "base": {"ref": "main"}}
        if method == "GET" and path.startswith("/pulls/77/reviews"):
            return [{"id": 1, "state": "CHANGES_REQUESTED", "commit_id": "sha31", "user": {"login": "human"}, "body": "Please guard None"}]
        if method == "GET" and path.startswith("/pulls/77/comments"):
            return [{"id": 5, "user": {"login": "human"}, "path": "bgg_recommender/scoring.py", "line": 19, "body": "Use `or 0.0`", "diff_hunk": "@@", "in_reply_to_id": None}]
        if method == "GET" and path.startswith("/issues/77/comments"):
            return []
        if method == "GET" and path.startswith("/pulls/77/files"):
            return [{"filename": "bgg_recommender/scoring.py", "status": "modified", "additions": 2, "deletions": 1}]
        if method == "GET" and path.startswith("/commits/sha31/check-runs"):
            return {"check_runs": []}
        if method == "PATCH" and path == "/issues/31":
            issue_labels[:] = payload["labels"]
            return {"number": 31, "labels": payload["labels"]}
        if method == "POST" and path == "/issues/31/comments":
            return {"id": 88}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh_next), \
         patch.object(agent_backlog, "get_github_token", return_value="tok"), \
         patch.object(agent_backlog, "detect_repo_slug", return_value="owner/repo"), \
         patch.object(agent_backlog, "prepare_task_worktree", return_value="D:/repo/scratch/worktrees/agent-issue-31") as mock_wt:
        rc = agent_backlog.main(["next", "--claim", "--worktree", "--json"])

    assert rc == 0
    mock_wt.assert_called_once_with("agent/issue-31", resume_existing=True)
    out_payload = json.loads(capsys.readouterr().out)
    assert out_payload["number"] == 31
    assert out_payload["rework"] is True
    assert out_payload["claimed"] is True
    assert out_payload["pr_feedback"]["inline_comments"][0]["line"] == 19
    assert "agent:in-progress" in issue_labels


def test_complete_task_issue_posts_rework_comment_on_existing_pr():
    pr_comments = []

    def fake_gh(method, path, payload=None, repo=None, token=None, accept=None):
        if method == "GET" and path == "/issues/31":
            return {"number": 31, "title": "Fix rating", "labels": [{"name": "agent:in-progress"}]}
        if method == "PATCH" and path == "/issues/31":
            return {"number": 31, "html_url": "https://example.com/31", "state": "open", "labels": payload["labels"]}
        if method == "GET" and path.startswith("/pulls?"):
            return [{"number": 77, "html_url": "https://example.com/pull/77"}]
        if method == "POST" and path == "/issues/77/comments":
            pr_comments.append(payload["body"])
            return {"id": 201}
        if method == "POST" and path == "/issues/31/comments":
            return {"id": 202}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(agent_backlog, "github_request", side_effect=fake_gh):
        updated = agent_backlog.complete_task_issue(
            31,
            summary="Added None guard as requested.",
            pr="agent/issue-31",
            open_pr=True,
            verification_results="| `pytest` | PASS |",
            repo="owner/repo",
            token="tok",
        )
    assert updated["labels"] == ["agent:review"]
    assert len(pr_comments) == 1
    assert "Added None guard as requested." in pr_comments[0]


def test_submit_review_cli_parses_inline_comments(capsys):
    with patch.object(
        agent_backlog,
        "submit_pr_review",
        return_value={"pr_number": 9, "issue_number": 4, "event": "REQUEST_CHANGES", "issue_status": "agent:changes-requested"},
    ) as mock_sub:
        rc = agent_backlog.main([
            "submit-review", "9",
            "--event", "request_changes",
            "--body", "Needs test",
            "--comment", "scripts/agent_backlog.py:10:Add docstring",
            "--json",
        ])
    assert rc == 0
    mock_sub.assert_called_once()
    call_kwargs = mock_sub.call_args.kwargs
    assert call_kwargs["event"] == "request_changes"
    assert call_kwargs["comments"] == [{
        "path": "scripts/agent_backlog.py",
        "line": 10,
        "side": "RIGHT",
        "body": "Add docstring",
    }]
    assert json.loads(capsys.readouterr().out)["issue_status"] == "agent:changes-requested"
