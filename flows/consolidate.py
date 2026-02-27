"""Weekly episodic → semantic consolidation flow."""
from __future__ import annotations

import subprocess

from prefect import flow, task

from flows.base import WORKING_DIR, write_episodic_task


@task(name="run-consolidate")
def consolidate_task() -> str:
    """Run the consolidation script and return its output."""
    result = subprocess.run(
        ["uv", "run", "python", "scripts/consolidate.py", "--apply"],
        capture_output=True,
        text=True,
        cwd=str(WORKING_DIR),
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(f"Consolidation failed (rc={result.returncode}):\n{output}")
    return output.strip() or "Consolidation complete (no output)"


@flow(name="weekly-consolidation", log_prints=True)
async def consolidate_flow() -> str:
    """Archive old episodic entries and save semantic summaries."""
    output = consolidate_task()
    await write_episodic_task(output, domain="general", task_name="weekly-consolidation")
    print(f"Consolidation complete:\n{output}")
    return output


if __name__ == "__main__":
    import asyncio
    asyncio.run(consolidate_flow())
