# tentacle: seo-agent

Заменяет stub `bot/workers/seo.py`. Из готового шорта + контекста (transcript, hook, original-title) генерирует SEO-метаданные: title, description, hashtags.

## Job contract

- **Input** `payload` (от editor):
  - `clip_path` — путь к готовому шорту 1080×1920.
  - `source_path`, `clip_index`, `hook` — для контекста.
  - `transcript_path` — опц. (от analyzer через editor-payload).
  - `language` — опц. (auto-detect из transcript если есть).
  - `original_title`, `uploader` — опц. (от downloader через цепочку).
- **Output** `result`:
  - `clip_path`, `source_path`, `clip_index`, `hook` — пробрасываем.
  - `seo_title` — ≤90 символов (YT Shorts limit ~100).
  - `seo_description` — ≤500 символов с встроенными хэштегами в конце.
  - `tags` — список из ≤15 строк, каждая ≤30 символов.
  - `language` — финальный язык метаданных.
  - `trends_used` — list[str] — какие тренды подтянулись.
  - `seo_method` — `"llm"` если OpenRouter ответил, иначе `"template"`.

## Источник трендов

[`pytrends`](https://github.com/GeneralMills/pytrends) — клиент Google Trends без официального API. Бесплатный, но rate-limited. Ловим `TooManyRequestsError` и работаем без трендов (`trends_used = []`).

Регион запроса:
- `language="ru"` → geo `RU`, hl `ru-RU`.
- `language="en"` → geo `US`, hl `en-US`.
- иное → `geo=""`, `hl="en-US"` (worldwide).

Время: `today 7-d` (тренды последней недели).

## Промпт LLM

Системный:
```
You are an SEO/marketing copywriter for short-form video on
YouTube Shorts / TikTok / Instagram Reels. Output strict JSON:
{
  "title": "≤90 chars, hooky, language={lang}",
  "description": "≤400 chars + hashtags, language={lang}",
  "tags": ["≤15 items, language={lang}"]
}
Title MUST grab attention in 2 seconds. Description MUST end with
4-7 hashtags. Tags are search-keywords, not hashtags.
```

User:
```json
{
  "clip_hook": "...",
  "transcript_excerpt": "first 1500 chars of transcript",
  "original_title": "...",
  "uploader": "...",
  "trending_now": ["tag1", "tag2", ...]
}
```

## Фолбэк (без LLM или при ошибке)

Шаблон:
- title = `(hook[:80] or original_title[:80])`.
- description = `f"{hook}\n\n{trending_hashtags}"`.
- tags = `["shorts", "viral", language] + trends_used[:10]`.

Воркер не падает — `seo_method == "template"`.

## Tests

- `test_uses_template_without_api_key` — `OPENROUTER_API_KEY=""` + мок pytrends → `seo_method == "template"`, выходные ключи присутствуют.
- `test_uses_llm_when_key_present` — мокаем `httpx.post` с готовым JSON → `seo_method == "llm"`.
- `test_pulls_trending_keywords` — мокаем `pytrends.TrendReq.trending_searches()` → возвращает 5 строк, проверяем что они в `trends_used`.
- `test_handles_pytrends_rate_limit` — мок бросает `TooManyRequestsError` → `trends_used = []`, всё остальное работает.
- `test_language_propagated` — payload `language="ru"` → result `language == "ru"`.
- `test_invalid_llm_response_falls_back` — мок возвращает не-JSON → `seo_method == "template"`.
- `test_passes_payload_through_to_publisher` — `enqueue_next` создаёт publish-job с правильным payload.

## После мержа

- publisher-agent читает `seo_title`, `seo_description`, `tags`, `clip_path`.
