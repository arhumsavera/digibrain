"""Domain and item management routes."""
from __future__ import annotations

import json
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse

from ..db import get_conn
from ..templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def list_domains(request: Request):
    """List all domains."""
    db = get_conn()
    domains = db.execute("""
        SELECT d.id, d.name, d.description, d.keywords, d.created_at,
               COUNT(i.id) as item_count
        FROM domains d
        LEFT JOIN items i ON i.domain_id = d.id
        GROUP BY d.id
        ORDER BY d.created_at DESC
    """).fetchall()
    
    return templates.TemplateResponse("domains/list.html", {
        "request": request,
        "domains": domains
    })


def _parse_item(item) -> dict:
    """Convert a DB row to a dict with parsed data and tags."""
    d = dict(item)
    try:
        d["data_parsed"] = json.loads(d.get("data") or "{}")
    except Exception:
        d["data_parsed"] = {}
    try:
        d["tags_parsed"] = json.loads(d.get("tags") or "[]")
    except Exception:
        d["tags_parsed"] = []
    return d


@router.get("/{domain_id}", response_class=HTMLResponse)
async def view_domain(request: Request, domain_id: str):
    """View a specific domain and its items."""
    db = get_conn()

    domain = db.execute(
        "SELECT * FROM domains WHERE id = ?", (domain_id,)
    ).fetchone()

    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    rows = db.execute("""
        SELECT * FROM items
        WHERE domain_id = ?
        ORDER BY
            CASE status
                WHEN 'active' THEN 1
                WHEN 'pending' THEN 2
                ELSE 3
            END,
            created_at DESC
    """, (domain_id,)).fetchall()

    items = [_parse_item(r) for r in rows]
    all_tags = sorted({tag for item in items for tag in item["tags_parsed"]})

    return templates.TemplateResponse("domains/detail.html", {
        "request": request,
        "domain": domain,
        "items": items,
        "all_tags": all_tags,
    })


@router.post("/{domain_id}/items", response_class=HTMLResponse)
async def create_item(
    request: Request,
    domain_id: str,
    title: str = Form(...),
    item_type: str = Form("note"),
    status: str = Form("active")
):
    """Create a new item in a domain (HTMX form submission)."""
    db = get_conn()
    
    # Verify domain exists
    domain = db.execute(
        "SELECT id FROM domains WHERE id = ?", (domain_id,)
    ).fetchone()
    
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")
    
    cursor = db.execute("""
        INSERT INTO items (domain_id, title, type, status, data, tags)
        VALUES (?, ?, ?, ?, '{}', '[]')
    """, (domain_id, title, item_type, status))
    
    db.commit()

    # Return updated item list fragment
    rows = db.execute("""
        SELECT * FROM items
        WHERE domain_id = ?
        ORDER BY created_at DESC
    """, (domain_id,)).fetchall()

    items = [_parse_item(r) for r in rows]
    all_tags = sorted({tag for item in items for tag in item["tags_parsed"]})

    return templates.TemplateResponse("fragments/item_list.html", {
        "request": request,
        "items": items,
        "all_tags": all_tags,
    })


@router.post("/items/{item_id}/status", response_class=HTMLResponse)
async def update_item_status(
    request: Request,
    item_id: str,
    status: str = Form(...)
):
    """Update item status inline."""
    db = get_conn()
    
    db.execute(
        "UPDATE items SET status = ? WHERE id = ?",
        (status, item_id)
    )
    db.commit()
    
    # Return updated item card
    row = db.execute(
        "SELECT * FROM items WHERE id = ?", (item_id,)
    ).fetchone()

    return templates.TemplateResponse("fragments/item_row.html", {
        "request": request,
        "item": _parse_item(row),
    })
