"""
CLI interface for ApplyOps — Typer commands for agent and human consumption.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from . import db

app = typer.Typer(help="ApplyOps — agent data store and memory CLI", no_args_is_help=True)
log_app    = typer.Typer(help="Agent audit log", no_args_is_help=True)
flows_app  = typer.Typer(help="Manage Prefect scheduled flows", no_args_is_help=True)
domain_app = typer.Typer(help="Manage domains", no_args_is_help=True)
item_app   = typer.Typer(help="Generic item store", no_args_is_help=True)

app.add_typer(log_app,    name="log")
app.add_typer(flows_app,  name="flows")
app.add_typer(domain_app, name="domain")
app.add_typer(item_app,   name="item")

# Optional private extension: job/resume/application tracking
try:
    from .jobs_cli import register as _register_jobs
    _register_jobs(app)
except ImportError:
    pass


def _out(data, as_json: bool = False):
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                print(item)
                print()
        else:
            print(data)


def _date(dt_str: str | None) -> str:
    return dt_str[:10] if dt_str else "—"


def fmt_log(l: dict) -> str:
    return (
        f"[{l['id'][:8]}] {_date(l['created_at'])} | "
        f"{l.get('agent') or '—'} | {l.get('action') or '—'} | "
        f"{l.get('entity_type') or '—'}:{l.get('entity_id') or '—'}"
    )


# --- Log ---

@log_app.command("add")
def log_add(
    agent: str = typer.Option(..., help="Agent name"),
    action: str = typer.Option(..., help="What was done"),
    entity_type: str = typer.Option(..., help="Entity type"),
    entity_id: str = typer.Option(..., help="Entity ID"),
    details: Optional[str] = typer.Option(None, help="JSON details"),
):
    """Add an audit log entry."""
    l = db.log_add(agent=agent, action=action, entity_type=entity_type,
                    entity_id=entity_id, details=details)
    print(f"Logged: {fmt_log(l)}")


@log_app.command("list")
def log_list(
    limit: int = typer.Option(20, help="Max entries"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List audit log entries."""
    logs = db.log_list(limit=limit)
    if not logs:
        print("No task runs logged.")
        return
    _out([fmt_log(l) for l in logs] if not as_json else logs, as_json)


# --- Serve ---

@app.command("serve")
def serve(
    port: int = typer.Option(8000, help="Port"),
    host: str = typer.Option("0.0.0.0", help="Host"),
):
    """Start the web dashboard."""
    from .web import run_server
    run_server(host=host, port=port)


# --- Domain ---

def fmt_domain(d: dict) -> str:
    icon = d.get("icon") or ""
    lines = [f"[{d['id']}] {icon} {d['name']}".strip()]
    if d.get("description"):
        lines.append(f"  {d['description']}")
    if d.get("keywords"):
        try:
            kws = json.loads(d["keywords"])
            lines.append(f"  Keywords: {', '.join(kws)}")
        except (json.JSONDecodeError, TypeError):
            pass
    lines.append(f"  Created: {_date(d['created_at'])}")
    return "\n".join(lines)


@domain_app.command("add")
def domain_add(
    name: str = typer.Argument(help="Domain name (e.g. fitness, todos, reading)"),
    description: Optional[str] = typer.Option(None, help="Description"),
    keywords: Optional[str] = typer.Option(None, help="JSON array of trigger keywords"),
    instructions: Optional[str] = typer.Option(None, help="Agent instructions (markdown)"),
    schema: Optional[str] = typer.Option(None, help="JSON Schema for item data validation"),
    icon: Optional[str] = typer.Option(None, help="Emoji icon"),
):
    """Create a new domain."""
    d = db.domain_add(
        name=name, description=description, keywords=keywords,
        instructions=instructions, schema=schema, icon=icon,
    )
    print(f"Created domain:\n{fmt_domain(d)}")


