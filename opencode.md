# Agent Memory Framework

This repo is a shared memory system used by both Claude Code and opencode.
Follow the memory protocol below on every task.

## Memory Protocol

### Before every task:
1. Read all files in `memory/semantic/` (skip `_template.md`)
2. Read today's `memory/episodic/YYYY-MM-DD.md` if it exists
3. Check `memory/procedural/` for workflows relevant to the current task

### After every task:
1. **Episodic**: Append an entry to `memory/episodic/YYYY-MM-DD.md` (create if needed)
   - Use the format from `memory/episodic/_template.md`
   - Set Agent to `opencode`
   - Include timestamp, task summary, outcome, and any followups
   - Never edit past entries — append only

2. **Procedural**: If the user corrected you or gave feedback on how to do something:
   - Update or create an entry in `memory/procedural/`
   - Use the format from `memory/procedural/_template.md`

3. **Semantic**: If new persistent facts were learned (preferences, project info, etc.):
   - Update or create an entry in `memory/semantic/`
   - Use the format from `memory/semantic/_template.md`
   - Merge into existing files when relevant — don't create duplicates

### Forgetting:
When the user asks to forget, clear, or delete memories:
1. Use `python scripts/forget.py list` or `list --search "keyword"` to find relevant entries
2. Show the user what was found and confirm what to delete
3. Run `python scripts/forget.py forget` with the appropriate flags (dry run first)
4. Only add `--apply` after user confirms the dry run output

Common commands:
- `python scripts/forget.py list` — show all memories
- `python scripts/forget.py list --search "keyword"` — search across all types
- `python scripts/forget.py forget --search "keyword"` — remove matching entries (dry run)
- `python scripts/forget.py forget --file name.md` — remove a specific file (dry run)
- `python scripts/forget.py forget --type episodic --before YYYY-MM-DD` — remove old logs (dry run)
- Add `--apply` to any forget command to execute

### Consolidation:
To consolidate old episodic memories into semantic summaries:
- `python scripts/consolidate.py` — dry run
- `python scripts/consolidate.py --apply` — archive old episodes, save summary
- `python scripts/consolidate.py --days 14` — change age threshold

### Rules:
- Never delete procedural memories without user confirmation
- Episodic entries are append-only
- Semantic entries can be updated (merge new info, don't duplicate)
- Keep entries concise — this is context for future tasks, not a transcript
- When in doubt about whether to save something, save it to episodic

## ApplyOps (Job Application Tracker)

Local CLI tool backed by SQLite. Use `uv run applyops` to interact with it.
When the user asks about jobs, applications, resumes, or recruiting emails, use these commands.

### Companies
```bash
uv run applyops company add "Meta" --url "..." --description "..."
uv run applyops company list [--json]
uv run applyops company show <id-or-name> [--json]
```

### Jobs
```bash
uv run applyops job add --title "SWE" --company "Meta" [--url "..." --source email --description "..."]
uv run applyops job list [--status discovered|approved|rejected] [--company "Meta"] [--json]
uv run applyops job show <id> [--json]
uv run applyops job update <id> --status approved [--notes "..." --skills '["python","ml"]']
uv run applyops job remove <id>
```

### Resumes
```bash
uv run applyops resume add --name "base" --file resume.md
uv run applyops resume add --name "base" --content "markdown text..."
uv run applyops resume list [--json]
uv run applyops resume show <id-or-name> [--json] [--full]
```

### Applications
```bash
uv run applyops app add --job <job_id> [--resume <resume_id>]
uv run applyops app list [--status draft|applied|interviewing|offered|rejected] [--json]
uv run applyops app show <id> [--json]
uv run applyops app update <id> --status applied [--notes "..."]
uv run applyops app remove <id>
```

### Emails
```bash
uv run applyops email add --sender "..." --subject "..." [--body "..." --job <job_id>]
uv run applyops email list [--limit 10] [--json]
```

### Stats & Logs
```bash
uv run applyops stats [--json]
uv run applyops log add --agent opencode --action "analyzed job" --entity-type job --entity-id <id>
uv run applyops log list [--limit 20] [--json]
```

### Workflow examples
- **"Check this job link"**: Fetch the URL, extract info, then `job add` with details
- **"Parse this recruiter email"**: Read the email, then `email add` + `job add` with extracted info
- **"How's my pipeline?"**: `stats` or `app list`
- **"Approve a job"**: `job update <id> --status approved`

## Tools

### Email (`python tools/gmail.py`)
Fetches Gmail via IMAP. Use this when the user asks to check email.

```bash
python tools/gmail.py inbox                        # latest 10 emails
python tools/gmail.py inbox --limit 5              # latest 5
python tools/gmail.py inbox --unread               # unread only
python tools/gmail.py inbox --since 3d             # last 3 days
python tools/gmail.py inbox --since 1w             # last week
python tools/gmail.py inbox --from "linkedin"      # from address contains
python tools/gmail.py inbox --subject "invitation" # subject contains
python tools/gmail.py inbox --label "Jobs"         # specific Gmail label
python tools/gmail.py read <message_id>            # read full email
python tools/gmail.py search "job opportunity"     # full-text search
```

Filters can be combined: `inbox --unread --since 1d --from "recruiter"`

**Email → ApplyOps workflow:**
1. `python tools/gmail.py inbox --unread` → scan for job-related emails
2. `python tools/gmail.py read <id>` → get full email text
3. If it's a job/recruiter email: `uv run applyops email add` + `uv run applyops job add`
4. Show user the result, confirm, then `uv run applyops job update <id> --status approved`

## Project Structure
```
memory/
├── semantic/    # persistent facts, preferences, knowledge
├── episodic/    # daily interaction logs (YYYY-MM-DD.md)
└── procedural/  # learned workflows and rules
scripts/
├── consolidate.py  # summarize old episodic logs into semantic memory
└── forget.py       # selectively browse and delete memories
tools/
├── gmail.py        # Gmail IMAP fetch and search
└── applyops/       # job application tracker (CLI + web)
    ├── __main__.py # entry point (uv run applyops)
    ├── db.py       # shared SQLite data layer
    ├── cli.py      # Typer CLI commands
    └── web.py      # web dashboard (coming soon)
data/
└── applyops.db     # SQLite database (auto-created, gitignored)
```
