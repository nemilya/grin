---
name: paper-film
description: Take a story through the film pipeline (text → translation → bible → storyboard → assets → narration → timeline → sound → frames) or continue from a given stage; use when asked to make or update a film, check stage status, generate assets, narrate, render.
---

# Film pipeline

0. **Media first**: `make media-pull` (pictures and narration of `media.rev` from nemilya/grin-media). Until
   they are pulled, `make assets` / `make voice` / `make site` refuse to run — never bypass that with
   `MEDIA_CHECK=0` to "regenerate missing" files: they are not missing, they are not pulled.
1. `make status S=<story>` — what is ready. Work from the first unfinished stage.
2. **New story**: `stories/<slug>/story.json` modelled on `stories/mate-in-3/story.json` (source, film), then
   `make prepare S=<slug>`.
3. **Translation** (if the film language ≠ the source language): `make translate S=<slug>` (OpenRouter) — or translate
   in the session: write `{id: text}` and save it through `engine.translate` with the fingerprint `_sha(source paragraph)`
   into `translations/<lang>.json` (model: "claude-code"), then `make prepare`. First — `glossary.json` (names, refrains).
4. **Bible and storyboard** — skill `storyboard`.
5. **Assets**: check 1–2 pictures first (`python3 -m engine assets <slug> --keys refs/<character>,<character>/<pose>`),
   look at `assets/raw/` and the cut-out on a dark background; then `make assets-used S=<slug>`.
6. **Narration**: `stories/<slug>/voicings/<id>/voicing.json` (voice, delivery in English), per-paragraph delivery —
   `overrides/<lang>.json` → `manner`; `make voice S=<slug> FROM=.. TO=..`. Check `score` (≥ 0.85) and `tail`.
7. **Save paid work early**: after each batch of generated pictures or narration — `make media-push`, then commit
   the JSON together with the staged `media.rev` and `git push`. In a cloud session anything not pushed is lost with
   the container.
8. **Timeline and frames**: `make timeline`, stills `node tools/capture.mjs stills <slug> --scale 0.3`
   (first `--debug` — composition, then without — light). Look at the sheet `out/<slug>/stills/contact.jpg`.
9. **Sound and film**: `make sound`, `make video` (or a segment: `make video-demo START=<shot>`).
   The GPU is picked automatically (the `WebGL:` line at the start); without one ≈ 1 s/frame at 720×1280 — leave long
   renders to the user. Next to the master — `…-share.mp4` for social media (`make share FILE=…` for an existing file).
