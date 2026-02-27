#!/usr/bin/env python3
"""
Consolidate old episodic memories into semantic summaries.

Usage:
    python scripts/consolidate.py              # dry run (default)
    python scripts/consolidate.py --apply      # actually move/archive + regenerate index
    python scripts/consolidate.py --days 14    # change age threshold (default: 7)
    python scripts/consolidate.py --today      # mini-consolidation of today's entries (no archiving)
"""

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
EPISODIC_DIR = MEMORY_DIR / "episodic"
SEMANTIC_DIR = MEMORY_DIR / "semantic"
ARCHIVE_DIR = EPISODIC_DIR / "archive"


def extract_importance(block: str) -> int:
    """Extract importance score from an episodic block string.

    Returns an integer 1–5. Defaults to 2 if the field is absent.
    Values outside 1–5 are clamped to that range.
    """
    match = re.search(r"\*\*Importance\*\*:\s*(\d+)", block)
    if match:
        return max(1, min(5, int(match.group(1))))
    return 2


def get_old_episodic_files(days: int) -> list[Path]:
    """Find episodic files older than `days` days."""
    cutoff = datetime.now() - timedelta(days=days)
    old_files = []

    for f in EPISODIC_DIR.glob("*.md"):
        if f.name.startswith("_"):
            continue
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d")
            if file_date < cutoff:
                old_files.append(f)
        except ValueError:
            continue

    return sorted(old_files)


