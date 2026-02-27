"""Tests for run_gemini() in bot/agents.py.

Uses mock subprocesses to avoid live Gemini CLI calls.
Tests cover: text extraction, session ID, tool tracking, resumption, timeout, error.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.agents import run_gemini, AGENTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream(*events: dict) -> list[bytes]:
    """Encode dicts as newline-terminated JSON bytes, as the CLI would produce."""
    return [json.dumps(e).encode() + b"\n" for e in events]


class _MockProc:
    """Minimal asyncio.Process stand-in."""

    def __init__(self, lines: list[bytes], returncode: int = 0, stderr: bytes = b""):
        self._lines = lines
        self.returncode = returncode
        self._stderr = stderr
        self.stdout = _AsyncIterLines(lines)
        self.stderr = _AsyncReadable(stderr)

    async def wait(self):
        pass

    def kill(self):
        pass


class _AsyncIterLines:
    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class _AsyncReadable:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self) -> bytes:
        return self._data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_OUTPUT = _make_stream(
    {"type": "init", "session_id": "abc-123", "model": "gemini-3"},
    {"type": "message", "role": "user", "content": "hello"},
    {"type": "message", "role": "assistant", "content": "Hello there!", "delta": True},
    {"type": "message", "role": "assistant", "content": " How can I help?", "delta": True},
    {"type": "result", "status": "success", "stats": {"tool_calls": 0}},
)

TOOL_OUTPUT = _make_stream(
    {"type": "init", "session_id": "def-456", "model": "gemini-3"},
    {"type": "message", "role": "user", "content": "run ls"},
    {"type": "message", "role": "assistant", "content": "Running ls for you.", "delta": True},
    {"type": "tool_use", "tool_name": "run_shell_command", "tool_id": "t1", "parameters": {"command": "ls"}},
    {"type": "tool_result", "tool_id": "t1", "status": "success", "output": "file1.txt\nfile2.txt"},
    {"type": "message", "role": "assistant", "content": "Done.", "delta": True},
    {"type": "result", "status": "success", "stats": {"tool_calls": 1}},
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_gemini_registered_in_agents():
    assert "gemini" in AGENTS
    assert AGENTS["gemini"] is run_gemini


def test_simple_response_text():
    """Text from delta message events is concatenated correctly."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, session_id, files = asyncio.run(run_gemini("hello"))

    assert response == "Hello there! How can I help?"
    assert session_id == "abc-123"
    assert files == []


def test_session_id_from_init():
    """Session ID is read from the init event."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        _, session_id, _ = asyncio.run(run_gemini("hello"))

    assert session_id == "abc-123"


def test_resume_flag_passed():
    """--resume <id> is appended when session_id is provided."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        asyncio.run(run_gemini("hello", session_id="prev-session-id"))

    cmd = mock_exec.call_args[0]
    assert "--resume" in cmd
    assert "prev-session-id" in cmd


def test_no_resume_flag_without_session():
    """--resume is not passed when session_id is None."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        asyncio.run(run_gemini("hello"))

    cmd = mock_exec.call_args[0]
    assert "--resume" not in cmd


def test_yolo_flag_always_present():
    """--yolo is always passed (non-interactive approval)."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        asyncio.run(run_gemini("hello"))

    cmd = mock_exec.call_args[0]
    assert "--yolo" in cmd


def test_stream_json_output_format():
    """--output-format stream-json is always passed."""
    proc = _MockProc(SIMPLE_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        asyncio.run(run_gemini("hello"))

    cmd = mock_exec.call_args[0]
    assert "--output-format" in cmd
    idx = list(cmd).index("--output-format")
    assert cmd[idx + 1] == "stream-json"


def test_tool_use_progress_callback():
    """Progress callback is invoked when tool_use events arrive."""
    proc = _MockProc(TOOL_OUTPUT)
    progress_calls = []

    async def on_progress(msg: str):
        progress_calls.append(msg)

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch("bot.agents.time") as mock_time:
            mock_time.time.return_value = 100.0  # always > last_progress_time + 3
            asyncio.run(run_gemini("run ls", on_progress=on_progress))

    tool_progress = [c for c in progress_calls if "run_shell_command" in c]
    assert len(tool_progress) >= 1


def test_tool_output_text_accumulated():
    """Text from multiple delta events is joined in order."""
    proc = _MockProc(TOOL_OUTPUT)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, _, _ = asyncio.run(run_gemini("run ls"))

    assert "Running ls for you." in response
    assert "Done." in response


def test_non_delta_messages_ignored():
    """Non-delta assistant messages (role=user echo etc.) are not included."""
    output = _make_stream(
        {"type": "init", "session_id": "x", "model": "gemini-3"},
        {"type": "message", "role": "user", "content": "this is user echo"},
        {"type": "message", "role": "assistant", "content": "actual reply", "delta": True},
        {"type": "result", "status": "success", "stats": {}},
    )
    proc = _MockProc(output)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, _, _ = asyncio.run(run_gemini("hello"))

    assert "this is user echo" not in response
    assert response == "actual reply"


def test_error_return_on_nonzero_exit():
    """Non-zero exit code returns error string, not raw output."""
    proc = _MockProc(SIMPLE_OUTPUT, returncode=1, stderr=b"something went wrong")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, _, files = asyncio.run(run_gemini("hello"))

    assert response == "Agent error occurred."
    assert files == []


def test_timeout_returns_timeout_message():
    """TimeoutError kills the process and returns a timeout message."""
    async def _slow_iter():
        await asyncio.sleep(9999)
        yield b""

    class _SlowProc(_MockProc):
        def __init__(self):
            super().__init__([], returncode=0)
            self.stdout = _SlowIter()
            self._killed = False

        def kill(self):
            self._killed = True

    class _SlowIter:
        def __aiter__(self):
            return self

        async def __anext__(self) -> bytes:
            await asyncio.sleep(9999)
            raise StopAsyncIteration

    proc = _SlowProc()
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, _, _ = asyncio.run(run_gemini("hello", timeout=1))

    assert "Timed out" in response
    assert proc._killed


def test_invalid_json_lines_skipped():
    """Non-JSON lines in stdout don't crash the runner."""
    output = [
        b"not json at all\n",
        json.dumps({"type": "init", "session_id": "xyz", "model": "g"}).encode() + b"\n",
        b"also not json\n",
        json.dumps({"type": "message", "role": "assistant", "content": "ok", "delta": True}).encode() + b"\n",
        json.dumps({"type": "result", "status": "success", "stats": {}}).encode() + b"\n",
    ]
    proc = _MockProc(output)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, session_id, _ = asyncio.run(run_gemini("hello"))

    assert response == "ok"
    assert session_id == "xyz"


def test_empty_response_fallback():
    """If no text is produced, a fallback string is returned (not empty)."""
    output = _make_stream(
        {"type": "init", "session_id": "empty", "model": "g"},
        {"type": "result", "status": "success", "stats": {}},
    )
    proc = _MockProc(output)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        response, _, _ = asyncio.run(run_gemini("hello"))

    assert response  # not empty string
    assert response == "(empty response)"
