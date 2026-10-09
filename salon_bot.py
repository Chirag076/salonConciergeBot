import os
import sqlite3
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))

CHAT_MODEL = "gemini-3.5-flash-lite"

# --- database ---
def init_db():
    con = sqlite3.connect("bookings.db")
    con.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT, service TEXT, date TEXT, time TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit(); con.close()
init_db()

# --- the tool the agent can call ---
def book_appointment(customer_name: str, service: str, date: str, time: str) -> str:
    """Save a salon appointment. Call this ONLY once you have all four:
    customer name, service, date, and time.

    Args:
        customer_name: the customer's name.
        service: the service (e.g. 'Haircut (women)').
        date: the date (e.g. 'Saturday' or '2026-10-18').
        time: the time (e.g. '3 PM').
    """
    print(f"[tool] book_appointment({customer_name!r}, {service!r}, {date!r}, {time!r})")
    con = sqlite3.connect("bookings.db")
    cur = con.execute("INSERT INTO bookings (customer_name, service, date, time) VALUES (?,?,?,?)",
                      (customer_name, service, date, time))
    con.commit(); bid = cur.lastrowid; con.close()
    return f"Saved. Booking ID {bid}: {service} for {customer_name} on {date} at {time}."

SYSTEM_PROMPT = """You are the booking assistant for Glow Salon, a hair & beauty salon in Delhi.
Be warm and concise — reply like a friendly WhatsApp chat.

Services & prices:
- Haircut (women): Rs 800   - Haircut (men): Rs 400   - Hair color: Rs 2500
- Hair spa: Rs 1200   - Manicure: Rs 600   - Pedicure: Rs 800
- Facial: Rs 1500   - Bridal makeup: Rs 8000
Hours: Tuesday-Sunday, 10 AM - 8 PM. Closed Mondays.

Rules:
- Only mention services/prices from the list above. NEVER invent one.
- To book you need four things: customer name, service, date, time. Ask for whatever's missing.
- Once you have ALL four, call book_appointment to save it, then give the customer their booking ID.
- If unsure about something, say you'll check with the front desk.
- Customers can reschedule or cancel using their booking ID (the number from when they booked). If they don't have it, ask for it, then call reschedule_appointment or cancel_appointment.
"""

chats = {}
def get_chat(uid):
    if uid not in chats:
        chats[uid] = client.chats.create(
            model=CHAT_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[book_appointment, reschedule_appointment, cancel_appointment],      # <-- the agent's tool
            ))
    return chats[uid]

def reschedule_appointment(booking_id: int, new_date: str, new_time: str) -> str:
    """Change the date/time of an existing booking. Needs the booking ID.
    Args:
        booking_id: the ID the customer got when they booked.
        new_date: the new date.
        new_time: the new time.
    """
    print(f"[tool] reschedule_appointment({booking_id}, {new_date!r}, {new_time!r})")
    con = sqlite3.connect("bookings.db")
    cur = con.execute("UPDATE bookings SET date=?, time=? WHERE id=?", (new_date, new_time, booking_id))
    con.commit(); changed = cur.rowcount; con.close()
    return f"Booking #{booking_id} moved to {new_date} at {new_time}." if changed else f"No booking found with ID {booking_id}."

def cancel_appointment(booking_id: int) -> str:
    """Cancel an existing booking. Needs the booking ID.
    Args:
        booking_id: the ID the customer got when they booked.
    """
    print(f"[tool] cancel_appointment({booking_id})")
    con = sqlite3.connect("bookings.db")
    cur = con.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    con.commit(); changed = cur.rowcount; con.close()
    return f"Booking #{booking_id} is cancelled." if changed else f"No booking found with ID {booking_id}."

@bot.message_handler(commands=["start"])
def start(m):
    chats.pop(m.from_user.id, None)
    bot.reply_to(m, "Hi! Welcome to Glow Salon. I can book an appointment or answer questions about our services. What can I do for you?")

@bot.message_handler(commands=["bookings"])      # for YOU, to verify saves
def bookings(m):
    con = sqlite3.connect("bookings.db")
    rows = con.execute("SELECT id,customer_name,service,date,time FROM bookings ORDER BY id DESC LIMIT 10").fetchall()
    con.close()
    bot.reply_to(m, "Recent bookings:\n" + "\n".join(f"#{r[0]} {r[1]}: {r[2]} on {r[3]} at {r[4]}" for r in rows) if rows else "No bookings yet.")

@bot.message_handler(func=lambda m: True)
def handle(m):
    bot.reply_to(m, get_chat(m.from_user.id).send_message(m.text).text)

print("Bot is running...")
bot.infinity_polling()