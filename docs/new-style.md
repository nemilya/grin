# A new video style: how to add one

**English** · [Русский](new-style.ru.md)

A video version of a story = a **production**: the same text and voice, its own pictures, storyboard and sound. Its
"style" is made of three independent parts that can be combined:

| part | file | responsible for |
|---|---|---|
| visual style | `styles/<style>.json` | how pictures are drawn (prompts), the key, the scene's material and colour |
| director (optional) | `directors/<name>.json` | the film language: shot lengths, camera, shot defaults, rules for the storyboard |
| production | `stories/<story>-<style>/` | bible, storyboard (+16:9), sound, assets — a concrete film |

Ready examples: `paper-theatre` (paper theatre, no director — `stories/mate-in-3`) and `tarkovsky-film` +
`directors/tarkovsky.json` (`stories/mate-in-3-tarkovsky`). More on the second one — [director-style.md](director-style.md).

## 0. A test (≈ $0.15, half an hour)

Before making a production, compare the style on one scene: `tools/style_lab.py` — one scene (the doctor at the window,
rain, a table with a lamp) in several renderings on the same engine (camera, light, palette are shared). Add a prompt
variant to the script → `python3 tools/style_lab.py` → `make preview` with `?story=_lab-tarkovsky&tl=<variant>`
or films `node tools/capture.mjs video _lab-tarkovsky --tl <variant>`.

## 1. The visual style — `styles/<style>.json`

The engine's prompts are built from a **style-free description** (the bible) + **the technique from the style**. Fields:

