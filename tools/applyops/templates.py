"""Shared template instance for web routes."""
from __future__ import annotations

from pathlib import Path
from fastapi.templating import Jinja2Templates

ROOT_DIR = Path(__file__).parent.parent.parent
TEMPLATES_DIR = ROOT_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
