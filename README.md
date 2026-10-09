# Glow Salon Concierge — a Telegram AI booking agent

An AI concierge on **Telegram** that chats with customers in plain language, answers questions about a salon's services, and **books, reschedules, and cancels appointments** through conversation. It's an agentic LLM app — it doesn't just reply, it takes real actions against a database.

## Demo

**[Watch the full demo video →](https://drive.google.com/file/d/14jerL5v7q92tbmNTvLsdB3axggYMKE9h/view?usp=sharing)**

A complete walkthrough — booking an appointment, rescheduling it, and cancelling — all through natural conversation on Telegram.

## Try it

This bot runs **locally** and connects to Telegram as **[@salonConciergeBot](https://t.me/salonConciergeBot)**.

To see it in action, clone and run it yourself (setup below) — or request a **live demo**, and I'll spin it up and walk through the full booking flow (booking, rescheduling, cancelling) on request.

## What it does

- Natural-language chat on Telegram — no forms, no button menus
- Answers questions about services, prices, and hours
- **Books** appointments — collects the details and saves them
- **Reschedules** and **cancels** existing bookings by ID
- Remembers the conversation, so multi-step booking feels natural
- Won't invent services or prices — grounded to the real menu

## How it works

```
Customer message (Telegram)
        ↓
   Gemini agent  ──decides──▶  calls a tool  ──reads/writes──▶  SQLite database
        ↓                     (book / reschedule / cancel)
   Plain-language reply
```

The agent has three tools it chooses between on its own:

| Tool | What it does |
|------|--------------|
| `book_appointment(name, service, date, time)` | Saves a new booking, returns a booking ID |
| `reschedule_appointment(booking_id, new_date, new_time)` | Moves an existing booking |
| `cancel_appointment(booking_id)` | Cancels a booking |

A **system prompt** defines the concierge's persona and the rules (only real services/prices, collect all details before booking). Each customer gets their **own conversation**, so context carries across messages.

## Tech stack

- **Python**
- **pyTelegramBotAPI** — Telegram Bot API
- **Google Gemini** — LLM + tool (function) calling
- **SQLite** — persistent bookings

## Run it

```bash
git clone https://github.com/Chirag076/salonConciergeBot.git
cd salonConciergeBot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env`:

```
GEMINI_API_KEY=your_gemini_key
TELEGRAM_TOKEN=your_botfather_token
```

Run it:

```bash
python salon_bot.py
```

Then message your bot on Telegram. Use `/bookings` to see saved appointments.

## What I learned

- Designing an **agent with tools** that take real, persistent actions — not just Q&A.
- Using a **system prompt + guardrails** to keep an LLM grounded ("never invent a price").
- Managing **per-user conversation state** for multi-turn booking flows.

## Possible improvements

- `check_availability` to prevent double-booking and respect opening hours
- Look up bookings by phone number instead of ID
- Swap SQLite for Postgres for production
- Deploy always-on so it runs 24/7
- Port to WhatsApp for real-world customer reach

## Contact

Built by **Chirag Chhabra** — happy to walk through a live demo on request.

- Email: chiragchhabrahmo@gmail.com
- Portfolio: https://chiragchhabra.vercel.app/
- GitHub: https://github.com/Chirag076
