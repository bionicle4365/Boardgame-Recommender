#!/usr/bin/env python3
"""GitHub Issues-backed autonomous task queue CLI for Boardgame-Recommender."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_REPO = "bionicle4365/Boardgame-Recommender"
GITHUB_API_BASE = "https://api.github.com"

SPEC_BLOCK_PATTERN = re.compile(
    r"```json\s+agent-task-spec\s*\r?\n(.*?)\r?\n```",
    re.DOTALL,
)

STATUS_LABELS: Dict[str, Tuple[str, str]] = {
    "agent:proposed": (
        "D4C5F9",
        "Proposed task awaiting human approval before execution",
    ),
    "agent:ready": (
        "0E8A16",
        "Ready for an autonomous agent to claim and execute",
    ),
    "agent:in-progress": (
        "FBCA04",
        "Currently claimed by an active autonomous agent",
    ),
    "agent:review": (
        "1D76DB",
        "Implementation complete; awaiting verifier or human PR review",
    ),
    "agent:changes-requested": (
        "E99695",
        "PR review requested changes; awaiting autonomous rework",
    ),
    "agent:approved": (
        "0E8A16",
        "PR approved by automated reviewer; awaiting human merge",
    ),
    "agent:blocked": (
        "D93F0B",
        "Blocked by external dependency, failing check, or ambiguity",
    ),
}

SOURCE_LABELS: Dict[str, Tuple[str, str]] = {
    "source:roadmap": (
        "5319E7",
        "Planned feature or architectural milestone",
    ),
    "source:telemetry": (
        "006B75",
        "Auto-generated from pipeline, S3, or runtime health checks",
    ),
    "source:test-gap": (
        "C2E0C6",
        "Auto-generated from unit test or coverage audit",
    ),
    "source:data-drift": (
        "F9D0C4",
        "Auto-generated from BGG schema or convention preview drift",
    ),
}

PRIORITY_LABELS: Dict[str, Tuple[str, str]] = {
    "priority:p1": ("B60205", "High priority task"),
    "priority:p2": ("FBCA04", "Medium priority task"),
    "priority:p3": ("0E8A16", "Low priority task"),
}

DOMAIN_LABELS: Dict[str, Tuple[str, str]] = {
    "domain:recommender": ("C5DEF5", "Recommendation engine, scoring, narration, sessions"),
    "domain:data": ("C5DEF5", "Data pipelines, Parquet schemas, compaction, analytics"),
    "domain:bgg-api": ("C5DEF5", "BGG XML/JSON scrapers, proxy, convention previews"),
    "domain:aws-infra": ("C5DEF5", "Terraform, IAM, API Gateway, Lambda, DynamoDB, SQS"),
    "domain:site-ui": ("C5DEF5", "Jekyll templates, Vanilla CSS, client JS, Vitest"),
}

STANDARD_LABELS: Dict[str, Tuple[str, str]] = {
    **STATUS_LABELS,
    **SOURCE_LABELS,
    **PRIORITY_LABELS,
    **DOMAIN_LABELS,
}

PRIORITY_ORDER = {"priority:p1": 1, "priority:p2": 2, "priority:p3": 3}
PROTECTED_BRANCHES = {"main", "master"}
DEFAULT_MAX_REWORK_ROUNDS = 3
AGENT_REVIEW_MARKER_RE = re.compile(
    r"<!--\s*agent-review:event=(APPROVE|REQUEST_CHANGES)\s+sha=([0-9a-zA-Z_-]+)\s*-->"
)


def validate_agent_branch(branch: str) -> str:
    """Ensure task executors only target isolated `agent/...` branches, never `main`/`master`."""
    cleaned = (branch or "").strip()
    if not cleaned or cleaned in PROTECTED_BRANCHES or not cleaned.startswith("agent/"):
        raise ValueError(
            f"Task executors must use an isolated 'agent/...' branch (got '{branch}'). "
            "Pushing or merging to 'main'/'master' is forbidden."
        )
    return cleaned


def get_current_git_branch() -> str:
    """Return the active local git branch name."""
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


def push_task_branch(branch: Optional[str] = None) -> str:
    """Safely push a validated `agent/...` branch to `origin`, refusing while on `main`/`master`."""
    current = get_current_git_branch()
    if current in PROTECTED_BRANCHES:
        raise ValueError(f"Refusing to push while checked out on protected branch '{current}'.")
    target = validate_agent_branch(branch or current)
    subprocess.run(["git", "push", "-u", "origin", f"{target}:{target}"], check=True)
    return target


def _resolve_base_ref(base_branch: str = "main") -> str:
    """Fetch latest `origin/<base_branch>` and fail loudly if `origin` exists but fetch fails."""
    remote_ref = f"origin/{base_branch}"
    fetch_proc = subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{base_branch}:refs/remotes/origin/{base_branch}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if fetch_proc.returncode != 0:
        remote_probe = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            check=False,
        )
        if remote_probe.returncode == 0:
            detail = (fetch_proc.stderr or fetch_proc.stdout or "").strip()
            raise RuntimeError(
                f"Failed to fetch latest '{remote_ref}' from origin: {detail or 'git fetch failed'}"
            )
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", remote_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return remote_ref
    remote_probe = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        text=True,
        capture_output=True,
        check=False,
    )
    if remote_probe.returncode == 0:
        raise RuntimeError(f"Remote ref '{remote_ref}' could not be resolved after fetching origin.")
    return base_branch


def _unlink_worktree_junction(wt_path: str) -> None:
    """Remove any Windows NTFS junction / symlink at `<wt_path>/site_ui/node_modules` before removal."""
    existing_nm = os.path.normpath(os.path.join(wt_path, "site_ui", "node_modules"))
    if os.path.lexists(existing_nm):
        try:
            if os.path.islink(existing_nm):
                os.unlink(existing_nm)
            else:
                os.rmdir(existing_nm)
        except OSError:
            pass


def _find_branch_worktree(branch: str) -> Optional[str]:
    """Return the worktree path if `branch` is currently checked out in any git worktree."""
    proc = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    target_ref = f"refs/heads/{branch}"
    current_wt: Optional[str] = None
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            current_wt = None
        elif line.startswith("worktree "):
            current_wt = line.split(" ", 1)[1].strip()
        elif line.startswith("branch ") and current_wt:
            if line.split(" ", 1)[1].strip() == target_ref:
                return current_wt
    return None


def cleanup_task_worktree(
    worktree_path: Optional[str] = None,
    branch: Optional[str] = None,
    delete_branch: bool = False,
) -> Optional[str]:
    """Safely remove an isolated worktree (unlinking node_modules junctions first) and optionally delete its agent branch."""
    target_branch = validate_agent_branch(branch) if branch is not None else None
    top_proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    repo_root = top_proc.stdout.strip() if top_proc.returncode == 0 and top_proc.stdout.strip() else os.getcwd()
    wt_path = worktree_path
    if not wt_path and target_branch:
        wt_path = _find_branch_worktree(target_branch) or os.path.join(
            repo_root, "scratch", "worktrees", target_branch.replace("/", "-")
        )
    if wt_path and os.path.exists(wt_path):
        _unlink_worktree_junction(wt_path)
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], text=True, capture_output=True, check=False)
    if delete_branch and target_branch:
        subprocess.run(
            ["git", "branch", "-D", target_branch],
            text=True,
            capture_output=True,
            check=False,
        )
    return wt_path.replace("\\", "/") if wt_path else None


def prepare_task_branch(
    branch: str,
    base_branch: str = "main",
    resume_existing: bool = False,
) -> str:
    """Create/reset `branch` from `origin/main` (or existing `origin/<branch>` when resuming)."""
    target = validate_agent_branch(branch)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode == 0 and status.stdout.strip():
        raise RuntimeError(
            "Working tree has uncommitted changes. Commit/stash them or pass '--worktree' "
            "to isolate the task branch from local edits."
        )
    resolved_base = _resolve_base_ref(base_branch=target if resume_existing else base_branch)
    subprocess.run(["git", "checkout", "-B", target, resolved_base], check=True)
    return target


def prepare_task_worktree(
    branch: str,
    worktree_path: Optional[str] = None,
    base_branch: str = "main",
    resume_existing: bool = False,
) -> str:
    """Create an isolated `scratch/worktrees/...` checkout on `branch` from `origin/main` or existing `origin/<branch>`."""
    target = validate_agent_branch(branch)
    top_proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    repo_root = top_proc.stdout.strip() if top_proc.returncode == 0 and top_proc.stdout.strip() else os.getcwd()
    wt_path = worktree_path or os.path.join(repo_root, "scratch", "worktrees", target.replace("/", "-"))
    resolved_base = _resolve_base_ref(base_branch=target if resume_existing else base_branch)

    existing_wt = _find_branch_worktree(target)
    if existing_wt:
        norm_root = os.path.normcase(os.path.abspath(repo_root))
        norm_existing = os.path.normcase(os.path.abspath(existing_wt))
        if norm_existing == norm_root:
            raise RuntimeError(
                f"Branch '{target}' is currently checked out in the main repository at '{existing_wt}'. "
                "Switch the main repository back to 'main' before creating a task worktree."
            )
        _unlink_worktree_junction(existing_wt)
        subprocess.run(
            ["git", "worktree", "remove", "--force", existing_wt],
            text=True,
            capture_output=True,
            check=False,
        )

    if os.path.exists(wt_path):
        _unlink_worktree_junction(wt_path)
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_path],
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], text=True, capture_output=True, check=False)
    os.makedirs(os.path.dirname(wt_path), exist_ok=True)
    subprocess.run(["git", "worktree", "add", "-B", target, wt_path, resolved_base], check=True)

    src_nm = os.path.normpath(os.path.join(repo_root, "site_ui", "node_modules"))
    dst_nm = os.path.normpath(os.path.join(wt_path, "site_ui", "node_modules"))
    if os.path.isdir(src_nm) and not os.path.exists(dst_nm):
        os.makedirs(os.path.dirname(dst_nm), exist_ok=True)
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", dst_nm, src_nm], check=False, capture_output=True)
        else:
            os.symlink(src_nm, dst_nm)

    return wt_path.replace("\\", "/")


def detect_repo_slug(fallback: str = DEFAULT_REPO) -> str:
    """Detect the GitHub `owner/repo` slug from `git remote get-url origin`."""
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            url = proc.stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
    except OSError:
        pass
    return fallback


def get_github_token(prefer_reviewer: bool = False) -> str:
    """Retrieve a GitHub personal access token from env vars or git credential fill."""
    env_vars: Tuple[str, ...] = (
        ("GITHUB_REVIEWER_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
        if prefer_reviewer
        else ("GITHUB_TOKEN", "GH_TOKEN")
    )
    for env_var in env_vars:
        token = os.environ.get(env_var, "").strip()
        if token:
            return token

    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("password="):
                    token = line.split("=", 1)[1].strip()
                    if token:
                        return token
    except OSError as exc:
        raise RuntimeError(f"Unable to invoke git credential fill: {exc}") from exc

    raise RuntimeError(
        "No GitHub token found in GITHUB_TOKEN, GH_TOKEN, or git credential helper."
    )


def github_request(
    method: str,
    path: str,
    payload: Optional[Any] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    accept: Optional[str] = None,
) -> Any:
    """Execute an authenticated GitHub REST API request scoped to `repo`."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    if not path or path == "/":
        normalized_path = ""
    else:
        normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{GITHUB_API_BASE}/repos/{target_repo}{normalized_path}"

    accept_header = accept or "application/vnd.github+json"
    data_bytes: Optional[bytes] = None
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": accept_header,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Boardgame-Recommender-Agent",
    }
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            if accept_header != "application/vnd.github+json" and "json" not in accept_header:
                return raw
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API {method.upper()} {url} failed with HTTP {err.code}: {err_body}"
        ) from err


