# Glow Salon Concierge: a Telegram AI booking agent

[![CI](https://github.com/Chirag076/salonConciergeBot/actions/workflows/ci.yml/badge.svg)](https://github.com/Chirag076/salonConciergeBot/actions/workflows/ci.yml)

An AI concierge on **Telegram** that chats with customers in plain language, answers questions about a salon's services, and **books, reschedules and cancels appointments** through conversation. It's an agentic LLM app: it doesn't just reply, it takes real actions against a database.

The design goal is an agent you can trust with a real business: **every price, slot and booking ID it tells a customer comes from a tool call, never from the model's memory**, double bookings are impossible at the database level, and every change is checked by an automated eval suite.

## Demo

**[Watch the full demo video →](https://drive.google.com/file/d/14jerL5v7q92tbmNTvLsdB3axggYMKE9h/view?usp=sharing)**

Booking an appointment, rescheduling it and cancelling it, all through natural conversation on Telegram. Bot: [@salonConciergeBot](https://t.me/salonConciergeBot)

## What it does

- Natural-language chat on Telegram, no forms or button menus
- Answers questions about services, prices and hours, from live data
- Checks free slots, then **books** appointments and returns a booking ID
- **Reschedules** and **cancels** existing bookings by ID
- Refuses off-menu services, closed days, past times and taken slots, and offers free alternatives
- Remembers each customer's conversation, so multi-step booking feels natural

## How it works

```
Customer message (Telegram)
        ↓
   Gemini agent ──decides──▶ calls a tool ──reads/writes──▶ SQLite
        ↓                    (booking.py)                    UNIQUE (date, time)
   Plain-language reply
```

The agent chooses between five tools on its own. They live in `booking.py`, which has no Telegram or Gemini code, so it is fully unit-tested.

| Tool | What it does |
|------|--------------|
| `list_services()` | The real menu, prices and opening hours |
| `check_availability(date)` | Free one-hour slots on a date |
| `book_appointment(name, service, date, time)` | Validates service, day, hours and slot, then saves and returns a booking ID |
| `reschedule_appointment(booking_id, new_date, new_time)` | Moves a booking, refusing taken or closed slots |
| `cancel_appointment(booking_id)` | Cancels a booking and frees the slot |

### Guardrails that don't depend on the prompt

- **No invented prices or services.** The system prompt contains no menu at all. The agent has to call `list_services`, and `book_appointment` rejects anything not on the menu.
- **No double bookings.** A `UNIQUE (date, time)` index means the database itself rejects a second booking for the same slot, even if two customers book at the same instant. A test fires 12 concurrent bookings at one slot and checks that exactly one succeeds.
- **Survives a busy AI provider.** Temporary Gemini errors (503 overloaded, 429 rate limited) are retried with growing waits; real errors are not retried, and the customer gets a polite message instead of silence.
- **No impossible bookings.** Mondays, past dates, times outside 10:00 to 19:00 and free-text dates are rejected by the tool, with a reason the agent can pass on.

## Testing

Two layers, both run in [GitHub Actions](.github/workflows/ci.yml) on every push.

**1. Unit tests** (`tests/`, 21 tests, no API key needed): booking rules, double-booking, 12-way concurrency, opening hours, reschedule, cancel, and retrying temporary Gemini outages.

```bash
pip install -r requirements-dev.txt
pytest -v
```

**2. Agent evals** (`eval.py`, 13 scenarios): real customer messages sent through the real Gemini agent, then the database and the agent's tool calls are checked. Covers bookings, reschedule, cancel, off-menu services, a taken slot, a closed Monday, and whether a price question is answered by calling `list_services`. Runs on a throwaway database and exits non-zero on any failure.

```bash
python eval.py
```

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

### With Docker

```bash
docker build -t salon-concierge .
docker run -d --env-file .env -v salon-data:/data salon-concierge
```

Bookings are stored on the `salon-data` volume, so they survive restarts.

## Tech stack

- **Python**
- **Google Gemini**: LLM with automatic function calling
- **pyTelegramBotAPI**: Telegram Bot API
- **SQLite**: bookings, with a unique index as the double-booking guard
- **pytest** and **GitHub Actions**: unit tests and agent evals on every push
- **Docker**

## What I learned

- Reliability in an agent comes from system design more than prompt wording: tool-only facts and database constraints guarantee what a prompt can only encourage.
- Agent behaviour needs tests like any other code, so the eval suite runs after every prompt or tool change.
- Designing tools with clear errors ("13:00 is taken, free slots: 14:00, 15:00") lets the model recover gracefully instead of guessing.

## Next

- Look up bookings by phone number instead of ID
- Multiple stylists, with per-stylist slots
- Postgres for production, and a WhatsApp channel

## Contact

Built by **Chirag Chhabra**.

- Email: chiragchhabrahmo@gmail.com
- Portfolio: https://portfolio.evrrun.com
- GitHub: https://github.com/Chirag076
