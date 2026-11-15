#!/usr/bin/env python3
"""Capture Playwright screenshots of Jekyll-built `site_ui/` pages and optionally upload to the orphan `screenshots` branch."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
from typing import Any, Dict, Iterator, List, Optional, Sequence

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


DEFAULT_SHARED_ROUTES = ["/", "/recommender/", "/cafe/"]
ROUTE_PREFIX_MAP = (
    ("site_ui/cafe/", "/cafe/"),
    ("site_ui/recommender/", "/recommender/"),
    ("site_ui/collection/", "/collection/"),
    ("site_ui/groups/", "/groups/"),
    ("site_ui/profile/", "/profile/"),
    ("site_ui/settings/", "/settings/"),
    ("site_ui/vote/", "/vote/"),
)
PR_COMMENT_MARKER = "<!-- ui-screenshots-bot -->"


def infer_routes_from_files(changed_files: Sequence[str]) -> List[str]:
    """Map changed repository paths under `site_ui/` to Jekyll site routes for screenshotting."""
    routes: List[str] = []

    def _add(route: str) -> None:
        if route not in routes:
            routes.append(route)

    for raw in changed_files:
        norm = str(raw).strip().replace("\\", "/").lstrip("./")
        if not norm.startswith("site_ui/"):
            continue
        if norm.startswith("site_ui/tests/") or norm in ("site_ui/package.json", "site_ui/package-lock.json", "site_ui/vitest.config.js"):
            continue
        matched_specific = False
        for prefix, route in ROUTE_PREFIX_MAP:
            if norm.startswith(prefix) or norm.endswith(f"/{os.path.basename(prefix.rstrip('/'))}.js") or norm.endswith(f"/{os.path.basename(prefix.rstrip('/'))}.css"):
                _add(route)
                matched_specific = True
        if not matched_specific:
            for route in DEFAULT_SHARED_ROUTES:
                _add(route)

    return routes


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler that suppresses noisy stdout request logs."""

    def log_message(self, format: str, *args: Any) -> None:
        return


class _ReusableThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextmanager
def serve_directory(directory: str) -> Iterator[str]:
    """Serve `directory` on an ephemeral `127.0.0.1` port for Playwright screenshot capture."""
    abs_dir = os.path.abspath(directory)
    if not os.path.isdir(abs_dir):
        raise FileNotFoundError(f"Built site directory not found: {abs_dir}")

    handler = partial(_QuietHandler, directory=abs_dir)
    server = _ReusableThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _route_slug(route: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", route.strip("/")).strip("-")
    return cleaned or "home"


def _launch_chromium(playwright_obj: Any) -> Any:
    """Launch headless Chromium, falling back to system Chrome/Edge if Playwright's browser binary is absent."""
    try:
        return playwright_obj.chromium.launch(headless=True)
    except Exception as primary_exc:
        for channel in ("chrome", "msedge"):
            try:
                return playwright_obj.chromium.launch(headless=True, channel=channel)
            except Exception:
                continue
        raise primary_exc


def capture_routes(
    site_dir: str = "site_ui/_site",
    routes: Optional[Sequence[str]] = None,
    out_dir: str = "scratch/screenshots",
    include_mobile: bool = False,
    full_page: bool = True,
    settle_ms: int = 400,
) -> List[Dict[str, str]]:
    """Render `routes` from `site_dir` using headless Chromium via Playwright and save PNG screenshots."""
    target_routes = list(routes or DEFAULT_SHARED_ROUTES)
    if not target_routes:
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required to capture screenshots (`pip install playwright && playwright install chromium`)."
        ) from exc

    os.makedirs(out_dir, exist_ok=True)
    viewports = [("desktop", {"width": 1440, "height": 900})]
    if include_mobile:
        viewports.append(("mobile", {"width": 390, "height": 844}))

    captured: List[Dict[str, str]] = []
    with serve_directory(site_dir) as base_url:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            try:
                for label, vp in viewports:
                    context = browser.new_context(viewport=vp, device_scale_factor=1)
                    page = context.new_page()

                    def _handle_route(route_obj: Any) -> None:
                        url = route_obj.request.url
                        if "PLACEHOLDER_API_URL" in url:
                            route_obj.fulfill(
                                status=200,
                                content_type="application/json",
                                body=json.dumps({}),
                            )
                        elif not url.startswith(base_url) and not url.startswith("data:") and not url.startswith("blob:"):
                            route_obj.abort()
                        else:
                            route_obj.continue_()

                    page.route("**/*", _handle_route)

                    for route in target_routes:
                        normalized_route = route if route.startswith("/") else f"/{route}"
                        target_url = f"{base_url}{normalized_route}"
                        slug = _route_slug(normalized_route)
                        filename = f"{slug}-{label}.png"
                        out_path = os.path.join(out_dir, filename).replace("\\", "/")
                        page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        if settle_ms > 0:
                            page.wait_for_timeout(settle_ms)
                        page.screenshot(path=out_path, full_page=full_page)
                        captured.append(
                            {
                                "route": normalized_route,
                                "viewport": label,
                                "path": out_path,
                                "filename": filename,
                            }
                        )
                    context.close()
            finally:
                browser.close()

    return captured


