# tentacle: downloader-agent

Заменяет stub `bot/workers/downloader.py` реальным скачиванием через `yt-dlp`.

## Job contract

- **Input** `payload`:
  - `url` — ссылка (YouTube / Vimeo / Twitch VOD / любой источник, поддерживаемый yt-dlp).
  - опц. `max_height` (default `1080`) — кеп резолюции.
  - опц. `max_filesize_mb` (default `5000` = 5 GB) — отклоняем источник до начала скачивания.
- **Output** `result`:
  - `source_path` — абсолютный путь до файла, например `data/downloads/<job_id>/source.mp4`.
  - `metadata_path` — путь до `data/downloads/<job_id>/metadata.json` с info-dict от yt-dlp.
  - `duration_s` — длительность в секундах (нужно analyzer'у для разбивки на сцены).
  - `title`, `uploader`, `original_url`, `width`, `height`, `fps`, `language` — для SEO/UI.

Следующая стадия (`analyze`) получает payload-копию `result`.

## Где живут файлы

```
data/downloads/<job_id>/
  source.mp4           # видео + аудио, склеено через ffmpeg
  metadata.json        # info-dict yt-dlp
  thumbnail.jpg        # если доступен
  download.log         # лог yt-dlp
```

`data/` в `.gitignore`. Кейп размером — pre-flight через `yt-dlp.extract_info(download=False)`, до фактической загрузки.

## Прогресс в чат

`yt-dlp` поддерживает `progress_hooks`. На каждом 10% (или каждые 5 секунд) отправляем апдейт в исходный chat через бота. Чтобы не плодить сообщения в Telegram, **редактируем одно** через `bot.edit_message_text`.

Для skeleton-PR без бота — прогресс просто пишется в `download.log`. Поддержка edit-message — в отдельной мини-таске после.

## Авторизация / cookies

Для YouTube без cookies возрастные ограничения и регион-локи будут падать. Поддержка cookies:
- `YT_COOKIES_FILE` env — путь до Netscape-формат cookie-файла. yt-dlp передаёт его как `cookiefile`.
- Если переменная не задана — работаем без cookies, на restricted-content кидаем человекочитаемый error в `job.error`.

## Ошибки и retry

Тип ошибок yt-dlp:
- `DownloadError` — обычно временный (network) → пометить failed, ретрай руками.
- `ExtractorError` с `geo_restricted` — **не ретраить**, явный fail.
- `UnsupportedError` — фейл с понятным месседжем.

В этом tentacle ретраев нет (skeleton). Дальше отдельный tentacle добавит retry-стратегию.

## Tests

- `test_downloader_resolves_metadata_only` — мокаем `YoutubeDL.extract_info`, проверяем что `download=False` запускается первым (pre-flight), что результат заполняет правильные поля.
- `test_downloader_rejects_oversized_source` — extract_info возвращает `filesize_approx` > cap, наш воркер кидает понятную ошибку.
- `test_downloader_writes_metadata_json` — после успешной загрузки `metadata.json` существует и парсится.
- `test_downloader_progress_hook_logs` — progress_hook заполняет `download.log` хотя бы одной строкой.

Без сети — все тесты используют `monkeypatch` на `YoutubeDL`.
