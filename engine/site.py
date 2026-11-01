"""Building the static site (grin.nemilya.me) → dist/: uploaded to the hosting as is.

    dist/index.html                       → the default language (site.json: default_lang)
    dist/<lang>/                          about the author and the list of stories
    dist/<lang>/<story>/                  a story: about it, "read and listen", MP3, video versions
    dist/<lang>/<story>/read/             reading with narration: sentence and word highlighting
    dist/<lang>/<story>/audio/story.mp3   the whole narration (+ story.json — the timing marks)
    dist/<lang>/<story>/<style>/          video in the browser: the scene (WebGL) by the timeline + sound, no mp4;
                                          vertical on a phone, horizontal on a wide screen (a switch)
    dist/media/<production>/              video media: assets/*.webp (layers), <orientation>-<lang>.json (timeline),
                                          sound-<lang>.m4a (voice + ambience + music), poster-<orientation>.webp
    dist/assets/                          the site's styles, scripts, fonts; stage-<stamp>/ — the stage and three.js

What is published — site.json (stories, narrations by language, video versions = productions stories/<id>). The video is
in the page's language if the production has a full narration in that language (film.voicings), otherwise in the storyboard's.
A rebuild redoes only what changed (dist/.build.json): layers, sound (the slowest), posters, MP3.
Links are relative, resources carry a ?v=<hash> stamp (they can be cached forever, pages — briefly).
"""
from __future__ import annotations

import hashlib
import html
import json
import shutil
import subprocess
import time
from pathlib import Path

from . import audio, config, prepare, sound, timeline, voicing

UI = {
    'en': {'stories': 'Stories', 'about': 'About the author', 'read': 'Read & listen', 'download': 'Download audio', 'mp3': 'MP3', 'mb': 'MB',
           'video': 'Video versions', 'watch': 'Watch', 'vertical': 'Vertical', 'horizontal': 'Horizontal',
           'min': 'min', 'h': 'h', 'narration': 'narration', 'translated': 'Translated from the Russian.',
           'original': 'Original Russian text.', 'video_in': 'Video in {lang}', 'back': 'All stories',
           'subtitles': 'Subtitles', 'fullscreen': 'Full screen', 'orientation': 'Vertical / horizontal',
           'loading': 'Loading the scene…', 'no_webgl': 'This browser cannot show the scene (WebGL is unavailable).',
           'play': 'Play', 'pause': 'Pause', 'page': 'Page', 'speed': 'Speed', 'follow': 'Back to narration',
           'tap_to_listen': 'Tap to listen', 'share': 'Share a link to this place', 'copied': 'Link copied',
           'copy_link': 'Link to this place:', 'day': 'Day theme', 'night': 'Night theme', 'voice': 'voice',
           'versions': '{n} video versions', 'one_version': '1 video version', 'lang_name': 'English',
           'about_video': 'The video is drawn live in your browser: a 3D scene, light and camera are computed as it plays.',
           'keys': 'Space — pause · ← → — 5 s · C — subtitles · F — full screen'},
    'ru': {'stories': 'Рассказы', 'about': 'Об авторе', 'read': 'Читать и слушать', 'download': 'Скачать аудио', 'mp3': 'MP3', 'mb': 'МБ',
           'video': 'Видеоверсии', 'watch': 'Смотреть', 'vertical': 'Вертикаль', 'horizontal': 'Горизонталь',
           'min': 'мин', 'h': 'ч', 'narration': 'озвучка', 'translated': 'Перевод с русского.',
           'original': 'Оригинальный текст.', 'video_in': 'Видео на языке: {lang}', 'back': 'Все рассказы',
           'subtitles': 'Субтитры', 'fullscreen': 'Во весь экран', 'orientation': 'Вертикаль / горизонталь',
           'loading': 'Загружается сцена…', 'no_webgl': 'Этот браузер не может показать сцену (нет WebGL).',
           'play': 'Слушать', 'pause': 'Пауза', 'page': 'Стр.', 'speed': 'Скорость', 'follow': 'К звучащему',
           'tap_to_listen': 'Нажмите, чтобы слушать', 'share': 'Поделиться ссылкой на это место',
           'copied': 'Ссылка скопирована', 'copy_link': 'Ссылка на это место:', 'day': 'Дневная схема',
           'night': 'Ночная схема', 'voice': 'голос', 'versions': 'видеоверсий: {n}', 'one_version': '1 видеоверсия',
           'lang_name': 'Русский',
           'about_video': 'Видео рисуется прямо в браузере: объёмная сцена, свет и камера считаются во время просмотра.',
           'keys': 'Пробел — пауза · ← → — 5 с · C — субтитры · F — во весь экран'},
}
LANG_NAMES = {'en': {'en': 'English', 'ru': 'Russian'}, 'ru': {'en': 'английском', 'ru': 'русском'}}
e = html.escape
V = {'assets': '', 'stage': ''}
ICON_DL = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="m7 10.5 5 5 5-5"/>'
           '<path d="M5 19.5h14"/></svg>')
ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M8 5.5v13a.6.6 0 0 0 .9.5l10.2-6.5a.6.6 0 0 0 0-1L8.9 5a.6.6 0 0 0-.9.5z"/></svg>'
ICON_BOOK = ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" '
             'stroke-linecap="round" stroke-linejoin="round"><path d="M12 6.5C10 5 7 4.5 4 5v13c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V5c-3-.5-6 0-8 1.5z"/>'
             '<path d="M12 6.5v13"/></svg>')


