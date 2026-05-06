# analyzer-agent — todo

- [ ] Добавить `faster-whisper` + `scenedetect` в `pyproject.toml` deps + `requirements.txt`.
- [ ] `bot/config.py`: `WHISPER_MODEL_SIZE` (default `base`), `WHISPER_DEVICE` (default `cpu`), `ANALYZER_TARGET_CLIPS` (default `3`).
- [ ] `bot/workers/analyzer.py`: переписать на реальный пайплайн (audio extract → whisper → scenedetect → ranker → output).
- [ ] LLM-ranker через `bot.agent.openrouter_chat` (или копия) — fallback на эвристику если ключ отсутствует.
- [ ] Тесты с моками: ffmpeg, WhisperModel, scenedetect, OpenRouter response.
- [ ] PR против `devin/1778040133-downloader-agent` (downloader-agent), CI зелёный.

## После мержа

- editor-agent потребляет `clips`, `source_path`.
- seo-agent потребляет `transcript_path`.