def extract_entries(filepath: Path) -> list[dict]:
    """Parse episodic entries from a daily log file."""
    content = filepath.read_text()
    entries = []

    # Split on ## HH:MM headers
    blocks = re.split(r"(?=^## \d{2}:\d{2})", content, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block.startswith("## "):
            continue

        entry = {"raw": block, "date": filepath.stem, "importance": 2}

        for line in block.split("\n"):
            line = line.strip("- ")
            if line.startswith("**Task**:"):
                entry["task"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Outcome**:"):
                entry["outcome"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Agent**:"):
                entry["agent"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Domain**:"):
                entry["domain"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Importance**:"):
                try:
                    val = int(line.split(":", 1)[1].strip())
                    entry["importance"] = max(1, min(5, val))
                except ValueError:
                    pass

        if "task" in entry or "outcome" in entry:
            entries.append(entry)

    return entries


def summarize_entries(entries: list[dict], domain_filter: str | None = None) -> str:
    """Create a plain-text summary sorted by importance (desc), high-importance flagged with ⚑."""
    if not entries:
        return ""

    if domain_filter:
        entries = [e for e in entries if e.get("domain", "general") == domain_filter]
        if not entries:
            return ""

    lines = ["# Consolidated Episodic Summary", ""]
    dates = sorted(set(e["date"] for e in entries))
    lines.append(f"Period: {dates[0]} to {dates[-1]}")
    lines.append(f"Total entries: {len(entries)}")

    if domain_filter:
        lines.append(f"Domain: {domain_filter}")
        lines.append("")
        lines.append(f"<!-- domain: {domain_filter} -->")

    lines.append("")

    # Group by domain
    domains: dict[str, list[dict]] = {}
    for entry in entries:
        d = entry.get("domain", "general")
        domains.setdefault(d, []).append(entry)

    for domain_name in sorted(domains.keys()):
        # Sort each group by importance descending
        domain_entries = sorted(
            domains[domain_name], key=lambda e: e.get("importance", 2), reverse=True
        )
        if len(domains) > 1:
            lines.append(f"### {domain_name}")
            lines.append("")
        for entry in domain_entries:
            task = entry.get("task", "unknown task")
            outcome = entry.get("outcome", "no outcome recorded")
            agent = entry.get("agent", "unknown")
            importance = entry.get("importance", 2)
            flag = "⚑ " if importance >= 4 else ""
            lines.append(f"- {flag}[{entry['date']}] ({agent}) {task} -> {outcome}")
        if len(domains) > 1:
            lines.append("")

    lines.append("")
    lines.append(f"<!-- Consolidated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->")
    return "\n".join(lines)


def generate_index(memory_dir: Path) -> str:
    """Generate memory/index.md as a vectorless table of contents.

    Scans semantic/ and procedural/ directories, extracts H1 titles,
    domain tags (<!-- domain: X -->), and last-updated comments
    (<!-- Last updated: ... -->) to build a navigational index.

    Writes the result to memory_dir/index.md and returns the content.
    """
    semantic_dir = memory_dir / "semantic"
    procedural_dir = memory_dir / "procedural"

    def scan_dir(d: Path) -> list[dict]:
        files = []
        if not d.exists():
            return files
        for f in sorted(d.glob("*.md")):
            if f.name.startswith("_"):
                continue
            text = f.read_text()

            title = "(untitled)"
            for line in text.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            domain_match = re.search(r"<!--\s*domain:\s*(\S+)\s*-->", text)
            domain = domain_match.group(1) if domain_match else "(global)"

            updated_match = re.search(r"<!--\s*Last updated:\s*(\S+)\s*-->", text)
            updated = updated_match.group(1) if updated_match else "(unknown)"

            files.append({"file": f.name, "title": title, "domain": domain, "updated": updated})
        return files

    semantic_files = scan_dir(semantic_dir)
    procedural_files = scan_dir(procedural_dir)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Memory Index",
        "_Auto-generated by consolidate.py. Read this first, then load only relevant files._",
        f"_Last generated: {now}_",
        "",
        "## Semantic Memory",
    ]

    if semantic_files:
        lines += [
            "| File | Title | Domain | Last Updated |",
            "|------|-------|--------|-------------|",
        ]
        for f in semantic_files:
            lines.append(f"| {f['file']} | {f['title']} | {f['domain']} | {f['updated']} |")
    else:
        lines.append("(none)")

    lines += ["", "## Procedural Memory"]

    if procedural_files:
        lines += [
            "| File | Title | Domain | Last Updated |",
            "|------|-------|--------|-------------|",
        ]
        for f in procedural_files:
            lines.append(f"| {f['file']} | {f['title']} | {f['domain']} | {f['updated']} |")
    else:
        lines.append("(none)")

    content = "\n".join(lines) + "\n"
    (memory_dir / "index.md").write_text(content)
    return content


def consolidate_today(
    episodic_dir: Path, semantic_dir: Path, apply: bool = True
) -> int | None:
    """Mini-consolidation of today's episodic entries.

    - Only includes entries with importance >= 3.
    - Writes a semantic summary when apply=True but does NOT archive the file.
    - Returns 0 if no qualifying entries are found, None otherwise.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    today_file = episodic_dir / f"{today}.md"

    if not today_file.exists():
        print(f"No episodic file for today ({today}).")
        return 0

    entries = extract_entries(today_file)
    high_entries = [e for e in entries if e.get("importance", 2) >= 3]

    if not high_entries:
        print(f"No entries with importance >= 3 found in {today_file.name}.")
        return 0

    summary = summarize_entries(high_entries)
    if not summary:
        print("No structured entries found.")
        return 0

    print(f"\nFound {len(high_entries)} high-importance entry(ies) for today.")
    print("\n--- Today's Summary Preview ---")
    print(summary)
    print("--- End Preview ---\n")

    if apply:
        summary_path = semantic_dir / f"consolidated-{today}-today.md"
        summary_path.write_text(summary)
        print(f"Summary saved to {summary_path}")
    else:
        print("Dry run. Use --apply to save the summary (no archiving for --today).")


def main():
    parser = argparse.ArgumentParser(description="Consolidate old episodic memories")
    parser.add_argument("--days", type=int, default=7, help="Age threshold in days (default: 7)")
    parser.add_argument("--domain", type=str, default=None, help="Only consolidate entries for this domain")
    parser.add_argument("--apply", action="store_true", help="Actually archive old files (default: dry run)")
    parser.add_argument("--today", action="store_true", help="Mini-consolidation of today's entries without archiving")
    args = parser.parse_args()

    # --today mode: consolidate today's high-importance entries without archiving
    if args.today:
        consolidate_today(EPISODIC_DIR, SEMANTIC_DIR, apply=True)
        generate_index(MEMORY_DIR)
        return

    old_files = get_old_episodic_files(args.days)

    if not old_files:
        print(f"No episodic files older than {args.days} days found.")
        if args.apply:
            generate_index(MEMORY_DIR)
            print(f"Index refreshed at {MEMORY_DIR / 'index.md'}")
        return

    print(f"Found {len(old_files)} file(s) older than {args.days} days:")
    for f in old_files:
        print(f"  {f.name}")

    all_entries = []
    for f in old_files:
        all_entries.extend(extract_entries(f))

    summary = summarize_entries(all_entries, domain_filter=args.domain)

    if not summary:
        print("No structured entries found to consolidate.")
        if args.apply:
            generate_index(MEMORY_DIR)
        return

    print(f"\nExtracted {len(all_entries)} entries.")
    print("\n--- Summary Preview ---")
    print(summary)
    print("--- End Preview ---\n")

    if not args.apply:
        print("Dry run complete. Use --apply to archive old files and save summary.")
        return

    # Save summary
    timestamp = datetime.now().strftime("%Y-%m-%d")
    suffix = f"-{args.domain}" if args.domain else ""
    summary_path = SEMANTIC_DIR / f"consolidated-{timestamp}{suffix}.md"
    summary_path.write_text(summary)
    print(f"Summary saved to {summary_path}")

    # Archive old files
    ARCHIVE_DIR.mkdir(exist_ok=True)
    for f in old_files:
        dest = ARCHIVE_DIR / f.name
        f.rename(dest)
        print(f"Archived {f.name}")

    # Always regenerate index after --apply
    generate_index(MEMORY_DIR)
    print(f"Index refreshed at {MEMORY_DIR / 'index.md'}")

    print("Consolidation complete.")


if __name__ == "__main__":
    main()
