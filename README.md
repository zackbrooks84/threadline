# threadline

**Work continuity engine for AI agents.**

Every AI session starts with amnesia. Memory systems store facts — but they don't preserve *why* decisions were made, what dead ends were hit, or what the exact next action is. When a session ends, the thread breaks.

Threadline keeps the thread.

```
threadline checkpoint --project myapp --task "refactoring auth middleware" \
  --goal "make sessions comply with new security requirements" \
  --finding "JWT tokens currently stored in localStorage — insecure" \
  --dead-end "tried httpOnly cookies, broke SSO flow" \
  --next "implement secure cookie with SameSite=Strict" \
  --decide "drop Redis session store::latency overhead not justified::keep Redis"
```

Next session, anywhere, any agent:

```
threadline resume --project myapp
```

```
═══════════════════════════════════════════════
  RESUME: myapp
═══════════════════════════════════════════════
  Goal:   make sessions comply with new security requirements
  Status: in-progress

  START HERE → implement secure cookie with SameSite=Strict

  DO NOT repeat:
    • tried httpOnly cookies, broke SSO flow

  Key decision: dropped Redis session store (latency overhead not justified)
═══════════════════════════════════════════════
```

---

## Why threadline

The four memory types AI systems need — working, procedural, semantic, episodic — are well understood. What's missing is a layer designed specifically for **work continuity**: the ability to pause complex multi-session work and resume it without re-deriving everything.

Threadline is that layer. It's:

- **Project-local** — one SQLite DB at `~/.threadline/threadline.db`, no cloud required
- **Agent-agnostic** — CLI works with any agent; MCP server plugs directly into Claude Code
- **Human-readable** — all data is structured Markdown + JSON you can read and edit
- **Decision-preserving** — not just *what* happened, but *why* choices were made and what was rejected

---

## Install

```bash
pip install threadline
# or with uv:
uv add threadline
```

Requires Python 3.11+.

---

## Quick start

**Save a checkpoint:**
```bash
threadline checkpoint \
  --project myproject \
  --task "implementing user auth" \
  --goal "add OAuth2 login" \
  --finding "Google OAuth works, GitHub returns 401 on callback" \
  --dead-end "tried passport.js — incompatible with our session setup" \
  --next "debug GitHub OAuth callback URL mismatch" \
  --next "write integration tests once GitHub flow works"
```

**Resume in a new session:**
```bash
threadline resume --project myproject
```

**Generate a full handoff document:**
```bash
threadline handoff --project myproject
# write to file:
threadline handoff --project myproject --output handoff.md
```

**Check current status:**
```bash
threadline status --project myproject
```

**View history:**
```bash
threadline history --project myproject
threadline history --all-projects
```

**See what changed between two checkpoints:**
```bash
threadline diff <checkpoint-id-a> <checkpoint-id-b>
```

**Export a full project timeline:**
```bash
threadline export --project myproject --output timeline.md
```

---

## CLI reference

| Command | Description |
|---|---|
| `checkpoint` | Save current work state |
| `resume` | Concise briefing to start a new session |
| `handoff` | Full handoff document for agent-to-agent transfer |
| `status` | Current task, next steps, open questions |
| `history` | List recent checkpoints |
| `diff` | Compare two checkpoints |
| `export` | Export project timeline as markdown |
| `projects` | List all tracked projects |
| `search` | Search checkpoints by keyword |

### checkpoint options

| Flag | Short | Description |
|---|---|---|
| `--project` | `-p` | Project name (default: current directory name) |
| `--task` | `-t` | What you're doing right now *(required)* |
| `--goal` | `-g` | Overall goal *(required)* |
| `--status` | `-s` | `in-progress` \| `blocked` \| `complete` \| `abandoned` |
| `--context` | `-c` | Background, constraints, relevant history |
| `--finding` | `-f` | Something learned (repeatable) |
| `--dead-end` | `-d` | Approach tried and ruled out (repeatable) |
| `--next` | `-n` | Next step, ordered (repeatable) |
| `--question` | `-q` | Open question (repeatable) |
| `--file` | | File created or modified (repeatable) |
| `--decide` | | Decision: `what::why` or `what::why::alt1,alt2` (repeatable) |
| `--agent` | | Agent identifier, e.g. `claude-sonnet-4-6` |
| `--tag` | | Tag for filtering (repeatable) |

---

## MCP server

Threadline ships an MCP server so AI agents can checkpoint themselves mid-task — no human required.

**Install with MCP support:**
```bash
pip install 'threadline[mcp]'
```

**Add to Claude Code** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "threadline": {
      "command": "python",
      "args": ["-m", "threadline.mcp_server"]
    }
  }
}
```

**Available MCP tools:**

| Tool | Description |
|---|---|
| `threadline_checkpoint` | Save a checkpoint from within a task |
| `threadline_handoff` | Generate a handoff for the next session |
| `threadline_status` | Get current work state |
| `threadline_history` | List recent checkpoints |
| `threadline_projects` | List all tracked projects |

Once connected, an agent can call `threadline_checkpoint(...)` at any natural pause point — end of a subtask, before a risky operation, when context is getting long — and the next session picks up with full fidelity.

---

## Data model

```
Checkpoint
  id                  uuid
  project             str
  timestamp           datetime
  current_task        str          what you're doing right now
  goal                str          the overall goal
  status              in-progress | blocked | complete | abandoned
  context             str          background and constraints
  findings            list[str]    things learned
  dead_ends           list[str]    approaches ruled out
  decisions           list[Decision]
    .what             str          the choice made
    .why              str          reasoning
    .alternatives_rejected  list[str]
  next_steps          list[str]    ordered — first item = do this now
  open_questions      list[str]
  files_changed       list[str]
  git_ref             str | None   current commit hash
  agent               str | None   agent identifier
  tags                list[str]

Handoff  (generated from Checkpoint)
  executive_summary   str          2-3 sentences: what, where, why
  full_context        str          complete markdown briefing
  immediate_action    str          the single first thing to do
  watch_out_for       list[str]    dead ends not to repeat
```

Storage: SQLite at `~/.threadline/threadline.db`. Override with `THREADLINE_DB` env var.

---

## Philosophy

Three things break AI work continuity:

1. **Context loss** — sessions end, summaries lose nuance
2. **Decision opacity** — later sessions don't know *why* things are the way they are
3. **Dead end repetition** — without explicit records, the same failed approaches get tried again

Threadline addresses all three. A checkpoint is not a log entry — it's a structured handoff from one instance of an agent to the next, with enough decision context to avoid relitigating what's already been resolved.

---

## License

MIT
