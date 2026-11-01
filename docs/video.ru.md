# Рендер фильма (YouTube, Shorts, соцсети)

[English](video.md) · **Русский**

Фильмы рендерятся на своей машине: браузер (Playwright Chromium) рисует каждый кадр по времени, ffmpeg кодирует.
В облачной сессии видеокарты нет — там рендер программный и идёт часами.

## Форматы постановок

| постановка | основной формат | второй формат |
|---|---|---|
| `mate-in-3` (бумажный театр) | вертикаль 1080×1920 | `F=horizontal` → 1920×1080 |
| `mate-in-3-tarkovsky` | вертикаль 1080×1920 | `F=horizontal` → 1920×1080 |
| `sila-nepost` (немое кино) | горизонталь 1920×1080 | — |
| `leaf-story` (авангард) | горизонталь 1920×1080 | `F=vertical` → 1080×1920 |

Для обычного ролика на YouTube нужна горизонталь, для Shorts / Reels / TikTok — вертикаль. Язык: `L=ru` — русский
голос и субтитры, без него — английские (`story.json → film.voicings`).

## Рецепт: один фильм для YouTube

```bash
make media-pull                                       # картинки и озвучка (без них рендер покажет заглушки)
make video-demo S=mate-in-3 F=horizontal START=s12a   # проба: от кадра s12a до конца, пара минут
make video S=mate-in-3 F=horizontal                   # фильм целиком; таймлайн и звук соберутся сами
make youtube S=mate-in-3 F=horizontal                 # субтитры .srt и главы для описания
make thumbnail S=mate-in-3 F=horizontal SHOT=s01a     # обложка: кадр + название
```

Результаты — в `out/<история>/`:

| файл | что это | куда |
|---|---|---|
| `<история>-<F>[-<L>][-subs].mp4` | мастер, без субтитров (`-subs` — `SUBS=1`, вшиты): 1080p, H.264 High, ≈ 16 Мбит/с на маке (videotoolbox; иначе x264 CRF 17), AAC 160k | **YouTube** |
| `<история>-<F>[-<L>]-share.mp4` | 720p, ≈ 3,5 Мбит/с, AAC 128k, faststart — делается сразу после мастера, бережно: на маке аппаратное декодирование и кодирование, низкий приоритет, 2 потока (`--no-share` — не делать) | Telegram, Reels, TikTok |
| `<история>-<F>[-<L>].srt` | субтитры (`make youtube`) | YouTube Studio → Субтитры |
| `<история>-<F>[-<L>]-thumb-<кадр>.jpg` | обложка (`make thumbnail`, ниже) | YouTube Studio → «Значок» |
| `<история>-<F>[-<L>]-chapters.txt` | главы по сценам, `0:00 …` (`make youtube`) | в описание ролика как есть |

Например, `make video S=mate-in-3 F=horizontal L=ru` → `out/mate-in-3/mate-in-3-horizontal-ru.mp4`.
`make youtube` нужна полная озвучка (`timing: voicing` в строке таймлайна), иначе главы и субтитры разойдутся с роликом —
он предупредит.

## Субтитры: по умолчанию — отдельным файлом

Фильм рендерится **без вшитых субтитров**: для YouTube загружается `.srt` из `make youtube` (зритель может их
выключить, YouTube их индексирует, можно несколько языков). В YouTube Studio: загрузить `.mp4`, потом «Субтитры» →
добавить язык → «Загрузить файл» → `.srt` (английский; и русский — `make youtube … L=ru`, к тому же английскому ролику).

Где отдельной дорожки субтитров нет — Shorts, Reels, Telegram — вшить их: `SUBS=1`:

```bash
make video S=mate-in-3 SUBS=1     # → out/mate-in-3/mate-in-3-subs.mp4 (+ -subs-share.mp4)
```

Это касается только рендера фильма: в плеере на сайте субтитры остаются (кнопка CC), на стоп-кадрах тоже
(`--no-subs` — без них). Интертитры немого кино (`sila-nepost`) — часть картинки, они остаются.
Не ставьте `"subtitles": {"burn": false}` в `story.json`: так субтитры пропадут и в плеере на сайте.

## Обложка (thumbnail)

```bash
make thumbnail S=mate-in-3 F=horizontal SHOT=s01a SUB="a paper theatre film"   # та, что на YouTube
# → out/mate-in-3/mate-in-3-horizontal-thumb-s01a.jpg (1280×720) + -raw.jpg (тот же кадр без текста)
```

Один кадр раскадровки без субтитров, 1280 px по длинной стороне, поверх — название, автор и год из `story.json`
и строка под ними (по умолчанию — название видео в `site.json`), шрифтами сайта.

| параметр | по умолчанию | |
|---|---|---|
| `SHOT=` | постер постановки в `site.json` | какой кадр (id — по листу стоп-кадров: `make stills F=…`) |
| `AT=` | доля из постера, иначе 0.5 | момент внутри кадра, 0…1 |
| `POS=` | `top` | текст: `top` (по центру, на тёмном верху), `left`, `right` — там, где в кадре темно |
| `TITLE=` / `SUB=` | из `story.json` / `site.json` | заменить название / строку под ним |
| `L=ru` | английский | русские название и автор (и русский таймлайн: сначала `make timeline F=… L=ru`) |

Что работает на YouTube: один ясный предмет, который читается в маленьком превью на телефоне (лицо, освещённая
фигура на тёмной сцене), текст — на тёмной стороне кадра. Загрузка: YouTube Studio → ролик → «Значок» →
«Загрузить файл» (≤ 2 МБ). «Test & Compare» в Studio сравнит две-три обложки на зрителях.

## Время и железо

| | скорость | фильм 18,7 мин (≈ 27 000 кадров при 24 fps) |
|---|---|---|
| Mac, Apple M2 (видеокарта, `h264_videotoolbox`) | ≈ 0,04 с/кадр при 1920×1080 (замер) | ≈ 20 мин |
| без видеокарты (SwiftShader) | ≈ 1 с/кадр при 720×1280 | часы |

Первые строки рендера говорят, на чём он идёт: `WebGL: … Apple M2 … — GPU` или `SwiftShader` (программный),
и `codec: h264_videotoolbox` (аппаратный). Настройки (`local.mk` или в команде):

- `COOL=1` (`CAPTURE_COOL = 1`) — без перегрева: ffmpeg с низким приоритетом, 2 потока, паузы между кадрами;
- `CAPTURE_GL = gpu | cpu`, `CAPTURE_ENCODER = videotoolbox | x264` — задать явно;
- `SCALE=0.5` — половинное разрешение (быстро проверить фильм целиком).

Пока идёт рендер, ноутбук не должен засыпать — захват остановится.

## Все фильмы сразу

```bash
# горизонталь, по-английски, субтитры отдельным .srt — для YouTube
make video S=mate-in-3 F=horizontal           && make youtube S=mate-in-3 F=horizontal
make video S=mate-in-3-tarkovsky F=horizontal && make youtube S=mate-in-3-tarkovsky F=horizontal
make video S=sila-nepost                      && make youtube S=sila-nepost
make video S=leaf-story                       && make youtube S=leaf-story

# вертикаль, субтитры вшиты — для Shorts / Reels
make video S=mate-in-3 SUBS=1
make video S=mate-in-3-tarkovsky SUBS=1
make video S=leaf-story F=vertical SUBS=1
```

К любой команде можно добавить `L=ru` — будет русская версия. Версия для соцсетей из готового файла:
`make share FILE=out/…/x.mp4`.
