# Paper theatre: story → translation → bible/storyboard → assets → narration → timeline → sound → render.
# The OpenRouter key — in the environment, .env or local.mk (OPENROUTER_API_KEY = sk-or-…). Needs Python 3.10+ (+ numpy
# for assets and sound), ffmpeg, Node 18+ with playwright (npm i && npx playwright install chromium).
-include local.mk
export OPENROUTER_API_KEY OPENROUTER_PROXY CAPTURE_GL CAPTURE_ENCODER DEPLOY SITE_URL
# COOL=1 — rendering without overheating the laptop (low ffmpeg priority, 2 threads, pauses between frames)
export CAPTURE_COOL = $(COOL)

PY ?= python3
S ?= mate-in-3
PORT ?= 8720
SCALE ?= 1
# F=horizontal — another film format (story.json → formats): its own cameras and storyboard, the same narration, sound, assets
# L=ru — the film in another language (story.json → film.voicings): that language's voice and subtitles, the same storyboard
FMT = $(if $(F),--format $(F)) $(if $(L),--lang $(L))
empty :=
space := $(empty) $(empty)
TL = $(subst $(space),-,$(strip $(F) $(L)))
TLDEMO = $(if $(TL),$(TL)-demo,demo)
.PHONY: admin site serve deploy deploy-dry help setup share thumbnail youtube preview status media-pull media-push media-status prepare translate assets assets-used voice timeline demo sound stage stills video video-demo test check

help:  ## list the targets
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup:  ## 0) once: check python/numpy/ffmpeg/node, npm install, a browser for capture, local.mk
	@command -v $(PY) >/dev/null || { echo '✗ no python3 (macOS: brew install python)'; exit 1; }
	@$(PY) -c 'import sys; assert sys.version_info >= (3, 10)' || { echo '✗ Python 3.10+ is required'; exit 1; }
	@$(PY) -c 'import numpy, PIL.features; assert PIL.features.check("webp")' 2>/dev/null || { echo '✗ no numpy/Pillow (with WebP): $(PY) -m pip install numpy pillow  (or in a venv)'; exit 1; }
	@command -v ffmpeg >/dev/null || { echo '✗ no ffmpeg (macOS: brew install ffmpeg)'; exit 1; }
	@command -v node >/dev/null || { echo '✗ no Node 18+ (macOS: brew install node)'; exit 1; }
	npm install
	@npx playwright install chromium || echo '⚠ Playwright Chromium did not install — capture will use an installed Google Chrome (install it if there is none)'
	@test -f local.mk || { cp local.mk.example local.mk; echo '→ created local.mk: put OPENROUTER_API_KEY there (needed only for generation: translation, pictures, narration)'; }
	@git config core.hooksPath tools/hooks
	@echo '✓ done. Pictures and narration: make media-pull (≈ 0.3 GB); check: make status; demo: make video-demo'

media-pull:  ## media (pictures, narration) of media.rev from nemilya/grin-media; LATEST=1 — the tip of the media branch
	$(PY) -m engine.media pull $(if $(LATEST),--latest) $(if $(FORCE),--force)

media-push:  ## commit and push changed media, write media.rev (commit it with the JSON); MSG="…" — message
	$(PY) -m engine.media push $(if $(MSG),-m "$(MSG)")

media-status:  ## media: pulled / changed locally / not pushed
	$(PY) -m engine.media status

status:  ## what is ready, stage by stage
	$(PY) -m engine status $(S)

prepare:  ## 1) source → prepared/ (and prepared/<film language> from the translation)
	$(PY) -m engine prepare $(S)

translate:  ## 2) paragraph translation via OpenRouter (missing and stale ones)
	$(PY) -m engine translate $(S)

assets-used:  ## 4) generate the assets that are in the timeline (Seedream, ~$0.018 per picture)
	$(PY) -m engine assets $(S) --used

assets:  ## 4) all the bible's assets
	$(PY) -m engine assets $(S)

voice:  ## 5) narrate missing paragraphs (FROM=040 TO=046 — a range, L=ru — that language's narration)
	$(PY) -m engine voice $(S) $(if $(L),--lang $(L)) $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO))

