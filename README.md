# 🧠 digibrain

> **Your AI agents, but they actually remember you.**

Persistent shared memory for AI coding agents. Gives Claude Code, opencode, and Gemini the ability to remember facts, track interactions, and follow learned workflows across sessions — so every conversation picks up exactly where the last one left off.

🚀 **No vectors. No embeddings. No infrastructure.** Memory is plain Markdown files. Retrieval is a tree-index the agent reasons over — the right files get loaded, irrelevant ones stay out of context. Includes a Telegram bridge so you can talk to your agents from your phone.

---

## 🏗️ Design Philosophy

Most agent memory systems reach for vector databases: embed everything, retrieve by cosine similarity, hope the right chunks surface. **digibrain** takes a more surgical approach.

### 🌲 Vectorless Retrieval via Tree Index
`memory/index.md` is an auto-generated table of contents — one row per file, with title, domain tag, and last-updated date. Before each task, the agent reads the index, reasons about relevance, and loads only what it needs.

*   **Small & Structured:** Perfect for personal/team memory (dozens of files, not millions).
*   **Semantic Routing:** The agent understands "fitness goal" implies loading `fitness-goals.md`.
*   **Transparent:** Read the index yourself and see exactly what the agent sees.
*   **Zero Dependencies:** Just plain text files.

### 📂 Three Memory Types
Matching how humans store different kinds of knowledge:

*   **📖 Episodic:** Append-only daily logs of interactions (`memory/episodic/YYYY-MM-DD.md`).
*   **🧠 Semantic:** Persistent facts, preferences, and project knowledge (`memory/semantic/`).
*   **🛠️ Procedural:** Learned workflows and rules, updated when you correct the agent (`memory/procedural/`).

### ⚡ Importance Scoring
Every episodic entry carries a signal strength (1–5). 
*   **High signal (4-5):** Corrections and preference changes update semantic memory **immediately**.
*   **Low signal (1-3):** Routine logs accumulate and are batch-consolidated by a weekly cron job.

---

## 🤖 Supported Agents

The full protocol lives in `PROTOCOL.md`. Adding a new agent takes 30 seconds.

*   **Anthropic Claude Code:** Loads `CLAUDE.md`.
*   **OpenCode:** Loads `opencode.md`.
*   **Gemini CLI:** Loads `GEMINI.md`.

---

## 🛠️ Data Store (applyops)

`applyops` is a CLI-driven SQLite store for structured data. It uses a **domain + item** model where each domain organizes items of any shape.

```bash
# 🔍 Detect domain from intent
uv run applyops domain detect "I want to track my workouts"

# ➕ Add and query items
uv run applyops item add --domain research --title "Attention Is All You Need" --type paper
uv run applyops item search "transformer"
```

| Domain | Use Case |
| :--- | :--- |
| `research` | Papers, articles, notes |
| `fitness` | Workouts, runs, PRs |
| `todos` | Tasks with priorities and due dates |
| `projects` | Side projects and milestones |

---

## 📱 Telegram Bridge

Talk to your local agents from your phone — no terminal required.
*   **Streamed Responses:** Watch the agent "type" back in real-time.
*   **File Support:** Send screenshots or logs directly to the agent.
*   **Custom Personas:** Switch between `/claude`, `/gemini`, or your own custom agents.

```bash
uv run agent-bot
```

---

## 🌊 Prefect Flows

Scheduled automation built on [Prefect 3](https://docs.prefect.io/).
*   **Weekly Consolidation:** Automatically archives old episodic logs and updates semantic summaries.
*   **Generic Agent Flow:** Run any prompt as a background task and log the result to memory.

---

## 🚀 Getting Started

### Requirements
*   Python 3.12+
*   [uv](https://docs.astral.sh/uv/)
*   Your favorite Agent CLI (Claude Code, opencode, or Gemini)

### Install
```bash
git clone https://github.com/arhumsavera/digibrain
cd digibrain
uv sync
```

### Configure
```bash
cp .env.example .env
# Edit .env with your credentials
uv run applyops domain list  # Initializes the DB
```

### Test
```bash
uv run pytest tests/
```

---

## 📁 Project Structure

```text
memory/
├── semantic/    # Persistent facts & preferences
├── episodic/    # Daily interaction logs
└── procedural/  # Learned workflows & rules
tools/
├── gmail.py     # Gmail IMAP client
└── applyops/    # CLI + SQLite Layer + Web Dashboard
scripts/
├── consolidate.py  # Episodic → Semantic archival
└── forget.py       # Selective memory deletion
flows/           # Prefect workflow definitions
```

---
🧬 *Built for agents that don't want to forget.*
