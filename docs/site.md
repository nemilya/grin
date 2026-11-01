# The site grin.nemilya.me

**English** · [Русский](site.ru.md)

A static site about Alexander Grin: stories read aloud and on screen. English is the default (`/en/`), Russian is
`/ru/`. It is built from the repository with one command and uploaded as is ([deploy/README.md](../deploy/README.md)).

```bash
make site      # → dist/ (a rebuild redoes only what changed; the first build takes a while: video sound ≈ 1.5 min per production and language)
make serve     # → http://127.0.0.1:8730/
make deploy    # → the server (DEPLOY in local.mk)
```

## What is on the site

| page | address | what |
|---|---|---|
| showcase | `/<lang>/` | story after story: the year and the title (no retelling), "Read and listen", MP3 — and right away all the video versions as large posters (16:9 on a wide screen; on a phone one column, a vertical frame in 4:5) |
| about the author | `/<lang>/author/` | name, years, biography (`site/author.json`); linked from the showcase header |
| story | `/<lang>/<story>/` | the year, the title, "Read and listen", "Download audio" (MP3), video versions (poster, a line about the style, duration, vertical/horizontal) |
| reading | `/<lang>/<story>/read/` | the text in pages by screen height, highlighting of the sentence and word being heard, a click on a word — listen from it, speed, a link to the place (`#t=…`), continue where you stopped |
| video | `/<lang>/<story>/<style>/` | the scene is drawn in the browser (WebGL, stage.js) by the timeline, time comes from the sound; no mp4 |

Video:
- **format by screen:** a phone, a portrait or narrow screen — vertical 9:16, a wide one — horizontal 16:9; the ⇄ button
  switches (the position is kept), `?o=vertical|horizontal` — explicitly;
- **language:** the page's language if the production has a full narration in it (`film.voicings`), otherwise the
  storyboard's language (the story page says "Video in: …");
- **quality by device:** the scene resolution follows the screen size and pixel density (no more than 540×960 on a
  phone), fewer focus rays on a phone;
- subtitles (CC) can be turned on and off, fullscreen, keys: space, ← →, C, F; the viewing position is remembered;
- before the first frame — a poster (a storyboard shot without subtitles) and a ▶ button: the sound starts on a tap (browsers require it).

The ☀/☾ theme follows the system, the choice is remembered; the video page is always dark.

## Where things come from — `site.json`

```json
{"url": "https://grin.nemilya.me", "langs": ["en", "ru"], "default_lang": "en", "author": "site/author.json",
 "stories": [{"story": "mate-in-3", "voicings": {"en": "narrator-en", "ru": "narrator-ru"},
              "videos": [{"production": "mate-in-3-tarkovsky", "name": {…}, "about": {…}, "poster": ["t05b", 0.1]},
                         {"production": "mate-in-3", "name": {…}, "about": {…}, "poster": ["s03a", 0.5]}]}]}
```

A new story: a story in `stories/` (text → translation → narration, [pipeline.md](pipeline.md)) + an entry in `stories`.
A new video version: a production ([new-style.md](new-style.md)) + an entry in `videos`.

## The layout of `dist/`

```
index.html                         → en/
en/ ru/                            pages (see above)
<lang>/<story>/audio/story.mp3     the whole narration (+ story.json — timing marks for reading)
media/<production>/                assets/*.webp (layers: WebP with transparency, ≤ 1400 px),
                                   <orientation>-<lang>.json (timeline), sound-<lang>.m4a (AAC 96k, mono),
                                   poster-<orientation>.webp
assets/                            site.css, site.js, reader.js, watch.js, fonts/ (Source Serif 4, Golos — OFL)
assets/stage-<hash>/               the stage: js/ (stage.js, paper.js, post.js, geometry.js) and vendor/three
```

Code: `engine/site.py` (the build), `site/` (styles, scripts, fonts, `author.json`). The build remembers fingerprints
(`dist/.build.json`): a layer is re-encoded only if its picture changed; the video sound — if the speech, the shots,
the storyboard's sound or the synthesis code it sounds with changed (`sound.signature`: the mix + its ambience, music,
effects — a new ambience for one production doesn't recompute the others); a poster — if its shot or assets changed;
the narration MP3 — if the takes changed. Everything the build didn't confirm is deleted.

## Later

- narration and video for other stories (the same pipeline);
- choosing a voice/narration on the page if there are several;
- "continue watching" hints on the story page (video progress is already stored in localStorage).
