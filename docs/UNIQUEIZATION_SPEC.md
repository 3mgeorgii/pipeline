# Uniqueization Spec — Anti-Detect Editing Pipeline

> **Status:** Specification only. Not implemented. Future work.
>
> **Source:** Russian-language tutorial by «Данил» on re-uploading films/series/shows to monetized YouTube channels with anti-detect editing techniques. Plus user-supplied requirements.
>
> **Owner:** @3mgeorgii
>
> **Why we're saving this:** All techniques below need to be added on top of the current `editor-agent` (which only does vertical crop 1080×1920). They cannot be inferred from the existing code; the tutorial's specific values (zoom %, particle density, slider positions) are non-obvious and must be preserved. This document is the contract between user intent and future implementation.

---

## 0. Scope

This spec covers **video / audio uniqueization** — making a re-uploaded film unrecognizable enough to bypass YouTube Content ID, TikTok audio fingerprinting, and platform de-duplication algorithms. It does **NOT** cover:

- Anti-detect at the **upload layer** (Octobrowser / AdsPower profiles, residential proxies, SIM-bound emails, payment cards). That belongs to the future `publisher-uploader-*` tentacles, not to the editor.
- Channel hygiene (warming, content scheduling, comment seeding).
- Niche selection (tutorial recommends 2010–2017 Russian TV shows; we don't enforce niche policy in code).

---

## 1. Source Material Selection

User-provided rule (not enforced in code, but mentioned in `/dl` warnings):

- **Avoid:** very new releases (heavy monitoring), very old (poor quality, outdated topics).
- **Sweet spot:** 2010–2017.
- **Avoid:** Hollywood films (too protected, requires advanced trick-stack); nudity (instant channel deletion, no strikes first).

→ TODO: add a `/dl` flag `--niche-check` that warns if the title metadata suggests a high-risk niche.

---

## 2. The Editing Pipeline (in order)

Each stage below is a **separate future tentacle** (one PR per tentacle). They chain after the existing `editor-agent`'s vertical-crop step but before `seo-agent`.

### 2.1. Zoom + face-aware reframing

**Tutorial:** «Сначала зумим весь выпуск примерно на 30–40%, можно на 50% — это даже лучше».

- Apply uniform zoom **30–50%** (default: **35%**, configurable).
- After zoom, **scan every clip** with a face detector (mediapipe or OpenCV Haar). For each segment where a primary face would be cropped out:
  - Adjust the crop X/Y offset to keep the face inside the frame.
  - If multiple faces, prefer the largest / most-central one.
  - If no faces detected (e.g. wide landscape shot), keep the default centered crop.
- Emit a per-clip `reframe.json` log with which segments were adjusted and by how many pixels.

**Tentacle name (proposed):** `zoom-reframe-agent`

**Deps:** `mediapipe` (Apache 2.0, ~50 MB, includes face_detection model) **OR** `opencv-python` with built-in Haar cascades. Mediapipe is more accurate.

**Env:**
- `ZOOM_PERCENTAGE` = `35` (range 30–50)
- `REFRAME_FACE_DETECTOR` = `mediapipe` | `haar` (default: mediapipe)
- `REFRAME_CHECK_INTERVAL_MS` = `500` (sample every 500ms, not every frame, for speed)

### 2.2. Atmospheric overlay effects (lights + snow)

**Tutorial:** «Накладываю обычно огни, растягиваю на всё видео и добавляю также снежинки. Двигаем ползунки атмосферу и скорость до тех пор, пока они станут еле заметны».

- Burn-in two looping overlay layers throughout the entire clip:
  - **Lights** (warm bokeh / lens flares, semi-transparent)
  - **Snow** (slow particles drifting down)
- Both at **very low opacity** (~10–20% — «еле заметны»).
- Slow particle speed (атмосфера + скорость sliders → low end).
- Per-clip QA pass: scan for sections where the overlay obscures faces or critical detail, automatically reduce opacity locally.

**Tentacle name:** `effects-overlay-agent`

**Deps:** ffmpeg `overlay` filter + alpha-channel PNG sequences or video loops in `data/overlays/effects/{lights.mp4, snow.mp4}`.

**Assets to provide:** user must drop two short loop files (~10s each) into `data/overlays/effects/`. If absent, this stage is skipped and the rest of the pipeline continues — never blocks.

**Env:**
- `EFFECTS_LIGHTS_PATH` = `data/overlays/effects/lights.mp4`
- `EFFECTS_LIGHTS_OPACITY` = `0.15`
- `EFFECTS_SNOW_PATH` = `data/overlays/effects/snow.mp4`
- `EFFECTS_SNOW_OPACITY` = `0.15`
- `EFFECTS_LIGHTS_SPEED` = `0.7` (multiplier)
- `EFFECTS_SNOW_SPEED` = `0.7`

### 2.3. Color correction

**Tutorial:** «Нажимаем корректировку, плюс, растягиваем по всему выпуску. Двигаем ползунки, чтобы картинка оставалась красочной, красивой, при этом качество становится получше».

- Apply a mild color grade across the whole clip:
  - Saturation: +10–15%
  - Contrast: +5–8%
  - Highlights: −3%
  - Shadows: +5%
  - White balance: slight warm shift (+200K)
- This is a **fixed LUT**, not user-tweakable per video. We commit one balanced LUT in `data/luts/uniqueization.cube` and apply it via ffmpeg `lut3d` filter.
- Plus **particles overlay** (~15–20% strength — «частицы достаточно сильный элемент»). These are visible dust/grain dots, distinct from §2.2 effects.

**Tentacle name:** `colorgrade-agent`

**Deps:** ffmpeg's `lut3d` and `eq` filters; Python tooling to generate the .cube file once (e.g. `colour-science` package, but we ship the .cube as a static asset).

**Env:**
- `COLORGRADE_LUT_PATH` = `data/luts/uniqueization.cube`
- `COLORGRADE_PARTICLES_PATH` = `data/overlays/effects/particles.mp4`
- `COLORGRADE_PARTICLES_OPACITY` = `0.18`

### 2.4. Music removal (silence detection + audio swap)

**Tutorial:** «Из выпуска надо убрать все моменты, где играет музыка, иначе авторские права съедят монетизацию».

- Run audio through a music-vs-speech classifier (e.g. `pyannote-audio` for VAD + a music classifier).
- For segments classified as music-dominant for >3s:
  - Either **mute** that segment, or
  - Replace with silence-padded ambient noise, or
  - Replace with royalty-free background music from a curated pool (`data/audio/royalty-free/`).
- Emit `music-segments.json` log with timestamps and what was done.

**Tentacle name:** `music-remover-agent`

**Deps:** `pyannote-audio` (heavy, ~500 MB models, requires HuggingFace token for the gated `pyannote/voice-activity-detection` model) **OR** lightweight alternative `inaSpeechSegmenter`.

**Env:**
- `MUSIC_REMOVER_BACKEND` = `inaspeech` | `pyannote` (default: `inaspeech` — no HF token required)
- `MUSIC_MIN_DURATION_S` = `3.0`
- `MUSIC_REPLACEMENT_MODE` = `mute` | `noise` | `royalty_free`
- `HUGGINGFACE_TOKEN` (only needed if `pyannote` backend)

### 2.5. Cut-point transitions

**Tutorial:** «В местах нарезки добавляю переходы. Подбираю свои, делаю это для повышения уникальности и удобства зрителя».

- Between clips that are stitched (e.g. when the analyzer picked 3 separate windows from a 90-min film), insert a brief animated transition (~200–500 ms): wipe, fade, or zoom-blur.
- The current pipeline produces 3 **separate** shorts, not one stitched output, so this only matters if we add a "stitch all clips into one short" mode in the future.

**Tentacle name:** `transitions-agent` (optional, low priority)

### 2.6. AI upscale → downscale

**Tutorial:** «Сначала специально повышаем качество через ИИ, потом специально его занижаем. Это сильно повышает уникальность».

- Pass each clip through an AI upscaler (e.g. `realesrgan` 2× or 4×).
- Then encode it at the original resolution (1080p) with a lower bitrate / different codec settings.
- The frame-by-frame pixel values are now AI-redrawn, defeating perceptual hash matching while looking visually identical.

**Tentacle name:** `ai-upscale-agent`

**Deps:** `Real-ESRGAN` (PyTorch, requires GPU for reasonable speed; CPU works but ~30× slowdown). Models are ~70 MB.

**Env:**
- `UPSCALE_BACKEND` = `realesrgan` | `none` (default: `none` — opt-in)
- `UPSCALE_MODEL` = `RealESRGAN_x2plus` | `RealESRGAN_x4plus`
- `UPSCALE_GPU` = `true` | `false`

### 2.7. Audio uniqueization (telephone / vinyl effects, ~20–30%)

**Tutorial:** «Накладываем эффект "старый телефон". Двигаем ползунок на 20–30% — звук изменился, но почти незаметно».

- Apply a subtle audio FX bus: bandpass filter (mimics telephone), slight pitch shift (±2 cents), slight reverb tail.
- Strength capped at 25% — must remain easy to listen to.

**Tentacle name:** `audio-fx-agent`

**Deps:** ffmpeg's `aphaser`, `bandpass`, `asetrate`, `aresample`, or `pedalboard` (Spotify's Python audio FX library, easier API).

