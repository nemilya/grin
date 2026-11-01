# Pipeline: story → narration → video → site

**English** · [Русский](pipeline.ru.md)

The process described as a contract of stages: what goes in, what comes out, how it is run, how it is checked,
who makes the decision. The future automatic pipeline (`make film S=…`, see "Automation") is built from it.
The example throughout is *Mate in Three Moves* (`stories/mate-in-3`) and the Tarkovsky production
(`stories/mate-in-3-tarkovsky`).

## Concepts

| | what it is | where |
|---|---|---|
| **story** | text, translation, narrations by language | `stories/<story>/` (`story.json`, `prepared/`, `translations/`, `voicings/`) |
| **production** | a video of a story in one style: bible, storyboard, assets | its own story with `"base": "<story>"`, or the story itself (the first production) |
| **style** | how pictures are drawn + scene parameters | `styles/<style>.json` |
| **director** | the film language: shot lengths, camera, shot defaults | `directors/<name>.json` (optional) |
| **format** | vertical 9:16 (`film`), horizontal 16:9 (`formats.horizontal` + `storyboard-16x9.json`) | the production's `story.json` |
| **film language** | voice and subtitles; there is one storyboard (in the translation's language) | `film.voicings`, `make … L=ru` |

Links: paragraph ids (`story-018`) are shared by all languages; storyboard cues (`018.13+0.4`) refer to sentences of
the storyboard's language — for another language the engine moves them by share of the paragraph text, and pauses
to the nearest gap between sentences. So one storyboard gives films in every language.

## Stages

Statuses and fingerprints: everything generated has a fingerprint of its inputs (text, settings, references);
when something upstream changes, what is downstream becomes "stale", the rest is left alone. The summary — `make status`.

### 1. Text — `make prepare`
- **in:** `content/<story>.txt`, `story.json → source` (`skip` — how many leading blocks are not narrated: the author and title);
- **out:** `prepared/<lang>.json` — paragraphs → sentences → words (offsets in the text);
- **check:** the paragraph count; changing the sentence splitting shifts the storyboard cues — afterwards compare
  the sentence counts per paragraph;
- **who:** a script.

### 2. Glossary and translation — `make translate`
- **in:** `prepared/ru.json`, the bible (names);
- **out:** `glossary.json`, `translations/en.json` (by paragraph, the same ids), `prepared/en.json`;
- **cost:** ≈ $0.2 for a story of this size (Opus via OpenRouter);
- **who:** an LLM; a human reads and edits the translation (JSON).

### 3. Narration — `make voice` (`L=ru` — another language)
- **in:** `prepared/<lang>.json`, `voicings/<id>/voicing.json` (voice, model, the overall manner), `overrides/<lang>.json`
  (the manner per paragraph: "whispering", "a shout");
- **out:** `voicings/<id>/items/<paragraph>.json` (takes, the transcription score, word timings), `takes/*.opus`;
- **check:** every take is transcribed back and compared with the text (score ≥ 0.9, the end of the phrase in place),
  otherwise a new take; a provider failure (429, empty audio) — the paragraph is skipped, a rerun picks it up;
- **cost:** ≈ $0.015 per minute (TTS + transcription), a 15–19 min story ≈ $0.25;
- **who:** a script; a human listens (admin → "Narration").

### 4. The production's bible — `bible.json`
- **in:** the text, the production's style;
- **out:** the world, characters (the canon of their appearance + poses), sets (layers by depth: a backdrop, a wall with
  an opening, a floor, furniture; positions in cm), props. Descriptions are in English and **style-free**;
- **check:** `assets.plan` builds; the poses cover the storyboard (otherwise `make timeline` says "no asset");
- **who:** for now an agent (Claude Code) with the `storyboard` skill; later an LLM by schema (see "Automation").

### 5. Storyboard — `storyboard.json` (+ `storyboard-16x9.json`)
- **in:** the text with sentence ids, the bible, the director;
- **out:** scenes → shots: the starting cue (`at`), camera (`cam`, `cam_to`, `push`, `drift`, `hand`), focus, light
  (presets, fog, colour), elements and their movement (`cast`), pauses (`holds`), sound (`sound`, `sfx`);
- **check:** `make timeline` — cue, camera and asset errors fail the command; the director's warnings (short
  shots); stills `node tools/capture.mjs stills <production> --scale 0.3` and the sheet `out/<production>/stills/contact.jpg`
  (`--debug` — flat light, shows the composition); the same for `F=horizontal`;
