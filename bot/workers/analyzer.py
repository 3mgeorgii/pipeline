"""Stub analyzer worker.

The real implementation will transcribe with faster-whisper, detect
scene cuts with pyscenedetect, then ask an LLM to rank moments worth
clipping. The stub just emits three fake clip windows so the editor
can fan out and exercise the multi-job branch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class AnalyzerWorker(Worker):
    kind = "analyze"
    next_kind = "edit"

    async def process(self, job: Job) -> dict[str, Any]:
        # Downloader emits ``source_path``; older callers used ``file_path``.
        source_path = job.payload.get("source_path") or job.payload.get("file_path")
        if not source_path:
            raise ValueError("analyze payload missing 'source_path'")
        logger.info("[stub] would analyze %s", source_path)
        await asyncio.sleep(1)
        clips = [
            {"start_s": 30.0, "end_s": 60.0, "hook": "stub clip 1"},
            {"start_s": 600.0, "end_s": 645.0, "hook": "stub clip 2"},
            {"start_s": 3000.0, "end_s": 3050.0, "hook": "stub clip 3"},
        ]
        return {"source_path": source_path, "clips": clips}

    async def enqueue_next(self, job: Job, result: dict[str, Any]) -> None:
        """Fan out: one ``edit`` job per detected clip."""
        source_path = result["source_path"]
        for idx, clip in enumerate(result.get("clips", [])):
            await self.queue.enqueue(
                self.next_kind or "edit",
                {
                    "source_path": source_path,
                    "clip_index": idx,
                    **clip,
                },
                chat_id=job.chat_id,
                parent_id=job.id,
            )
