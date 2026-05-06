# Tentacle: lilush-pipeline

Pivot проекта `codesp-bot-starter` → **Lilush**: мульти-агентный конвейер
для нарезки длинного видео в шортсы и постинга на YouTube/TikTok/IG.

## Высокоуровневый поток

```
Telegram (ссылка на видео)
        │
        ▼
[1. Intake]   ── валидирует URL, ставит job в очередь
        │
        ▼
[2. Downloader]   ── yt-dlp → /data/sources/<job>/source.mp4
        │
        ▼
[3. Curator/Analyzer]   ── транскрипт + сцен-детект + LLM-выбор моментов
        │                  → clips.json: [{start, end, hook, why}]
        ▼
[4. Editor (pool)]   ── ffmpeg: cut, vertical 1080×1920, subtitle burn-in,
        │              опц. зеркало/цветокоррекция, добавление capt-ов
        ▼
[5. SEO]   ── LLM по платформе: title / description / hashtags / hook,
        │     опц. trending-данные (Google Trends API, YouTube search)
        ▼
[6. Publisher]   ── YouTube Data API / TikTok API / IG Graph API
        │                  → пост-ссылки обратно в Telegram
        ▼
[7. Reporter]   ── статус каждой задачи в `data/jobs.db`
                  и сводка владельцу в чат
```

Каждый шаг — отдельный воркер (asyncio task), тянет работу из своей
очереди. Это даёт **естественную параллелизацию**: пока Downloader
качает видео #2, Editor режет видео #1, SEO готовит метаданные для #0,
Publisher заливает #-1. Никто не простаивает.

## Очередь и состояние

- **`data/jobs.db`** (SQLite через `aiosqlite`) — таблица `jobs`:
  `id, kind, payload_json, status, retries, created_at, updated_at`.
- Воркеры `LISTEN`/polling SQLite с интервалом, `UPDATE ... WHERE status='pending'`.
- Альтернатива при росте: Redis Streams + `arq`.

Зачем не сразу Redis: на одной VPS-ке SQLite достаточно до ~десятков
тысяч джобов в день; меньше движущихся частей.

## Агенты

| Агент          | Что делает                                        | CPU/IO        |
|----------------|---------------------------------------------------|---------------|
| `intake`       | парсит TG-сообщение, нормализует URL              | nil           |
| `downloader`   | `yt-dlp -f "bv*+ba/b" -S "res:1080,fps"`           | net + disk    |
| `analyzer`     | `whisper` (или `faster-whisper`) → транскрипт;    |               |
|                | `pyscenedetect` → cut points; LLM-ranker          | CPU + LLM     |
| `editor`       | `ffmpeg` атомарными командами, шаблоны фильтров   | CPU heavy     |
| `seo`          | LLM-генератор метаданных + опц. `pytrends`/YT API | LLM + net     |
| `publisher`    | YT Data API v3, TikTok Content Posting API,       | net           |
|                | IG Graph API. OAuth-токены в `state.json` (0600). |               |
| `reporter`     | агрегирует статусы, шлёт в TG через `bot.send`    | nil           |

## Технологии

- **Скачивание:** `yt-dlp` (CLI) + `requirements.txt`. Для авторизованных
  площадок — куки через `--cookies-from-browser` или сохранённый
  `cookies.txt`.
- **Транскрипт:** `faster-whisper` (CTranslate2-бэкенд, в 4× быстрее на
  CPU чем openai-whisper). Альтернатива — Whisper API (платно, быстрее).