- **who:** an agent or an LLM + a validator; a human looks at the sheet of shots.

### 6. Assets — `make assets-used` (or `python3 -m engine assets <production>`)
- **in:** the bible, the style, the character sheets;
- **out:** `assets/` — first the character sheets (a turnaround of 4 views — the reference for every pose), then poses,
  sets, props; chroma key → lossless WebP with transparency (the style's `key: soft` — the soft "cinema" edge);
  `assets.json` — fingerprints, seed, cost;
- **check:** before mass generation — 1–2 test pictures; then the sheet of shots; a failed one —
  `--redo <key>` (a new seed), clean-up — `erase` in the bible + `--rekey`; accept as is — `--accept`;
- **cost:** $0.018 per picture; a production ≈ 60–75 pictures ≈ $1.1–1.4;
- **who:** a script; a human selects.

### 7. Timeline — `make timeline` (`F=horizontal`, `L=ru`)
- **in:** the storyboard, speech timing (the narration; without it — an estimate from the pace), the bible, the assets;
- **out:** `build/timeline[-format][-lang].json` — every shot has the full list of elements, camera, focus, light;
  subtitles by word; pauses cut the takes between sentences;
- **who:** a script.

### 8. Sound — `make sound`
- **in:** the timeline, `storyboard.json → sound` (ambience by set, music from shot to shot, effects in shots);
- **out:** `build/sound[-…].wav` — voice + ambience (rain, wind, a clock, crickets…) + music (a music box, a drone, an organ),
  the ambience ducks under the voice (`bed_duck`), a fade at the end (`fade_out`), loudness −16 LUFS;
- **who:** a script (synthesis without samples); a human listens.

### 9. Preview and render
- `make preview` — the player without rendering (shots + sound), `&shot=…`, `&debug`;
- `make video` / `make video-demo` — mp4 (on the GPU if there is one) + a social media version; `make youtube F=horizontal` —
  `.srt` and chapters ([video.md](video.md)).

### 10. Site — `make site` → `dist/` ([site.md](site.md))
- **in:** `site.json` (stories, narrations by language, video versions = productions), everything above;
- **out:** EN/RU pages, reading with highlighting and MP3, video in the browser (timelines, webp layers, m4a sound, posters);
- **check:** `make serve`; only what changed is rebuilt (sound takes the longest);
- **then:** `make deploy` ([deploy/README.md](../deploy/README.md)).

## Who decides what

| decision | now | in the automatic pipeline |
|---|---|---|
| the story, voice, style, director | a human | a human (config) |
| translation | an LLM, a human reads | an LLM, a human approves |
| bible, storyboard | an agent with the `paper-film`, `storyboard` skills | an LLM by schema + a validator; a human approves |
| selecting pictures | the agent and a human, by the sheets | automatic checks + a human |
| camera and light from the stills | the agent looks at the sheets and edits | a vision model → JSON edits → rebuild (optional) |
| sound, music | the agent in the storyboard, a human listens | an LLM draft per scene, or your own music as a file |

## Automation (plan)

Everything the agent did is API calls and creative decisions that can be expressed as a prompt with checks. Scripts:

1. **`engine/bible.py`** — text analysis (an LLM, by the `bible.json` schema): the world, characters with a canon,
   poses from the scenes, sets in layers with positions on a typical set grid (backdrop z −80…−100, a wall with an
   opening z −30, the floor, objects on the table).
2. **`engine/board.py`** — a storyboard draft scene by scene (1–3 paragraphs per request, with the previous scenes as
   context): the LLM gets the text with sentence ids, the bible, the director's profile (`directors/*.json → language`),
   the vocabulary of cameras and effects, and a finished storyboard as an example → JSON; a **validator**
   (`timeline.build`: cue, camera, asset errors; shot lengths per the director) feeds the errors back to the LLM until clean.
3. **`engine/review.py`** — model-free shot checks (brightness, the share of empty frame, a character at the edge, a visible
   edge of a set layer) and an optional vision-model pass over the sheet of stills.
4. **`make film S=<production>`** — in a row: prepare → translate → voice (all languages) → bible → board → assets
   (2 test ones → stop for approval → all) → timeline (all formats and languages) → sound → stills (stop) → site.
5. The admin — approving the bible and the storyboard, selecting pictures (for now view only: `make admin`).

The cost of a full run for a story of this size: translation ≈ $0.2, narration ≈ $0.25 per language, bible and
storyboard ≈ $0.3–0.5 (LLM), assets ≈ $1.2 per production — **about $2–3 for a story with one production**.
