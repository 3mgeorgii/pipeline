"""First-run setup wizard for the bot.

Flow when a fresh container starts up:

1. *Anyone* may click ``/start``. The first user who does so is locked in
   as the **owner** (single-tenant). All later messages from anyone else
   get a polite refusal.

2. Owner is shown a 3-button menu to pick a brain:

   - ``[OpenRouter]``  → opens API/Model/URL config sub-menu
   - ``[Devin.ai]``    → emits a copy-pasteable prompt for a new Devin session
   - ``[Другое]``      → same sub-menu as OpenRouter (custom OpenAI-compatible
     endpoint such as Together, Groq, vLLM, LM Studio, etc.)

3. In the API/Model/URL sub-menu each button starts an FSM step where the
   bot asks for that single field. Sensitive values (API key) get the
   user's message deleted right after capture.

The wizard handlers live in their own ``Router`` so ``handlers.py`` stays
focused on day-to-day commands. The wizard router is included by
``main.py`` *before* the main router so its callback queries take
priority.
"""

from __future__ import annotations

import contextlib
import logging
import os

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .persona import get_persona, list_personas
from .storage import storage

logger = logging.getLogger(__name__)
wizard_router = Router(name="wizard")


# ---- FSM states ----------------------------------------------------------


class SetupStates(StatesGroup):
    awaiting_api_key = State()
    awaiting_model = State()
    awaiting_url = State()
    # External research/scraping tools (Apify / Firecrawl / Tavily / ...).
    # We stash the chosen tool name in FSM data so the capture handler
    # knows which key to save.
    awaiting_external_tool_key = State()


# ---- Keyboards -----------------------------------------------------------


def _kb_claim() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить и стать владельцем", callback_data="claim_owner")]
        ]
    )


def _kb_brain() -> InlineKeyboardMarkup:
    hb_label = (
        "💓 Heartbeat OpenRouter: ON"
        if storage.get_heartbeat_enabled()
        else "💤 Heartbeat OpenRouter: OFF"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 OpenRouter (бесплатно/платно, рекомендую)", callback_data="brain:openrouter")],
            [InlineKeyboardButton(text="🎯 Devin.ai (ручные ответы через шелл)", callback_data="brain:devin")],
            [InlineKeyboardButton(text="⚙️  Другое (свой OpenAI-совместимый endpoint)", callback_data="brain:other")],
            [InlineKeyboardButton(text="🛠 Внешние API (Apify, Firecrawl, Tavily, ...)", callback_data="ext:menu")],
            [InlineKeyboardButton(text=hb_label, callback_data="brain:heartbeat_toggle")],
        ]
    )


def _kb_main_after_claim() -> InlineKeyboardMarkup:
    """Top-level menu shown to an authenticated owner after /start.

    Provides quick links into the most common flows so the owner does
    not have to remember slash-commands.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать видео", callback_data="main:download")],
            [InlineKeyboardButton(text="🎭 Сменить роль (/role)", callback_data="main:role")],
            [InlineKeyboardButton(text="🧠 Перенастроить мозг", callback_data="main:brain")],
            [InlineKeyboardButton(text="📊 Статистика токенов (/tokens)", callback_data="main:tokens")],
        ]
    )


def _kb_role_picker() -> InlineKeyboardMarkup:
    """Grid of every persona + 'Info' + 'Back' buttons.

    Each persona button switches the bot's role on click (with a confirm
    step). 20 entries arranged 2 per row keeps the keyboard compact on
    mobile.
    """
    personas = list_personas()
    rows: list[list[InlineKeyboardButton]] = []
    active = get_persona().key
    for i in range(0, len(personas), 2):
        row: list[InlineKeyboardButton] = []
        for p in personas[i : i + 2]:
            marker = "▶ " if p.key == active else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{marker}{p.display_name}",
                    callback_data=f"role:pick:{p.key}",
                )
            )
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="ℹ️ Инфо о ролях", callback_data="role:info"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="role:back"),
        ]
    )
    # If an override is active, show a button to revert to env-var default.
    if storage.get_persona_override() is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Сбросить override (вернуться к BOT_PERSONA)",
                    callback_data="role:reset",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_role_confirm(persona_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Использовать эту роль",
                    callback_data=f"role:use:{persona_key}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="role:back")],
        ]
    )


def _kb_external_tools() -> InlineKeyboardMarkup:
    """Menu of external research/scraping tools the bot may need to log in to.

    Reads the list from ``KNOWN_EXTERNAL_TOOLS`` in storage so adding a new
    tool there automatically grows the keyboard.
    """
    from .storage import KNOWN_EXTERNAL_TOOLS

    keys_state = storage.list_external_tool_keys()
    rows: list[list[InlineKeyboardButton]] = []
    for tool, meta in KNOWN_EXTERNAL_TOOLS.items():
        state = keys_state.get(tool, {})
        source = state.get("source", "none")
        marker = "✅" if source == "telegram" else ("🌍" if source == "env" else "⚪️")
        label = meta["label"]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker} {label}",
                    callback_data=f"ext:set:{tool}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️  Назад к мозгам", callback_data="ext:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_llm_config(provider_label: str) -> InlineKeyboardMarkup:
    """Sub-menu shown after OpenRouter / Other.

    All three fields are optional individually but at minimum API + Model
    are needed to make a request. The wizard does not enforce that — the
    first message to the bot will surface a clear error if something's
    missing.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔑 API ключ ({provider_label})", callback_data="cfg:api")],
            [InlineKeyboardButton(text="🤖 Модель", callback_data="cfg:model")],
            [InlineKeyboardButton(text="🌐 URL (только для Другое)", callback_data="cfg:url")],
            [InlineKeyboardButton(text="✅ Готово, поехали", callback_data="cfg:done")],
            [InlineKeyboardButton(text="↩️  Сменить мозг", callback_data="cfg:back")],
        ]
    )


