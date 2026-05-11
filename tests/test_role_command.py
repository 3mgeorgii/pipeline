"""Tests for the /role command UI helpers in bot.wizard.

The actual aiogram callback round-trip is exercised in integration; here
we focus on the keyboard builder + text formatter so changes to the
persona roster keep the picker consistent (20 persona buttons + Info +
Back). Heavy mocking of aiogram is intentionally avoided.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def fresh_modules(tmp_path, monkeypatch):
    """Provide a Storage + wizard view freshly bound to a tmp data dir."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOT_PERSONA", "boss")
    import sys

    for mod in ("bot.config", "bot.storage", "bot.persona", "bot.wizard"):
        sys.modules.pop(mod, None)
    config = importlib.import_module("bot.config")
    storage_mod = importlib.import_module("bot.storage")
    storage_mod.storage = storage_mod.Storage(data_dir=config.DATA_DIR)
    wizard = importlib.import_module("bot.wizard")
    return storage_mod.storage, wizard


def _flat_callbacks(markup) -> list[str]:
    out: list[str] = []
    for row in markup.inline_keyboard:
        for btn in row:
            if btn.callback_data:
                out.append(btn.callback_data)
    return out


def test_role_picker_has_20_persona_buttons(fresh_modules) -> None:
    _, wizard = fresh_modules
    markup = wizard._kb_role_picker()
    callbacks = _flat_callbacks(markup)
    picks = [c for c in callbacks if c.startswith("role:pick:")]
    assert len(picks) == 20


def test_role_picker_includes_info_and_back(fresh_modules) -> None:
    _, wizard = fresh_modules
    callbacks = _flat_callbacks(wizard._kb_role_picker())
    assert "role:info" in callbacks
    assert "role:back" in callbacks


def test_role_picker_shows_reset_only_when_override_set(fresh_modules) -> None:
    storage, wizard = fresh_modules
    # No override yet → no reset button.
    callbacks = _flat_callbacks(wizard._kb_role_picker())
    assert "role:reset" not in callbacks
    # Set override → reset button appears.
    storage.set_persona_override("research_lead")
    callbacks = _flat_callbacks(wizard._kb_role_picker())
    assert "role:reset" in callbacks


def test_brain_keyboard_includes_heartbeat_toggle(fresh_modules) -> None:
    _, wizard = fresh_modules
    callbacks = _flat_callbacks(wizard._kb_brain())
    assert "brain:heartbeat_toggle" in callbacks


def test_main_menu_keyboard_has_download_button(fresh_modules) -> None:
    _, wizard = fresh_modules
    callbacks = _flat_callbacks(wizard._kb_main_after_claim())
    assert "main:download" in callbacks
    assert "main:role" in callbacks
    assert "main:brain" in callbacks
    assert "main:tokens" in callbacks


def test_role_picker_text_mentions_active_persona(fresh_modules) -> None:
    storage, wizard = fresh_modules
    text = wizard._role_picker_text()
    assert "Lilush Boss" in text  # default persona display_name
    storage.set_persona_override("research_lead")
    text = wizard._role_picker_text()
    assert "Research Lead" in text


def test_role_confirm_keyboard_includes_use_button(fresh_modules) -> None:
    _, wizard = fresh_modules
    markup = wizard._kb_role_confirm("debate_lead")
    callbacks = _flat_callbacks(markup)
    assert "role:use:debate_lead" in callbacks
    assert "role:back" in callbacks
