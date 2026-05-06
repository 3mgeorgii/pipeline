# Tentacle: _global

Глобальный контекст по всему репо `codesp-bot-starter`. Этот файл — точка
входа для любого щупальца (tentacle). Конкретные задачи живут в
соседних tentacle-папках со своими `CONTEXT.md` и `todo.md`.

## Что это за проект

Self-hosted Telegram-бот с встроенным LLM-агентом. Деплоится на любое
облако (Render / Railway / Fly.io / VPS) **с одним секретом — `BOT_TOKEN`**.
Всё остальное (LLM-провайдер, ключ, модель, brain-режим) настраивается
через инлайн-кнопки в самом Telegram (`/start`, `/setup`).

UI бота на русском. Внутри агент пользуется OpenRouter (по умолчанию)
или любым OpenAI-совместимым endpoint-ом.

## Стек

- Python 3.12 (см. `Dockerfile`)
- `aiogram==3.13.1` — Telegram-фреймворк
- `aiohttp==3.10.10` — health-сервер + self-ping
- `openai>=1.55,<3` — клиент к LLM (OpenRouter / OpenAI-compatible)
- `httpx`, `python-dotenv`
- Деплой-конфиги: `Dockerfile`, `render.yaml`, `railway.json`, `fly.toml`
- Зависимости — только `requirements.txt`, **`pyproject.toml` отсутствует**

## Карта модулей (`bot/`)

| Файл           | Строк | Роль                                                                         |
|----------------|-------|------------------------------------------------------------------------------|
| `main.py`      | 207   | Entrypoint. Polling/webhook + aiohttp `/healthz` + jittered self-ping (4–7m) |
| `config.py`    | 99    | Чтение env-vars, ресолв KEEP_ALIVE_URL, дефолтные модели/тюны                |
| `wizard.py`    | 477   | FSM-онбординг: claim owner, выбор brain (OpenRouter/Devin/Other), ввод ключа |
| `handlers.py`  | 554   | Команды `/help`, `/clone`, `/exec`, `/git`, `/setkey`, `/setmodel`, и т.д.   |
| `agent.py`     | 166   | Tool-calling-loop, fallback по `:free`-моделям, чтение `state.json`          |
| `tools.py`     | 210   | 4 tool-а: `list_dir`, `read_file`, `write_file`, `exec_bash` (path-confined) |
| `storage.py`   | 214   | `data/state.json` (chmod 0600). Owner, ключи, модель, brain, history, cwd   |
| `inbox.py`     | 38    | Append-only `data/inbox.log` — чат-бэкап + источник для `brain=devin`        |
| `send.py`      | 67    | CLI `python -m bot.send <chat_id> "msg"` — для devin-режима                  |

## Ключевые архитектурные моменты

- **Owner-claim**: первый, кто нажмёт `/start → 🚀 Запустить`, становится
  единственным авторизованным пользователем (single-tenant). Owner_id
  лежит в `data/state.json::_settings.owner_id`.
- **Хранение ключей**: API-ключи провайдеров **не в env**, а в
  `data/state.json` (0600). Сообщение пользователя с ключом удаляется
  ботом сразу после захвата (в FSM `awaiting_api_key`).
- **Brain-режимы**: `auto` (LLM отвечает сам) и `devin` (бот только
  логирует входящие в `inbox.log`; ответы шлёт внешний Devin через
  `python -m bot.send`).
- **Песочница `exec_bash`**: её **нет** — это полноценный shell.
  Защита держится только на owner-claim (см. README §Безопасность).
- **`tools._resolve`**: строгая проверка, что путь не выходит за корень
  выбранного проекта в `PROJECTS_DIR`.
- **Self-ping**: jittered loop пингует свой `/healthz` через публичный
  URL платформы (Render/Railway/Fly авто-детект), чтобы Render Free не
  засыпал.
- **Webhook path**: `/tg/<numeric-prefix-of-bot-token>` — не полный
  токен, чтобы не светить его в логах балансировщика.

## Что в репо НЕ лежит

- Тестов нет (`tests/`, `pytest.ini`, `conftest.py` — отсутствуют).
- Линтеры/тайпчекеры не сконфигурированы (`ruff`, `mypy`, `pyright`).
- CI не сконфигурирован (`.github/workflows/` — нет).
- `pyproject.toml` отсутствует, только `requirements.txt`.
- Нет миграций/версионирования схемы `state.json`.
- Нет structured logging / log rotation.

## Конвенции (наблюдаемые в коде)

- Type hints везде (PEP 604: `int | None`, `set[int]`).
- Docstrings — Google-ish стиль, иногда с разделом `Three modes:` /
  `Rules:` / маркированными списками.
- Импорты сгруппированы: stdlib → third-party → relative (с пустыми
  строками между группами). Иногда внутрифункциональный импорт,
  чтобы разорвать цикл (`from .config import DEFAULT_MODEL`
  внутри `Storage.get_model`).
- Логгеры заводятся через `logger = logging.getLogger(__name__)`.
- Комментарии — содержательные, описывают «почему», не «что».

## Точки входа

- `python -m bot.main` — запустить бота (polling по умолчанию).
- `python -m bot.send <chat_id> "..."` — отправить сообщение из шелла.
- `docker build -t codesp-bot . && docker run ...` — контейнер.

## Полезное про деплой

- Render Free засыпает после 15 минут без входящих HTTP — ловится
  self-ping-ом (рандомный интервал 4–7 минут, чтобы не выглядеть как
  cron-tick).
- Fly.io always-on → `KEEP_ALIVE_INTERVAL=0` отключает self-ping.
- VPS: `KEEP_ALIVE_URL` пуст → self-ping автоматически отключён.

## Как мы работаем (Octogent-style)

- Каждая обособленная задача → новая папка
  `.devin/tentacles/<scope>/` с `CONTEXT.md` + `todo.md` + по нужде
  `notes.md`.
- `todo.md` внутри щупальца — единственный источник правды по
  прогрессу. Я и пользователь его читаем/правим.
- Большие задачи дробятся на под-щупальца, каждое можно отдать
  отдельной child-сессии Devin.
- Долгоживущие договорённости (стиль, команды линта/тестов, тестовые
  аккаунты) уходят в knowledge notes / `SKILL.md`.
