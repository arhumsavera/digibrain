"""
CLI interface for ApplyOps — Typer commands for agent and human consumption.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from . import db

app = typer.Typer(help="ApplyOps — local job application tracker", no_args_is_help=True)
company_app = typer.Typer(help="Manage companies", no_args_is_help=True)
job_app = typer.Typer(help="Manage jobs", no_args_is_help=True)
resume_app = typer.Typer(help="Manage resumes", no_args_is_help=True)
app_app = typer.Typer(help="Manage applications", no_args_is_help=True)
email_app = typer.Typer(help="Track email events", no_args_is_help=True)
match_app = typer.Typer(help="Resume-job match analysis", no_args_is_help=True)
log_app = typer.Typer(help="Agent audit log", no_args_is_help=True)

app.add_typer(company_app, name="company")
app.add_typer(job_app, name="job")
app.add_typer(resume_app, name="resume")
app.add_typer(app_app, name="app")
app.add_typer(email_app, name="email")
app.add_typer(match_app, name="match")
app.add_typer(log_app, name="log")


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


# --- Formatters ---

def fmt_company(c: dict) -> str:
    lines = [f"[{c['id']}] {c['name']}"]
    if c.get("url"):
        lines.append(f"  URL: {c['url']}")
    if c.get("description"):
        lines.append(f"  {c['description']}")
    lines.append(f"  Created: {_date(c['created_at'])}")
    return "\n".join(lines)


def fmt_job(j: dict) -> str:
    label = j.get("company_name") or "No company"
    lines = [f"[{j['id']}] {label} — {j['title']}"]
    lines.append(f"  Status: {j['status']} | Source: {j.get('source') or '—'}")
    if j.get("url"):
        lines.append(f"  URL: {j['url']}")
    if j.get("skills"):
        lines.append(f"  Skills: {j['skills']}")
    if j.get("notes"):
        lines.append(f"  Notes: {j['notes']}")
    lines.append(f"  Created: {_date(j['created_at'])}")
    return "\n".join(lines)


def fmt_resume(r: dict) -> str:
    lines = [f"[{r['id']}] {r['name']}"]
    if r.get("tailored_for_job_id"):
        lines.append(f"  Tailored for job: {r['tailored_for_job_id']}")
    preview = (r.get("content") or "")[:100]
    if preview:
        lines.append(f"  Preview: {preview}...")
    lines.append(f"  Created: {_date(r['created_at'])}")
    return "\n".join(lines)


def fmt_app(a: dict) -> str:
    job_label = a.get("job_title") or a["job_id"]
    company = a.get("company_name") or ""
    if company:
        job_label = f"{company} — {job_label}"
    lines = [f"[{a['id']}] {job_label}"]
    lines.append(f"  Status: {a['status']}")
    if a.get("applied_at"):
        lines.append(f"  Applied: {_date(a['applied_at'])}")
    if a.get("notes"):
        lines.append(f"  Notes: {a['notes']}")
    lines.append(f"  Created: {_date(a['created_at'])}")
    return "\n".join(lines)


def fmt_email(e: dict) -> str:
    lines = [f"[{e['id']}] {e.get('sender') or '—'}"]
    lines.append(f"  Subject: {e.get('subject') or '—'}")
    if e.get("body_preview"):
        lines.append(f"  Preview: {e['body_preview'][:80]}...")
    if e.get("job_id"):
        lines.append(f"  Linked job: {e['job_id']}")
    lines.append(f"  Created: {_date(e['created_at'])}")
    return "\n".join(lines)


def fmt_log(l: dict) -> str:
    return (
        f"[{l['id'][:8]}] {_date(l['created_at'])} | "
        f"{l.get('agent') or '—'} | {l.get('action') or '—'} | "
        f"{l.get('entity_type') or '—'}:{l.get('entity_id') or '—'}"
    )


# --- Company ---

@company_app.command("add")
def company_add(
    name: str = typer.Argument(help="Company name"),
    url: Optional[str] = typer.Option(None, help="Company URL"),
    description: Optional[str] = typer.Option(None, help="Description"),
):
    """Add a company."""
    c = db.company_add(name, url=url, description=description)
    print(f"Created company:\n{fmt_company(c)}")


@company_app.command("list")
def company_list(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List all companies."""
    companies = db.company_list()
    if not companies:
        print("No companies found.")
        return
    _out([fmt_company(c) for c in companies] if not as_json else companies, as_json)


