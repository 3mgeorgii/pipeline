import contextlib
import json
import os
from pathlib import Path

from .config import DATA_DIR, HISTORY_LIMIT, PROJECTS_DIR

# Settings live under this key inside state.json so they don't collide with
# user-id-keyed entries (Telegram user ids are stringified ints).
_SETTINGS_KEY = "_settings"

# LLM providers we know about. Each entry maps to a UI label and the env-var
# that acts as a fallback when nothing has been set via Telegram.
KNOWN_PROVIDERS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# External research/scraping tools that the bot may need to authenticate
# against. Researcher-type bots (github_scout, reddit_scout, apify_runner,
# etc.) read these via ``storage.get_external_tool_key("apify")`` when they
# perform their work. Each value is the env-var fallback name.
#
# Adding a new tool here automatically adds a button to the /setup wizard
# under "🔑 Внешние API" — no UI changes needed.
KNOWN_EXTERNAL_TOOLS: dict[str, dict[str, str]] = {
    "apify": {
        "env_var": "APIFY_API_TOKEN",
        "label": "Apify",
        "url": "https://console.apify.com/account/integrations",
        "hint": "Готовые scrap-actors для Reddit / TikTok / YT / Twitter и др.",
    },
    "firecrawl": {
        "env_var": "FIRECRAWL_API_KEY",
        "label": "Firecrawl",
        "url": "https://firecrawl.dev/app/api-keys",
        "hint": "Превращает любой сайт в чистый markdown для LLM.",
    },
    "tavily": {
        "env_var": "TAVILY_API_KEY",
        "label": "Tavily",
        "url": "https://app.tavily.com/home",
        "hint": "Search-API для AI-агентов (1000 запросов / мес бесплатно).",
    },
    "brave": {
        "env_var": "BRAVE_SEARCH_API_KEY",
        "label": "Brave Search",
        "url": "https://api-dashboard.search.brave.com/app/keys",
        "hint": "Альтернатива Google без трекинга (2000 / мес бесплатно).",
    },
    "exa": {
        "env_var": "EXA_API_KEY",
        "label": "Exa",
        "url": "https://dashboard.exa.ai/api-keys",
        "hint": "Семантический поиск (1000 / мес бесплатно).",
    },
    "github_pat": {
        "env_var": "GITHUB_RESEARCH_PAT",
        "label": "GitHub PAT (read-only)",
        "url": "https://github.com/settings/tokens",
        "hint": "Personal Access Token (Fine-grained, public-repo read) — поднимает rate-limit с 60 до 5000 запросов/час.",
    },
}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}***{key[-4:]}"


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.state_file.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
        # Best-effort chmod — platforms without POSIX permissions silently fall through.
        with contextlib.suppress(OSError):
            os.chmod(self.state_file, 0o600)

    # ---- per-user state -------------------------------------------------

    def _user(self, user_id: int) -> dict:
        key = str(user_id)
        if key not in self._state:
            self._state[key] = {"cwd": None, "history": []}
        return self._state[key]

    def get_cwd(self, user_id: int) -> Path | None:
        cwd = self._user(user_id).get("cwd")
        if cwd is None:
            return None
        path = Path(cwd)
        return path if path.exists() else None

    def set_cwd(self, user_id: int, path: Path) -> None:
        self._user(user_id)["cwd"] = str(path)
        self._save()

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._user(user_id).get("history", []))

    def append_history(self, user_id: int, message: dict) -> None:
        history = self._user(user_id).setdefault("history", [])
        history.append(message)
        if len(history) > HISTORY_LIMIT * 2:
            del history[: len(history) - HISTORY_LIMIT * 2]
        self._save()

    def clear_history(self, user_id: int) -> None:
        self._user(user_id)["history"] = []
        self._save()

    def list_projects(self) -> list[str]:
        if not PROJECTS_DIR.exists():
            return []
        return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())

    # ---- bot-wide settings (keys, model, enabled flag) ------------------

    def _settings(self) -> dict:
        return self._state.setdefault(_SETTINGS_KEY, {})

    def set_provider_key(self, provider: str, key: str) -> None:
        provider = provider.lower()
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(
                f"unknown provider '{provider}'. known: {', '.join(KNOWN_PROVIDERS)}"
            )
        keys = self._settings().setdefault("keys", {})
        keys[provider] = key
        self._save()

    def delete_provider_key(self, provider: str) -> bool:
        provider = provider.lower()
        keys = self._settings().get("keys", {})
        if provider in keys:
            del keys[provider]
            self._save()
            return True
        return False

    def get_provider_key(self, provider: str) -> str:
        """Return the key for ``provider`` from state, falling back to env."""
        provider = provider.lower()
        stored = self._settings().get("keys", {}).get(provider)
        if stored:
            return stored
        env_var = KNOWN_PROVIDERS.get(provider)
        if env_var:
            return os.environ.get(env_var, "")
        return ""

    def list_provider_keys(self) -> dict[str, dict]:
        """List known providers with the source and a masked preview."""
        out: dict[str, dict] = {}
        keys = self._settings().get("keys", {})
        for provider, env_var in KNOWN_PROVIDERS.items():
            stored = keys.get(provider, "")
            env_value = os.environ.get(env_var, "")
            active = stored or env_value
            out[provider] = {
                "source": "telegram" if stored else ("env" if env_value else "none"),
                "masked": _mask_key(active),
                "env_var": env_var,
            }
        return out

    # ---- external research/scraping tools -------------------------------

    def set_external_tool_key(self, tool: str, key: str) -> None:
        tool = tool.lower()
        if tool not in KNOWN_EXTERNAL_TOOLS:
            raise ValueError(
                f"unknown external tool '{tool}'. known: "
                f"{', '.join(KNOWN_EXTERNAL_TOOLS)}"
            )
        tools = self._settings().setdefault("external_tools", {})
        tools[tool] = key
        self._save()

    def delete_external_tool_key(self, tool: str) -> bool:
        tool = tool.lower()
        tools = self._settings().get("external_tools", {})
        if tool in tools:
            del tools[tool]
            self._save()
            return True
        return False

    def get_external_tool_key(self, tool: str) -> str:
        """Return the key for ``tool`` from state, falling back to env.

        Used by researcher-type bots (github_scout, apify_runner, etc.) to
        authenticate against external APIs. Returns empty string if the
        tool was never configured — callers must handle that explicitly.
        """
        tool = tool.lower()
        stored = self._settings().get("external_tools", {}).get(tool)
        if stored:
            return stored
        meta = KNOWN_EXTERNAL_TOOLS.get(tool)
        if meta is not None:
            return os.environ.get(meta["env_var"], "")
        return ""

    def list_external_tool_keys(self) -> dict[str, dict]:
        """List known external tools with source + masked preview."""
        out: dict[str, dict] = {}
        tools = self._settings().get("external_tools", {})
        for tool, meta in KNOWN_EXTERNAL_TOOLS.items():
            stored = tools.get(tool, "")
            env_value = os.environ.get(meta["env_var"], "")
            active = stored or env_value
            out[tool] = {
                "source": "telegram" if stored else ("env" if env_value else "none"),
                "masked": _mask_key(active),
                "env_var": meta["env_var"],
                "label": meta["label"],
                "url": meta["url"],
                "hint": meta["hint"],
            }
        return out

    def set_model(self, model: str) -> None:
        self._settings()["model"] = model
        self._save()

    def get_model(self) -> str:
        from .config import DEFAULT_MODEL  # local import to avoid cycles

        return self._settings().get("model") or DEFAULT_MODEL

    def is_enabled(self) -> bool:
        return bool(self._settings().get("enabled", True))

    # ---- brain mode (auto vs devin) -------------------------------------

    def get_brain(self) -> str:
        """Return current brain mode: ``auto`` (LLM via OpenRouter) or ``devin``.

        ``devin`` mode means the bot does NOT auto-reply; incoming messages
        are logged to ``data/inbox.log`` and a real Devin session (with shell
        access to the same VM) responds via ``python -m bot.send``.
        """
        return str(self._settings().get("brain", "auto"))

    def set_brain(self, mode: str) -> None:
        if mode not in ("auto", "devin"):
            raise ValueError(f"unknown brain mode '{mode}', expected 'auto' or 'devin'")
        self._settings()["brain"] = mode
        self._save()

    def set_enabled(self, enabled: bool) -> None:
        self._settings()["enabled"] = bool(enabled)
        self._save()

    # ---- owner (single-owner claim) -------------------------------------

    def get_owner_id(self) -> int | None:
        """Telegram user-id that owns this container, or ``None`` if unclaimed."""
        raw = self._settings().get("owner_id")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def set_owner_id(self, user_id: int) -> None:
        """Lock the container to a single Telegram user. Idempotent."""
        self._settings()["owner_id"] = int(user_id)
        self._save()

    # ---- LLM provider selection (auto-mode backend) ---------------------

    def get_provider(self) -> str:
        """Which LLM provider auto-mode talks to.

        Defaults to ``openrouter`` for backwards compatibility. Other valid
        values are ``custom`` (a self-hosted OpenAI-compatible endpoint) or
        ``devin`` (handled separately by brain=devin and ignored here).
        """
        return str(self._settings().get("provider", "openrouter"))

    def set_provider(self, provider: str) -> None:
        if provider not in ("openrouter", "custom"):
            raise ValueError(
                f"unknown provider '{provider}', expected 'openrouter' or 'custom'"
            )
        self._settings()["provider"] = provider
        self._save()

    def get_base_url(self) -> str:
        """Base URL for the active provider. Empty = use provider's default."""
        return str(self._settings().get("base_url", ""))

    def set_base_url(self, url: str) -> None:
        self._settings()["base_url"] = url.rstrip("/")
        self._save()

    # ---- persona override (per-bot role change from TG) ------------------

    def get_persona_override(self) -> str | None:
        """Read TG-set persona override. None = fall back to BOT_PERSONA env var.

        The override is set via the `/role` command and persists across
        restarts in state.json. Acts as a soft re-assignment without
        touching Render env vars.
        """
        raw = self._settings().get("persona_override")
        if raw and isinstance(raw, str):
            return raw.strip().lower() or None
        return None

    def set_persona_override(self, persona_key: str) -> None:
        """Lock this bot into a new persona until cleared."""
        self._settings()["persona_override"] = persona_key.strip().lower()
        self._save()

    def clear_persona_override(self) -> None:
        """Remove the override → fall back to BOT_PERSONA env var."""
        if "persona_override" in self._settings():
            del self._settings()["persona_override"]
            self._save()

    # ---- heartbeat OpenRouter (idle ping toggle) -------------------------

    def get_heartbeat_enabled(self) -> bool:
        """True if OpenRouter heartbeat pings are enabled.

        When enabled, a background task pings the OpenRouter API
        periodically with a tiny prompt to keep the connection warm
        (and burn a fraction of free-tier quota). Independent of which
        provider is currently the active brain.
        """
        return bool(self._settings().get("heartbeat_enabled", False))

    def set_heartbeat_enabled(self, enabled: bool) -> None:
        self._settings()["heartbeat_enabled"] = bool(enabled)
        self._save()

    # ---- token usage tracking --------------------------------------------

    def log_llm_call(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        purpose: str = "chat",
    ) -> None:
        """Record one LLM call's token usage.

        Stored as a flat list of dicts under ``_settings.token_log``. We
        cap the log at 5000 entries so state.json stays under a megabyte
        on long-running bots; older entries roll off FIFO.
        """
        import time

        log = self._settings().setdefault("token_log", [])
        log.append(
            {
                "ts": int(time.time()),
                "provider": provider,
                "model": model,
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "purpose": purpose,
            }
        )
        if len(log) > 5000:
            del log[: len(log) - 5000]
        self._save()

    def get_token_log(self, since_ts: int = 0) -> list[dict]:
        """Return token log entries with ``ts >= since_ts``."""
        log = self._settings().get("token_log", [])
        if since_ts <= 0:
            return list(log)
        return [e for e in log if e.get("ts", 0) >= since_ts]


storage = Storage()