def _ui(lang: str) -> dict:
    return UI.get(lang, UI['en'])


def fmt_dur(sec: float, lang: str) -> str:
    u, m = _ui(lang), round(sec / 60)
    return f'{m // 60} {u["h"]} {m % 60:02d} {u["min"]}' if m >= 60 else f'{max(m, 1)} {u["min"]}'


def _hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- the page

def page(cfg: dict, lang: str, title: str, body: str, *, depth: int, path: str = '', extra_head: str = '',
         body_class: str = '', author: dict | None = None) -> str:
    """path — this page's address inside the language (for the language switch: the same page in another language)."""
    up = '../' * depth
    u = _ui(lang)
    langs = ''.join(f'<a href="{up}{x}/{path}"{" class=on" if x == lang else ""} hreflang="{x}">{x.upper()}</a>'
                    for x in cfg['langs'])
    brand = (author or {}).get('name', {}).get(lang, '')
    canon = f'<link rel="canonical" href="{e(cfg.get("url", "").rstrip("/"))}/{lang}/{path}">' if cfg.get('url') else ''
    alts = ''.join(f'<link rel="alternate" hreflang="{x}" href="{e(cfg.get("url", "").rstrip("/"))}/{x}/{path}">'
                   for x in cfg['langs']) if cfg.get('url') else ''
    return f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
{canon}{alts}
<link rel="stylesheet" href="{up}assets/site.css?v={V['assets']}">
<script>(function(d){{try{{var t=localStorage.getItem('theme');if(t)d.dataset.theme=t}}catch(e){{}}}})(document.documentElement)</script>
{extra_head}
</head>
<body class="{body_class}">
<header class="top">
  <a class="brand" href="{up}{lang}/">{e(brand)}</a>
  <div class="tools"><button class="theme" data-day="{e(u['day'])}" data-night="{e(u['night'])}" aria-label="{e(u['night'])}">☾</button>
  <nav class="langs">{langs}</nav></div>