| field | what | example (cinema) |
|---|---|---|
| `name` | the name (ru, en) | "Film image (Tarkovsky)" |
| `cutout` | the technique of a figure/object on chroma key | "Rendered photographically, like a figure from a 1970s Soviet art-house film…" |
| `cutout_bg` | the background for the key | "Isolated on a perfectly flat, uniform pure chroma-green (#00FF00)…" |
| `backdrop` | the backdrop technique (no people) | "A wide background plate for a multi-plane film composite…" |
| `texture` | a floor, a tabletop — seen from above | "A seamless flat texture seen straight from above…" |
| `silhouette` | silhouettes (shadows, a procession in fog) | — |
| `figure` | the start of a pose prompt: "… <name> (<age>): <appearance>" | "A single isolated figure (nothing else in the image, only this one person) of" |
| `piece`, `object`, `part` | a set piece, a prop, a puppet part | by default — from `cutout` with "puppet" → "piece of toy-theatre scenery" |
| `sheet`, `sheet_each`, `sheet_bg` | the character sheet (4 views — the reference for every pose) | "for a film (costume and casting reference photographs)" |
| `no_text` | no lettering | — |
| `key` | `soft` — a feathered edge, the neighbours' colour under the transparent part (cinema); absent — an edge with a white rim (paper) | `soft` |
| `layers` | what to add to cut-outs in the scene: `soft` (a soft edge), `cast: false` (no shadows) | `{"soft": true, "cast": false}` |
| `stage` | material and film: `curl` (cardboard bend), `paper_normal`, `paper_roughness`, `grain`, `vignette`, `saturation`, `tint`, `flicker`, `fog` | no bend or texture, grain 0.075, fog |
| `stage` (silent film) | `autochrome` (coloured starch grain and the softness of the plate, 0–1), `scratches`, `dust` (scratches and dust, 0–1), `weave` (the frame "weaves", pixels), `fps_look` (the scene moves at 18 fps), `hand` (the strength of the camera's "hands") | `silent-autochrome` |

Rules learned in practice:
- **A detail without a person** (a hand, hands, an object in close-up): a pose with `"closeup": true` (and `"ref": false`) —
  the prompt of a detail without a figure or appearance, otherwise the model draws the whole person.
- For a "photo" style, pose descriptions must not say "cut-out".
- **A prop in a different manner** (a natural leaf in a painted film): the prop's `"technique"` replaces the style's
  `object`; a green prop — `"key": "magenta"` (a magenta background, keyed on it).
- **Jointed parts** (an arm in three pieces) work for a puppet but not for a photograph — there movement is better
  solved by editing (a close-up of a hand in the dark).
- Edits to the engine's prompts must not change other styles' prompts (otherwise their assets go stale): compare
  `assets.plan('<story>')` before and after.

## 2. A director (if you need your own film language) — `directors/<name>.json`

```json
{"name": {"ru": "…", "en": "…"},
 "defaults": {"hand": 0, "ease": "inOut"},
 "min_shot": 12,
 "language": {"editing": "…", "camera": "…", "people": "…", "light_color": "…", "elements": "…", "time": "…", "sound": "…"}}
```

- `defaults` — shot fields by default (a shot overrides them): `hand` (a handheld camera, 0 — a tripod), `ease`…;
- `min_shot` — a shorter shot gets a warning in `make timeline`;
- `language` — a description for whoever writes the storyboard (an agent, an LLM): editing, camera, people, light,
  elements, pauses, sound.

Without a director — the engine defaults (paper theatre: the puppeteer's handheld camera).

## 3. The production — `stories/<story>-<style>/`

1. **`story.json`**:
   ```json
   {"base": "mate-in-3", "film": {"style": "<style>", "width": 1080, "height": 1920, "fps": 24},
    "formats": {"horizontal": {"width": 1920, "height": 1080, "fps": 24, "storyboard": "storyboard-16x9.json"}},
    "art_context": "…the era and the world in this style…"}
   ```
   Text, translation, narrations (`film.voicings`) — from `base`.
2. **`bible.json`** — characters: the canon from the base bible (the same faces and costumes — `look` is copied, the pose
   wordings are translated into the style's language), poses — whichever the storyboard needs; sets — **in layers by
   depth** (a backdrop `draw: screen` — the glowing distance behind the window, a wall with an opening `hole: true`, a floor
   `kind: floor`, furniture); someone else's card without generation — `"card": "office/floor"`.
3. **`storyboard.json`** — `"director": "<name>"`, `"lang": "en"`, light (presets with `fog` and `grade`; `grade_to` +
   `grade_at: [a, b]` — a colour transition over the shot: `saturation`, `tint`, `autochrome`), the iris (`"in": "iris"`,
   `end.iris_out`, `iris.center`), intertitles (the procedural card `draw: title`: `story_title`, `para` + `attr`, `big`;
   `no_subtitles` — paragraphs without subtitles), procedural geometry (`stage/js/geometry.js`): shapes `draw: shape`
   (disc, ring, rect, wedge, cross; `soft`, `add`), lines `draw: trace` (`points`, `dash`, `wave`; in a shot
   `grow: [a, b]` — it draws itself), an element's `spin` (+ `trail` — a trail: a sphere) and `fall` (a card falling like a
   pendulum; in the next shot it lies at `to`), cameras, scenes and shots, `holds`, `sound` (ambience: `rain`, `drips`,
   `wind`, `wind-night`, `clock`, `crickets`, `room`; music: `organ`, `drone`, `musicbox`, `piano` — a silent-film pianist,
   `loop` — the phrase repeats, `motor` — an aeroplane: `env`/`pitch` keys by shot `["j04+0.5", -2]`; ambience
   `projector`, `crowd`, `birds`, `tram`, a mix `"birds+crowd*0.5"`, `bed` in a shot — the shot's own ambience; effects
   `bell`, `boom`, `tram-bell`; `bed_gain`, `bed_duck`), `fade_out`, `demo_start`.
4. **Assets:** `python3 -m engine assets <production> --keys refs/<character>,<character>/<pose>,<set>/<piece>` —
   2–3 test ones → look → `python3 -m engine assets <production>` — the rest (≈ $1.2).
5. **Shots:** `make timeline S=<production>` → `node tools/capture.mjs stills <production> --scale 0.25 --at 0.5` → the sheet;
   layer edges must not get into the frame (especially at the start/end of camera moves: `--at 0.02` and `--at 0.98`).
6. **16:9:** `storyboard-16x9.json` (`extends`, `cams` for the wide frame, shot edits) →
   `make timeline S=<production> F=horizontal` → the sheet.
7. **Other languages:** `make timeline S=<production> L=ru` — the cues move by themselves; look at 2–3 shots.
8. **Sound:** `make preview S=<production>` — listen to the ambience, music, pauses, the finale.
9. **A test:** in `tests/test_engine.py` — builds without errors, the horizontal format with the same cues (like `ProductionTest`).

## 4. To the site

In `site.json` → `stories[].videos` add:
```json
{"production": "<production>", "name": {"en": "…", "ru": "…"}, "about": {"en": "…", "ru": "…"}, "poster": ["<shot>", 0.5]}
```
`make site` builds the video in all the production's formats and in the languages with a full narration (otherwise in
the storyboard's language), the posters, the sound; the video's address is `/<lang>/<story>/<style>/`. Then
`make serve` → `make deploy`.

## Cost and time

A test ≈ $0.15; a production: bible + storyboard (an agent or an LLM) + ≈ 60–75 pictures (≈ $1.2), redos ≈ $0.1;
sound and rendering are local. A site build with a new production: sound ≈ 1.5 min per language, posters, webp layers.
