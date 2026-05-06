"""Real ``yt-dlp`` based downloader worker.

Lifecycle:

1. ``extract_info(download=False)`` — pre-flight: check the source exists,
   read its size and duration. Reject with a clear error if the file would
   exceed :data:`bot.config.DOWNLOAD_MAX_FILESIZE_MB`.
2. ``YoutubeDL.download([url])`` — actually fetch the video, merging
   bestvideo + bestaudio into a single MP4 via ffmpeg.
3. Persist the yt-dlp ``info_dict`` to ``metadata.json`` and emit a
   structured ``result`` dict the analyzer stage can consume.

All filesystem writes go under ``DOWNLOADS_DIR / <job_id>/`` so concurrent
downloads can't collide. Progress is streamed to ``download.log`` in the
same dir; bot-side progress messages are wired up by a follow-up tentacle.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..config import (
    DOWNLOAD_MAX_FILESIZE_MB,
    DOWNLOAD_MAX_HEIGHT,
    DOWNLOADS_DIR,
    YT_COOKIES_FILE,
)
from ..jobs import Job
from .base import Worker

logger = logging.getLogger(__name__)


class DownloaderWorker(Worker):
    kind = "download"
    next_kind = "analyze"

    async def process(self, job: Job) -> dict[str, Any]:
        url = (job.payload.get("url") or "").strip()
        if not url:
            raise ValueError("download payload missing 'url'")
        max_height = int(job.payload.get("max_height") or DOWNLOAD_MAX_HEIGHT)
        max_filesize_mb = int(
            job.payload.get("max_filesize_mb") or DOWNLOAD_MAX_FILESIZE_MB
        )
        max_filesize_bytes = max_filesize_mb * 1024 * 1024

        job_dir = DOWNLOADS_DIR / str(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        log_path = job_dir / "download.log"

        # yt-dlp is sync (blocking); run it in the default executor so the
        # async worker loop stays responsive.
        return await asyncio.to_thread(
            self._download_blocking,
            url=url,
            job_dir=job_dir,
            log_path=log_path,
            max_height=max_height,
            max_filesize_bytes=max_filesize_bytes,
        )

    @staticmethod
    def _download_blocking(
        *,
        url: str,
        job_dir: Path,
        log_path: Path,
        max_height: int,
        max_filesize_bytes: int,
    ) -> dict[str, Any]:
        # Pre-flight: extract metadata only. Cheaper than downloading and
        # gives us a chance to reject oversized sources up front.
        info_opts = _ydl_options(
            job_dir=job_dir,
            log_path=log_path,
            max_height=max_height,
            quiet=True,
        )
        with YoutubeDL(info_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except DownloadError as exc:
                raise RuntimeError(f"yt-dlp pre-flight failed: {exc}") from exc
        if info is None:
            raise RuntimeError("yt-dlp returned no metadata for url")
        # Some extractors return playlists; we only handle a single entry.
        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            if not entries:
                raise RuntimeError("yt-dlp returned an empty playlist")
            info = entries[0]

        approx_bytes = (
            info.get("filesize")
            or info.get("filesize_approx")
            or 0
        )
        if approx_bytes and approx_bytes > max_filesize_bytes:
            raise RuntimeError(
                f"source too big: ~{approx_bytes // (1024 * 1024)} MB exceeds "
                f"cap of {max_filesize_bytes // (1024 * 1024)} MB"
            )

        # Real download.
        download_opts = _ydl_options(
            job_dir=job_dir,
            log_path=log_path,
            max_height=max_height,
            quiet=False,
        )
        with YoutubeDL(download_opts) as ydl:
            try:
                final_info = ydl.extract_info(url, download=True)
            except DownloadError as exc:
                raise RuntimeError(f"yt-dlp download failed: {exc}") from exc
        if final_info is None:
            raise RuntimeError("yt-dlp returned no info after download")
        if final_info.get("_type") == "playlist":
            entries = final_info.get("entries") or []
            if not entries:
                raise RuntimeError("yt-dlp playlist had no entries")
            final_info = entries[0]

        # Persist the info_dict next to the source. ``default=str`` handles
        # the few non-JSON-able fields yt-dlp occasionally returns (paths,
        # datetime objects).
        metadata_path = job_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(final_info, ensure_ascii=False, indent=2, default=str)
        )

        # Locate the actual on-disk file. yt-dlp may have transmuxed it.
        source_path = _resolve_source_path(final_info, job_dir)
        if source_path is None or not source_path.exists():
            raise RuntimeError(
                "downloaded file not found on disk; check yt-dlp output template"
            )

        return {
            "url": url,
            "source_path": str(source_path),
            "metadata_path": str(metadata_path),
            "duration_s": float(final_info.get("duration") or 0.0),
            "title": final_info.get("title") or "",
            "uploader": final_info.get("uploader") or "",
            "original_url": final_info.get("webpage_url") or url,
            "width": final_info.get("width"),
            "height": final_info.get("height"),
            "fps": final_info.get("fps"),
            "language": final_info.get("language"),
        }


def _ydl_options(
    *,
    job_dir: Path,
    log_path: Path,
    max_height: int,
    quiet: bool,
) -> dict[str, Any]:
    """Build a ``YoutubeDL`` option dict shared by pre-flight and download."""
    outtmpl = str(job_dir / "source.%(ext)s")
    fmt = (
        f"bestvideo[height<={max_height}]+bestaudio/"
        f"best[height<={max_height}]/best"
    )
    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "format": fmt,
        "merge_output_format": "mp4",
        "noprogress": False,
        "quiet": quiet,
        "no_warnings": quiet,
        "logger": _FileLogger(log_path),
        "progress_hooks": [_make_progress_hook(log_path)],
        "retries": 3,
        "fragment_retries": 3,
        # Stay polite — single connection, no aria2c speedups by default.
        "concurrent_fragment_downloads": 1,
        # Skip livestreams; they don't make sense as a video source for
        # the pipeline.
        "match_filter": _no_live_filter,
    }
    if YT_COOKIES_FILE:
        opts["cookiefile"] = YT_COOKIES_FILE
    return opts


def _no_live_filter(info_dict: dict[str, Any]) -> str | None:
    """yt-dlp ``match_filter``: skip live broadcasts."""
    if info_dict.get("is_live"):
        return "live broadcast not supported"
    return None


def _make_progress_hook(log_path: Path):
    """Append yt-dlp progress events to ``log_path`` for later inspection."""

    def hook(d: dict[str, Any]) -> None:
        status = d.get("status", "?")
        line: str
        if status == "downloading":
            pct = d.get("_percent_str", "??")
            speed = d.get("_speed_str", "??")
            eta = d.get("_eta_str", "??")
            line = f"[downloading] {pct} speed={speed} eta={eta}"
        elif status == "finished":
            filename = d.get("filename", "?")
            line = f"[finished] {filename}"
        else:
            line = f"[{status}] {d.get('filename', '')}"
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            # Logging failure must not abort a download.
            logger.warning("progress log write failed: %s", exc)

    return hook


class _FileLogger:
    """yt-dlp logger adapter that mirrors output into a job-local file."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def _emit(self, level: str, msg: str) -> None:
        try:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"[{level}] {msg}\n")
        except OSError:
            pass
        getattr(logger, level, logger.info)(msg)

    def debug(self, msg: str) -> None:  # noqa: D401 — yt-dlp interface
        # yt-dlp prefixes "real" debug output with "[debug] ".
        if msg.startswith("[debug] "):
            return
        self._emit("debug", msg)

    def info(self, msg: str) -> None:
        self._emit("info", msg)

    def warning(self, msg: str) -> None:
        self._emit("warning", msg)

    def error(self, msg: str) -> None:
        self._emit("error", msg)


def _resolve_source_path(info: dict[str, Any], job_dir: Path) -> Path | None:
    """Find the concrete file yt-dlp wrote, regardless of extension."""
    # Newer yt-dlp records the final filename in ``requested_downloads``.
    for entry in info.get("requested_downloads") or []:
        path = entry.get("filepath") or entry.get("_filename")
        if path:
            p = Path(path)
            if p.exists():
                return p
    # Older releases just expose ``_filename``.
    legacy = info.get("_filename")
    if legacy and Path(legacy).exists():
        return Path(legacy)
    # Fallback: glob for the merged output template.
    for candidate in job_dir.glob("source.*"):
        if candidate.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
            return candidate
    return None
