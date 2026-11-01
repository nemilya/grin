# TODO

**English** · [Русский](TODO.ru.md)

Open work, in rough order. Each item: what, why, and implementation notes gathered so far. When an item is done —
delete it here (the history is in git) and update the docs it touches.

## 1. "About the project" page on the site

`/<lang>/about/` next to "About the author", linked from the landing header and every page's footer.

- Texts — `site/about.json` (`{"en": [paragraphs], "ru": [...]}`), like `site/author.json`: what this is, how it is
  made (one paragraph of the pipeline: text → translation → staging → pictures → narration → a scene drawn in the
  browser), that the code, stagings and texts were made together with Claude Code, licenses (code MIT, content CC0),
  the repository.
- Links and the "made with" line — config, not code: `site.json → "project": {"repo": "https://github.com/nemilya/grin",
  "contact": {"telegram": "https://t.me/<nick>"}, "made_with": {"en": "…", "ru": "…"}}` — the maintainer fills in the
  Telegram nick and the model name they want to credit.
- Code: `engine/site.py` — copy `write_author` into `write_about`, call it from `write_landing`; `UI` gets
  `'about_project'` in both languages; `site/site.css` — reuse `.story.author-page`. Exclude `about.json` in
  `_copy_assets` (as `author.json`). `deploy.site_state` already watches `site/`, so a changed `about.json` marks the
  build stale.

**Open question**: the Telegram nick.

## 2. Make the repositories public

- Before: run GitHub secret scanning on both; `grep -rn "sk-or-\|OPENROUTER_API_KEY *=" .` (only the example in
  `local.mk.example` should match); the history of `grin` is fresh (since the move), `grin-media` holds only media.
- Then: `make media-pull` works for anyone over https without a login; add the GitHub link to the YouTube
  descriptions and to the about page; mention in `README` how to contribute (media are pushed only by the maintainer).
- Archive nemilya/mate-in-3 (Settings → Archive) — it keeps the full old history with the media.

## 3. Publish the other films

Recipe — `docs/video.md` (render without burnt-in subtitles, `make youtube` for `.srt` + chapters, `make thumbnail`).
Published: *Mate in Three Moves*, paper theatre, horizontal, English. Next: `mate-in-3-tarkovsky F=horizontal`,
`sila-nepost`, `leaf-story`; Russian versions (`L=ru`); vertical cuts for Shorts with `SUBS=1`.

- **Description generator**: `make youtube` could also write `…-description.txt` — the hook line, about the story
  (author, year — `story.json`), about the production (`site.json → videos[].about`), chapters, links (site, repo),
  how it was made, license, hashtags. The text that worked for the first video (in the session where it was
  published): hook without spoilers; "translated from the Russian and read in English"; chapters; "Read along … at
  grin.nemilya.me"; how it was made (Seedream pictures, Gemini TTS voice, three.js, Claude Code); CC0; hashtags
  `#AlexanderGrin #ShortStory #Audiobook #PaperTheatre #RussianLiterature`. Chapter titles come from scene titles —
  check them for spoilers (the paper theatre's "The hand (mate)" was shortened to "The hand").
- **Link videos from the site**: `site.json → videos[].youtube` (URL per language) → a "Watch on YouTube" link on the
  story page.

## 4. Media housekeeping (not urgent)

- **Mirrors** on the maintainer's servers: cron `git clone --mirror` once, then `git remote update` — a full backup
  of `grin-media` with history; `MEDIA_REMOTE` can point to a mirror if GitHub becomes unreachable.
- **Squash** when `grin-media` grows to a few GB: archive the full history (`git bundle` or the mirror), create an
  orphan commit with the current files, force-push `main`, `make media-pull LATEST=1` in `grin` and commit the new
  `media.rev`. Old `media.rev` pins then point to commits that are only in the archive — document that in
  `docs/media.md` when it happens.

## 5. Small things noticed

- Paper theatre, horizontal shot `s04i`: a stray white "D"-shaped card behind the doctor's chair (seen in the
  thumbnail candidates) — check the storyboard/state for that shot.
- `make thumbnail` on vertical frames: text is scaled to 720 px width — readable, could be larger/two lines.
- The first `make site` on a new machine takes ≈ 30 min (video sound for every production × language) — could
  cache `sound-*.m4a` by fingerprint in `grin-media` or on the server to skip it.
- Deploy runs only from the maintainer's machine (ssh); a cloud session can build `dist/` but not deploy.
- `node tools/capture.mjs stills sila-nepost` (without pulled media, in a cloud session) fails with the page error
  "boolean true is not iterable" and times out; `mate-in-3` works. It was there before the translation — check with media.

## 6. Later: a pipeline without an agent

Everything an agent did (Claude Code) is either API calls or creative decisions that can be expressed as a prompt
with checks. For the next stories the same path could become `make` steps:

| stage | now | without an agent |
|---|---|---|
| text, translation | `make prepare`, `make translate` | ✓ already scripts |
| bible: world, characters, poses, sets | agent writes | `engine/bible.py analyze`: LLM over the text → JSON by schema; poses from the storyboard's scenes |
| storyboard | agent writes | `engine/board.py draft`: LLM gets the text with sentence ids, the bible, the camera/effects vocabulary and an existing storyboard as an example → JSON; a **validator loop** (`timeline.build` errors, shot lengths, cameras, existing assets) feeds errors back until clean |
| assets, narration, sound, render | ✓ `make` | ✓ (music cues — an LLM draft per scene, or a music file) |
| quality control | agent looks at still sheets, fixes cameras/light | `engine/review.py`: automatic checks (mean brightness, empty frame share, the main figure cut by the frame edge) + an optional vision-model pass → JSON fixes → rebuild |

The human keeps: choosing the story and the voice, approving the bible and the storyboard, looking at the still
sheet, "keep / redo". A full run for a story of this size ≈ $2–3 (translation ≈ $0.2, bible + storyboard ≈ $0.3–0.5,
≈ 75 pictures ≈ $1.5, narration ≈ $0.2). Steps: `bible.py` → `board.py` (scene by scene, 1–3 paragraphs per request,
with the previous scenes as context) → `review.py` → `make film S=<story>` (stops at the stills for approval) → a
simple admin page for approving the bible and the storyboard.
