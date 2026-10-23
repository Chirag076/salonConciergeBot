"""The webhook must accept Telegram's updates and reject anyone without the secret."""
import json
import os
import tempfile
import time

os.environ.setdefault("GEMINI_API_KEY", "dummy-key-for-tests")
os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("SALON_DB", os.path.join(tempfile.mkdtemp(), "import.db"))
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["REGISTER_WEBHOOK"] = "0"       # never call Telegram from tests

import pytest  # noqa: E402

import webhook  # noqa: E402

UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1, "date": 0, "text": "hi",
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "is_bot": False, "first_name": "Riya"},
    },
}


@pytest.fixture
def client(monkeypatch):
    received = []
    monkeypatch.setattr(webhook.bot, "process_new_updates", lambda updates: received.extend(updates))
    c = webhook.app.test_client()
    c.received = received
    return c


def test_health_check(client):
    assert client.get("/").status_code == 200


def test_accepts_update_with_secret(client):
    r = client.post("/webhook", data=json.dumps(UPDATE),
                    headers={"X-Telegram-Bot-Api-Secret-Token": webhook.SECRET})
    assert r.status_code == 200
    for _ in range(50):                  # processed on a background thread
        if client.received:
            break
        time.sleep(0.02)
    assert client.received[0].message.text == "hi"


def test_rejects_wrong_secret(client):
    r = client.post("/webhook", data=json.dumps(UPDATE),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert r.status_code == 403
    assert client.received == []


def test_raw_secret_is_not_accepted(client):
    # Only the hashed value we registered with Telegram works.
    r = client.post("/webhook", data=json.dumps(UPDATE),
                    headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"})
    assert r.status_code == 403


def test_rejects_missing_secret(client):
    r = client.post("/webhook", data=json.dumps(UPDATE))
    assert r.status_code == 403


def test_a_crashing_reply_does_not_kill_the_bot(monkeypatch):
    """Telegram failing to send a reply must be logged, and the next message must still be handled."""
    import salon_bot
    from telebot import types
    bot = salon_bot.build_bot(threaded=False)
    seen = []
    monkeypatch.setattr(salon_bot, "send_with_retry", lambda chat, text: seen.append(text) or "ok")
    monkeypatch.setattr(salon_bot, "get_chat", lambda uid: None)

    def broken_reply(*args, **kwargs):
        raise RuntimeError("telegram is down")
    monkeypatch.setattr(bot, "reply_to", broken_reply)

    for i, text in enumerate(["first", "second"]):
        update = types.Update.de_json(json.dumps({**UPDATE, "update_id": i,
                                                  "message": {**UPDATE["message"], "text": text}}))
        bot.process_new_updates([update])     # must not raise
    assert seen == ["first", "second"]
