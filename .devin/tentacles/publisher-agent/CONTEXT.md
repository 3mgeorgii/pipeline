# tentacle: publisher-agent

Заменяет stub `bot/workers/publisher.py`. **DRY-RUN режим** в этом релизе — генерирует JSON-метаданные для трёх платформ (YouTube Shorts, TikTok, Instagram Reels) + копирует клип в готовый-к-аплоаду каталог. Реальная заливка — отдельным tentacle позже, когда у пользователя будут готовы cookies/session-tokens.

## Зачем DRY-RUN

1. Безопасно тестировать пайплайн без банов/страйков на реальных аккаунтах.
2. Пользователь руками перетаскивает готовые папки в TikTok studio / YT Studio / IG → проверяет качество → потом включаем real-upload.
3. Заливка через unofficial libs (`tiktok-uploader`, `instagrapi`) требует отдельного хранилища credentials и proxy/anti-detect стэка — это уже задача *уровня инфраструктуры*, а не tentacle.

## Job contract

- **Input** `payload` (от seo):
  - `clip_path`, `source_path`, `clip_index`, `hook`, `language`.
  - `seo_title`, `seo_description`, `tags`.
- **Output** `result`:
  - `release_dir` — каталог куда положены готовые файлы.
  - `clip_path` — путь к клипу внутри release_dir.
  - `metadata_paths` — `{youtube, tiktok, instagram}` — пути к JSON-ам.
  - `platforms` — список platform-ключей.
  - `dry_run` — всегда `True` в текущей версии.

## Файловая структура

```
data/releases/<job_id>/
├── clip.mp4              # символическая ссылка/копия от editor
├── youtube.json          # title, description, tags, categoryId, privacyStatus
├── tiktok.json           # caption, hashtags, music_id (null), language
├── instagram.json        # caption, hashtags, share_to_feed
└── upload-instructions.md   # human-readable инструкция
```

Использует **hard-link** где возможно (быстрее и без удвоения диска), `shutil.copy` как fallback.

## Формат YouTube metadata

```json
{
  "snippet": {
    "title": "...",
    "description": "...",
    "tags": ["..."],
    "categoryId": "22",          // People & Blogs (default for shorts)
    "defaultLanguage": "en"
  },
  "status": {
    "privacyStatus": "private",  // safe default; user makes public
    "selfDeclaredMadeForKids": false
  }
}
```

## Формат TikTok metadata

```json
{
  "caption": "title + description, capped at 2200 chars",
  "hashtags": ["..."],
  "language": "en",
  "schedule_at": null,
  "disable_duet": false,
  "disable_stitch": false,
  "disable_comment": false,
  "private": true                // safe default
}
```

## Формат Instagram metadata

```json
{
  "caption": "title\n\ndescription\n\n#hashtags",
  "share_to_feed": true,
  "language": "en"
}
```

## Tests

- `test_creates_release_directory_per_job` — проверяет что `data/releases/<job_id>/` создаётся.
- `test_links_or_copies_clip_into_release` — clip присутствует в release_dir и контент совпадает.
- `test_youtube_metadata_format` — title/description/tags + privacyStatus=private.
- `test_tiktok_metadata_format` — caption + hashtags + private=true.
- `test_instagram_metadata_format` — caption включает hashtags.
- `test_terminal_no_enqueue_next` — `next_kind is None`, дочерних джобов нет.
- `test_telegram_report_skipped_in_dry_run` — без чата → не падаем (терминальная задача).
- `test_handles_missing_clip` — graceful FileNotFoundError.

## После мержа

Это последняя стадия пайплайна для DRY-RUN. Следующие tentacle'ы:
- `publisher-youtube-uploader` — реальная заливка через cookies + `youtube-uploader`.
- `publisher-tiktok-uploader` — `tiktok-uploader` либа с anti-detect прослойкой.
- `publisher-instagrapi` — `instagrapi` с rotating proxy.

Эти tentacle'ы потребляют тот же `release_dir` от DRY-RUN — meta уже готова.
