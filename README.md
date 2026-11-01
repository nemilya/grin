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

| | |
|---|---|
| [`docs/video.md`](docs/video.md) | rendering a film for YouTube, Shorts, social media: the productions' formats, subtitles, chapters, thumbnails, timing |
| [`docs/media.md`](docs/media.md) | media: how `grin` and `grin-media` work together (`media.rev`, `make media-pull` / `media-push`) |
| [`docs/pipeline.md`](docs/pipeline.md) | the film pipeline stage by stage (in, out, check, cost, who decides) and the automation plan |
| [`docs/new-style.md`](docs/new-style.md) | how to add a new video style (style, director, production → site) |
| [`docs/site.md`](docs/site.md) | the site: pages, video in the browser, `site.json`, the layout of `dist/`; deploy — [`deploy/README.md`](deploy/README.md) |
| [`docs/director-style.md`](docs/director-style.md) | the Tarkovsky production: the film language, what was added to the engine |
| [`docs/treatment.md`](docs/treatment.md) | the director's treatment of the paper theatre; the original brief (in Russian) — [`brief.md`](brief.md) |

The engine continues `nemilya/mountain-rock` (text, translation, narration, a site with reading and highlighting) —
modules were carried over from there and adapted.

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

The capture browser is Playwright's Chromium (pinned to `playwright@1.59.1`: newer versions don't install Chromium
on macOS 13); if it is missing, an installed Google Chrome is used. The GPU is chosen automatically: capture tries
the GPU first and falls back to the software SwiftShader (≈ 1 s/frame at 720×1280); set it explicitly with
`CAPTURE_GL = gpu` or `cpu` in `local.mk`. The first line of a render says which: `WebGL: … — GPU` (Apple M…,
NVIDIA…) or `software renderer` (SwiftShader).

```bash
make preview F=horizontal   # the same for 16:9 (&tl=horizontal); &debug — work light, &shot=s05g — from a shot
```

After a render, next to the master (1080×1920, a high bitrate — for editing and the archive) comes
**`…-share.mp4` — a version for social media**: 720×1280, H.264, ≈ 3.5 Mbit/s, AAC 128k, faststart — Reels, Shorts,
TikTok, Telegram take it without re-encoding (≈ 25 MB per minute); it is made gently (hardware on a Mac, low priority,
2 threads). The film has no burnt-in subtitles (for YouTube — the `.srt` from `make youtube`); for social media it is
better to burn them in: `make video SUBS=1` → `…-subs.mp4` and `…-subs-share.mp4`. For a finished file —
`make share FILE=out/mate-in-3/mate-in-3-demo.mp4`; to skip it — `--no-share`.

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

While an asset is missing, the scene draws a **placeholder** (a coloured silhouette with a label); while a paragraph
is not narrated, its timing is **estimated** from the reading pace: the storyboard can be watched and edited from day
one, everything after that only refines it. Without an agent — the plan in [TODO.md](TODO.md).

## Formats: vertical and horizontal

The full recipe for YouTube and Shorts (which production has which format, which file goes where, subtitles, chapters,
timing) — **[docs/video.md](docs/video.md)**.

One film — several formats (`story.json → formats`). The main one is vertical 9:16 (`film`); horizontal 16:9 for
YouTube is `formats.horizontal` with its own storyboard `storyboard-16x9.json`, which **inherits** the main one
(`"extends": "storyboard.json"`) and changes only the cameras (`cams` — the same names, framed for 16:9) and individual
shots (`shots`: edits by id, `drop` — remove, `add` — add). Translation, narration, sound, assets, cues and the scene
state are shared; subtitles are laid out for the format (in 16:9 — at the bottom, up to 84 chars).

```bash
make video-demo F=horizontal     # a 1920×1080 demo → out/mate-in-3/mate-in-3-horizontal-demo.mp4 (+ -share.mp4, 1280×720)
make video F=horizontal          # the whole film in 16:9
make youtube F=horizontal        # .srt subtitles and chapters by scene for the video description
make stills F=horizontal         # stills to check the composition
```

A format preview: `http://127.0.0.1:8720/stage/?story=mate-in-3&tl=horizontal` (after `make timeline F=horizontal`).

## Film languages

Narrations by language — `story.json → film.voicings` (`narrator-en`, `narrator-ru`, the same Charon voice). There is
one storyboard (cues by the sentences of the English translation); a film in another language — `L=ru`: the voice and
subtitles are Russian, cues and pauses are moved by share of the paragraph text (pauses — to the nearest gap between
Russian sentences).

```bash
make voice L=ru                                  # narrate the missing paragraphs in Russian (≈ $0.25)
# a long paragraph the TTS stumbles on (empty audio, finish reason OTHER) — shorter pieces: overrides/ru.json → {"story-040": {"max_chars": 220}}
make timeline S=mate-in-3-tarkovsky L=ru         # build/timeline-ru.json (F=horizontal L=ru → timeline-horizontal-ru.json)
make preview S=mate-in-3-tarkovsky L=ru
```

## Storyboard

