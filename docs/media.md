# How `grin` and `grin-media` work together

**English** · [Русский](media.ru.md)

In short: **`grin` is the main repository, [`grin-media`](https://github.com/nemilya/grin-media) is the file store
for it.** One line in `grin` ties them together: the file `media.rev`.

## One folder, two git repositories

```
grin/                          ← the folder on disk
├── .git/                      ← git of grin: sees the code and JSON, ignores pictures and sound (.gitignore)
├── .media.git/                ← git of grin-media: sees only the media in stories/
├── media.rev                  ← in grin: "this commit needs media version 5bf11a8"
├── engine/  stage/  site/ …   ← grin only
└── stories/mate-in-3/assets/
    ├── assets.json            ← grin: the list of assets, prompts, fingerprints
    └── doctor/seated.webp     ← grin-media: the picture itself
```

Both repositories write into the same folder, so the engine knows nothing about this: a picture sits exactly where it
always did. Every file belongs to exactly one of the two repositories.

| | `grin` | `grin-media` |
|---|---|---|
| what | code, texts, translations, bibles, storyboards, manifests (`assets.json`, `voicing.json`) | `stories/**/*.webp` (cut-outs, sets), `*.jpg` (character sheets), `*.opus` (narration takes) |
| git dir | `.git/` | `.media.git/` (created by `make media-pull`) |
| size | ≈ 1.5 MB | ≈ 0.3 GB, grows with every new or regenerated picture |
| who commits | you / Claude Code, as usual | only `make media-push` |

Not in either: `assets/takes/` (earlier picture variants), `assets/raw/` (sources before keying), `build/`, `out/`,
`dist/` — local only.

## The link: `media.rev`

`grin-media` is just a sequence of media snapshots:

```
grin-media:  be76cbf (README) → cfccf96 → 0fda1c5 → 3837137 → 2bae254 → 5bf11a8 (leaf-story)
                                                                          ↑
grin:        59fcd6f, 33e70d7 ─── media.rev = 5bf11a8 ──────────────────┘
```

By itself `grin-media` doesn't know which code it belongs to — `grin` says so: "my commit needs media snapshot
5bf11a8". Like a git submodule, except the files are laid into the same folders instead of a subfolder.

## Example: one picture redrawn

| step | in `grin` | in `grin-media` |
|---|---|---|
| `make assets … --redo doctor/seated` | `assets.json`: new seed and fingerprint (not committed yet) | a new `seated.webp` on disk (not committed yet) |
| `make media-push` | `media.rev`: `5bf11a8` → `M2`, staged | new commit `M2` (parent `5bf11a8`) with that one file, pushed to `main` |
| `git commit` + `git push` | commit `C2` = `assets.json` + `media.rev = M2`; the hook checks that `M2` is already in grin-media | — |
| on another machine: `git pull` | `C2` arrives, `media.rev = M2` | the old picture is still on disk; `make status` says "media.rev wants M2", generation and `make site` refuse to run |
| there: `make media-pull` | — | `M2` is fetched, `seated.webp` replaced |

The old version doesn't disappear: `git checkout C1` → there `media.rev = 5bf11a8` → `make media-pull` brings the old
picture back.

## The everyday rule

- **after `git pull` — `make media-pull`** (the code says which media version, this command brings it);
- **before `git push` — `make media-push`**, if anything was generated (first the pictures, then the code that refers
  to them). In a Claude Code cloud session push early: anything not pushed is lost with the container.

Safety nets: forgot `media-push` → the `pre-push` hook stops `git push`; forgot `media-pull` → `make status` shows the
mismatch, and generation and the site build refuse to run (otherwise a fresh clone + `make assets` would pay to redraw
the whole film; `MEDIA_CHECK=0` overrides).

## Branches

A media branch has the same name as the code branch: `main` → `main`, `claude/x` → `claude/x` — experiments in a
branch don't end up in the media of main. Two pushes at the same time (two sessions) are merged by `media-push` itself,
without touching files outside `stories/`; only the same file changed on both sides is a conflict.

## Commands

```bash
make media-pull            # the media of media.rev (LATEST=1 — the tip of the media branch; FORCE=1 — discard local changes)
make media-push            # commit and push changed media, write and stage media.rev (MSG="…" — message)
make media-status          # pulled? changed locally? pushed?
```

Code — `engine/media.py`, tests — `tests/test_media.py`, hook — `tools/hooks/pre-push`.

**Where media come from.** The media remote follows the code repository's: `grin` cloned over ssh
(`git@github.com:nemilya/grin.git`) → media over ssh (`git@github.com:nemilya/grin-media.git`) with the same keys;
over https → https. While the repositories are private, https asks for a GitHub login (a token, not the password) —
clone over ssh instead. `MEDIA_REMOTE` in `local.mk` overrides it (e.g. a mirror on your own server).

## What not to do

- clone `grin-media` separately — it lives inside the `grin` folder as `.media.git`, `make media-pull` creates it;
- commit to it by hand — only `make media-push`;
- commit media files to `grin` — `.gitignore` and CI stop it.

## Why this way

Before, everything was in one repository: 963 MB of `.git` after a few stories, because every regenerated picture
stays in history forever, and an open repository can't rewrite its history. Now `grin` stays ≈ 1.5 MB; `grin-media`
can, when it grows to a few GB, be squashed to the current snapshot (its old history archived on your own servers),
or moved to other storage — the `make media-*` commands stay the same. Cut-outs are stored as lossless WebP
(pixel-identical to PNG, ≈ 45 % of the size).
