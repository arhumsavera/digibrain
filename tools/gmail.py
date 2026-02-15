#!/usr/bin/env python3
from __future__ import annotations
"""
Gmail IMAP tool — fetch and search emails from the command line.

Usage:
    python tools/email.py inbox                          # latest 10 emails
    python tools/email.py inbox --limit 5                # latest 5
    python tools/email.py inbox --unread                 # unread only
    python tools/email.py inbox --since 3d               # last 3 days
    python tools/email.py inbox --since 1w               # last week
    python tools/email.py inbox --from "linkedin"        # from address contains
    python tools/email.py inbox --subject "invitation"   # subject contains
    python tools/email.py inbox --unread --since 1d      # combine filters

    python tools/email.py read <message_id>              # read full email body
    python tools/email.py read <message_id> --raw        # raw text (no truncation)

    python tools/email.py search "job opportunity"       # full-text search via IMAP

All commands output structured text for easy agent consumption.
"""

import argparse
import email
import email.header
import email.utils
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
MAX_BODY_LENGTH = 3000


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return "".join(self.parts)


def strip_html(html: str) -> str:
    s = HTMLStripper()
    s.feed(html)
    text = s.get_text()
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def decode_header(raw: str) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def parse_since(value: str) -> datetime:
    """Parse duration string like '3d', '1w', '2h' into a datetime."""
    match = re.match(r"^(\d+)([dhw])$", value)
    if not match:
        raise ValueError(f"Invalid duration: {value}. Use format like 3d, 1w, 2h")

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    elif unit == "w":
        delta = timedelta(weeks=amount)
    else:
        raise ValueError(f"Unknown unit: {unit}")

    return datetime.now() - delta


def connect() -> imaplib.IMAP4_SSL:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("Error: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")
        sys.exit(1)

    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    return conn


def build_search_criteria(
    unread: bool = False,
    since: str | None = None,
    from_addr: str | None = None,
    subject: str | None = None,
    body_search: str | None = None,
    label: str | None = None,
) -> str:
    """Build IMAP search criteria string."""
    criteria = []

    if unread:
        criteria.append("UNSEEN")
    if since:
        dt = parse_since(since)
        date_str = dt.strftime("%d-%b-%Y")
        criteria.append(f'SINCE {date_str}')
    if from_addr:
        criteria.append(f'FROM "{from_addr}"')
    if subject:
        criteria.append(f'SUBJECT "{subject}"')
    if body_search:
        criteria.append(f'BODY "{body_search}"')

    return " ".join(criteria) if criteria else "ALL"


def get_body(msg: email.message.Message) -> str:
    """Extract readable text from email message."""
    if msg.is_multipart():
        text_parts = []
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace"))
            elif content_type == "text/html" and not text_parts:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(strip_html(payload.decode(charset, errors="replace")))
        return "\n".join(text_parts)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                text = strip_html(text)
            return text
    return ""


def format_email_summary(msg_id: str, msg: email.message.Message) -> str:
    """Format a single email as a concise summary line."""
    from_addr = decode_header(msg.get("From", ""))
    subject = decode_header(msg.get("Subject", "(no subject)"))
    date = msg.get("Date", "")

    # Parse and simplify date
    parsed_date = email.utils.parsedate_to_datetime(date) if date else None
    date_str = parsed_date.strftime("%b %d %H:%M") if parsed_date else "unknown"

    # Truncate long from addresses
    if len(from_addr) > 40:
        from_addr = from_addr[:37] + "..."

    return f"[{msg_id}] {date_str} | {from_addr}\n  Subject: {subject}"


def cmd_inbox(args):
    """List emails from inbox."""
    conn = connect()
    mailbox = args.label or "INBOX"
    conn.select(mailbox, readonly=True)

    criteria = build_search_criteria(
        unread=args.unread,
        since=args.since,
        from_addr=getattr(args, "from"),
        subject=args.subject,
    )

    _, data = conn.search(None, criteria)
    msg_ids = data[0].split()

    if not msg_ids:
        print("No emails found matching criteria.")
        conn.logout()
        return

    # Get latest N
    msg_ids = msg_ids[-args.limit:]
    msg_ids.reverse()

    print(f"Found {len(msg_ids)} email(s) ({mailbox}, {criteria}):\n")

    for mid in msg_ids:
        _, msg_data = conn.fetch(mid, "(RFC822.HEADER)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        print(format_email_summary(mid.decode(), msg))
        print()

    conn.logout()


def cmd_read(args):
    """Read a full email by message ID."""
    conn = connect()
    conn.select("INBOX", readonly=True)

    _, msg_data = conn.fetch(args.message_id.encode(), "(RFC822)")
    if not msg_data or not msg_data[0]:
        print(f"Message {args.message_id} not found.")
        conn.logout()
        return

    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)

    from_addr = decode_header(msg.get("From", ""))
    to_addr = decode_header(msg.get("To", ""))
    subject = decode_header(msg.get("Subject", "(no subject)"))
    date = msg.get("Date", "")
    body = get_body(msg)

    if not args.raw and len(body) > MAX_BODY_LENGTH:
        body = body[:MAX_BODY_LENGTH] + f"\n\n... (truncated, {len(body)} chars total. Use --raw for full text)"

    print(f"From: {from_addr}")
    print(f"To: {to_addr}")
    print(f"Date: {date}")
    print(f"Subject: {subject}")
    print(f"\n{body}")

    conn.logout()


def cmd_search(args):
    """Full-text search across emails."""
    conn = connect()
    conn.select("INBOX", readonly=True)

    criteria = build_search_criteria(
        body_search=args.query,
        since=args.since,
    )

    _, data = conn.search(None, criteria)
    msg_ids = data[0].split()

    if not msg_ids:
        print(f'No emails matching "{args.query}".')
        conn.logout()
        return

    msg_ids = msg_ids[-args.limit:]
    msg_ids.reverse()

    print(f'Found {len(msg_ids)} email(s) matching "{args.query}":\n')

    for mid in msg_ids:
        _, msg_data = conn.fetch(mid, "(RFC822.HEADER)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        print(format_email_summary(mid.decode(), msg))
        print()

    conn.logout()


def main():
    parser = argparse.ArgumentParser(description="Gmail IMAP tool")
    sub = parser.add_subparsers(dest="command")

    # inbox
    inbox = sub.add_parser("inbox", help="List emails from inbox")
    inbox.add_argument("--limit", type=int, default=10, help="Max emails to show (default: 10)")
    inbox.add_argument("--unread", action="store_true", help="Unread only")
    inbox.add_argument("--since", help="Duration: 3d, 1w, 2h")
    inbox.add_argument("--from", dest="from", help="From address contains")
    inbox.add_argument("--subject", help="Subject contains")
    inbox.add_argument("--label", help="Gmail label/folder (default: INBOX)")

    # read
    read = sub.add_parser("read", help="Read a full email")
    read.add_argument("message_id", help="Message ID from inbox listing")
    read.add_argument("--raw", action="store_true", help="Full body, no truncation")

    # search
    search = sub.add_parser("search", help="Full-text search")
    search.add_argument("query", help="Search query")
    search.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    search.add_argument("--since", help="Duration: 3d, 1w, 2h")

    args = parser.parse_args()

    if args.command == "inbox":
        cmd_inbox(args)
    elif args.command == "read":
        cmd_read(args)
    elif args.command == "search":
        cmd_search(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
