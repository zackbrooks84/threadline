"""Core tests for threadline — models, store, handoff generation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from threadline.models import Checkpoint, Decision, Handoff
from threadline.store import Store
from threadline.handoff import generate_handoff


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """Temporary in-memory-ish store backed by a temp file."""
    db = tmp_path / "test.db"
    s = Store(db_path=db)
    yield s
    s.close()


@pytest.fixture
def basic_checkpoint():
    return Checkpoint(
        project="testproject",
        current_task="writing unit tests",
        goal="ensure threadline is reliable",
        status="in-progress",
        context="pytest, tempfile fixtures",
        findings=["Store persists correctly", "handoff generation works"],
        dead_ends=["tried unittest — too verbose"],
        decisions=[
            Decision(
                what="use pytest",
                why="cleaner fixtures and assertion introspection",
                alternatives_rejected=["unittest", "nose2"],
            )
        ],
        next_steps=["run tests in CI", "add CLI integration tests"],
        open_questions=["should we test MCP server?"],
        files_changed=["tests/test_core.py"],
        agent="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestCheckpoint:
    def test_defaults(self):
        cp = Checkpoint(project="p", current_task="t", goal="g")
        assert cp.status == "in-progress"
        assert cp.findings == []
        assert cp.dead_ends == []
        assert cp.next_steps == []
        assert cp.id  # uuid generated

    def test_roundtrip_json(self, basic_checkpoint):
        json_str = basic_checkpoint.model_dump_json()
        restored = Checkpoint.model_validate_json(json_str)
        assert restored.id == basic_checkpoint.id
        assert restored.project == basic_checkpoint.project
        assert restored.findings == basic_checkpoint.findings
        assert len(restored.decisions) == 1
        assert restored.decisions[0].alternatives_rejected == ["unittest", "nose2"]

    def test_decision_structure(self):
        d = Decision(what="use SQLite", why="no server needed", alternatives_rejected=["Postgres"])
        assert d.what == "use SQLite"
        assert "Postgres" in d.alternatives_rejected


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_and_retrieve(self, store, basic_checkpoint):
        store.save_checkpoint(basic_checkpoint)
        retrieved = store.get_checkpoint(basic_checkpoint.id)
        assert retrieved is not None
        assert retrieved.id == basic_checkpoint.id
        assert retrieved.current_task == basic_checkpoint.current_task

    def test_latest_checkpoint(self, store):
        cp1 = Checkpoint(project="myproject", current_task="task 1", goal="g")
        cp2 = Checkpoint(project="myproject", current_task="task 2", goal="g")
        store.save_checkpoint(cp1)
        store.save_checkpoint(cp2)
        latest = store.latest_checkpoint("myproject")
        # cp2 was saved last — should be latest
        assert latest.current_task == "task 2"

    def test_latest_returns_none_for_unknown_project(self, store):
        assert store.latest_checkpoint("nonexistent") is None

    def test_get_returns_none_for_unknown_id(self, store):
        assert store.get_checkpoint("00000000-0000-0000-0000-000000000000") is None

    def test_list_checkpoints_filtered(self, store):
        cp_a = Checkpoint(project="alpha", current_task="a", goal="g")
        cp_b = Checkpoint(project="beta", current_task="b", goal="g")
        store.save_checkpoint(cp_a)
        store.save_checkpoint(cp_b)

        alpha_list = store.list_checkpoints(project="alpha")
        assert len(alpha_list) == 1
        assert alpha_list[0].project == "alpha"

    def test_list_checkpoints_all(self, store):
        for i in range(5):
            store.save_checkpoint(Checkpoint(project=f"proj{i}", current_task="t", goal="g"))
        all_cps = store.list_checkpoints(project=None, limit=10)
        assert len(all_cps) == 5

    def test_list_respects_limit(self, store):
        for i in range(10):
            store.save_checkpoint(Checkpoint(project="p", current_task=f"task {i}", goal="g"))
        limited = store.list_checkpoints(project="p", limit=3)
        assert len(limited) == 3

    def test_search(self, store):
        cp = Checkpoint(
            project="p", current_task="debug auth flow", goal="g",
            findings=["JWT expiry is 15 minutes"]
        )
        store.save_checkpoint(cp)
        results = store.search_checkpoints("p", "JWT")
        assert len(results) == 1
        assert results[0].id == cp.id

    def test_search_no_results(self, store, basic_checkpoint):
        store.save_checkpoint(basic_checkpoint)
        results = store.search_checkpoints("testproject", "xyznotfound")
        assert results == []

    def test_list_projects(self, store):
        for name in ["alpha", "beta", "gamma"]:
            store.save_checkpoint(Checkpoint(project=name, current_task="t", goal="g"))
        projects = store.list_projects()
        assert set(projects) == {"alpha", "beta", "gamma"}

    def test_save_handoff(self, store, basic_checkpoint):
        store.save_checkpoint(basic_checkpoint)
        h = generate_handoff(basic_checkpoint)
        store.save_handoff(h)
        latest = store.latest_handoff("testproject")
        assert latest is not None
        assert latest.checkpoint_id == basic_checkpoint.id

    def test_overwrite_checkpoint(self, store, basic_checkpoint):
        store.save_checkpoint(basic_checkpoint)
        basic_checkpoint.status = "complete"
        store.save_checkpoint(basic_checkpoint)
        retrieved = store.get_checkpoint(basic_checkpoint.id)
        assert retrieved.status == "complete"


# ---------------------------------------------------------------------------
# Handoff generation tests
# ---------------------------------------------------------------------------

class TestHandoff:
    def test_generates_handoff(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint)
        assert isinstance(h, Handoff)
        assert h.checkpoint_id == basic_checkpoint.id
        assert h.project == basic_checkpoint.project

    def test_executive_summary_contains_key_info(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint)
        assert "testproject" in h.executive_summary
        assert "in progress" in h.executive_summary.lower() or "in-progress" in h.executive_summary.lower()

    def test_immediate_action_is_first_next_step(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint)
        assert h.immediate_action == basic_checkpoint.next_steps[0]

    def test_watch_out_for_contains_dead_ends(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint)
        assert basic_checkpoint.dead_ends[0] in h.watch_out_for

    def test_full_context_contains_sections(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint)
        assert "Dead Ends" in h.full_context
        assert "Key Decisions" in h.full_context
        assert "What We Know" in h.full_context
        assert "Start Here" in h.full_context

    def test_target_agent_stored(self, basic_checkpoint):
        h = generate_handoff(basic_checkpoint, target_agent="gpt-4o")
        assert h.target_agent == "gpt-4o"

    def test_no_next_steps_fallback(self):
        cp = Checkpoint(project="p", current_task="debugging", goal="fix the bug")
        h = generate_handoff(cp)
        assert "debugging" in h.immediate_action

    def test_complete_status_phrasing(self):
        cp = Checkpoint(
            project="p", current_task="deploy", goal="ship it", status="complete"
        )
        h = generate_handoff(cp)
        assert "completed" in h.executive_summary.lower()

    def test_blocked_status_phrasing(self):
        cp = Checkpoint(
            project="p", current_task="waiting on API key", goal="integrate API",
            status="blocked"
        )
        h = generate_handoff(cp)
        assert "blocked" in h.executive_summary.lower()
