# seo-agent — todo

- [ ] Добавить `pytrends` в `pyproject.toml` deps + `requirements.txt`.
- [ ] `bot/config.py`: `SEO_LLM_MODEL` (default `openai/gpt-4o-mini`).
- [ ] `bot/workers/seo.py`: переписать на pytrends + LLM с фолбэком.
- [ ] Тесты с моками: pytrends, httpx (для OpenRouter), без сети.
- [ ] PR против `devin/1778040975-editor-agent`, CI зелёный.

## После мержа

- publisher загружает с метаданными от seo.
