# todo: pipeline-skeleton

Acceptance criteria: можно отправить `/dl <url>` боту → джоб проходит
через 5 стадий-стабов → бот рапортует «готово, fake post URL = ...».

## Реализация

- [ ] `bot/jobs.py` — async SQLite-обёртка:
  - `init(db_path)` — создаёт таблицу/индексы при необходимости
  - `enqueue(kind, payload, chat_id, parent_id=None) -> int`
  - `pop_one(kind) -> Job | None` — атомарный UPDATE-RETURNING
  - `mark_done(job_id, result)`
  - `mark_failed(job_id, error)`
  - `list_active(chat_id=None) -> list[Job]`
  - `Job` — dataclass или TypedDict
- [ ] `bot/workers/base.py` — `Worker` базовый класс с polling-loop,
  graceful stop, error-handling
- [ ] `bot/workers/downloader.py` — стаб: `await asyncio.sleep(2)`,
  возвращает `{"file_path": f"/tmp/sources/{job.id}.mp4", "duration_s": 5400}`
- [ ] `bot/workers/analyzer.py` — стаб: возвращает 3 фейковых клипа,
  enqueue-ит 3 `edit`-джоба
- [ ] `bot/workers/editor.py` — стаб: `await asyncio.sleep(1)`,
  возвращает `{"clip_path": ...}`
- [ ] `bot/workers/seo.py` — стаб: возвращает фейковый title/desc/tags
- [ ] `bot/workers/publisher.py` — стаб: возвращает fake URL,
  репортит владельцу через `bot.send_message`
- [ ] `bot/handlers.py` — `+@router.message(Command("dl"))`:
  валидация URL, enqueue, ответ «job #N принят»
- [ ] `bot/handlers.py` — `+@router.message(Command("jobs"))`:
  список активных джобов

## Интеграция

- [ ] `bot/main.py` — запустить пул воркеров через `asyncio.gather`,
  корректно останавливать на shutdown (signal handler уже есть в aiogram)
- [ ] `bot/config.py` — `JOBS_DB_PATH`, `WORKER_POLL_INTERVAL_S`
- [ ] `requirements.txt` — добавить `aiosqlite`

## Качество кода

- [ ] `pyproject.toml` — package metadata, deps, dev-deps,
  ruff config (line-length, target-version), mypy config
- [ ] `ruff check .` проходит без ошибок
- [ ] `mypy bot/ tests/` проходит
- [ ] `tests/test_jobs.py` — enqueue/pop_one атомарность, transitions,
  parent_id chain, list_active фильтрация по chat_id
- [ ] `tests/test_worker.py` — базовый worker берёт джоб, обрабатывает,
  правильно переводит статус. Использует `asyncio` fixture
- [ ] CI pipeline (`.github/workflows/ci.yml`) — запускается на push,
  ruff + mypy + pytest

## Ребрендинг (минимальный)

- [ ] README.md — переписать первую строку: «codesp-bot-starter» → «Lilush»
- [ ] handlers.py: `HELP_TEXT` — «codespace bot» → «Lilush»
- [ ] config.py: `APP_TITLE` env-var default — «codesp telegram bot» → «Lilush»

## Документация

- [ ] README — добавить раздел про pipeline-архитектуру и команду `/dl`
- [ ] `.devin/tentacles/_global/todo.md` — отметить done пакет P0/P1
  (часть пунктов покроется этим tentacle: pyproject, ci, tests)

## Out of scope (для отдельных tentacle)

- Реальная интеграция yt-dlp / ffmpeg / whisper / LLM / YT API
- Retry-policy с экспоненциальным backoff
- Storage migration system (`_settings.schema_version`)
- Распределённые воркеры (отдельный процесс / VPS)
