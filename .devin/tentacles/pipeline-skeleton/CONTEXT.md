# Tentacle: pipeline-skeleton

Первый tentacle проекта Lilush. Цель — собрать **каркас мульти-агентного
конвейера** так, чтобы был виден поток джоба через все стадии, но без
реальной обработки видео. Стабы воркеров логируют свою стадию и
протаскивают джоб дальше.

## В каком состоянии репо после этого tentacle

- Команда `/dl <url>` в Telegram создаёт `job` со статусом `queued`.
- 5 воркеров (`downloader` → `analyzer` → `editor` → `seo` → `publisher`)
  работают как asyncio-таски в том же процессе, что и polling Telegram.
- Каждый воркер тянет джобы своей стадии из SQLite-очереди, логирует
  «начал/закончил», и переводит джоб в следующую стадию.
- Reporter раз в N секунд шлёт владельцу сводку «что в работе».
- Тесты pytest для очереди (enqueue/dequeue/transition).
- `pyproject.toml` + `ruff` + `mypy` сконфигурированы.

Что **не делается** в этом tentacle:
- Реальный `yt-dlp`, `ffmpeg`, `whisper` — стабы.
- Авторизация YT/TikTok/IG — нет.
- LLM-вызовы для SEO — нет.
- Распределённый деплой на отдельный VPS — всё в одном процессе.

## Дизайн очереди

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,           -- 'download' | 'analyze' | 'edit' | 'seo' | 'publish'
    status      TEXT    NOT NULL DEFAULT 'queued',  -- 'queued' | 'running' | 'done' | 'failed'
    parent_id   INTEGER,                    -- родительский job (например edit берёт parent=download)
    payload     TEXT    NOT NULL,           -- JSON-сериализованный payload стадии
    result      TEXT,                       -- JSON результата для следующей стадии
    error       TEXT,                       -- traceback при failed
    retries     INTEGER NOT NULL DEFAULT 0,
    chat_id     INTEGER,                    -- куда репортить статус
    created_at  TEXT    NOT NULL,           -- ISO timestamp
    updated_at  TEXT    NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_kind_status ON jobs(kind, status);
```

`payload` и `result` — это JSON-словари. Например:
- `download.payload = {"url": "https://..."}`
- `download.result = {"file_path": "/data/sources/123/source.mp4", "duration_s": 5400}`
- `analyze.payload = {"source_path": "...", "duration_s": 5400}`
- `analyze.result = {"clips": [{"start": 12.5, "end": 32.0, "hook": "..."}]}`
- и т.д.

Цепочка job-ов — через `parent_id`. После завершения `download` создаём
`analyze` с `parent_id = download.id` и `payload = download.result`.

## Дизайн воркеров

Базовый класс `Worker(kind: str)`:
- async-loop: каждые `poll_interval` секунд (default 1.0) делает
  `pop_one(kind)` — атомарно `UPDATE jobs SET status='running' WHERE id=(SELECT id FROM jobs WHERE kind=? AND status='queued' ORDER BY id LIMIT 1) RETURNING *`.
- Если джоб найден — вызывает `await self.process(job)`, который должен
  вернуть `result_payload: dict` или бросить исключение.
- На успех: `mark_done(job.id, result)` и `enqueue_next(job)`.
- На ошибку: `mark_failed(job.id, traceback)`. Retries — отдельным
  механизмом во второй итерации.
- Грейсфул-shutdown: `worker.stop()` ставит флаг, текущий джоб
  доходит до конца, цикл выходит.

Конкретные воркеры наследуют `Worker` и переопределяют `process()` +
объявляют `next_kind: str | None`.

Цепочка по умолчанию:
- `download` → `analyze`
- `analyze` → `edit` (множественно — по N клипов)
- `edit` → `seo`
- `seo` → `publish`
- `publish` → конец, репорт владельцу

## Файловая раскладка

```
bot/
├── jobs.py             # SQLite-очередь, enqueue/pop/done/failed/list
├── workers/
│   ├── __init__.py
│   ├── base.py         # Worker base class
│   ├── downloader.py   # стаб: спит N сек, отдаёт fake file_path
│   ├── analyzer.py     # стаб: возвращает 3 фейковых клипа
│   ├── editor.py       # стаб: возвращает fake output_path
│   ├── seo.py          # стаб: возвращает заглушку метаданных
│   └── publisher.py    # стаб: возвращает fake post_url
└── handlers.py         # +/dl команда
```

## Точки изменений в существующем коде

- `bot/main.py`: рядом с `start_polling` запустить `asyncio.gather`
  с воркерами. На shutdown — корректно остановить их.
- `bot/handlers.py`: добавить `@router.message(Command("dl"))` →
  `jobs.enqueue("download", {"url": ...}, chat_id=msg.chat.id)`.
- `bot/config.py`: новый `JOBS_DB_PATH = DATA_DIR / "jobs.db"`,
  `WORKER_POLL_INTERVAL_S = 1.0`.
- `requirements.txt`: добавить `aiosqlite>=0.20`.
- `bot/__init__.py`: ничего.

## Зависимости (новые в `requirements.txt`)

```
aiosqlite>=0.20,<0.21
```

Pytest и dev-deps — отдельно в `pyproject.toml`.

## Что входит в этот PR

- Скелет очереди и воркеров (стабы).
- `/dl` команда.
- Базовый `pyproject.toml` (ruff + mypy + pytest).
- Тесты `tests/test_jobs.py`.
- Документация в этом tentacle.

## Что **не** входит (отдельные PR-ы)

- Реальный yt-dlp интеграция → tentacle `downloader-agent`.
- ffmpeg-нарезка → tentacle `editor-agent`.
- Whisper + LLM-ranker → tentacle `analyzer-agent`.
- LLM SEO-генератор → tentacle `seo-agent`.
- YT/TT/IG публикаторы → tentacle `publisher-agent`.
- Рекламный overlay → встроится в `editor-agent` v2.
