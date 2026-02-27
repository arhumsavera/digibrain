"""Dashboard routes — main landing page and overview."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..db import DB_PATH
from ..templates import templates
from ..db import get_conn

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard view."""
    # Get recent activity from database
    db = get_conn()
    
    # Recent domains
    domains = db.execute(
        "SELECT id, name, description, created_at FROM domains ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    
    # Recent items (across all domains)
    recent_items = db.execute(
        """
        SELECT i.id, i.title, i.type, i.status, i.created_at, d.name as domain_name
        FROM items i
        JOIN domains d ON i.domain_id = d.id
        ORDER BY i.created_at DESC
        LIMIT 10
        """
    ).fetchall()
    
    # Domain stats
    domain_stats = db.execute(
        """
        SELECT d.name, COUNT(i.id) as item_count
        FROM domains d
        LEFT JOIN items i ON i.domain_id = d.id
        GROUP BY d.id
        ORDER BY item_count DESC
        """
    ).fetchall()
    
    # Recent memory files
    memory_dir = Path(__file__).parent.parent.parent.parent / "memory" / "episodic"
    recent_memories = []
    if memory_dir.exists():
        files = sorted(memory_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:5]:
            stat = f.stat()
            recent_memories.append({
                "name": f.name,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "size": f"{stat.st_size / 1024:.1f} KB"
            })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "domains": domains,
        "recent_items": recent_items,
        "domain_stats": domain_stats,
        "recent_memories": recent_memories,
        "db_path": str(DB_PATH)
    })


@router.get("/stats", response_class=HTMLResponse)
async def stats_fragment(request: Request):
    """HTMX fragment for live stats refresh."""
    db = get_conn()
    
    stats = {
        "total_domains": db.execute("SELECT COUNT(*) FROM domains").fetchone()[0],
        "total_items": db.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        "active_items": db.execute("SELECT COUNT(*) FROM items WHERE status = 'active'").fetchone()[0],
        "db_size": f"{DB_PATH.stat().st_size / (1024*1024):.2f} MB" if DB_PATH.exists() else "N/A"
    }
    
    return templates.TemplateResponse("fragments/stats.html", {
        "request": request,
        "stats": stats
    })
