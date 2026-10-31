# Alexander Grin's stories: narration, films, website

**English** · [Русский](README.ru.md)

An engine that turns a short story into narration and a film in several visual styles, and the website
**[grin.nemilya.me](https://grin.nemilya.me)** where the stories are read, listened to and watched. A story is
translated (Russian → English), narrated in both languages and staged on a WebGL scene (three.js): layers in
depth, light, depth of field, camera. Every frame is computed from time — right in the browser on the site,
or captured to mp4.

Stories so far, by Alexander Grin (1880–1932):

| story | productions |
|---|---|
| *Mate in Three Moves* (1908), `stories/mate-in-3` | **paper theatre** (cut-outs on a desk under a lamp) and **in the manner of Tarkovsky** (`stories/mate-in-3-tarkovsky`: photographic layers, long takes, rain, fog, silence) |
| *The Power of the Incomprehensible* (1918), `stories/sila-nepost` | **silent film → autochrome** (painted sets, tinted black and white, intertitles, a pianist) |
| *The Crime of the Fallen Leaf* (1918), `stories/leaf-story` | **avant-garde 1918** (cubo-futurist painting, suprematist geometry) |

Each production has a vertical 9:16 and a horizontal 16:9 cut.

> Documentation in `docs/` and code comments are being translated from Russian; [README.ru.md](README.ru.md) is
> the most detailed description for now.

## Quick start

macOS (on Linux — the same through your package manager):

```bash
brew install python ffmpeg node          # Python 3.10+, ffmpeg, Node 18+
python3 -m pip install numpy pillow
make setup                               # checks the above, npm install, Chromium for capture, creates local.mk
make media-pull                          # pictures and narration from nemilya/grin-media (≈ 0.3 GB)
```

```bash
make status S=mate-in-3                  # what is ready, stage by stage
make preview S=mate-in-3                 # player without rendering: http://127.0.0.1:8720/stage/?story=mate-in-3
make video-demo S=mate-in-3              # the finale, 1080×1920 → out/mate-in-3/mate-in-3-demo.mp4
make site && make serve                  # the website → http://127.0.0.1:8730/
make admin                               # read-only admin: assets, character sheets, storyboard, narration
```

The whole cycle — new machine → work → build → deploy to the server — [below](#full-cycle-from-a-clone-to-the-live-site).
Rendering films for YouTube, Shorts and social media (formats, subtitles, chapters, thumbnails, timing) — [docs/video.md](docs/video.md).

`OPENROUTER_API_KEY` in `local.mk` is needed only to generate (translation, images, narration) — all generated
media are already in the media repository.

## Pipeline

Each stage writes files into `stories/<story>/`, the next one reads them. Generated files carry a fingerprint
(text + settings + references): when something upstream changes, what depends on it becomes *stale*, the rest is
kept. `make status` shows everything at once.

| | stage | command | files |
|---|---|---|---|
| 1 | text: paragraphs → sentences → words | `make prepare` | `prepared/ru.json` |
| 2 | glossary and translation by paragraph | `make translate` | `glossary.json`, `translations/en.json`, `prepared/en.json` |
| 3 | bible: world, characters and poses, sets, props | by hand / agent | `bible.json` |
| 3 | storyboard: scenes → shots tied to sentences | by hand / agent | `storyboard.json` |
| 4 | assets: character sheets → pose cut-outs (chroma key → alpha) → sets | `make assets-used` | `assets/`, `assets/assets.json` |
| 5 | narration by paragraph, checked by transcription | `make voice` | `voicings/<id>/` |
| 6 | timeline: shot timing from speech, scene state, subtitles | `make timeline` | `build/timeline.json` |
| 7 | sound: voice + ambience + synthesized music + effects | `make sound` | `build/sound.wav` |
| 8 | frames: storyboard stills / the film (+ a social-media cut) | `make stills` / `make video` | `out/<story>/` |

Images — Seedream via OpenRouter ($0.018 per image); narration — Gemini TTS (≈ $0.01 per minute). Cut-outs are
generated on a flat chroma key and keyed with a soft edge; they are stored as lossless WebP.

## Media: a second repository

How the two repositories work together, with an example and the everyday rule — **[docs/media.md](docs/media.md)**.

Code, texts, translations, bibles, storyboards and manifests live here. Pictures and narration
(`stories/**/*.webp|jpg|opus`) live in **[nemilya/grin-media](https://github.com/nemilya/grin-media)** at the same
paths. Its git dir is `.media.git/` and its work tree is this folder, so the files sit exactly where the engine
expects them. `media.rev` (one line, committed) pins the media commit this code commit needs: any commit can be
reproduced with `git checkout …` and `make media-pull`.

```bash
make media-pull      # the media of media.rev (LATEST=1 — the tip of the media branch)
make media-push      # after generating: commit and push changed media, write media.rev (commit it with the JSON)
make media-status    # pulled? changed locally? pushed?
```

- the media branch is named after the code branch (`main` → `main`); concurrent pushes are merged automatically;
- until the media of `media.rev` are pulled, `make assets`, `make voice` and `make site` refuse to run — otherwise
  a fresh clone + `make assets` would pay to redraw the whole film (`MEDIA_CHECK=0` overrides);
- the `pre-push` hook (`tools/hooks`, installed by `make setup` and `make media-pull`) stops code whose
  `media.rev` is not pushed yet.

## Full cycle: from a clone to the live site

**1. A new machine (once).**

```bash
git clone https://github.com/nemilya/grin && cd grin
make setup            # checks python/numpy/pillow/ffmpeg/node, npm install, Chromium, creates local.mk, installs the git hook
make media-pull       # pictures and narration of media.rev (≈ 0.3 GB, a few seconds to a minute)
make status S=mate-in-3
```

In `local.mk` (not in git; can be copied from the old checkout): `OPENROUTER_API_KEY` — only to generate;
`DEPLOY` and `SITE_URL` — only to publish (step 4).

**2. A server for the site (once).** nginx serving a folder, https via certbot, DNS — [deploy/README.md](deploy/README.md)
(a ready `deploy/nginx.conf`). The site is static: everything it needs is in `dist/`.

**3. Work: a new story or changes** (on your machine or in a Claude Code cloud session):

```bash
git pull && make media-pull                    # the current code and the media it pins
# … text → translation → bible → storyboard → make assets-used / make voice (paid) → make timeline → stills
make media-push                                # pictures and narration → grin-media; media.rev is staged
git add -A stories/<story> && git commit -m "…" && git push      # the hook checks the media are pushed
```

A new story appears on the site once it is listed in `site.json` (`stories`, its `voicings` and `videos`).

**4. Publish** (on your machine — deploy goes over ssh, which a cloud session doesn't have):

```bash
git pull && make media-pull     # exactly what is in main
make site                       # → dist/; the first build ≈ 30 min (video sound for every production and language),
                                #   then only what changed
make serve                      # look at it: http://127.0.0.1:8730/
make deploy-dry                 # what would be uploaded
make deploy                     # upload → https://grin.nemilya.me
```

`make deploy` uploads exactly the build you have seen and refuses a stale one (texts, narration, storyboards, assets,
`site.json`, the scene changed after `make site`). Details — [deploy/README.md](deploy/README.md).

## Layout

```
stories/<story>/
  story.json             source, language and format of the film, style, narration
  prepared/ ru|en.json   text: paragraphs, sentences, words (paragraph ids shared across languages)
  glossary.json  translations/en.json        translation
  bible.json  storyboard.json                staging
  assets/  voicings/  overrides/             generated (with fingerprints; media files — in grin-media)
  build/                 timeline and sound (not in git)
engine/    text, prepare, translate, llm, openrouter, voicing, align, audio, pricing; assets (Seedream + key),
           timeline (storyboard → shots), sound (synthesis and mixing), site, deploy, media, __main__ (harness)
stage/     the scene: index.html, js/stage.js, paper.js, post.js, geometry.js, fonts/, vendor/three
site/      website styles, scripts, fonts, texts (site.json — what is published)
tools/     capture.mjs (stills and video), admin, serve, style_lab, hooks/
styles/ directors/   visual styles of assets and directing presets
docs/      pipeline, new styles, the site, directing notes, story analyses
```

`make test` — tests without network; `make check` — tests + JS syntax.

Open work and implementation notes — [TODO.md](TODO.md) ([по-русски](TODO.ru.md)).

## License

Code — [MIT](LICENSE). Everything generated for the project — pictures, narration, translations, bibles,
storyboards, website texts — is dedicated to the public domain: [CC0 1.0](LICENSE-content). Alexander Grin's
stories are in the public domain. Third-party: three.js — MIT (`stage/vendor/three/LICENSE`), the fonts Source
Serif 4 and Golos Text — OFL (`site/fonts/`, `stage/fonts/`).

Made together with [Claude Code](https://claude.com/claude-code).
