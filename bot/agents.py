import asyncio
import json
import logging
import os
import re
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from bot.config import WORKING_DIR, AGENT_TIMEOUT

logger = logging.getLogger(__name__)

# Type for the progress callback
ProgressCallback = Callable[[str], Coroutine[Any, Any, None]]

# Where soul files live
AGENTS_DIR = Path.home() / ".claude" / "agents"

# Only match file types we'd actually send as Telegram documents
_SENDABLE_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".csv")
_PATH_RE = re.compile(r'(/[\w./-]+\.(?:' + '|'.join(ext.lstrip('.') for ext in _SENDABLE_EXTENSIONS) + r'))\b')

# Return type: (response_text, session_id, file_paths)
AgentResult = tuple[str, str | None, list[Path]]


def _scan_for_files(text: str) -> list[Path]:
    """Find unique sendable file paths in text that exist on disk."""
    seen = set()
    paths = []
    for match in _PATH_RE.finditer(text):
        p = Path(match.group(1))
        if p in seen:
            continue
        seen.add(p)
        if p.is_file() and p.stat().st_size > 0:
            paths.append(p)
    return paths


def list_personas() -> list[str]:
    """Return names of all available soul files."""
    if not AGENTS_DIR.exists():
        return []
    return sorted(p.stem for p in AGENTS_DIR.glob("*.md"))


def _load_soul(name: str) -> str | None:
    """Load and strip YAML frontmatter from a soul file."""
    path = AGENTS_DIR / f"{name}.md"
    if not path.exists():
        return None
    content = path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()


def _extract_subagent_turns(raw_output: list[str]) -> list[tuple[str, str]]:
    """Parse stream-json output for Task tool calls and their results.
    Returns list of (agent_name, result_text) tuples."""
    turns = []
    pending_name: str | None = None

    for line in raw_output:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        # Capture Task tool invocations to get the subagent name
        if etype == "assistant" and "message" in event:
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "Task":
                    inp = block.get("input", {})
                    pending_name = inp.get("name") or inp.get("subagent_type") or "subagent"

        # Capture the result that follows
        elif etype == "tool_result" and pending_name:
            for block in event.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        turns.append((pending_name, text))
            pending_name = None

    return turns


_DEFAULT_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"]


async def run_claude(
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
    tools: list[str] | None = None,
    timeout: int | None = None,
) -> AgentResult:
    """Run Claude Code CLI with streaming progress."""
    cmd = ["claude"]
    if session_id:
        cmd.extend(["--resume", session_id])
    cmd.extend([
        "-p", message,
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", *( tools if tools is not None else _DEFAULT_TOOLS),
    ])

    # Strip CLAUDECODE so Claude doesn't refuse to run nested inside another Claude session
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
        env=env,
        limit=1024 * 1024,  # 1MB line buffer — agents can dump large JSON
    )

    text_parts = []
    raw_output = []  # collect ALL output for file path scanning
    new_session_id = session_id
    last_progress_time = 0.0
    tool_uses = []

    effective_timeout = timeout if timeout is not None else AGENT_TIMEOUT

    try:
        async with asyncio.timeout(effective_timeout):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                raw_output.append(line)
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
        return f"Timed out after {effective_timeout}s", new_session_id, []

    await proc.wait()

    stderr_text = (await proc.stderr.read()).decode().strip()
    if proc.returncode != 0:
        logger.error("Claude CLI error (rc=%d): %s", proc.returncode, stderr_text or "(no stderr)")
        return "Agent error occurred.", new_session_id, []
    elif stderr_text:
        logger.debug("Claude CLI stderr (rc=0): %s", stderr_text)

    logger.info(
        "Claude done: rc=%d, lines=%d, tool_calls=%d, result_parts=%d",
        proc.returncode, len(raw_output), len(tool_uses), len(text_parts),
    )

    response = "".join(text_parts)
    if not response:
        logger.warning("Claude returned empty response (session=%s, tool_calls=%d)", new_session_id, len(tool_uses))

    # Scan all raw output for file paths (tool results, not just final text)
    all_text = "\n".join(raw_output)
    files = _scan_for_files(all_text)
    if files:
        logger.info("Detected files in output: %s", [str(f) for f in files])

    logger.debug("Claude response preview: %s", response[:200] if response else "(empty)")
    return response or "(empty response)", new_session_id, files


async def run_persona(
    persona_name: str,
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
    timeout: int | None = None,
) -> AgentResult:
    """Run Claude Code with a specific persona soul injected."""
    soul = _load_soul(persona_name)
    if soul is None:
        available = ", ".join(list_personas()) or "none"
        return f"No agent named '{persona_name}' found. Available: {available}", None, []

    display_name = persona_name.replace("-", " ").title()
    full_message = (
        f"You are operating as: {display_name}\n\n"
        f"{soul}\n\n"
        f"---\n\n"
        f"Prefix every response with [{display_name}]. "
        f"If you invoke subagents (via Task tool), include their outputs in your final response "
        f"prefixed with their agent name in brackets.\n\n"
        f"Task: {message}"
    )
    return await run_claude(full_message, session_id, on_progress, timeout=timeout)


