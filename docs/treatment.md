# *Mate in Three Moves* — the director's treatment

**English** · [Русский](treatment.ru.md)

A story by Alexander Grin (1908), a vertical 9:16 film in English: the narrator's voice + subtitles; the image — a
children's paper-theatre performance on a table, filmed handheld by the light of a desk lamp. The author and the title
are not read out. The translation — `stories/mate-in-3/translations/en.json`, the storyboard — `storyboard.json`,
characters and sets — `bible.json`.

## The idea

**Naive material against existential horror.** Cardboard puppets moved by a child — and a text about a man who is
afraid to "think death through". The simpler and more touching the paper, the more frightening what it depicts. Paper in
the story is not a metaphor but an object: "a clean sheet of paper… I write 10, I rub it out, I write 10 again".

**One light source.** The whole film is lit by the "puppeteer's lamp" above the stage and a lampshade in the frame — the
light is warm, a pool, the edges of the frame sink into darkness. In the finale the text itself gives the light: "flooded
with electric light" — the warm lamp gives way to the flat, cold light of a bulb from above, hard shadows, a 50 Hz hum.

**A handheld camera = life.** The camera breathes slightly all the time. The only absolutely still shot is the last one:
the empty armchair, a point above its back "where, a minute before, my eyes had been shining".

**Mate in three moves.** The patient's story is three "moves", three growing attacks:
1. **The window, a summer day** — a procession: a woman with a baby → a little girl → a schoolgirl → a lady → an old woman;
   "all that's missing is a funeral procession".
2. **The garden at night** — the stars, infinity, "10" on the sheet; then "no walls" — the walls of the cardboard box fall.
3. **The porch, the bed, the night procession** — "Misha!", the heart, the bed floats away; the thought stops on the old woman.

**Mate** — a raised hand, eyes like abysses, the hand comes down joint by joint. "Leipzig!" — too late.

## Visual rules

| | |
|---|---|
| Material | cut-outs of thin cardboard: gouache + coloured pencils, a white rim from the scissors, paper texture; the cards are slightly curved and cast shadows by their silhouette |
| Movement | the figures are not animated — they are **moved**: sliding across the floor, a card's "hops", the trembling of the puppeteer's hand (jitter), swaying; a change of pose = a change of card |
| A jointed puppet | the patient's arm — three pieces on brass fasteners (upper arm, forearm, hand); the bronzed cufflink rhymes with a fastener |
| Light | the puppeteer's lamp (a spot from the front and above) + the lampshade in the frame (a halo) + fill; day — the sun, night — the moon, imagination — a shadow screen |
| Focus | shallow depth of field, "macro": focus as a tool — racking from a face to the portière, from the sheet to the "10"; in the finale the eyes go out of focus ("abysses going out") |
| Colour | the procession loses colour: red calico → a ginger plait → a brown uniform → a lilac-grey lady → a grey old woman → black funeral silhouettes |
| Three worlds | the present (the office) — coloured paper; memory — the same paper in its own light (the only day — the window); imagination and fear — black silhouettes on backlit paper (Lotte Reiniger) |
| Subtitles | Source Serif 4, warm white with a soft shadow, at 73% of the frame height — above the Reels/Shorts interface |

## References

