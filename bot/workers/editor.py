"""Stub editor worker.

The real implementation will run ffmpeg: cut the requested window from
the source, crop to vertical 1080×1920, optionally burn in subtitles
and overlay a watermark/end-card. The stub just constructs an output
path and pretends the work is done.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class EditorWorker(Worker):
    kind = "edit"
    next_kind = "seo"

    async def process(self, job: Job) -> dict[str, Any]:
        clip_index = job.payload.get("clip_index", 0)
        source_path = job.payload.get("source_path", "<unknown>")
        logger.info("[stub] would edit clip %s from %s", clip_index, source_path)
        await asyncio.sleep(1)
        return {
            "source_path": source_path,
            "clip_index": clip_index,
            "clip_path": f"/tmp/lilush/clips/{job.id}.mp4",
            "duration_s": float(job.payload.get("end_s", 0) - job.payload.get("start_s", 0)),
            "hook": job.payload.get("hook", ""),
        }
