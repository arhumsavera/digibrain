"""
Resume validation — diff tailored versions against the base to catch hallucinations.

Compares structured JSON resumes and flags:
- New companies, titles, schools not in base
- New skills not in base
- New dates/timelines not in base
- New metrics/numbers not in base
- Text quality issues (first person, weak verbs, etc.)
"""
from __future__ import annotations

import json
import re


def _extract_strings(obj, depth: int = 0) -> set[str]:
    """Recursively extract all string values from a JSON structure."""
    strings = set()
    if isinstance(obj, str):
        strings.add(obj.strip().lower())
    elif isinstance(obj, list):
        for item in obj:
            strings.update(_extract_strings(item, depth + 1))
    elif isinstance(obj, dict):
        for v in obj.values():
            strings.update(_extract_strings(v, depth + 1))
    return strings


def _extract_entities(data: dict) -> dict[str, set[str]]:
    """Extract named entities from resume JSON by category."""
    entities: dict[str, set[str]] = {
        "companies": set(),
        "titles": set(),
        "schools": set(),
        "degrees": set(),
        "dates": set(),
        "skills": set(),
        "numbers": set(),
    }

    for job in data.get("experience", []):
        if job.get("company"):
            entities["companies"].add(job["company"].lower())
        if job.get("title"):
            entities["titles"].add(job["title"].lower())
        if job.get("dates"):
            entities["dates"].add(job["dates"].lower())
        # Extract numbers from detail bullets
        for detail in job.get("details", []):
            for num in re.findall(r'\d+[%+]?|\$[\d,.]+[kKmMbB]?', detail):
                entities["numbers"].add(num)

    for edu in data.get("education", []):
        if edu.get("school"):
            entities["schools"].add(edu["school"].lower())
        if edu.get("degree"):
            entities["degrees"].add(edu["degree"].lower())
        if edu.get("dates"):
            entities["dates"].add(edu["dates"].lower())

    for skill_group in data.get("skills", []):
        for item in skill_group.get("items", []):
            entities["skills"].add(item.lower())

    return entities


def _check_text_quality(data: dict) -> list[str]:
    """Check resume text for common quality issues."""
    issues = []

    # Collect all detail bullets
    bullets = []
    for job in data.get("experience", []):
        bullets.extend(job.get("details", []))
    for proj in data.get("projects", []):
        bullets.extend(proj.get("details", []))

    # First person check
    first_person = re.compile(r'\b(I|my|me|mine|myself)\b', re.IGNORECASE)
    for bullet in bullets:
        if first_person.search(bullet):
            issues.append(f"First person detected: \"{bullet[:60]}...\"")

    # Weak verb starters
    weak_starts = {"helped", "assisted", "worked on", "was responsible for",
                   "participated in", "involved in", "tasked with"}
    for bullet in bullets:
        lower = bullet.lower().strip()
        for weak in weak_starts:
            if lower.startswith(weak):
                issues.append(f"Weak verb start \"{weak}\": \"{bullet[:60]}...\"")

    # Overly long bullets
    for bullet in bullets:
        if len(bullet) > 200:
            issues.append(f"Bullet too long ({len(bullet)} chars): \"{bullet[:50]}...\"")

    # Empty sections that should have content
    if not data.get("summary"):
        issues.append("Missing summary section")
    if not data.get("experience"):
        issues.append("Missing experience section")

    return issues


def validate_against_base(base_json: str, tailored_json: str) -> dict:
    """
    Compare a tailored resume against the base. Returns a dict with:
    - additions: new entities not in base (potential hallucinations)
    - removals: entities dropped from base
    - quality: text quality issues
    - ok: True if no additions found (safe)
    """
    base = json.loads(base_json)
    tailored = json.loads(tailored_json)

    base_entities = _extract_entities(base)
    tailored_entities = _extract_entities(tailored)

    additions: dict[str, list[str]] = {}
    removals: dict[str, list[str]] = {}

    for category in base_entities:
        added = tailored_entities[category] - base_entities[category]
        removed = base_entities[category] - tailored_entities[category]
        if added:
            additions[category] = sorted(added)
        if removed:
            removals[category] = sorted(removed)

    # Check for new detail bullets with numbers not in base
    base_numbers = set()
    for job in base.get("experience", []):
        for detail in job.get("details", []):
            for num in re.findall(r'\d+[%+]?|\$[\d,.]+[kKmMbB]?', detail):
                base_numbers.add(num)

    tailored_numbers = set()
    for job in tailored.get("experience", []):
        for detail in job.get("details", []):
            for num in re.findall(r'\d+[%+]?|\$[\d,.]+[kKmMbB]?', detail):
                tailored_numbers.add(num)

    new_numbers = tailored_numbers - base_numbers
    if new_numbers:
        additions["new_metrics"] = sorted(new_numbers)

    quality = _check_text_quality(tailored)

    return {
        "additions": additions,
        "removals": removals,
        "quality": quality,
        "ok": len(additions) == 0,
    }


def format_validation(result: dict) -> str:
    """Format validation results as human-readable text."""
    lines = []

    if result["ok"] and not result["quality"]:
        lines.append("PASS — No hallucinations detected, no quality issues.")
        if result["removals"]:
            lines.append("\nRemoved from base (intentional?):")
            for cat, items in result["removals"].items():
                lines.append(f"  {cat}: {', '.join(items)}")
        return "\n".join(lines)

    if result["additions"]:
        lines.append("WARN — New claims not in base resume:")
        for cat, items in result["additions"].items():
            label = cat.replace("_", " ").title()
            lines.append(f"  {label}: {', '.join(items)}")
        lines.append("")
        lines.append("These may be hallucinations. Verify each one before using.")

    if result["removals"]:
        lines.append("\nRemoved from base:")
        for cat, items in result["removals"].items():
            lines.append(f"  {cat}: {', '.join(items)}")

    if result["quality"]:
        lines.append("\nText quality issues:")
        for issue in result["quality"]:
            lines.append(f"  - {issue}")

    return "\n".join(lines)
