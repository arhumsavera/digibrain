"""Shared Prefect tasks used by all flows."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from prefect import task

WORKING_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = WORKING_DIR / "memory" / "episodic"


@task(name="ollama-summarize", retries=1, retry_delay_seconds=5)
async def ollama_task(
    prompt: str,
    model: str = "llama3.2:1b",
    system: str = "You are a concise assistant. Return only the requested output, no preamble.",
    base_url: str = "http://localhost:11434",
) -> str:
    """Call local Ollama for fast, free text summarization — no API key needed."""
    import httpx

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{base_url}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]


@task(name="run-claude", retries=1, retry_delay_seconds=30)
async def claude_task(
    prompt: str,
    tools: list[str] | None = None,
    timeout: int = 180,
) -> str:
    """Run Claude CLI from a temp dir (no CLAUDE.md = no memory protocol overhead)."""
    import asyncio
    import os
    import json
    import tempfile

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
    ]
    if tools:
        cmd.extend(["--allowedTools", *tools])
    else:
        cmd.extend(["--allowedTools", "Bash"])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    # Run from a temp dir so Claude doesn't load CLAUDE.md / memory protocol
    with tempfile.TemporaryDirectory() as tmpdir:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir,
            env=env,
        )
        text_parts = []
        try:
            async with asyncio.timeout(timeout):
                async for raw_line in proc.stdout:
                    line = raw_line.decode().strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "result":
                        text_parts.append(event.get("result", ""))
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Timed out after {timeout}s"
        await proc.wait()

    return "".join(text_parts) or "(empty response)"


@task(name="persona-claude", retries=1, retry_delay_seconds=30)
async def persona_claude_task(
    persona_name: str,
    prompt: str,
    cwd: str | None = None,
    tools: list[str] | None = None,
    timeout: int = 300,
) -> str:
    """Run Claude CLI as a specific persona by injecting its soul file."""
    import asyncio
    import json
    import os
    from pathlib import Path

    agents_dir = Path.home() / ".claude" / "agents"
    soul_path = agents_dir / f"{persona_name}.md"

    soul = ""
    if soul_path.exists():
        content = soul_path.read_text()
        if content.startswith("---"):
            parts = content.split("---", 2)
            soul = parts[2].strip() if len(parts) >= 3 else content
        else:
            soul = content

    display_name = persona_name.replace("-", " ").title()
    full_prompt = (
        f"You are operating as: {display_name}\n\n{soul}\n\n---\n\n"
        f"Prefix every message section with [{display_name}].\n\nTask: {prompt}"
    ) if soul else prompt

    default_tools = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]
    cmd = [
        "claude", "-p", full_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", *(tools or default_tools),
    ]

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    run_dir = cwd or str(WORKING_DIR)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=run_dir,
        env=env,
        limit=2 * 1024 * 1024,
    )

    text_parts = []
    try:
        async with asyncio.timeout(timeout):
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "result":
                    text_parts.append(event.get("result", ""))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return f"[{display_name}] Timed out after {timeout}s"

    await proc.wait()
    return "".join(text_parts) or f"[{display_name}] (empty response)"


@task(name="write-episodic")
async def write_episodic_task(
    result: str,
    domain: str = "general",
    task_name: str = "flow-run",
) -> None:
    """Append a flow result to today's episodic memory log."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%H:%M")
    log_file = MEMORY_DIR / f"{date_str}.md"

    header = f"# {date_str}\n\n" if not log_file.exists() else ""
    outcome = result[:500] + "..." if len(result) > 500 else result
    entry = (
        f"{header}"
        f"## {time_str} — {task_name}\n"
        f"- **Agent**: claude\n"
        f"- **Domain**: {domain}\n"
        f"- **Task**: Scheduled flow: {task_name}\n"
        f"- **Outcome**: {outcome}\n\n"
    )

    with log_file.open("a") as f:
        f.write(entry)


@task(name="notify-telegram")
async def notify_telegram_task(text: str, title: str = "") -> None:
    """Send a flow result to all allowed Telegram users."""
    from dotenv import load_dotenv
    load_dotenv(WORKING_DIR / ".env")

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    user_ids_str = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")

    if not bot_token or not user_ids_str:
        print("Skipping Telegram notification: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USER_IDS not set")
        return

    from telegram import Bot
    from telegram.constants import ParseMode

    user_ids = [int(uid.strip()) for uid in user_ids_str.split(",") if uid.strip()]

    header = f"*{title}*\n\n" if title else ""
    message = header + text
    if len(message) > 4096:
        message = message[:4090] + "..."

    async with Bot(token=bot_token) as bot:
        for chat_id in user_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.MARKDOWN)
                print(f"Sent Telegram notification to {chat_id}")
            except Exception:
                # Retry as plain text if markdown parse fails
                try:
                    await bot.send_message(chat_id=chat_id, text=message)
                    print(f"Sent Telegram notification (plain text) to {chat_id}")
                except Exception as e:
                    print(f"Failed to send Telegram message to {chat_id}: {e}")


def run_flow(coro) -> None:
    """Helper to run an async flow coroutine from a sync context (e.g. CLI)."""
    asyncio.run(coro)
