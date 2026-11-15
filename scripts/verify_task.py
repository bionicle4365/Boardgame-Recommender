#!/usr/bin/env python3
"""Deterministic verification runner for autonomous tasks and Verifier agents."""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Sequence, Tuple

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


BACKEND_PREFIXES = ("bgg_", "scripts/", "tests/")


def _normalize_path(path: str) -> str:
    """Normalize path separators and strip leading './'."""
    norm = path.strip().strip('"').replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _matches_pattern(file_path: str, pattern: str) -> bool:
    """Return True if `file_path` matches a file path, directory prefix, or glob `pattern`."""
    norm_file = _normalize_path(file_path)
    norm_pat = _normalize_path(pattern)
    if not norm_pat:
        return False
    if norm_pat.endswith("/"):
        return norm_file.startswith(norm_pat)
    if norm_file == norm_pat or norm_file.startswith(f"{norm_pat}/"):
        return True
    return fnmatch.fnmatch(norm_file, norm_pat)


def get_current_branch() -> str:
    """Return the active local git branch name."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip()


def check_branch_safety(branch: str) -> Tuple[bool, str]:
    """Ensure verification runs on an isolated `agent/...` branch rather than `main`/`master`."""
    cleaned = (branch or "").strip()
    if cleaned in ("main", "master") or not cleaned.startswith("agent/"):
        return (
            False,
            f"Protected or non-agent branch '{cleaned}' is active. Task executors must work on an "
            "'agent/...' branch and never modify 'main' directly.",
        )
    return (True, "")


def resolve_default_base_ref() -> Optional[str]:
    """Return `origin/main...HEAD` (or `main...HEAD`) when available for committed-branch diffs."""
    for candidate in ("origin/main", "main"):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return f"{candidate}...HEAD"
    return None


def get_modified_files(base_ref: Optional[str] = None) -> List[str]:
    """Return modified and untracked repository files, ignoring .git/ and scratch/."""
    files: List[str] = []
    seen = set()

    def _add(raw_path: str) -> None:
        norm = _normalize_path(raw_path)
        if not norm or norm.startswith(".git/") or norm == ".git" or norm.startswith("scratch/"):
            return
        if norm not in seen:
            seen.add(norm)
            files.append(norm)

    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if status_proc.returncode == 0:
        for line in status_proc.stdout.splitlines():
            if len(line) < 4:
                continue
            path_part = line[3:]
            if " -> " in path_part:
                path_part = path_part.split(" -> ", 1)[1]
            _add(path_part)

    if base_ref:
        diff_proc = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if diff_proc.returncode == 0:
            for line in diff_proc.stdout.splitlines():
                _add(line)

    return files


def check_path_boundaries(
    modified_files: Sequence[str],
    owned_paths: Sequence[str],
    forbidden_paths: Sequence[str],
) -> Tuple[bool, List[str]]:
    """
    Validate that all `modified_files` stay within `owned_paths` (if specified)
    and do not touch any path in `forbidden_paths`.
    """
    violations: List[str] = []
    owned_clean = [p for p in owned_paths if _normalize_path(p)]
    forbidden_clean = [p for p in forbidden_paths if _normalize_path(p)]

    for raw_file in modified_files:
        norm_file = _normalize_path(raw_file)
        if not norm_file or norm_file.startswith(".git/") or norm_file.startswith("scratch/"):
            continue

        if any(_matches_pattern(norm_file, pat) for pat in forbidden_clean):
            violations.append(f"Forbidden path modified: {norm_file}")
            continue

        if owned_clean and not any(_matches_pattern(norm_file, pat) for pat in owned_clean):
            violations.append(f"Out-of-scope file modified (not in owned_paths): {norm_file}")

    return len(violations) == 0, violations


def infer_domain_checks(modified_files: Sequence[str]) -> List[str]:
    """Infer deterministic verification commands from the modified file paths."""
    checks: List[str] = []
    norm_files = [_normalize_path(f) for f in modified_files]

    touches_backend = any(
        f.endswith(".py") or f.startswith(BACKEND_PREFIXES)
        for f in norm_files
    )
    touches_ui = any(f == "site_ui" or f.startswith("site_ui/") for f in norm_files)
    touches_infra = any(f == "infrastructure" or f.startswith("infrastructure/") for f in norm_files)

    if touches_backend:
        checks.append("python -m pytest")
    if touches_ui:
        checks.append("npm --prefix site_ui test")
    if touches_infra and shutil.which("terraform"):
        checks.append("terraform -chdir=infrastructure fmt -check")
        checks.append("terraform -chdir=infrastructure validate")

    return checks


def format_verification_markdown(
    results: Sequence[Tuple[str, int]],
    modified_files: Optional[Sequence[str]] = None,
    branch: Optional[str] = None,
    snippets: Optional[Sequence[Tuple[str, str]]] = None,
) -> str:
    """Format verification results into a Markdown table and optional output excerpts for PR descriptions."""
    lines: List[str] = []
    if branch:
        lines.append(f"- **Branch:** `{branch}`")
    if modified_files is not None:
        lines.append(f"- **Files Modified ({len(modified_files)}):** " + (
            ", ".join(f"`{f}`" for f in modified_files) if modified_files else "_none_"
        ))
    if lines:
        lines.append("")

    lines.extend(["| Check / Command | Result |", "| --- | --- |"])
    for cmd, code in results:
        badge = "PASS" if code == 0 else f"FAIL ({code})"
        lines.append(f"| `{cmd}` | {badge} |")

    for cmd, excerpt in snippets or []:
        if excerpt and excerpt.strip():
            lines.extend(["", f"<details><summary>Output excerpt: <code>{cmd}</code></summary>", "", "```text", excerpt.strip(), "```", "</details>"])

    return "\n".join(lines)


def run_verification_commands(
    commands: Sequence[str],
    capture_output: bool = False,
) -> List[Tuple[str, int]]:
    """Run verification commands sequentially and return `(command, exit_code)` results."""
    results, _ = _run_verification_commands_with_logs(commands, capture_output=capture_output)
    return results


def _run_verification_commands_with_logs(
    commands: Sequence[str],
    capture_output: bool = False,
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, str]]]:
    """Run verification commands sequentially and optionally capture tail output snippets."""
    results: List[Tuple[str, int]] = []
    snippets: List[Tuple[str, str]] = []
    seen = set()
    for raw_cmd in commands:
        cmd = raw_cmd.strip()
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        print(f"\n>>> Running verification: {cmd}")
        if capture_output:
            proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, check=False)
            combined = "\n".join(
                part for part in (getattr(proc, "stdout", ""), getattr(proc, "stderr", ""))
                if isinstance(part, str) and part.strip()
            )
            if combined:
                print(combined)
                tail_lines = combined.strip().splitlines()[-15:]
                snippets.append((cmd, "\n".join(tail_lines)))
        else:
            proc = subprocess.run(cmd, shell=True, check=False)
        results.append((cmd, proc.returncode))
        if proc.returncode != 0:
            print(f"!!! FAILED (exit {proc.returncode}): {cmd}")
        else:
            print(f"+++ PASSED: {cmd}")
    return results, snippets


def verify_task(
    issue_number: Optional[int] = None,
    base_ref: Optional[str] = None,
    owned_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
    verify_cmds: Optional[Sequence[str]] = None,
    skip_git_check: bool = False,
    repo: Optional[str] = None,
    cwd: Optional[str] = None,
    report_markdown: Optional[str] = None,
) -> int:
    """Execute full boundary + test verification for a task and return exit code (0=pass, 1=fail)."""
    prev_cwd: Optional[str] = None
    if cwd:
        prev_cwd = os.getcwd()
        os.chdir(cwd)
    try:
        return _verify_task_impl(
            issue_number=issue_number,
            base_ref=base_ref,
            owned_paths=owned_paths,
            forbidden_paths=forbidden_paths,
            verify_cmds=verify_cmds,
            skip_git_check=skip_git_check,
            repo=repo,
            report_markdown=report_markdown,
        )
    finally:
        if prev_cwd is not None:
            os.chdir(prev_cwd)


def _verify_task_impl(
    issue_number: Optional[int] = None,
    base_ref: Optional[str] = None,
    owned_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
    verify_cmds: Optional[Sequence[str]] = None,
    skip_git_check: bool = False,
    repo: Optional[str] = None,
    report_markdown: Optional[str] = None,
) -> int:
    resolved_owned: List[str] = list(owned_paths or [])
    resolved_forbidden: List[str] = list(forbidden_paths or [])
    resolved_cmds: List[str] = list(verify_cmds or [])

    if issue_number is not None:
        issue_data = agent_backlog.get_task_issue(issue_number, repo=repo)
        if issue_data.get("spec_error") or not issue_data.get("spec"):
            print(f"ERROR: Could not parse task spec from issue #{issue_number}: {issue_data.get('spec_error')}")
            return 1
        spec = issue_data["spec"]
        if not resolved_owned:
            resolved_owned = list(spec.get("owned_paths", []))
        if not resolved_forbidden:
            resolved_forbidden = list(spec.get("forbidden_paths", []))
        for cmd in spec.get("verification_commands", []):
            if cmd not in resolved_cmds:
                resolved_cmds.append(cmd)
        print(f"Loaded task spec from GitHub Issue #{issue_number}: {issue_data.get('title')}")

    branch: Optional[str] = None
    modified_files: List[str] = []
    if not skip_git_check:
        branch = get_current_branch()
        branch_ok, branch_err = check_branch_safety(branch)
        if not branch_ok:
            print(f"ERROR: {branch_err}")
            return 1
        print(f"Branch safety check: PASSED ({branch})")
        resolved_base = base_ref if base_ref is not None else resolve_default_base_ref()
        if resolved_base:
            print(f"Diff base: {resolved_base}")
        modified_files = get_modified_files(base_ref=resolved_base)
        print(f"Modified files ({len(modified_files)}): {modified_files}")
        ok, violations = check_path_boundaries(modified_files, resolved_owned, resolved_forbidden)
        if not ok:
            print("\n=== PATH BOUNDARY VIOLATIONS ===")
            for v in violations:
                print(f"  - {v}")
            return 1
        print("Path boundary check: PASSED")

    inferred = infer_domain_checks(modified_files) if modified_files else []
    all_commands = [*inferred, *resolved_cmds]
    if not all_commands:
        print("No verification commands specified or inferred. Exiting cleanly.")
        if report_markdown:
            os.makedirs(os.path.dirname(os.path.abspath(report_markdown)), exist_ok=True)
            with open(report_markdown, "w", encoding="utf-8") as rf:
                rf.write(format_verification_markdown([], modified_files=modified_files if not skip_git_check else None, branch=branch))
        return 0

    results, snippets = _run_verification_commands_with_logs(
        all_commands,
        capture_output=bool(report_markdown),
    )
    failed = [cmd for cmd, code in results if code != 0]

    print("\n=== VERIFICATION SUMMARY ===")
    for cmd, code in results:
        status = "PASS" if code == 0 else f"FAIL ({code})"
        print(f"  [{status}] {cmd}")

    if report_markdown:
        os.makedirs(os.path.dirname(os.path.abspath(report_markdown)), exist_ok=True)
        with open(report_markdown, "w", encoding="utf-8") as rf:
            rf.write(
                format_verification_markdown(
                    results,
                    modified_files=modified_files if not skip_git_check else None,
                    branch=branch,
                    snippets=snippets,
                )
            )

    return 1 if failed else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic task verification runner")
    parser.add_argument("--issue", type=int, default=None, help="GitHub Issue number to load spec from")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name")
    parser.add_argument("--cwd", default=None, help="Optional working directory (e.g. isolated git worktree path)")
    parser.add_argument("--base", default=None, help="Optional git base ref for diff file detection")
    parser.add_argument("--owned-paths", nargs="*", default=[], help="Allowed file/directory paths")
    parser.add_argument("--forbidden-paths", nargs="*", default=[], help="Disallowed file/directory paths")
    parser.add_argument("--verify-cmd", action="append", default=[], help="Verification command to execute")
    parser.add_argument("--skip-git-check", action="store_true", help="Skip git status boundary check")
    parser.add_argument("--report-markdown", default=None, help="Write Markdown verification report to this file")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return verify_task(
        issue_number=args.issue,
        base_ref=args.base,
        owned_paths=args.owned_paths,
        forbidden_paths=args.forbidden_paths,
        verify_cmds=args.verify_cmd,
        skip_git_check=args.skip_git_check,
        repo=args.repo,
        cwd=args.cwd,
        report_markdown=args.report_markdown,
    )


if __name__ == "__main__":
    sys.exit(main())
