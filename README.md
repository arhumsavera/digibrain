# digibrain

> Your AI agents, but they actually remember you.

Persistent shared memory for AI coding agents. Gives Claude Code, opencode, and other agents the ability to remember facts, track interactions, and follow learned workflows across sessions — so every conversation picks up where the last one left off.

**No vectors. No embeddings. No infrastructure.** Memory is plain Markdown files. Retrieval is a table-of-contents index the agent reasons over — the right files get loaded, irrelevant ones stay out of context. Includes a Telegram bridge so you can talk to your agents from your phone.

## Design

Most agent memory systems reach for vector databases: embed everything, retrieve by cosine similarity, hope the right chunks surface. digibrain takes a different approach.

**Vectorless retrieval via a tree index.** `memory/index.md` is an auto-generated table of contents — one row per file, with title, domain tag, and last-updated date. Before each task the agent reads the index (a few hundred tokens), reasons about which files are relevant, and loads only those. No embeddings, no retrieval infrastructure, no approximate nearest-neighbor search. The agent's own language understanding does the routing.

This works well for personal and team agent memory because:
- The memory corpus is small and well-structured (dozens of files, not millions of documents)
- Relevance is semantic, not just lexical — the agent understands "fitness goal" implies loading `fitness-goals.md`
- Transparent: you can read the index yourself and see exactly what the agent will load
- Zero dependencies beyond the files themselves

**Three memory types**, matching how humans store different kinds of knowledge:

- **Episodic** — append-only daily logs of interactions (`memory/episodic/YYYY-MM-DD.md`)
- **Semantic** — persistent facts, preferences, and project knowledge (`memory/semantic/`)
- **Procedural** — learned workflows and rules, updated when the agent is corrected (`memory/procedural/`)

**Importance scoring.** Every episodic entry carries a signal strength (1–5). High-importance entries (corrections, preference changes) immediately update semantic/procedural memory in the same session. Low-importance entries accumulate and are batch-consolidated by the weekly cron.

**Telegram bridge.** A bot connects your local agents to Telegram so you can run prompts, check results, and get proactive notifications from your phone — no terminal required. Responses stream in as they arrive.

Agents read relevant memory before each task and write to it afterward, building context over time.

## Supported Agents

The full protocol lives in `PROTOCOL.md`. Each agent has a small stub file that declares its identifier and points there — that's the only thing that differs between agents.

### Claude Code

`CLAUDE.md` (auto-loaded by Claude Code):
```
Your agent identifier is `claude`. Read PROTOCOL.md for the full protocol.
```

### opencode

`opencode.md` (auto-loaded by opencode):
```
Your agent identifier is `opencode`. Read PROTOCOL.md for the full protocol.
```

### Adding a new agent (e.g. Gemini)

Create a stub file for whichever instruction filename that agent loads (e.g. `GEMINI.md`):

```markdown
# digibrain — Gemini

Your agent identifier is `gemini`. Use this in the **Agent** field of all episodic memory entries.

Read `PROTOCOL.md` for the full memory protocol, modes, domain commands, and tools.
```

That's it. All protocol changes stay in `PROTOCOL.md` — no duplication across agent files.

Optionally, add a runner in `bot/agents.py` to expose the new agent through the Telegram bridge.

## Memory Protocol

### Before each task
1. Detect the domain from the user's message (`uv run applyops domain detect "..."`)
2. Load domain instructions if one is detected
3. Read `memory/index.md` (if it exists) and load only the relevant semantic/procedural files it lists; fall back to all untagged files if the index doesn't exist yet
4. Read today's episodic log if it exists
5. Check `memory/procedural/` for relevant workflows

### After each task
1. **Episodic**: Append an entry to `memory/episodic/YYYY-MM-DD.md`
2. **Procedural**: Update if the user gave feedback or corrections
3. **Semantic**: Update if new persistent facts were learned
4. **Importance**: Set `**Importance**: N` (1–5) on each episodic entry — if ≥ 4, also update semantic/procedural immediately without waiting for the weekly cron
   - 5: hard correction ("never do X")  4: significant preference/update  3: useful context  2: routine (default)  1: trivial

