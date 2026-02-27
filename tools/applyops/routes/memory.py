"""Memory browsing routes — semantic, episodic, procedural."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from ..templates import templates

router = APIRouter()

MEMORY_DIR = Path(__file__).parent.parent.parent.parent / "memory"


def _get_memory_files(memory_type: str) -> list[dict]:
    """Get all memory files of a given type."""
    dir_path = MEMORY_DIR / memory_type
    if not dir_path.exists():
        return []
    
    files = []
    for f in sorted(dir_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.startswith("_") or f.name.startswith("."):
            continue
        stat = f.stat()
        content = f.read_text()
        # Extract first line as preview
        preview = content.split("\n")[0][:100] if content else ""
        files.append({
            "name": f.name,
            "path": str(f.relative_to(MEMORY_DIR.parent)),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "size": f"{stat.st_size / 1024:.1f} KB",
            "preview": preview
        })
    return files


def _get_file_path(memory_type: str, filename: str) -> Path | None:
    """Get validated file path or None if invalid."""
    # Prevent directory traversal
    if ".." in filename or filename.startswith("/"):
        return None
    
    file_path = MEMORY_DIR / memory_type / filename
    
    # Security check - ensure path is within memory dir
    try:
        resolved_path = file_path.resolve()
        resolved_memory = MEMORY_DIR.resolve()
        if not str(resolved_path).startswith(str(resolved_memory)):
            return None
    except (OSError, ValueError):
        return None
    
    return file_path


@router.get("/", response_class=HTMLResponse)
async def memory_index(request: Request):
    """Memory browser landing page."""
    return templates.TemplateResponse("memory/index.html", {
        "request": request,
        "semantic": _get_memory_files("semantic"),
        "episodic": _get_memory_files("episodic"),
        "procedural": _get_memory_files("procedural")
    })


@router.get("/view/{memory_type}/{filename}", response_class=HTMLResponse)
async def view_memory(request: Request, memory_type: str, filename: str):
    """View a specific memory file."""
    file_path = _get_file_path(memory_type, filename)
    
    if not file_path:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = file_path.read_text()
    
    return templates.TemplateResponse("memory/view.html", {
        "request": request,
        "filename": filename,
        "memory_type": memory_type,
        "content": content
    })


@router.get("/edit/{memory_type}/{filename}", response_class=HTMLResponse)
async def edit_memory_form(request: Request, memory_type: str, filename: str):
    """Show edit form for a memory file."""
    file_path = _get_file_path(memory_type, filename)
    
    if not file_path:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    content = file_path.read_text()
    
    return templates.TemplateResponse("memory/edit.html", {
        "request": request,
        "filename": filename,
        "memory_type": memory_type,
        "content": content
    })


@router.post("/edit/{memory_type}/{filename}")
async def save_memory(
    request: Request,
    memory_type: str,
    filename: str,
    content: str = Form(...)
):
    """Save edited memory file."""
    file_path = _get_file_path(memory_type, filename)
    
    if not file_path:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Write new content
    file_path.write_text(content)
    
    # Redirect back to view
    return RedirectResponse(
        url=f"/memory/view/{memory_type}/{filename}",
        status_code=303
    )


@router.post("/create/{memory_type}")
async def create_memory(
    request: Request,
    memory_type: str,
    filename: str = Form(...),
    content: str = Form(default="")
):
    """Create a new memory file."""
    # Ensure filename ends with .md
    if not filename.endswith(".md"):
        filename += ".md"
    
    file_path = _get_file_path(memory_type, filename)
    
    if not file_path:
        raise HTTPException(status_code=403, detail="Invalid filename")
    
    if file_path.exists():
        raise HTTPException(status_code=409, detail="File already exists")
    
    # Ensure directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write content (default template if empty)
    if not content:
        content = f"# {filename.replace('.md', '')}\n\n"
    
    file_path.write_text(content)
    
    # Redirect to view
    return RedirectResponse(
        url=f"/memory/view/{memory_type}/{filename}",
        status_code=303
    )


@router.get("/search", response_class=HTMLResponse)
async def search_memory(request: Request, q: str = ""):
    """Search memory files (simple text search)."""
    results = []
    
    if q:
        for memory_type in ["semantic", "episodic", "procedural"]:
            dir_path = MEMORY_DIR / memory_type
            if not dir_path.exists():
                continue
            for f in dir_path.glob("*.md"):
                if f.name.startswith("_"):
                    continue
                content = f.read_text()
                if q.lower() in content.lower():
                    # Find context around match
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if q.lower() in line.lower():
                            context = "\n".join(lines[max(0,i-1):i+2])
                            results.append({
                                "file": f.name,
                                "type": memory_type,
                                "context": context[:200]
                            })
                            break
    
    return templates.TemplateResponse("memory/search.html", {
        "request": request,
        "query": q,
        "results": results
    })
