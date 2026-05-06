# Кандидаты на улучшения — codesp-bot-starter

Каждый пункт — кандидат в отдельный tentacle (`.devin/tentacles/<имя>/`).
Поставлены [P0]/[P1]/[P2] по моей субъективной оценке отдачи. Финальный
порядок — за пользователем.

## P0 — фундамент (без этого больно делать остальное)

- [ ] **tests-foundation** — добавить `pytest` + `pytest-asyncio`,
      первые smoke-тесты на `tools.py` (path-escape, write/read,
      exec_bash timeout) и `storage.py` (owner-claim, set/get_provider_key,
      history rolling). Каркас под фикстуры с tmp DATA_DIR.
- [ ] **lint-typecheck** — `ruff` + `mypy` (или `pyright`), конфиг в
      `pyproject.toml`, прогон по чистому репо, фикс импорт-сортировки и
      явных мисматчей типов.
- [ ] **ci-github-actions** — workflow `.github/workflows/ci.yml`:
      install → ruff → mypy → pytest на 3.11/3.12. Кэш pip.
- [ ] **pyproject-toml** — переезд на `pyproject.toml`
      (deps + tool config), `requirements.txt` оставить как
      lock для совместимости с Render/Railway/Fly.

## P1 — безопасность и устойчивость

- [ ] **exec-bash-hardening** — мягкая песочница: blocklist опасных
      команд (`rm -rf /`, `curl|bash`), audit-лог в `data/audit.log`,
      явное подтверждение для деструктивных команд, лимит вывода.
- [ ] **state-schema-versioning** — поле `_settings.schema_version`,
      простой миграционный механизм + тесты.
- [ ] **storage-locking** — `asyncio.Lock` или файл-лок вокруг записи
      `state.json` (FSM и agent-loop пишут параллельно).
- [ ] **handlers-split** — `handlers.py` (554 строки) разбить по модулям:
      `commands_projects.py`, `commands_keys.py`, `commands_brain.py`,
      `commands_meta.py`. Отдельный `middleware.py`.
- [ ] **structured-logging** — JSON-лог с `chat_id`, `user_id`,
      `tool_name`, `model`, `duration_ms`. Опц. ротация.

## P1 — фичи под пользователя

- [ ] **inline-model-picker** — кнопочный выбор модели из
      `MODEL_CATALOGUE` прямо в `/setup`, без ручного ввода имени.
- [ ] **diff-preview-write-file** — перед `write_file` показывать
      unified-diff и спрашивать подтверждение в чате (или флаг
      `auto_apply` в storage).
- [ ] **multi-owner-allowlist** — снять single-tenant: owner может
      приглашать других через `/invite <user_id>` с ролями
      `owner|user|readonly`.
- [ ] **healthz-richer** — `/healthz` отдаёт JSON со статусом brain,
      моделью, версией (git sha из env).
- [ ] **keep-alive-on-httpx** — единый HTTP-клиент (httpx) вместо
      одновременного aiohttp+httpx в зависимостях.

## P2 — DX и доки

- [ ] **dev-makefile** — `make install/test/lint/run` для локалки.
- [ ] **docker-compose-local** — `docker-compose.yml` с volume для
      `data/` и hot-reload через `watchfiles`.
- [ ] **readme-architecture-section** — диаграмма потока сообщения
      (Telegram → middleware → router → wizard|handlers → agent → tools).
- [ ] **example-tentacle** — пример работы Octogent-style как раздел
      в README или `CONTRIBUTING.md`.

## Что уже сделано

- [x] **bootstrap** — git-репо инициализирован, базовая ветка `master`,
      первый коммит из распакованного зипа.
- [x] **tentacle-scaffold** — каркас `.devin/tentacles/_global/` с
      `CONTEXT.md` и этим `todo.md`.
