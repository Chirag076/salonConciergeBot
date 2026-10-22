"""The bot should ride out temporary Gemini outages (503/429) but not hide real errors."""
import os
import tempfile

import pytest

os.environ.setdefault("GEMINI_API_KEY", "dummy-key-for-tests")
os.environ.setdefault("SALON_DB", os.path.join(tempfile.mkdtemp(), "import.db"))

import salon_bot  # noqa: E402
from google.genai import errors  # noqa: E402


class Reply:
    def __init__(self, text):
        self.text = text


class FlakyChat:
    """Fails with the given errors first, then answers."""
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0

    def send_message(self, text):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return Reply("ok")


def api_error(code):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": "test", "status": "TEST"}})


def test_retries_through_temporary_503s():
    chat = FlakyChat([api_error(503), api_error(503)])
    assert salon_bot.send_with_retry(chat, "hi", waits=[0, 0, 0]) == "ok"
    assert chat.calls == 3


def test_retries_rate_limit_429():
    chat = FlakyChat([api_error(429)])
    assert salon_bot.send_with_retry(chat, "hi", waits=[0]) == "ok"


def test_gives_up_after_last_retry():
    chat = FlakyChat([api_error(503)] * 5)
    with pytest.raises(errors.ServerError):
        salon_bot.send_with_retry(chat, "hi", waits=[0, 0])
    assert chat.calls == 3


def test_does_not_retry_real_errors():
    chat = FlakyChat([api_error(400)])
    with pytest.raises(errors.ClientError):
        salon_bot.send_with_retry(chat, "hi", waits=[0, 0])
    assert chat.calls == 1