timeline:  ## 6) storyboard + speech timing → build/timeline[-F].json  (F=horizontal — horizontal 16:9)
	$(PY) -m engine timeline $(S) $(FMT)

sound: timeline  ## 7) the film's sound → build/sound[-F].wav
	$(PY) -m engine sound $(S) $(FMT)

demo:  ## an excerpt to try things: timeline and sound from shot START to shot END → build/*-demo.*
	$(PY) -m engine timeline $(S) $(FMT) --start $(or $(START),demo) $(if $(END),--end $(END)) --name demo
	$(PY) -m engine sound $(S) $(FMT) --name demo

stage:  ## preview the scene in a browser: http://127.0.0.1:8720/stage/?story=mate-in-3 (&tl=horizontal, &debug)
	$(PY) -m http.server $(PORT) --bind 127.0.0.1

preview: sound  ## build the timeline and sound [F=…] and open the player (no render): shots + voice + music
	@echo 'player: http://127.0.0.1:$(PORT)/stage/?story=$(S)$(if $(TL),&tl=$(TL))   (space — play, ← → — shots, g — safe area)'
	$(PY) -m http.server $(PORT) --bind 127.0.0.1

stills: timeline  ## a still of every storyboard shot + a sheet → out/<story>/[F-]stills/
	node tools/capture.mjs stills $(S) --scale 0.5 $(if $(TL),--tl $(TL))

video: sound  ## 8) the whole film, no subtitles (YouTube: + .srt from make youtube) → out/<story>/<story>[-F].mp4 (+ -share.mp4); SUBS=1 — burn in subtitles → …-subs.mp4
	node tools/capture.mjs video $(S) --scale $(SCALE) $(if $(TL),--tl $(TL)) $(if $(filter 1,$(SUBS)),--subs)

video-demo: demo  ## an excerpt film → out/<story>/<story>[-F]-demo.mp4 (SUBS=1 — with burnt-in subtitles)
	node tools/capture.mjs video $(S) --tl $(TLDEMO) --scale $(SCALE) $(if $(filter 1,$(SUBS)),--subs)

youtube:  ## .srt subtitles and chapters for the description from the built timeline (after make timeline F=horizontal)
	$(PY) -m engine youtube $(S) $(FMT)

thumbnail: timeline  ## a YouTube thumbnail: a shot without subtitles + the title → out/<story>/<story>[-F]-thumb-<shot>.jpg (SHOT=s01a AT=0.5 POS=top|left|right TITLE=… SUB=…, L=ru)
	node tools/capture.mjs thumbnail $(S) $(if $(TL),--tl $(TL)) $(if $(SHOT),--shot $(SHOT)) $(if $(AT),--at $(AT)) $(if $(POS),--pos $(POS)) $(if $(L),--lang $(L)) $(if $(TITLE),--title "$(TITLE)") $(if $(SUB),--sub "$(SUB)")

share:  ## a social media version of a finished film: make share FILE=out/mate-in-3/mate-in-3-demo.mp4 (video makes it itself)
	node tools/capture.mjs share $(or $(FILE),out/$(S)/$(S).mp4)

admin:  ## the local admin (view only): assets, character sheets, storyboard, narration — http://127.0.0.1:8740/admin/
	$(PY) tools/admin.py

site:  ## the site → dist/ (site.json: stories, narration, video in the browser; a rebuild redoes only what changed)
	$(PY) -m engine site

serve:  ## view the built site as on the hosting: http://127.0.0.1:8730/
	$(PY) tools/serve.py 8730

deploy:  ## upload the built dist/ to the server (DEPLOY in local.mk); refuses a stale build
	$(PY) -m engine.deploy

deploy-dry:  ## what deploy would upload — changes nothing
	$(PY) -m engine.deploy --dry

test:  ## tests (no network)
	$(PY) -m unittest discover -s tests -v

check: test  ## tests + JS syntax
	node --check stage/js/stage.js && node --check stage/js/paper.js && node --check stage/js/post.js && node --check stage/js/geometry.js && node --check tools/capture.mjs