def _normalize_text_list(value: Any) -> List[str]:
    """Normalize an optional string or sequence of strings into non-empty stripped items."""
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    items: List[str] = []
    for entry in value:
        text = str(entry).strip()
        if text:
            items.append(text)
    return items


def validate_task_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize an agent task specification dictionary."""
    if not isinstance(spec, dict):
        raise ValueError("Task spec must be a JSON object.")

    owned = [str(p).strip().replace("\\", "/") for p in spec.get("owned_paths") or [] if str(p).strip()]
    if not owned:
        raise ValueError("Task spec must include at least one path in 'owned_paths'.")

    forbidden_raw = spec.get("forbidden_paths")
    if forbidden_raw is None:
        forbidden = ["infrastructure/"] if not any(p.startswith("infrastructure") for p in owned) else []
    else:
        forbidden = [str(p).strip().replace("\\", "/") for p in forbidden_raw if str(p).strip()]

    acceptance = [str(a).strip() for a in spec.get("acceptance_criteria") or [] if str(a).strip()]
    if not acceptance:
        raise ValueError("Task spec must include at least one item in 'acceptance_criteria'.")

    verify_cmds = [str(c).strip() for c in spec.get("verification_commands") or [] if str(c).strip()]
    if not verify_cmds:
        raise ValueError("Task spec must include at least one command in 'verification_commands'.")

    normalized: Dict[str, Any] = {
        "owned_paths": owned,
        "forbidden_paths": forbidden,
        "acceptance_criteria": acceptance,
        "verification_commands": verify_cmds,
    }
    if spec.get("objective"):
        normalized["objective"] = str(spec["objective"]).strip()
    if spec.get("context"):
        context_text = str(spec["context"]).strip()
        if context_text:
            normalized["context"] = context_text
    examples = _normalize_text_list(spec.get("examples"))
    if examples:
        normalized["examples"] = examples
    visuals = _normalize_text_list(spec.get("visuals"))
    if visuals:
        normalized["visuals"] = visuals
    impl_notes = _normalize_text_list(spec.get("implementation_notes"))
    if impl_notes:
        normalized["implementation_notes"] = impl_notes
    return normalized


def _render_rich_block(item: str) -> str:
    """Render a multi-line/code block item verbatim or single-line text as a bullet."""
    if "\n" in item or item.startswith(("```", "![", "|", ">")):
        return item
    return f"- {item}"


def format_task_body(objective: str, spec: Dict[str, Any]) -> str:
    """Format a GitHub Issue body with rich context, examples, visuals, and an embedded agent-task-spec block."""
    validated = validate_task_spec({**spec, "objective": objective})
    spec_payload: Dict[str, Any] = {
        "owned_paths": validated["owned_paths"],
        "forbidden_paths": validated["forbidden_paths"],
        "acceptance_criteria": validated["acceptance_criteria"],
        "verification_commands": validated["verification_commands"],
    }
    spec_json = json.dumps(spec_payload, indent=2)

    lines = [
        "## Objective",
        objective.strip(),
        "",
    ]

    if validated.get("context"):
        lines.extend(["## Context & Motivation", validated["context"], ""])

    if validated.get("examples"):
        lines.append("## Examples")
        for ex in validated["examples"]:
            lines.append(_render_rich_block(ex))
        lines.append("")

    if validated.get("visuals"):
        lines.append("## Visuals & Mockups")
        for vis in validated["visuals"]:
            lines.append(_render_rich_block(vis))
        lines.append("")

    if validated.get("implementation_notes"):
        lines.append("## Implementation Notes")
        for note in validated["implementation_notes"]:
            lines.append(_render_rich_block(note))
        lines.append("")

    lines.extend(
        [
            "## Owned Paths",
            *[f"- `{p}`" for p in validated["owned_paths"]],
            "",
            "## Forbidden Paths",
            *([f"- `{p}`" for p in validated["forbidden_paths"]] or ["- *(None)*"]),
            "",
            "## Acceptance Criteria",
            *[f"- [ ] {item}" for item in validated["acceptance_criteria"]],
            "",
            "## Verification Commands",
            *[f"- `{cmd}`" for cmd in validated["verification_commands"]],
            "",
            "```json agent-task-spec",
            spec_json,
            "```",
        ]
    )
    return "\n".join(lines)


def _extract_markdown_section_items(body: str, heading: str) -> List[str]:
    """Extract bulleted or line items under a Markdown H2/H3 heading from Issue Forms or prose."""
    pattern = re.compile(
        rf"^#{{2,3}}\s+{re.escape(heading)}\s*\r?\n(.*?)(?=^#{{2,3}}\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(body or "")
    if not match:
        return []
    items: List[str] = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.lower() in ("_no response_", "*(none)*", "none"):
            continue
        line = re.sub(r"^[-*]\s+(?:\[[ xX]\]\s+)?", "", line).strip()
        if line.startswith("`") and line.endswith("`") and len(line) > 2:
            line = line[1:-1]
        if line:
            items.append(line)
    return items


def parse_task_spec(issue_body: str) -> Dict[str, Any]:
    """Parse and validate an agent task spec from either embedded JSON or Markdown headings."""
    body = issue_body or ""
    match = SPEC_BLOCK_PATTERN.search(body)
    if match:
        raw_spec = json.loads(match.group(1))
        return validate_task_spec(raw_spec)

    # Fallback parser for GitHub Issue Form submissions without the JSON block
    spec = {
        "owned_paths": _extract_markdown_section_items(body, "Owned Paths"),
        "forbidden_paths": _extract_markdown_section_items(body, "Forbidden Paths"),
        "acceptance_criteria": _extract_markdown_section_items(body, "Acceptance Criteria"),
        "verification_commands": _extract_markdown_section_items(body, "Verification Commands"),
    }
    return validate_task_spec(spec)


def _get_paginated_issues(
    state: str = "open",
    labels: Optional[List[str]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Fetch repository issues (excluding pull requests) across pages."""
    issues: List[dict] = []
    page = 1
    while True:
        params: Dict[str, Any] = {"state": state, "per_page": 100, "page": page}
        if labels:
            params["labels"] = ",".join(labels)
        query = urllib.parse.urlencode(params)
        batch = github_request("GET", f"/issues?{query}", repo=repo, token=token) or []
        if not batch:
            break
        for item in batch:
            if "pull_request" not in item:
                issues.append(item)
        if len(batch) < 100:
            break
        page += 1
    return issues


def _issue_priority_rank(issue: dict) -> Tuple[int, int]:
    """Sort key placing P1 before P2 before P3, then ascending issue number."""
    labels = {lbl.get("name", "") for lbl in issue.get("labels", [])}
    rank = min((PRIORITY_ORDER[l] for l in labels if l in PRIORITY_ORDER), default=99)
    return (rank, int(issue.get("number", 0)))


