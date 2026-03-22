"""Generate handoff documents from checkpoints."""

from __future__ import annotations

from .models import Checkpoint, Handoff


def generate_handoff(cp: Checkpoint, target_agent: str | None = None) -> Handoff:
    """
    Build a Handoff from a Checkpoint.

    The handoff is structured to be read at the top of a new agent session —
    executive summary first, then enough context to resume without re-deriving
    what's already known.
    """
    # Executive summary: what, where, why in 2-3 sentences
    status_phrase = {
        "in-progress": "This work is in progress",
        "blocked": "This work is currently blocked",
        "complete": "This work was completed",
        "abandoned": "This work was abandoned",
    }.get(cp.status, "Work is in an unknown state")

    exec_parts = [f"{status_phrase} on project '{cp.project}'."]
    exec_parts.append(f"Current task: {cp.current_task}.")
    exec_parts.append(f"Goal: {cp.goal}")
    executive_summary = " ".join(exec_parts)

    # Full context block
    sections: list[str] = []

    sections.append(f"# Threadline Handoff — {cp.project}")
    sections.append(f"**Checkpoint**: {cp.id}  |  **Time**: {cp.timestamp.isoformat()}")
    if cp.agent:
        sections.append(f"**Previous agent**: {cp.agent}")
    sections.append("")

    sections.append("## Goal")
    sections.append(cp.goal)
    sections.append("")

    if cp.context:
        sections.append("## Background & Constraints")
        sections.append(cp.context)
        sections.append("")

    sections.append("## Current Task")
    sections.append(f"`{cp.status}` — {cp.current_task}")
    sections.append("")

    if cp.findings:
        sections.append("## What We Know")
        for f in cp.findings:
            sections.append(f"- {f}")
        sections.append("")

    if cp.decisions:
        sections.append("## Key Decisions Made")
        for d in cp.decisions:
            sections.append(f"### {d.what}")
            sections.append(f"**Why**: {d.why}")
            if d.alternatives_rejected:
                rejected = ", ".join(d.alternatives_rejected)
                sections.append(f"**Rejected alternatives**: {rejected}")
        sections.append("")

    if cp.dead_ends:
        sections.append("## Dead Ends (Do Not Repeat)")
        for de in cp.dead_ends:
            sections.append(f"- {de}")
        sections.append("")

    if cp.open_questions:
        sections.append("## Open Questions")
        for q in cp.open_questions:
            sections.append(f"- {q}")
        sections.append("")

    if cp.files_changed:
        sections.append("## Files In Play")
        for f in cp.files_changed:
            sections.append(f"- `{f}`")
        sections.append("")

    if cp.git_ref:
        sections.append(f"**Git ref**: `{cp.git_ref}`")
        sections.append("")

    # Immediate action
    if cp.next_steps:
        immediate_action = cp.next_steps[0]
        if len(cp.next_steps) > 1:
            remaining = "\n".join(f"- {s}" for s in cp.next_steps[1:])
            sections.append("## Remaining Next Steps")
            sections.append(remaining)
            sections.append("")
    else:
        immediate_action = f"Resume work on: {cp.current_task}"

    sections.append("## Start Here")
    sections.append(f"**First action**: {immediate_action}")

    full_context = "\n".join(sections)
    watch_out_for = list(cp.dead_ends)  # dead ends are the main pitfalls

    return Handoff(
        checkpoint_id=cp.id,
        project=cp.project,
        target_agent=target_agent,
        executive_summary=executive_summary,
        full_context=full_context,
        immediate_action=immediate_action,
        watch_out_for=watch_out_for,
    )