</header>
{body}
<script src="{up}assets/site.js?v={V['assets']}"></script>
</body>
</html>
'''


# ---------------------------------------------------------------- video media

class Build:
    def __init__(self, cfg: dict, log=print):
        self.cfg, self.log = cfg, log
        self.dist = config.DIST
        self.state_f = self.dist / '.build.json'
        self.state = config.read_json(self.state_f, {}) or {}
        self.new = {}
        self.started = time.time()

    def touch(self, *files: Path) -> None:
        for f in files:
            f.parent.mkdir(parents=True, exist_ok=True)
            if f.exists():
                f.touch()

    def webp(self, prod: str, file: str) -> str:
        """A production layer (assets/…png|jpg) → media/<production>/assets/….webp; the path is relative to the production folder."""
        src = config.story_dir(prod) / file
        rel = str(Path(file).with_suffix('.webp'))
        out = self.dist / 'media' / prod / rel
        key = f'img/{prod}/{rel}'
        h = _hash(src.read_bytes())
        if self.state.get(key) != h or not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(src), '-vf',
                            "scale='if(gt(iw,ih),min(1400,iw),-2)':'if(gt(iw,ih),-2,min(1400,ih))'",
                            '-c:v', 'libwebp', '-quality', '82', '-pix_fmt',
                            'yuva420p' if src.suffix in ('.png', '.webp') else 'yuv420p', str(out)], check=True)
        self.touch(out)
        self.new[key] = h
        return f'{rel}?v={h}'

    def sound(self, prod: str, vlang: str, tl: dict) -> tuple[str, float]:
        """Video sound (voice + ambience + music) → media/<production>/sound-<lang>.m4a; shared by vertical and horizontal
        (the formats share their cues). Rebuilt only if the speech, the shots, the storyboard's sound or the synthesis
        code this production uses changed (sound.signature)."""
        if not any(p.get('take') for p in tl['paragraphs']):
            raise RuntimeError(f'{prod} [{vlang}]: no narration takes in the timeline — the sound would have no voice')
        sb = timeline.storyboard(prod)
        fp = _hash([{k: p.get(k) for k in ('id', 't0', 't1', 'take', 'cuts')} for p in tl['paragraphs']],
                   [(s['id'], s['t0'], s['t1'], s['set'], s.get('sfx')) for s in tl['shots']],
                   sb.get('sound'), tl['duration'], tl.get('fade_out'), sound.signature(sb, tl))  # code — only what is heard
        out = self.dist / 'media' / prod / f'sound-{vlang}.m4a'
        key = f'sound/{prod}/{vlang}'
        if self.state.get(key) != fp or not out.exists():
            wav = timeline.build_dir(prod) / f'sound-site-{vlang}.wav'
            self.log(f'♪ {prod} [{vlang}]: sound {tl["duration"] / 60:.1f} min…')
            sound.build(prod, tl, wav, log=lambda *a: None)
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(wav), '-ac', '1', '-c:a', 'aac', '-b:a', '96k',
                            '-movflags', '+faststart', str(out)], check=True)
        self.touch(out)
        self.new[key] = fp
        return f'sound-{vlang}.m4a?v={fp}', out.stat().st_size

    def poster(self, prod: str, orient: str, tag: str, tl: dict, shot: str, at: float) -> str | None:
        """A video poster: a storyboard shot without subtitles (captured by tools/capture.mjs) → poster-<orientation>.webp."""
        sh = next((s for s in tl['shots'] if s['id'] == shot), None)
        if not sh:
            self.log(f'⚠ {prod}: no shot {shot} for the poster')
            return None
        man = config.story_dir(prod) / 'assets' / 'assets.json'
        fp = _hash(sh, at, tl['width'], tl['height'], man.read_bytes() if man.exists() else b'')
        out = self.dist / 'media' / prod / f'poster-{orient}.webp'
        key = f'poster/{prod}/{orient}'
        if self.new.get(key) != fp and (self.state.get(key) != fp or not out.exists()):  # once per build (not per language)
            self.log(f'🖼 {prod}: poster {orient} ({shot})')
            cmd = ['node', str(config.ROOT / 'tools' / 'capture.mjs'), 'stills', prod, '--shots', shot, '--at', str(at),
                   '--scale', '0.5', '--no-subs'] + (['--tl', tag] if tag else [])
            r = subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True)
            jpg = config.OUT / prod / (f'{tag}-stills' if tag else 'stills') / f'{shot}.jpg'
            if r.returncode or not jpg.exists():
                self.log(f'⚠ poster {prod}/{orient} not captured: {r.stderr.strip()[-300:]}')
                return None
            out.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(jpg), '-c:v', 'libwebp', '-quality', '80', str(out)],
                           check=True)
        self.touch(out)
        self.new[key] = fp
        return f'poster-{orient}.webp?v={fp}'

    def video(self, prod: str, vlang: str, poster: list) -> dict | None:
        """A production's video in language vlang: the formats' timelines (vertical, horizontal), sound, posters."""
        fm = timeline.film(prod)
        L = vlang if vlang != fm['lang'] else None
        st = config.story(prod)
        out = {'formats': {}, 'lang': vlang}
        main_tl = None
        for fmt in [None, *(st.get('formats') or {})]:
            tl = timeline.build(prod, save=True, fmt=fmt, lang=L)
            if tl['errors']:
                self.log(f'⚠ {prod} {fmt or "main"} [{vlang}]: timeline errors — skipped: {tl["errors"][:3]}')
                continue
            if not tl['timing'] == 'voicing':
                self.log(f'⚠ {prod} [{vlang}]: not everything is narrated ({tl["timing"]}) — skipped')
                return None
            orient = 'horizontal' if tl['width'] > tl['height'] else 'vertical'
            for spec in tl['assets'].values():
                if spec.get('file'):
                    spec['file'] = self.webp(prod, spec['file'])
            # the browser doesn't need the narration takes — but tl stays whole: the sound is built from it (the voice — from take)
            web = {**tl, 'paragraphs': [{k: v for k, v in p.items() if k not in ('take', 'cuts')} for p in tl['paragraphs']]}
            data = json.dumps(web, ensure_ascii=False, separators=(',', ':'))
            f = self.dist / 'media' / prod / f'{orient}-{vlang}.json'
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(data, encoding='utf8')
            fp = _hash(data.encode())
            # the poster — from a storyboard shot, in the storyboard's language (posters have no subtitles)
            ptl = tl if not L else timeline.build(prod, save=True, fmt=fmt)
            pst = self.poster(prod, orient, timeline.tag(fmt), ptl, *poster) if poster else None
            out['formats'][orient] = {'timeline': f'{orient}-{vlang}.json?v={fp}', 'width': tl['width'],
                                      'height': tl['height'], 'poster': pst}
            if main_tl is None:
                main_tl = tl
            out['duration'] = tl['duration']
        if main_tl is None:
            return None
        out['audio'], out['audio_size'] = self.sound(prod, vlang, main_tl)
        return out

    # ---------------------------------------------------------------- the story's narration

    def narration(self, slug: str, lang: str, vid: str) -> dict | None:
        """The whole narration of a story → <lang>/<story>/audio/story.mp3 + story.json (marks for reading)."""
        try:
            v = voicing.settings(slug, vid)
        except KeyError:
            self.log(f'⚠ {slug}/{lang}: no narration {vid}')
            return None
        pl = voicing.plan(slug, vid)
        sig = [v['gaps']] + [[it['id'], it['status'], it['selected'], it['key'], it['text'], it['times']]
                             for s in pl['sections'] for it in s['items']]
        fp = _hash(sig)
        d = self.dist / lang / slug / 'audio'
        mp3, meta_f = d / 'story.mp3', d / 'story.json'
        key = f'narration/{slug}/{lang}'
        if self.state.get(key) == fp and mp3.exists() and meta_f.exists():
            meta = config.read_json(meta_f)
        else:
            sid = pl['sections'][0]['id']
            tr = voicing.section_track(slug, vid, sid)
            if tr is None:
                self.log(f'… {slug}/{lang}: not fully narrated — no audio')
                return None
            pcm, meta = tr
            st = config.story(slug)
            self.log(f'♪ {slug}/{lang}: narration {fmt_dur(meta["duration"], lang)} → mp3')
            audio.encode_mp3(pcm, mp3, title=st['title'].get(lang, slug), album=st['title'].get(lang, slug),
                             artist=st.get('author', {}).get(lang, ''), track='1')
            meta['size'] = mp3.stat().st_size
            meta['voice'] = {'model': v['model'], 'voice': v['voice']}
            config.write_json(meta_f, meta)
        self.touch(mp3, meta_f)
        self.new[key] = fp
        meta['v'] = fp
        return meta


# ---------------------------------------------------------------- the build

def _copy_assets(dist: Path) -> None:
    assets = dist / 'assets'
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(config.SITE, assets, ignore=shutil.ignore_patterns('*.py', '__pycache__', 'author.json'))
    h = hashlib.sha256()
    for f in sorted(config.SITE.rglob('*')):
        if f.is_file():
            h.update(f.name.encode() + f.read_bytes())
    V['assets'] = h.hexdigest()[:10]
    css = assets / 'site.css'
    css.write_text(css.read_text(encoding='utf8').replace('.woff2)', f".woff2?v={V['assets']})"), encoding='utf8')
    # the stage (stage/js + three.js): in a stamped folder — the modules import each other without ?v
    h = hashlib.sha256()
    for f in sorted([*(config.ROOT / 'stage' / 'js').rglob('*'), *(config.ROOT / 'stage' / 'vendor').rglob('*')]):
        if f.is_file():
            h.update(str(f).encode() + f.read_bytes())
    V['stage'] = h.hexdigest()[:10]
    sdir = assets / f'stage-{V["stage"]}'
    shutil.copytree(config.ROOT / 'stage' / 'js', sdir / 'js')
    shutil.copytree(config.ROOT / 'stage' / 'vendor', sdir / 'vendor')


def build(log=print) -> dict:
    cfg = {'langs': ['en', 'ru'], 'default_lang': 'en', 'stories': [], **config.site_config()}
    b = Build(cfg, log)
    b.dist.mkdir(exist_ok=True)
    _copy_assets(b.dist)
    author = config.read_json(config.ROOT / cfg.get('author', 'site/author.json'), {}) or {}
    videos_cache: dict = {}
    catalog = {lang: [] for lang in cfg['langs']}
    for item in cfg['stories']:
        slug = item['story']
        st = config.story(slug)
        for lang in cfg['langs']:
            vid = (item.get('voicings') or {}).get(lang)
            narr = b.narration(slug, lang, vid) if vid else None
            vids = []
            for v in item.get('videos') or []:
                prod = v['production']
                fm = timeline.film(prod)
                langs_ok = [fm['lang'], *[x for x in (fm.get('voicings') or {}) if x != fm['lang']]]
                def get(vl, prod=prod, v=v):
                    if (prod, vl) not in videos_cache:
                        videos_cache[(prod, vl)] = b.video(prod, vl, v.get('poster'))
                    return videos_cache[(prod, vl)]
                media = get(lang) if lang in langs_ok else None
                if media is None:  # no narration in the page's language — the video in the storyboard's language
                    media = get(fm['lang'])
                if media:
                    vids.append({**v, 'media': media, 'path': config.story(prod)['film'].get('style', prod)})
            catalog[lang].append({'slug': slug, 'story': st, 'item': item, 'narration': narr, 'videos': vids})
    for lang, items in catalog.items():
        write_landing(cfg, lang, author, items)
        for x in items:
            write_story(cfg, lang, author, x)
            if x['narration']:
                write_reader(cfg, lang, author, x)
            for v in x['videos']:
                write_watch(cfg, lang, author, x, v)
    (b.dist / 'index.html').write_text(_redirect(f'{cfg["default_lang"]}/'), encoding='utf8')
    # remove everything the build didn't write or confirm
    for top in [b.dist / x for x in cfg['langs']] + [b.dist / 'media']:
        if not top.exists():
            continue
        for f in sorted(top.rglob('*'), key=lambda x: -len(x.parts)):
            if f.is_file() and f.stat().st_mtime < b.started - 1:
                f.unlink()
            elif f.is_dir() and not any(f.iterdir()):
                f.rmdir()
    config.write_json(b.state_f, b.new)
    n = sum(len(x['videos']) for items in catalog.values() for x in items)
    log(f'site: {sum(len(v) for v in catalog.values())} story pages, {n} videos → {b.dist}')
    return {'stories': len(cfg['stories']), 'videos': n}


# ---------------------------------------------------------------- pages

def _title(x: dict, lang: str) -> str:
    return x['story']['title'].get(lang) or next(iter(x['story']['title'].values()))


def _poster_img(v: dict, up: str, cls: str = 'poster') -> str:
    """A video poster: vertical on a narrow/portrait screen, horizontal on a wide one."""
    f = v['media']['formats']
    base = f'{up}media/{v["production"]}/'
    vert, hor = (f.get('vertical') or {}).get('poster'), (f.get('horizontal') or {}).get('poster')
    if not (vert or hor):
        return ''
    src = base + (hor or vert)
    source = (f'<source media="(max-width: 700px), (orientation: portrait)" srcset="{base}{vert}">' if vert and hor else '')
    return f'<picture class="{cls}">{source}<img src="{src}" alt="" loading="lazy"></picture>'


def _video_card(lang: str, v: dict, href: str, up: str) -> str:
    """A video version card: the poster (16:9 on a wide screen, 9:16 on a narrow one), the style, about it, duration, formats."""
    u, m = _ui(lang), v['media']
    fmts = m['formats']
    alt = ' · '.join(f'<a href="{href}?o={o}">{e(u[o])}</a>' for o in ('vertical', 'horizontal') if o in fmts) if len(fmts) > 1 else ''
    note = '' if m['lang'] == lang else f' · {e(u["video_in"].format(lang=LANG_NAMES[lang][m["lang"]]))}'
    return f'''<li class="vcard">
  <a class="pic" href="{href}">{_poster_img(v, up)}<span class="play">{ICON_PLAY}</span></a>
  <h3><a href="{href}">{e((v.get('name') or {}).get(lang, v['path']))}</a></h3>
  <p>{e((v.get('about') or {}).get(lang, ''))}</p>
  <p class="vmeta">{fmt_dur(m['duration'], lang)}{' · ' + alt if alt else ''}{note}</p>
