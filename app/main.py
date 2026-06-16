"""Entry point — Telegram bot polling + daily scheduler."""
from __future__ import annotations

import logging
import threading
import time

import requests
import schedule

from app.core.config import OLLAMA_MODEL, SCHEDULE_TIME, TELEGRAM_BOT_TOKEN
from app.services.bot_handler import BotHandler

log = logging.getLogger(__name__)


def poll_telegram(handler: BotHandler) -> None:
    log.info("Starting Telegram long polling …")
    offset = 0

    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        params={"offset": -1, "timeout": 1},
        timeout=5,
    )
    data = resp.json()
    if data.get("ok") and data.get("result"):
        offset = data["result"][-1]["update_id"] + 1

    while True:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        resp = requests.get(url, params={"offset": offset, "timeout": 15}, timeout=20)
        if resp.status_code != 200:
            time.sleep(5)
            continue
        data = resp.json()
        if not data.get("ok"):
            time.sleep(5)
            continue
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            handler.handle_update(update)


def run_scheduled_tasks() -> None:
    log.info("Running scheduled tasks …")
    from app.tasks.arxiv_fetcher import main as send_papers_main
    send_papers_main()
    log.info("Scheduled tasks completed.")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is empty in .env!")
        return

    log.info("=" * 60)
    log.info("  DAILY PAPER BRIEF BOT")
    log.info("  Schedule : %s", SCHEDULE_TIME)
    log.info("  Model    : %s", OLLAMA_MODEL)
    log.info("=" * 60)

    handler = BotHandler()

    poll_thread = threading.Thread(
        target=poll_telegram, args=(handler,), daemon=True
    )
    poll_thread.start()

    schedule.every().day.at(SCHEDULE_TIME).do(run_scheduled_tasks)
    next_run = schedule.next_run()
    if next_run:
        log.info("Next scheduled run: %s", next_run)

    while True:
        schedule.run_pending()
        time.sleep(2)


if __name__ == "__main__":
    main()
