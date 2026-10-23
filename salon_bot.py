import os
import time
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

import booking

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.5-flash-lite")

booking.init_db()

SYSTEM_PROMPT = """You are the booking assistant for Glow Salon, a hair & beauty salon in Delhi.
Be warm and concise. Reply like a friendly WhatsApp chat.

Today is {today} ({weekday}). Convert relative dates like "Saturday" or "tomorrow" to YYYY-MM-DD
and times like "3 PM" to 24-hour HH:MM before calling a tool.

Rules:
- You do not know the menu, prices or free slots from memory. Call list_services before stating
  any service or price, and check_availability before offering or confirming any time.
- If a service is not returned by list_services, say the salon does not offer it. Never invent one.
- To book you need four things: customer name, service, date, time. Ask for whatever is missing.
- Once you have all four, call book_appointment and give the customer their booking ID.
- If a tool says a slot is taken or the salon is closed, tell the customer and offer the free slots it returns.
- Customers can reschedule or cancel with their booking ID. If they don't have it, ask for it,
  then call reschedule_appointment or cancel_appointment.
- If unsure about something, say you'll check with the front desk.
"""


def new_chat(tools=None):
    """A fresh agent conversation. Used by the bot (one per customer) and by eval.py."""
    t = booking.today()
    return client.chats.create(
        model=CHAT_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT.format(today=t.isoformat(), weekday=t.strftime("%A")),
            tools=tools or booking.TOOLS,
        ),
    )


RETRY_WAITS = [5, 15, 30]   # seconds to wait before each retry


def is_temporary(err) -> bool:
    """503 (model overloaded) and 429 (rate limited) usually clear up if you wait."""
    return getattr(err, "code", None) in (429, 500, 503)


def send_with_retry(chat, text, waits=RETRY_WAITS):
    """Send a message, retrying temporary Gemini errors with growing waits."""
    attempts = [0] + list(waits)
    for i, wait in enumerate(attempts):
        time.sleep(wait)
        try:
            return chat.send_message(text).text or ""
        except genai_errors.APIError as e:
            if not is_temporary(e) or i == len(attempts) - 1:
                raise


chats = {}


def get_chat(uid):
    if uid not in chats:
        chats[uid] = new_chat()
    return chats[uid]


def build_bot():
    """Create the Telegram bot and register its handlers. Used by polling (local) and webhook (cloud)."""
    bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))

    @bot.message_handler(commands=["start"])
    def start(m):
        chats.pop(m.from_user.id, None)
        bot.reply_to(m, "Hi! Welcome to Glow Salon. I can book an appointment or answer questions "
                        "about our services. What can I do for you?")

    @bot.message_handler(commands=["bookings"])      # for you, to verify saves
    def bookings(m):
        con = booking.connect()
        rows = con.execute("SELECT id, customer_name, service, date, time FROM bookings "
                           "ORDER BY id DESC LIMIT 10").fetchall()
        con.close()
        text = ("Recent bookings:\n" + "\n".join(f"#{r[0]} {r[1]}: {r[2]} on {r[3]} at {r[4]}" for r in rows)
                if rows else "No bookings yet.")
        bot.reply_to(m, text)

    @bot.message_handler(func=lambda m: True)
    def handle(m):
        try:
            reply = send_with_retry(get_chat(m.from_user.id), m.text)
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}")
            reply = "Sorry, I'm having trouble right now. Please try again in a minute."
        bot.reply_to(m, reply or "Sorry, could you say that again?")

    return bot


def run_polling():
    """Local development: the bot asks Telegram for new messages in a loop."""
    bot = build_bot()
    bot.remove_webhook()   # Telegram won't serve polling while a webhook is set
    print("Bot is running (polling)...")
    bot.infinity_polling()


if __name__ == "__main__":
    run_polling()
