import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for chunk in (raw or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return out


# Which farm role this process represents — see bot/persona.py. Defaults
# to "boss" so a single-bot deploy (the original @openaiopus_bot setup)
# keeps working unchanged.
BOT_PERSONA = os.environ.get("BOT_PERSONA", "boss").strip().lower()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ALLOWED_USER_IDS = _split_ids(os.environ.get("ALLOWED_USER_IDS", ""))

# Default to polling so a freshly-deployed container works without any
# webhook URL setup. Switch to ``webhook`` + set ``PUBLIC_URL`` for
# production scale.
MODE = os.environ.get("BOT_MODE", "polling")
PORT = int(os.environ.get("PORT", "8080"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
WEBHOOK_PATH = f"/tg/{BOT_TOKEN.split(':', 1)[0]}"
WEBHOOK_URL = f"{PUBLIC_URL}{WEBHOOK_PATH}" if PUBLIC_URL else ""


def _resolve_keepalive_url() -> str:
    """Best-effort detect the bot's own public URL for self-pinging.

    Render, Railway, Fly.io expose this as platform-specific env vars; if
    none of them are set, fall back to ``KEEP_ALIVE_URL`` or ``PUBLIC_URL``.
    Returns empty string when no URL is known (local dev / VPS) — caller
    should treat that as "self-ping disabled".
    """
    explicit = os.environ.get("KEEP_ALIVE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    render = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if render:
        return render
    rw_dom = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if rw_dom:
        return f"https://{rw_dom}"
    fly_app = os.environ.get("FLY_APP_NAME", "").strip()
    if fly_app:
        return f"https://{fly_app}.fly.dev"
    return PUBLIC_URL


# Self-ping keeps Render Free (15-minute idle timer) awake. By default we
# pick a random delay between MIN and MAX seconds, biased toward MAX so
# the pattern doesn't look like a fixed cron interval. Set
# ``KEEP_ALIVE_INTERVAL=N`` to use a fixed N-second interval instead, or
# ``KEEP_ALIVE_INTERVAL=0`` to disable self-pinging entirely (e.g. on Fly
# always-on or your own VPS).
KEEP_ALIVE_URL = _resolve_keepalive_url()

_raw_interval = os.environ.get("KEEP_ALIVE_INTERVAL", "").strip()
if _raw_interval == "":
    KEEP_ALIVE_INTERVAL: int | None = None  # random mode
else:
    KEEP_ALIVE_INTERVAL = int(_raw_interval)  # 0 disables, >0 fixed

KEEP_ALIVE_MIN_SECONDS = int(os.environ.get("KEEP_ALIVE_MIN_SECONDS", "240"))  # 4 min
KEEP_ALIVE_MAX_SECONDS = int(os.environ.get("KEEP_ALIVE_MAX_SECONDS", "420"))  # 7 min
KEEP_ALIVE_BIAS = float(os.environ.get("KEEP_ALIVE_BIAS", "0.8"))

DEFAULT_MODEL = os.environ.get("MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
# Backward-compat alias for older imports.
MODEL = DEFAULT_MODEL
FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "FALLBACK_MODELS",
        "openai/gpt-oss-120b:free,qwen/qwen3-coder:free,minimax/minimax-m2.5:free",
    ).split(",")
    if m.strip()
]

DATA_DIR = Path(os.environ.get("DATA_DIR", "/tmp/bot-data"))
PROJECTS_DIR = DATA_DIR / "projects"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Lilush pipeline: SQLite-backed job queue + worker poll cadence.
JOBS_DB_PATH = DATA_DIR / "jobs.db"
WORKER_POLL_INTERVAL_S = float(os.environ.get("WORKER_POLL_INTERVAL_S", "1.0"))

# Downloader stage (yt-dlp).
DOWNLOADS_DIR = DATA_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_MAX_FILESIZE_MB = int(os.environ.get("DOWNLOAD_MAX_FILESIZE_MB", "5000"))
DOWNLOAD_MAX_HEIGHT = int(os.environ.get("DOWNLOAD_MAX_HEIGHT", "1080"))
# Optional: Netscape-format cookies file passed to yt-dlp for restricted
# content (age-gate / region-locked). Empty == no cookies.
YT_COOKIES_FILE = os.environ.get("YT_COOKIES_FILE", "").strip()

# Analyzer stage (faster-whisper + pyscenedetect + LLM ranker).
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
ANALYZER_TARGET_CLIPS = int(os.environ.get("ANALYZER_TARGET_CLIPS", "3"))
ANALYZER_CLIP_MIN_S = float(os.environ.get("ANALYZER_CLIP_MIN_S", "15"))
ANALYZER_CLIP_MAX_S = float(os.environ.get("ANALYZER_CLIP_MAX_S", "60"))
# Threshold (0-100) for pyscenedetect's ContentDetector.
SCENEDETECT_THRESHOLD = float(os.environ.get("SCENEDETECT_THRESHOLD", "27"))

# Editor stage (ffmpeg crop / scale / overlay).
EDITOR_OUTPUT_WIDTH = int(os.environ.get("EDITOR_OUTPUT_WIDTH", "1080"))
EDITOR_OUTPUT_HEIGHT = int(os.environ.get("EDITOR_OUTPUT_HEIGHT", "1920"))
EDITOR_VIDEO_CRF = int(os.environ.get("EDITOR_VIDEO_CRF", "23"))
EDITOR_AUDIO_BITRATE = os.environ.get("EDITOR_AUDIO_BITRATE", "128k")
EDITOR_VIDEO_PRESET = os.environ.get("EDITOR_VIDEO_PRESET", "medium")
# Optional PNG (with alpha) burned into the bottom-right of every clip.
# Empty == no overlay.
OVERLAY_LOGO_PATH = os.environ.get("OVERLAY_LOGO_PATH", "").strip()
OVERLAY_MARGIN_PX = int(os.environ.get("OVERLAY_MARGIN_PX", "40"))

# SEO stage (pytrends + LLM-generated metadata).
SEO_LLM_MODEL = os.environ.get("SEO_LLM_MODEL", "openai/gpt-4o-mini")
SEO_MAX_TAGS = int(os.environ.get("SEO_MAX_TAGS", "15"))
SEO_TITLE_MAX_LEN = int(os.environ.get("SEO_TITLE_MAX_LEN", "90"))
SEO_DESCRIPTION_MAX_LEN = int(os.environ.get("SEO_DESCRIPTION_MAX_LEN", "500"))

# Publisher stage. DRY-RUN packages metadata + clip into a release dir;
# real uploaders are separate tentacles that consume that release.
RELEASES_DIR = DATA_DIR / "releases"
RELEASES_DIR.mkdir(parents=True, exist_ok=True)
# When True (default) we never call upload APIs — just stage the files.
PUBLISHER_DRY_RUN = os.environ.get("PUBLISHER_DRY_RUN", "true").lower() != "false"
# Default privacy status on YouTube; user flips to public manually.
PUBLISHER_YT_PRIVACY = os.environ.get("PUBLISHER_YT_PRIVACY", "private")
PUBLISHER_YT_CATEGORY_ID = os.environ.get("PUBLISHER_YT_CATEGORY_ID", "22")

EXEC_TIMEOUT = int(os.environ.get("EXEC_TIMEOUT", "30"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", "200000"))
HISTORY_LIMIT = int(os.environ.get("HISTORY_LIMIT", "20"))
AGENT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "8"))

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HTTP_REFERER = os.environ.get("HTTP_REFERER", "https://github.com/")
APP_TITLE = os.environ.get("APP_TITLE", "Lilush")