</li>'''


def write_landing(cfg: dict, lang: str, author: dict, items: list) -> None:
    """The showcase: story after story — the year and the title (no retelling: no spoilers), reading and audio, and right away
    all the video versions."""
    u = _ui(lang)
    blocks = []
    for x in items:
        slug, n = x['slug'], x['narration']
        acts = ''
        if n:
            acts = (f'<p class="acts"><a class="btn primary small" href="{slug}/read/">{ICON_BOOK}<span>{e(u["read"])}</span></a>'
                    f'<a class="btn ghost small" href="{slug}/audio/story.mp3?v={n["v"]}" download>{ICON_DL}<span>{e(u["mp3"])}</span></a>'
                    f'<span class="dur">{fmt_dur(n["duration"], lang)} · {e(u["narration"])}</span></p>')
        cards = ''.join(_video_card(lang, v, f'{slug}/{v["path"]}/', '../') for v in x['videos'])
        blocks.append(f'''<section class="show">
  <header class="show-head">
    <p class="year">{e(str(x['story'].get('year', '')))}</p>
    <h2><a href="{slug}/">{e(_title(x, lang))}</a></h2>
    {acts}
  </header>
  {f'<ul class="vgrid">{cards}</ul>' if cards else ''}
</section>''')
    body = f'''<main class="landing">
  <section class="hero">
    <p class="years">{e(author.get('years', ''))}</p>
    <h1>{e(author.get('name', {}).get(lang, ''))}</h1>
    <p class="lead">{e(author.get('lead', {}).get(lang, ''))} <a href="author/">{e(u['about'])} →</a></p>
  </section>
  {''.join(blocks)}
