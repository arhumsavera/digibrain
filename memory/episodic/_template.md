# Episodic Memory Template
#
# Episodic memory logs what happened during interactions.
# One file per day, append-only. Never edit past entries.
#
# File naming: YYYY-MM-DD.md
#   e.g., 2026-02-15.md
#
# Format:

# YYYY-MM-DD

## HH:MM — [Brief task title]
- **Agent**: claude | opencode
- **Domain**: jobs | fitness | general | ...
- **Task**: What was requested
- **Outcome**: What happened, key results
- **Importance**: 2  <!-- 1=trivial, 2=routine (default), 3=useful context, 4=significant preference/update, 5=hard correction ("never do X") -->
- **Artifacts**: Files created/modified, if any
- **Followup**: Next steps identified, if any