`storyboard.json` — scenes and shots. A shot starts at a cue `"at": "018.13"` (paragraph 18, sentence 13; `"+0.5"` —
from the middle of the sentence) — so shots are tied to the text, not to seconds, and survive re-narration. The scene
state carries over from shot to shot: a shot names only the changes.

```json
{"id": "s05g", "at": "018.17", "cam": "win-street", "push": 3, "focus": {"on": [0, 15, -27], "f": 1.6},
 "cast": {"woman-baby": {"card": "woman-baby/walking", "pos": [-24, 8, -27],
                         "move": {"to": [24, 8, -27], "ease": "linear"}, "fx": {"bob": 0.25}}},
 "sfx": [{"name": "rustle", "at": 0.1}], "note": "the red calico kerchief"}
```

- **elements** (`cast`): `card` — an asset (`character/pose`, `set/piece`, `prop/…`), `pos` [x, y, z] in cm (y — up from
  the stage floor, z — towards the camera, a card stands on its bottom edge), `rot`, `move` {to, rot_to, start, end,
  ease} or a route `move.keys` [[share of the shot, [x, y, z]], …] (came out from behind the portière, stood, left),
  `fx` — puppeteer effects: `walk` (a step: the card rocks without hopping), `bob` (hopping — running), `jitter` (a
  trembling hand), `sway`, `breathe`, `wobble`, `twinkle` (stars), `flicker`; `glow` — a glow; `parts` — joint angles
  (`[[share of the shot, degrees], …]`); `shadow_only` — only the shadow; `null` — remove; `{"reset": true}` — a set
  piece back in its place;
- **camera**: `cam` (a named point from `cams`), `push` (a push-in, cm), `drift`, `hand` (the strength of the handheld
  camera, 0 — a tripod);
- **focus**: `on` → `to` (an element or a point) at shares `at`, `f` — the "aperture" (larger — shallower depth of
  field), `f_to`;
- **light**: the set's preset or `preset`, `k`/`k_to`/`ramp`, `angle_to`, `target_to`, `warm`, `fx` — `swing` (the lamp
  was knocked), `heartbeat`, `breath`; the transition `in`: `cut` / `dip` (the light goes out and comes back — a change
  of place) / `fade`;
- **sound**: `sound.beds` (ambience by set), `sound.music` (from shot to shot: `drone`, `musicbox` with notes
  `"D4+A4:1 D5:1 …"`), `sfx` in a shot (`click`, `hum`, `breath`, `thump`, `rustle`, `heartbeat`).

The full vocabulary of styles, directors, light, geometry and sound — [docs/new-style.md](docs/new-style.md).

## Assets

`assets.py`: the prompt = the style (`styles/paper-theatre.json`: gouache and pencil on cardboard, a white scissors
rim) + the character's canon from the bible + the pose. First the **character sheet** (a turnaround of 4 views) — it
goes as a reference into every pose: the face and costume stay recognizable. Cut-outs are drawn on a #00FF00 chroma
key, keyed by "greenness" with a soft edge and spill suppression, cropped to the silhouette. Seedream 5.0 Flash
via OpenRouter, $0.018 per picture; the finale (26 pictures) — $0.45. Cut-outs are stored as lossless WebP (the same
pixels as PNG, ≈ 45 % of the size). The sources before keying — `assets/raw/`, previous variants — `assets/takes/`
(both local only). Narration — Gemini TTS (≈ $0.01 per minute).

## Stage and render

`stage/` — a static page (three.js 0.160 lives in `stage/vendor`, no CDN): cards on curved textured paper with
shadows by alpha, the lamp's light (a spot) + a lampshade in the frame + fill, depth of field (our own: depth aware of
the cut-outs' alpha, bokeh on a golden spiral), vignette, grain, subtitles. Any frame is computed from time t —
`tools/capture.mjs` captures frames with Playwright and pipes them into ffmpeg (H.264 + AAC). The GPU is chosen
automatically (Apple M2 — ≈ 0.07 s/frame at 1080×1920); without one — the software SwiftShader, ≈ 1 s/frame at
720×1280. The codec on macOS is the hardware `h264_videotoolbox` (the CPU is almost idle); `COOL=1` — a
no-overheating mode (low ffmpeg priority, 2 threads, pauses between frames).

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
docs/      pipeline, new styles, the site, directing notes, story analyses (docs/stories/, in Russian)
```

`make test` — tests without network; `make check` — tests + JS syntax.

Open work and implementation notes — [TODO.md](TODO.md) ([по-русски](TODO.ru.md)).

## License

Code — [MIT](LICENSE). Everything generated for the project — pictures, narration, translations, bibles,
storyboards, website texts — is dedicated to the public domain: [CC0 1.0](LICENSE-content). Alexander Grin's
stories are in the public domain. Third-party: three.js — MIT (`stage/vendor/three/LICENSE`), the fonts Source
Serif 4 and Golos Text — OFL (`site/fonts/`, `stage/fonts/`).

Made together with [Claude Code](https://claude.com/claude-code).
