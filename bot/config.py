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
WORKING_DIR = str(ROOT_DIR)
