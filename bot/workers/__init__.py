"""Workers that pull jobs from the SQLite queue and chain pipeline stages.

Each worker subclasses :class:`bot.workers.base.Worker` and overrides
``process()``. The base class handles polling, status transitions and
failure paths so concrete workers stay focused on their stage logic.
"""

from .analyzer import AnalyzerWorker
from .base import Worker
from .downloader import DownloaderWorker
from .editor import EditorWorker
from .publisher import PublisherWorker
from .seo import SeoWorker

__all__ = [
    "AnalyzerWorker",
    "DownloaderWorker",
    "EditorWorker",
    "PublisherWorker",
    "SeoWorker",
    "Worker",
]
