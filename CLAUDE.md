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
   - Set Agent to `claude`
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

## Project Structure
```
memory/
├── semantic/    # persistent facts, preferences, knowledge
├── episodic/    # daily interaction logs (YYYY-MM-DD.md)
└── procedural/  # learned workflows and rules
scripts/
├── consolidate.py  # summarize old episodic logs into semantic memory
└── forget.py       # selectively browse and delete memories
```
