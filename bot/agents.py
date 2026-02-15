import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from bot.config import WORKING_DIR, AGENT_TIMEOUT

logger = logging.getLogger(__name__)

# Type for the progress callback
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]]


async def run_claude(
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, str | None]:
    """Run Claude Code CLI with streaming progress."""
    cmd = ["claude"]
    if session_id:
        cmd.extend(["--resume", session_id])
    cmd.extend([
        "-p", message,
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
    ])

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
    )

    text_parts = []
    new_session_id = session_id
    last_progress_time = 0.0
    tool_uses = []

    try:
        async with asyncio.timeout(AGENT_TIMEOUT):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Capture session ID
                if "session_id" in event:
                    new_session_id = event["session_id"]

                etype = event.get("type", "")

                # Collect final text
                if etype == "result":
                    text_parts.append(event.get("result", ""))

                # Track tool use for progress
                elif etype == "assistant" and "message" in event:
                    msg = event["message"]
                    for block in msg.get("content", []):
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "tool")
                            tool_uses.append(tool_name)

                            if on_progress and time.time() - last_progress_time > 3:
                                await on_progress(f"Using {tool_name}...")
                                last_progress_time = time.time()

                elif etype == "tool_result":
                    if on_progress and time.time() - last_progress_time > 3:
                        count = len(tool_uses)
                        await on_progress(f"Working... ({count} tool call{'s' if count != 1 else ''} so far)")
                        last_progress_time = time.time()

    except TimeoutError:
        proc.kill()
        await proc.wait()
        return f"Timed out after {AGENT_TIMEOUT}s", new_session_id

    await proc.wait()

    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode().strip()
        logger.error("Claude CLI error: %s", stderr)
        return "Agent error occurred.", new_session_id

    response = "".join(text_parts)
    return response or "(empty response)", new_session_id


async def run_opencode(
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, str | None]:
    """Run opencode CLI with streaming progress."""
    cmd = ["opencode", "run", message, "--format", "json"]
    if session_id:
        cmd.extend(["--session", session_id])

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
    )

    text_parts = []
    new_session_id = session_id
    last_progress_time = 0.0
    tool_count = 0

    try:
        async with asyncio.timeout(AGENT_TIMEOUT):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # Capture session ID
                if "sessionID" in event and event["sessionID"]:
                    new_session_id = event["sessionID"]

                # Collect text
                if etype == "text":
                    text_parts.append(event.get("part", {}).get("text", ""))

                # Track tool use for progress
                elif etype == "tool_use":
                    tool_count += 1
                    tool_name = event.get("part", {}).get("name", "tool")
                    if on_progress and time.time() - last_progress_time > 3:
                        await on_progress(f"Using {tool_name}...")
                        last_progress_time = time.time()

                elif etype == "tool_result":
                    if on_progress and time.time() - last_progress_time > 3:
                        await on_progress(f"Working... ({tool_count} tool call{'s' if tool_count != 1 else ''} so far)")
                        last_progress_time = time.time()

    except TimeoutError:
        proc.kill()
        await proc.wait()
        return f"Timed out after {AGENT_TIMEOUT}s", new_session_id

    await proc.wait()

    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode().strip()
        stdout_raw = "".join(text_parts)
        logger.error("opencode CLI error (rc=%d): %s", proc.returncode, stderr or stdout_raw)
        return "Agent error occurred.", new_session_id

    response = "".join(text_parts)
    return response or "(empty response)", new_session_id


AGENTS = {
    "claude": run_claude,
    "opencode": run_opencode,
}


async def run_agent(
    agent: str,
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[str, str | None]:
    """Route to the appropriate agent runner."""
    runner = AGENTS[agent]
    return await runner(message, session_id, on_progress)
