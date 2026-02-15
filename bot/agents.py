import asyncio
import json
import logging

from bot.config import WORKING_DIR

logger = logging.getLogger(__name__)


async def run_claude(message: str, session_id: str | None = None) -> tuple[str, str | None]:
    """Run Claude Code CLI and return (response_text, session_id)."""
    cmd = ["claude"]
    if session_id:
        cmd.extend(["--resume", session_id])
    cmd.extend(["-p", message, "--output-format", "json"])

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode().strip()
        logger.error("Claude CLI error: %s", err)
        return f"Error from Claude Code:\n{err}", session_id

    try:
        data = json.loads(stdout.decode())
        text = data.get("result", "")
        new_session_id = data.get("session_id", session_id)
        return text, new_session_id
    except json.JSONDecodeError:
        # Fall back to raw text output
        return stdout.decode().strip(), session_id


async def run_opencode(message: str, session_id: str | None = None) -> tuple[str, str | None]:
    """Run opencode CLI and return (response_text, session_id)."""
    cmd = ["opencode", "run"]
    if session_id:
        cmd.extend(["--session", session_id])
    cmd.extend([message, "--format", "json", "-q"])

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode().strip()
        logger.error("opencode CLI error: %s", err)
        return f"Error from opencode:\n{err}", session_id

    # Parse NDJSON — collect text events and session ID
    text_parts = []
    new_session_id = session_id
    for line in stdout.decode().strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                text_parts.append(event["part"]["text"])
            if "sessionID" in event and event["sessionID"]:
                new_session_id = event["sessionID"]
        except (json.JSONDecodeError, KeyError):
            continue

    response = "".join(text_parts) if text_parts else stdout.decode().strip()
    return response, new_session_id


AGENTS = {
    "claude": run_claude,
    "opencode": run_opencode,
}


async def run_agent(agent: str, message: str, session_id: str | None = None) -> tuple[str, str | None]:
    """Route to the appropriate agent runner."""
    runner = AGENTS[agent]
    return await runner(message, session_id)