async def create_persona(name: str, description: str) -> str:
    """Generate a soul file for a new agent via Claude and save it."""
    name = name.lower().replace(" ", "-")
    soul_path = AGENTS_DIR / f"{name}.md"

    prompt = (
        f"Create a Claude Code subagent soul file for an agent named '{name}'.\n"
        f"Description / purpose: {description}\n\n"
        f"Output ONLY the raw markdown content of the soul file — no explanation, no code fences.\n"
        f"Start with YAML frontmatter (---) containing: name, description (when to activate this agent), "
        f"appropriate tools, model: sonnet.\n"
        f"Then include these sections:\n"
        f"# Who I am — rich personality, voice, values, instincts\n"
        f"# My mission — one sentence\n"
        f"# How I think — numbered principles (5-7)\n"
        f"# What I always do (no permission needed)\n"
        f"# What I ask before doing\n"
        f"# How I hand off — output format when done\n"
        f"Make the personality distinctive and opinionated. Tools should match the domain."
    )

    result, _, _ = await run_claude(prompt)

    # Strip any accidental code fences
    content = result.strip()
    for fence in ("```markdown", "```md", "```"):
        if fence in content:
            parts = content.split(fence)
            if len(parts) >= 3:
                content = parts[1].strip()
                break

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(content)
    logger.info("Created persona: %s at %s", name, soul_path)
    return content


async def run_gemini(
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
    timeout: int | None = None,
) -> AgentResult:
    """Run Gemini CLI with streaming progress."""
    cmd = ["gemini", "-p", message, "--output-format", "stream-json", "--yolo"]
    if session_id:
        cmd.extend(["--resume", session_id])

    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKING_DIR,
        limit=1024 * 1024,
    )

    text_parts = []
    raw_output = []
    new_session_id = session_id
    last_progress_time = 0.0
    tool_count = 0

    effective_timeout = timeout if timeout is not None else AGENT_TIMEOUT

    try:
        async with asyncio.timeout(effective_timeout):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                raw_output.append(line)
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # Session ID from init event
                if etype == "init":
                    new_session_id = event.get("session_id", new_session_id)

                # Accumulate streaming assistant text
                elif etype == "message" and event.get("role") == "assistant" and event.get("delta"):
                    text_parts.append(event.get("content", ""))

                # Track tool use for progress
                elif etype == "tool_use":
                    tool_count += 1
                    tool_name = event.get("tool_name", "tool")
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
        return f"Timed out after {effective_timeout}s", new_session_id, []

    await proc.wait()

    stderr_text = (await proc.stderr.read()).decode().strip()
    if proc.returncode != 0:
        logger.error("Gemini CLI error (rc=%d): %s", proc.returncode, stderr_text or "(no stderr)")
        return "Agent error occurred.", new_session_id, []
    elif stderr_text:
        logger.debug("Gemini CLI stderr (rc=0): %s", stderr_text)

    logger.info(
        "Gemini done: rc=%d, lines=%d, tool_calls=%d, text_parts=%d",
        proc.returncode, len(raw_output), tool_count, len(text_parts),
    )

    response = "".join(text_parts)
    if not response:
        logger.warning("Gemini returned empty response (session=%s, tool_calls=%d)", new_session_id, tool_count)

    all_text = "\n".join(raw_output)
    files = _scan_for_files(all_text)
    if files:
        logger.info("Detected files in output: %s", [str(f) for f in files])

    logger.debug("Gemini response preview: %s", response[:200] if response else "(empty)")
    return response or "(empty response)", new_session_id, files


async def run_opencode(
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> AgentResult:
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
        limit=1024 * 1024,  # 1MB line buffer — opencode dumps large JSON
    )

    text_parts = []
    raw_output = []  # collect ALL output for file path scanning
    new_session_id = session_id
    last_progress_time = 0.0
    tool_count = 0

    try:
        async with asyncio.timeout(AGENT_TIMEOUT):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                raw_output.append(line)
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
        return f"Timed out after {AGENT_TIMEOUT}s", new_session_id, []

    await proc.wait()

    stderr_text = (await proc.stderr.read()).decode().strip()
    if proc.returncode != 0:
        logger.error("opencode CLI error (rc=%d): %s", proc.returncode, stderr_text or "(no stderr)")
        return "Agent error occurred.", new_session_id, []
    elif stderr_text:
        logger.debug("opencode CLI stderr (rc=0): %s", stderr_text)

    logger.info(
        "opencode done: rc=%d, lines=%d, tool_calls=%d, text_parts=%d",
        proc.returncode, len(raw_output), tool_count, len(text_parts),
    )

    response = "".join(text_parts)
    if not response:
        logger.warning("opencode returned empty response (session=%s, tool_calls=%d)", new_session_id, tool_count)

    # Scan all raw output for file paths
    all_text = "\n".join(raw_output)
    files = _scan_for_files(all_text)
    if files:
        logger.info("Detected files in output: %s", [str(f) for f in files])

    logger.debug("opencode response preview: %s", response[:200] if response else "(empty)")
    return response or "(empty response)", new_session_id, files


AGENTS = {
    "claude": run_claude,
    "opencode": run_opencode,
    "gemini": run_gemini,
}


async def run_agent(
    agent: str,
    message: str,
    session_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> AgentResult:
    """Route to the appropriate agent runner."""
    runner = AGENTS[agent]
    return await runner(message, session_id, on_progress)