- **Victorian toy theatre** (Pollock's, Webb): figures on "slides", ground rows (a low fence hides the legs and the
  procession's guides), wings and backdrops.
- **Lotte Reiniger** — silhouette animation: the funeral procession, running dogs, the wife in the door.
- **Yuri Norstein** (*Tale of Tales*, *Hedgehog in the Fog*) — multiple planes, light and fog between the layers,
  focus as breathing.
- **Michel Ocelot** — silhouettes and background colour.
- **Technical references** — `nemilya/mountain-rock`: paragraph-by-paragraph translation with a glossary and fingerprints,
  a bible with characters by phase, character sheets as references, narration with back-transcription, a
  pending/stale/ok harness. `nemilya/garden3d` — a three.js scene: shadows, tone mapping, frame export.

## Characters

| | appearance (the canon — `bible.json`) | poses |
|---|---|---|
| The doctor | ~27, thin, a thin moustache, a pince-nez on a cord, a dark three-piece suit, a stand-up collar | walks, sits, legs crossed with a pencil, frozen, jumps up and shouts |
| The patient (Misha) | ~45, bald, a curly fair beard, a sharp nose, short-sighted, plump; a brown frock coat, starched cuffs, bronzed cufflinks | 9 sitting poses (the bentwood chair is part of the cut-out) + the head, abyss eyes, hands in a cobweb, a button; at home: at the window, on a bench, in bed, in a hammock |
| The procession | a woman with a baby (red calico), a girl of 7 (a ginger plait), a schoolgirl, a prim lady, an old woman | walk from left to right; the old woman still faces us |
| The wife | only a silhouette in a lit doorway | |
| Shadows | the funeral (a hearse, mourners), dogs | silhouettes |
| Prologue | a yard-keeper with a broom, a visitor with a tic — "the first procession" in the office doorway | |

## Sets

The office (box walls, a portière, a desk with green baize, a lamp with a green shade, an armchair, a bulb under the
ceiling; behind the walls — black cardboard with pin-prick stars), a window onto the street (a fence ground row),
the garden at night (stars, trees, a house with a porch and a glowing door), the bedroom, the void, a shadow screen,
a dark table for close-up inserts.

## Scenes

| | scene | paragraphs | key devices |
|---|---|---|---|
| s01 | An empty practice | 001 | the click of the lamp — the paper office lights up; the doctor paces; the yard-keeper and the visitor pass in the doorway |
| s02 | The third patient | 002–003 | a figure slides out from behind the portière; the light closes in on him ("as if he were alive"); a portrait, fingers in a cobweb; he blushes — a pink glow |
| s03 | "What is your complaint?" | 004–011 | a doctor/patient figure-eight, a gaze over the writing things (a focus rack), the card breathing |
| s04 | Leipzig | 012–017 | a pencil through the fingers; **a cut-out with a chess problem** emerges from the dark; a paper "?" slides out after the doctor |
| s05 | The window (move 1) | 018 | a dip into the only daylight; dust motes in a beam; the procession loses colour |
| s06 | The chain | 019–023 | the procession's shadow along the wall; the focus goes behind the portière; **a shadow theatre — the funeral**; apples on a bough; "a terrible simplicity" |
| s07 | The handkerchief | 024–027 | a breather: the hammock, the handkerchief — the light grows warmer |
| s08 | The garden. Infinity (move 2) | 028–029 | the stars twinkle "irritatingly"; the sheet on the doctor's desk: 10 → rubbed out → 10 |
| s09 | Without fear of death | 030–036 | the lamp swings ("a whirl of thoughts"); a whisper — the camera freezes |
| s10 | No walls | 037–039 | a pull-back — the office turns out to be a box on a table; **the walls fall**, the doctor in the armchair in a void with stars; the walls are back as if nothing happened |
| s11 | The porch, the bed, the procession (move 3) | 040 | the wife's silhouette in the door; the light beats like a heart; the bed floats away; running dog-thoughts; a pale night procession; the old woman turns round |
| s12 | The hand (mate) | 041–043 | the room sighs (walls and light — an inhale); the hand rises; the cufflink in close-up; the abyss eyes go out in defocus; the hand comes down joint by joint |
| s13 | Leipzig! | 044–045 | he jumps up — short hits of shots on every phrase |
| s14 | Electric light | 046 | a click — cold light from above, a hum; a still camera; the empty armchair; the light goes out |

Vertical 9:16: single shots and close-ups, verticals (the window, the portière, the raised hand the full height of the
frame), the procession passes through the narrow window one figure at a time. The average shot is 7 s, 133 shots over ~16 minutes.

## Sound

The voice — one narrator (Gemini TTS, Charon), the manner per paragraph: the patient's monologue — whispered, halting;
the shout "Leipzig!" — loud, measured. Ambience — a ticking clock in the office, crickets in the garden, the quiet of the
room. Music — synthesized: a low drone of tension, a broken music-box waltz in D minor slowing towards the end like a
spring running down — cut off at the doctor's leap. Effects: the click of the lamp, the room's sigh, a palm slapping a
knee, the electric hum; the finale — a click, silence.
