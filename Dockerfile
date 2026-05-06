FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    PORT=8080

WORKDIR /app

# system deps for git/clone helper inside the bot
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# app code
COPY bot/ /app/bot/

# data dir for persisted state.json
RUN mkdir -p /data

EXPOSE 8080
CMD ["python", "-m", "bot.main"]
