"""Stub downloader worker.

The real implementation will shell out to ``yt-dlp`` and stream progress
back to the chat. This stub just sleeps for a moment and returns a fake
file path so the rest of the pipeline can be exercised end-to-end.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class DownloaderWorker(Worker):
    kind = "download"
    next_kind = "analyze"

    async def process(self, job: Job) -> dict[str, Any]:
        url = job.payload.get("url")
        if not url:
            raise ValueError("download payload missing 'url'")
        logger.info("[stub] would download %s", url)
        # Pretend the download takes a couple of seconds — long enough
        # for the queue to look concurrent in logs.
        await asyncio.sleep(2)
        return {
            "url": url,
            "file_path": f"/tmp/lilush/sources/{job.id}/source.mp4",
            "duration_s": 5400,  # 90 min, plausible feature-length placeholder
            "title": f"stub-source-{job.id}",
        }
