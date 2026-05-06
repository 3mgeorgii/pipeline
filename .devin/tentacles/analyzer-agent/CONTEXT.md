# tentacle: analyzer-agent

Заменяет stub `bot/workers/analyzer.py` реальным анализом, который выбирает «жирные» моменты для шортсов.

## Job contract

- **Input** `payload` (от downloader):
  - `source_path` — абсолютный путь до файла.
  - `duration_s` — длительность в секундах (из metadata downloader).
  - `language` — опц. (auto-detect если нет).
  - `target_clip_count` — опц., default `3`.
  - `target_clip_min_s` / `target_clip_max_s` — опц., default `15` / `60`.
- **Output** `result`:
  - `source_path`, `duration_s`, `language` — пробрасываем дальше.
  - `transcript_path` — JSON с whisper segments.
  - `clips` — список словарей: `{start_s, end_s, hook, score}`.
  - `analysis_method` — `"llm"` если ranker отработал, иначе `"heuristic"`.

## Стадии анализа

```
ffmpeg ──► aac/wav (16 kHz mono, скоростно) ──► faster-whisper ──► segments.json
                                                                  │
            pyscenedetect (content-aware) ──► scene_list ─────────┤
                                                                  ▼
                                                     candidate windows
                                                                  │
                                  ┌───────────────────────────────┤
                                  ▼                               ▼
                   LLM-ranker (OpenRouter)         heuristic (energy + length)
                                  │                               │
                                  └─────────► top-N clips ◄───────┘
```

## Зачем фолбэк-эвристика

OpenRouter ключ может отсутствовать (локальный dev, окружение без интернета). Тогда analyzer не должен падать — берёт сцены с самой высокой суммарной длиной транскрипта (proxy для «насыщенный диалог») + пик RMS-энергии. Выдаёт 3 клипа.

## Стоимость на проде

- faster-whisper `base` — ~150 MB модель, ~1 GB RAM, на 90-минутный фильм ~15 минут CPU.
- pyscenedetect content-aware — секунды.
- LLM-ranker — один OpenRouter call с длиной транскрипта (~10K токенов промт + 500 токенов ответ).

В тестах **ничего из этого не запускается реально** — мокается через `monkeypatch`.

## Tests

- `test_extracts_audio_then_transcribes` — мокаем `ffmpeg-python` + `WhisperModel.transcribe()`, проверяем последовательность вызовов и наличие `transcript_path`.
- `test_falls_back_to_heuristic_without_api_key` — `OPENROUTER_API_KEY` пустой → `analysis_method == "heuristic"` + 3 клипа.
- `test_uses_llm_ranker_when_key_present` — мок OpenRouter response с готовым JSON-ом из 3 клипов → `analysis_method == "llm"`.
- `test_clip_windows_within_bounds` — все клипы лежат внутри `[0, duration_s]` и удовлетворяют min/max длине.
- `test_payload_passes_through_to_editor` — chain via `enqueue_next` создаёт N edit-джобов с правильным payload (`source_path`, `start_s`, `end_s`, `hook`).

## После мержа

- editor-agent читает `clip.start_s`, `clip.end_s`, `clip.hook`.
- seo-agent читает `transcript_path`, `language`, `clips[*].hook`.