- **Сцен-детект:** [`pyscenedetect`](https://www.scenedetect.com/) +
  `ffmpeg`-keyframes. Дополняем эвристикой по громкости речи.
- **Редактирование:** чистый `ffmpeg` через subprocess. Никаких
  `moviepy`/`movie.py` — медленнее и нестабильнее.
- **Шорт-вертикалка:** `ffmpeg -vf "crop=ih*9/16:ih,scale=1080:1920"` или
  blurred-bg pad для широкого исходника.
- **Сабы:** burn-in через `subtitles=...` filter, стиль через ASS.
- **«Зеркало»/цветокор:** см. блок «правовые риски» — это бесполезно
  против Content ID.
- **YouTube:** [YouTube Data API v3, `videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert).
  OAuth 2.0, refresh-токены.
- **TikTok:** [Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started).
  Требует TikTok for Developers аккаунт + одобрение приложения.
- **Instagram:** Graph API для бизнес-аккаунтов, `media_publish`.

## Где «brain отдыхает»

В исходном вопросе: «пока качает фильм мозг отдыхает?». Ответ: нет, при
правильной архитектуре каждый агент пилит свою стадию. Distribution:

- Скачивание идёт в **отдельном процессе/треде**, не блокирует event-loop.
- `analyzer` и `editor` запускают свои подпроцессы (`whisper`, `ffmpeg`)
  параллельно с downloader-ом.
- LLM-вызовы (`seo`, `analyzer`) — асинхронные, не блокируют.
- На одной VPS-ке можно крутить пул из N редакторов (по числу ядер) +
  по одному ингесту/SEO/публикеру.

## Что НЕ нужно (и почему)

### Mirror / минорная цветокоррекция «чтобы не забанили»
**Не работает.** YouTube Content ID:
- Сравнивает аудио-фингерпринт (Echoprint-like). Зеркало видео не меняет аудио вообще.
- Перцептивный видео-хеш (pHash) устойчив к flip-у и сдвигу яркости/контраста на ±10%.
- Pitch-shift аудио → ломает звучание + Content ID всё равно ловит
  по характерному ритмическому рисунку.
- Реальный обход: либо лицензия, либо твой собственный контент, либо CC0.

### Dolphin Anty / GoLogin / Multilogin / AdsPower
- Anti-detect-браузеры нужны, когда заходишь через **веб-UI** разных аккаунтов
  и хочешь, чтобы платформа не связала их по fingerprint-у.
- Для постинга на YT/TikTok/IG **через официальные API** они не нужны:
  ты ходишь по HTTPS с OAuth-токеном, не через браузер.
- Если очень нужно крутить веб-флоу — **AdsPower** имеет local-API,
  работает на Linux в headless через Xvfb. **Dolphin Anty** на Linux
  тоже есть, но без CLI/API в free tier.
- Multi-account для YT всё равно ловится по cookies, IP, behaviour, refresh-token-ам.

### MuMu Player на сервере
- Windows-онли официально. На Linux:
  [`Waydroid`](https://waydro.id/) (Android-контейнер на ядре Linux),
  [`Genymotion`](https://www.genymotion.com/) (платный, есть Cloud-вариант),
  Android-x86 в QEMU.
- **Зачем эмулятор вообще?** Для постинга в TikTok/IG достаточно их
  API. Эмулятор нужен только для дикого скрейпинга или мобильно-онли
  фич (например, TikTok Live).

### tmux
- На сервере полезен для **ручных** длительных задач (одноразовый
  rip, дебаг). Но Lilush должен крутиться как **systemd-сервис** или
  Docker-контейнер с `restart: unless-stopped`. tmux — не оркестратор.

### «Плагины Claude для SEO»
- У Claude нет marketplace плагинов в стиле GPT Store. Есть **MCP**-серверы
  (Model Context Protocol). Под SEO релевантные есть, но обычно их
  проще заменить прямыми API: `pytrends` (Google Trends), YouTube
  Data API (`search.list` с trending параметрами), Reddit API.
- Лучшая стратегия: **SEO-агент** — это просто отдельный LLM-промт +
  набор tool-ов (поиск трендов, проверка занятости тэга).

## Правовые риски (по делу, без морали)

1. **Чужие фильмы и сериалы → re-upload на YT.** YT забанит канал по
   strikes (3 = терминация). После — IP-бан и часто термината любых
   связанных аккаунтов. Mirror/цветокор не помогает (см. выше).
2. **TikTok** не использует Content ID того же уровня, но имеет систему
   жалоб + auto-ban при репортах правообладателя.
3. **Multi-account автопостинг** одной и той же нарезки на 50 каналов:
   считается spam-сетью, аккаунты блокируются пакетом, refresh-токены
   отзываются.
4. **«Чистые» альтернативные источники, на которых пайплайн работает
   без рисков:**
   - твой собственный контент (стримы, подкасты, длинные видео)
   - public domain (archive.org, Library of Congress)
   - Creative Commons (CC0, CC-BY) — тысячи часов на YT поиск-фильтре
   - лицензированный сток (Storyblocks, Pexels Video, Mixkit)
   - revenue-share с креатором (его длинные ролики → твои шортсы → %)

Технически Lilush работает одинаково для любого источника. Решение
о том, что в него скармливать — за владельцем.

## План tentacle-ов

Каждый — отдельная папка `.devin/tentacles/<scope>/` с CONTEXT + todo:

1. `pipeline-skeleton` — `data/jobs.db` schema, базовый воркер-loop,
   очередь, статус-репортер. Никаких реальных tool-ов, только каркас.
2. `intake-bot` — `/dl <url>` команда в Telegram, валидация, enqueue.
   Переиспользует существующий `wizard.py`/`handlers.py`.
3. `downloader-agent` — yt-dlp wrapper с retries, прогресс-репортинг.
4. `analyzer-agent` — `faster-whisper` + `pyscenedetect` + LLM-ranker.
5. `editor-agent` — ffmpeg-конвейер, шаблоны фильтров, A/B output.
6. `seo-agent` — LLM-генератор + Google Trends + YT search.
7. `publisher-agent` — YT/TikTok/IG, OAuth, retry-policy.
8. `ops-anti-detect` — опционально, AdsPower local-API через Xvfb.

P0 для рабочего MVP: 1 + 2 + 3 + 5 + 6 + ручной аплоад.
P1: 4 (умная нарезка), 7 (автопостинг).
P2: 8 (если останется потребность).

## Требования к серверу

- **Минимум:** 4 vCPU, 8 GB RAM, 50 GB SSD, любой Linux. Render Free
  не потянет (нет долгоживущих воркеров с CPU-нагрузкой).
- **Рекомендуется:** 8 vCPU / 16 GB / 200 GB SSD. На таком одна нарезка
  60-минутного исходника в шортсы занимает ~5–15 минут.
- **GPU:** не обязателен. `faster-whisper` на CPU «medium» model ~1×RT.
  С GPU (>=8 GB VRAM) ускорение ×3–10×.
