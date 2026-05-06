# editor-agent — todo

- [ ] `bot/config.py`: `EDITOR_OUTPUT_WIDTH=1080`, `EDITOR_OUTPUT_HEIGHT=1920`, `EDITOR_VIDEO_CRF=23`, `EDITOR_AUDIO_BITRATE=128k`, `OVERLAY_LOGO_PATH` (env-var, optional).
- [ ] `bot/workers/editor.py`: переписать на реальный ffmpeg-pipeline (cut + crop + scale + overlay).
- [ ] Тесты с моками `subprocess.run`.
- [ ] PR против `devin/1778040562-analyzer-agent`, CI зелёный.

## После мержа

- seo читает контекст клипа (transcript_path).
- publisher загружает результат.
