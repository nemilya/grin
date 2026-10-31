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
# for YouTube — without burnt-in subtitles: make video … SUBS=0 (see Subtitles below)
```

Results in `out/<story>/`:

| file | what | where to |
|---|---|---|
| `<story>-<F>[-<L>][-nosubs].mp4` | master (`-nosubs` — `SUBS=0`, no burnt-in subtitles): 1080p, H.264 High, ≈ 16 Mbit/s on a Mac (videotoolbox; elsewhere x264 CRF 17), AAC 160k | **YouTube** |
| `<story>-<F>[-<L>]-share.mp4` | 720p, ≈ 3.5 Mbit/s, AAC 128k, faststart — made right after the master (`--no-share` — skip) | Telegram, Reels, TikTok |
| `<story>-<F>[-<L>].srt` | subtitles (`make youtube`) | YouTube Studio → Subtitles |
| `<story>-<F>[-<L>]-chapters.txt` | chapters by scene, `0:00 …` (`make youtube`) | the video description as is |

E.g. `make video S=mate-in-3 F=horizontal L=ru` → `out/mate-in-3/mate-in-3-horizontal-ru.mp4`.
`make youtube` needs a full narration (`время: voicing` in the timeline line), otherwise chapters and subtitles
drift from the film — it warns.

## Subtitles: burnt in or a separate file

By default subtitles are **burnt into the picture** — right for Shorts, Reels, Telegram, where there is no separate
subtitle track. For YouTube render without them and upload the `.srt` (viewers turn them off, YouTube indexes them,
several languages):

```bash
make video S=mate-in-3 F=horizontal SUBS=0     # → out/mate-in-3/mate-in-3-horizontal-nosubs.mp4 (+ -share)
make youtube S=mate-in-3 F=horizontal          # → mate-in-3-horizontal.srt and -chapters.txt
make youtube S=mate-in-3 F=horizontal L=ru     # → a Russian .srt for the same English film
```

In YouTube Studio: upload `…-nosubs.mp4`, then Subtitles → add a language → upload file → `.srt` (English; and Russian
from the `L=ru` run). `SUBS=0` changes only this render; the site keeps its subtitles (the CC button). Intertitles of the
silent film (`sila-nepost`) are part of the picture, not subtitles — they stay.

Don't use `"subtitles": {"burn": false}` in `story.json` for this: it removes subtitles from the site's player too.

## Time and hardware

| | speed | an 18.7-min film (≈ 27,000 frames at 24 fps) |
|---|---|---|
| Mac, Apple M2 (GPU, `h264_videotoolbox`) | ≈ 0.04 s/frame at 1920×1080 (measured) | ≈ 20 min |
| no GPU (SwiftShader) | ≈ 1 s/frame at 720×1280 | hours |

The first lines of a render say what it runs on: `WebGL: … Apple M2 … — видеокарта` (GPU) or `SwiftShader` (software),
and `кодек: h264_videotoolbox` (hardware encoder). Options (`local.mk` or the command line):

- `COOL=1` (`CAPTURE_COOL = 1`) — no overheating: low-priority ffmpeg, 2 threads, pauses between frames;
- `CAPTURE_GL = gpu | cpu`, `CAPTURE_ENCODER = videotoolbox | x264` — force the choice;
- `SCALE=0.5` — half resolution (a quick check of the whole film).

Don't let the laptop sleep during a render — capture stops.

## All films at once

```bash
# horizontal, English, subtitles as .srt — for YouTube
make video S=mate-in-3 F=horizontal SUBS=0           && make youtube S=mate-in-3 F=horizontal
make video S=mate-in-3-tarkovsky F=horizontal SUBS=0 && make youtube S=mate-in-3-tarkovsky F=horizontal
make video S=sila-nepost SUBS=0                      && make youtube S=sila-nepost
make video S=leaf-story SUBS=0                       && make youtube S=leaf-story

# vertical, subtitles burnt in — for Shorts / Reels
make video S=mate-in-3
make video S=mate-in-3-tarkovsky
make video S=leaf-story F=vertical
```

Add `L=ru` to any of them for the Russian version. A share version of an existing file: `make share FILE=out/…/x.mp4`.
