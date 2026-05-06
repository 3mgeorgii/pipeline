# publisher-agent (DRY-RUN) — todo

- [ ] `bot/config.py`: `RELEASES_DIR = DATA_DIR / "releases"`, `PUBLISHER_DRY_RUN=True` (флаг для будущего переключения).
- [ ] `bot/workers/publisher.py`: переписать на DRY-RUN — копирование клипа + JSON-генерация для YT/TikTok/IG.
- [ ] Сохранить `enqueue_next`-репорт в чат с путями к release_dir.
- [ ] Тесты: формат всех 3 JSON-ов, существование файлов, terminal-stage поведение.
- [ ] PR против `devin/1778041276-seo-agent`, CI зелёный.

## Будущие tentacle'ы

- `publisher-youtube-uploader` — `youtube-uploader` (Go) + cookies.txt.
- `publisher-tiktok-uploader` — Python `tiktok-uploader` + AdsPower/Selenium.
- `publisher-instagrapi` — `instagrapi` + rotating residential proxies.
