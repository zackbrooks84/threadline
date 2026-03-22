"""Core data models for threadline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Decision(BaseModel):
    """A key choice made during work, with reasoning."""
    what: str
    why: str
    alternatives_rejected: list[str] = Field(default_factory=list)


class Checkpoint(BaseModel):
    """A point-in-time snapshot of work state."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # What am I doing?
    current_task: str
    status: Literal["in-progress", "blocked", "complete", "abandoned"] = "in-progress"

    # Why?
    goal: str
    context: str = ""  # background, constraints, relevant history

    # What have I learned?
    findings: list[str] = Field(default_factory=list)
    dead_ends: list[str] = Field(default_factory=list)  # tried and ruled out
    decisions: list[Decision] = Field(default_factory=list)

    # What's next?
    next_steps: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    # Technical state
    files_changed: list[str] = Field(default_factory=list)
    git_ref: str | None = None
    agent: str | None = None  # "claude-sonnet-4-6", "gpt-4o", etc.
    tags: list[str] = Field(default_factory=list)

    model_config = {}


class Handoff(BaseModel):
    """Context document optimized for a new agent session to resume work."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    checkpoint_id: str
    project: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    target_agent: str | None = None

    executive_summary: str   # 2-3 sentences: what, where, why — read this first
    full_context: str         # everything the new session needs
    immediate_action: str     # the single first thing to do
    watch_out_for: list[str]  # known pitfalls / dead ends not to repeat

    model_config = {}
