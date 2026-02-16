"""Entry point: python -m tools.applyops"""
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so relative imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.applyops.cli import app

app()
