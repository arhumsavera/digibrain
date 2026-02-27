#!/usr/bin/env python3
"""
Selectively forget memories across all memory types.

Usage:
    python scripts/forget.py list                          # show all memories
    python scripts/forget.py list --type semantic          # show only semantic
    python scripts/forget.py list --search "tailscale"     # search across all

    python scripts/forget.py forget --type episodic --all  # wipe all episodic logs
    python scripts/forget.py forget --file user-preferences.md  # delete specific file
    python scripts/forget.py forget --search "gmail"       # delete entries matching keyword
    python scripts/forget.py forget --type episodic --before 2026-02-10  # by date

    All forget commands are dry-run by default. Add --apply to execute.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "memory"
MEMORY_TYPES = ["semantic", "episodic", "procedural"]
ARCHIVE_DIR = MEMORY_DIR / "episodic" / "archive"


def get_memory_files(mem_type: str | None = None) -> list[tuple[str, Path]]:
    """Get all memory files, optionally filtered by type."""
    types = [mem_type] if mem_type else MEMORY_TYPES
    files = []

    for t in types:
        mem_dir = MEMORY_DIR / t
        if not mem_dir.exists():
            continue
        for f in sorted(mem_dir.glob("*.md")):
            if f.name.startswith("_") or f.name == ".gitkeep":
                continue
            files.append((t, f))

        # Also check archive for episodic
        if t == "episodic" and ARCHIVE_DIR.exists():
            for f in sorted(ARCHIVE_DIR.glob("*.md")):
                files.append(("episodic/archive", f))

    return files


def search_files(files: list[tuple[str, Path]], query: str) -> list[tuple[str, Path, list[str]]]:
    """Search memory files for a keyword, return matching files with matched lines."""
    results = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    for mem_type, filepath in files:
        content = filepath.read_text()
        matched_lines = [
            line.strip() for line in content.split("\n")
            if pattern.search(line)
        ]
        if matched_lines:
            results.append((mem_type, filepath, matched_lines))

    return results


def remove_matching_entries(filepath: Path, query: str) -> tuple[str, int]:
    """Remove episodic entries matching a query from a daily log. Returns new content and count removed."""
    content = filepath.read_text()
    blocks = re.split(r"(?=^## \d{2}:\d{2})", content, flags=re.MULTILINE)
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    header = blocks[0] if blocks and not blocks[0].strip().startswith("## ") else ""
    kept = []
    removed = 0

    for block in blocks:
        block_stripped = block.strip()
        if not block_stripped.startswith("## "):
            continue
        if pattern.search(block):
            removed += 1
        else:
            kept.append(block)

    new_content = header + "\n".join(kept) if kept else ""
    return new_content.strip(), removed


def get_file_domain(filepath: Path) -> str | None:
    """Extract domain tag from a memory file (<!-- domain: X --> comment)."""
    try:
        content = filepath.read_text()
        m = re.search(r"<!--\s*domain:\s*(\S+)\s*-->", content)
        return m.group(1) if m else None
    except (OSError, UnicodeDecodeError):
        return None


def filter_by_domain(files: list[tuple[str, Path]], domain: str) -> list[tuple[str, Path]]:
    """Filter memory files to those tagged with a specific domain."""
    result = []
    for mem_type, filepath in files:
        file_domain = get_file_domain(filepath)
        if file_domain == domain:
            result.append((mem_type, filepath))
        elif mem_type in ("episodic", "episodic/archive") and file_domain is None:
            # Episodic files may contain mixed-domain entries — include for entry-level filtering
            content = filepath.read_text()
            if f"**Domain**: {domain}" in content:
                result.append((mem_type, filepath))
    return result


def format_file_summary(mem_type: str, filepath: Path, max_preview: int = 80) -> str:
    """Format a one-line summary of a memory file."""
    content = filepath.read_text().strip()
    first_meaningful = ""
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("<!--"):
            first_meaningful = line[:max_preview]
            break

    size = len(content)
    return f"  [{mem_type:>16}] {filepath.name:<30} ({size:>5} bytes)  {first_meaningful}"


def cmd_list(args):
    """List all memories."""
    files = get_memory_files(args.type)
    if args.domain:
        files = filter_by_domain(files, args.domain)

    if not files:
        print("No memories found.")
        return

    if args.search:
        results = search_files(files, args.search)
        if not results:
            print(f'No memories matching "{args.search}".')
            return
        print(f'Memories matching "{args.search}":\n')
        for mem_type, filepath, matched_lines in results:
            print(f"  [{mem_type:>16}] {filepath.name}")
            for line in matched_lines[:3]:
                print(f"                      > {line[:100]}")
            if len(matched_lines) > 3:
                print(f"                      ... and {len(matched_lines) - 3} more matches")
            print()
    else:
        print(f"All memories ({len(files)} files):\n")
        for mem_type, filepath in files:
            print(format_file_summary(mem_type, filepath))
        print()


def cmd_forget(args):
    """Selectively forget memories."""
    if not args.file and not args.search and not args.all and not args.before:
        print("Specify what to forget: --file, --search, --before, or --all")
        print("Run with 'list' first to see what's available.")
        sys.exit(1)

    files = get_memory_files(args.type)
    if args.domain:
        files = filter_by_domain(files, args.domain)
    to_delete: list[tuple[str, Path]] = []
    to_edit: list[tuple[str, Path, str]] = []  # (type, path, query)

    if args.all:
        if not args.type:
            print("--all requires --type to prevent accidental full wipe.")
            print("Use --type semantic|episodic|procedural")
            sys.exit(1)
        to_delete = files

    elif args.file:
        to_delete = [(t, f) for t, f in files if f.name == args.file]
        if not to_delete:
            print(f'File "{args.file}" not found in memory.')
            sys.exit(1)

    elif args.before:
        try:
            cutoff = datetime.strptime(args.before, "%Y-%m-%d")
        except ValueError:
            print("--before must be YYYY-MM-DD format.")
            sys.exit(1)
        for mem_type, filepath in files:
            try:
                file_date = datetime.strptime(filepath.stem, "%Y-%m-%d")
                if file_date < cutoff:
                    to_delete.append((mem_type, filepath))
            except ValueError:
                continue

    elif args.search:
        results = search_files(files, args.search)
        if not results:
            print(f'No memories matching "{args.search}".')
            return

        for mem_type, filepath, matched_lines in results:
            # For episodic files, we can surgically remove matching entries
            if mem_type in ("episodic", "episodic/archive"):
                to_edit.append((mem_type, filepath, args.search))
            else:
                # For semantic/procedural, flag whole file for deletion
                to_delete.append((mem_type, filepath))

    # Preview
    if to_delete:
        print(f"Files to DELETE ({len(to_delete)}):\n")
        for mem_type, filepath in to_delete:
            print(format_file_summary(mem_type, filepath))
        print()

    if to_edit:
        print(f"Entries to REMOVE from episodic logs:\n")
        total_entries = 0
        for mem_type, filepath, query in to_edit:
            _, count = remove_matching_entries(filepath, query)
            total_entries += count
            print(f"  [{mem_type:>16}] {filepath.name}: {count} entry(ies) matching \"{query}\"")
        print(f"\n  Total: {total_entries} entry(ies)\n")

    if not to_delete and not to_edit:
        print("Nothing to forget.")
        return

    if not args.apply:
        print("Dry run. Add --apply to execute.")
        return

    # Execute deletions
    for mem_type, filepath in to_delete:
        filepath.unlink()
        print(f"Deleted: [{mem_type}] {filepath.name}")

    # Execute surgical edits
    for mem_type, filepath, query in to_edit:
        new_content, count = remove_matching_entries(filepath, query)
        if new_content:
            filepath.write_text(new_content + "\n")
            print(f"Removed {count} entry(ies) from [{mem_type}] {filepath.name}")
        else:
            filepath.unlink()
            print(f"Deleted: [{mem_type}] {filepath.name} (no entries remaining)")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Selectively forget memories")
    sub = parser.add_subparsers(dest="command")

    # list
    ls = sub.add_parser("list", help="List all memories")
    ls.add_argument("--type", choices=MEMORY_TYPES, help="Filter by memory type")
    ls.add_argument("--domain", help="Filter by domain tag")
    ls.add_argument("--search", help="Search for keyword across memories")

    # forget
    fg = sub.add_parser("forget", help="Selectively forget memories")
    fg.add_argument("--type", choices=MEMORY_TYPES, help="Filter by memory type")
    fg.add_argument("--domain", help="Filter by domain tag")
    fg.add_argument("--file", help="Delete a specific file by name")
    fg.add_argument("--search", help="Delete entries matching keyword")
    fg.add_argument("--before", help="Delete episodic files before date (YYYY-MM-DD)")
    fg.add_argument("--all", action="store_true", help="Delete all files of a type (requires --type)")
    fg.add_argument("--apply", action="store_true", help="Actually delete (default: dry run)")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "forget":
        cmd_forget(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
