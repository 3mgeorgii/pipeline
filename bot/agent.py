import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from openai import AsyncOpenAI
from openai._exceptions import APIError

from .config import (
    AGENT_MAX_STEPS,
    APP_TITLE,
    DEFAULT_MODEL,
    FALLBACK_MODELS,
    HTTP_REFERER,
    OPENROUTER_BASE_URL,
)
from .storage import storage
from .token_tracker import record as record_token_usage
from .tools import TOOL_DEFINITIONS, ToolError, dispatch_tool

# Coroutine the agent calls to push a mini-status string to the user
# ("🔄 Думаю...", "🔄 Вызываю tool list_dir", "✅ Готово", ...).
# Empty no-op default is used in non-Telegram contexts (tests / CLI).
StatusUpdate = Callable[[str], Awaitable[None]]


async def _noop_status(_: str) -> None:
    return None

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous coding agent that operates inside a Telegram bot.

Rules:
- Always answer in the user's language (Russian by default for this user).
- You have access to tools: list_dir, read_file, write_file, exec_bash. Use them whenever the user asks you to look at, change, or run something. Do not invent file contents — read them.
- Be concise: in chat replies aim for short paragraphs. Long file content goes via tools, not into the reply.
- After making changes, suggest a git commit message; do not commit unless the user confirms or explicitly asks.
- If the user asks for git operations, use exec_bash with git commands.
- If no project is selected, tell the user to run /clone <url> or /project <name> first.
"""


class NoApiKeyError(RuntimeError):
    """Raised when no usable provider key is configured anywhere."""


def _build_client() -> AsyncOpenAI:
    """Create a fresh OpenAI client per request so /setkey takes effect immediately.

    Picks the endpoint based on ``storage.get_provider()``:
      - ``openrouter`` (default): hits https://openrouter.ai/api/v1
      - ``custom``: hits ``storage.get_base_url()`` — set via /setup wizard
        for self-hosted endpoints (vLLM, Ollama, Together, Groq, etc.).
    """
    api_key = storage.get_provider_key("openrouter")
    provider = storage.get_provider()
    if provider == "custom":
        base_url = storage.get_base_url() or OPENROUTER_BASE_URL
    else:
        base_url = OPENROUTER_BASE_URL

    if not api_key:
        if provider == "custom":
            raise NoApiKeyError(
                "Не задан API-ключ для кастомного endpoint-а. Открой /setup → 🔑 API ключ."
            )
        raise NoApiKeyError(
            "Не задан ключ OpenRouter. Поставь его командой:\n"
            "<code>/setkey openrouter sk-or-...</code>\n"
            "Получить ключ: https://openrouter.ai/keys"
        )

    headers = {"HTTP-Referer": HTTP_REFERER, "X-Title": APP_TITLE}
    return AsyncOpenAI(api_key=api_key, base_url=base_url, default_headers=headers)


def _candidate_models() -> list[str]:
    """Active model first, then free fallbacks only if active itself is free.

    Premium models (e.g. ``anthropic/claude-opus-4.5``) intentionally do NOT
    fall back to free models — silent downgrade would be confusing.
    """
    active = storage.get_model() or DEFAULT_MODEL
    candidates = [active]
    is_free = ":free" in active or active in FALLBACK_MODELS
    if is_free:
        for m in FALLBACK_MODELS:
            if m != active and m not in candidates:
                candidates.append(m)
    return candidates


def _build_messages(user_id: int, user_text: str) -> list[dict]:
    history = storage.get_history(user_id)
    return (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_text}]
    )


async def _call_model(
    client: AsyncOpenAI, messages: list[dict], purpose: str = "chat"
) -> tuple[object, str]:
    """Call the active model with fallback. Logs token usage on success."""
    last_error: Exception | None = None
    for model in _candidate_models():
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                temperature=0.2,
            )
            usage = getattr(resp, "usage", None)
            if usage is not None:
                pt = getattr(usage, "prompt_tokens", 0) or 0
                ct = getattr(usage, "completion_tokens", 0) or 0
                try:
                    record_token_usage(
                        provider=storage.get_provider(),
                        model=model,
                        prompt_tokens=int(pt),
                        completion_tokens=int(ct),
                        purpose=purpose,
                    )
                except Exception:  # noqa: BLE001 — never crash on stats
                    logger.exception("token-tracker recording failed")
            return resp.choices[0].message, model
        except APIError as exc:
            logger.warning("model %s failed: %s", model, exc)
            last_error = exc
    raise RuntimeError(f"all models failed: {last_error}")


async def run_agent(
    user_id: int,
    user_text: str,
    cwd: Path | None,
    on_status: StatusUpdate | None = None,
) -> str:
    """Run the agent loop. ``on_status`` is called with progress strings
    for the mini-status indicator (caller edits a single TG message)."""
    status = on_status or _noop_status

    client = _build_client()
    messages = _build_messages(user_id, user_text)
    final_text = ""
    requested_model = storage.get_model() or DEFAULT_MODEL
    used_model = requested_model

    await status(f"🔄 Думаю... ({requested_model})")

    for step in range(AGENT_MAX_STEPS):
        await status(f"🔄 Шаг {step + 1}: вызываю LLM…")
        msg, used_model = await _call_model(client, messages)
        tool_calls = getattr(msg, "tool_calls", None) or []

        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if not tool_calls:
            final_text = msg.content or ""
            break

        # Surface tool activity to the user so they see what the bot is doing.
        names = ", ".join(tc.function.name for tc in tool_calls)
        await status(f"🔧 Шаг {step + 1}: использую {names}")

        for tc in tool_calls:
            try:
                result = await dispatch_tool(tc.function.name, tc.function.arguments, cwd)
            except ToolError as exc:
                result = f"ERROR: {exc}"
            except Exception as exc:  # noqa: BLE001
                logger.exception("tool %s crashed", tc.function.name)
                result = f"ERROR: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": result[:8000],
                }
            )
    else:
        final_text = (
            "(превышен лимит шагов агента — попробуй упростить запрос или /reset)"
        )

    storage.append_history(user_id, {"role": "user", "content": user_text})
    if final_text:
        storage.append_history(user_id, {"role": "assistant", "content": final_text})

    if used_model != requested_model:
        final_text = f"[fallback model: {used_model}]\n{final_text}"
    await status("✅ Готово")
    return final_text or "(пустой ответ)"