# ---- Helpers -------------------------------------------------------------


def _is_owner(user_id: int) -> bool:
    owner = storage.get_owner_id()
    return owner is not None and owner == user_id


def _provider_label(brain_choice: str) -> str:
    return "openrouter" if brain_choice == "openrouter" else "custom"


# ---- Handlers ------------------------------------------------------------


@wizard_router.message(Command("start"))
async def cmd_start_wizard(message: Message, state: FSMContext) -> None:
    """Owner-aware /start.

    - Unclaimed: anyone may claim. Show big ``Запустить`` button.
    - Owner: re-enter the brain picker (``/setup`` is an alias).
    - Stranger: deny with their id so the *real* owner can spot a leak.
    """
    user = message.from_user
    if user is None:
        return
    await state.clear()

    persona = get_persona()
    owner = storage.get_owner_id()
    if owner is None:
        await message.answer(
            f"<b>Привет! Я {persona.display_name}.</b>\n"
            f"<i>{persona.title}</i>\n\n"
            f"{_html_escape(persona.description)}\n\n"
            "Ты только что развернул мой контейнер. Я не знаю кому теперь подчиняться — "
            "первый человек, кто нажмёт кнопку ниже, станет владельцем (только он сможет писать мне дальше).\n\n"
            f"Твой Telegram id: <code>{user.id}</code>",
            reply_markup=_kb_claim(),
        )
        return

    if owner != user.id:
        await message.answer(
            f"Я {persona.display_name}, и я уже привязан к другому владельцу. Если это твой контейнер и ты потерял доступ — "
            "удали в <code>data/state.json</code> поле <code>_settings.owner_id</code> и перезапусти бот.\n\n"
            f"Твой Telegram id: <code>{user.id}</code>"
        )
        return

    override = storage.get_persona_override()
    extra = (
        f"\n<i>(роль переопределена через /role — env BOT_PERSONA={_html_escape(os.environ.get('BOT_PERSONA', 'boss'))})</i>"
        if override is not None
        else ""
    )
    await message.answer(
        f"<b>{persona.display_name}</b> на связи. Ты владелец.{extra}\n\n"
        f"<i>{persona.title}</i>\n\n"
        "Что хочешь? Жми кнопку или используй команду:\n"
        "• <code>/dl &lt;url&gt;</code> — скачать видео в конвейер\n"
        "• <code>/role</code> — сменить роль этого бота\n"
        "• <code>/setup</code> — перенастроить мозг\n"
        "• <code>/tokens</code> — статистика токенов\n"
        "• <code>/help</code> — все команды",
        reply_markup=_kb_main_after_claim(),
    )


@wizard_router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext) -> None:
    """Re-open the brain picker (owner only)."""
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await message.answer("Только владелец может перенастраивать бот.")
        return
    await state.clear()
    await message.answer(
        "Перенастройка. Выбери мозг:",
        reply_markup=_kb_brain(),
    )


