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
```

Результаты — в `out/<история>/`:

| файл | что это | куда |
|---|---|---|
| `<история>-<F>[-<L>].mp4` | мастер: 1080p, H.264 High, ≈ 16 Мбит/с на маке (videotoolbox; иначе x264 CRF 17), AAC 160k | **YouTube** |
| `<история>-<F>[-<L>]-share.mp4` | 720p, ≈ 3,5 Мбит/с, AAC 128k, faststart — делается сразу после мастера (`--no-share` — не делать) | Telegram, Reels, TikTok |
| `<история>-<F>[-<L>].srt` | субтитры (`make youtube`) | YouTube Studio → Субтитры |
| `<история>-<F>[-<L>]-chapters.txt` | главы по сценам, `0:00 …` (`make youtube`) | в описание ролика как есть |

Например, `make video S=mate-in-3 F=horizontal L=ru` → `out/mate-in-3/mate-in-3-horizontal-ru.mp4`.
`make youtube` нужна полная озвучка (`время: voicing` в строке таймлайна), иначе главы и субтитры разойдутся с роликом —
он предупредит.

## Субтитры: вшитые или отдельным файлом

По умолчанию субтитры вшиты в картинку — ролик можно загружать как есть. Для YouTube лучше отдельный `.srt`
(зритель может их выключить, YouTube их индексирует, можно несколько языков): `"subtitles": {"burn": false}` в
`story.json` — в `formats.horizontal` для `mate-in-3` / `mate-in-3-tarkovsky`, в `film` для `sila-nepost` / `leaf-story`
(у них горизонталь — основной формат), затем заново `make video` и `make youtube`. К английскому ролику можно
загрузить и английские, и русские субтитры: русский `.srt` — `make youtube … L=ru`.

## Время и железо

| | скорость | фильм 18,7 мин (≈ 27 000 кадров при 24 fps) |
|---|---|---|
| Mac, Apple M2 (видеокарта, `h264_videotoolbox`) | ≈ 0,04 с/кадр при 1920×1080 (замер) | ≈ 20 мин |
| без видеокарты (SwiftShader) | ≈ 1 с/кадр при 720×1280 | часы |

Первые строки рендера говорят, на чём он идёт: `WebGL: … Apple M2 … — видеокарта` или `SwiftShader` (программный),
и `кодек: h264_videotoolbox` (аппаратный). Настройки (`local.mk` или в команде):

- `COOL=1` (`CAPTURE_COOL = 1`) — без перегрева: ffmpeg с низким приоритетом, 2 потока, паузы между кадрами;
- `CAPTURE_GL = gpu | cpu`, `CAPTURE_ENCODER = videotoolbox | x264` — задать явно;
- `SCALE=0.5` — половинное разрешение (быстро проверить фильм целиком).

Пока идёт рендер, ноутбук не должен засыпать — захват остановится.

## Все фильмы сразу

```bash
# горизонталь, по-английски — для YouTube
make video S=mate-in-3 F=horizontal           && make youtube S=mate-in-3 F=horizontal
make video S=mate-in-3-tarkovsky F=horizontal && make youtube S=mate-in-3-tarkovsky F=horizontal
make video S=sila-nepost                      && make youtube S=sila-nepost
make video S=leaf-story                       && make youtube S=leaf-story

# вертикаль — для Shorts / Reels
make video S=mate-in-3
make video S=mate-in-3-tarkovsky
make video S=leaf-story F=vertical
```

К любой команде можно добавить `L=ru` — будет русская версия. Версия для соцсетей из готового файла:
`make share FILE=out/…/x.mp4`.
