"""CLI smoke tests — verify commands parse and run via subprocess."""
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def run_cli(*args) -> tuple[int, str]:
    result = subprocess.run(
        ["uv", "run", "applyops"] + list(args),
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    return result.returncode, (result.stdout + result.stderr).strip()


class TestCLIDomain:
    def test_domain_list(self):
        rc, out = run_cli("domain", "list")
        assert rc == 0

    def test_domain_detect(self):
        rc, out = run_cli("domain", "detect", "update my resume for jobs")
        assert rc == 0
        assert "jobs" in out.lower()

    def test_domain_show(self):
        rc, out = run_cli("domain", "show", "jobs")
        assert rc == 0
        assert "jobs" in out.lower()


class TestCLIItem:
    def test_item_list(self):
        rc, out = run_cli("item", "list")
        assert rc == 0


class TestCLIExisting:
    def test_stats(self):
        rc, out = run_cli("stats")
        if rc == 2 and "No such command 'stats'" in out:
            pytest.skip("Private extension 'stats' not available")
        assert rc == 0
        assert "tracker stats" in out.lower()

    def test_help(self):
        rc, out = run_cli("--help")
        assert rc == 0
        assert "domain" in out.lower()
        assert "item" in out.lower()
        # Optional commands
        if "company" in out.lower():
            assert "job" in out.lower()


class TestScripts:
    def test_forget_list(self):
        result = subprocess.run(
            ["python", "scripts/forget.py", "list"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_consolidate_dry(self):
        result = subprocess.run(
            ["python", "scripts/consolidate.py", "--days", "999"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_forget_domain_flag(self):
        result = subprocess.run(
            ["python", "scripts/forget.py", "list", "--domain", "jobs"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

    def test_consolidate_domain_flag(self):
        result = subprocess.run(
            ["python", "scripts/consolidate.py", "--days", "999", "--domain", "jobs"],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
