# tentacle: editor-agent

Заменяет stub `bot/workers/editor.py`. Из исходника + clip-окна делает готовый вертикальный шортc 1080×1920.

## Job contract

- **Input** `payload` (от analyzer):
  - `source_path`, `start_s`, `end_s`, `hook` — клип-окно.
  - `clip_index` — порядковый номер (для имени файла).
  - `transcript_path` — опц. (для caption burn-in в будущем).
  - `language` — опц.
- **Output** `result`:
  - `source_path` — пробрасываем дальше.
  - `clip_path` — абсолютный путь к итоговому `.mp4`.
  - `clip_index`, `hook` — пробрасываем.
  - `duration_s` — реальная длительность готового клипа.
  - `width=1080`, `height=1920` — формат шорта.
  - `overlay_used` — bool, был ли применён логотип-overlay.

## ffmpeg-граф

```
[in] -ss start_s -to end_s
       │
       ▼
crop=ih*9/16:ih   (центральная вертикальная полоса 9:16)
       │
       ▼
scale=1080:1920   (фикс. шортc-резолюция)
       │
       ▼ (если overlay включён и файл существует)
overlay=W-w-40:H-h-40   (правый-нижний угол, отступ 40px)
       │
       ▼
output.mp4 (libx264 CRF 23, AAC 128k)
```

Алгоритм без перекодирования аудио бы был быстрее, но ради совместимости с любыми источниками — всегда делаем полный re-encode в `yuv420p`/AAC.

## Smart-crop

Сейчас делаем **центральный crop** — вертикальная полоса `ih*9/16` шириной из центра кадра. Это безопасно для большинства talking-head контента.

В будущем можно добавить face-detect via OpenCV → пан камеры по лицу. Пока инфраструктура готова, метод `_compute_crop_filter()` вынесен наружу и подменяем для тестов.

## Overlay

Если в `OVERLAY_LOGO_PATH` указан существующий PNG (с alpha), он вкатывается в правый-нижний угол на всё время клипа. Отсутствие файла → шорт без оверлея, не падаем.

## Tests

- `test_runs_ffmpeg_with_correct_filter_chain` — мокаем `subprocess.run`, проверяем что в команде есть `crop=`, `scale=1080:1920` и `-ss`/`-to`.
- `test_writes_output_under_clips_dir` — проверяем что выходной файл попадает в `<source_dir>/clips/<job_id>_<idx>.mp4`.
- `test_overlay_added_when_logo_exists` — задаём `OVERLAY_LOGO_PATH`, проверяем что в команде появляется второй `-i` и фильтр `overlay=`.
- `test_overlay_skipped_when_logo_missing` — `OVERLAY_LOGO_PATH=/no/such/file.png` → команда без overlay.
- `test_ffmpeg_failure_surfaces_friendly_error` — `subprocess.run` бросает `CalledProcessError` → `RuntimeError` с понятным сообщением.

## После мержа

- seo-agent читает `source_path`, `language`, `transcript_path` (через analyzer-result в parent-payload).
- publisher-agent читает `clip_path` и публикует его.