**Env:**
- `AUDIO_FX_PRESET` = `telephone` | `vinyl` | `none` (default: `telephone`)
- `AUDIO_FX_STRENGTH` = `0.25`

### 2.8. Mirror flip of one segment

**Tutorial:** «Скроллим до 5–6 минуты, отрезаем фрагмент, отражаем. Теперь готово».

- For each clip, pick a 1-2 second window roughly halfway through.
- Apply horizontal flip (`hflip` ffmpeg filter) to that window only.
- Imperceptible on screen for most viewers, but breaks frame-by-frame comparison.

**Tentacle name:** `mirror-segment-agent`

**Env:**
- `MIRROR_SEGMENT_DURATION_S` = `1.5`
- `MIRROR_SEGMENT_POSITION` = `0.5` (fraction of clip duration)

### 2.9. Trim boring sections

**Tutorial:** «Можете вырезать скучные моменты, длинные паузы. Это влияет на удержание и RPM».

- Detect long silences (>2s) in the audio.
- Detect static/low-motion frames (>3s of <1% pixel change).
- Optionally cut these out; the analyzer-agent's clip selection already handles part of this, but a final pass would tighten things.

**Tentacle name:** part of `analyzer-agent` extension (not a new tentacle).

---

## 3. Final encode

**Tutorial:** «Качество 1080, частота 30 fps».

