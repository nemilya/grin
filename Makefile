# Бумажный театр: история → перевод → библия/раскадровка → ассеты → озвучка → таймлайн → звук → рендер.
# Ключ OpenRouter — в окружении, .env или local.mk (OPENROUTER_API_KEY = sk-or-…). Нужны Python 3.10+ (+ numpy
# для ассетов и звука), ffmpeg, Node 18+ с playwright (npm i && npx playwright install chromium).
-include local.mk
export OPENROUTER_API_KEY OPENROUTER_PROXY CAPTURE_GL CAPTURE_ENCODER DEPLOY SITE_URL
# COOL=1 — рендер без перегрева ноутбука (низкий приоритет ffmpeg, 2 потока, паузы между кадрами)
export CAPTURE_COOL = $(COOL)

PY ?= python3
S ?= mate-in-3
PORT ?= 8720
SCALE ?= 1
# F=horizontal — другой формат ролика (story.json → formats): свои камеры и раскадровка, те же озвучка, звук, ассеты
# L=ru — ролик на другом языке (story.json → film.voicings): голос и субтитры языка, раскадровка та же
FMT = $(if $(F),--format $(F)) $(if $(L),--lang $(L))
empty :=
space := $(empty) $(empty)
TL = $(subst $(space),-,$(strip $(F) $(L)))
TLDEMO = $(if $(TL),$(TL)-demo,demo)
.PHONY: admin site serve deploy deploy-dry help setup share youtube preview status media-pull media-push media-status prepare translate assets assets-used voice timeline demo sound stage stills video video-demo test check

help:  ## список целей
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup:  ## 0) один раз: проверка python/numpy/ffmpeg/node, npm install, браузер для захвата, local.mk
	@command -v $(PY) >/dev/null || { echo '✗ нет python3 (macOS: brew install python)'; exit 1; }
	@$(PY) -c 'import sys; assert sys.version_info >= (3, 10)' || { echo '✗ нужен Python 3.10+'; exit 1; }
	@$(PY) -c 'import numpy, PIL.features; assert PIL.features.check("webp")' 2>/dev/null || { echo '✗ нет numpy/Pillow (с WebP): $(PY) -m pip install numpy pillow  (или в venv)'; exit 1; }
	@command -v ffmpeg >/dev/null || { echo '✗ нет ffmpeg (macOS: brew install ffmpeg)'; exit 1; }
	@command -v node >/dev/null || { echo '✗ нет Node 18+ (macOS: brew install node)'; exit 1; }
	npm install
	@npx playwright install chromium || echo '⚠ Chromium Playwright не установился — захват возьмёт установленный Google Chrome (поставьте его, если нет)'
	@test -f local.mk || { cp local.mk.example local.mk; echo '→ создан local.mk: впишите OPENROUTER_API_KEY (нужен только для генерации: перевод, картинки, озвучка)'; }
	@git config core.hooksPath tools/hooks
	@echo '✓ готово. Картинки и озвучка: make media-pull (≈ 0,3 ГБ); проверка: make status; демо: make video-demo'

media-pull:  ## media (pictures, narration) of media.rev from nemilya/grin-media; LATEST=1 — the tip of the media branch
	$(PY) -m engine.media pull $(if $(LATEST),--latest) $(if $(FORCE),--force)

media-push:  ## commit and push changed media, write media.rev (commit it with the JSON); MSG="…" — message
	$(PY) -m engine.media push $(if $(MSG),-m "$(MSG)")

media-status:  ## media: pulled / changed locally / not pushed
	$(PY) -m engine.media status

status:  ## что готово по этапам
	$(PY) -m engine status $(S)

prepare:  ## 1) исходник → prepared/ (и prepared/<язык ролика> из перевода)
	$(PY) -m engine prepare $(S)

translate:  ## 2) перевод абзацев через OpenRouter (недостающие и устаревшие)
	$(PY) -m engine translate $(S)

assets-used:  ## 4) сгенерировать ассеты, которые есть в таймлайне (Seedream, ~$0.018 за картинку)
	$(PY) -m engine assets $(S) --used

