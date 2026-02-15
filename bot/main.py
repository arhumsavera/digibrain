#!/usr/bin/env python3
"""Telegram bot that bridges messages to Claude Code and opencode."""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from bot.config import BOT_TOKEN, ALLOWED_USER_IDS, WORKING_DIR
from bot.sessions import sessions
from bot.agents import run_agent

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


def is_authorized(user_id: int) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


async def send_response(update: Update, text: str):
    """Send response, splitting into multiple messages if needed."""
    if not text:
        text = "(empty response)"

    while text:
        chunk = text[:MAX_MESSAGE_LENGTH]
        text = text[MAX_MESSAGE_LENGTH:]
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
    await update.message.reply_text(
        f"Agent: {session.agent}\n"
        f"Session: {sid_display}\n"
        f"Messages: {session.message_count}"
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

    await route_message(update, message)


async def route_message(update: Update, message: str):
    """Route a message to the current agent and send the response."""
    user_id = update.effective_user.id
    session = sessions.get(user_id)

    # Show typing indicator
    await update.message.chat.send_action("typing")

    logger.info(
        "User %s → %s (session: %s, msg #%d)",
        user_id,
        session.agent,
        session.session_id or "new",
        session.message_count + 1,
    )

    try:
        response, new_session_id = await run_agent(
            session.agent, message, session.session_id
        )
        session.session_id = new_session_id
        session.message_count += 1
    except Exception as e:
        logger.exception("Agent error")
        response = f"Agent error: {e}"

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
    logger.info("Allowed users: %s", ALLOWED_USER_IDS or "all")
    logger.info("Working dir: %s", WORKING_DIR)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
