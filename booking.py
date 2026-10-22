"""
booking.py - the salon's source of truth: services, opening hours and bookings.

Every fact the agent tells a customer (a price, a free slot, a booking ID) comes
from a function in this file, never from the model's memory. The functions are
also the agent's tools, so their docstrings are what Gemini reads.

No Telegram or Gemini imports here, so the whole module is unit-testable.
"""
import os
import sqlite3
from datetime import date as Date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")

SERVICES = {                      # name -> price in Rs
    "Haircut (women)": 800,
    "Haircut (men)": 400,
    "Hair color": 2500,
    "Hair spa": 1200,
    "Manicure": 600,
    "Pedicure": 800,
    "Facial": 1500,
    "Bridal makeup": 8000,
}

OPEN_DAYS = {1, 2, 3, 4, 5, 6}    # Mon=0 ... Sun=6, closed Mondays
FIRST_SLOT = 10 * 60              # 10:00, in minutes after midnight
LAST_SLOT = 19 * 60               # 19:00 is the last 1-hour slot before closing at 20:00
SLOT_MINUTES = 60                 # one chair, one-hour slots


def db_path() -> str:
    return os.getenv("SALON_DB", "bookings.db")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_path(), timeout=10)
    con.execute("PRAGMA busy_timeout = 10000")
    return con


def init_db() -> None:
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT, service TEXT, date TEXT, time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    # The double-booking guard lives in the database, not in the prompt:
    # even if two customers book the same slot at the same moment, the second
    # INSERT fails.
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot ON bookings (date, time)")
    con.commit()
    con.close()


def today() -> Date:
    return datetime.now(TZ).date()


# ---------- validation helpers (not tools) ----------

def _match_service(name: str):
    """Case-insensitive match against the real menu. Returns the canonical name or None."""
    wanted = " ".join(name.lower().replace("'s", "").split())
    for real in SERVICES:
        canon = real.lower()
        if wanted == canon:
            return real
    # tolerate "women haircut" / "haircut for men" style phrasing
    for real in SERVICES:
        words = set(real.lower().replace("(", "").replace(")", "").split())
        if words and words <= set(wanted.replace("(", "").replace(")", "").split()):
            return real
    return None


def _parse_date(value: str):
    try:
        return Date.fromisoformat(value.strip())
    except (ValueError, AttributeError):
        return None


def _parse_time(value: str):
    """Accepts 'HH:MM' (24h). Returns minutes after midnight or None."""
    try:
        t = datetime.strptime(value.strip(), "%H:%M")
    except (ValueError, AttributeError):
        return None
    return t.hour * 60 + t.minute


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _slot_problem(d, minutes):
    """Returns a reason string if the slot is not bookable, else None."""
    if d is None:
        return "Date must be in YYYY-MM-DD format."
    if minutes is None:
        return "Time must be in 24-hour HH:MM format, e.g. 15:00."
    if d < today():
        return f"{d.isoformat()} is in the past."
    if d.weekday() not in OPEN_DAYS:
        return "The salon is closed on Mondays."
    if minutes < FIRST_SLOT or minutes > LAST_SLOT or (minutes - FIRST_SLOT) % SLOT_MINUTES:
        return "Slots are on the hour from 10:00 to 19:00."
    if d == today() and minutes <= datetime.now(TZ).hour * 60 + datetime.now(TZ).minute:
        return "That time has already passed today."
    return None


def _free_slots(d) -> list:
    con = connect()
    taken = {r[0] for r in con.execute("SELECT time FROM bookings WHERE date = ?", (d.isoformat(),))}
    con.close()
    return [_fmt(m) for m in range(FIRST_SLOT, LAST_SLOT + 1, SLOT_MINUTES)
            if _fmt(m) not in taken and _slot_problem(d, m) is None]


# ---------- tools the agent can call ----------

