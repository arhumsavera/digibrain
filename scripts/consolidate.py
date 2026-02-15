#!/usr/bin/env python3
"""
Consolidate old episodic memories into semantic summaries.

Usage:
    python scripts/consolidate.py              # dry run (default)
    python scripts/consolidate.py --apply      # actually move/archive
    python scripts/consolidate.py --days 14    # change age threshold (default: 7)
"""

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
EPISODIC_DIR = MEMORY_DIR / "episodic"
SEMANTIC_DIR = MEMORY_DIR / "semantic"
ARCHIVE_DIR = EPISODIC_DIR / "archive"


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

        entry = {"raw": block, "date": filepath.stem}

        # Extract fields
        for line in block.split("\n"):
            line = line.strip("- ")
            if line.startswith("**Task**:"):
                entry["task"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Outcome**:"):
                entry["outcome"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Agent**:"):
                entry["agent"] = line.split(":", 1)[1].strip()

        if "task" in entry or "outcome" in entry:
            entries.append(entry)

    return entries


def summarize_entries(entries: list[dict]) -> str:
    """Create a plain-text summary of episodic entries."""
    if not entries:
        return ""

    lines = ["# Consolidated Episodic Summary", ""]
    dates = sorted(set(e["date"] for e in entries))
    lines.append(f"Period: {dates[0]} to {dates[-1]}")
    lines.append(f"Total entries: {len(entries)}")
    lines.append("")

    for entry in entries:
        task = entry.get("task", "unknown task")
        outcome = entry.get("outcome", "no outcome recorded")
        agent = entry.get("agent", "unknown")
        lines.append(f"- [{entry['date']}] ({agent}) {task} -> {outcome}")

    lines.append("")
    lines.append(f"<!-- Consolidated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Consolidate old episodic memories")
    parser.add_argument("--days", type=int, default=7, help="Age threshold in days (default: 7)")
    parser.add_argument("--apply", action="store_true", help="Actually archive old files (default: dry run)")
    args = parser.parse_args()

    old_files = get_old_episodic_files(args.days)

    if not old_files:
        print(f"No episodic files older than {args.days} days found.")
        return

    print(f"Found {len(old_files)} file(s) older than {args.days} days:")
    for f in old_files:
        print(f"  {f.name}")

    # Extract and summarize
    all_entries = []
    for f in old_files:
        all_entries.extend(extract_entries(f))

    summary = summarize_entries(all_entries)

    if not summary:
        print("No structured entries found to consolidate.")
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
    summary_path = SEMANTIC_DIR / f"consolidated-{timestamp}.md"
    summary_path.write_text(summary)
    print(f"Summary saved to {summary_path}")

    # Archive old files
    ARCHIVE_DIR.mkdir(exist_ok=True)
    for f in old_files:
        dest = ARCHIVE_DIR / f.name
        f.rename(dest)
        print(f"Archived {f.name}")

    print("Consolidation complete.")


if __name__ == "__main__":
    main()