def init_repo(repo: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """Enable GitHub Issues on the repository and create/update all standard agentic labels."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    repo_resp = github_request(
        "PATCH",
        "",
        payload={"has_issues": True},
        repo=target_repo,
        token=auth_token,
    )

    existing_labels: Dict[str, dict] = {}
    page = 1
    while True:
        batch = github_request(
            "GET",
            f"/labels?per_page=100&page={page}",
            repo=target_repo,
            token=auth_token,
        ) or []
        for lbl in batch:
            existing_labels[lbl["name"].casefold()] = lbl
        if len(batch) < 100:
            break
        page += 1

    created = 0
    updated = 0
    for name, (color, description) in STANDARD_LABELS.items():
        payload = {"name": name, "color": color, "description": description}
        existing = existing_labels.get(name.casefold())
        if existing is None:
            github_request("POST", "/labels", payload=payload, repo=target_repo, token=auth_token)
            created += 1
        elif existing.get("color", "").upper() != color.upper() or existing.get("description") != description:
            encoded_name = urllib.parse.quote(existing["name"], safe="")
            github_request(
                "PATCH",
                f"/labels/{encoded_name}",
                payload=payload,
                repo=target_repo,
                token=auth_token,
            )
            updated += 1

    return {
        "repo": target_repo,
        "has_issues": bool(repo_resp.get("has_issues", True)) if isinstance(repo_resp, dict) else True,
        "labels_created": created,
        "labels_updated": updated,
        "total_standard_labels": len(STANDARD_LABELS),
    }


def create_task_issue(
    title: str,
    objective: str,
    owned_paths: List[str],
    acceptance_criteria: List[str],
    verification_commands: List[str],
    forbidden_paths: Optional[List[str]] = None,
    context: Optional[str] = None,
    examples: Optional[Sequence[str]] = None,
    visuals: Optional[Sequence[str]] = None,
    implementation_notes: Optional[Sequence[str]] = None,
    priority: str = "p2",
    source: str = "roadmap",
    domains: Optional[List[str]] = None,
    initial_status: str = "proposed",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an agentic GitHub Issue if no open issue with the same title already exists."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    status_label = initial_status if initial_status.startswith("agent:") else f"agent:{initial_status}"
    if status_label not in STATUS_LABELS:
        raise ValueError(f"Invalid initial_status '{initial_status}'.")

    open_issues = _get_paginated_issues(state="open", repo=target_repo, token=auth_token)
    normalized_title = title.strip().casefold()
    for existing in open_issues:
        if (existing.get("title") or "").strip().casefold() == normalized_title:
            return {"deduplicated": True, "issue": existing}

    body = format_task_body(
        objective=objective,
        spec={
            "owned_paths": owned_paths,
            "forbidden_paths": forbidden_paths,
            "acceptance_criteria": acceptance_criteria,
            "verification_commands": verification_commands,
            "context": context,
            "examples": examples,
            "visuals": visuals,
            "implementation_notes": implementation_notes,
        },
    )

    labels = [status_label]
    prio_label = priority if priority.startswith("priority:") else f"priority:{priority}"
    if prio_label in PRIORITY_LABELS:
        labels.append(prio_label)

    src_label = source if source.startswith("source:") else f"source:{source}"
    if src_label in SOURCE_LABELS:
        labels.append(src_label)

    for dom in domains or []:
        dom_label = dom if dom.startswith("domain:") else f"domain:{dom}"
        if dom_label in DOMAIN_LABELS and dom_label not in labels:
            labels.append(dom_label)

    created = github_request(
        "POST",
        "/issues",
        payload={"title": title.strip(), "body": body, "labels": labels},
        repo=target_repo,
        token=auth_token,
    )
    return {"deduplicated": False, "issue": created}


def update_task_issue(
    issue_number: int,
    objective: Optional[str] = None,
    owned_paths: Optional[List[str]] = None,
    forbidden_paths: Optional[List[str]] = None,
    acceptance_criteria: Optional[List[str]] = None,
    verification_commands: Optional[List[str]] = None,
    context: Optional[str] = None,
    examples: Optional[Sequence[str]] = None,
    visuals: Optional[Sequence[str]] = None,
    implementation_notes: Optional[Sequence[str]] = None,
    title: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Update an existing GitHub Issue body with enriched context, examples, visuals, or spec fields."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    existing_body = issue.get("body", "") or ""
    existing_spec = parse_task_spec(existing_body)

    existing_objective_items = _extract_markdown_section_items(existing_body, "Objective")
    resolved_objective = (
        objective.strip()
        if objective and objective.strip()
        else ("\n".join(existing_objective_items) if existing_objective_items else issue.get("title", f"Issue #{issue_number}"))
    )

    merged_spec: Dict[str, Any] = {
        "owned_paths": owned_paths if owned_paths is not None else existing_spec["owned_paths"],
        "forbidden_paths": forbidden_paths if forbidden_paths is not None else existing_spec["forbidden_paths"],
        "acceptance_criteria": acceptance_criteria if acceptance_criteria is not None else existing_spec["acceptance_criteria"],
        "verification_commands": verification_commands if verification_commands is not None else existing_spec["verification_commands"],
        "context": context if context is not None else existing_spec.get("context"),
        "examples": examples if examples is not None else existing_spec.get("examples"),
        "visuals": visuals if visuals is not None else existing_spec.get("visuals"),
        "implementation_notes": implementation_notes if implementation_notes is not None else existing_spec.get("implementation_notes"),
    }

    payload: Dict[str, Any] = {"body": format_task_body(resolved_objective, merged_spec)}
    if title and title.strip():
        payload["title"] = title.strip()

    return github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=payload,
        repo=target_repo,
        token=auth_token,
    )


def list_task_issues(
    status: str = "ready",
    domain: Optional[str] = None,
    state: str = "open",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """List agentic issues filtered by status/domain and sorted by priority."""
    labels: List[str] = []
    if status and status != "all":
        labels.append(status if status.startswith("agent:") else f"agent:{status}")
    if domain:
        labels.append(domain if domain.startswith("domain:") else f"domain:{domain}")

    issues = _get_paginated_issues(state=state, labels=labels or None, repo=repo, token=token)
    return sorted(issues, key=_issue_priority_rank)


def get_task_issue(
    issue_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a single issue and parse its embedded task specification."""
    issue = github_request("GET", f"/issues/{issue_number}", repo=repo, token=token)
    spec: Optional[Dict[str, Any]] = None
    spec_error: Optional[str] = None
    try:
        spec = parse_task_spec(issue.get("body", ""))
    except Exception as exc:
        spec_error = str(exc)

    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "html_url": issue.get("html_url"),
        "labels": [lbl.get("name") for lbl in issue.get("labels", [])],
        "spec": spec,
        "spec_error": spec_error,
        "body": issue.get("body", ""),
    }


def _replace_status_label(current_labels: List[str], target_status_label: str) -> List[str]:
    """Return updated label list replacing any `agent:*` status label with `target_status_label`."""
    preserved = [lbl for lbl in current_labels if lbl not in STATUS_LABELS]
    if target_status_label not in preserved:
        preserved.append(target_status_label)
    return preserved


def approve_task_issue(
    issue_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Approve a proposed issue by transitioning its status label to `agent:ready`."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:ready")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": "Approved for autonomous execution (`agent:ready`)."},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def claim_task_issue(
    issue_number: int,
    agent_name: str,
    branch: Optional[str] = None,
    force: bool = False,
    allow_rework: bool = False,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an approved `agent:ready` or `agent:changes-requested` issue to `agent:in-progress`."""
    if branch is not None:
        branch = validate_agent_branch(branch)
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    claimable = "agent:ready" in current_labels or "agent:changes-requested" in current_labels
    if allow_rework and "agent:review" in current_labels:
        claimable = True
    if not force and not claimable:
        raise ValueError(
            f"Issue #{issue_number} is not approved for execution (missing 'agent:ready' label; "
            f"current labels: {current_labels}). Approve it first with "
            f"'python scripts/agent_backlog.py approve {issue_number}' or by setting the 'agent:ready' label on GitHub."
        )
    new_labels = _replace_status_label(current_labels, "agent:in-progress")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )

    branch_note = f" on branch `{branch}`" if branch else ""
    rework_note = " (PR rework)" if "agent:changes-requested" in current_labels or allow_rework else ""
    comment = f"Claimed by autonomous agent `{agent_name}`{branch_note}{rework_note}."
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": comment},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def get_next_ready_issue(
    domain: Optional[str] = None,
    reclaim_stale_hours: Optional[float] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch the highest-priority `agent:ready` issue, parse its spec, and suggest a feature branch."""
    if reclaim_stale_hours is not None and reclaim_stale_hours > 0:
        reclaim_stale_in_progress_issues(
            max_age_hours=reclaim_stale_hours,
            repo=repo,
            token=token,
        )
    issues = list_task_issues(status="ready", domain=domain, state="open", repo=repo, token=token)
    if not issues:
        return None
    top_number = int(issues[0]["number"])
    task = get_task_issue(top_number, repo=repo, token=token)
    task["branch"] = f"agent/issue-{top_number}"
    return task


def _parse_github_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 UTC timestamp string returned by the GitHub REST API."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def reclaim_stale_in_progress_issues(
    max_age_hours: float = 6.0,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Reclaim open `agent:in-progress` issues older than `max_age_hours` back to `agent:ready` (or `agent:review` if a PR exists)."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    owner = target_repo.split("/")[0]
    now = datetime.now(timezone.utc)

    in_progress = list_task_issues(
        status="in-progress",
        state="open",
        repo=target_repo,
        token=auth_token,
    )
    reclaimed: List[dict] = []
    for item in in_progress:
        issue_number = int(item.get("number", 0))
        if not issue_number:
            continue
        updated_at = _parse_github_iso_timestamp(item.get("updated_at") or item.get("created_at"))
        if updated_at is None:
            continue
        age_hours = (now - updated_at).total_seconds() / 3600.0
        if age_hours < max_age_hours:
            continue

        head_branch = f"agent/issue-{issue_number}"
        pr_query = urllib.parse.urlencode(
            {"state": "open", "head": f"{owner}:{head_branch}", "base": "main"}
        )
        open_prs = github_request("GET", f"/pulls?{pr_query}", repo=target_repo, token=auth_token) or []
        current_labels = [lbl.get("name", "") for lbl in item.get("labels", [])]

        if open_prs:
            new_labels = _replace_status_label(current_labels, "agent:review")
            pr_url = open_prs[0].get("html_url", "")
            comment = (
                f"Detected open Pull Request ({pr_url}) on stale `agent:in-progress` issue "
                f"({age_hours:.1f}h old); transitioning to `agent:review`."
            )
        else:
            new_labels = _replace_status_label(current_labels, "agent:ready")
            comment = (
                f"Reclaimed stale `agent:in-progress` lease after {age_hours:.1f}h without an open PR; "
                "resetting status to `agent:ready` for retry."
            )

        updated = github_request(
            "PATCH",
            f"/issues/{issue_number}",
            payload={"labels": new_labels},
            repo=target_repo,
            token=auth_token,
        )
        github_request(
            "POST",
            f"/issues/{issue_number}/comments",
            payload={"body": comment},
            repo=target_repo,
            token=auth_token,
        )
        reclaimed.append(updated)

    return reclaimed


SCREENSHOT_BRANCH = "screenshots"


