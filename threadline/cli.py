"""threadline CLI — checkpoint, handoff, history, status."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import box

from .models import Checkpoint, Decision
from .store import Store
from .handoff import generate_handoff

console = Console()


def _store() -> Store:
    db = os.environ.get("THREADLINE_DB")
    return Store(db_path=db if db else None)


def _current_project() -> str:
    """Use the current directory name as the default project."""
    return os.environ.get("THREADLINE_PROJECT", Path.cwd().name)


def _git_ref() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """threadline — work continuity engine for AI agents."""


# ---------------------------------------------------------------------------
# checkpoint
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None, help="Project name (default: cwd name)")
@click.option("--task", "-t", required=True, help="What are you doing right now?")
@click.option("--goal", "-g", required=True, help="What is the overall goal?")
@click.option("--status", "-s",
              type=click.Choice(["in-progress", "blocked", "complete", "abandoned"]),
              default="in-progress")
@click.option("--context", "-c", default="", help="Background / constraints")
@click.option("--finding", "-f", multiple=True, help="Something learned (repeatable)")
@click.option("--dead-end", "-d", multiple=True, help="Dead end to avoid (repeatable)")
@click.option("--next", "-n", multiple=True, help="Next step (repeatable, ordered)")
@click.option("--question", "-q", multiple=True, help="Open question (repeatable)")
@click.option("--file", multiple=True, help="File changed (repeatable)")
@click.option("--agent", default=None, help="Agent identifier (e.g. claude-sonnet-4-6)")
@click.option("--tag", multiple=True, help="Tag for filtering")
@click.option("--decide", multiple=True,
              help="Decision in format 'what::why' or 'what::why::alt1,alt2'")
def checkpoint(project, task, goal, status, context, finding, dead_end,
               next, question, file, agent, tag, decide):
    """Save a checkpoint of current work state."""
    store = _store()
    proj = project or _current_project()

    decisions = []
    for d in decide:
        parts = d.split("::", 2)
        what = parts[0].strip()
        why = parts[1].strip() if len(parts) > 1 else ""
        alts = [a.strip() for a in parts[2].split(",")] if len(parts) > 2 else []
        decisions.append(Decision(what=what, why=why, alternatives_rejected=alts))

    cp = Checkpoint(
        project=proj,
        current_task=task,
        goal=goal,
        status=status,
        context=context,
        findings=list(finding),
        dead_ends=list(dead_end),
        decisions=decisions,
        next_steps=list(next),
        open_questions=list(question),
        files_changed=list(file),
        git_ref=_git_ref(),
        agent=agent,
        tags=list(tag),
    )
    store.save_checkpoint(cp)
    console.print(Panel(
        f"[bold green]Checkpoint saved[/]\n"
        f"[dim]id:[/] {cp.id}\n"
        f"[dim]project:[/] {cp.project}\n"
        f"[dim]task:[/] {cp.current_task}\n"
        f"[dim]status:[/] {cp.status}",
        title="threadline", border_style="green"
    ))


# ---------------------------------------------------------------------------
# handoff
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None)
@click.option("--checkpoint-id", "-c", default=None, help="Checkpoint ID (default: latest)")
@click.option("--for-agent", default=None, help="Target agent identifier")
@click.option("--save", is_flag=True, help="Save handoff to store")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write to file")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON instead of markdown")
def handoff(project, checkpoint_id, for_agent, save, output, as_json):
    """Generate a handoff document from the latest (or specified) checkpoint."""
    store = _store()
    proj = project or _current_project()

    if checkpoint_id:
        cp = store.get_checkpoint(checkpoint_id)
        if not cp:
            console.print(f"[red]Checkpoint not found: {checkpoint_id}[/]")
            sys.exit(1)
    else:
        cp = store.latest_checkpoint(proj)
        if not cp:
            console.print(f"[red]No checkpoints found for project '{proj}'[/]")
            sys.exit(1)

    h = generate_handoff(cp, target_agent=for_agent)

    if save:
        store.save_handoff(h)

    if as_json:
        text = h.model_dump_json(indent=2)
    else:
        text = h.full_context

    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"[green]Handoff written to {output}[/]")
    else:
        if as_json:
            console.print_json(text)
        else:
            console.print(Markdown(text))


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None)
def status(project):
    """Show current work state for a project."""
    store = _store()
    proj = project or _current_project()
    cp = store.latest_checkpoint(proj)
    if not cp:
        console.print(f"[yellow]No checkpoints for '{proj}'[/]")
        return

    status_color = {
        "in-progress": "yellow",
        "blocked": "red",
        "complete": "green",
        "abandoned": "dim",
    }.get(cp.status, "white")

    console.print(Panel(
        f"[bold]{cp.current_task}[/]\n"
        f"[dim]goal:[/] {cp.goal}\n"
        f"[dim]status:[/] [{status_color}]{cp.status}[/]\n"
        f"[dim]as of:[/] {cp.timestamp.strftime('%Y-%m-%d %H:%M')} UTC\n"
        + (f"[dim]git:[/] {cp.git_ref}\n" if cp.git_ref else "")
        + (f"[dim]agent:[/] {cp.agent}\n" if cp.agent else ""),
        title=f"[bold]threadline — {proj}[/]",
        border_style=status_color,
    ))

    if cp.next_steps:
        console.print("[dim]Next steps:[/]")
        for i, s in enumerate(cp.next_steps, 1):
            prefix = "→" if i == 1 else " "
            console.print(f"  {prefix} {s}")

    if cp.open_questions:
        console.print("\n[dim]Open questions:[/]")
        for q in cp.open_questions:
            console.print(f"  ? {q}")


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None)
@click.option("--limit", "-l", default=10, show_default=True)
@click.option("--all-projects", is_flag=True)
def history(project, limit, all_projects):
    """List recent checkpoints."""
    store = _store()

    if all_projects:
        checkpoints = store.list_checkpoints(project=None, limit=limit)
    else:
        proj = project or _current_project()
        checkpoints = store.list_checkpoints(project=proj, limit=limit)

    if not checkpoints:
        console.print("[yellow]No checkpoints found.[/]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    table.add_column("Time", style="dim", width=16)
    table.add_column("Project", style="cyan", width=18)
    table.add_column("Task")
    table.add_column("Status", width=12)
    table.add_column("ID", style="dim", width=10)

    status_colors = {
        "in-progress": "yellow",
        "blocked": "red",
        "complete": "green",
        "abandoned": "dim",
    }

    for cp in checkpoints:
        color = status_colors.get(cp.status, "white")
        table.add_row(
            cp.timestamp.strftime("%m-%d %H:%M"),
            cp.project,
            cp.current_task[:50] + ("…" if len(cp.current_task) > 50 else ""),
            f"[{color}]{cp.status}[/]",
            cp.id[:8],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------

@cli.command()
def projects():
    """List all projects with checkpoints."""
    store = _store()
    projs = store.list_projects()
    if not projs:
        console.print("[yellow]No projects found.[/]")
        return
    for p in projs:
        cp = store.latest_checkpoint(p)
        suffix = f" — {cp.current_task[:50]}" if cp else ""
        console.print(f"  [cyan]{p}[/]{suffix}")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--project", "-p", default=None)
def search(query, project):
    """Search checkpoints by keyword."""
    store = _store()
    proj = project or _current_project()
    results = store.search_checkpoints(proj, query)
    if not results:
        console.print(f"[yellow]No results for '{query}' in '{proj}'[/]")
        return
    console.print(f"[dim]{len(results)} result(s) for '{query}':[/]\n")
    for cp in results:
        console.print(
            f"  [dim]{cp.timestamp.strftime('%m-%d %H:%M')}[/] "
            f"[cyan]{cp.id[:8]}[/] {cp.current_task[:60]}"
        )


# ---------------------------------------------------------------------------
# resume  (the key command — run at the start of a new session)
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None)
@click.option("--checkpoint-id", "-c", default=None)
def resume(project, checkpoint_id):
    """Print a concise briefing to resume work in a new session.

    This is the command to run at the start of every session.
    It shows exactly where you left off and what to do first.
    """
    store = _store()
    proj = project or _current_project()

    if checkpoint_id:
        cp = store.get_checkpoint(checkpoint_id)
        if not cp:
            console.print(f"[red]Checkpoint not found: {checkpoint_id}[/]")
            sys.exit(1)
    else:
        cp = store.latest_checkpoint(proj)
        if not cp:
            console.print(f"[yellow]No checkpoints for '{proj}'. Start with: threadline checkpoint ...[/]")
            return

    status_color = {
        "in-progress": "yellow",
        "blocked": "red",
        "complete": "green",
        "abandoned": "dim",
    }.get(cp.status, "white")

    lines = []
    lines.append(f"[bold]Goal[/]   {cp.goal}")
    lines.append(f"[bold]Status[/] [{status_color}]{cp.status}[/]  •  {cp.timestamp.strftime('%Y-%m-%d %H:%M')} UTC")
    if cp.agent:
        lines.append(f"[bold]Agent[/]  {cp.agent}")
    lines.append("")

    if cp.next_steps:
        lines.append(f"[bold green]START HERE →[/] {cp.next_steps[0]}")
        if len(cp.next_steps) > 1:
            lines.append("")
            lines.append("[dim]Then:[/]")
            for step in cp.next_steps[1:]:
                lines.append(f"  • {step}")
    else:
        lines.append(f"[bold green]START HERE →[/] Resume: {cp.current_task}")

    if cp.dead_ends:
        lines.append("")
        lines.append("[bold red]DO NOT repeat:[/]")
        for de in cp.dead_ends:
            lines.append(f"  • {de}")

    if cp.decisions:
        lines.append("")
        lines.append("[dim]Key decisions already made:[/]")
        for d in cp.decisions:
            lines.append(f"  • {d.what} — {d.why}")

    if cp.open_questions:
        lines.append("")
        lines.append("[dim]Open questions:[/]")
        for q in cp.open_questions:
            lines.append(f"  ? {q}")

    if cp.git_ref:
        lines.append("")
        lines.append(f"[dim]git ref:[/] {cp.git_ref}")

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]RESUME: {proj}[/]",
        border_style=status_color,
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# diff — compare two checkpoints
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("id_a")
@click.argument("id_b")
def diff(id_a, id_b):
    """Compare two checkpoints — see how understanding evolved."""
    store = _store()

    cp_a = store.get_checkpoint(id_a) or store.get_checkpoint(
        next((c.id for c in store.list_checkpoints(limit=50) if c.id.startswith(id_a)), "")
    )
    cp_b = store.get_checkpoint(id_b) or store.get_checkpoint(
        next((c.id for c in store.list_checkpoints(limit=50) if c.id.startswith(id_b)), "")
    )

    if not cp_a:
        console.print(f"[red]Checkpoint not found: {id_a}[/]")
        sys.exit(1)
    if not cp_b:
        console.print(f"[red]Checkpoint not found: {id_b}[/]")
        sys.exit(1)

    # Ensure A is older
    if cp_a.timestamp > cp_b.timestamp:
        cp_a, cp_b = cp_b, cp_a

    console.print(f"\n[dim]A:[/] {cp_a.id[:8]}  {cp_a.timestamp.strftime('%m-%d %H:%M')}  {cp_a.current_task[:50]}")
    console.print(f"[dim]B:[/] {cp_b.id[:8]}  {cp_b.timestamp.strftime('%m-%d %H:%M')}  {cp_b.current_task[:50]}\n")

    def _set_diff(label, old: list, new: list) -> None:
        added = [x for x in new if x not in old]
        removed = [x for x in old if x not in new]
        if added or removed:
            console.print(f"[bold]{label}[/]")
            for x in added:
                console.print(f"  [green]+ {x}[/]")
            for x in removed:
                console.print(f"  [red]- {x}[/]")
            console.print()

    if cp_a.current_task != cp_b.current_task:
        console.print(f"[bold]Task[/]")
        console.print(f"  [red]- {cp_a.current_task}[/]")
        console.print(f"  [green]+ {cp_b.current_task}[/]\n")

    if cp_a.status != cp_b.status:
        console.print(f"[bold]Status[/]  {cp_a.status} → {cp_b.status}\n")

    _set_diff("Findings", cp_a.findings, cp_b.findings)
    _set_diff("Dead ends", cp_a.dead_ends, cp_b.dead_ends)
    _set_diff("Next steps", cp_a.next_steps, cp_b.next_steps)
    _set_diff("Open questions", cp_a.open_questions, cp_b.open_questions)
    _set_diff("Files", cp_a.files_changed, cp_b.files_changed)

    new_decisions = [d for d in cp_b.decisions if d.what not in {x.what for x in cp_a.decisions}]
    if new_decisions:
        console.print("[bold]New decisions[/]")
        for d in new_decisions:
            console.print(f"  [green]+ {d.what}[/] — {d.why}")
        console.print()


# ---------------------------------------------------------------------------
# export — full project timeline as markdown
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--project", "-p", default=None)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write to file (default: stdout)")
@click.option("--limit", "-l", default=50, show_default=True)
def export(project, output, limit):
    """Export full project checkpoint history as a markdown document."""
    store = _store()
    proj = project or _current_project()
    checkpoints = store.list_checkpoints(project=proj, limit=limit)

    if not checkpoints:
        console.print(f"[yellow]No checkpoints for '{proj}'[/]")
        return

    # Oldest first for timeline
    checkpoints = list(reversed(checkpoints))

    lines = [f"# {proj} — Work Timeline", ""]
    lines.append(f"*{len(checkpoints)} checkpoint(s) exported*\n")

    for i, cp in enumerate(checkpoints, 1):
        lines.append(f"---\n")
        lines.append(f"## {i}. {cp.current_task}")
        lines.append(f"*{cp.timestamp.strftime('%Y-%m-%d %H:%M')} UTC · {cp.status}*")
        if cp.agent:
            lines.append(f"*agent: {cp.agent}*")
        lines.append("")

        if cp.goal:
            lines.append(f"**Goal:** {cp.goal}\n")

        if cp.findings:
            lines.append("**Findings:**")
            for f in cp.findings:
                lines.append(f"- {f}")
            lines.append("")

        if cp.decisions:
            lines.append("**Decisions:**")
            for d in cp.decisions:
                alts = f" *(rejected: {', '.join(d.alternatives_rejected)})*" if d.alternatives_rejected else ""
                lines.append(f"- **{d.what}** — {d.why}{alts}")
            lines.append("")

        if cp.dead_ends:
            lines.append("**Dead ends:**")
            for de in cp.dead_ends:
                lines.append(f"- {de}")
            lines.append("")

        if cp.next_steps:
            lines.append("**Next steps:**")
            for s in cp.next_steps:
                lines.append(f"- {s}")
            lines.append("")

    text = "\n".join(lines)

    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"[green]Timeline written to {output}[/]")
    else:
        console.print(Markdown(text))
