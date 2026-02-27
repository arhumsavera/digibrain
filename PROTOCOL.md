# digibrain — Shared Protocol

This is the canonical protocol for all agents using this memory framework.
Each agent has its own stub file (e.g. `CLAUDE.md`, `opencode.md`) that declares
its identifier and points here.

## Modes

### User mode (default)
You're helping the user accomplish tasks — checking email, managing items, researching, etc.
Follow the full memory protocol below.

### Dev mode
You're working on the app itself — modifying code in `tools/`, `bot/`, `scripts/`, or any agent instruction file.
**Skip the memory protocol entirely** — no reading memory before, no logging after. Focus on the code.

Dev mode activates when:
- The user says "dev mode"
- The user explicitly says not to log

When in doubt, ask.

## Memory Protocol

### Before every task:
1. Detect domain from the user's message (use `uv run applyops domain detect "..."` or your own judgment)
2. If a domain is detected, load its instructions: `uv run applyops domain show <name>`
3. Read `memory/index.md` (if it exists). Reason over it to select which semantic and procedural files are relevant to this task. Load only those files. If the index doesn't exist, fall back to loading all untagged (global) files plus any domain-tagged files (`<!-- domain: X -->`) matching the detected domain.
4. Read today's `memory/episodic/YYYY-MM-DD.md` if it exists
5. Check `memory/procedural/` for workflows matching the detected domain + `general`

### After every task:
1. **Episodic**: Append an entry to `memory/episodic/YYYY-MM-DD.md` (create if needed)
   - Use the format from `memory/episodic/_template.md`
   - Set Agent to **your agent identifier** (declared in your stub file)
   - Set Domain to the detected domain (or `general` if none)
   - Include timestamp, task summary, outcome, and any followups
   - Never edit past entries — append only

2. **Procedural**: If the user corrected you or gave feedback on how to do something:
   - Update or create an entry in `memory/procedural/`
   - Use the format from `memory/procedural/_template.md`

3. **Semantic**: If new persistent facts were learned (preferences, project info, etc.):
   - Update or create an entry in `memory/semantic/`
   - Use the format from `memory/semantic/_template.md`
   - Merge into existing files when relevant — don't create duplicates

4. **Importance**: Set `**Importance**: N` (1–5) on each episodic entry:
   - **5**: User said "never do X" / explicit hard correction
   - **4**: Significant preference or workflow update
   - **3**: Useful context, moderate signal
   - **2**: Routine task (default)
   - **1**: Trivial / informational
   If importance ≥ 4, also update semantic or procedural memory immediately in this session — don't wait for the weekly cron.

### Forgetting:
When the user asks to forget, clear, or delete memories:
1. Use `python scripts/forget.py list` or `list --search "keyword"` to find relevant entries
2. Show the user what was found and confirm what to delete
3. Run `python scripts/forget.py forget` with the appropriate flags (dry run first)
4. Only add `--apply` after user confirms the dry run output

Common commands:
- `python scripts/forget.py list` — show all memories
- `python scripts/forget.py list --search "keyword"` — search across all types
- `python scripts/forget.py list --domain jobs` — filter by domain tag
- `python scripts/forget.py forget --search "keyword"` — remove matching entries (dry run)
- `python scripts/forget.py forget --file name.md` — remove a specific file (dry run)
- `python scripts/forget.py forget --type episodic --before YYYY-MM-DD` — remove old logs (dry run)
- `python scripts/forget.py forget --domain fitness --all --type episodic` — remove all entries for a domain
- Add `--apply` to any forget command to execute

### Consolidation:
To consolidate old episodic memories into semantic summaries:
- `python scripts/consolidate.py` — dry run
- `python scripts/consolidate.py --apply` — archive old episodes, save summary, regenerate index
- `python scripts/consolidate.py --days 14` — change age threshold
- `python scripts/consolidate.py --domain jobs` — consolidate only one domain
- `python scripts/consolidate.py --today` — mini-consolidation of today's entries without archiving (agent-triggered; importance ≥ 3 only)

### Rules:
- Never delete procedural memories without user confirmation
- Episodic entries are append-only
- Semantic entries can be updated (merge new info, don't duplicate)
- Keep entries concise — this is context for future tasks, not a transcript
- When in doubt about whether to save something, save it to episodic

## Domains

Domains organize tools and data by topic. Each domain has instructions loaded from the database at runtime.

### Specialized domains
Some domains have dedicated storage and richer CLI commands beyond the generic item store.
These are loaded as private extensions — run `uv run applyops domain show <name>` for a domain's full CLI reference.

### Generic domains
Any domain (fitness, todos, reading, projects, etc.) uses the generic item store. Create domains on the fly when the user asks to track something new.

### Domain commands
```bash
uv run applyops domain add "fitness" --description "..." --keywords '["workout","gym"]'
uv run applyops domain list [--json]
uv run applyops domain show <name-or-id> [--json]
uv run applyops domain update <name-or-id> [--keywords '["..."]'] [--instructions "..."]
uv run applyops domain remove <name-or-id>
uv run applyops domain detect "user message text"
```

### Item commands
```bash
uv run applyops item add --domain <name> --title "..." [--type workout] [--data '{}'] [--tags '[]'] [--status active] [--due "YYYY-MM-DD"] [--priority N]
uv run applyops item list --domain <name> [--type] [--status] [--sort due|priority|created] [--limit N] [--json]
uv run applyops item show <id> [--json]
uv run applyops item update <id> [--title] [--status done] [--data] [--tags] [--due] [--priority]
uv run applyops item remove <id>
uv run applyops item search "query" [--domain <name>]
uv run applyops item stats <domain> [--json]
```

### Creating domains on the fly
When a user says something like "track my workouts":
1. `uv run applyops domain add "fitness" --keywords '["workout","exercise","gym","run","lift"]' --description "Workout and health tracking"`
2. Start adding items: `uv run applyops item add --domain fitness --type workout --title "Morning run" --data '{"distance":"5k"}'`

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
1. `python tools/gmail.py inbox --unread` → scan for relevant emails
2. `python tools/gmail.py read <id>` → get full email text
3. Log structured data: `uv run applyops email add` + `uv run applyops item add` (or domain-specific commands)
4. Show user the result and confirm

## Project Structure
```
memory/
├── semantic/    # persistent facts, preferences, knowledge
├── episodic/    # daily interaction logs (YYYY-MM-DD.md), domain-tagged
└── procedural/  # learned workflows and rules, domain-tagged
scripts/
├── consolidate.py  # summarize old episodic logs (supports --domain)
└── forget.py       # selectively browse and delete memories (supports --domain)
tools/
├── gmail.py        # Gmail IMAP fetch and search
└── applyops/       # CLI: domain/item store + web dashboard
    ├── __main__.py # entry point (uv run applyops)
    ├── db.py       # SQLite data layer
    ├── cli.py      # Typer CLI commands
    └── web.py      # web dashboard
data/
├── applyops.db     # SQLite database (auto-created, gitignored)
└── output/         # rendered output files (gitignored)
```
