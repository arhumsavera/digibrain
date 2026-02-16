#!/usr/bin/env python3
"""Telegram bot that bridges messages to Claude Code and opencode."""

import logging
import time
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.config import BOT_TOKEN, ALLOWED_USER_IDS, WORKING_DIR, RATE_LIMIT_PER_MINUTE
from bot.sessions import sessions
from bot.agents import run_agent

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096

# Rate limiting: track message timestamps per user
_rate_log: dict[int, list[float]] = {}
# Concurrency: track if a user has an agent running
_active_users: set[int] = set()


def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS


def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    timestamps = _rate_log.setdefault(user_id, [])
    # Prune old entries
    _rate_log[user_id] = [t for t in timestamps if now - t < 60]
    return len(_rate_log[user_id]) >= RATE_LIMIT_PER_MINUTE


def record_message(user_id: int):
    _rate_log.setdefault(user_id, []).append(time.time())


async def send_files(update: Update, paths: list[Path]):
    """Send files as Telegram documents."""
    for p in paths:
        try:
            with open(p, "rb") as f:
                await update.message.reply_document(document=f, filename=p.name)
            logger.info("Sent file: %s (%dKB)", p.name, p.stat().st_size // 1024)
        except Exception:
            logger.exception("Failed to send file: %s", p)


async def send_response(update: Update, text: str):
    """Send response, splitting into multiple messages if needed.
    Tries Markdown first, falls back to plain text if parsing fails."""
    if not text:
        text = "(empty response)"

    while text:
        chunk = text[:MAX_MESSAGE_LENGTH]
        text = text[MAX_MESSAGE_LENGTH:]
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(chunk)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    await update.message.reply_text(
        "Agent bridge ready.\n\n"
        "Messages go to opencode by default.\n"
        "/claude <msg> — switch to Claude Code\n"
        "/oc <msg> — switch to opencode\n"
        "/new — start fresh session\n"
        "/status — current session info"
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    session = sessions.get(update.effective_user.id)
    sid = session.session_id or "none"
    sid_display = f"{sid[:12]}..." if len(sid) > 12 else sid
    active = update.effective_user.id in _active_users
    await update.message.reply_text(
        f"Agent: {session.agent}\n"
        f"Session: {sid_display}\n"
        f"Messages: {session.message_count}\n"
        f"Active: {'yes' if active else 'no'}"
    )


async def new_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    sessions.reset(update.effective_user.id)
    session = sessions.get(update.effective_user.id)
    await update.message.reply_text(f"Session cleared. Next message starts fresh with {session.agent}.")


async def claude_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    message = " ".join(context.args) if context.args else None
    if not message:
        sessions.reset(update.effective_user.id, agent="claude")
        await update.message.reply_text("Switched to Claude Code. Send a message.")
        return

    sessions.reset(update.effective_user.id, agent="claude")
    await route_message(update, message)


async def oc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    message = " ".join(context.args) if context.args else None
    if not message:
        sessions.reset(update.effective_user.id, agent="opencode")
        await update.message.reply_text("Switched to opencode. Send a message.")
        return

    sessions.reset(update.effective_user.id, agent="opencode")
    await route_message(update, message)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return

    message = update.message.text
    if not message:
        return

    # If replying to a bot message, prepend it as context
    reply = update.message.reply_to_message
    if reply and reply.text:
        message = f"[Previous message for context:\n{reply.text}]\n\nUser's follow-up: {message}"

    await route_message(update, message)


async def route_message(update: Update, message: str):
    """Route a message to the current agent and send the response."""
    user_id = update.effective_user.id
    session = sessions.get(user_id)

    # Rate limit check
    if is_rate_limited(user_id):
        await update.message.reply_text("Slow down — rate limit reached. Try again in a minute.")
        return

    # Concurrency check
    if user_id in _active_users:
        await update.message.reply_text("Still working on your last message. Wait for it to finish or /new to reset.")
        return

    record_message(user_id)
    _active_users.add(user_id)

    logger.info(
        "User %s → %s (session: %s, msg #%d)",
        user_id,
        session.agent,
        session.session_id or "new",
        session.message_count + 1,
    )

    # Send initial status message that we'll edit with progress
    status_msg = await update.message.reply_text(f"[{session.agent}] Working...")

    async def on_progress(text: str):
        """Edit the status message with progress updates."""
        try:
            await status_msg.edit_text(f"[{session.agent}] {text}")
        except Exception:
            pass  # Telegram may reject edits if text hasn't changed

    files = []
    try:
        response, new_session_id, files = await run_agent(
            session.agent, message, session.session_id, on_progress
        )
        session.session_id = new_session_id
        session.message_count += 1
    except Exception:
        logger.exception("Agent error")
        response = "Agent error occurred."
    finally:
        _active_users.discard(user_id)

    # Delete the progress message and send the final response
    try:
        await status_msg.delete()
    except Exception:
        pass

    # Send any files the agent produced (PDFs, images, etc.)
    if files:
        await send_files(update, files)

    await send_response(update, response)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("new", new_handler))
    app.add_handler(CommandHandler("claude", claude_handler))
    app.add_handler(CommandHandler("oc", oc_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot starting (polling)...")
    logger.info("Default agent: opencode")
    logger.info("Allowed users: %s", ALLOWED_USER_IDS)
    logger.info("Working dir: %s", WORKING_DIR)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