### Memory management

```bash
# Consolidate old episodic logs into semantic summaries
python scripts/consolidate.py              # dry run
python scripts/consolidate.py --apply      # archive episodes, write summary, regenerate index
python scripts/consolidate.py --days 14    # custom age threshold
python scripts/consolidate.py --domain X   # one domain only
python scripts/consolidate.py --today      # mini-consolidation of today's entries (no archiving, importance ≥ 3 only)

# Selectively forget memories
python scripts/forget.py list                     # show all
python scripts/forget.py list --search "keyword"  # search
python scripts/forget.py forget --search "keyword" # dry run
python scripts/forget.py forget --search "keyword" --apply  # execute
python scripts/forget.py forget --type episodic --before 2026-01-01 --apply
```

## Data Store (applyops)

`applyops` is a CLI-driven SQLite store for structured data. It uses a **domain + item** model where each domain organizes items of any shape.

```bash
# Manage domains
uv run applyops domain add "research" --description "Research notes" --keywords '["paper","study","read"]'
uv run applyops domain list
uv run applyops domain show research
uv run applyops domain detect "I want to track my workouts"

# Add and query items
uv run applyops item add --domain research --title "Attention Is All You Need" --type paper --data '{"year":2017,"authors":"Vaswani et al."}'
uv run applyops item list --domain research --sort created
uv run applyops item search "transformer"
uv run applyops item update <id> --status done
uv run applyops item stats research
```

Items support: `type`, `data` (arbitrary JSON), `tags`, `status`, `priority`, `due`.

### Example domains

| Domain | Use case |
|--------|----------|
| `research` | Papers, articles, notes |
| `fitness` | Workouts, runs, PRs |
| `todos` | Tasks with priorities and due dates |
| `reading` | Books and reading progress |
| `projects` | Side projects and milestones |

Domains are created on the fly — just `domain add` and start adding items.

### Specialized domains

Some domains have dedicated SQL tables for richer tracking. The `jobs` domain, for example, has tables for companies, applications, resumes, emails, and match analysis. Run `uv run applyops domain show jobs` for its full CLI reference.

### Web dashboard

```bash
uv run applyops serve   # starts at http://127.0.0.1:8000
```

Browse and search memory, inspect domains and items, view interaction history.

## Tools

### Gmail (`tools/gmail.py`)

Fetches email via IMAP. Useful for agents that need to act on email.

```bash
python tools/gmail.py inbox                        # latest 10
python tools/gmail.py inbox --unread --since 1d    # unread from today
python tools/gmail.py inbox --from "github.com"    # filter by sender
python tools/gmail.py inbox --subject "alert"      # filter by subject
python tools/gmail.py read <message_id>            # full email body
python tools/gmail.py search "deployment failed"   # IMAP search
```

Requires `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.env`.

## Telegram Bot

The bot bridges Telegram messages to agents running locally, so you can interact without a terminal.

```bash
uv run agent-bot
```

Commands in Telegram:
- `/opencode <prompt>` — run opencode (default)
- `/claude <prompt>` — run Claude Code
- `/gemini <prompt>` — run Gemini
- `/agent <name> <prompt>` — run as a named agent persona
- `/agents` — list available personas
- `/newagent <name> <description>` — create a new persona on the fly
- `/new` — start fresh session
- `/status` — current session info

The bot streams responses back as they arrive, supports file attachments, and can resume long-running sessions.

## Prefect Flows

