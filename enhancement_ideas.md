# Enhancement Ideas

Living backlog of ideas, future features, and architectural decisions.
Updated as ideas come up in conversation. Not agent instructions.

---

## Voice Interface

> **Note**: Reference implementation was built for a different machine. Adapt paths and check compatibility before implementing. Also needs to support opencode hooks (not just Claude Code Stop/Notification hooks), or be refactored so both agents can share the same TTS/STT layer.

Local push-to-talk + TTS pipeline for hands-free agent interaction.

**STT**: `whisper-server` (whisper.cpp) running warm on `:8787`. Hotkey (Raycast) triggers recording → audio sent to server → transcription pasted into focused app via `pbcopy` + `Cmd+V`.

**TTS**: Kokoro ONNX TTS server on `:8788`. Claude's Stop hook calls `voice speak` after each turn. Responses are sentence-split and streamed in chunks — first sentence plays in ~2s while next is generating.

**Priority / concurrency**:
- Hotkey press kills active TTS immediately (`pkill afplay`)
- All TTS calls block while recording (`dictate.pid` exists)
- `mkdir`-based speech lock prevents multiple agents from interleaving audio
- Mute kills current sentence + abandons remaining chunks

**Hook integration** (Claude Code today):
- Stop hook: strip code blocks, speak prose (max 2000 chars)
- Notification hook: speak permission prompts aloud

**opencode gap**: opencode has no Stop/Notification hooks. Would need either: (a) opencode hook support added, or (b) a shared `voice speak` wrapper that both agents call explicitly, or (c) polling the conversation log.

**Known limitations**:
- ~2s first-sentence latency (kokoro generation time)
- Clipboard clobbered by dictate (pbcopy)
- Focus-dependent paste — switching apps during transcription mispastes
- RAM: whisper ~1GB + kokoro ~500MB
- 20dB mic gain hardcoded for MacBook built-in mic

**Stack**: whisper.cpp, kokoro-onnx, sox, afplay, Raycast, launchd for auto-start.

---

## Search & Retrieval

- **Embedding-based search**: sqlite-vec + Ollama `nomic-embed-text` (768d, free/local). Add `items_vec` virtual table with domain_id partition key for scoped vector search.
- **Hybrid retrieval**: Combine FTS5 keyword search + vec0 semantic search, merge via Reciprocal Rank Fusion (RRF) scoring.
- **Cross-domain discovery**: Unscoped vector search to find related items across domains.
- **Embedding-based domain detection**: Replace keyword matching with semantic similarity when embeddings are available.

## Memory System

- **Domain schema validation**: JSON Schema on `domains.schema` to validate `items.data` on insert.
- **Smart context loading**: Only load memory relevant to the detected domain, reducing token waste.
- **Memory search**: FTS5 or embedding search across episodic/semantic memory (currently just file reads).

## Tools & Integrations

- **Gmail API migration**: Replace IMAP with Gmail API for OAuth2, structured data, labels, push notifications.
- **Scheduled email scanning**: Cron or webhook for proactive inbox checks (currently manual trigger only).
- **Google Calendar integration**: `tools/gcal.py` using Google Calendar API (OAuth2). Needs `google-api-python-client` + `google-auth-oauthlib`. One-time auth flow saves `data/gcal_token.json`. Commands: `agenda`, `search`, `add`. Prereqs: enable Calendar API in Google Cloud Console, download `data/gcal_credentials.json`, add account as test user with `calendar.readonly` (or `.events`) scope.

## Agent Architecture

- **Cost tiering**: Route routine tasks (inbox scans, simple lookups) to opencode (free model), complex analysis to Claude.
- **Multi-agent coordination**: Agents working on subtasks in parallel with shared memory.

## Data & Analytics

- **Dashboard stats across all domains**: Unified view of activity, not just job tracking.
- **Export**: CSV/JSON export of any domain's items.
- **Backup/restore**: SQLite DB snapshots with restore capability.

---

## Code Review Notes

*From: opencode (2026-02-16)*

### Current Strengths

1. **Architecture** — Clean separation (memory/tools/bot/scripts), domain-driven design for generic item tracking
2. **Documentation** — CLAUDE.md is thorough; memory protocol is well-defined
3. **Modern tooling** — uv, pyproject.toml, Typer for CLI, pytest for testing
4. **Security-minded** — Bot validates TELEGRAM_ALLOWED_USER_IDS, refuses open access
5. **Flexible** — Domain system handles specialized (jobs) + generic (fitness/todos) use cases
6. **Git hygiene** — .gitignore properly excludes PII, DBs, cache files
7. **Memory model** — Semantic/episodic/procedural split is thoughtful

### Areas for Improvement

1. **Path coupling** — Hardcoded `/Users/arhumsavera/scripts/digibrain` paths; not portable
2. **No README** — Only agent-facing docs (CLAUDE.md); missing human onboarding
3. **Database pollution** — SQLite WAL/SHM files untracked in working dir (cosmetic but messy)
4. **Error handling gaps** — Some bare `except Exception: pass` in bot progress updates
5. **No validation** — `db.py` likely lacks input sanitization (haven't checked but common issue)
6. **Missing CI** — No GitHub Actions, pre-commit hooks
7. **Monolithic CLI** — `cli.py` is getting large; could split formatters/logic
8. **Secrets in env only** — No key rotation, no encrypted secrets option

---

## Completed: Web Dashboard MVP (2026-02-16)

*Built by: opencode*

Fully functional FastAPI + HTMX web interface for the Agent Memory Framework.

### Features Implemented

**Dashboard** (`/`)
- Live stats with auto-refresh (domains, items, DB size)
- Recent domains and items
- Recent memory files
- Quick action buttons

**Memory Browser** (`/memory`)
- Browse semantic, episodic, procedural memory
- Full-text search across all memory files
- **Editable**: View and edit any .md file directly in browser
- **Create new**: Add new memory files via web form
- Security: Path traversal protection on all file operations

**Domain Management** (`/domains`)
- List all domains with item counts
- Domain detail pages with all items
- Inline item creation via HTMX
- Status updates without page reload
- Item CRUD (Create, Read, Update)

**Agent Chat** (`/chat`)
- Real agent integration (opencode + Claude)
- Streaming responses via Server-Sent Events
- Session persistence
- File detection in agent responses
- Word-by-word streaming for natural feel

**Technical Stack**
- FastAPI for backend
- Jinja2 templates
- HTMX for partial page updates (no React)
- Dark theme (GitHub-inspired)
- Responsive grid layout
- Auto-reloading stats

**Routes Structure**
```
/                    → Dashboard
/memory              → Memory browser
/memory/view/...     → View memory file
/memory/edit/...     → Edit memory file
/memory/create/...   → Create new file
/memory/search       → Search memory
/domains             → List domains
/domains/{id}        → Domain detail
/chat                → Agent chat
```

**To Run**
```bash
uv run applyops serve
# Open http://127.0.0.1:8000
```

---

*Last updated: 2026-02-16*
