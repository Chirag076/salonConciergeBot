"""Unit tests for the booking tools. No API keys needed: these never call Gemini or Telegram."""
import sqlite3
import threading
from datetime import timedelta

import pytest

import booking


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SALON_DB", str(tmp_path / "test.db"))
    booking.init_db()


def next_open_day(min_days_ahead=1):
    d = booking.today() + timedelta(days=min_days_ahead)
    while d.weekday() not in booking.OPEN_DAYS:
        d += timedelta(days=1)
    return d.isoformat()


def next_monday():
    d = booking.today() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d.isoformat()


def count():
    con = sqlite3.connect(booking.db_path())
    n = con.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    con.close()
    return n


def test_books_a_valid_slot():
    out = booking.book_appointment("Riya", "Haircut (women)", next_open_day(), "15:00")
    assert out.startswith("Saved. Booking ID 1")
    assert "Rs 800" in out
    assert count() == 1


def test_matches_service_names_loosely():
    out = booking.book_appointment("Karan", "men's haircut", next_open_day(), "11:00")
    assert "Haircut (men)" in out


def test_rejects_off_menu_service():
    out = booking.book_appointment("Rohit", "Full body massage", next_open_day(), "15:00")
    assert out.startswith("Not booked")
    assert count() == 0


def test_rejects_double_booking_and_offers_alternatives():
    day = next_open_day()
    booking.book_appointment("Riya", "Facial", day, "15:00")
    out = booking.book_appointment("Ishaan", "Manicure", day, "15:00")
    assert "already taken" in out
    assert "16:00" in out          # suggests a free slot
    assert count() == 1


def test_concurrent_bookings_on_one_slot_give_exactly_one_winner():
    day = next_open_day()
    results = []

    def attempt(i):
        results.append(booking.book_appointment(f"Customer {i}", "Facial", day, "12:00"))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(r.startswith("Saved") for r in results) == 1
    assert count() == 1


def test_rejects_monday():
    out = booking.book_appointment("Dev", "Facial", next_monday(), "11:00")
    assert "closed on Mondays" in out
    assert count() == 0


@pytest.mark.parametrize("time", ["09:00", "20:00", "15:30", "3 PM"])
def test_rejects_times_outside_slots(time):
    out = booking.book_appointment("Neha", "Facial", next_open_day(), time)
    assert out.startswith("Not booked")


def test_rejects_past_date():
    past = (booking.today() - timedelta(days=3)).isoformat()
    out = booking.book_appointment("Neha", "Facial", past, "11:00")
    assert "in the past" in out


def test_rejects_free_text_dates():
    out = booking.book_appointment("Neha", "Facial", "Saturday", "11:00")
    assert "YYYY-MM-DD" in out


def test_availability_hides_taken_slots():
    day = next_open_day()
    booking.book_appointment("Riya", "Facial", day, "10:00")
    out = booking.check_availability(day)
    assert "10:00" not in out
    assert "11:00" in out and "19:00" in out


def test_reschedule_moves_booking():
    day = next_open_day()
    booking.book_appointment("Meera", "Pedicure", day, "13:00")
    out = booking.reschedule_appointment(1, day, "16:00")
    assert "moved" in out
    free = booking.check_availability(day)
    assert "13:00" in free and "16:00" not in free


def test_reschedule_into_taken_slot_is_refused():
    day = next_open_day()
    booking.book_appointment("Meera", "Pedicure", day, "13:00")
    booking.book_appointment("Tara", "Hair color", day, "14:00")
    out = booking.reschedule_appointment(1, day, "14:00")
    assert "already taken" in out


def test_cancel_frees_the_slot():
    day = next_open_day()
    booking.book_appointment("Tara", "Hair color", day, "10:00")
    assert "cancelled" in booking.cancel_appointment(1)
    assert "10:00" in booking.check_availability(day)
    assert "No booking found" in booking.cancel_appointment(1)


def test_list_services_has_real_prices():
    out = booking.list_services()
    assert "Hair spa: Rs 1200" in out
    assert "Closed Mondays" in out