Scheduled automation built on [Prefect 3](https://docs.prefect.io/). Flows run locally — no cloud account needed.

### First-time setup

**1. Create the work pool** (one time):
```bash
prefect work-pool create local --type process
```

**2. Start the server** (keep running in a terminal):
```bash
prefect server start
# UI at http://localhost:4200
```

**3. Start the worker** (keep running in a separate terminal):
```bash
PREFECT_API_URL=http://127.0.0.1:4200/api prefect worker start --pool local
```

**4. Deploy and verify:**
```bash
uv run applyops flows deploy   # registers all flows from prefect.yaml
uv run applyops flows list     # confirm deployments are registered
```

Both the server and worker need to be restarted manually after a reboot.

### Running flows

```bash
uv run applyops flows run weekly-consolidation          # trigger immediately
uv run applyops flows run generic-agent-flow            # run with default params
uv run applyops flows ui                                # open Prefect UI in browser
```

The `generic-agent-flow` accepts parameters via the Prefect UI or CLI:
```bash
uv run applyops flows run generic-agent-flow \
  --param prompt="summarize my memory/semantic/ directory" \
  --param domain="general"
```

### Included flows

| Flow | Schedule | What it does |
|------|----------|-------------|
| `weekly-consolidation` | Sundays 9 AM PST | Runs `scripts/consolidate.py --apply` — archives old episodic logs, writes semantic summaries |
| `generic-agent-flow` | On demand | Runs any Claude prompt, logs result to episodic memory |

> Additional flows (e.g. email processing) can be added as private extensions in `flows/` and registered in `prefect.yaml`.

### Adding a custom scheduled flow

1. Create `flows/my_flow.py`:
```python
from prefect import flow
from flows.base import write_episodic_task

@flow(name="my-flow")
async def my_flow():
    result = "done something"
    await write_episodic_task(result, domain="general", task_name="my-flow")
```

2. Add to `prefect.yaml`:
```yaml
- name: my-flow
  entrypoint: flows/my_flow.py:my_flow
  schedules:
    - cron: "0 8 * * *"
      timezone: "America/Los_Angeles"
  work_pool:
    name: local
    work_queue_name: default
```

3. Redeploy: `uv run applyops flows deploy`

### Ollama (optional, for summarization tasks)

Flows that use `ollama_task` from `flows/base.py` require [Ollama](https://ollama.com/) running locally:
```bash
brew install ollama
ollama pull llama3.2:1b
ollama serve   # runs on http://localhost:11434
```

`llama3.2:1b` is fast (~5s/call) and requires no API key — used for text summarization in automated flows.

## Getting Started

### Requirements

**Agent engines** (install whichever you use):
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — `npm install -g @anthropic-ai/claude-code`
- [opencode](https://opencode.ai) — `npm install -g opencode`
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) — `npm install -g @google/gemini-cli`

**Runtime:**
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) (for flows, optional)

### Install

```bash
git clone https://github.com/your-username/digibrain
cd digibrain
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env with your credentials
```

### Initialize the database

```bash
uv run applyops domain list   # creates data/applyops.db on first run
```

### Run tests

```bash
uv run pytest tests/
```

## Project Structure

```
memory/
├── index.md        # auto-generated table of contents (read this first)
├── semantic/       # persistent facts and knowledge
├── episodic/       # daily interaction logs (YYYY-MM-DD.md)
│   └── archive/    # logs older than N days, post-consolidation
└── procedural/     # learned workflows and correction history
tools/
├── gmail.py        # Gmail IMAP client
└── applyops/       # CLI + data layer + web dashboard
    ├── cli.py      # Typer CLI
    ├── db.py       # SQLite schema and queries
    ├── web.py      # FastAPI server
    └── routes/     # route handlers
bot/
├── main.py         # Telegram bot
├── agents.py       # Claude / opencode runners
└── sessions.py     # per-user session state
scripts/
├── consolidate.py  # episodic → semantic archival
└── forget.py       # selective memory deletion
flows/              # Prefect workflow definitions
data/               # SQLite database (gitignored)
PROTOCOL.md         # canonical shared protocol (edit this)
CLAUDE.md           # stub: declares agent identifier `claude`
opencode.md         # stub: declares agent identifier `opencode`
```

## Dev Mode

When working on digibrain itself, tell the agent to enter dev mode to skip the memory protocol:

> "dev mode: ..."

In dev mode, no memory is read before the task and nothing is logged after.
