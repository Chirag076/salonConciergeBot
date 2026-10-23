"""
webhook.py - runs the bot in the cloud.

Locally the bot polls Telegram ("any new messages?") in a loop. On a free host
that sleeps when idle, polling stops working, so here Telegram pushes each
message to us instead (a webhook): an HTTP POST to /webhook, which also wakes
the server up.

Run in production with:
    gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT webhook:app
One worker only: conversations are kept in memory and SQLite likes one writer.
"""
import hashlib
import hmac
import logging
import os
import threading

import telebot
from flask import Flask, abort, request

import salon_bot

app = Flask(__name__)
# threaded=False: we start our own thread per update below. telebot's built-in pool
# hides errors at DEBUG level and a crashed worker stops for good, which made the bot go silent.
bot = salon_bot.build_bot(threaded=False)
log = logging.getLogger("salon.webhook")

# Telegram only allows A-Z, a-z, 0-9, _ and - in the secret, so we send a hex hash of
# whatever secret is configured (Render's generated values can contain + / =).
_raw = os.getenv("WEBHOOK_SECRET", "")
SECRET = hashlib.sha256(_raw.encode()).hexdigest() if _raw else ""
BASE_URL = os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL")   # Render sets the latter


@app.get("/")
def health():
    return "Glow Salon Concierge is up."


@app.post("/webhook")
def webhook():
    # Telegram echoes the secret we registered, so random people can't post fake messages.
    sent = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not SECRET or not hmac.compare_digest(sent, SECRET):
        abort(403)
    update = telebot.types.Update.de_json(request.get_data(as_text=True))
    log.info("update %s received", update.update_id)
    # Reply in the background so Telegram gets its 200 immediately (the AI can take seconds).
    threading.Thread(target=process, args=(update,), daemon=True).start()
    return "", 200


def process(update):
    try:
        bot.process_new_updates([update])
    except Exception:
        log.exception("failed to process update %s", update.update_id)


def register_webhook():
    if not (BASE_URL and SECRET):
        log.warning("WEBHOOK_BASE_URL/RENDER_EXTERNAL_URL or WEBHOOK_SECRET missing, webhook not registered")
        return
    bot.set_webhook(url=f"{BASE_URL.rstrip('/')}/webhook", secret_token=SECRET)
    log.info("Webhook registered at %s/webhook", BASE_URL.rstrip('/'))


if os.getenv("REGISTER_WEBHOOK", "1") == "1":
    register_webhook()