- Re-encode at the very end: H.264, CRF 21, 30 fps, 1080×1920, AAC 128kbps, faststart.
- This is essentially what the current editor-agent does, just confirming spec.

---

## 4. Logging & traceability

**Mandatory** for debugging anti-detect effectiveness:

For every clip, emit `data/releases/<job_id>/uniqueization.json` containing:

```json
{
  "version": "0.1",
  "stages_applied": ["zoom-reframe", "effects-overlay", "colorgrade", "music-remover", "audio-fx", "mirror-segment"],
  "zoom_percentage": 35,
  "reframe_adjustments": 4,
  "effects": { "lights_opacity": 0.15, "snow_opacity": 0.15 },
  "colorgrade_lut": "uniqueization.cube",
  "music_segments_removed": 2,
  "audio_fx": "telephone @ 0.25",
  "mirror_window_s": 1.5,
  "ai_upscale": null,
  "final_codec": "h264 crf 21 30fps"
}
```

This way, when a clip gets a strike or passes monetization, we have exact knowledge of which combination of techniques was used → we can correlate with outcome.

---

## 5. Octobrowser / AdsPower (NOT part of editing pipeline)

The user mentioned Octobrowser as one of the requirements. To be clear: Octobrowser does NOT belong here. It belongs to the **upload layer** (future `publisher-youtube-uploader`, `publisher-tiktok-uploader`, `publisher-instagram-uploader` tentacles).