assets:  ## 4) все ассеты библии
	$(PY) -m engine assets $(S)

voice:  ## 5) озвучка недостающих абзацев (FROM=040 TO=046 — диапазон, L=ru — озвучка языка)
	$(PY) -m engine voice $(S) $(if $(L),--lang $(L)) $(if $(FROM),--from $(FROM)) $(if $(TO),--to $(TO))

timeline:  ## 6) раскадровка + время речи → build/timeline[-F].json  (F=horizontal — горизонталь 16:9)
	$(PY) -m engine timeline $(S) $(FMT)

sound: timeline  ## 7) звук ролика → build/sound[-F].wav
	$(PY) -m engine sound $(S) $(FMT)

demo:  ## отрезок для пробы: таймлайн и звук от кадра START до кадра END → build/*-demo.*
	$(PY) -m engine timeline $(S) $(FMT) --start $(or $(START),demo) $(if $(END),--end $(END)) --name demo
	$(PY) -m engine sound $(S) $(FMT) --name demo

stage:  ## предпросмотр сцены в браузере: http://127.0.0.1:8720/stage/?story=mate-in-3 (&tl=horizontal, &debug)
	$(PY) -m http.server $(PORT) --bind 127.0.0.1

preview: sound  ## собрать таймлайн и звук [F=…] и открыть плеер (без рендера): кадры + голос + музыка
	@echo 'плеер: http://127.0.0.1:$(PORT)/stage/?story=$(S)$(if $(TL),&tl=$(TL))   (пробел — пуск, ← → — кадры, g — безопасная зона)'
	$(PY) -m http.server $(PORT) --bind 127.0.0.1

stills: timeline  ## стоп-кадр каждого кадра раскадровки + лист → out/<история>/[F-]stills/
	node tools/capture.mjs stills $(S) --scale 0.5 $(if $(TL),--tl $(TL))

video: sound  ## 8) ролик целиком, без субтитров (YouTube: + .srt из make youtube) → out/<история>/<история>[-F].mp4 (+ -share.mp4); SUBS=1 — вшить субтитры → …-subs.mp4
	node tools/capture.mjs video $(S) --scale $(SCALE) $(if $(TL),--tl $(TL)) $(if $(filter 1,$(SUBS)),--subs)

video-demo: demo  ## ролик-отрезок → out/<история>/<история>[-F]-demo.mp4 (SUBS=1 — с вшитыми субтитрами)
	node tools/capture.mjs video $(S) --tl $(TLDEMO) --scale $(SCALE) $(if $(filter 1,$(SUBS)),--subs)

youtube:  ## субтитры .srt и главы для описания из собранного таймлайна (после make timeline F=horizontal)
	$(PY) -m engine youtube $(S) $(FMT)

share:  ## версия для соцсетей из готового ролика: make share FILE=out/mate-in-3/mate-in-3-demo.mp4 (после video — сама)
	node tools/capture.mjs share $(or $(FILE),out/$(S)/$(S).mp4)

admin:  ## локальная админка (только просмотр): ассеты, листы героев, раскадровка, озвучка — http://127.0.0.1:8740/admin/
	$(PY) tools/admin.py

site:  ## сайт → dist/ (site.json: рассказы, озвучка, видео в браузере; повторная сборка — только изменившееся)
	$(PY) -m engine site

serve:  ## посмотреть собранный сайт как на хостинге: http://127.0.0.1:8730/
	$(PY) tools/serve.py 8730

deploy:  ## залить собранный dist/ на сервер (DEPLOY в local.mk); устаревшую сборку не заливает
	$(PY) -m engine.deploy

deploy-dry:  ## что залил бы deploy — ничего не меняет
	$(PY) -m engine.deploy --dry

test:  ## тесты (без сети)
	$(PY) -m unittest discover -s tests -v

check: test  ## тесты + синтаксис JS
	node --check stage/js/stage.js && node --check stage/js/paper.js && node --check stage/js/post.js && node --check stage/js/geometry.js && node --check tools/capture.mjs
