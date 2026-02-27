"""Agent chat interface routes."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from bot.agents import run_agent, AGENTS
from ..templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()

# session key → agent session_id
_chat_sessions: dict[str, str] = {}


@router.get("/", response_class=HTMLResponse)
async def chat_interface(request: Request):
    return templates.TemplateResponse("chat/index.html", {
        "request": request,
        "agents": list(AGENTS.keys()),
    })


@router.get("/stream")
async def stream_response(message: str = "", agent: str = "opencode", session: str = ""):
    """SSE endpoint — named events: progress | response | files | error | done.
    Keepalive comment lines are sent every 5s so the connection stays alive.
    """
    if agent not in AGENTS:
        async def _err():
            yield f"event: error\ndata: Unknown agent '{agent}'\n\n"
            yield "event: done\ndata: \n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    session_id = _chat_sessions.get(session) if session else None

    async def event_generator() -> AsyncGenerator[str, None]:
        nonlocal session_id

        # Flush an immediate keepalive so the browser knows the connection is live
        yield ": connected\n\n"

        progress_queue: asyncio.Queue[str] = asyncio.Queue()
        result: dict = {"text": "", "files": [], "done": False, "error": None}

        async def on_progress(msg: str) -> None:
            await progress_queue.put(msg)

        async def run() -> None:
            try:
                text, new_sid, files = await run_agent(agent, message, session_id, on_progress)
                result["text"] = text
                result["files"] = files
                if new_sid and session:
                    _chat_sessions[session] = new_sid
            except Exception as e:
                logger.exception("Agent error in chat stream")
                result["error"] = str(e)
            finally:
                result["done"] = True

        task = asyncio.create_task(run())
        last_keepalive = time.monotonic()

        while not result["done"]:
            # Drain any progress events
            try:
                msg = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                yield f"event: progress\ndata: {msg}\n\n"
            except asyncio.TimeoutError:
                pass

            # Keepalive every 5s to prevent proxy/browser timeouts
            if time.monotonic() - last_keepalive > 5:
                yield ": keepalive\n\n"
                last_keepalive = time.monotonic()

        await task

        if result["error"]:
            yield f"event: error\ndata: {result['error']}\n\n"
        else:
            yield f"event: response\ndata: {json.dumps(result['text'])}\n\n"
            if result["files"]:
                names = [f.name for f in result["files"]]
                yield f"event: files\ndata: {json.dumps(names)}\n\n"

        yield "event: done\ndata: \n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
