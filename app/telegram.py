"""Run with python -m app.telegram; reads the bot token without displaying it."""
import argparse
import getpass
import os
import sys
import time
from contextlib import contextmanager

from . import config, db
from .services.telegram import TelegramClient, TelegramError, TelegramIntake


@contextmanager
def worker_lock(bot_id):
    """Only one local polling worker per bot/data folder."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (config.DATA_DIR / f"telegram-{bot_id}.lock").open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("A Telegram worker is already using this bot/data folder.") from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("A Telegram worker is already using this bot/data folder.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def main():
    parser = argparse.ArgumentParser(description="Telegram resident reports, using free keyword classification.")
    parser.add_argument("--check", action="store_true", help="Check the token and polling configuration, then exit.")
    args = parser.parse_args()
    token = os.environ.get("TOWNSHIPFIX_TELEGRAM_BOT_TOKEN", "").strip()
    if not token and sys.stdin.isatty():
        token = getpass.getpass("Telegram bot token (hidden; not saved): ").strip()
    if not token:
        parser.error("Set TOWNSHIPFIX_TELEGRAM_BOT_TOKEN, or run in an interactive terminal for a hidden token prompt.")
    raw_allowlist = os.environ.get("TOWNSHIPFIX_TELEGRAM_ALLOWED_CHATS", "").strip()
    try:
        allowed_chats = {int(value.strip()) for value in raw_allowlist.split(",")} if raw_allowlist else None
    except ValueError:
        parser.error("TOWNSHIPFIX_TELEGRAM_ALLOWED_CHATS must contain comma-separated numeric private chat IDs.")
    # This worker never calls a paid vision API, even if the web app has a key.
    config.VISION_PROVIDER = "keywords"
    client = TelegramClient(token)
    try:
        bot = client.call("getMe")
        if client.call("getWebhookInfo").get("url"):
            parser.error("This bot already has a webhook. Use a new bot or remove that webhook before polling.")
        print(f"Telegram bot @{bot['username']} ready. Data folder: {config.DATA_DIR.resolve()}")
        print("Classification: local keyword rules. Dashboard must use the same data folder.")
        if args.check:
            return 0
        with worker_lock(bot["id"]):
            intake = TelegramIntake(client, bot["id"], allowed_chats)
            print("Listening for private reports. Press Ctrl+C to stop.")
            while True:
                try:
                    intake.poll_once()
                except TelegramError as error:
                    print(str(error), file=sys.stderr)
                    if error.code in (401, 409):
                        return 1
                    time.sleep(error.retry_after)
    except (TelegramError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nTelegram worker stopped.")
        return 0
    finally:
        db.reset_connection()


if __name__ == "__main__":
    raise SystemExit(main())