def upload_screenshots(
    file_mappings: Dict[str, str],
    commit_message: str = "Upload screenshots for issue/PR preview",
    branch: str = SCREENSHOT_BRANCH,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Upload screenshot files to an orphan branch (default: `screenshots`) via GitHub Git Data API
    so inline images render in Issues/PRs without adding binary blobs to `main`.
    """
    if not file_mappings:
        return []

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    parent_sha: Optional[str] = None
    base_tree_sha: Optional[str] = None
    try:
        ref_data = github_request("GET", f"/git/ref/heads/{branch}", repo=target_repo, token=auth_token)
        if isinstance(ref_data, dict) and isinstance(ref_data.get("object"), dict):
            parent_sha = ref_data["object"].get("sha")
        if parent_sha:
            commit_data = github_request("GET", f"/git/commits/{parent_sha}", repo=target_repo, token=auth_token)
            if isinstance(commit_data, dict) and isinstance(commit_data.get("tree"), dict):
                base_tree_sha = commit_data["tree"].get("sha")
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise

    tree_entries: List[Dict[str, str]] = []
    uploaded: List[Dict[str, str]] = []

    if parent_sha is None:
        readme_text = (
            "# PR & Issue Screenshots\n\n"
            "Orphan branch storing UI verification screenshots and mockups referenced by GitHub Issues and Pull Requests.\n"
        )
        readme_b64 = base64.b64encode(readme_text.encode("utf-8")).decode("ascii")
        readme_blob = github_request(
            "POST",
            "/git/blobs",
            payload={"content": readme_b64, "encoding": "base64"},
            repo=target_repo,
            token=auth_token,
        )
        tree_entries.append(
            {"path": "README.md", "mode": "100644", "type": "blob", "sha": readme_blob["sha"]}
        )

    for local_path, raw_repo_path in file_mappings.items():
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"Screenshot file not found: {local_path}")
        repo_path = raw_repo_path.strip().lstrip("/").replace("\\", "/")
        with open(local_path, "rb") as f:
            b64_content = base64.b64encode(f.read()).decode("ascii")
        blob = github_request(
            "POST",
            "/git/blobs",
            payload={"content": b64_content, "encoding": "base64"},
            repo=target_repo,
            token=auth_token,
        )
        tree_entries.append(
            {"path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
        )
        raw_url = f"https://raw.githubusercontent.com/{target_repo}/{branch}/{repo_path}"
        alt_label = os.path.splitext(os.path.basename(repo_path))[0].replace("-", " ").replace("_", " ").title()
        uploaded.append(
            {
                "local_path": local_path,
                "repo_path": repo_path,
                "raw_url": raw_url,
                "markdown": f"![{alt_label}]({raw_url})",
            }
        )

    tree_payload: Dict[str, Any] = {"tree": tree_entries}
    if base_tree_sha:
        tree_payload["base_tree"] = base_tree_sha
    created_tree = github_request("POST", "/git/trees", payload=tree_payload, repo=target_repo, token=auth_token)

    commit_payload: Dict[str, Any] = {
        "message": commit_message,
        "tree": created_tree["sha"],
        "parents": [parent_sha] if parent_sha else [],
    }
    created_commit = github_request("POST", "/git/commits", payload=commit_payload, repo=target_repo, token=auth_token)

    if parent_sha:
        github_request(
            "PATCH",
            f"/git/refs/heads/{branch}",
            payload={"sha": created_commit["sha"]},
            repo=target_repo,
            token=auth_token,
        )
    else:
        github_request(
            "POST",
            "/git/refs",
            payload={"ref": f"refs/heads/{branch}", "sha": created_commit["sha"]},
            repo=target_repo,
            token=auth_token,
        )

    return uploaded


def resolve_screenshot_markdown(
    screenshots: Optional[Sequence[str]],
    prefix: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[str]:
    """Resolve URLs, Markdown image tags, or local screenshot paths (uploading local files to `screenshots` branch)."""
    if not screenshots:
        return []
    markdown_items: List[str] = []
    local_mappings: Dict[str, str] = {}
    for item in screenshots:
        text = str(item).strip()
        if not text:
            continue
        if text.startswith("![") or text.startswith("<img"):
            markdown_items.append(text)
        elif text.startswith(("http://", "https://")):
            label = os.path.splitext(os.path.basename(urllib.parse.urlparse(text).path))[0] or "Screenshot"
            markdown_items.append(f"![{label}]({text})")
        elif os.path.isfile(text):
            clean_prefix = prefix.strip("/")
            fname = os.path.basename(text)
            local_mappings[text] = f"{clean_prefix}/{fname}" if clean_prefix else fname
        else:
            markdown_items.append(text)

    if local_mappings:
        uploaded = upload_screenshots(
            local_mappings,
            commit_message=f"Add screenshots for {prefix}",
            repo=repo,
            token=token,
        )
        markdown_items.extend(entry["markdown"] for entry in uploaded)

    return markdown_items


def _collect_git_diff_context(base_branch: str = "main") -> Dict[str, Any]:
    """Safely collect changed files and diffstat against `origin/<base_branch>` when on an agent branch."""
    try:
        current = get_current_git_branch()
        if current in PROTECTED_BRANCHES:
            return {}
        base_ref = None
        for candidate in (f"origin/{base_branch}", base_branch):
            probe = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", candidate],
                text=True,
                capture_output=True,
                check=False,
            )
            if probe.returncode == 0:
                base_ref = f"{candidate}...HEAD"
                break
        if not base_ref:
            return {}

        stat_proc = subprocess.run(
            ["git", "diff", "--stat", base_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        names_proc = subprocess.run(
            ["git", "diff", "--name-status", base_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        changed_files = [
            line.strip()
            for line in (names_proc.stdout or "").splitlines()
            if line.strip()
        ] if names_proc.returncode == 0 else []
        diff_stat = (stat_proc.stdout or "").strip() if stat_proc.returncode == 0 else ""
        return {"changed_files": changed_files, "diff_stat": diff_stat}
    except Exception:
        return {}


def format_pr_body(
    issue_number: int,
    summary: str = "",
    changed_files: Optional[Sequence[str]] = None,
    diff_stat: str = "",
    examples: Optional[Sequence[str]] = None,
    verification_results: str = "",
    screenshots: Optional[Sequence[str]] = None,
    acceptance_criteria: Optional[Sequence[str]] = None,
) -> str:
    """Format a comprehensive GitHub Pull Request body with diff details, examples, verification proof, and screenshots."""
    summary_text = summary.strip() or "Autonomous implementation verified via `scripts/verify_task.py`."
    lines: List[str] = [
        f"Closes #{issue_number}",
        "",
        "## Summary",
        summary_text,
        "",
    ]

    files_list = _normalize_text_list(changed_files)
    if files_list or diff_stat.strip():
        lines.append("## Changes Made")
        for entry in files_list:
            parts = entry.split("\t", 1)
            if len(parts) == 2:
                lines.append(f"- **{parts[0].strip()}**: `{parts[1].strip()}`")
            else:
                lines.append(f"- `{entry}`")
        if diff_stat.strip():
            lines.extend(["", "```text", diff_stat.strip(), "```"])
        lines.append("")

    example_items = _normalize_text_list(examples)
    if example_items:
        lines.append("## Examples")
        for ex in example_items:
            lines.append(_render_rich_block(ex))
        lines.append("")

    lines.append("## Verification & Test Results")
    if verification_results.strip():
        lines.append(verification_results.strip())
    else:
        lines.append("- Verified locally via `python scripts/verify_task.py --issue " + str(issue_number) + "`.")
    lines.append("")

    shot_items = _normalize_text_list(screenshots)
    lines.append("## Screenshots")
    if shot_items:
        lines.extend(shot_items)
    else:
        lines.append("_No UI changes in this PR (or capture pending PR CI `ui-screenshots`)._")
    lines.append("")

    criteria = _normalize_text_list(acceptance_criteria)
    lines.append("## Review Checklist")
    if criteria:
        for item in criteria:
            lines.append(f"- [x] {item}")
    lines.extend(
        [
            "- [x] Changes isolated to `agent/issue-" + str(issue_number) + "` branch and within `owned_paths`",
            "- [x] Automated unit tests and verification checks pass",
        ]
    )
    return "\n".join(lines)


def create_or_get_pull_request(
    issue_number: int,
    head_branch: str,
    base_branch: str = "main",
    title: Optional[str] = None,
    summary: str = "",
    examples: Optional[Sequence[str]] = None,
    verification_results: str = "",
    screenshots: Optional[Sequence[str]] = None,
    changed_files: Optional[Sequence[str]] = None,
    diff_stat: Optional[str] = None,
    acceptance_criteria: Optional[Sequence[str]] = None,
    issue_data: Optional[dict] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a GitHub Pull Request for `head_branch` -> `base_branch` or return an existing open PR."""
    head_branch = validate_agent_branch(head_branch)
    if (base_branch or "").strip() != "main":
        raise ValueError(f"Task executor Pull Requests must target 'main' (got '{base_branch}').")
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    owner = target_repo.split("/")[0]

    query = urllib.parse.urlencode(
        {"state": "open", "head": f"{owner}:{head_branch}", "base": base_branch}
    )
    existing = github_request("GET", f"/pulls?{query}", repo=target_repo, token=auth_token) or []
    if existing:
        return {"deduplicated": True, "pull_request": existing[0]}

    resolved_issue = issue_data
    if resolved_issue is None and (not title or acceptance_criteria is None):
        resolved_issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)

    pr_title = title
    if not pr_title:
        assert resolved_issue is not None
        pr_title = f"{resolved_issue.get('title', f'Task #{issue_number}')} (#{issue_number})"

    resolved_criteria = acceptance_criteria
    if resolved_criteria is None and isinstance(resolved_issue, dict) and resolved_issue.get("body"):
        try:
            resolved_criteria = parse_task_spec(resolved_issue["body"]).get("acceptance_criteria", [])
        except Exception:
            resolved_criteria = []

    git_ctx: Dict[str, Any] = {}
    if changed_files is None or diff_stat is None:
        git_ctx = _collect_git_diff_context(base_branch=base_branch)

    resolved_shots = resolve_screenshot_markdown(
        screenshots,
        prefix=f"prs/issue-{issue_number}",
        repo=target_repo,
        token=auth_token,
    )

    pr_body = format_pr_body(
        issue_number=issue_number,
        summary=summary,
        changed_files=changed_files if changed_files is not None else git_ctx.get("changed_files"),
        diff_stat=diff_stat if diff_stat is not None else git_ctx.get("diff_stat", ""),
        examples=examples,
        verification_results=verification_results,
        screenshots=resolved_shots,
        acceptance_criteria=resolved_criteria,
    )

    created = github_request(
        "POST",
        "/pulls",
        payload={
            "title": pr_title,
            "head": head_branch,
            "base": base_branch,
            "body": pr_body,
        },
        repo=target_repo,
        token=auth_token,
    )
    return {"deduplicated": False, "pull_request": created}