@company_app.command("show")
def company_show(
    id: str = typer.Argument(help="Company ID or name"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show a company by ID or name."""
    c = db.company_find(id)
    if not c:
        print(f"Company not found: {id}")
        raise typer.Exit(1)
    _out(c if as_json else fmt_company(c), as_json)


# --- Job ---

@job_app.command("add")
def job_add(
    title: str = typer.Option(..., help="Job title"),
    company: Optional[str] = typer.Option(None, help="Company name (auto-created if new)"),
    url: Optional[str] = typer.Option(None, help="Job URL"),
    source: Optional[str] = typer.Option(None, help="Source: email, manual, web"),
    description: Optional[str] = typer.Option(None, help="Job description"),
):
    """Add a job listing."""
    j = db.job_add(title=title, company=company, url=url, source=source, description=description)
    print(f"Created job:\n{fmt_job(j)}")


@job_app.command("list")
def job_list(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    company: Optional[str] = typer.Option(None, help="Filter by company"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List jobs."""
    jobs = db.job_list(status=status, company=company)
    if not jobs:
        print("No jobs found.")
        return
    _out([fmt_job(j) for j in jobs] if not as_json else jobs, as_json)


@job_app.command("show")
def job_show(
    id: str = typer.Argument(help="Job ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show a job by ID."""
    j = db.job_get(id)
    if not j:
        print(f"Job not found: {id}")
        raise typer.Exit(1)
    if as_json:
        _out(j, True)
    else:
        print(fmt_job(j))
        if j.get("description"):
            print(f"\nDescription:\n{j['description']}")


@job_app.command("update")
def job_update(
    id: str = typer.Argument(help="Job ID"),
    status: Optional[str] = typer.Option(None, help="New status"),
    notes: Optional[str] = typer.Option(None, help="Notes"),
    skills: Optional[str] = typer.Option(None, help="Skills JSON array"),
    url: Optional[str] = typer.Option(None, help="Job URL"),
):
    """Update a job."""
    j = db.job_update(id, status=status, notes=notes, skills=skills, url=url)
    if not j:
        print(f"Job not found: {id}")
        raise typer.Exit(1)
    print(f"Updated job:\n{fmt_job(j)}")


@job_app.command("remove")
def job_remove(id: str = typer.Argument(help="Job ID")):
    """Remove a job."""
    if db.job_remove(id):
        print(f"Removed job {id}")
    else:
        print(f"Job not found: {id}")
        raise typer.Exit(1)


# --- Resume ---

@resume_app.command("add")
def resume_add(
    name: str = typer.Option(..., help="Resume name, e.g. 'base', 'ml-focused'"),
    file: Optional[Path] = typer.Option(None, help="Path to markdown file"),
    content: Optional[str] = typer.Option(None, help="Resume content as string"),
):
    """Add a resume version."""
    text = content
    if file:
        text = file.read_text()
    if not text:
        print("Provide --content or --file")
        raise typer.Exit(1)
    r = db.resume_add(name=name, content=text)
    print(f"Created resume:\n{fmt_resume(r)}")


@resume_app.command("list")
def resume_list(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List all resumes."""
    resumes = db.resume_list()
    if not resumes:
        print("No resumes found.")
        return
    _out([fmt_resume(r) for r in resumes] if not as_json else resumes, as_json)


@resume_app.command("show")
def resume_show(
    id: str = typer.Argument(help="Resume ID or name"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    full: bool = typer.Option(False, "--full", help="Show full content"),
):
    """Show a resume by ID or name."""
    r = db.resume_find(id)
    if not r:
        print(f"Resume not found: {id}")
        raise typer.Exit(1)
    if as_json:
        _out(r, True)
    else:
        print(fmt_resume(r))
        if full:
            print(f"\nContent:\n{r['content']}")


@resume_app.command("render")
def resume_render(
    id: str = typer.Argument(help="Resume ID or name"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output PDF path"),
    template: str = typer.Option("resume", help="Template name (default: resume)"),
):
    """Render a resume to PDF using Typst.

    Resume content must be stored as JSON matching the template schema.
    """
    import shutil
    import subprocess
    import tempfile

    r = db.resume_find(id)
    if not r:
        print(f"Resume not found: {id}")
        raise typer.Exit(1)

    # Validate content is JSON
    try:
        json.loads(r["content"])
    except (json.JSONDecodeError, TypeError):
        print("Resume content must be JSON for rendering. Use 'resume show <id> --full' to check.")
        raise typer.Exit(1)

    templates_dir = Path(__file__).parent / "templates"
    template_file = templates_dir / f"{template}.typ"
    if not template_file.exists():
        print(f"Template not found: {template_file}")
        raise typer.Exit(1)

    # Check typst is installed
    if not shutil.which("typst"):
        print("typst not found. Install with: brew install typst")
        raise typer.Exit(1)

    # Write data to temp dir alongside a copy of the template
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        data_file = tmp / "data.json"
        data_file.write_text(r["content"])
        typ_file = tmp / f"{template}.typ"
        typ_file.write_text(template_file.read_text())

        # Default output: data/output/{name}_{id_short}.pdf
        if output:
            out_path = output
        else:
            output_dir = Path(__file__).parent.parent.parent / "data" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{r['name']}_{r['id'][:8]}.pdf"
        pdf_tmp = tmp / "output.pdf"

        result = subprocess.run(
            ["typst", "compile", str(typ_file), str(pdf_tmp)],
            capture_output=True, text=True,
        )

        if result.returncode != 0:
            print(f"Typst error:\n{result.stderr}")
            raise typer.Exit(1)

        # Copy to final destination
        shutil.copy2(str(pdf_tmp), str(out_path))

    # Store PDF path in DB
    resolved = str(out_path.resolve())
    db.resume_set_pdf(r["id"], resolved)
    print(f"Rendered: {resolved} ({out_path.stat().st_size // 1024}KB)")


@resume_app.command("validate")
def resume_validate(
    id: str = typer.Argument(help="Tailored resume ID or name to validate"),
    base: str = typer.Option("base", help="Base resume ID or name to compare against"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Validate a tailored resume against the base — catch hallucinations.

    Compares entities (companies, titles, skills, dates, metrics) and flags
    anything in the tailored version that doesn't exist in the base.
    Also checks text quality (weak verbs, first person, bullet length).
    """
    from .validate import validate_against_base, format_validation

    tailored = db.resume_find(id)
    if not tailored:
        print(f"Resume not found: {id}")
        raise typer.Exit(1)

    base_resume = db.resume_find(base)
    if not base_resume:
        print(f"Base resume not found: {base}")
        raise typer.Exit(1)

    # Both must be JSON
    for label, r in [("Tailored", tailored), ("Base", base_resume)]:
        try:
            json.loads(r["content"])
        except (json.JSONDecodeError, TypeError):
            print(f"{label} resume content must be JSON. Check: resume show {r['name']} --full")
            raise typer.Exit(1)

    result = validate_against_base(base_resume["content"], tailored["content"])

    if as_json:
        _out(result, True)
    else:
        print(f"Validating [{tailored['name']}] against [{base_resume['name']}]\n")
        print(format_validation(result))


# --- Application ---

@app_app.command("add")
def application_add(
    job: str = typer.Option(..., help="Job ID"),
    resume: Optional[str] = typer.Option(None, help="Resume ID"),
):
    """Create an application for a job."""
    a = db.app_add(job_id=job, resume_id=resume)
    print(f"Created application:\n{fmt_app(a)}")


@app_app.command("list")
def application_list(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List applications."""
    apps = db.app_list(status=status)
    if not apps:
        print("No applications found.")
        return
    _out([fmt_app(a) for a in apps] if not as_json else apps, as_json)


@app_app.command("show")
def application_show(
    id: str = typer.Argument(help="Application ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show an application."""
    a = db.app_get(id)
    if not a:
        print(f"Application not found: {id}")
        raise typer.Exit(1)
    _out(a if as_json else fmt_app(a), as_json)


@app_app.command("update")
def application_update(
    id: str = typer.Argument(help="Application ID"),
    status: Optional[str] = typer.Option(None, help="New status"),
    notes: Optional[str] = typer.Option(None, help="Notes"),
):
    """Update an application."""
    a = db.app_update(id, status=status, notes=notes)
    if not a:
        print(f"Application not found: {id}")
        raise typer.Exit(1)
    print(f"Updated application:\n{fmt_app(a)}")


@app_app.command("remove")
def application_remove(id: str = typer.Argument(help="Application ID")):
    """Remove an application."""
    if db.app_remove(id):
        print(f"Removed application {id}")
    else:
        print(f"Application not found: {id}")
        raise typer.Exit(1)


# --- Email ---

@email_app.command("add")
def email_add(
    sender: Optional[str] = typer.Option(None, help="Sender address"),
    subject: Optional[str] = typer.Option(None, help="Email subject"),
    body: Optional[str] = typer.Option(None, help="Email body text"),
    job: Optional[str] = typer.Option(None, help="Linked job ID"),
):
    """Add an email entry."""
    e = db.email_add(sender=sender, subject=subject, body=body, job_id=job)
    print(f"Created email entry:\n{fmt_email(e)}")


@email_app.command("list")
def email_list(
    limit: int = typer.Option(20, help="Max entries"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List tracked emails."""
    emails = db.email_list(limit=limit)
    if not emails:
        print("No email entries found.")
        return
    _out([fmt_email(e) for e in emails] if not as_json else emails, as_json)


# --- Match ---

def fmt_match(m: dict) -> str:
    job_label = m.get("company_name") or ""
    if job_label:
        job_label = f"{job_label} — "
    job_label += m.get("job_title") or m["job_id"]
    score = f"{m['score']}%" if m.get("score") is not None else "—"
    lines = [f"[{m['id']}] {job_label} (resume: {m.get('resume_name') or m['resume_id']})"]
    lines.append(f"  Score: {score}")
    if m.get("strong_matches"):
        lines.append(f"  Strong: {m['strong_matches']}")
    if m.get("gaps"):
        lines.append(f"  Gaps: {m['gaps']}")
    if m.get("red_flags"):
        lines.append(f"  Red flags: {m['red_flags']}")
    if m.get("notes"):
        lines.append(f"  Notes: {m['notes']}")
    lines.append(f"  Created: {_date(m['created_at'])}")
    return "\n".join(lines)


@match_app.command("add")
def match_add(
    job: str = typer.Option(..., help="Job ID"),
    resume: str = typer.Option(..., help="Resume ID or name"),
    score: Optional[int] = typer.Option(None, help="Match score 0-100"),
    strong_matches: Optional[str] = typer.Option(None, "--strong", help="JSON array of strong matches"),
    gaps: Optional[str] = typer.Option(None, help="JSON array of gaps"),
    red_flags: Optional[str] = typer.Option(None, "--red-flags", help="JSON array of red flags"),
    notes: Optional[str] = typer.Option(None, help="Analysis notes"),
):
    """Save a match analysis result."""
    # Resolve resume by name if needed
    r = db.resume_find(resume)
    resume_id = r["id"] if r else resume
    m = db.match_add(
        job_id=job, resume_id=resume_id, score=score,
        strong_matches=strong_matches, gaps=gaps,
        red_flags=red_flags, notes=notes,
    )
    print(f"Created match:\n{fmt_match(m)}")


@match_app.command("list")
def match_list(
    job: Optional[str] = typer.Option(None, help="Filter by job ID"),
    min_score: Optional[int] = typer.Option(None, "--min-score", help="Minimum match score"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """List match analyses."""
    matches = db.match_list(job_id=job, min_score=min_score)
    if not matches:
        print("No match analyses found.")
        return
    _out([fmt_match(m) for m in matches] if not as_json else matches, as_json)


@match_app.command("show")
def match_show(
    id: str = typer.Argument(help="Match ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show a match analysis."""
    m = db.match_get(id)
    if not m:
        print(f"Match not found: {id}")
        raise typer.Exit(1)
    _out(m if as_json else fmt_match(m), as_json)


# --- Stats ---

@app.command("stats")
def stats(
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Dashboard stats."""
    s = db.get_stats()
    if as_json:
        _out(s, True)
        return
    print("=== ApplyOps Dashboard ===\n")
    print(f"Companies:    {s['companies']}")
    print(f"Jobs:         {s['jobs']}")
    print(f"Resumes:      {s['resumes']}")
    print(f"Applications: {s['applications']}")
    print(f"Emails:       {s['emails']}")
    print(f"Matches:      {s['matches']}")
    if s["jobs_by_status"]:
        print("\nJobs by status:")
        for st, c in s["jobs_by_status"].items():
            print(f"  {st}: {c}")
    if s["apps_by_status"]:
        print("\nApplications by status:")
        for st, c in s["apps_by_status"].items():
            print(f"  {st}: {c}")


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
    host: str = typer.Option("127.0.0.1", help="Host"),
):
    """Start the web dashboard."""
    from .web import run_server
    run_server(host=host, port=port)
