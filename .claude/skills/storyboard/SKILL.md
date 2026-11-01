---
name: storyboard
description: Develop or fix a paper-theatre bible (characters, poses, sets) and storyboard (scenes, shots, camera, focus, light, sound); use for new scenes, fixing shot composition, after looking at stills.
---

# Bible and storyboard

Format — README.md ("Storyboard"), the full vocabulary — docs/new-style.md, an example — `stories/mate-in-3/bible.json`,
`storyboard.json`, rules — docs/treatment.md.

## Bible
- A character: `look` (the canon, in English, style-free), poses with `desc`, `h` (cm), `aspect`, `facing`. Sitting poses —
  with the chair in the same cut-out. A jointed puppet — `parts` (pivot/attach in fractions of the card; parts are
  generated without the character sheet).
- A set: pieces with `kind` (backdrop / floor / cutout / procedural), `size` or `h`, `pos`; an opening — `hole`;
  a light source inside a card — `cast: false`.

## Storyboard
- First write out the sentences with their indices (prepared/<lang>.json) and a time estimate; a shot sits on a unit of
  meaning, 5–12 s; longer than 14 s — only if there is movement (a push-in, a walk), shorter than 1.5 s — only as a hit.
- Vertical: single shots, vertical shapes, processions — one figure at a time through a narrow opening.
- Every shot gets a `note` (what and why). A change of place — `"in": "dip"`. After an insert in another set,
  return the `"set"` explicitly.
- Check: `make timeline` (no errors), stills with `--debug` for composition, without it for light; fix `cams`,
  `pos`, `push`, `focus`. The key light is front-top.