def complete_task_issue(
    issue_number: int,
    summary: str = "",
    pr: Optional[str] = None,
    push: bool = False,
    open_pr: bool = False,
    base_branch: str = "main",
    close: bool = False,
    examples: Optional[Sequence[str]] = None,
    verification_results: str = "",
    screenshots: Optional[Sequence[str]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an issue to `agent:review` (optionally pushing, opening a PR, or closing) and post a detailed comment."""
    head_branch: Optional[str] = None
    if push or open_pr or pr is not None:
        head_branch = validate_agent_branch(pr or f"agent/issue-{issue_number}")

    if push:
        push_task_branch(head_branch)

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:review")

    patch_payload: Dict[str, Any] = {"labels": new_labels}
    if close:
        patch_payload["state"] = "closed"

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload=patch_payload,
        repo=target_repo,
        token=auth_token,
    )

    resolved_shots = resolve_screenshot_markdown(
        screenshots,
        prefix=f"prs/issue-{issue_number}",
        repo=target_repo,
        token=auth_token,
    )

    pr_info: Optional[dict] = None
    if open_pr:
        assert head_branch is not None
        pr_res = create_or_get_pull_request(
            issue_number=issue_number,
            head_branch=head_branch,
            base_branch=base_branch,
            summary=summary,
            examples=examples,
            verification_results=verification_results,
            screenshots=resolved_shots,
            issue_data=issue,
            repo=target_repo,
            token=auth_token,
        )
        pr_info = pr_res["pull_request"]
        updated["pull_request"] = pr_info
        if pr_res.get("deduplicated") and pr_info and pr_info.get("number") and (
            summary.strip() or verification_results.strip()
        ):
            pr_update_parts = ["Updated PR with rework fixes; ready for re-review."]
            if summary.strip():
                pr_update_parts.append(f"\n### Rework Summary\n{summary.strip()}")
            if verification_results.strip():
                pr_update_parts.append(f"\n### Verification Results\n{verification_results.strip()}")
            github_request(
                "POST",
                f"/issues/{int(pr_info['number'])}/comments",
                payload={"body": "\n".join(pr_update_parts)},
                repo=target_repo,
                token=auth_token,
            )

    comment_parts = ["Verification passed and task implementation is ready for review."]
    if pr:
        comment_parts.append(f"- **Branch:** `{pr}`")
    if pr_info and pr_info.get("html_url"):
        comment_parts.append(f"- **Pull Request:** {pr_info['html_url']}")
    if summary:
        comment_parts.append(f"\n### Summary\n{summary}")
    if verification_results.strip():
        comment_parts.append(f"\n### Verification Results\n{verification_results.strip()}")
    if resolved_shots:
        comment_parts.append("\n### Screenshots\n" + "\n".join(resolved_shots))

    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": "\n".join(comment_parts)},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def block_task_issue(
    issue_number: int,
    reason: str = "",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Transition an issue to `agent:blocked` and post the failure/blocker reason."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, "agent:blocked")

    updated = github_request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"labels": new_labels},
        repo=target_repo,
        token=auth_token,
    )
    reason_text = reason.strip() or "Autonomous execution failed or requires human intervention."
    github_request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": f"Blocked during autonomous execution (`agent:blocked`).\n\nReason:\n{reason_text}"},
        repo=target_repo,
        token=auth_token,
    )
    return updated


def _set_issue_status_label(
    issue_number: int,
    target_status_label: str,
    comment: Optional[str] = None,
    issue_data: Optional[dict] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Update an issue's `agent:*` status label and optionally post a status comment."""
    if target_status_label not in STATUS_LABELS:
        raise ValueError(f"Unknown status label '{target_status_label}'.")
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    issue = issue_data or github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    new_labels = _replace_status_label(current_labels, target_status_label)
    if new_labels != current_labels:
        updated = github_request(
            "PATCH",
            f"/issues/{issue_number}",
            payload={"labels": new_labels},
            repo=target_repo,
            token=auth_token,
        )
    else:
        updated = issue
    if comment:
        github_request(
            "POST",
            f"/issues/{issue_number}/comments",
            payload={"body": comment},
            repo=target_repo,
            token=auth_token,
        )
    return updated


def _extract_issue_number_from_pr(pr: dict) -> Optional[int]:
    """Infer the linked backlog issue number from a PR's head branch or body."""
    head_ref = ((pr.get("head") or {}).get("ref") or "").strip()
    branch_match = re.match(r"^agent/issue-(\d+)$", head_ref)
    if branch_match:
        return int(branch_match.group(1))
    body = pr.get("body") or ""
    body_match = re.search(r"(?:Closes|Fixes|Resolves)\s+#(\d+)\b", body, re.IGNORECASE)
    if body_match:
        return int(body_match.group(1))
    return None


def _get_paginated_list(
    base_path: str,
    params: Optional[Dict[str, Any]] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[dict]:
    """Fetch all pages of a GitHub REST list endpoint."""
    items: List[dict] = []
    page = 1
    while True:
        query_params = dict(params or {})
        query_params["per_page"] = 100
        query_params["page"] = page
        query = urllib.parse.urlencode(query_params)
        batch = github_request("GET", f"{base_path}?{query}", repo=repo, token=token) or []
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def _get_pr_ci_status(
    head_sha: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Summarize GitHub Actions check runs for a PR head commit SHA."""
    if not head_sha:
        return {"total": 0, "completed": 0, "pending": 0, "failed": 0, "failed_checks": [], "overall": "none"}
    resp = github_request(
        "GET",
        f"/commits/{head_sha}/check-runs?per_page=100",
        repo=repo,
        token=token,
    ) or {}
    runs = resp.get("check_runs", []) if isinstance(resp, dict) else []
    total = len(runs)
    completed = 0
    pending = 0
    failed = 0
    failed_checks: List[Dict[str, Any]] = []
    for run in runs:
        if run.get("status") != "completed":
            pending += 1
            continue
        completed += 1
        conclusion = (run.get("conclusion") or "").lower()
        if conclusion not in ("success", "neutral", "skipped"):
            failed += 1
            failed_checks.append(
                {
                    "name": run.get("name"),
                    "conclusion": conclusion or "unknown",
                    "html_url": run.get("html_url"),
                }
            )
    if total == 0:
        overall = "none"
    elif pending > 0:
        overall = "pending"
    elif failed > 0:
        overall = "failure"
    else:
        overall = "success"
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "failed": failed,
        "failed_checks": failed_checks,
        "overall": overall,
    }


def _summarize_pr_reviews(reviews: Sequence[dict], head_sha: str) -> Dict[str, Any]:
    """Summarize native PR reviews and single-PAT marker reviews relative to `head_sha`."""
    latest_by_actor: Dict[str, Dict[str, Any]] = {}
    latest_substantive: Optional[Dict[str, Any]] = None
    changes_requested_rounds = 0

    for rev in reviews:
        raw_state = (rev.get("state") or "").upper()
        body = rev.get("body") or ""
        commit_id = rev.get("commit_id") or ""
        actor = ((rev.get("user") or {}).get("login") or "unknown").strip()
        effective_state: Optional[str] = None

        marker = AGENT_REVIEW_MARKER_RE.search(body) if raw_state == "COMMENTED" else None
        if raw_state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            effective_state = raw_state
        elif marker:
            effective_state = "APPROVED" if marker.group(1) == "APPROVE" else "CHANGES_REQUESTED"
            commit_id = marker.group(2)
            actor = "__agent_reviewer__"

        if not effective_state:
            continue

        entry = {
            "id": rev.get("id"),
            "actor": actor,
            "state": effective_state,
            "commit_id": commit_id,
            "submitted_at": rev.get("submitted_at"),
            "body": body,
        }
        if effective_state == "CHANGES_REQUESTED":
            changes_requested_rounds += 1
        latest_by_actor[actor] = entry
        latest_substantive = entry

    active_changes = [r for r in latest_by_actor.values() if r["state"] == "CHANGES_REQUESTED"]
    has_changes_requested_at_head = any(r["commit_id"] == head_sha for r in active_changes)
    is_approved_at_head = (
        bool(latest_by_actor)
        and not active_changes
        and all(r["state"] == "APPROVED" and r["commit_id"] == head_sha for r in latest_by_actor.values())
    )
    needs_review = (
        not has_changes_requested_at_head
        and (latest_substantive is None or latest_substantive["commit_id"] != head_sha)
    )
    return {
        "latest_by_actor": latest_by_actor,
        "latest_substantive": latest_substantive,
        "active_changes_requested": active_changes,
        "has_changes_requested_at_head": has_changes_requested_at_head,
        "is_approved_at_head": is_approved_at_head,
        "needs_review": needs_review,
        "changes_requested_rounds": changes_requested_rounds,
    }


def _find_open_pr_for_issue(
    issue_number: int,
    base_branch: str = "main",
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[dict]:
    """Return the open PR for `agent/issue-<issue_number>` if one exists."""
    target_repo = repo or detect_repo_slug()
    owner = target_repo.split("/")[0]
    head_branch = f"agent/issue-{issue_number}"
    query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{head_branch}", "base": base_branch})
    prs = github_request("GET", f"/pulls?{query}", repo=target_repo, token=token) or []
    return prs[0] if prs else None


def get_pr_feedback(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch PR reviews, inline review comments, conversation comments, changed files, and CI status."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    pr = github_request("GET", f"/pulls/{pr_number}", repo=target_repo, token=auth_token)
    head_sha = (pr.get("head") or {}).get("sha") or ""
    reviews = _get_paginated_list(f"/pulls/{pr_number}/reviews", repo=target_repo, token=auth_token)
    inline_comments = _get_paginated_list(f"/pulls/{pr_number}/comments", repo=target_repo, token=auth_token)
    issue_comments = _get_paginated_list(f"/issues/{pr_number}/comments", repo=target_repo, token=auth_token)
    changed_files = _get_paginated_list(f"/pulls/{pr_number}/files", repo=target_repo, token=auth_token)
    ci_status = _get_pr_ci_status(head_sha, repo=target_repo, token=auth_token)
    review_summary = _summarize_pr_reviews(reviews, head_sha)

    actionable_reviews = [
        {
            "id": rev.get("id"),
            "user": (rev.get("user") or {}).get("login"),
            "state": rev.get("state"),
            "commit_id": rev.get("commit_id"),
            "submitted_at": rev.get("submitted_at"),
            "body": rev.get("body") or "",
        }
        for rev in reviews
        if (rev.get("state") or "").upper() in ("CHANGES_REQUESTED", "APPROVED") or (rev.get("body") or "").strip()
    ]
    formatted_inline = [
        {
            "id": c.get("id"),
            "user": (c.get("user") or {}).get("login"),
            "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"),
            "body": c.get("body") or "",
            "diff_hunk": c.get("diff_hunk") or "",
            "in_reply_to_id": c.get("in_reply_to_id"),
        }
        for c in inline_comments
    ]
    formatted_comments = [
        {
            "id": c.get("id"),
            "user": (c.get("user") or {}).get("login"),
            "created_at": c.get("created_at"),
            "body": c.get("body") or "",
        }
        for c in issue_comments
    ]
    return {
        "pr_number": pr.get("number"),
        "pr_url": pr.get("html_url"),
        "title": pr.get("title"),
        "head_branch": (pr.get("head") or {}).get("ref"),
        "head_sha": head_sha,
        "base_branch": (pr.get("base") or {}).get("ref"),
        "issue_number": _extract_issue_number_from_pr(pr),
        "rework_round": review_summary["changes_requested_rounds"],
        "has_changes_requested_at_head": review_summary["has_changes_requested_at_head"],
        "is_approved_at_head": review_summary["is_approved_at_head"],
        "needs_review": review_summary["needs_review"],
        "reviews": actionable_reviews,
        "inline_comments": formatted_inline,
        "issue_comments": formatted_comments,
        "changed_files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            }
            for f in changed_files
        ],
        "ci_status": ci_status,
    }


def list_review_queue(
    include_pending_ci: bool = False,
    include_reviewed: bool = False,
    all_prs: bool = False,
    include_diff: bool = False,
    domain: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List open Pull Requests targeting `main` that need automated code review."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    open_prs = _get_paginated_list("/pulls", params={"state": "open", "base": "main"}, repo=target_repo, token=auth_token)
    domain_label = (domain if domain.startswith("domain:") else f"domain:{domain}") if domain else None

    queue: List[Dict[str, Any]] = []
    for pr in open_prs:
        head_ref = ((pr.get("head") or {}).get("ref") or "").strip()
        if not all_prs and not head_ref.startswith("agent/"):
            continue
        pr_number = int(pr.get("number", 0))
        if not pr_number:
            continue

        issue_number = _extract_issue_number_from_pr(pr)
        issue_data: Optional[Dict[str, Any]] = None
        issue_labels: List[str] = []
        if issue_number is not None:
            try:
                issue_data = get_task_issue(issue_number, repo=target_repo, token=auth_token)
                issue_labels = issue_data.get("labels") or []
            except Exception:
                issue_data = None

        if not include_reviewed and any(lbl in ("agent:in-progress", "agent:blocked") for lbl in issue_labels):
            continue
        if domain_label and domain_label not in issue_labels:
            continue

        head_sha = (pr.get("head") or {}).get("sha") or ""
        reviews = _get_paginated_list(f"/pulls/{pr_number}/reviews", repo=target_repo, token=auth_token)
        review_summary = _summarize_pr_reviews(reviews, head_sha)
        if not include_reviewed and not review_summary["needs_review"]:
            continue

        ci_status = _get_pr_ci_status(head_sha, repo=target_repo, token=auth_token)
        if not include_pending_ci and ci_status["overall"] == "pending":
            continue

        changed_files = _get_paginated_list(f"/pulls/{pr_number}/files", repo=target_repo, token=auth_token)
        entry: Dict[str, Any] = {
            "pr_number": pr_number,
            "pr_url": pr.get("html_url"),
            "title": pr.get("title"),
            "author": (pr.get("user") or {}).get("login"),
            "head_branch": head_ref,
            "head_sha": head_sha,
            "base_branch": (pr.get("base") or {}).get("ref") or "main",
            "issue_number": issue_number,
            "issue_labels": issue_labels,
            "spec": issue_data.get("spec") if issue_data else None,
            "ci_status": ci_status,
            "rework_round": review_summary["changes_requested_rounds"],
            "needs_review": review_summary["needs_review"],
            "changed_files": [
                {
                    "filename": f.get("filename"),
                    "status": f.get("status"),
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                    "patch": f.get("patch"),
                }
                for f in changed_files
            ],
        }
        if include_diff:
            entry["diff"] = github_request(
                "GET",
                f"/pulls/{pr_number}",
                repo=target_repo,
                token=auth_token,
                accept="application/vnd.github.v3.diff",
            )
        queue.append(entry)

    def _queue_sort_key(item: Dict[str, Any]) -> Tuple[int, int]:
        lbls = set(item.get("issue_labels") or [])
        prio = min((PRIORITY_ORDER[l] for l in lbls if l in PRIORITY_ORDER), default=99)
        return (prio, int(item["pr_number"]))

    return sorted(queue, key=_queue_sort_key)


def _parse_inline_comment_arg(raw: str) -> Dict[str, Any]:
    """Parse `path:line:comment` CLI argument into a GitHub PR review comment object."""
    parts = raw.split(":", 2)
    if len(parts) != 3 or not parts[0].strip() or not parts[2].strip():
        raise ValueError(f"Inline comment must use 'path:line:message' format (got '{raw}').")
    try:
        line_num = int(parts[1].strip())
    except ValueError as exc:
        raise ValueError(f"Inline comment line number must be an integer (got '{parts[1]}').") from exc
    if line_num <= 0:
        raise ValueError(f"Inline comment line number must be > 0 (got {line_num}).")
    return {
        "path": parts[0].strip().replace("\\", "/"),
        "line": line_num,
        "side": "RIGHT",
        "body": parts[2].strip(),
    }


def _format_inline_comments_fallback(comments: Sequence[Dict[str, Any]]) -> str:
    """Render inline comments as Markdown bullets when falling back to body-only submission."""
    lines = ["\n### Line Comments"]
    for c in comments:
        loc = f"`{c.get('path')}:{c.get('line') or c.get('position')}`"
        lines.append(f"- {loc}: {c.get('body', '').strip()}")
    return "\n".join(lines)


def submit_pr_review(
    pr_number: int,
    event: str,
    body: str,
    comments: Optional[Sequence[Dict[str, Any]]] = None,
    max_rework_rounds: int = DEFAULT_MAX_REWORK_ROUNDS,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit a GitHub PR review (`APPROVE`, `REQUEST_CHANGES`, or `COMMENT`) and sync linked issue status."""
    normalized_event = (event or "").strip().upper()
    if normalized_event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
        raise ValueError(f"Review event must be APPROVE, REQUEST_CHANGES, or COMMENT (got '{event}').")
    if normalized_event == "REQUEST_CHANGES" and not (body or "").strip() and not comments:
        raise ValueError("REQUEST_CHANGES review requires a non-empty --body or at least one inline comment.")

    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token(prefer_reviewer=True)
    pr = github_request("GET", f"/pulls/{pr_number}", repo=target_repo, token=auth_token)
    head_sha = (pr.get("head") or {}).get("sha") or ""
    issue_number = _extract_issue_number_from_pr(pr)

    existing_reviews = _get_paginated_list(f"/pulls/{pr_number}/reviews", repo=target_repo, token=auth_token)
    review_summary = _summarize_pr_reviews(existing_reviews, head_sha)
    next_rework_round = review_summary["changes_requested_rounds"] + (1 if normalized_event == "REQUEST_CHANGES" else 0)
    circuit_breaker_tripped = (
        normalized_event == "REQUEST_CHANGES"
        and max_rework_rounds > 0
        and next_rework_round > max_rework_rounds
    )

    review_body = (body or "").strip()
    if circuit_breaker_tripped:
        review_body = (
            f"{review_body}\n\n"
            f"⚠️ Exceeded max autonomous rework rounds ({max_rework_rounds}). "
            "Transitioning linked issue to `agent:blocked` for human attention."
        ).strip()

    inline_list = list(comments or [])
    payload: Dict[str, Any] = {
        "commit_id": head_sha,
        "event": normalized_event,
        "body": review_body,
    }
    if inline_list:
        payload["comments"] = inline_list

    used_marker_fallback = False
    try:
        posted = github_request("POST", f"/pulls/{pr_number}/reviews", payload=payload, repo=target_repo, token=auth_token)
    except RuntimeError as exc:
        msg = str(exc)
        msg_lower = msg.lower()
        if "http 422" in msg_lower and "own pull request" in msg_lower and normalized_event in ("APPROVE", "REQUEST_CHANGES"):
            used_marker_fallback = True
            marker = f"<!-- agent-review:event={normalized_event} sha={head_sha} -->"
            fallback_payload: Dict[str, Any] = {
                "commit_id": head_sha,
                "event": "COMMENT",
                "body": f"{marker}\n\n{review_body}".strip(),
            }
            if inline_list:
                fallback_payload["comments"] = inline_list
            try:
                posted = github_request(
                    "POST", f"/pulls/{pr_number}/reviews", payload=fallback_payload, repo=target_repo, token=auth_token
                )
            except RuntimeError as inner_exc:
                if "http 422" in str(inner_exc).lower() and inline_list:
                    fallback_payload.pop("comments", None)
                    fallback_payload["body"] = f"{fallback_payload['body']}\n{_format_inline_comments_fallback(inline_list)}"
                    posted = github_request(
                        "POST", f"/pulls/{pr_number}/reviews", payload=fallback_payload, repo=target_repo, token=auth_token
                    )
                else:
                    raise
        elif "http 422" in msg_lower and inline_list:
            payload.pop("comments", None)
            payload["body"] = f"{review_body}\n{_format_inline_comments_fallback(inline_list)}".strip()
            posted = github_request("POST", f"/pulls/{pr_number}/reviews", payload=payload, repo=target_repo, token=auth_token)
        else:
            raise

    issue_status: Optional[str] = None
    if issue_number is not None:
        if circuit_breaker_tripped:
            block_task_issue(
                issue_number,
                reason=f"PR #{pr_number} exceeded max autonomous rework rounds ({max_rework_rounds}).\n\nLatest review:\n{review_body}",
                repo=target_repo,
                token=auth_token,
            )
            issue_status = "agent:blocked"
        elif normalized_event == "REQUEST_CHANGES":
            _set_issue_status_label(
                issue_number,
                "agent:changes-requested",
                comment=f"Automated code review on PR #{pr_number} requested changes (`agent:changes-requested`).",
                repo=target_repo,
                token=auth_token,
            )
            issue_status = "agent:changes-requested"
        elif normalized_event == "APPROVE":
            _set_issue_status_label(
                issue_number,
                "agent:approved",
                comment=f"Automated code review approved PR #{pr_number} (`agent:approved`); ready for human merge.",
                repo=target_repo,
                token=auth_token,
            )
            issue_status = "agent:approved"

    return {
        "pr_number": pr_number,
        "issue_number": issue_number,
        "event": normalized_event,
        "used_marker_fallback": used_marker_fallback,
        "circuit_breaker_tripped": circuit_breaker_tripped,
        "issue_status": issue_status,
        "review": posted,
    }


def sync_pr_review_status(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync the linked issue's `agent:*` status label from the current GitHub PR review state."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    pr = github_request("GET", f"/pulls/{pr_number}", repo=target_repo, token=auth_token)
    issue_number = _extract_issue_number_from_pr(pr)
    if issue_number is None:
        return {"pr_number": pr_number, "issue_number": None, "synced": False, "reason": "No linked issue found"}

    issue = github_request("GET", f"/issues/{issue_number}", repo=target_repo, token=auth_token)
    current_labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    if "agent:in-progress" in current_labels or "agent:blocked" in current_labels:
        return {"pr_number": pr_number, "issue_number": issue_number, "synced": False, "reason": "Issue is in-progress or blocked"}

    head_sha = (pr.get("head") or {}).get("sha") or ""
    reviews = _get_paginated_list(f"/pulls/{pr_number}/reviews", repo=target_repo, token=auth_token)
    summary = _summarize_pr_reviews(reviews, head_sha)

    target_label: Optional[str] = None
    if summary["active_changes_requested"] and summary["has_changes_requested_at_head"]:
        target_label = "agent:changes-requested"
    elif summary["is_approved_at_head"]:
        target_label = "agent:approved"
    elif "agent:changes-requested" in current_labels or "agent:approved" in current_labels:
        target_label = "agent:review"

    if target_label and target_label not in current_labels:
        _set_issue_status_label(issue_number, target_label, issue_data=issue, repo=target_repo, token=auth_token)
        return {"pr_number": pr_number, "issue_number": issue_number, "synced": True, "status": target_label}
    return {"pr_number": pr_number, "issue_number": issue_number, "synced": False, "status": target_label}


def get_next_rework_task(
    domain: Optional[str] = None,
    max_rework_rounds: int = DEFAULT_MAX_REWORK_ROUNDS,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Find the highest-priority open PR with requested changes (from human or auto-reviewer)."""
    target_repo = repo or detect_repo_slug()
    auth_token = token or get_github_token()
    open_prs = _get_paginated_list("/pulls", params={"state": "open", "base": "main"}, repo=target_repo, token=auth_token)
    domain_label = (domain if domain.startswith("domain:") else f"domain:{domain}") if domain else None

    candidates: List[Tuple[Tuple[int, int], Dict[str, Any], Dict[str, Any], Dict[str, Any]]] = []
    for pr in open_prs:
        head_ref = ((pr.get("head") or {}).get("ref") or "").strip()
        if not head_ref.startswith("agent/"):
            continue
        issue_number = _extract_issue_number_from_pr(pr)
        if issue_number is None:
            continue
        issue_data = get_task_issue(issue_number, repo=target_repo, token=auth_token)
        if issue_data.get("state") != "open":
            continue
        labels = issue_data.get("labels") or []
        if "agent:in-progress" in labels or "agent:blocked" in labels:
            continue
        if domain_label and domain_label not in labels:
            continue

        pr_number = int(pr["number"])
        head_sha = (pr.get("head") or {}).get("sha") or ""
        reviews = _get_paginated_list(f"/pulls/{pr_number}/reviews", repo=target_repo, token=auth_token)
        review_summary = _summarize_pr_reviews(reviews, head_sha)

        needs_rework = "agent:changes-requested" in labels or review_summary["has_changes_requested_at_head"]
        if not needs_rework:
            continue

        if max_rework_rounds > 0 and review_summary["changes_requested_rounds"] > max_rework_rounds:
            block_task_issue(
                issue_number,
                reason=f"PR #{pr_number} exceeded max rework rounds ({max_rework_rounds}).",
                repo=target_repo,
                token=auth_token,
            )
            continue

        prio = min((PRIORITY_ORDER[l] for l in labels if l in PRIORITY_ORDER), default=99)
        candidates.append(((prio, issue_number), issue_data, pr, review_summary))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    _, task, pr, _ = candidates[0]
    pr_number = int(pr["number"])
    task["branch"] = ((pr.get("head") or {}).get("ref") or f"agent/issue-{task['number']}").strip()
    task["rework"] = True
    task["resume_branch"] = True
    task["pr_feedback"] = get_pr_feedback(pr_number, repo=target_repo, token=auth_token)
    return task


def get_next_task(
    domain: Optional[str] = None,
    reclaim_stale_hours: Optional[float] = None,
    include_rework: bool = True,
    max_rework_rounds: int = DEFAULT_MAX_REWORK_ROUNDS,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return the next rework PR (prioritized) or highest-priority `agent:ready` issue."""
    if reclaim_stale_hours is not None and reclaim_stale_hours > 0:
        reclaim_stale_in_progress_issues(
            max_age_hours=reclaim_stale_hours,
            repo=repo,
            token=token,
        )
    if include_rework:
        rework_task = get_next_rework_task(
            domain=domain,
            max_rework_rounds=max_rework_rounds,
            repo=repo,
            token=token,
        )
        if rework_task is not None:
            return rework_task

    ready_task = get_next_ready_issue(domain=domain, repo=repo, token=token)
    if ready_task is not None:
        ready_task["rework"] = False
        ready_task["resume_branch"] = False
    return ready_task


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GitHub Issues-backed autonomous task backlog CLI")
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name (defaults to git origin)")
    parser.add_argument("--cwd", default=None, help="Optional working directory (e.g. isolated git worktree path)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Enable GitHub Issues and sync standard agentic labels")

    create_p = subparsers.add_parser("create", help="Create a deduplicated agentic GitHub Issue")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--objective", required=True)
    create_p.add_argument("--owned-paths", nargs="+", required=True)
    create_p.add_argument("--forbidden-paths", nargs="*", default=None)
    create_p.add_argument("--acceptance", nargs="+", required=True)
    create_p.add_argument("--verify", nargs="+", required=True)
    create_p.add_argument("--context", default=None, help="Background, motivation, or telemetry/CI evidence")
    create_p.add_argument("--example", nargs="*", default=None, help="Concrete examples (payloads, CLI usage, logs)")
    create_p.add_argument("--visual", nargs="*", default=None, help="Mermaid diagrams, ASCII mockups, or image markdown/URLs")
    create_p.add_argument("--note", nargs="*", default=None, help="Implementation hints or edge-case notes")
    create_p.add_argument("--priority", choices=["p1", "p2", "p3"], default="p2")
    create_p.add_argument("--source", choices=["roadmap", "telemetry", "test-gap", "data-drift"], default="roadmap")
    create_p.add_argument("--domain", nargs="*", default=[])
    create_p.add_argument("--status", choices=["proposed", "ready"], default="proposed")
    create_p.add_argument("--json", action="store_true")

    update_p = subparsers.add_parser("update", help="Enrich or update an existing agentic GitHub Issue")
    update_p.add_argument("issue_number", type=int)
    update_p.add_argument("--title", default=None)
    update_p.add_argument("--objective", default=None)
    update_p.add_argument("--owned-paths", nargs="+", default=None)
    update_p.add_argument("--forbidden-paths", nargs="*", default=None)
    update_p.add_argument("--acceptance", nargs="+", default=None)
    update_p.add_argument("--verify", nargs="+", default=None)
    update_p.add_argument("--context", default=None)
    update_p.add_argument("--example", nargs="*", default=None)
    update_p.add_argument("--visual", nargs="*", default=None)
    update_p.add_argument("--note", nargs="*", default=None)
    update_p.add_argument("--json", action="store_true")

    upload_p = subparsers.add_parser("upload-screenshots", help="Upload local PNGs to the orphan screenshots branch")
    upload_p.add_argument("--files", nargs="+", required=True, help="Local image file paths")
    upload_p.add_argument("--prefix", default="misc", help="Target folder prefix in the screenshots branch")
    upload_p.add_argument("--branch", default=SCREENSHOT_BRANCH, help="Target orphan branch name")
    upload_p.add_argument("--message", default="Upload UI screenshots", help="Commit message")
    upload_p.add_argument("--json", action="store_true")

    list_p = subparsers.add_parser("list", help="List backlog issues sorted by priority")
    list_p.add_argument(
        "--status",
        choices=[
            "proposed",
            "ready",
            "in-progress",
            "review",
            "changes-requested",
            "approved",
            "blocked",
            "all",
        ],
        default="ready",
    )
    list_p.add_argument("--domain", default=None)
    list_p.add_argument("--state", choices=["open", "closed", "all"], default="open")
    list_p.add_argument("--json", action="store_true")

    get_p = subparsers.add_parser("get", help="Fetch an issue and parse its task spec")
    get_p.add_argument("issue_number", type=int)
    get_p.add_argument("--json", action="store_true")

    next_p = subparsers.add_parser(
        "next",
        help="Fetch the next rework PR (changes requested) or highest-priority approved (agent:ready) task",
    )
    next_p.add_argument("--domain", default=None)
    next_p.add_argument("--claim", action="store_true")
    next_p.add_argument("--agent", default="autonomous-executor")
    next_p.add_argument("--checkout", action="store_true")
    next_p.add_argument("--worktree", action="store_true", help="Create an isolated git worktree")
    next_p.add_argument("--no-rework", action="store_true", help="Skip PR rework queue and only check agent:ready issues")
    next_p.add_argument(
        "--max-rework-rounds",
        type=int,
        default=DEFAULT_MAX_REWORK_ROUNDS,
        help="Block PR tasks that exceed N rework cycles (default: 3)",
    )
    next_p.add_argument(
        "--reclaim-stale-hours",
        type=float,
        default=None,
        help="Reclaim stale agent:in-progress issues older than N hours before selecting the next task",
    )
    next_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional repository working directory")
    next_p.add_argument("--json", action="store_true")

    worktree_p = subparsers.add_parser(
        "worktree",
        help="Create or clean up an isolated agent/... git worktree rooted at latest origin/main or origin/<branch>",
    )
    worktree_p.add_argument("--branch", required=True, help="Isolated agent/... branch name")
    worktree_p.add_argument("--base", default="main", help="Base branch to fetch and branch from (default: main)")
    worktree_p.add_argument("--resume", action="store_true", help="Resume from existing remote origin/<branch> instead of base")
    worktree_p.add_argument("--path", default=None, help="Optional explicit worktree directory path")
    worktree_p.add_argument("--remove", action="store_true", help="Remove the worktree instead of creating it")
    worktree_p.add_argument(
        "--delete-branch",
        action="store_true",
        help="Also delete the local agent/... branch when removing the worktree",
    )
    worktree_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional repository working directory")
    worktree_p.add_argument("--json", action="store_true")

    approve_p = subparsers.add_parser("approve", help="Approve a proposed issue (transition agent:proposed -> agent:ready)")
    approve_p.add_argument("issue_number", type=int)

    claim_p = subparsers.add_parser("claim", help="Claim an issue as agent:in-progress")
    claim_p.add_argument("issue_number", type=int)
    claim_p.add_argument("--agent", required=True)
    claim_p.add_argument("--branch", default=None)

    block_p = subparsers.add_parser("block", help="Mark an issue agent:blocked with a diagnostic reason")
    block_p.add_argument("issue_number", type=int)
    block_p.add_argument("--reason", required=True)
    block_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional working directory")

    complete_p = subparsers.add_parser("complete", help="Mark an issue agent:review or close it")
    complete_p.add_argument("issue_number", type=int)
    complete_p.add_argument("--summary", default="")
    complete_p.add_argument("--example", nargs="*", default=None, help="Concrete usage/API/before-after examples for the PR")
    complete_p.add_argument("--verification", default="", help="Markdown verification results summary")
    complete_p.add_argument("--verify-report", default=None, help="Path to Markdown verification report (e.g. from verify_task.py --report-markdown)")
    complete_p.add_argument("--screenshot", nargs="*", default=None, help="Local screenshot paths (uploaded to orphan branch) or image URLs/Markdown")
    complete_p.add_argument("--pr", default=None)
    complete_p.add_argument("--push", action="store_true", help="Safely push the validated agent/... branch to origin before completing")
    complete_p.add_argument("--open-pr", action="store_true", help="Open or reuse a GitHub Pull Request for the task branch")
    complete_p.add_argument("--base", default="main", help="Base branch for the pull request")
    complete_p.add_argument("--close", action="store_true")
    complete_p.add_argument("--cwd", dest="sub_cwd", default=None, help="Optional working directory (e.g. git worktree)")

    rq_p = subparsers.add_parser("review-queue", help="List open Pull Requests awaiting code review")
    rq_p.add_argument("--include-pending-ci", action="store_true", help="Include PRs whose CI checks are still pending")
    rq_p.add_argument("--include-reviewed", action="store_true", help="Include PRs already reviewed at current head SHA")
    rq_p.add_argument("--all-prs", action="store_true", help="Include non-agent/* PRs targeting main")
    rq_p.add_argument("--with-diff", action="store_true", help="Fetch full unified diff for each queued PR")
    rq_p.add_argument("--domain", default=None)
    rq_p.add_argument("--json", action="store_true")

    fb_p = subparsers.add_parser("pr-feedback", help="Fetch reviews, inline comments, and CI status for a PR or issue")
    fb_p.add_argument("number", type=int, help="PR number (or issue number if --issue is set)")
    fb_p.add_argument("--issue", action="store_true", help="Treat number as an issue number and look up its open PR")
    fb_p.add_argument("--json", action="store_true")

    sr_p = subparsers.add_parser("submit-review", help="Submit a PR review (APPROVE, REQUEST_CHANGES, COMMENT) and sync issue status")
    sr_p.add_argument("pr_number", type=int)
    sr_p.add_argument("--event", required=True, choices=["APPROVE", "REQUEST_CHANGES", "COMMENT", "approve", "request_changes", "comment"])
    sr_p.add_argument("--body", default="")
    sr_p.add_argument("--comment", action="append", default=[], help="Inline review comment in 'path:line:message' format")
    sr_p.add_argument("--comments-json", default=None, help="Path to JSON file containing list of {path, line, body} comments")
    sr_p.add_argument("--max-rework-rounds", type=int, default=DEFAULT_MAX_REWORK_ROUNDS)
    sr_p.add_argument("--json", action="store_true")

    sync_p = subparsers.add_parser("sync-pr-review", help="Sync linked issue label from a PR's current GitHub review state")
    sync_p.add_argument("--pr", type=int, required=True)
    sync_p.add_argument("--json", action="store_true")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    target_cwd = getattr(args, "sub_cwd", None) or getattr(args, "cwd", None)
    if target_cwd:
        os.chdir(target_cwd)
    else:
        inside_proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
        )
        if inside_proc.returncode != 0:
            script_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if os.path.isdir(os.path.join(script_repo_root, ".git")):
                os.chdir(script_repo_root)

    if args.command == "init":
        result = init_repo(repo=args.repo)
        print(
            f"Initialized {result['repo']} (has_issues={result['has_issues']}): "
            f"{result['labels_created']} labels created, {result['labels_updated']} updated "
            f"({result['total_standard_labels']} standard labels)."
        )
        return 0

    if args.command == "create":
        res = create_task_issue(
            title=args.title,
            objective=args.objective,
            owned_paths=args.owned_paths,
            forbidden_paths=args.forbidden_paths,
            acceptance_criteria=args.acceptance,
            verification_commands=args.verify,
            context=args.context,
            examples=args.example,
            visuals=args.visual,
            implementation_notes=args.note,
            priority=args.priority,
            source=args.source,
            domains=args.domain,
            initial_status=args.status,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            issue = res["issue"]
            action = "Existing open issue matched" if res["deduplicated"] else "Created issue"
            print(f"{action}: #{issue['number']} {issue['title']} ({issue['html_url']})")
        return 0

    if args.command == "update":
        updated = update_task_issue(
            args.issue_number,
            title=args.title,
            objective=args.objective,
            owned_paths=args.owned_paths,
            forbidden_paths=args.forbidden_paths,
            acceptance_criteria=args.acceptance,
            verification_commands=args.verify,
            context=args.context,
            examples=args.example,
            visuals=args.visual,
            implementation_notes=args.note,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(updated, indent=2))
        else:
            print(f"Updated #{updated['number']} {updated['title']} ({updated['html_url']})")
        return 0

    if args.command == "upload-screenshots":
        clean_prefix = args.prefix.strip("/")
        mappings = {
            f: (f"{clean_prefix}/{os.path.basename(f)}" if clean_prefix else os.path.basename(f))
            for f in args.files
        }
        uploaded = upload_screenshots(
            mappings,
            commit_message=args.message,
            branch=args.branch,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(uploaded, indent=2))
        else:
            for item in uploaded:
                print(item["markdown"])
        return 0

    if args.command == "list":
        issues = list_task_issues(
            status=args.status,
            domain=args.domain,
            state=args.state,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(issues, indent=2))
        else:
            print(f"Found {len(issues)} issue(s):")
            for issue in issues:
                lbls = ", ".join(l.get("name", "") for l in issue.get("labels", []))
                print(f"  #{issue['number']} [{lbls}] {issue['title']}")
        return 0

    if args.command == "get":
        data = get_task_issue(args.issue_number, repo=args.repo)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"#{data['number']} {data['title']} ({data['state']}) - {data['html_url']}")
            print(f"Labels: {', '.join(data['labels'])}")
            if data["spec_error"]:
                print(f"Spec Error: {data['spec_error']}")
            else:
                print(json.dumps(data["spec"], indent=2))
        return 0

    if args.command == "next":
        task = get_next_task(
            domain=args.domain,
            reclaim_stale_hours=args.reclaim_stale_hours,
            include_rework=not args.no_rework,
            max_rework_rounds=args.max_rework_rounds,
            repo=args.repo,
        )
        if task is None:
            if args.json:
                print("null")
            else:
                print("No rework PRs or approved (agent:ready) issues queued.")
            return 0
        resume = bool(task.get("resume_branch"))
        if args.worktree:
            task["worktree_path"] = (
                prepare_task_worktree(task["branch"], resume_existing=True)
                if resume
                else prepare_task_worktree(task["branch"])
            )
        elif args.checkout:
            prepare_task_branch(task["branch"], resume_existing=resume)
        if args.claim:
            claim_task_issue(
                int(task["number"]),
                agent_name=args.agent,
                branch=task["branch"],
                allow_rework=bool(task.get("rework")),
                repo=args.repo,
            )
            task["claimed"] = True
        if args.json:
            print(json.dumps(task, indent=2))
        else:
            wt_note = f" in {task['worktree_path']}" if task.get("worktree_path") else ""
            kind = "[REWORK] " if task.get("rework") else ""
            print(f"{kind}#{task['number']} {task['title']} -> branch {task['branch']}{wt_note} ({task['html_url']})")
        return 0

    if args.command == "worktree":
        if args.remove:
            removed_path = cleanup_task_worktree(
                worktree_path=args.path,
                branch=args.branch,
                delete_branch=args.delete_branch,
            )
            payload = {
                "removed": True,
                "branch": args.branch,
                "worktree_path": removed_path,
                "deleted_branch": bool(args.delete_branch),
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Removed worktree for {args.branch} ({removed_path})")
            return 0
        wt_path = (
            prepare_task_worktree(
                args.branch,
                worktree_path=args.path,
                base_branch=args.base,
                resume_existing=True,
            )
            if args.resume
            else prepare_task_worktree(
                args.branch,
                worktree_path=args.path,
                base_branch=args.base,
            )
        )
        payload = {"branch": args.branch, "base_branch": args.base, "resume": bool(args.resume), "worktree_path": wt_path}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            src_note = f"origin/{args.branch}" if args.resume else f"origin/{args.base}"
            print(f"Prepared worktree for {args.branch} from {src_note} at {wt_path}")
        return 0

    if args.command == "approve":
        updated = approve_task_issue(args.issue_number, repo=args.repo)
        print(f"Approved #{updated['number']} ({updated['html_url']}) as agent:ready.")
        return 0

    if args.command == "claim":
        updated = claim_task_issue(
            args.issue_number,
            agent_name=args.agent,
            branch=args.branch,
            repo=args.repo,
        )
        print(f"Claimed #{updated['number']} ({updated['html_url']}) as agent:in-progress.")
        return 0

    if args.command == "block":
        updated = block_task_issue(
            args.issue_number,
            reason=args.reason,
            repo=args.repo,
        )
        print(f"Marked #{updated['number']} ({updated['html_url']}) as agent:blocked.")
        return 0

    if args.command == "complete":
        verification_text = args.verification or ""
        if args.verify_report:
            with open(args.verify_report, "r", encoding="utf-8") as vf:
                report_content = vf.read().strip()
            verification_text = f"{verification_text}\n\n{report_content}".strip() if verification_text else report_content
        updated = complete_task_issue(
            args.issue_number,
            summary=args.summary,
            pr=args.pr,
            push=args.push,
            open_pr=args.open_pr,
            base_branch=args.base,
            close=args.close,
            examples=args.example,
            verification_results=verification_text,
            screenshots=args.screenshot,
            repo=args.repo,
        )
        pr_note = f" (PR: {updated['pull_request']['html_url']})" if updated.get("pull_request") else ""
        print(f"Completed #{updated['number']} (state={updated['state']}) -> {updated['html_url']}{pr_note}")
        return 0

    if args.command == "review-queue":
        queue = list_review_queue(
            include_pending_ci=args.include_pending_ci,
            include_reviewed=args.include_reviewed,
            all_prs=args.all_prs,
            include_diff=args.with_diff,
            domain=args.domain,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(queue, indent=2))
        else:
            print(f"Found {len(queue)} PR(s) in review queue:")
            for item in queue:
                issue_str = f" (issue #{item['issue_number']})" if item.get("issue_number") else ""
                ci_overall = (item.get("ci_status") or {}).get("overall", "none")
                print(
                    f"  PR #{item['pr_number']}{issue_str} [{item['head_branch']}] "
                    f"CI={ci_overall} round={item.get('rework_round', 0)}: {item['title']}"
                )
        return 0

    if args.command == "pr-feedback":
        target_pr = args.number
        if args.issue:
            found_pr = _find_open_pr_for_issue(args.number, repo=args.repo)
            if not found_pr:
                raise RuntimeError(f"No open Pull Request found for issue #{args.number}.")
            target_pr = int(found_pr["number"])
        feedback = get_pr_feedback(target_pr, repo=args.repo)
        if args.json:
            print(json.dumps(feedback, indent=2))
        else:
            print(
                f"PR #{feedback['pr_number']} ({feedback['head_branch']}) "
                f"rework_round={feedback['rework_round']} changes_requested={feedback['has_changes_requested_at_head']}"
            )
            for rev in feedback["reviews"]:
                print(f"  Review [{rev['state']}] by {rev['user']}: {rev['body'][:120]}")
            for ic in feedback["inline_comments"]:
                print(f"  Inline {ic['path']}:{ic['line']} by {ic['user']}: {ic['body'][:120]}")
        return 0

    if args.command == "submit-review":
        inline_comments: List[Dict[str, Any]] = [_parse_inline_comment_arg(c) for c in args.comment]
        if args.comments_json:
            with open(args.comments_json, "r", encoding="utf-8") as cf:
                loaded = json.load(cf)
            if not isinstance(loaded, list):
                raise ValueError("--comments-json must contain a JSON array of comment objects.")
            for entry in loaded:
                inline_comments.append(
                    {
                        "path": str(entry["path"]).strip().replace("\\", "/"),
                        "line": int(entry["line"]),
                        "side": entry.get("side", "RIGHT"),
                        "body": str(entry["body"]).strip(),
                    }
                )
        res = submit_pr_review(
            args.pr_number,
            event=args.event,
            body=args.body,
            comments=inline_comments or None,
            max_rework_rounds=args.max_rework_rounds,
            repo=args.repo,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            note = f" -> issue #{res['issue_number']} [{res['issue_status']}]" if res.get("issue_number") else ""
            print(f"Submitted {res['event']} review on PR #{res['pr_number']}{note}.")
        return 0

    if args.command == "sync-pr-review":
        res = sync_pr_review_status(args.pr, repo=args.repo)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(
                f"PR #{res['pr_number']} -> issue #{res.get('issue_number')} "
                f"(synced={res.get('synced')}, status={res.get('status')})"
            )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
