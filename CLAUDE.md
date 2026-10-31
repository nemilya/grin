# grin — notes for Claude Code

Alexander Grin's stories: narration, films in several styles, the website grin.nemilya.me. Pipeline and data
format — README.md (most detailed: README.ru.md); the paper-theatre treatment — docs/treatment.md.

- Talk to the maintainer in Russian. The repository is public and English-first: code, comments, commit
  messages, docs in English (Russian translations of docs — `*.ru.md`). Film content (translation, subtitles,
  narration) — English; visual descriptions in bible.json — English and style-free (style — styles/*.json).
- **Media** (pictures, narration) are in the second repository nemilya/grin-media, laid over this folder:
  start with `make media-pull`; after generating — `make media-push`, then commit the JSON together with the staged
  `media.rev` (how it works — docs/media.md). Never commit media files here (.gitignore and CI stop it), never bypass the media check to
  regenerate files that are merely not pulled.
- Stage order and checks: `make status`. After editing a storyboard/bible — `make timeline` (cue/camera/asset errors
  are printed and fail the command), then look at frames: `node tools/capture.mjs stills <story> --scale 0.3`
  (+ `--debug` — flat work light, no focus: shows composition) and the sheet `out/<story>/stills/contact.jpg`.
- Paid calls (OpenRouter: translation, Seedream, TTS) — only when the task needs them; before mass generation check
  1–2 pictures. Prices: an image $0.018, a minute of narration ≈ $0.01.
- Don't shift sentence indices silently: editing `engine/text.py` (sentence splitting) moves the `at` cues in
  storyboards — afterwards compare sentence counts per paragraph (`prepared/en.json`).
- Russian-language data in the code stays Russian (abbreviations and regexes in text.py/prepare.py, chapter words
  in translate.py, the TTS lead 'Этот фрагмент:' in voicing.py — changing it makes all Russian takes stale).
- Light: the key light of the toy theatre is front-top (the puppeteer's lamp). A source behind the card's plane
  lights its back — the figure goes dark.
- Productions (docs/director-style.md): `stories/mate-in-3-tarkovsky` — `"base": "mate-in-3"` (text and voice from
  there), its own bible/storyboard/assets; all targets with `S=mate-in-3-tarkovsky`. Engine prompt edits must not
  change other productions' prompts (all their assets would go stale) — compare `assets.plan(<story>)` before/after.
- Rendering films (YouTube/Shorts: formats, subtitles, chapters) — docs/video.md; renders run on the maintainer's Mac
  (GPU), not in a cloud session.
- Tests: `make check`.
