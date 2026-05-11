import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from openai import AsyncOpenAI
from openai._exceptions import APIError

from .config import (
    AGENT_MAX_STEPS,
    AGENT_MAX_TOKENS,
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

# Base system rules shared by every persona. Persona-specific framing is
# appended in ``_build_system_prompt()`` below depending on whether the
# user has selected a role via /role.
_BASE_RULES = """You are a Telegram bot assistant.

General rules:
- Always answer in the user's language (Russian by default for this user).
- You have access to tools: list_dir, read_file, write_file, exec_bash. Use them whenever the user asks you to look at, change, or run something. Do not invent file contents — read them.
- Be concise: in chat replies aim for short paragraphs. Long file content goes via tools, not into the reply.
- After making changes, suggest a git commit message; do not commit unless the user confirms or explicitly asks.
- If the user asks for git operations, use exec_bash with git commands.
- A working project (CWD) is optional. If the user asks about files / code / shell and no project is set, gently mention they can run /clone <url> or /project <name>. For ordinary chat, just respond — do not block on a missing project.
"""

# Free-chat framing used before the user picks a role via /role. The bot
# is encouraged to chat openly about anything so the user can probe its
# capabilities. Triggered when active persona is the default ``boss`` AND
# no override is set.
_DISCOVERY_FRAMING = """
Mode: DISCOVERY (no specific role selected yet).
The user is exploring your capabilities. Chat freely on any topic — casual conversation, technical help, file/code work, opinions, jokes — whatever they ask. If they ask "what can you do?" or "who are you?", answer openly.
Tell them they can run /role at any time to switch into a specialized persona (researcher, debater, coder, devops, etc.) once they want to focus your behavior.
"""

# Role-framing used after the user has picked a non-default persona. The
# bot is constrained to stay on-task within that role.
_ROLE_FRAMING_TEMPLATE = """
Your role: {display_name} — {title}.
Department: {department}. Rank: {rank}.

Role brief: {description}

STAY IN ROLE. Focus strictly on tasks that fit your role above. If the user asks for something far outside this role (e.g. asks a Research Lead to write code, or asks a Watchdog to run a debate), politely redirect: tell them which role would be appropriate and suggest they run /role to switch.
Don't break character. Don't help with arbitrary off-topic requests — keep the user on-task.
"""


def _build_system_prompt() -> str:
    """Compose the system prompt based on the active persona and override.

    The user's most-recent feedback: before /role is chosen, allow free
    chat so they can probe the bot. After /role is chosen, constrain the
    bot to that role's brief so it doesn't scatter across topics.
    """
    # Lazy import to keep the module graph acyclic.
    from .persona import get_persona

    persona = get_persona()
    override = storage.get_persona_override()
    is_default_boss = persona.key == "boss" and not override

    if is_default_boss:
        return _BASE_RULES + _DISCOVERY_FRAMING
    return _BASE_RULES + _ROLE_FRAMING_TEMPLATE.format(
        display_name=persona.display_name,
        title=persona.title,
        department=persona.department,
        rank=persona.rank,
        description=persona.description,
    )


# Backwards-compat alias for callers/tests that imported the constant
# directly. ``_build_system_prompt()`` is the authoritative source.
SYSTEM_PROMPT = _BASE_RULES + _DISCOVERY_FRAMING


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
        [{"role": "system", "content": _build_system_prompt()}]
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
                max_tokens=AGENT_MAX_TOKENS,
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
