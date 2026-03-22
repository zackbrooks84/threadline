"""
threadline MCP server — exposes checkpoint/handoff tools to AI agents.

Run with:
    uv run python -m threadline.mcp_server

Or install and run:
    threadline-mcp

Requires the [mcp] optional dependency:
    pip install 'threadline[mcp]'

Once running, add to Claude Code config:
    {
      "mcpServers": {
        "threadline": {
          "command": "python",
          "args": ["-m", "threadline.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from fastmcp import FastMCP
except ImportError:
    print(
        "fastmcp is not installed. Install it with: pip install 'threadline[mcp]'",
        file=sys.stderr,
    )
    sys.exit(1)

from .models import Checkpoint, Decision
from .store import Store
from .handoff import generate_handoff


def _store() -> Store:
    db = os.environ.get("THREADLINE_DB")
    return Store(db_path=db if db else None)


def _git_ref() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None


mcp = FastMCP("threadline")


@mcp.tool()
def threadline_checkpoint(
    project: str,
    task: str,
    goal: str,
    status: str = "in-progress",
    context: str = "",
    findings: list[str] | None = None,
    dead_ends: list[str] | None = None,
    next_steps: list[str] | None = None,
    open_questions: list[str] | None = None,
    files_changed: list[str] | None = None,
    decisions: list[dict] | None = None,
    agent: str | None = None,
) -> dict:
    """
    Save a checkpoint of the current work state.

    Use this whenever you want to preserve where you are so work can be
    resumed — by you in a future session, or by another agent.

    Args:
        project: Project identifier (e.g. 'autoresearch_cpu', 'helixos')
        task: What you are doing RIGHT NOW, concisely
        goal: The overall goal this work is driving toward
        status: 'in-progress' | 'blocked' | 'complete' | 'abandoned'
        context: Background, constraints, or relevant history
        findings: Things you've learned that are useful to know
        dead_ends: Approaches tried and ruled out — don't repeat these
        next_steps: Ordered list of what to do next (first item = most immediate)
        open_questions: Unresolved questions that need answers
        files_changed: Files created or modified in this work
        decisions: List of {what, why, alternatives_rejected} dicts
        agent: Your agent identifier (e.g. 'claude-sonnet-4-6')

    Returns:
        dict with 'checkpoint_id' and confirmation message
    """
    store = _store()

    parsed_decisions = []
    for d in (decisions or []):
        parsed_decisions.append(Decision(
            what=d.get("what", ""),
            why=d.get("why", ""),
            alternatives_rejected=d.get("alternatives_rejected", []),
        ))

    cp = Checkpoint(
        project=project,
        current_task=task,
        goal=goal,
        status=status,
        context=context,
        findings=findings or [],
        dead_ends=dead_ends or [],
        decisions=parsed_decisions,
        next_steps=next_steps or [],
        open_questions=open_questions or [],
        files_changed=files_changed or [],
        git_ref=_git_ref(),
        agent=agent,
    )
    store.save_checkpoint(cp)
    return {
        "checkpoint_id": cp.id,
        "project": cp.project,
        "saved_at": cp.timestamp.isoformat(),
        "message": f"Checkpoint saved for project '{project}'",
    }


@mcp.tool()
def threadline_handoff(
    project: str,
    checkpoint_id: str | None = None,
    target_agent: str | None = None,
    save: bool = True,
) -> dict:
    """
    Generate a handoff document to resume work in a new session.

    Returns a structured markdown document with executive summary,
    full context, immediate action, and dead ends to avoid.

    Args:
        project: Project to generate handoff for
        checkpoint_id: Specific checkpoint (default: latest)
        target_agent: Who will receive the handoff (optional, informational)
        save: Whether to persist the handoff to the store

    Returns:
        dict with 'executive_summary', 'full_context', 'immediate_action',
        'watch_out_for', and 'handoff_id'
    """
    store = _store()

    if checkpoint_id:
        cp = store.get_checkpoint(checkpoint_id)
        if not cp:
            return {"error": f"Checkpoint not found: {checkpoint_id}"}
    else:
        cp = store.latest_checkpoint(project)
        if not cp:
            return {"error": f"No checkpoints found for project '{project}'"}

    h = generate_handoff(cp, target_agent=target_agent)
    if save:
        store.save_handoff(h)

    return {
        "handoff_id": h.id,
        "checkpoint_id": h.checkpoint_id,
        "executive_summary": h.executive_summary,
        "full_context": h.full_context,
        "immediate_action": h.immediate_action,
        "watch_out_for": h.watch_out_for,
    }


@mcp.tool()
def threadline_status(project: str) -> dict:
    """
    Get the current work state for a project.

    Returns the latest checkpoint's task, goal, status, next steps,
    and open questions.

    Args:
        project: Project identifier

    Returns:
        dict with work state, or {'error': ...} if no checkpoints exist
    """
    store = _store()
    cp = store.latest_checkpoint(project)
    if not cp:
        return {"error": f"No checkpoints found for project '{project}'"}

    return {
        "project": cp.project,
        "current_task": cp.current_task,
        "goal": cp.goal,
        "status": cp.status,
        "timestamp": cp.timestamp.isoformat(),
        "next_steps": cp.next_steps,
        "open_questions": cp.open_questions,
        "findings": cp.findings,
        "dead_ends": cp.dead_ends,
        "git_ref": cp.git_ref,
        "agent": cp.agent,
        "checkpoint_id": cp.id,
    }


@mcp.tool()
def threadline_history(
    project: str | None = None,
    limit: int = 10,
) -> dict:
    """
    List recent checkpoints, optionally filtered by project.

    Args:
        project: Filter by project (None = all projects)
        limit: Max number of checkpoints to return

    Returns:
        dict with 'checkpoints' list
    """
    store = _store()
    checkpoints = store.list_checkpoints(project=project, limit=limit)
    return {
        "checkpoints": [
            {
                "id": cp.id,
                "project": cp.project,
                "task": cp.current_task,
                "status": cp.status,
                "timestamp": cp.timestamp.isoformat(),
                "git_ref": cp.git_ref,
            }
            for cp in checkpoints
        ]
    }


@mcp.tool()
def threadline_projects() -> dict:
    """
    List all projects that have checkpoints.

    Returns:
        dict with 'projects' list, each with latest task and status
    """
    store = _store()
    project_names = store.list_projects()
    projects = []
    for name in project_names:
        cp = store.latest_checkpoint(name)
        projects.append({
            "project": name,
            "latest_task": cp.current_task if cp else None,
            "latest_status": cp.status if cp else None,
            "latest_timestamp": cp.timestamp.isoformat() if cp else None,
        })
    return {"projects": projects}


if __name__ == "__main__":
    mcp.run()
