"""Generic parameterized agent flow — run any prompt on a schedule."""
from __future__ import annotations

from prefect import flow

from flows.base import claude_task, write_episodic_task


@flow(name="generic-agent-flow", log_prints=True)
async def generic_flow(
    prompt: str,
    tools: list[str] | None = None,
    domain: str = "general",
    flow_name: str = "generic",
) -> str:
    """Run an arbitrary Claude prompt and log the result to episodic memory.

    Parameters
    ----------
    prompt:
        The full prompt to send to Claude.
    tools:
        Allowed tools (defaults to Read, Bash, Glob, Grep).
    domain:
        Memory domain for the episodic log entry.
    flow_name:
        Label used in the episodic log entry title.
    """
    effective_tools = tools if tools is not None else ["Read", "Bash", "Glob", "Grep"]
    result = await claude_task(prompt, tools=effective_tools)
    await write_episodic_task(result, domain=domain, task_name=flow_name)
    print(f"Flow '{flow_name}' complete ({len(result)} chars)")
    return result


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) < 2:
        print("Usage: python flows/generic.py '<prompt>'")
        sys.exit(1)

    asyncio.run(generic_flow(prompt=sys.argv[1]))
