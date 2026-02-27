# Memory Buffs

A shared scratchpad for agents to propose improvements to the memory system.
Write under your agent identifier. No need to hold back — speculation is welcome.

---

## [claude]

*Research basis: A-MEM (NeurIPS 2025), Mem0 (arxiv 2504.19413), MemGPT (arxiv 2310.08560), design patterns survey at serokell.io*

---

### 1. Semantic Embeddings for Retrieval (instead of keyword grep)

**What:** Embed every semantic and procedural memory file (and each episodic entry) using a local embedding model (e.g. `nomic-embed-text` via Ollama). Store vectors in a lightweight store like ChromaDB or sqlite-vec. On each task, retrieve the top-k most similar memories by cosine similarity against the user's message, rather than loading everything.

**Why this matters now:** We currently load all untagged semantic files every session. As the semantic directory grows (>20 files), context bloat becomes real. Retrieval lets the system scale to hundreds of notes without blowing the context window.

**Benefit:** 90%+ token cost reduction (consistent with Mem0's benchmarks), more relevant context per task, no manual domain tagging required for basic relevance.

**Implementation sketch:**
```
scripts/embed.py --index     # rebuild the vector index
uv run applyops item search  # already does text search; vector search as fallback
```

---

### 2. Zettelkasten-Style Memory Linking (A-MEM pattern)

**What:** When a new semantic memory note is written, run a lightweight pass to find related existing notes (by embedding similarity or keyword overlap) and append a `<!-- links: file1.md, file2.md -->` annotation. When loading context, optionally follow links one hop deep.

**Why this matters:** Right now semantic notes are isolated flat files. A note about "user prefers short responses" doesn't connect to a note about "user's communication style." Linking builds a knowledge graph without any graph DB.

**Benefit:** Retrieval becomes relational, not just matching. The agent surfaces connected context it wouldn't have found with a straight similarity search. Mirrors how human associative memory works.

**Implementation sketch:**
```python
# In scripts/consolidate.py or a new scripts/link.py
# After writing/updating a semantic file, find top-3 related files
# Append: <!-- links: related1.md, related2.md -->
```

---

### 3. Importance Scoring + Memory Decay

**What:** Tag each episodic entry and semantic fact with an importance score (1–5) at write time, set by the agent based on signal strength (explicit user correction = 5, casual mention = 1). Apply time decay: importance × e^(−λ·days_old). Facts below a threshold get flagged for review during consolidation rather than auto-archived.

**Why this matters:** Currently all episodic entries are equal. A user saying "I hate this pattern, never do it again" has the same weight as "checked email." Consolidation should surface high-importance signals more aggressively.

**Benefit:** Procedural corrections survive consolidation. Low-signal noise decays naturally. Agents stop re-making the same corrected mistakes after consolidation runs.

**Implementation sketch:**
```yaml
# Episodic entry header extension
Importance: 4
Decay-Half-Life: 30d  # days
```

---

### 4. Agent-Triggered Consolidation (not just cron)

**What:** During the memory write step, check if today's episodic log has exceeded N entries (e.g. 10) or if a high-importance correction was made. If so, auto-trigger a mini-consolidation of just today's entries into a semantic update.

**Why this matters:** The weekly cron is too coarse. A productive day with 15 interactions might contain 3 corrections worth promoting to procedural memory immediately — but they sit in the episodic log for up to 7 days.

**Benefit:** Procedural corrections take effect in the next session, not next week. Autonomy increases — the system self-organizes without requiring a scheduled job.

**Implementation sketch:**
```python
# At end of PROTOCOL.md write step:
# if len(today_entries) >= 10 or any entry.importance >= 4:
#     run consolidate.py --days 0 --apply
```

---

### 5. Cross-Agent Memory Conflict Detection

**What:** When any agent writes a semantic memory, scan existing semantic files for contradictions (same topic, different claim). Flag conflicts in a `memory/semantic/_conflicts.md` file with both the old and new claim for human review, rather than silently overwriting.

**Why this matters:** Claude and Gemini might learn contradictory "facts" from different conversation threads. Right now one silently overwrites the other. A conflict log makes disagreements visible.

**Benefit:** Trust increases — humans can audit what each agent believes. Prevents silent regression when one agent's session contradicts an established fact.

**Example conflict entry:**
```
## Conflict detected 2026-02-27
Topic: user's preferred response length
claude (2026-02-20): "user prefers concise, bullet-point responses"
gemini (2026-02-27): "user prefers detailed narrative explanations"
Resolution: [ ] keep claude  [ ] keep gemini  [ ] merge
```

---

### 6. MemGPT-Style Context Budgeting

**What:** Define a context budget (e.g. 4000 tokens) for the memory load step. Rank candidate memory files by relevance score (embedding similarity) and recency. Load greedily until budget is consumed. Summarize or truncate lower-priority files rather than omitting them.

**Why this matters:** Right now the protocol says "load all untagged semantic files." With no ceiling, this scales linearly with memory growth. MemGPT treats the context window as RAM — finite, managed.

**Benefit:** Predictable and stable context usage regardless of memory volume. Faster cold-start per task.

---

### 7. Structured Episodic Schema (machine-readable frontmatter)

**What:** Move episodic entries to YAML frontmatter + markdown body, instead of free-form markdown headers. This makes entries queryable without LLM parsing.

```yaml
---
date: 2026-02-27
agent: claude
domain: fitness
importance: 2
tags: [workout, run]
outcome: success
---
User logged a 5k run. Added item to fitness domain.
```

**Why this matters:** `scripts/consolidate.py` currently uses an LLM to parse entries. Structured frontmatter makes consolidation, search, and decay scoring deterministic and fast — no LLM call needed to read importance scores or domains.

**Benefit:** Faster consolidation, reliable filtering by domain/date/agent/importance without regex hacks. Opens the door to SQLite-backed episodic storage (episodic entries as rows, not files).

---

### 8. Multi-Agent Memory Sync Protocol

**What:** Add a lightweight "last-write-wins with tombstone" sync mechanism. Each semantic file carries a `last_updated_by: claude` and `version: 3` header. When an agent writes, it increments the version. If two agents both increment from version 3 → 4, the second write detects the conflict (sees version 4 already exists) and routes to `_conflicts.md` instead.

**Why this matters:** Claude Code, opencode, and Gemini all write to the same `memory/semantic/` directory. There's no coordination right now — last write wins silently. At scale (3+ agents, multiple sessions per day), this is a latent data loss bug.

**Benefit:** Safe multi-agent writes. Foundation for a proper shared memory layer if we ever move to a remote store.

---

### 9. Vectorless RAG via Tree-Indexed Memory (PageIndex pattern)

**What:** Instead of embedding memory files and doing vector similarity search (idea #1), build a lightweight hierarchical index over the memory directory — a `memory/index.md` that is a structured table of contents: each semantic file gets a one-line description, grouped by topic cluster. On each task, the agent reads the index first, reasons about which files are relevant, then fetches only those. No embeddings, no vector DB.

**Why this is interesting:** PageIndex achieves 98.7% on FinanceBench using this approach — no chunking, no vectors, just structure + LLM reasoning about *where* to look. The key insight: **semantic similarity ≠ relevance**. An agent reasoning over a ToC ("the user asked about fitness, so load `fitness-goals.md` and `workout-history.md`, skip `career-notes.md`") is often more accurate than pure cosine similarity, especially for short queries or queries with implicit context.

**Why it fits this codebase perfectly:** Our memory directory is *already* a tree: `semantic/`, `episodic/`, `procedural/`, each with domain-tagged files. We already have domain detection (`uv run applyops domain detect`). We're one `memory/index.md` file away from the PageIndex pattern — the agent reads the index, picks files, loads them. No new infrastructure at all.

**Benefit:**
- Zero infra overhead (no Chroma, no Ollama embeddings endpoint needed)
- Reasoning-based retrieval is more robust for multi-hop questions ("what did I work on last week related to my fitness goals?")
- The index doubles as human-readable memory documentation
- Degrades gracefully if the index is stale — agent falls back to loading all untagged files

**Implementation sketch:**
```markdown
<!-- memory/index.md — auto-maintained by consolidate.py -->
## Semantic Memory Index
| File | Topics | Last Updated |
|------|--------|-------------|
| identity.md | user identity, name, timezone, preferences | 2026-02-20 |
| fitness-goals.md | running, lifting, weekly targets | 2026-02-15 |
| project-arch.md | digibrain repo structure, tech stack | 2026-02-27 |

## Procedural Memory Index
| File | Domain | Trigger |
|------|--------|---------|
| response-style.md | general | user corrects tone/format |
| git-workflow.md | dev | user corrects git commands |
```

```python
# In consolidate.py --apply, after archiving episodes:
# Regenerate memory/index.md from current semantic/ and procedural/ files
```

**The PROTOCOL.md update would be:**
> Before every task: read `memory/index.md`, select relevant files by reasoning, load only those. Fall back to loading all untagged files if index doesn't exist.

**vs. idea #1 (embeddings):** Vectorless is simpler and has no runtime dependency. Embeddings win on pure recall at scale (1000+ files). For this system at its current scale, vectorless tree indexing is the pragmatic choice — revisit embeddings if semantic/ exceeds ~50 files.

---

### Summary Priority Matrix

| Idea | Autonomy Gain | Effort | Impact |
|------|--------------|--------|--------|
| Structured episodic schema | Medium | Low | High — enables everything downstream |
| Agent-triggered consolidation | High | Low | High — corrections propagate same-day |
| Importance scoring + decay | Medium | Low | High — signal/noise improves over time |
| **Vectorless tree index** | **High** | **Low** | **High — zero infra, better retrieval now** |
| Cross-agent conflict detection | Medium | Medium | High — trust + correctness |
| Zettelkasten linking | High | Medium | Medium — emergent knowledge graph |
| MemGPT context budgeting | Low | Medium | Medium — scalability ceiling fix |
| Semantic embeddings | High | High | High — best at scale (50+ files), needs infra |
| Multi-agent sync protocol | Medium | High | Medium — needed at scale |

**Recommended starting point:** Structured episodic schema + vectorless tree index + agent-triggered consolidation. All three are low-effort, require no new infrastructure, and the tree index immediately improves retrieval quality without the embedding overhead.

---

*Sources consulted:*
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560)
- [Design Patterns for Long-Term Memory in LLM-Powered Architectures](https://serokell.io/blog/design-patterns-for-long-term-memory-in-llm-powered-architectures)
- [Agent Memory: How to Build Agents that Learn and Remember — Letta](https://www.letta.com/blog/agent-memory)
- [Graph Memory for AI Agents — Mem0](https://mem0.ai/blog/graph-memory-solutions-ai-agents)
- [PageIndex: Vectorless, reasoning-first RAG](https://pageindex.ai/blog/pageindex-intro)
- [GitHub — VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex)
- [Vectorless RAG: Letting an LLM Navigate Documents Like a Human](https://medium.com/@omtita.codes/vectorless-rag-letting-an-llm-navigate-documents-like-a-human-d5834ad518ec)
