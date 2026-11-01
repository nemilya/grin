# Rendering a film (YouTube, Shorts, social media)

**English** · [Русский](video.ru.md)

Films are rendered on your own machine: a browser (Playwright Chromium) draws every frame from time, ffmpeg encodes.
A cloud session has no GPU — rendering there is software-only and takes hours.

## Formats of each production

| production | main format | second format |
|---|---|---|
| `mate-in-3` (paper theatre) | vertical 1080×1920 | `F=horizontal` → 1920×1080 |
| `mate-in-3-tarkovsky` | vertical 1080×1920 | `F=horizontal` → 1920×1080 |
| `sila-nepost` (silent film) | horizontal 1920×1080 | — |
| `leaf-story` (avant-garde) | horizontal 1920×1080 | `F=vertical` → 1080×1920 |

YouTube — horizontal; Shorts / Reels / TikTok — vertical. The language: `L=ru` — Russian voice and subtitles,
without it — English (`story.json → film.voicings`).

## Recipe: one film for YouTube

```bash
make media-pull                                       # pictures and narration (without them — placeholders)
make video-demo S=mate-in-3 F=horizontal START=s12a   # a try-out: from shot s12a to the end, a couple of minutes
make video S=mate-in-3 F=horizontal                   # the whole film; timeline and sound are built by itself
make youtube S=mate-in-3 F=horizontal                 # .srt subtitles and chapters for the description
make thumbnail S=mate-in-3 F=horizontal SHOT=s01a     # a thumbnail: the shot + the title
```

Results in `out/<story>/`:

| file | what | where to |
|---|---|---|
| `<story>-<F>[-<L>][-subs].mp4` | master, without subtitles (`-subs` — `SUBS=1`, burnt in): 1080p, H.264 High, ≈ 16 Mbit/s on a Mac (videotoolbox; elsewhere x264 CRF 17), AAC 160k | **YouTube** |
| `<story>-<F>[-<L>]-share.mp4` | 720p, ≈ 3.5 Mbit/s, AAC 128k, faststart — made right after the master, gently: hardware decoding/encoding on a Mac, low priority, 2 threads (`--no-share` — skip) | Telegram, Reels, TikTok |
| `<story>-<F>[-<L>].srt` | subtitles (`make youtube`) | YouTube Studio → Subtitles |
| `<story>-<F>[-<L>]-thumb-<shot>.jpg` | a thumbnail (`make thumbnail`, below) | YouTube Studio → Thumbnail |
| `<story>-<F>[-<L>]-chapters.txt` | chapters by scene, `0:00 …` (`make youtube`) | the video description as is |

E.g. `make video S=mate-in-3 F=horizontal L=ru` → `out/mate-in-3/mate-in-3-horizontal-ru.mp4`.
`make youtube` needs a full narration (`timing: voicing` in the timeline line), otherwise chapters and subtitles
drift from the film — it warns.

## Subtitles: a separate file by default

A film is rendered **without burnt-in subtitles**: for YouTube upload the `.srt` of `make youtube` (viewers turn them
off, YouTube indexes them, several languages). In YouTube Studio: upload the `.mp4`, then Subtitles → add a language →
upload file → `.srt` (English; and Russian — `make youtube … L=ru`, for the same English film).

Where there is no separate subtitle track — Shorts, Reels, Telegram — burn them in with `SUBS=1`:

```bash
make video S=mate-in-3 SUBS=1     # → out/mate-in-3/mate-in-3-subs.mp4 (+ -subs-share.mp4)
```

This is only about the rendered film: the site's player keeps its subtitles (the CC button), and stills show them
(`--no-subs` — without). Intertitles of the silent film (`sila-nepost`) are part of the picture — they stay.
Don't use `"subtitles": {"burn": false}` in `story.json`: it removes subtitles from the site's player too.

## Thumbnail

```bash
make thumbnail S=mate-in-3 F=horizontal SHOT=s01a SUB="a paper theatre film"   # the one on YouTube
# → out/mate-in-3/mate-in-3-horizontal-thumb-s01a.jpg (1280×720) + -raw.jpg (the same frame without text)
```

One shot of the storyboard without subtitles, 1280 px on the long side, with the title, author and year from
`story.json` and a line under them (by default — the video's name in `site.json`), in the site's fonts.

| option | default | |
|---|---|---|
| `SHOT=` | the production's poster in `site.json` | which shot (ids — the stills sheet: `make stills F=…`) |
| `AT=` | poster's fraction, else 0.5 | the moment within the shot, 0…1 |
| `POS=` | `top` | text: `top` (centred, over the dark top), `left`, `right` — on the side with dark space |
| `TITLE=` / `SUB=` | from `story.json` / `site.json` | override the title / the line under it |
| `L=ru` | English | Russian title and author (and the Russian timeline: `make timeline F=… L=ru` first) |

What works on YouTube: one clear subject that reads at phone size (a face, a lit figure on a dark stage), the text
on the darker side of the frame. Upload: YouTube Studio → the video → Thumbnail → Upload file (≤ 2 MB). Test &
Compare in Studio can A/B-test two or three thumbnails.

## Time and hardware

| | speed | an 18.7-min film (≈ 27,000 frames at 24 fps) |
|---|---|---|
| Mac, Apple M2 (GPU, `h264_videotoolbox`) | ≈ 0.04 s/frame at 1920×1080 (measured) | ≈ 20 min |
| no GPU (SwiftShader) | ≈ 1 s/frame at 720×1280 | hours |

The first lines of a render say what it runs on: `WebGL: … Apple M2 … — GPU` or `SwiftShader` (software),
and `codec: h264_videotoolbox` (hardware encoder). Options (`local.mk` or the command line):

- `COOL=1` (`CAPTURE_COOL = 1`) — no overheating: low-priority ffmpeg, 2 threads, pauses between frames;
- `CAPTURE_GL = gpu | cpu`, `CAPTURE_ENCODER = videotoolbox | x264` — force the choice;
- `SCALE=0.5` — half resolution (a quick check of the whole film).

Don't let the laptop sleep during a render — capture stops.

## All films at once

```bash
# horizontal, English, subtitles as .srt — for YouTube
make video S=mate-in-3 F=horizontal           && make youtube S=mate-in-3 F=horizontal
make video S=mate-in-3-tarkovsky F=horizontal && make youtube S=mate-in-3-tarkovsky F=horizontal
make video S=sila-nepost                      && make youtube S=sila-nepost
make video S=leaf-story                       && make youtube S=leaf-story

# vertical, subtitles burnt in — for Shorts / Reels
make video S=mate-in-3 SUBS=1
make video S=mate-in-3-tarkovsky SUBS=1
make video S=leaf-story F=vertical SUBS=1
```

Add `L=ru` to any of them for the Russian version. A share version of an existing file: `make share FILE=out/…/x.mp4`.
