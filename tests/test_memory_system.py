"""Tests for memory system improvements.

Covers:
1. Importance scoring (1–5 field on episodic entries)
2. Vectorless tree index (memory/index.md)
3. Agent-triggered promotion (--today flag and consolidate_today())
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Add scripts/ to path so we can import consolidate directly
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import consolidate


# ---------------------------------------------------------------------------
# TestImportanceParsing
# ---------------------------------------------------------------------------

class TestImportanceParsing:
    """Tests for importance field extraction from episodic entry blocks."""

    def test_extracts_importance_field(self):
        block = "## 10:00 — test\n- **Importance**: 4\n- **Task**: something\n"
        assert consolidate.extract_importance(block) == 4

    def test_defaults_to_2_when_missing(self):
        block = "## 10:00 — test\n- **Task**: something\n- **Outcome**: done\n"
        assert consolidate.extract_importance(block) == 2

    def test_importance_range_clamped(self):
        block_low = "## 10:00 — test\n- **Importance**: 0\n"
        block_high = "## 10:00 — test\n- **Importance**: 6\n"
        assert consolidate.extract_importance(block_low) == 1
        assert consolidate.extract_importance(block_high) == 5

    def test_high_importance_flagged_in_summary(self):
        """importance=5 entry is flagged with ⚑ and sorted before lower-importance entries."""
        entries = [
            {
                "date": "2026-02-01",
                "task": "low task",
                "outcome": "done",
                "agent": "claude",
                "domain": "general",
                "importance": 1,
            },
            {
                "date": "2026-02-01",
                "task": "high task",
                "outcome": "critical fix",
                "agent": "claude",
                "domain": "general",
                "importance": 5,
            },
        ]
        summary = consolidate.summarize_entries(entries)
        lines = summary.split("\n")

        # At least one line should be flagged
        flagged = [l for l in lines if "⚑" in l]
        assert len(flagged) >= 1
        assert any("high task" in l for l in flagged)

        # High-importance entry should appear before low-importance entry
        high_pos = next(i for i, l in enumerate(lines) if "high task" in l)
        low_pos = next(i for i, l in enumerate(lines) if "low task" in l)
        assert high_pos < low_pos


# ---------------------------------------------------------------------------
# TestIndexGeneration
# ---------------------------------------------------------------------------

class TestIndexGeneration:
    """Tests for generate_index() producing memory/index.md."""

    @pytest.fixture
    def memory_dir(self, tmp_path):
        """Temp memory dir with empty semantic/ and procedural/ subdirs."""
        (tmp_path / "semantic").mkdir()
        (tmp_path / "procedural").mkdir()
        return tmp_path

    def test_index_created_from_semantic_files(self, memory_dir):
        (memory_dir / "semantic" / "user-prefs.md").write_text(
            "# User Preferences\n\n<!-- domain: general -->\n\n<!-- Last updated: 2026-02-20 -->\n"
        )
        content = consolidate.generate_index(memory_dir)
        assert "user-prefs.md" in content
        assert "User Preferences" in content

    def test_index_includes_procedural_files(self, memory_dir):
        (memory_dir / "procedural" / "response-style.md").write_text(
            "# Response Style Rules\n\n<!-- domain: general -->\n\n<!-- Last updated: 2026-02-27 -->\n"
        )
        content = consolidate.generate_index(memory_dir)
        assert "response-style.md" in content
        assert "Response Style Rules" in content
        assert "## Procedural Memory" in content

    def test_index_skips_template_files(self, memory_dir):
        (memory_dir / "semantic" / "_template.md").write_text("# Template\n")
        (memory_dir / "semantic" / "real-file.md").write_text("# Real File\n")
        content = consolidate.generate_index(memory_dir)
        assert "_template.md" not in content
        assert "real-file.md" in content

    def test_index_extracts_h1_title(self, memory_dir):
        (memory_dir / "semantic" / "fitness-goals.md").write_text(
            "# Fitness Goals\n\nSome content here.\n"
        )
        content = consolidate.generate_index(memory_dir)
        assert "Fitness Goals" in content

    def test_index_extracts_last_updated(self, memory_dir):
        (memory_dir / "semantic" / "test.md").write_text(
            "# Test\n\n<!-- Last updated: 2026-02-15 -->\n"
        )
        content = consolidate.generate_index(memory_dir)
        assert "2026-02-15" in content

    def test_index_extracts_domain_tag(self, memory_dir):
        (memory_dir / "semantic" / "fitness.md").write_text(
            "# Fitness\n\n<!-- domain: fitness -->\n"
        )
        content = consolidate.generate_index(memory_dir)
        assert "fitness" in content

    def test_index_empty_directory_graceful(self, memory_dir):
        content = consolidate.generate_index(memory_dir)
        assert "(none)" in content

    def test_consolidate_apply_regenerates_index(self, tmp_path, monkeypatch):
        """Running consolidate --apply (via main()) rewrites memory/index.md."""
        memory = tmp_path / "memory"
        episodic = memory / "episodic"
        semantic = memory / "semantic"
        archive = episodic / "archive"
        episodic.mkdir(parents=True)
        semantic.mkdir(parents=True)
        archive.mkdir(parents=True)

        # Create an episodic file old enough to be picked up by --days 1
        old_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        (episodic / f"{old_date}.md").write_text(
            f"# {old_date}\n\n## 10:00 — task\n"
            "- **Agent**: claude\n- **Domain**: general\n"
            "- **Task**: Some task\n- **Outcome**: Done\n"
            "- **Importance**: 2\n"
        )

        monkeypatch.setattr(consolidate, "MEMORY_DIR", memory)
        monkeypatch.setattr(consolidate, "EPISODIC_DIR", episodic)
        monkeypatch.setattr(consolidate, "SEMANTIC_DIR", semantic)
        monkeypatch.setattr(consolidate, "ARCHIVE_DIR", archive)
        monkeypatch.setattr(sys, "argv", ["consolidate.py", "--apply", "--days", "1"])

        consolidate.main()

        index_path = memory / "index.md"
        assert index_path.exists()
        assert "Memory Index" in index_path.read_text()


# ---------------------------------------------------------------------------
# TestTodayFlag
# ---------------------------------------------------------------------------

class TestTodayFlag:
    """Tests for consolidate_today() / --today mini-consolidation."""

    @pytest.fixture
    def memory_dir(self, tmp_path):
        episodic = tmp_path / "episodic"
        semantic = tmp_path / "semantic"
        episodic.mkdir()
        semantic.mkdir()
        return tmp_path

    def _today_file(self, memory_dir: Path, content: str) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        f = memory_dir / "episodic" / f"{today}.md"
        f.write_text(content)
        return f

    def test_today_flag_does_not_archive_file(self, memory_dir):
        """Today's episodic file must remain in episodic/ after consolidation."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_file = self._today_file(
            memory_dir,
            f"# {today}\n\n## 10:00 — important\n"
            "- **Agent**: claude\n- **Domain**: general\n"
            "- **Task**: Critical fix\n- **Outcome**: Fixed\n"
            "- **Importance**: 4\n",
        )

        consolidate.consolidate_today(
            memory_dir / "episodic", memory_dir / "semantic", apply=True
        )

        assert today_file.exists(), "Today's file must NOT be archived by --today"

    def test_today_flag_produces_summary(self, memory_dir):
        """--today writes a semantic summary file for today's high-importance entries."""
        today = datetime.now().strftime("%Y-%m-%d")
        self._today_file(
            memory_dir,
            f"# {today}\n\n## 10:00 — important\n"
            "- **Agent**: claude\n- **Domain**: general\n"
            "- **Task**: Important task\n- **Outcome**: Done\n"
            "- **Importance**: 4\n",
        )

        consolidate.consolidate_today(
            memory_dir / "episodic", memory_dir / "semantic", apply=True
        )

        summaries = list((memory_dir / "semantic").glob("*today*.md"))
        assert len(summaries) == 1
        assert "Important task" in summaries[0].read_text()

    def test_today_flag_filters_importance(self, memory_dir):
        """Only entries with importance >= 3 appear in the today summary."""
        today = datetime.now().strftime("%Y-%m-%d")
        self._today_file(
            memory_dir,
            f"# {today}\n\n"
            "## 10:00 — low\n"
            "- **Agent**: claude\n- **Domain**: general\n"
            "- **Task**: Routine task\n- **Outcome**: Done\n"
            "- **Importance**: 2\n\n"
            "## 11:00 — high\n"
            "- **Agent**: claude\n- **Domain**: general\n"
            "- **Task**: High priority task\n- **Outcome**: Fixed\n"
            "- **Importance**: 4\n",
        )

        consolidate.consolidate_today(
            memory_dir / "episodic", memory_dir / "semantic", apply=True
        )

        summaries = list((memory_dir / "semantic").glob("*today*.md"))
        assert len(summaries) == 1
        content = summaries[0].read_text()
        assert "High priority task" in content
        assert "Routine task" not in content

    def test_today_flag_noop_when_no_entries(self, memory_dir, capsys):
        """No today episodic file → prints informative message, no crash."""
        result = consolidate.consolidate_today(
            memory_dir / "episodic", memory_dir / "semantic", apply=True
        )

        captured = capsys.readouterr()
        assert result == 0
        assert "No episodic" in captured.out


# ---------------------------------------------------------------------------
# TestCLIIntegration  (subprocess via uv run)
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    """End-to-end CLI tests via subprocess."""

    ROOT = Path(__file__).parent.parent

    def test_consolidate_dry_run_shows_importance(self):
        """Dry run with --days 0 exits cleanly (importance-aware code path runs)."""
        import subprocess

        result = subprocess.run(
            ["uv", "run", "python", "scripts/consolidate.py", "--days", "0"],
            capture_output=True,
            text=True,
            cwd=self.ROOT,
        )
        assert result.returncode == 0

    def test_consolidate_apply_creates_index_file(self):
        """--apply with a very large --days threshold generates memory/index.md."""
        import subprocess

        result = subprocess.run(
            ["uv", "run", "python", "scripts/consolidate.py", "--days", "9999", "--apply"],
            capture_output=True,
            text=True,
            cwd=self.ROOT,
        )
        assert result.returncode == 0
        assert (self.ROOT / "memory" / "index.md").exists()