def post_pr_screenshot_comment(
    pr_number: int,
    uploaded_items: Sequence[Dict[str, str]],
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Create or update an idempotent PR comment embedding uploaded UI screenshots."""
    if not uploaded_items:
        return {}

    lines = [
        PR_COMMENT_MARKER,
        "## UI Screenshots",
        "",
        "Automated Playwright renders from the built Jekyll preview (`screenshots` orphan branch):",
        "",
    ]
    for item in uploaded_items:
        label = item.get("repo_path", item.get("filename", "Screenshot"))
        lines.append(f"### `{label}`")
        lines.append(item["markdown"])
        lines.append("")

    body = "\n".join(lines).strip()
    existing_comments = agent_backlog.github_request(
        "GET",
        f"/issues/{pr_number}/comments?per_page=100",
        repo=repo,
        token=token,
    ) or []
    for comment in existing_comments:
        if PR_COMMENT_MARKER in (comment.get("body") or ""):
            return agent_backlog.github_request(
                "PATCH",
                f"/issues/comments/{comment['id']}",
                payload={"body": body},
                repo=repo,
                token=token,
            )

    return agent_backlog.github_request(
        "POST",
        f"/issues/{pr_number}/comments",
        payload={"body": body},
        repo=repo,
        token=token,
    )


def _detect_changed_files_against_base(base_ref: str = "origin/main") -> List[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture UI screenshots from built Jekyll site_ui/_site")
    parser.add_argument("--site-dir", default="site_ui/_site", help="Path to built Jekyll _site directory")
    parser.add_argument("--out-dir", default="scratch/screenshots", help="Directory to write PNG screenshots")
    parser.add_argument("--routes", nargs="*", default=None, help="Explicit Jekyll routes to capture (e.g. / /cafe/)")
    parser.add_argument("--changed-files", nargs="*", default=None, help="Changed file paths used to infer UI routes")
    parser.add_argument("--base", default=None, help="Git base ref (e.g. origin/main) to infer changed UI routes")
    parser.add_argument("--mobile", action="store_true", help="Also capture 390x844 mobile viewport screenshots")
    parser.add_argument("--build", action="store_true", help="Run `bundle exec jekyll build` in site_ui/ before capturing")
    parser.add_argument("--upload", action="store_true", help="Upload captured PNGs to orphan `screenshots` branch")
    parser.add_argument("--prefix", default="manual", help="Target directory prefix in orphan `screenshots` branch")
    parser.add_argument("--branch", default=agent_backlog.SCREENSHOT_BRANCH, help="Orphan branch name (default: screenshots)")
    parser.add_argument("--post-pr-comment", type=int, default=None, help="Post/update PR comment with uploaded screenshots")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.build:
        subprocess.run(["bundle", "exec", "jekyll", "build"], cwd="site_ui", check=True)

    routes = list(args.routes) if args.routes else []
    if not routes and args.changed_files is not None:
        routes = infer_routes_from_files(args.changed_files)
    elif not routes and args.base:
        routes = infer_routes_from_files(_detect_changed_files_against_base(args.base))
    elif not routes:
        routes = list(DEFAULT_SHARED_ROUTES)

    if not routes:
        if args.json:
            print(json.dumps({"captured": [], "uploaded": []}))
        else:
            print("No site_ui routes affected; skipping screenshot capture.")
        return 0

    captured = capture_routes(
        site_dir=args.site_dir,
        routes=routes,
        out_dir=args.out_dir,
        include_mobile=args.mobile,
    )

    uploaded: List[Dict[str, str]] = []
    if args.upload and captured:
        clean_prefix = args.prefix.strip("/")
        mappings = {
            item["path"]: (f"{clean_prefix}/{item['filename']}" if clean_prefix else item["filename"])
            for item in captured
        }
        uploaded = agent_backlog.upload_screenshots(
            mappings,
            commit_message=f"Capture UI screenshots ({args.prefix})",
            branch=args.branch,
            repo=args.repo,
        )
        if args.post_pr_comment:
            post_pr_screenshot_comment(args.post_pr_comment, uploaded, repo=args.repo)

    if args.json:
        print(json.dumps({"captured": captured, "uploaded": uploaded}, indent=2))
    else:
        for item in captured:
            print(f"Captured {item['route']} ({item['viewport']}) -> {item['path']}")
        for item in uploaded:
            print(f"Uploaded -> {item['markdown']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