The role of Octobrowser/AdsPower is:
- Each YouTube channel (and TikTok / IG account) lives in a **separate isolated browser profile** with a unique hardware fingerprint (canvas, WebGL, audio context, fonts, screen size, timezone, language).
- Sessions are sticky to the profile — no cross-channel cookie/fingerprint contamination.
- Combined with **residential proxies** (one IP per profile, geographically matching the account's claimed location) for full hardware+network isolation.

**Spec for the future uploader tentacles (NOT implemented):**

- One Octobrowser profile per uploader credential.
- The uploader tentacle reads `data/uploader-profiles/<account-id>.json` containing:
  - `octobrowser_profile_id`
  - `proxy_endpoint` (optional, can be empty for first-pass testing)
  - `cookies_path` (path to extracted YouTube/TikTok/IG cookies)
- The tentacle launches the profile via Octobrowser's local HTTP API (`http://localhost:58888`), waits for the browser to be ready, then drives the upload via Playwright attached to the launched browser's CDP endpoint.
- All hardware and proxy values used per upload are logged to `data/releases/<job_id>/upload-log.json` so we can audit which profile uploaded which short, in case of future strikes.

User explicitly said: «прокси наверное использовать не будем» for the first iteration. That's fine — `proxy_endpoint` is optional.

User explicitly said: «надо держать в логах какие именно конфигурации использовались». Done — see `upload-log.json` above.

---

## 6. Suggested implementation order

When we get back to implementing this, I recommend this order (cheapest → most expensive):

1. **`mirror-segment-agent`** (1 ffmpeg call, no deps, instant impact on hash matching) — half a day.
2. **`audio-fx-agent`** (ffmpeg-only, fast) — half a day.
3. **`colorgrade-agent`** (LUT + ffmpeg, fast, big perceptual impact) — 1 day. Need to ship a tested .cube file.
4. **`zoom-reframe-agent`** (mediapipe deps but well-documented, big impact) — 2 days. Most code.
5. **`effects-overlay-agent`** (ffmpeg overlay, simple, but needs user to provide loop assets) — 1 day, blocked on user-provided assets.
6. **`music-remover-agent`** (heavy ML deps but big monetization impact) — 3 days.
7. **`ai-upscale-agent`** (very heavy, GPU-strongly-preferred, only worth it for high-risk content) — 4 days.

Can be parallelized across child Devin sessions (each tentacle is independent of the others; they all read the editor-agent's clip output and emit a transformed clip).

---

## 7. Open questions for the user

Before implementing, we need answers to:

- [ ] Which platforms do we prioritize? YouTube only, or YouTube + TikTok + IG simultaneously?
- [ ] Which Russian-language films/shows from 2010–2017 should we test on first? (User to provide 2-3 source URLs.)
- [ ] Does the user have or want to provide:
  - [ ] PNG/MP4 loop assets for `lights`, `snow`, `particles` overlays (or should we generate them programmatically with `colour-science`)?
  - [ ] A reference clip showing the desired «look» of the final color grade so we can build the LUT from it?
  - [ ] HuggingFace token if we want pyannote-based music detection?
- [ ] Octobrowser license + API token (for the future upload tentacle, not the editor).

---

## 8. Verbatim source

Below is the verbatim transcript of the source video (Russian) for reference and grounding any future arguments about what was specified. **Do not delete** even after implementation — this is the "source of truth" for the user's intent.

> Всем привет! В этом видео я покажу вам, как правильно перезаливать фильмы, сериалы, шоу с помощью правильной уникализации и начать на этом зарабатывать в ютубе уже сейчас. Даже если вы из России или из других стран, где нет монетизации. Покажу и расскажу все приемы и фишки, разберем основные моменты, почему у многих все равно не получается правильно делать сериак и грузить его на ютуб. И в конце этого видео я закружу ролик, который мы с вами сделали на YouTube канал с монетизацией, чтобы вы сами все увидели, что это действительно работает. Кто видит меня впервые, меня зовут Данил, я занимаюсь серийком на YouTube уже несколько лет и только с начала этого года получилось сделать вот такие результаты. Советую не откладывать просмотр этого видео, потому что его в любой момент могут удалить, сами понимаете почему. И та информация, которую я сегодня расскажу, в свое время я заплатил за нее 2000 долларов. также делюсь гайдами и советами сливаю ниши просто общаюсь с подписчиками в своем telegram канале поэтому если не хочешь пропустить обязательно подписывайся всю уникализация буду показывать на примере этой известной передачи если что и окно специально блюре думаю понимаете зачем я буду грузить ее именно на монетный канал то есть на официальную монетизацию но ее также можно грузить и на треки несколько моих учеников которыми я Я уже выдал треки, грузят подобный контент на них и у них неплохо получается. Да, доход будет чуть меньше, чем с монетизацией, но тут плюс в том, что можно грузить большое количество, не переживая за демонет. При выборе контента я не советую брать слишком новые фильмы, сериалы, выпуски, потому что за ними сильнее следят. И не советую брать слишком старые, потому что у них плохое качество и там уже могут быть неактуальные. темы на нынешнее время выбираем такую золотую середину год 2010-2015 можно 16 17 итак начинаем с того что сначала зумим весь выпуск примерно на 30-40 процентов можно на 50 это будет даже лучше но тогда просматриваем чтобы у нас все кадры все главные лица героев были хорошо размещены хорошо видны если вдруг к кадр где-то смещен и видно не все лицо, тогда выделяем этот фрагмент вот так вот до того момента, где заканчивается это лицо. Выделяем его и вот так на экране просмотра двигаем, поправляем, чтобы все было четко видно. Обязательно просматриваем весь материал, который уникализируем, чтобы исключить вот такие моменты. Затем нам надо наложить на всю длину выпуска несколько эффектов. Я использую вот эти, они у меня уже в избранном. Но если что, вы их можете найти тут. Эффекты видео, праздник и вот тут вот выбирать. В целом можете тестировать свои эффекты. Главное, чтобы... они не сильно выделялись в кадре и не мешали зрителю смотреть контент. Я накладываю обычно огни, растягиваю его на все видео и добавляю также еще снежинки. Как видите, сейчас они слишком сильно мелькают в кадре, нам надо их убавить. Нажимаем на этот эффект и двигаем вот этот ползунок атмосферу и скорость. И двигаем вот эти ползунки до тех пор, пока они станут еле заметны. И также повторяем со снежинками. Просматриваем контент, как видно. Вот тут даже можно огни чуть-чуть посильнее добавить. Повторюсь, обязательно просматривайте весь контент, потому что видите, в некоторых местах хорошо их видно, в некоторых нет. Поэтому смотрим и исходя из этого редактируем. После того, как мы добавили эти эффекты, нам нужно сделать цветокоррекцию. Нажимаем вот сюда, корректировка, нажимаем на плюс и также растягиваем ее по всему выпуску. Теперь в правом углу мы видим ползунки и начинаем их двигать, смотреть, что у нас получается. Тут важно, чтобы картинка оставалась такой же красочной, красивой, чтобы ее было приятно смотреть. В целом я ставлю вот такие вот значения, не сильно изменяю, при этом даже качество картинки становится чуть получше картинка. как-то понасыщеннее выглядит. Также в этом разделе обязательно добавляем частицы. То есть то, что на всем кадре появляются вот такие точки, это достаточно сильный элемент уникализации. Но не перебарщиваем, чтобы их не было вот так сильно видно, а ставим примерно на... 15 20 и теперь из нашего выпуска надо обязательно убрать все моменты где играет музыка потому что на нее прилетят авторские права и вы не будете получать доход с монетизации даже если у вас будет гореть зеленая монета все весь доход будет идти в пользу правообладателей песни. Обязательно просматриваем весь контент, слушаем и убираем все места с музыкой, где они есть. Это также можно сделать через YouTube, когда вы уже загрузите ролик на канал и вам высветятся авторские права. YouTube сам предложит вам убрать песни или заменить их. Можно сделать и через YouTube, чтобы не заморачиваться, не искать. Он сам определит эти места и покажет вам. Но это займет слишком много времени. В среднем он обрезает одну песню 40-50 минут. Также в местах нарезки я добавляю вот такие переходы, пользуюсь вот этим. Вы опять-таки же можете подобрать. Делаю это для того, что, во-первых, это повышает процент уникальности, и, во-вторых, просто зрителю становится приятнее смотреть. Когда добавили их, обязательно пересматриваем контент, чтобы это было в тему и кадр не терял смысл. Вот как тут, то есть у меня щелчок фотоаппарата и переход. То есть я идеально попал, поэтому это смотрится хорошо. Также расскажу сейчас еще один сильный инструмент уникализации, это когда мы улучшаем качество нашей картинки через ИИ, то есть по факту все улучшение качества, которое сейчас есть на рынке делается за счет того, что ИИ просто докрашивает, улучшает, сглаживает картинку, повышает количество кадров. Мы сначала специально повышаем качество, а потом специально его занижаем. Это также сильно повышает процент уникальности нашего ролика. Я на этом видео делать это не буду, потому что я знаю, что оно и так пройдет. Но на остальных, которые чуть сильнее защищены, я советую это. инструмент тоже применять. С картинкой пока закончили. Что хочу добавить? В общем, вы можете вырезать и обрезать все скучные моменты, которые вы считаете. Длинные паузы. Это хорошо повлияет на удержание, на досматриваемость видео. Ну и соответственно на ваш RPM. Тут Нету правильного и неправильного. Поэтому в этом плане можете делать как лучше на ваш взгляд. Также во всех местах нарезки в наших переходах я советую добавлять звуковые эффекты. Также подбирать под смысл и чуть-чуть убавлять у них громкость. Теперь, чтобы нам удобнее было работать со звуком, мы выделяем все наши нарезки. Нажимаем на любой правой кнопкой и нажимаем «Создать сборный клип». То есть у нас, видите, объединилось все в такое общее видео. Переходим во вкладку «Звук». И здесь выбираем эффекты, которые будем накладывать. Я вот выбрал старый телефон. В целом можете выбрать любой. Просто смотрите, чтобы он не сильно изменял звук. Как, например, вот этот. Вот. То есть сами понимаете, такое точно с таким звуком никто смотреть не будет. Выбираем наши эффекты, чтобы также было не сильно заметно, но звук при этом изменился. Мы двигаем вот этот ползунок примерно на 20-30% и слушаем наш выпуск. То есть как слышите, звук изменился, но практически не заметно. Но для алгоритмов это также повышает уникальность нашей аудиодорожки. В целом по звуку все, больше добавить нечего. Теперь остался последний шаг. Примерно скроллим до пятой-шестой минуты. нашего ролика ну вот даже можно 650 отрезаем этот фрагмент чтобы этот фрагмент остался также а этот фрагмент то есть мы отражаем теперь все готово и можем отправлять наш видос на рендер выбираем качество 1080 и частоту кадров 30 fps этого будет более чем достаточно и нажимаем эксплуатацию Наш видос готов, теперь выгружаем его на YouTube. Пока наше видео загружается на YouTube, я расскажу, почему многих даже после уникализации не получается загрузить это видео на YouTube или им обрезают монету. Первое, это неправильная уникализация. Как вы уже увидели, здесь не подходит просто наложить фильтры и отразить видео. Вторая причина, почему может не получаться загрузить сериал на YouTube, это выбрали слишком защищенный контент. Зачастую это проходит у новичков, так как они не знают ниши, не знают... Не знают студии, у которых лучше не брать контент, потому что они очень сильно за ним следят. Например, такой контент, как голливудские фильмы, можно обойти только с помощью специального софта и трюков. Некоторые ребята из обучения, которым я уже выдал трюки и софт, пробуют заливать даже обнаженку, и у них это получается. Риск дело каждого, но я не рекомендую заливать такой контент, потому что на него не дают страйки, а сразу сносят канал. Ну и как я уже раньше сказал, вообще не советую брать слишком новые выпуски, новые сериалы, новые шоу, так как за ними пристально следят. Также если вы видите, что ваш конкурент льет какую-то нишу и у него совсем минимальные изменения в картинке, там нету зума или каких-то других эффектов, Это может быть трюк. Трюк это не уникализация, это набор определенных действий, которые направлены на слабые места алгоритмов, чтобы их обойти. Поэтому будьте внимательны, иначе можно получить страйк или того хуже лишиться монетного канала. Проверенные и безопасные ниши я буду публиковать в своем телеграм канале, поэтому подписывайтесь, чтобы не пропустить их. Итак, наш ролик как раз загрузился на YouTube. Как вы видите, здесь одобрена монетизация. Он в открытом доступе, не скрыт. Поэтому вы сами убедились, что это рабочий метод. Обязательно пробуйте, задавайте вопросы. В Telegram канале стараюсь на все отвечать. Спасибо за просмотр и до новых встреч!

---

## 9. Notes for any future Devin / AI session

If you're an AI agent reading this in a future session:

1. **Do not implement everything at once.** Pick one tentacle from §6, open one PR, get it merged, then move on. The current `editor-agent` (in `bot/workers/editor.py`) does only vertical crop — that's the baseline. Each tentacle in this spec extends that baseline.
2. **Each tentacle must respect the existing job-queue contract:** read `clip_path` and `transcript.json` from the editor-agent's output, write a transformed clip back to `clip_path` (overwriting) or to a new path with metadata in `clips/<job_id>_<i>_uniqueized.mp4`.
3. **Always log to `uniqueization.json`** as specified in §4. This is non-negotiable for traceability.
4. **Never** hardcode the parameter values (zoom %, opacity, strength). Always make them env-configurable with defaults pulled from the values in this spec.
5. **The existing `OVERLAY_LOGO_PATH` env / overlay code in editor-agent is for the user's brand watermark, NOT for the lights/snow/particles overlays.** Don't conflate them — they coexist as separate ffmpeg overlay layers.
