"""Stub SEO worker.

The real implementation will call the configured LLM with a prompt
specialised per platform (YT Shorts / TikTok / IG Reels), augmented
with trending-tag data from Google Trends or platform search. The
stub returns a hard-coded title/description/tags blob.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class SeoWorker(Worker):
    kind = "seo"
    next_kind = "publish"

    async def process(self, job: Job) -> dict[str, Any]:
        clip_path = job.payload.get("clip_path", "<unknown>")
        hook = job.payload.get("hook", "")
        logger.info("[stub] would generate SEO for %s", clip_path)
        await asyncio.sleep(0.5)
        title = (hook or f"Stub clip {job.id}")[:90]
        return {
            "clip_path": clip_path,
            "title": title,
            "description": f"{hook}\n\n#shorts #stub #lilush",
            "tags": ["shorts", "stub", "lilush"],
        }
