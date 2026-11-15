import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts import verify_task


def test_check_path_boundaries_allows_owned_and_ignores_scratch():
    ok, violations = verify_task.check_path_boundaries(
        modified_files=[
            "bgg_recommender/scoring.py",
            "tests/test_bgg_recommender.py",
            "scratch/temp_debug.py",
            ".git/index",
        ],
        owned_paths=["bgg_recommender/", "tests/test_*.py"],
        forbidden_paths=["infrastructure/", "site_ui/"],
    )
    assert ok is True
    assert violations == []


def test_check_path_boundaries_detects_forbidden_and_out_of_scope():
    ok, violations = verify_task.check_path_boundaries(
        modified_files=[
            "bgg_recommender/scoring.py",
            "infrastructure/apigateway/main.tf",
            "site_ui/assets/js/utils.js",
        ],
        owned_paths=["bgg_recommender/"],
        forbidden_paths=["infrastructure/"],
    )
    assert ok is False
    assert len(violations) == 2
    assert any("Forbidden path modified: infrastructure/apigateway/main.tf" in v for v in violations)
    assert any("Out-of-scope file modified" in v and "site_ui/assets/js/utils.js" in v for v in violations)


def test_infer_domain_checks_maps_touched_directories():
    with patch("shutil.which", return_value="C:/Terraform/terraform.exe"):
        checks = verify_task.infer_domain_checks(
            [
                "bgg_recommender/scoring.py",
                "site_ui/recommender/index.html",
                "infrastructure/lambda/main.tf",
            ]
        )
    assert checks == [
        "python -m pytest",
        "npm --prefix site_ui test",
        "terraform -chdir=infrastructure fmt -check",
        "terraform -chdir=infrastructure validate",
    ]

    assert verify_task.infer_domain_checks(["docs/ARCHITECTURE.md"]) == []


def test_verify_task_with_issue_spec_passes_and_fails():
    issue_payload = {
        "number": 42,
        "title": "Add /similar endpoint",
        "spec_error": None,
        "spec": {
            "owned_paths": ["bgg_recommender/scoring.py"],
            "forbidden_paths": ["infrastructure/"],
            "acceptance_criteria": ["Works"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
        },
    }

    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="agent/issue-42"), \
         patch.object(verify_task, "resolve_default_base_ref", return_value="origin/main...HEAD"), \
         patch.object(verify_task, "get_modified_files", return_value=["bgg_recommender/scoring.py"]), \
         patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        exit_code = verify_task.verify_task(issue_number=42)
        assert exit_code == 0
        assert mock_run.call_count == 2  # inferred pytest + explicit test file command

    # Failing boundary check aborts before executing test commands
    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="agent/issue-42"), \
         patch.object(verify_task, "resolve_default_base_ref", return_value="origin/main...HEAD"), \
         patch.object(verify_task, "get_modified_files", return_value=["infrastructure/apigateway/main.tf"]), \
         patch("subprocess.run") as mock_run:
        exit_code = verify_task.verify_task(issue_number=42)
        assert exit_code == 1
        assert mock_run.call_count == 0

    # Failing command returns non-zero
    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="agent/issue-42"), \
         patch.object(verify_task, "resolve_default_base_ref", return_value="origin/main...HEAD"), \
         patch.object(verify_task, "get_modified_files", return_value=["bgg_recommender/scoring.py"]), \
         patch("subprocess.run", return_value=MagicMock(returncode=1)):
        exit_code = verify_task.verify_task(issue_number=42)
        assert exit_code == 1


def test_verify_task_rejects_main_branch():
    issue_payload = {
        "number": 42,
        "title": "Add /similar endpoint",
        "spec_error": None,
        "spec": {
            "owned_paths": ["bgg_recommender/scoring.py"],
            "forbidden_paths": ["infrastructure/"],
            "acceptance_criteria": ["Works"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
        },
    }
    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="main"), \
         patch.object(verify_task, "get_modified_files") as mock_files, \
         patch("subprocess.run") as mock_run:
        exit_code = verify_task.verify_task(issue_number=42)
        assert exit_code == 1
        mock_files.assert_not_called()
        mock_run.assert_not_called()


def test_resolve_default_base_ref_and_committed_diff():
    # origin/main available -> returns "origin/main...HEAD"
    with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
        assert verify_task.resolve_default_base_ref() == "origin/main...HEAD"
        mock_run.assert_called_once()

    # Fallback to main when origin/main missing
    with patch("subprocess.run", side_effect=[MagicMock(returncode=1), MagicMock(returncode=0)]):
        assert verify_task.resolve_default_base_ref() == "main...HEAD"

    # verify_task uses resolve_default_base_ref() when base_ref is omitted and checks committed branch diffs
    issue_payload = {
        "number": 42,
        "title": "Add /similar endpoint",
        "spec_error": None,
        "spec": {
            "owned_paths": ["bgg_recommender/scoring.py"],
            "forbidden_paths": ["infrastructure/"],
            "acceptance_criteria": ["Works"],
            "verification_commands": [],
        },
    }
    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="agent/issue-42"), \
         patch.object(verify_task, "resolve_default_base_ref", return_value="origin/main...HEAD"), \
         patch.object(verify_task, "get_modified_files", return_value=["infrastructure/apigateway/main.tf"]) as mock_files, \
         patch("subprocess.run") as mock_run:
        exit_code = verify_task.verify_task(issue_number=42)
        assert exit_code == 1
        mock_files.assert_called_once_with(base_ref="origin/main...HEAD")
        mock_run.assert_not_called()


def test_verify_task_cwd_restores_original_working_directory(tmp_path):
    orig_cwd = os.getcwd()
    exit_code = verify_task.verify_task(skip_git_check=True, cwd=str(tmp_path))
    assert exit_code == 0
    assert os.getcwd() == orig_cwd


def test_verify_task_writes_markdown_report(tmp_path):
    report_path = tmp_path / "verify-report.md"
    issue_payload = {
        "number": 42,
        "title": "Add /similar endpoint",
        "spec_error": None,
        "spec": {
            "owned_paths": ["bgg_recommender/scoring.py"],
            "forbidden_paths": ["infrastructure/"],
            "acceptance_criteria": ["Works"],
            "verification_commands": ["python -m pytest tests/test_bgg_recommender.py"],
        },
    }

    with patch.object(verify_task.agent_backlog, "get_task_issue", return_value=issue_payload), \
         patch.object(verify_task, "get_current_branch", return_value="agent/issue-42"), \
         patch.object(verify_task, "resolve_default_base_ref", return_value="origin/main...HEAD"), \
         patch.object(verify_task, "get_modified_files", return_value=["bgg_recommender/scoring.py"]), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="12 passed in 0.4s", stderr="")):
        exit_code = verify_task.verify_task(issue_number=42, report_markdown=str(report_path))

    assert exit_code == 0
    content = report_path.read_text(encoding="utf-8")
    assert "`agent/issue-42`" in content
    assert "`python -m pytest tests/test_bgg_recommender.py` | PASS" in content
    assert "12 passed in 0.4s" in content
