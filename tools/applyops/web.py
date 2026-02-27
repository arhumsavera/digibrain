"""
FastAPI web dashboard for Agent Memory Framework.
Run with: uv run applyops serve
"""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Paths
ROOT_DIR = Path(__file__).parent.parent.parent
STATIC_DIR = ROOT_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Agent Memory", description="Web interface for memory and agent management")

# Static files (HTMX, CSS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Import and include routers
from .routes import dashboard, memory, domains, chat

app.include_router(dashboard.router, prefix="", tags=["dashboard"])
app.include_router(memory.router, prefix="/memory", tags=["memory"])
app.include_router(domains.router, prefix="/domains", tags=["domains"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])

# Optional private extension
try:
    from .routes import jobs
    app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
except ImportError:
    pass


def run_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Run the web server."""
    import uvicorn
    print(f"Starting Agent Memory web dashboard on http://{host}:{port}")
    uvicorn.run(
        "tools.applyops.web:app",
        host=host,
        port=port,
        reload=reload
    )
