import os
import sys
import urllib.request
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts import capture_ui_screenshots


def test_infer_routes_from_files_maps_pages_and_ignores_tests():
    assert capture_ui_screenshots.infer_routes_from_files(["bgg_recommender/scoring.py", "site_ui/tests/cafe.test.js"]) == []
    assert capture_ui_screenshots.infer_routes_from_files(["site_ui/cafe/index.html", "site_ui/assets/js/cafe.js"]) == ["/cafe/"]
    assert capture_ui_screenshots.infer_routes_from_files(["site_ui/assets/css/style.css"]) == ["/", "/recommender/", "/cafe/"]


def test_serve_directory_serves_static_html(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Meeple Manifesto</h1>", encoding="utf-8")
    with capture_ui_screenshots.serve_directory(str(tmp_path)) as base_url:
        with urllib.request.urlopen(f"{base_url}/index.html", timeout=5) as resp:
            assert resp.status == 200
            assert "Meeple Manifesto" in resp.read().decode("utf-8")


def test_post_pr_screenshot_comment_updates_existing_marker():
    calls = []

    def fake_gh(method, path, payload=None, repo=None, token=None):
        calls.append((method, path, payload))
        if method == "GET":
            return [{"id": 77, "body": f"{capture_ui_screenshots.PR_COMMENT_MARKER}\nold"}]
        if method == "PATCH" and path == "/issues/comments/77":
            return {"id": 77, "body": payload["body"]}
        raise AssertionError(f"Unexpected call: {method} {path}")

    with patch.object(capture_ui_screenshots.agent_backlog, "github_request", side_effect=fake_gh):
        res = capture_ui_screenshots.post_pr_screenshot_comment(
            14,
            [{"repo_path": "prs/pr-14/cafe-desktop.png", "markdown": "![Cafe](https://raw.githubusercontent.com/o/r/screenshots/prs/pr-14/cafe-desktop.png)"}],
            repo="o/r",
            token="tok",
        )

    assert res["id"] == 77
    assert "prs/pr-14/cafe-desktop.png" in res["body"]