def list_services() -> str:
    """List every service the salon offers with its price, and the opening hours.
    Call this before telling a customer any price or whether a service exists."""
    lines = [f"- {name}: Rs {price}" for name, price in SERVICES.items()]
    return ("Services:\n" + "\n".join(lines) +
            "\nHours: Tuesday to Sunday, 10:00 to 20:00. Closed Mondays. One-hour slots from 10:00 to 19:00.")


def check_availability(date: str) -> str:
    """List the free appointment slots on a date. Call this before offering or confirming any time.

    Args:
        date: the date in YYYY-MM-DD format.
    """
    d = _parse_date(date)
    if d is None:
        return "Date must be in YYYY-MM-DD format."
    if d < today():
        return f"{d.isoformat()} is in the past."
    if d.weekday() not in OPEN_DAYS:
        return f"{d.isoformat()} is a Monday. The salon is closed on Mondays."
    free = _free_slots(d)
    return f"Free slots on {d.isoformat()}: {', '.join(free)}." if free else f"No free slots on {d.isoformat()}."


def book_appointment(customer_name: str, service: str, date: str, time: str) -> str:
    """Save a salon appointment. Call this ONLY once you have all four:
    customer name, service, date, and time.

    Args:
        customer_name: the customer's name.
        service: a service exactly as listed by list_services, e.g. 'Haircut (women)'.
        date: the date in YYYY-MM-DD format.
        time: the start time in 24-hour HH:MM format, e.g. '15:00'.
    """
    real = _match_service(service or "")
    if real is None:
        return f"Not booked: '{service}' is not a service we offer. Use list_services."
    if not (customer_name or "").strip():
        return "Not booked: customer name is missing."
    d, minutes = _parse_date(date), _parse_time(time)
    problem = _slot_problem(d, minutes)
    if problem:
        return f"Not booked: {problem}"
    con = connect()
    try:
        cur = con.execute("INSERT INTO bookings (customer_name, service, date, time) VALUES (?,?,?,?)",
                          (customer_name.strip(), real, d.isoformat(), _fmt(minutes)))
        con.commit()
        bid = cur.lastrowid
    except sqlite3.IntegrityError:
        con.close()
        free = _free_slots(d)
        alt = f" Free slots that day: {', '.join(free)}." if free else " No other slots are free that day."
        return f"Not booked: {_fmt(minutes)} on {d.isoformat()} is already taken.{alt}"
    con.close()
    return (f"Saved. Booking ID {bid}: {real} for {customer_name.strip()} on {d.isoformat()} "
            f"at {_fmt(minutes)}. Price Rs {SERVICES[real]}.")


def reschedule_appointment(booking_id: int, new_date: str, new_time: str) -> str:
    """Move an existing booking to a new date and time. Needs the booking ID.

    Args:
        booking_id: the ID the customer got when they booked.
        new_date: the new date in YYYY-MM-DD format.
        new_time: the new start time in 24-hour HH:MM format.
    """
    d, minutes = _parse_date(new_date), _parse_time(new_time)
    problem = _slot_problem(d, minutes)
    if problem:
        return f"Not moved: {problem}"
    con = connect()
    try:
        cur = con.execute("UPDATE bookings SET date=?, time=? WHERE id=?",
                          (d.isoformat(), _fmt(minutes), int(booking_id)))
        con.commit()
        changed = cur.rowcount
    except sqlite3.IntegrityError:
        con.close()
        return f"Not moved: {_fmt(minutes)} on {d.isoformat()} is already taken."
    con.close()
    if not changed:
        return f"No booking found with ID {booking_id}."
    return f"Booking #{booking_id} moved to {d.isoformat()} at {_fmt(minutes)}."


def cancel_appointment(booking_id: int) -> str:
    """Cancel an existing booking. Needs the booking ID.

    Args:
        booking_id: the ID the customer got when they booked.
    """
    con = connect()
    cur = con.execute("DELETE FROM bookings WHERE id=?", (int(booking_id),))
    con.commit()
    changed = cur.rowcount
    con.close()
    return f"Booking #{booking_id} is cancelled." if changed else f"No booking found with ID {booking_id}."


TOOLS = [list_services, check_availability, book_appointment, reschedule_appointment, cancel_appointment]
