import sys
from pathlib import Path

from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_IDS = {
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
}

if not ALLOWED_USER_IDS:
    print("FATAL: TELEGRAM_ALLOWED_USER_IDS is empty. Refusing to start with open access.")
    sys.exit(1)

WORKING_DIR = str(ROOT_DIR)
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "300"))  # 5 min default
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))
