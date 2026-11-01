# A director's style: the same story — a different film language

**English** · [Русский](director-style.ru.md)

The idea: stage the same story "by the hand" of another director. The first one is Andrei Tarkovsky. Everything that
makes up a film language changes: editing and shot length, camera movement, light and colour, the elements in the frame,
pauses, sound, the accents of scenes — and the image. The voice stays (the same narration files); it can be replaced later.

The chosen look is the **"film image"** (two variants were tried — `stories/_lab-tarkovsky`, `tools/style_lab.py`):
the same 3D scene of layers by depth (camera, parallax, focus), but the layers are drawn as parts of a frame from
1970s Soviet auteur cinema on 35 mm film — photographic, no rim or paper, with a soft edge, fog and film colour
grading. The cardboard cut-outs stay with the paper theatre (`mate-in-3`).

## The layers of a film

```
story + translation + voice  stories/<story>/                  text, translation, voicings/<voice>/
production                   stories/<production>/story.json   "base": <story> — text and voice are taken from there;
                                                               its own: bible.json, storyboard.json, assets/, build/
director                     directors/<name>.json             the film language + shot defaults (storyboard → "director")
visual style                 styles/<name>.json                how the layers are drawn + scene parameters (film.style)
```

`stories/mate-in-3` — the paper theatre (no director: the handheld camera is the engine default);
`stories/mate-in-3-tarkovsky` — the Tarkovsky production. There is one engine: fog, rain, monochrome, pauses,
soft layers are available to every production. A separate repository only if the productions ever need to be
published separately (the engine as a git submodule).

```bash
make status S=mate-in-3-tarkovsky
make preview S=mate-in-3-tarkovsky     # the player: http://127.0.0.1:8720/stage/?story=mate-in-3-tarkovsky
make video-demo S=mate-in-3-tarkovsky  # the finale (from the storyboard's demo_start shot — t13a "The hand")
make video S=mate-in-3-tarkovsky       # the whole film, 20 min
make preview S=mate-in-3-tarkovsky F=horizontal   # 16:9 (&tl=horizontal)
make video S=mate-in-3-tarkovsky F=horizontal     # 1920×1080 for YouTube (+ -share.mp4, 1280×720)
make youtube S=mate-in-3-tarkovsky F=horizontal   # .srt subtitles and chapters by scene
```

Horizontal 16:9 — `formats.horizontal` + `storyboard-16x9.json` (it inherits the production's storyboard): the same
cues, pauses, light and sound; its own cameras — tighter vertically, so that the wide frame doesn't go past the edges of
the set layers (the office wall is 64 cm, the night sky is enlarged in 16:9), the procession in the fog starts off-frame.

## Tarkovsky — `directors/tarkovsky.json`

| | paper theatre | Tarkovsky |
|---|---|---|
| editing | 134 shots, ~8 s | 45 shots of 15–90 s; the transition is often made by the camera itself (`cam` → `cam_to`) |
| camera | handheld, the "breathing" of hands | a tripod (`hand: 0` — the director's default); a slow track (`drift`), a push-in (`push`) |
| figures | move, sway | almost still, in profile, by the window, deep in the frame; levitation — in the void and in the bedroom |
| light | the puppeteer's lamp | rainy dusk from the window, a lamp on the table; in the finale — electric light from above |
| colour | warm gouache | muted film stock; memories — sepia, the void — b/w, night — blue, thoughts — grey fog |
| elements | — | rain outside the window, poplar fluff in a beam, wind in the grass, fog, stars, a curtain, apples on a branch |
| time | cues one after another | `holds` pauses: after a paragraph ("018") or a sentence ("018.16") — silence, the shot lasts |
| sound | a music box, a clock | rain, drops, wind, a night garden; an organ (a chorale) at the start and the end, a drone in the void |

## What the engine has

- **A production** (`story.json → base`): `config.text_dir` — the base story's text, translation, voice;
  `config.story` — the base story's fields + its own (film — key by key).
- **A director** (`storyboard.json → director`): `defaults` — shot fields by default, `min_shot` —
  warnings in `make timeline` about shots that are too short.
- **Pauses** (`storyboard.json → holds`): the timeline shifts the cues, the sound cuts the take between sentences
  (`paragraphs[].cuts`) — the narration is not redone.
- **The camera**: `cam_to` — a move from one camera to another over a shot.
- **The style** (`styles/tarkovsky-film.json`): prompt wordings (`figure`, `piece`, `object`, `part`,
  `sheet…`), a soft key (`key: soft` — a feathered edge, the neighbours' colour under the transparent part), `layers`
  (a soft edge and no shadows for cut-outs), `stage` (no bend or paper texture, grain, flicker, saturation,
  tint, fog).
- **The scene**: fog and colour grading per light preset (`fog`, `grade: {saturation, tint}`); rain as threads
  (`draw: rain`, parameters in the bible); a set piece can take someone else's card (`card`) — no generation.
- **Sound**: ambience `rain`, `drips`, `wind`, `wind-night`; music `organ` (chords "D3+A3+F4:4 …").

## The production's assets

62 pictures ($1.30 spent, with redos): character sheets (the same canon of faces and costumes), 32 poses, set layers
(the office with a door and a window, a corridor, a garden in the rain outside the window, a room with a window onto a
dusty street, a night garden with a porch, a bedroom, a table), props. The paper puppet's jointed arm doesn't work in a
photograph (the model doesn't take the arm off the body, the hand comes out green) — "the hand that rises and falls" is
shot as a close-up in the dark (`patient/hand-raised`, a `closeup` pose — the prompt of a detail without a figure).
Redo a layer: `python3 -m engine assets mate-in-3-tarkovsky --redo <key>`.

## Next

- The production's own voice: `film.voicing` in its `story.json` (the voices live with the base story).
- The next director — a new `directors/<name>.json` + a style + a production.