@domain_app.command("list")
def domain_list(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List all domains."""
    domains = db.domain_list()
    if not domains:
        print("No domains found.")
        return
    _out([fmt_domain(d) for d in domains] if not as_json else domains, as_json)


@domain_app.command("show")
def domain_show(
    id: str = typer.Argument(help="Domain ID or name"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show a domain and its instructions."""
    d = db.domain_find(id)
    if not d:
        print(f"Domain not found: {id}")
        raise typer.Exit(1)
    if as_json:
        _out(d, True)
    else:
        print(fmt_domain(d))
        if d.get("instructions"):
            print(f"\nInstructions:\n{d['instructions']}")


@domain_app.command("update")
def domain_update(
    id: str = typer.Argument(help="Domain ID or name"),
    description: Optional[str] = typer.Option(None, help="Description"),
    keywords: Optional[str] = typer.Option(None, help="JSON array of trigger keywords"),
    instructions: Optional[str] = typer.Option(None, help="Agent instructions"),
    schema: Optional[str] = typer.Option(None, help="JSON Schema for item data"),
    icon: Optional[str] = typer.Option(None, help="Emoji icon"),
):
    """Update a domain."""
    d = db.domain_update(
        id, description=description, keywords=keywords,
        instructions=instructions, schema=schema, icon=icon,
    )
    if not d:
        print(f"Domain not found: {id}")
        raise typer.Exit(1)
    print(f"Updated domain:\n{fmt_domain(d)}")


@domain_app.command("remove")
def domain_remove(id: str = typer.Argument(help="Domain ID or name")):
    """Remove a domain and all its items."""
    if db.domain_remove(id):
        print(f"Removed domain {id} and all its items")
    else:
        print(f"Domain not found: {id}")
        raise typer.Exit(1)


@domain_app.command("detect")
def domain_detect(
    message: str = typer.Argument(help="Message to detect domain from"),
):
    """Detect which domain a message belongs to."""
    results = db.detect_domain(message)
    if not results:
        print("No domain matched.")
        print("\nCreate one with: uv run applyops domain add <name> --keywords '[...]'")
        return
    for d in results:
        matched = ", ".join(d.get("_matched", []))
        print(f"  {d['name']} (score: {d['_score']}, matched: {matched})")


# --- Item ---

def fmt_item(i: dict) -> str:
    domain = i.get("domain_name") or "?"
    lines = [f"[{i['id']}] {domain}/{i['type']}: {i['title']}"]
    lines.append(f"  Status: {i['status']}")
    if i.get("priority") is not None:
        lines.append(f"  Priority: {i['priority']}")
    if i.get("due_at"):
        lines.append(f"  Due: {i['due_at']}")
    if i.get("tags"):
        try:
            tags = json.loads(i["tags"])
            lines.append(f"  Tags: {', '.join(tags)}")
        except (json.JSONDecodeError, TypeError):
            pass
    if i.get("data"):
        preview = i["data"][:120]
        if len(i["data"]) > 120:
            preview += "..."
        lines.append(f"  Data: {preview}")
    lines.append(f"  Created: {_date(i['created_at'])}")
    return "\n".join(lines)


@item_app.command("add")
def item_add(
    domain: str = typer.Option(..., help="Domain name or ID"),
    title: str = typer.Option(..., help="Item title"),
    type: str = typer.Option("note", help="Item type (e.g. workout, todo, book)"),
    data: Optional[str] = typer.Option(None, help="JSON data blob"),
    tags: Optional[str] = typer.Option(None, help="JSON array of tags"),
    status: str = typer.Option("active", help="Status: active, done, archived"),
    due: Optional[str] = typer.Option(None, help="Due date (YYYY-MM-DD)"),
    priority: Optional[int] = typer.Option(None, help="Priority (1=highest)"),
):
    """Add an item to a domain."""
    try:
        i = db.item_add(
            domain=domain, title=title, type=type, data=data,
            tags=tags, status=status, priority=priority, due_at=due,
        )
        print(f"Created item:\n{fmt_item(i)}")
    except ValueError as e:
        print(str(e))
        raise typer.Exit(1)


@item_app.command("list")
def item_list(
    domain: Optional[str] = typer.Option(None, help="Domain name or ID"),
    type: Optional[str] = typer.Option(None, help="Filter by type"),
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    sort: str = typer.Option("created", help="Sort: created, updated, due, priority"),
    limit: int = typer.Option(50, help="Max items"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List items, optionally filtered by domain/type/status."""
    items = db.item_list(domain=domain, type=type, status=status, sort=sort, limit=limit)
    if not items:
        print("No items found.")
        return
    _out([fmt_item(i) for i in items] if not as_json else items, as_json)


@item_app.command("show")
def item_show(
    id: str = typer.Argument(help="Item ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show an item."""
    i = db.item_get(id)
    if not i:
        print(f"Item not found: {id}")
        raise typer.Exit(1)
    if as_json:
        _out(i, True)
    else:
        print(fmt_item(i))
        if i.get("data"):
            print(f"\nData:\n{i['data']}")


@item_app.command("update")
def item_update(
    id: str = typer.Argument(help="Item ID"),
    title: Optional[str] = typer.Option(None, help="New title"),
    type: Optional[str] = typer.Option(None, help="New type"),
    status: Optional[str] = typer.Option(None, help="New status"),
    data: Optional[str] = typer.Option(None, help="New JSON data"),
    tags: Optional[str] = typer.Option(None, help="New JSON tags"),
    due: Optional[str] = typer.Option(None, help="New due date"),
    priority: Optional[int] = typer.Option(None, help="New priority"),
):
    """Update an item."""
    i = db.item_update(id, title=title, type=type, status=status,
                       data=data, tags=tags, due_at=due, priority=priority)
    if not i:
        print(f"Item not found: {id}")
        raise typer.Exit(1)
    print(f"Updated item:\n{fmt_item(i)}")


@item_app.command("remove")
def item_remove(id: str = typer.Argument(help="Item ID")):
    """Remove an item."""
    if db.item_remove(id):
        print(f"Removed item {id}")
    else:
        print(f"Item not found: {id}")
        raise typer.Exit(1)


@item_app.command("search")
def item_search(
    query: str = typer.Argument(help="Search query"),
    domain: Optional[str] = typer.Option(None, help="Scope to domain"),
    limit: int = typer.Option(20, help="Max results"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Full-text search across items."""
    items = db.item_search(query=query, domain=domain, limit=limit)
    if not items:
        print("No matches found.")
        return
    _out([fmt_item(i) for i in items] if not as_json else items, as_json)


@item_app.command("stats")
def item_stats(
    domain: str = typer.Argument(help="Domain name or ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show item stats for a domain."""
    try:
        s = db.item_stats(domain)
    except ValueError as e:
        print(str(e))
        raise typer.Exit(1)
    if as_json:
        _out(s, True)
        return
    print(f"=== {s['domain']} ===\n")
    print(f"Total items: {s['total']}")
    if s["by_type"]:
        print("\nBy type:")
        for t, c in s["by_type"].items():
            print(f"  {t}: {c}")
    if s["by_status"]:
        print("\nBy status:")
        for st, c in s["by_status"].items():
            print(f"  {st}: {c}")


# --- Flows ---

@flows_app.command("deploy")
def flows_deploy():
    """Deploy all flows defined in prefect.yaml."""
    import subprocess
    result = subprocess.run(["prefect", "deploy", "--all"], check=False)
    raise typer.Exit(result.returncode)


@flows_app.command("run")
def flows_run(
    name: str = typer.Argument(help="Deployment name (e.g. daily-email-summary)"),
    param: Optional[list[str]] = typer.Option(
        None, "--param", "-p",
        help="Flow parameters as key=value pairs (e.g. --param prompt='hello')",
    ),
):
    """Trigger an immediate flow run by deployment name."""
    import subprocess
    cmd = ["prefect", "deployment", "run", name]
    for p in (param or []):
        cmd.extend(["--param", p])
    result = subprocess.run(cmd, check=False)
    raise typer.Exit(result.returncode)


@flows_app.command("ui")
def flows_ui():
    """Open the Prefect UI in the default browser (http://localhost:4200)."""
    import webbrowser
    url = "http://localhost:4200"
    print(f"Opening Prefect UI at {url}")
    print("Make sure the server is running: prefect server start")
    webbrowser.open(url)
