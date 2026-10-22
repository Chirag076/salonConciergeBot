FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    SALON_DB=/data/bookings.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY booking.py salon_bot.py ./

# Bookings live on a volume so they survive restarts and redeploys.
VOLUME ["/data"]

CMD ["python", "salon_bot.py"]
