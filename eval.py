"""
eval.py - end-to-end eval suite for the Salon Concierge booking agent.

Sends real customer messages through the REAL Gemini agent and checks what
actually happened: rows in the database and which tools the agent called.
Runs against a throwaway database, so your real bookings.db is never touched.

Run:  python eval.py          (needs GEMINI_API_KEY in .env or the environment)
Exit code is non-zero if any scenario fails, so CI can gate on it.
"""
import functools
import os
import sqlite3
import sys
import tempfile
import time
from datetime import timedelta

# Point the agent at a throwaway database BEFORE importing it.
os.environ["SALON_DB"] = os.path.join(tempfile.mkdtemp(), "eval.db")

import booking      # noqa: E402
import salon_bot    # noqa: E402

PAUSE = int(os.getenv("EVAL_PAUSE", "12"))   # seconds between calls, to stay under free-tier rate limits

calls = []          # names of tools the agent called during the current scenario


def logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        calls.append(fn.__name__)
        return fn(*args, **kwargs)
    return wrapper


TOOLS = [logged(t) for t in booking.TOOLS]


def rows():
    con = sqlite3.connect(os.environ["SALON_DB"])
    out = con.execute("SELECT id, customer_name, service, date, time FROM bookings").fetchall()
    con.close()
    return out


def latest_id():
    return max((r[0] for r in rows()), default=0)


def ask(message):
    """Send one message to a fresh agent conversation.

    Temporary Gemini errors (503 overloaded, 429 rate limited) are retried on a
    fresh conversation with growing waits, so a busy API doesn't count as a
    failed scenario. Real errors still fail the scenario.
    """
    waits = [0, 20, 40, 60]
    for i, wait in enumerate(waits):
        time.sleep(wait)
        calls.clear()
        try:
            reply = salon_bot.new_chat(tools=TOOLS).send_message(message).text or ""
            break
        except salon_bot.genai_errors.APIError as e:
            if not salon_bot.is_temporary(e) or i == len(waits) - 1:
                raise
            print(f"    (Gemini busy: {e.code}, retrying in {waits[i + 1]}s)")
    time.sleep(PAUSE)
    return reply


passed = total = 0


def check(name, ok):
    global passed, total
    total += 1
    passed += bool(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


def scenario(name, fn):
    try:
        check(name, fn())
    except Exception as e:  # an API error counts as a failure, not a crash
        check(f"{name} (error: {type(e).__name__}: {e})", False)


print("Running eval...\n")

# --- BOOKING: each should add exactly one row for the right customer ---
for msg, name in [
    ("Book a women's haircut for Riya on Saturday at 3 PM", "Riya"),
    ("I'd like a hair spa for Aman this Sunday at 5 PM", "Aman"),
    ("Please book a facial for Neha on Friday at 11 AM", "Neha"),
    ("Bridal makeup for Priya on Saturday at noon", "Priya"),
    ("Book a men's haircut for Karan, Tuesday 6 PM", "Karan"),
    ("Manicure for Sana on Wednesday at 2 PM", "Sana"),
]:
    def books(msg=msg, name=name):
        before = len(rows())
        ask(msg)
        after = rows()
        return len(after) == before + 1 and any(name in (r[1] or "") for r in after)
    scenario(f"books: {name}", books)


def reschedules():
    ask("Book a pedicure for Meera on Thursday at 1 PM")
    bid = latest_id()
    ask(f"Reschedule booking {bid} to Sunday at 4 PM")
    row = [r for r in rows() if r[0] == bid]
    return bool(row) and row[0][4] == "16:00"


def cancels():
    ask("Book a hair color for Tara on Saturday at 10 AM")
    bid = latest_id()
    ask(f"Cancel booking {bid}")
    return all(r[0] != bid for r in rows())


scenario("reschedules an existing booking", reschedules)
scenario("cancels an existing booking", cancels)


# --- GUARDRAILS: nothing off-menu, no double booking, no Mondays ---
def no_new_row(msg):
    before = len(rows())
    ask(msg)
    return len(rows()) == before


scenario("declines tattoo (not a service)", lambda: no_new_row("Do you do tattoos?"))
scenario("refuses off-menu service", lambda: no_new_row("Book a full body massage for Rohit on Sunday 3 PM"))
def refuses_taken_slot():
    # Set up the clash directly, so this scenario doesn't depend on any earlier one.
    day = booking.today() + timedelta(days=1)
    while day.weekday() not in booking.OPEN_DAYS:
        day += timedelta(days=1)
    booking.book_appointment("Setup customer", "Facial", day.isoformat(), "15:00")
    return no_new_row(f"Book a manicure for Ishaan on {day.isoformat()} at 3 PM")


scenario("refuses a slot that is already taken", refuses_taken_slot)
scenario("refuses Monday (salon closed)", lambda: no_new_row("Book a facial for Dev on Monday at 11 AM"))


def price_from_tool():
    reply = ask("How much is a hair spa?")
    return "list_services" in calls and "1200" in reply.replace(",", "")


scenario("answers a price by calling list_services, not from memory", price_from_tool)

print(f"\nSCORE: {passed}/{total} scenarios passed")
sys.exit(0 if passed == total else 1)