</main>'''
    out = config.DIST / lang / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cfg, lang, author.get('name', {}).get(lang, ''), body, depth=1, author=author), encoding='utf8')
    write_author(cfg, lang, author)


def write_author(cfg: dict, lang: str, author: dict) -> None:
    """About the author — a separate page."""
    u = _ui(lang)
    bio = ''.join(f'<p>{e(p)}</p>' for p in author.get('bio', {}).get(lang, []))
    body = f'''<main class="story author-page">
  <p class="back"><a href="../">← {e(u['stories'])}</a></p>
  <p class="year">{e(author.get('years', ''))}</p>
  <h1>{e(author.get('name', {}).get(lang, ''))}</h1>
  <div class="bio">{bio}</div>
</main>'''
    out = config.DIST / lang / 'author' / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cfg, lang, f'{u["about"]} — {author.get("name", {}).get(lang, "")}', body, depth=2,
                        path='author/', author=author), encoding='utf8')


def write_story(cfg: dict, lang: str, author: dict, x: dict) -> None:
    u = _ui(lang)
    title, slug = _title(x, lang), x['slug']
    n = x['narration']
    src_lang = x['story']['source']['lang']
    actions = ''
    if n:
        mb = n.get('size', 0) / 1e6
        actions = f'''<div class="actions">
    <a class="btn primary" href="read/">{ICON_BOOK}<span>{e(u['read'])}</span></a>
    <a class="btn ghost" href="audio/story.mp3?v={n['v']}" download="{e(author.get('name', {}).get(lang, ''))} — {e(title)}.mp3">{ICON_DL}<span>{e(u['download'])}</span></a>
  </div>
  <p class="note">{e(u['mp3'])} · {mb:.0f} {e(u['mb'])} · {fmt_dur(n['duration'], lang)} · {e(u['voice'])} {e(n.get('voice', {}).get('voice', ''))}</p>'''
    vids = [_video_card(lang, v, f'{v["path"]}/', '../../') for v in x['videos']]
    body = f'''<main class="story">
  <p class="back"><a href="../">← {e(author.get('name', {}).get(lang, ''))}</a></p>
  <p class="year">{e(str(x['story'].get('year', '')))}</p>
  <h1>{e(title)}</h1>
  {actions}
  <p class="note">{e(u['original'] if lang == src_lang else u['translated'])}</p>
  {f'<h2>{e(u["video"])}</h2><ul class="vgrid">{"".join(vids)}</ul><p class="note">{e(u["about_video"])}</p>' if vids else ''}