@wizard_router.callback_query(F.data == "claim_owner")
async def cb_claim(query: CallbackQuery, state: FSMContext) -> None:
    user = query.from_user
    existing = storage.get_owner_id()
    if existing is not None:
        await query.answer("Владелец уже зарегистрирован.", show_alert=True)
        return
    storage.set_owner_id(user.id)
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            f"<b>Готово.</b> Ты владелец (id <code>{user.id}</code>).\n\n"
            "Теперь выбери, кто будет «мозгами» — кто отвечает на сообщения от тебя:",
            reply_markup=_kb_brain(),
        )
    await query.answer("Ты теперь владелец 🎉")


@wizard_router.callback_query(F.data.startswith("brain:"))
async def cb_brain(query: CallbackQuery, state: FSMContext) -> None:
    user = query.from_user
    if not _is_owner(user.id):
        await query.answer("Только владелец.", show_alert=True)
        return

    choice = (query.data or "").split(":", 1)[1]
    await state.clear()

    if choice == "heartbeat_toggle":
        new_state = not storage.get_heartbeat_enabled()
        storage.set_heartbeat_enabled(new_state)
        await query.answer(
            f"Heartbeat OpenRouter: {'ON' if new_state else 'OFF'}", show_alert=False
        )
        if query.message is not None:
            with contextlib.suppress(Exception):
                await query.message.edit_reply_markup(reply_markup=_kb_brain())
        return

    if choice == "devin":
        # Switch to brain=devin, show the prompt the owner gives to a fresh Devin session.
        storage.set_brain("devin")
        await query.answer("Brain = devin")
        prompt = _devin_handoff_prompt()
        if query.message is not None:
            await query.message.edit_text(
                "<b>Brain = devin</b>. Бот не отвечает сам — он только пишет входящие в "
                "<code>data/inbox.log</code>, а ты сидишь в <a href='https://app.devin.ai'>app.devin.ai</a>, "
                "читаешь их и отвечаешь через шелл-CLI <code>python -m bot.send</code>.\n\n"
                "Скопируй блок ниже и пришли первым сообщением в новую Devin-сессию — там всё про "
                "архитектуру и команды:",
            )
            # Send the prompt as a separate code block so it copies cleanly on mobile.
            await query.message.answer(f"<pre>{_html_escape(prompt)}</pre>")
            await query.message.answer(
                "Готов? /help покажет все команды бота. /setup — поменять мозг."
            )
        return

    # OpenRouter or custom — both share the same sub-menu, only the label and
    # provider label inside storage differ.
    provider = "openrouter" if choice == "openrouter" else "custom"
    storage.set_brain("auto")
    storage.set_provider(provider)
    if provider == "openrouter":
        # Reset any leftover custom URL from a previous "Другое" run.
        storage.set_base_url("")

    label = "OpenRouter" if provider == "openrouter" else "Кастом (свой endpoint)"
    await query.answer(f"Brain = {label}")
    if query.message is not None:
        await query.message.edit_text(
            f"<b>Brain = auto / {label}</b>\n\n"
            "Заполни конфиг по очереди — что не задано, то возьмётся по умолчанию:",
            reply_markup=_kb_llm_config(_provider_label(choice)),
        )


# --- /ext:* — external research/scraping tools sub-menu ------------------


def _external_tools_summary() -> str:
    """Pretty list of all known external tools and which are configured."""
    keys_state = storage.list_external_tool_keys()
    lines = ["<b>Внешние API</b> (для research/scraping):", ""]
    for _tool, info in keys_state.items():
        marker = (
            "✅"
            if info["source"] == "telegram"
            else ("🌍" if info["source"] == "env" else "⚪️")
        )
        masked = info["masked"] or "—"
        lines.append(
            f"{marker} <b>{info['label']}</b> — <code>{masked}</code>\n"
            f"   <i>{info['hint']}</i>"
        )
    lines.append("")
    lines.append(
        "Жми на инструмент — пришлёшь ключ одним сообщением, я его сохраню и "
        "удалю твоё сообщение. <b>⚪️</b> = не настроено, "
        "<b>🌍</b> = взято из env-var, <b>✅</b> = задано здесь."
    )
    return "\n".join(lines)


@wizard_router.callback_query(F.data == "ext:menu")
async def cb_ext_menu(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            _external_tools_summary(),
            reply_markup=_kb_external_tools(),
            disable_web_page_preview=True,
        )
    await query.answer()


