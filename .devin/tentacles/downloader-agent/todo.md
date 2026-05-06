# downloader-agent — todo

- [ ] Добавить `yt-dlp` в `pyproject.toml` deps + `requirements.txt`.
- [ ] `bot/config.py`: `DOWNLOADS_DIR`, `DOWNLOAD_MAX_FILESIZE_MB`, `DOWNLOAD_MAX_HEIGHT`, `YT_COOKIES_FILE`.
- [ ] `bot/workers/downloader.py`: переписать `process()` на реальный `yt-dlp`:
      pre-flight `extract_info(download=False)` → проверка размера → реальная загрузка → запись `metadata.json` → возврат структуры из CONTEXT.
- [ ] Progress-hook: пишем в `data/downloads/<job_id>/download.log`.
- [ ] Тесты с моком `YoutubeDL`: pre-flight, oversized, metadata-write, progress-hook.
- [ ] PR против `devin/init`, CI зелёный.

## После мержа (next tentacles)

- analyzer-agent читает `result["source_path"]`, `result["duration_s"]`.
- editor-agent читает `result["source_path"]` + clip из analyzer.
- seo-agent читает `result["title"]`, `result["uploader"]`, transcript из analyzer.
