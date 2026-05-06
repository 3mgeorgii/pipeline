"""Stub publisher worker.

The real implementation will upload to YouTube / TikTok / Instagram
through their APIs (or unofficial libs for novel use cases) and
include configurable retry-on-rate-limit logic. The stub fabricates
a fake post URL and reports completion back to the chat owner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class PublisherWorker(Worker):
    kind = "publish"
    next_kind = None  # terminal stage

    async def process(self, job: Job) -> dict[str, Any]:
        clip_path = job.payload.get("clip_path", "<unknown>")
        title = job.payload.get("title", "")
        logger.info("[stub] would publish %s with title=%r", clip_path, title)
        await asyncio.sleep(0.5)
        post_url = f"https://example.invalid/stub/{job.id}"
        return {
            "clip_path": clip_path,
            "title": title,
            "post_url": post_url,
            "platform": "stub",
        }

    async def enqueue_next(self, job: Job, result: dict[str, Any]) -> None:
        """Terminal stage — notify the owner via Telegram if a chat is set."""
        if job.chat_id is None:
            return
        # Lazy import to avoid pulling aiogram into pure-jobs unit tests.
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode

            from ..config import BOT_TOKEN
        except Exception:
            logger.exception("[publisher] could not import aiogram for chat report")
            return

        text = (
            f"<b>Готово</b>: job #{job.id}\n"
            f"<i>{result.get('title', '')}</i>\n"
            f"{result.get('post_url')}"
        )
        bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            await bot.send_message(job.chat_id, text)
        finally:
            await bot.session.close()