@wizard_router.callback_query(F.data == "ext:back")
async def cb_ext_back(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            "Выбери мозг:",
            reply_markup=_kb_brain(),
        )
    await query.answer()


@wizard_router.callback_query(F.data.startswith("ext:set:"))
async def cb_ext_set(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    from .storage import KNOWN_EXTERNAL_TOOLS

    tool = (query.data or "").split(":", 2)[-1]
    if tool not in KNOWN_EXTERNAL_TOOLS:
        await query.answer("Неизвестный инструмент.", show_alert=True)
        return
    meta = KNOWN_EXTERNAL_TOOLS[tool]
    await state.set_state(SetupStates.awaiting_external_tool_key)
    await state.update_data(external_tool=tool)
    if query.message is not None:
        await query.message.answer(
            f"Пришли ключ для <b>{meta['label']}</b> одним сообщением. "
            "Я удалю твоё сообщение как только сохраню.\n\n"
            f"Получить: <a href='{meta['url']}'>{meta['url']}</a>\n\n"
            f"<i>{meta['hint']}</i>",
            disable_web_page_preview=True,
        )
    await query.answer()


# --- /cfg:* — sub-menu inside OpenRouter / Other --------------------------


@wizard_router.callback_query(F.data == "cfg:back")
async def cb_cfg_back(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    if query.message is not None:
        await query.message.edit_text(
            "Выбери мозг:",
            reply_markup=_kb_brain(),
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:done")
async def cb_cfg_done(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.clear()
    summary = _config_summary()
    if query.message is not None:
        await query.message.edit_text(
            "<b>Готово.</b>\n\n"
            f"{summary}\n\n"
            "Теперь любое сообщение без <code>/</code> уйдёт в LLM. /help — все команды."
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:api")
async def cb_cfg_api(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.set_state(SetupStates.awaiting_api_key)
    if query.message is not None:
        provider = storage.get_provider()
        hint = (
            "Получить: <a href='https://openrouter.ai/keys'>openrouter.ai/keys</a>"
            if provider == "openrouter"
            else "Это твой ключ от того endpoint-а, который ты указал в URL"
        )
        await query.message.answer(
            "Пришли API-ключ <b>одним сообщением</b>. Я удалю его из чата как только сохраню.\n\n"
            + hint
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:model")
async def cb_cfg_model(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    await state.set_state(SetupStates.awaiting_model)
    if query.message is not None:
        provider = storage.get_provider()
        if provider == "openrouter":
            hint = (
                "Примеры:\n"
                "• <code>nvidia/nemotron-3-super-120b-a12b:free</code> (бесплатно)\n"
                "• <code>anthropic/claude-opus-4.7</code> (платно, лучшее качество)\n"
                "• <code>openai/gpt-5</code>\n"
                "Полный список: <a href='https://openrouter.ai/models'>openrouter.ai/models</a>"
            )
        else:
            hint = (
                "Имя модели для твоего endpoint-а. Например <code>llama3.1:70b</code>, "
                "<code>mistral-large</code>, <code>gpt-4o</code>."
            )
        await query.message.answer(
            "Пришли имя модели одним сообщением.\n\n" + hint
        )
    await query.answer()


@wizard_router.callback_query(F.data == "cfg:url")
async def cb_cfg_url(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    if storage.get_provider() == "openrouter":
        # URL для OpenRouter не настраивается, чтобы юзер случайно не сломал коннект.
        await query.answer(
            "Для OpenRouter URL не нужен. Выбери «Другое» если хочешь свой endpoint.",
            show_alert=True,
        )
        return
    await state.set_state(SetupStates.awaiting_url)
    if query.message is not None:
        await query.message.answer(
            "Пришли URL endpoint-а одним сообщением. Должен быть OpenAI-совместимым "
            "(заканчивается на <code>/v1</code>).\n\n"
            "Примеры:\n"
            "• <code>https://api.together.xyz/v1</code>\n"
            "• <code>https://api.groq.com/openai/v1</code>\n"
            "• <code>http://localhost:11434/v1</code> (Ollama)\n"
            "• <code>http://10.0.0.5:8000/v1</code> (свой vLLM)"
        )
    await query.answer()


# --- text capture for FSM --------------------------------------------------
# Filter out commands so users can /cancel, /setup, /help mid-wizard without
# their command being treated as the requested input.
_NOT_A_COMMAND = F.text & ~F.text.startswith("/")


@wizard_router.message(StateFilter(SetupStates.awaiting_api_key), _NOT_A_COMMAND)
async def capture_api_key(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    key = (message.text or "").strip()
    if not key:
        await message.answer("Пустое сообщение, попробуй ещё раз или нажми «Сменить мозг».")
        return
    # Save FIRST, then delete the message with the secret. If save fails we
    # want the user to be able to retry without re-typing the key blind.
    try:
        # The agent always reads the API key from the "openrouter" slot
        # regardless of provider (custom endpoints reuse this slot — only
        # base_url differs). Saving under any other label silently breaks
        # auth for custom endpoints, so we pin to "openrouter" here.
        storage.set_provider_key("openrouter", key)
    except Exception as exc:  # noqa: BLE001 — surface to the user, don't crash
        await message.answer(
            f"Не удалось сохранить ключ: <code>{_html_escape(str(exc))}</code>\n"
            "Попробуй ещё раз или напиши /cancel."
        )
        return
    with contextlib.suppress(Exception):
        await message.delete()
    await state.clear()
    summary = _config_summary()
    await message.answer(
        "Ключ сохранён, твоё сообщение удалено.\n\n"
        f"{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


@wizard_router.message(StateFilter(SetupStates.awaiting_model), _NOT_A_COMMAND)
async def capture_model(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    model = (message.text or "").strip()
    if not model:
        await message.answer("Пустое сообщение, попробуй ещё раз.")
        return
    storage.set_model(model)
    await state.clear()
    summary = _config_summary()
    await message.answer(
        f"Модель сохранена: <code>{_html_escape(model)}</code>\n\n{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


@wizard_router.message(
    StateFilter(SetupStates.awaiting_external_tool_key), _NOT_A_COMMAND
)
async def capture_external_tool_key(message: Message, state: FSMContext) -> None:
    """Save an external-tool API key after the user has clicked one in the menu.

    The chosen tool name was stashed in FSM ``data["external_tool"]`` by
    ``cb_ext_set``; we read it here, persist the key, delete the user's
    message (to keep the secret out of TG history), and re-show the menu
    with the updated ✅ marker.
    """
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    data = await state.get_data()
    tool = str(data.get("external_tool") or "").strip().lower()
    if not tool:
        await message.answer(
            "Не помню для какого инструмента ты задаёшь ключ — открой меню заново через /setup."
        )
        await state.clear()
        return
    key = (message.text or "").strip()
    if not key:
        await message.answer("Пустое сообщение, попробуй ещё раз.")
        return
    with contextlib.suppress(Exception):
        await message.delete()
    try:
        storage.set_external_tool_key(tool, key)
    except ValueError as exc:
        await message.answer(f"Не получилось сохранить ключ: {exc}")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"Ключ для <b>{tool}</b> сохранён, твоё сообщение удалено.\n\n"
        + _external_tools_summary(),
        reply_markup=_kb_external_tools(),
        disable_web_page_preview=True,
    )


@wizard_router.message(StateFilter(SetupStates.awaiting_url), _NOT_A_COMMAND)
async def capture_url(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id if message.from_user else 0):
        return
    url = (message.text or "").strip()
    if not url:
        await message.answer("Пустое сообщение, попробуй ещё раз.")
        return
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "URL должен начинаться с <code>http://</code> или <code>https://</code>. Попробуй ещё раз."
        )
        return
    storage.set_base_url(url)
    await state.clear()
    summary = _config_summary()
    await message.answer(
        f"URL сохранён: <code>{_html_escape(url)}</code>\n\n{summary}",
        reply_markup=_kb_llm_config(_provider_label_from_storage()),
    )


# ---- /main:* — top-level menu callbacks shortcuts -----------------------


@wizard_router.callback_query(F.data.startswith("main:"))
async def cb_main_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Handle clicks on the top-level main menu shown after /start."""
    user = query.from_user
    if not _is_owner(user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    action = (query.data or "").split(":", 1)[1]
    await state.clear()

    if action == "download":
        await query.answer()
        if query.message is not None:
            await query.message.answer(
                "<b>📥 Скачать видео</b>\n\n"
                "Пришли ссылку командой:\n"
                "<code>/dl &lt;url&gt;</code>\n\n"
                "Поддерживаются YouTube, Vimeo, TikTok, прямые .mp4 — "
                "всё что глотает yt-dlp.\n\n"
                "После /dl смотри статус через /jobs."
            )
        return

    if action == "role":
        await query.answer()
        await _show_role_picker(query, state)
        return

    if action == "brain":
        await query.answer()
        if query.message is not None:
            await query.message.edit_text(
                "Перенастройка. Выбери мозг:",
                reply_markup=_kb_brain(),
            )
        return

    if action == "tokens":
        await query.answer()
        if query.message is not None:
            from .token_tracker import format_token_stats

            await query.message.answer(format_token_stats())
        return

    await query.answer("Неизвестный пункт меню", show_alert=True)


# ---- /role — pick a persona for this bot --------------------------------


async def _show_role_picker(
    query: CallbackQuery | None = None, state: FSMContext | None = None
) -> None:
    """Render the role-picker UI; reused by /role command and main-menu button."""
    text = _role_picker_text()
    markup = _kb_role_picker()
    if query is not None and query.message is not None:
        # Try to edit the existing menu in place; if that fails (different
        # message type, etc.), send a fresh one.
        try:
            await query.message.edit_text(text, reply_markup=markup)
        except Exception:  # noqa: BLE001 — edit_text raises on inline-kb mismatch
            await query.message.answer(text, reply_markup=markup)


def _role_picker_text() -> str:
    """The header shown above the persona grid."""
    active = get_persona()
    override = storage.get_persona_override()
    env_persona = os.environ.get("BOT_PERSONA", "boss").strip().lower()
    if override is not None:
        source = (
            f"override (через /role) — env BOT_PERSONA=<code>{_html_escape(env_persona)}</code>"
        )
    else:
        source = "env BOT_PERSONA"
    return (
        "<b>🎭 Сменить роль этого бота</b>\n\n"
        f"Сейчас активна: <b>{active.display_name}</b> "
        f"(<code>{active.key}</code>, {source})\n"
        f"<i>{active.title}</i>\n\n"
        "Жми на роль чтобы её посмотреть и активировать. ▶ — текущая. "
        "После клика я попрошу подтвердить. Все 20 ролей ниже:"
    )


@wizard_router.message(Command("role"))
async def cmd_role(message: Message, state: FSMContext) -> None:
    """Show the role picker to the owner."""
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await message.answer("Только владелец может менять роль.")
        return
    await state.clear()
    await message.answer(_role_picker_text(), reply_markup=_kb_role_picker())


@wizard_router.callback_query(F.data.startswith("role:"))
async def cb_role(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(query.from_user.id):
        await query.answer("Только владелец.", show_alert=True)
        return
    action = (query.data or "").split(":", 1)[1]
    await state.clear()

    if action == "back":
        await query.answer()
        if query.message is not None:
            persona = get_persona()
            await query.message.edit_text(
                f"<b>{persona.display_name}</b> на связи. Ты владелец.\n\n"
                f"<i>{persona.title}</i>\n\n"
                "Что хочешь?",
                reply_markup=_kb_main_after_claim(),
            )
        return

    if action == "info":
        await query.answer()
        if query.message is not None:
            lines = ["<b>ℹ️ Все 20 ролей фермы</b>", ""]
            for p in list_personas():
                lines.append(
                    f"<b>{p.display_name}</b> (<code>{p.key}</code>) — "
                    f"{p.department}/{p.rank}"
                )
                lines.append(f"  <i>{p.title}</i>")
                lines.append(f"  {_html_escape(p.description)}")
                lines.append("")
            lines.append("◀️ Назад — кнопка ниже.")
            await query.message.answer(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ Назад к ролям", callback_data="role:back_to_picker")]
                    ]
                ),
                disable_web_page_preview=True,
            )
        return

    if action == "back_to_picker":
        await query.answer()
        if query.message is not None:
            await query.message.answer(_role_picker_text(), reply_markup=_kb_role_picker())
        return

    if action == "reset":
        storage.clear_persona_override()
        await query.answer("Override снят, возвращаюсь к BOT_PERSONA из env")
        if query.message is not None:
            await query.message.edit_text(_role_picker_text(), reply_markup=_kb_role_picker())
        return

    if action.startswith("pick:"):
        persona_key = action.split(":", 1)[1]
        from .persona import get_persona as _get

        persona = _get(persona_key)
        await query.answer()
        if query.message is not None:
            current = get_persona()
            already = persona.key == current.key
            same_note = (
                "\n\n<i>Сейчас эта роль уже активна — нажми «Использовать» чтобы "
                "закрепить override.</i>"
                if already
                else ""
            )
            await query.message.edit_text(
                f"<b>{persona.display_name}</b>\n"
                f"<i>{persona.title}</i>\n"
                f"Отдел: <code>{persona.department}</code> • Ранг: <code>{persona.rank}</code>\n\n"
                f"{_html_escape(persona.description)}{same_note}",
                reply_markup=_kb_role_confirm(persona.key),
            )
        return

    if action.startswith("use:"):
        persona_key = action.split(":", 1)[1]
        storage.set_persona_override(persona_key)
        from .persona import get_persona as _get

        persona = _get(persona_key)
        await query.answer(f"Роль: {persona.display_name}")
        if query.message is not None:
            await query.message.edit_text(
                f"<b>✅ Готово. Теперь я — {persona.display_name}.</b>\n"
                f"<i>{persona.title}</i>\n\n"
                "Override сохранён в state.json. Чтобы вернуться к роли из "
                "BOT_PERSONA — открой <code>/role</code> → 🗑 Сбросить override.",
                reply_markup=_kb_main_after_claim(),
            )
        return

    await query.answer("Неизвестная команда роли", show_alert=True)


# ---- Misc helpers --------------------------------------------------------


def _provider_label_from_storage() -> str:
    return storage.get_provider()


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _config_summary() -> str:
    """Pretty summary of the current LLM config, safe for HTML."""
    provider = storage.get_provider()
    keys = storage.list_provider_keys()
    label = "OpenRouter" if provider == "openrouter" else "Кастомный endpoint"
    key_state = keys.get("openrouter", {}).get("masked") or "не задан"
    if provider != "openrouter":
        key_state = keys.get("openrouter", {}).get("masked") or "не задан (нужен)"
    model = storage.get_model() or "—"
    base_url = storage.get_base_url()
    lines = [
        f"<b>{label}</b>",
        f"  Ключ: <code>{key_state}</code>",
        f"  Модель: <code>{_html_escape(model)}</code>",
    ]
    if provider != "openrouter":
        lines.append(f"  URL: <code>{_html_escape(base_url) if base_url else 'не задан'}</code>")
    return "\n".join(lines)


def _devin_handoff_prompt() -> str:
    """The text the owner pastes into a fresh Devin session.

    Devin will read this once and then live as the bot's brain — picking up
    inbox.log, replying via bot.send, etc.
    """
    return """Ты — мой удалённый ассистент с шелл-доступом к серверу, на котором живёт Telegram-бот.

ЧТО НА СЕРВЕРЕ
- Бот развёрнут как Docker-контейнер. Код — в моём GitHub-репо (точную ссылку
  я тебе дам отдельно, обычно это форк Lilush).
- Внутри контейнера: /app/bot/  (Python-пакет с handlers, wizard, agent и т.д.)
- Лог входящих сообщений: data/inbox.log  (бот пишет туда каждое моё сообщение)
- Состояние (ключи, brain, owner): data/state.json
- BOT_TOKEN — в .env рядом с ботом

ТВОЯ РАБОТА
Бот сейчас в режиме brain=devin: он НЕ отвечает мне сам. Когда я что-то пишу в TG, ты:
1. Читаешь свежие строки в data/inbox.log
2. Понимаешь что я хочу
3. Делаешь работу (правишь код, гонишь тесты, исследуешь, что угодно)
4. Отправляешь мне ответ обратно через CLI:
     set -a && source .env && set +a
     python -m bot.send <chat_id> "ответ"
   chat_id ты находишь в той же inbox.log строке.

ЕСЛИ ТЕБЕ НУЖЕН CONTEXT
Команды бота которые я могу запускать в TG (=ты их видишь в inbox.log как kind=cmd):
  /help, /start, /setup     — справка и перенастройка
  /brain, /setbrain auto|devin
  /clone <url>, /projects, /project <name>, /cd, /pwd
  /exec <bash>, /git <args>
  /keys, /setkey, /delkey, /models, /setmodel
  /enable, /disable, /reset

ВАЖНО
- Я (владелец) пингую тебя в нашем чате когда хочу чтобы ты отреагировал. Между пингами ты простаиваешь.
- Если просьба сложная — сначала разбери, потом ОДНИМ сообщением мне в TG пришли план; я скажу «ок» и ты делай.
- Если меняешь код — делай в ветке, делай PR, ссылку шли в TG.

Когда прочитал — ответь мне в этом чате (тут, у Devin) что готов, и я начну писать в TG."""