</main>'''
    out = config.DIST / lang / slug / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cfg, lang, f'{title} — {author.get("name", {}).get(lang, "")}', body, depth=2,
                        path=f'{slug}/', author=author), encoding='utf8')


def write_reader(cfg: dict, lang: str, author: dict, x: dict) -> None:
    """Reading with narration — the player: pages by screen height, sentence and word highlighting."""
    u = _ui(lang)
    n, slug = x['narration'], x['slug']
    title = _title(x, lang)
    paras = ''.join(f'<p id="{p["id"]}"{" class=it" if p.get("italic") else ""}>{e(p["text"])}</p>'
                    for p in n['paragraphs'])
    data = json.dumps({'id': 'story', 'book': slug, 'lang': lang, 'duration': n['duration'],
                       'audio': f'../audio/story.mp3?v={n["v"]}', 'next': None, 'nextId': None,
                       'title': title, 'bookTitle': title, 'author': author.get('name', {}).get(lang, ''),
                       'paragraphs': [{k: p[k] for k in ('id', 'kind', 't0', 't1', 'sentences', 'words')}
                                      for p in n['paragraphs']], 'ui': u},
                      ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    d = n['duration']
    body = f'''<div class="reader">
  <div class="bar"><a class="book-link" href="../">← {e(title)}</a></div>
  <div class="stage"><main class="page" id="page" tabindex="-1">{paras}</main></div>
  <div class="pager"><span></span><span class="pnum" id="pnum"></span><span></span></div>
  <div class="player" id="player">
    <button class="pp" id="pp" aria-label="{e(u['play'])}">▶</button>
    <div class="track"><span class="tm cur" id="cur">0:00</span>
      <input type="range" id="seek" min="0" max="{d:.1f}" step="0.1" value="0" aria-label="time">
      <span class="tm">{int(d // 60)}:{int(d % 60):02d}</span></div>
    <button class="sp" id="speed" title="{e(u['speed'])}">1×</button>
    <button class="fl" id="follow" hidden>{e(u['follow'])}</button>
    <button class="dl share" id="share" title="{e(u['share'])}" aria-label="{e(u['share'])}">↗</button>
    <a class="dl" href="../audio/story.mp3?v={n['v']}" download="{e(title)}.mp3" title="{e(u['download'])}" aria-label="{e(u['download'])}">{ICON_DL}</a>
  </div>
  <audio id="audio" src="../audio/story.mp3?v={n['v']}" preload="metadata"></audio>
</div>
<script type="application/json" id="data">{data}</script>
<script src="../../../assets/reader.js?v={V['assets']}"></script>'''
    out = config.DIST / lang / slug / 'read' / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cfg, lang, f'{title} — {author.get("name", {}).get(lang, "")}', body, depth=3,
                        path=f'{slug}/read/', body_class='reading', author=author), encoding='utf8')


def write_watch(cfg: dict, lang: str, author: dict, x: dict, v: dict) -> None:
    """Video in the browser: the scene (stage.js) draws shots by the timeline, time comes from the sound."""
    u = _ui(lang)
    m = v['media']
    title = _title(x, lang)
    name = (v.get('name') or {}).get(lang, v['path'])
    base = f'../../../media/{v["production"]}/'
    data = json.dumps({'lang': lang, 'title': title, 'name': name, 'author': author.get('name', {}).get(lang, ''),
                       'base': base, 'audio': base + m['audio'], 'duration': m['duration'],
                       'formats': {o: {**f, 'timeline': base + f['timeline'],
                                       'poster': base + f['poster'] if f.get('poster') else None}
                                   for o, f in m['formats'].items()},
                       'key': f'{x["slug"]}/{v["path"]}/{m["lang"]}', 'ui': u},
                      ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    stage_dir = f'../../../assets/stage-{V["stage"]}/'
    head = f'''<script type="importmap">{{"imports": {{"three": "{stage_dir}vendor/three/build/three.module.js"}}}}</script>'''
    body = f'''<div class="watch" id="watch">
  <div class="screen" id="screen">
    <div class="frame" id="frame"><img class="poster" id="poster" alt=""><button class="big-play" id="big" aria-label="{e(u['play'])}">{ICON_PLAY}</button>
      <p class="loading" id="loading" hidden>{e(u['loading'])} <span id="pct"></span></p></div>
  </div>
  <div class="controls" id="controls">
    <a class="back" href="../" title="{e(title)}">←</a>
    <button class="pp" id="pp" aria-label="{e(u['play'])}">▶</button>
    <span class="tm" id="cur">0:00</span>
    <input type="range" id="seek" min="0" max="{m['duration']:.1f}" step="0.1" value="0" aria-label="time">
    <span class="tm">{int(m['duration'] // 60)}:{int(m['duration'] % 60):02d}</span>
    <button class="cc on" id="cc" title="{e(u['subtitles'])}" aria-label="{e(u['subtitles'])}">CC</button>
    {f'<button class="or" id="or" title="{e(u["orientation"])}" aria-label="{e(u["orientation"])}">⇄</button>' if len(m['formats']) > 1 else ''}
    <button class="fs" id="fs" title="{e(u['fullscreen'])}" aria-label="{e(u['fullscreen'])}">⛶</button>
  </div>
  <p class="caption"><b>{e(title)}</b> · {e(name)} <span class="keys">{e(u['keys'])}</span></p>
  <audio id="audio" src="{base}{m['audio']}" preload="metadata"></audio>
</div>
<script type="application/json" id="data">{data}</script>
<script type="module">
import {{ Stage }} from '{stage_dir}js/stage.js';
window.Stage = Stage;
dispatchEvent(new Event('stage-ready'));
</script>
<script src="../../../assets/watch.js?v={V['assets']}"></script>'''
    out = config.DIST / lang / x['slug'] / v['path'] / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cfg, lang, f'{title} · {name} — {author.get("name", {}).get(lang, "")}', body, depth=3,
                        path=f'{x["slug"]}/{v["path"]}/', extra_head=head, body_class='watching', author=author),
                   encoding='utf8')


def _redirect(url: str) -> str:
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{url}"><title>…</title></head><body><a href="{url}">{url}</a></body></html>
'''
