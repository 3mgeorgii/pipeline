FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    PORT=8080

WORKDIR /app

# Base system deps. Includes Node.js (for vercel-labs/agent-browser CLI
# that research bots invoke via shell) and Chrome runtime libs so the
# bundled Chrome from agent-browser can launch headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates curl gnupg \
        # Chrome runtime dependencies (libs needed by headless Chrome) —
        # let agent-browser / browser-harness install Chrome itself.
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 libasound2 libdrm2 fonts-liberation \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install agent-browser CLI globally. We DO NOT run `agent-browser
# install` here (it downloads ~200MB of Chrome). Researcher bots that
# actually need a browser will run it lazily on first use, storing
# Chrome under /data so it persists across redeploys without bloating
# the image.
RUN npm install -g agent-browser@latest

# Install browser-harness (self-healing CDP harness from browser-use).
# Cloned to /opt so it's outside the app code; installed editable so
# the agent's runtime edits to agent-workspace/agent_helpers.py
# persist across the running bot's lifetime. Researcher bots invoke
# the `browser-harness` binary through the shell-tool.
RUN git clone --depth=1 https://github.com/browser-use/browser-harness /opt/browser-harness \
    && pip install --no-cache-dir -e /opt/browser-harness

# python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# app code
COPY bot/ /app/bot/

# data dir for persisted state.json + Chrome cache from agent-browser
RUN mkdir -p /data

EXPOSE 8080
CMD ["python", "-m", "bot.main"]
