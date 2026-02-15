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

## ApplyOps API (Job Application Tracker)

ApplyOps is running at `http://localhost:8000`. Use `curl` to interact with it.
When the user asks about jobs, applications, resumes, or recruiting emails, use these endpoints.

### Jobs
| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/jobs` | Create a job listing (body: `{title, company_name, description, url?, source?}`) |
| GET | `/api/jobs` | List jobs (query: `?company_id=&approval_status=`) |
| GET | `/api/jobs/{id}` | Get job details |
| PUT | `/api/jobs/{id}` | Update a job |
| POST | `/api/jobs/{id}/approve` | Approve a discovered job |
| POST | `/api/jobs/{id}/reject` | Reject a discovered job |
| POST | `/api/jobs/{id}/analyze` | AI-analyze job for skills/requirements |
| PUT | `/api/jobs/{id}/analysis` | Confirm analysis results |
| POST | `/api/jobs/{id}/match` | Match a resume against this job (body: `{resume_id}`) |

### Resumes
| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/resumes` | Create a resume version |
| GET | `/api/resumes` | List all resumes |
| GET | `/api/resumes/{id}` | Get resume details |
| POST | `/api/resumes/tailor` | Tailor resume to job (body: `{resume_id, job_id, mode: "suggest"\|"rewrite"}`) |
| PUT | `/api/resumes/tailor/confirm` | Confirm and save tailored resume |

### Applications
| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/applications` | Create application (body: `{job_id, resume_version_id?}`) |
| GET | `/api/applications` | List applications (query: `?status=`) |
| GET | `/api/applications/{id}` | Get application details |
| PATCH | `/api/applications/{id}` | Update status/details |
| DELETE | `/api/applications/{id}` | Delete application |

### Discovery (from emails/links)
| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/discovery/email` | Extract job info from email text (body: `{text}`) |
| POST | `/api/discovery/email/confirm` | Confirm discovered job → create listing |

### Emails
| Method | Path | What it does |
|--------|------|--------------|
| POST | `/api/emails/extract` | Extract structured data from email text |
| POST | `/api/emails` | Save email event |
| GET | `/api/emails` | List email events |

### Other
| Method | Path | What it does |
|--------|------|--------------|
| GET | `/api/dashboard/stats` | Dashboard stats (counts, skill gaps) |
| GET | `/api/companies` | List companies |
| POST | `/api/companies` | Create company |
| GET | `/api/task-runs` | List AI agent audit logs |

### Workflow examples
- **"Check this job link"**: Fetch the URL, then `POST /api/jobs` with extracted info, then `POST /api/jobs/{id}/analyze`
- **"Parse this recruiter email"**: `POST /api/discovery/email` with the text, review result, then `/confirm`
- **"How's my pipeline?"**: `GET /api/dashboard/stats` or `GET /api/applications`
- **"Tailor my resume for X role"**: Find the job and resume IDs, then `POST /api/resumes/tailor`

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
3. If it's a job/recruiter email: `POST /api/discovery/email` with the email text
4. Show user the result, if they confirm: `POST /api/discovery/email/confirm`

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
└── email.py        # Gmail IMAP fetch and search
```
