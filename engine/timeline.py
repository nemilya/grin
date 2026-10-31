"""Таймлайн: раскадровка + время речи → stories/<slug>/build/timeline.json — всё, что нужно сцене (stage/).

Время речи: из озвучки (film.voicing, когда озвучены все абзацы — время каждого предложения и слова
по обратному распознаванию), иначе — оценка по темпу чтения (CHARS_PER_SEC, паузы между абзацами как в озвучке).
Поменялась озвучка — пересобрать таймлайн, раскадровка остаётся та же: кадры привязаны к предложениям, не к секундам.

Раскадровка (storyboard.json) пишется дельтами: состояние сцены (элементы, их карточки и места, текущая
декорация) переходит из кадра в кадр, кадр меняет только то, что указал. Здесь дельты разворачиваются:
у каждого кадра в таймлайне — полный список видимых элементов, камера (откуда → куда), фокус, свет.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from . import config, pricing, prepare, voicing

CUT_LEAD = 0.25       # с: склейка чуть раньше начала фразы — как монтирует монтажёр
PARA_GAP = 0.8        # с: пауза между абзацами при оценке (как gaps.paragraph в озвучке)
SUB_MAX_CHARS = 64    # знаков в субтитре (две строки по ~32 в вертикальном кадре)
SUB_MIN_DUR = 1.1
PERSIST = ('card', 'pos', 'rot', 'h', 'fx', 'glow', 'parts', 'hidden', 'shadow_only', 'k', 'color', 'size', 'box', 'set')
CUE_RE = re.compile(r'^(?P<p>\d{3})\.(?P<s>\d+)(?:\+(?P<f>0?\.\d+|0|1(?:\.0+)?))?(?:-(?P<b>\d+(?:\.\d+)?))?$')
BUILTIN = {'prop/glow': {'kind': 'procedural', 'draw': 'glow', 'h': 1, 'aspect': 1}}


def build_dir(slug: str) -> Path:
    return config.story_dir(slug) / 'build'


SUBS = {  # раскладка субтитров по ориентации кадра: y — центр блока (доля высоты), width — доля ширины, size — кегль
    'portrait': {'y': 0.735, 'width': 0.82, 'size': 0.0285, 'max_chars': 64},
    'landscape': {'y': 0.885, 'width': 0.72, 'size': 0.046, 'max_chars': 84},
}


def film(slug: str, fmt: str | None = None, lang: str | None = None) -> dict:
    """Параметры ролика: story.json → film, поверх — formats.<fmt> (горизонталь и т. п.);
    lang — другой язык ролика: голос и субтитры этого языка (film.voicings.<lang>), раскадровка та же."""
    st = config.story(slug)
    f = dict(st.get('film', {}))
    f.setdefault('lang', st['source']['lang'])
    f['storyboard_lang'] = f['lang']  # язык, на предложения которого ссылаются реплики раскадровки
    if fmt:
        if fmt not in (st.get('formats') or {}):
            raise KeyError(f'нет формата {fmt} в story.json → formats')
        f.update(st['formats'][fmt])
    if lang and lang != f['lang']:
        vid = (f.get('voicings') or {}).get(lang)
        if not vid:
            raise KeyError(f'нет озвучки {lang}: story.json → film.voicings.{lang}')
        f.update(lang=lang, voicing=vid)
    orient = 'landscape' if f.get('width', 1080) > f.get('height', 1920) else 'portrait'
    f['subtitles'] = {**SUBS[orient], **(f.get('subtitles') or {})}
    f['orientation'] = orient
    return f


def storyboard(slug: str, fmt: str | None = None) -> dict:
    """Раскадровка формата. Своя раскадровка формата может наследовать основную (\"extends\") и менять:
    cams / lights (по ключам), shots — правки кадров по id (cast — по элементам; null — убрать ключ),
    drop — убрать кадры, add — новые кадры ({"after": id, …кадр})."""
    sdir = config.story_dir(slug)
    name = film(slug, fmt).get('storyboard', 'storyboard.json') if fmt else 'storyboard.json'
    sb = config.read_json(sdir / name, {}) or {}
    if not sb.get('extends'):
        return sb
    base = copy.deepcopy(config.read_json(sdir / sb['extends'], {}) or {})
    for k in ('cams', 'lights'):
        base.setdefault(k, {}).update(sb.get(k) or {})
    for k in ('preroll', 'tail'):
        if k in sb:
            base[k] = sb[k]
    drop = set(sb.get('drop') or [])
    patches = sb.get('shots') or {}
    adds = {}
    for a in sb.get('add') or []:
        adds.setdefault(a['after'], []).append({k: v for k, v in a.items() if k != 'after'})
    for sc in base.get('scenes', []):
        shots = []
        for sh in sc['shots']:
            if sh['id'] not in drop:
                p = patches.get(sh['id']) or {}
                for k, v in p.items():
                    if k == 'cast' and v is not None:
                        sh['cast'] = {**(sh.get('cast') or {}), **v}
                    elif v is None:
                        sh.pop(k, None)
                    else:
                        sh[k] = v
                shots.append(sh)
            shots += adds.get(sh['id'], [])
        sc['shots'] = shots
    base['format_overlay'] = name
    return base


def bible(slug: str) -> dict:
    return config.read_json(config.story_dir(slug) / 'bible.json', {}) or {}


# ---------------------------------------------------------------- время речи

def speech_times(slug: str, holds: dict | None = None, lang: str | None = None) -> tuple[dict, str]:
    """{id абзаца: {t0, t1, text, sentences: [[a, b, t0, t1]], words: [[a, b, t0, t1]], take?, cuts?}}, источник.
    Время — от начала речи (без preroll). Озвученный абзац (актуальный дубль в film.voicing) — по дублю:
    длительность и время слов из обратного распознавания; остальные — оценка по темпу. Так раскадровку можно
    смотреть и до озвучки, и с частью озвученных абзацев.
    holds — тишина, с. «018»: после абзаца 18; «018.3»: после его предложения 3 — дубль режется между
    предложениями, cuts: [[с от начала дубля, пауза]] (звук вставляет тишину).
    lang — язык ролика (по умолчанию film.lang); паузы, заданные по предложениям языка раскадровки,
    переносятся на ближайший промежуток между предложениями этого языка."""
    fm = film(slug, lang=lang)
    lang, vid = fm['lang'], fm.get('voicing')
    prep = prepare.load(slug, lang)
    if not prep:
        raise RuntimeError(f'нет prepared/{lang}.json: сначала make prepare / перевод')
    holds = _map_holds(holds or {}, slug, fm['storyboard_lang'], lang, prep)
    film_ = fm
    voiced = {}
    if vid and (config.text_dir(slug) / 'voicings' / vid / 'voicing.json').exists():
        for sec in voicing.plan(slug, vid)['sections']:
            for it in sec['items']:
                if it['status'] in ('ok', 'warn', 'approved') and it['times']:
                    take = next(t for t in it['takes'] if t['n'] == it['selected'])
                    voiced[it['id']] = (take, it['times'])
    cps = pricing.CHARS_PER_SEC.get(lang, 14.0)
    out, t = {}, 0.0
    for s in prep['sections']:
        for p in s['paragraphs']:
            if p['kind'] == 'heading' and not film_.get('speak_title'):
                continue
            if p['id'] in voiced:
                take, wt = voiced[p['id']]
                dur = take['dur']
                words = [[a, b, round(t + x, 3), round(t + y, 3)] for (a, b), (x, y) in zip(p['words'], wt)]
                sents = []
                for a, b in p['sentences']:
                    ws = [w for w in words if w[0] >= a and w[1] <= b]
                    sents.append([a, b, ws[0][2] if ws else t, ws[-1][3] if ws else t + dur])
                out[p['id']] = {'t0': t, 't1': t + dur, 'text': p['text'], 'sentences': sents, 'words': words,
                                'take': f"voicings/{vid}/takes/{take['url'].rsplit('/', 1)[-1]}" if take.get('url') else take.get('file')}
            else:
                n = max(len(p['text']), 1)
                dur = n / cps
                tt = lambda a, t0=t, d=dur: round(t0 + a / n * d, 3)  # noqa: E731
                out[p['id']] = {'t0': t, 't1': t + dur, 'text': p['text'],
                                'sentences': [[a, b, tt(a), tt(b)] for a, b in p['sentences']],
                                'words': [[a, b, tt(a), tt(b)] for a, b in p['words']]}
            num = p['id'].rsplit('-', 1)[-1]
            cuts = []
            for k in range(len(p['sentences']) - 1):
                h = float(holds.get(f'{num}.{k}', 0))
                if h <= 0:
                    continue
                rec = out[p['id']]
                a_end, b_start = rec['sentences'][k][3], rec['sentences'][k + 1][2]
                at = (a_end + b_start) / 2                      # середина промежутка между предложениями
                cuts.append([round(at - rec['t0'], 3), h])
                for lst in (rec['sentences'], rec['words']):
                    for x in lst:
                        if x[2] >= at:
                            x[2], x[3] = round(x[2] + h, 3), round(x[3] + h, 3)
                rec['t1'] += h
                dur += h
            if cuts:
                out[p['id']]['cuts'] = cuts
            t += dur + PARA_GAP + float(holds.get(num, 0))
    n_v = sum(1 for p in out if p in voiced)
    return out, ('voicing' if n_v == len(out) else f'voicing {n_v}/{len(out)} + estimate' if n_v else 'estimate')


def _paras(prep: dict) -> dict:
    return {p['id']: p for s in prep['sections'] for p in s['paragraphs']}


def _map_holds(holds: dict, slug: str, src_lang: str, lang: str, prep: dict) -> dict:
    """Паузы «018.16» (после предложения языка раскадровки) → предложение языка ролика с ближайшим концом
    по доле текста абзаца. Паузы после абзаца («018») — как есть."""
    if not holds or lang == src_lang:
        return holds
    src = _paras(prepare.load(slug, src_lang) or {'sections': []})
    dst = _paras(prep)
    out = {}
    for k, v in holds.items():
        num, _, sent = k.partition('.')
        pid = f'story-{num}'
        if not sent or pid not in src or pid not in dst:
            out[k] = v
            continue
        sp, dp = src[pid], dst[pid]
        x = sp['sentences'][int(sent)][1] / max(1, len(sp['text']))
        ends = [b / max(1, len(dp['text'])) for _, b in dp['sentences'][:-1]]
        if ends:
            out[f'{num}.{min(range(len(ends)), key=lambda j: abs(ends[j] - x))}'] = v
    return out


def _time_at(para: dict, x: float) -> float:
    """Время в абзаце (по словам) в точке x — доля длины его текста."""
    c = x * len(para['text'])
    prev = None
    for a, b, t0, t1 in para['words']:
        if a >= c:
            if prev is None:
                return t0
            pa, pb, p0, p1 = prev  # между словами — по доле промежутка
            return p1 + (t0 - p1) * min(1.0, max(0.0, (c - pb) / max(1, a - pb)))
        if b > c:
            return t0 + (t1 - t0) * (c - a) / max(1, b - a)
        prev = (a, b, t0, t1)
    return prev[3] if prev else para['t1']  # после последнего слова — его конец (дальше в дубле тишина)


def cue_time(cue: str, times: dict, src: dict | None = None) -> float:
    """«018.13+0.4» → секунды от начала речи; «start» → 0; «002.0-4» — за 4 с до реплики (интертитр в паузе).
    src — абзацы языка раскадровки, если ролик на другом языке: место реплики — по доле текста абзаца."""
    if cue == 'start':
        return 0.0
    m = CUE_RE.match(cue or '')
    if not m:
        raise ValueError(f'реплика «{cue}»: нужен вид 018.13, 018.13+0.4 или 018.13-4')
    pid = f"story-{m.group('p')}"
    para = times.get(pid)
    if para is None:
        raise ValueError(f'реплика «{cue}»: нет абзаца {pid}')
    k = int(m.group('s'))
    f = float(m.group('f') or 0)
    back = float(m.group('b') or 0)
    if src and pid in src and src[pid]['text'] != para['text']:
        sp = src[pid]
        if k >= len(sp['sentences']):
            raise ValueError(f'реплика «{cue}»: в {pid} предложений {len(sp["sentences"])}')
        a, b = sp['sentences'][k]
        n = max(1, len(sp['text']))
        t0, t1 = _time_at(para, a / n), _time_at(para, b / n)
        return t0 + f * (t1 - t0) - (CUT_LEAD if not f else 0) - back
    if k >= len(para['sentences']):
        raise ValueError(f'реплика «{cue}»: в {pid} предложений {len(para["sentences"])}')
    _, _, t0, t1 = para['sentences'][k]
    return t0 + f * (t1 - t0) - (CUT_LEAD if not f else 0) - back


# ---------------------------------------------------------------- ассеты

def asset_spec(b: dict, key: str, story_dir: Path) -> dict:
    """Ключ карточки → описание для сцены: вид, размер, цвет заглушки, файл (если сгенерирован), шарниры."""
    if key in BUILTIN:
        spec = dict(BUILTIN[key])
    else:
        head, _, tail = key.partition('/')
        spec = None
        if head == 'prop':
            spec = dict((b.get('props') or {}).get(tail) or {})
        elif head in (b.get('characters') or {}):
            ch = b['characters'][head]
            poses = ch.get('poses') or {}
            if tail in poses:
                spec = {k: v for k, v in poses[tail].items() if k != 'desc'}
                if 'parts' in spec:
                    spec['parts'] = {n: {k: v for k, v in pt.items() if k != 'desc'} | {'card': f'{head}/{n}'}
                                     for n, pt in spec['parts'].items()}
            else:  # часть шарнирной куклы
                for pose in poses.values():
                    if tail in (pose.get('parts') or {}):
                        spec = {k: v for k, v in pose['parts'][tail].items() if k not in ('desc', 'attach')}
                        break
            if spec is not None:
                spec.setdefault('color', ch.get('color'))
                spec['label'] = f"{ch.get('name', head)} · {tail}"
        elif head in (b.get('sets') or {}):
            spec = {k: v for k, v in (b['sets'][head]['pieces'].get(tail) or {}).items() if k not in ('desc', 'pos', 'rot')}
        if not spec:
            raise KeyError(f'нет ассета {key} в библии')
    spec.setdefault('kind', 'cutout')
    spec.setdefault('label', key)
    got = ((config.read_json(story_dir / 'assets' / 'assets.json', {}) or {}).get('items') or {}).get(key)
    if got and (story_dir / 'assets' / got['file']).exists():
        spec['file'] = f"assets/{got['file']}"
    return spec


# ---------------------------------------------------------------- разворачивание раскадровки

def _ease_last(v):
    """Значение шарнира: число или ключевые кадры [[доля, градусы], …] → последнее."""
    return v[-1][1] if isinstance(v, list) else v


def _settle(el: dict) -> dict:
    """Конец кадра → начальное состояние следующего: движения доехали, переходы закончились."""
    el = dict(el)
    mv = el.pop('move', None)
    if mv:
        if mv.get('keys'):
            el['pos'] = mv['keys'][-1][1]
        if 'to' in mv:
            el['pos'] = mv['to']
        if 'rot_to' in mv:
            el['rot'] = mv['rot_to']
    fall = el.pop('fall', None)
    if fall:  # лист упал — лежит, где упал
        el['pos'] = fall.get('to', el.get('pos'))
        if 'rot_to' in fall:
            el['rot'] = fall['rot_to']
    el.pop('grow', None)  # линия дорисована
    if 'k_to' in el:
        el['k'] = el.pop('k_to')
    el.pop('ramp', None)
    el.pop('swap_at', None)
    el.pop('card_prev', None)
    if el.get('parts'):
        el['parts'] = {n: _ease_last(v) for n, v in el['parts'].items()}
    if el.get('glow'):
        el['glow'] = {k: v for k, v in el['glow'].items() if k != 'start'}
    return el


def _piece_id(b: dict, set_id: str, key: str) -> str | None:
    return f'{set_id}:{key}' if key in ((b.get('sets') or {}).get(set_id, {}).get('pieces') or {}) else None


def _ensure_set(state: dict, b: dict, set_id: str) -> None:
    """Куски декорации — элементы состояния «<декорация>:<кусок>» (один раз, дальше их меняет раскадровка)."""
    for name, pc in ((b.get('sets') or {}).get(set_id, {}).get('pieces') or {}).items():
        pid = f'{set_id}:{name}'
        if pid not in state:
            state[pid] = {'card': pc.get('card', f'{set_id}/{name}'), 'pos': pc.get('pos', [0, 0, 0]), 'rot': pc.get('rot', [0, 0, 0]),
                          'set': set_id, 'piece': True}


def _apply(state: dict, b: dict, set_id: str, delta: dict | None, where: str, errors: list) -> None:
    for key, val in (delta or {}).items():
        eid = _piece_id(b, set_id, key) or key
        if val is None:
            state.pop(eid, None)
            continue
        cur = dict(state.get(eid) or {})
        if val.get('reset') and cur.get('piece'):  # кусок декорации — на место из библии
            pc = b['sets'][set_id]['pieces'][key]
            state[eid] = {'card': cur['card'], 'pos': pc.get('pos', [0, 0, 0]), 'rot': pc.get('rot', [0, 0, 0]), 'set': set_id, 'piece': True}
            continue
        if not cur and 'card' not in val:
            errors.append(f'{where}: элемент «{key}» появляется без card')
            continue
        if 'card' in val and cur.get('card') and val['card'] != cur['card'] and 'swap_at' in val:
            cur['card_prev'] = cur['card']
        if 'parts' in val and val['parts'] is not None:
            cur['parts'] = {**(cur.get('parts') or {}), **val['parts']}
            val = {k: v for k, v in val.items() if k != 'parts'}
        cur.update(val)
        if 'parts' in val and val['parts'] is None:
            cur.pop('parts', None)
        if not cur.get('piece') and ('pos' in val or 'set' not in cur):
            cur['set'] = set_id
        state[eid] = cur


def _cam(sb: dict, shot: dict, prev: dict | None, where: str, errors: list, cont: bool = False) -> dict:
    """cont — продолжить с места, где камера закончила прошлый план (та же камера, без перехода): без скачка назад."""
    base = shot.get('cam')
    if (base is None or cont) and prev:
        c = {'pos': prev['to']['pos'], 'look': prev['to']['look'], 'fov': prev['to']['fov']}
    else:
        c = copy.deepcopy((sb.get('cams') or {}).get(base) or {})
        if not c:
            errors.append(f'{where}: нет камеры «{base}»')
            c = {'pos': [0, 15, 60], 'look': [0, 10, 0], 'fov': 34}
    c.setdefault('fov', 34)
    to = copy.deepcopy(c)
    if shot.get('cam_to'):  # переезд: от камеры cam к камере cam_to за кадр
        to = copy.deepcopy((sb.get('cams') or {}).get(shot['cam_to']) or {})
        if not to:
            errors.append(f"{where}: нет камеры «{shot['cam_to']}»")
            to = copy.deepcopy(c)
        to.setdefault('fov', c['fov'])
    push = float(shot.get('push', 0))
    if push:
        d = [b - a for a, b in zip(c['pos'], c['look'])]
        n = sum(x * x for x in d) ** 0.5 or 1
        to['pos'] = [round(a + x / n * push, 3) for a, x in zip(c['pos'], d)]
    if shot.get('drift'):
        to['pos'] = [a + x for a, x in zip(to['pos'], shot['drift'])]
        to['look'] = [a + x for a, x in zip(to['look'], shot['drift'])]
    if 'fov_to' in shot:
        to['fov'] = shot['fov_to']
    return {'name': base or (prev or {}).get('name'), 'from': {k: c[k] for k in ('pos', 'look', 'fov')}, 'to': {k: to[k] for k in ('pos', 'look', 'fov')},
            'ease': shot.get('ease', 'inOut'), 'hand': shot.get('hand', 1.0)}


def _smooth_chains(shots: list) -> None:
    """Цепочка планов, где камера продолжает движение (cam_continue): на стыках не тормозить — разгон только в начале
    цепочки, торможение — в конце (ease in / out / linear вместо inOut у каждого плана)."""
    moving = lambda c: any(abs(a - b) > 1e-3 for k in ('pos', 'look') for a, b in zip(c['from'][k], c['to'][k]))  # noqa: E731
    for i, s in enumerate(shots):
        c = s['camera']
        if c.get('ease', 'inOut') != 'inOut' or not moving(c):
            continue
        start = c.get('cont') and moving(shots[i - 1]['camera'])                     # въезжает на ходу
        nxt = shots[i + 1]['camera'] if i + 1 < len(shots) else None
        end = bool(nxt and nxt.get('cont') and moving(nxt))                          # уезжает на ходу
        c['ease'] = {(True, True): 'linear', (True, False): 'out', (False, True): 'in'}.get((start, end), 'inOut')


def _light(sb: dict, b: dict, set_id: str, shot: dict, where: str, errors: list) -> dict:
    ov = shot.get('light') or {}
    name = ov.get('preset') or (b.get('sets') or {}).get(set_id, {}).get('light') or 'lamp'
    preset = copy.deepcopy((sb.get('lights') or {}).get(name))
    if preset is None:
        errors.append(f'{where}: нет света «{name}»')
        preset = copy.deepcopy(next(iter((sb.get('lights') or {'x': {}}).values())))
    return {'preset': name, **preset, **{k: v for k, v in ov.items() if k != 'preset'}}


def subtitles(times: dict, offset: float, max_chars: int = SUB_MAX_CHARS) -> list[dict]:
    """Субтитры из слов со временем: не длиннее max_chars, рвём по концу предложения и по знакам."""
    subs = []
    for pid, p in times.items():
        text, words = p['text'], p['words']
        sent_ends = {b for _, b, _, _ in p['sentences']}
        cur: list = []

        def flush():
            if not cur:
                return
            a, b = cur[0][0], cur[-1][1]
            while b < len(text) and not text[b].isspace():  # знаки и кавычки после слова
                b += 1
            subs.append({'t0': round(cur[0][2] + offset, 3), 't1': round(cur[-1][3] + offset, 3),
                         'text': text[a:b].strip(), 'p': pid})
            cur.clear()

        for i, w in enumerate(words):
            a, b = w[0], w[1]
            if cur and (b - cur[0][0]) > max_chars:
                flush()
            cur.append(w)
            tail = text[b:words[i + 1][0]] if i + 1 < len(words) else text[b:]
            size = b - cur[0][0]
            if any(e <= len(text) and b <= e <= b + len(tail) for e in sent_ends) and size > 18:
                flush()
            elif re.search(r'[,;:—…]', tail) and size > max_chars * 0.62:
                flush()
        flush()
    for i, s in enumerate(subs):  # держать до следующего, но не больше 0.6 с после конца речи
        nxt = subs[i + 1]['t0'] if i + 1 < len(subs) else s['t1'] + 1.5
        s['t1'] = round(min(max(s['t1'] + 0.35, s['t0'] + SUB_MIN_DUR), nxt - 0.04, s['t1'] + 0.6) if nxt > s['t0'] else s['t1'], 3)
    return subs


def tag(fmt: str | None = None, name: str | None = None, lang: str | None = None) -> str:
    """Имя сборки: '' (основной формат целиком), 'demo', 'horizontal', 'horizontal-demo', 'ru', 'horizontal-ru-demo'."""
    return '-'.join(x for x in (fmt, lang, name) if x)


def build(slug: str, *, save: bool = True, start: str | None = None, end: str | None = None, name: str | None = None,
          fmt: str | None = None, lang: str | None = None) -> dict:
    sdir = config.story_dir(slug)
    fm = film(slug, fmt, lang)
    lang = fm['lang'] if fm['lang'] != fm['storyboard_lang'] else None  # другой язык ролика (сборка «-ru»)
    sb, b = storyboard(slug, fmt), bible(slug)
    times, source = speech_times(slug, sb.get('holds'), fm['lang'])
    src = _paras(prepare.load(slug, fm['storyboard_lang']) or {'sections': []}) if lang else None
    pre = float(sb.get('preroll', 2.0))
    speech_end = max(p['t1'] for p in times.values()) + pre
    errors: list[str] = []
    director = config.read_json(config.DIRECTORS / f"{sb['director']}.json", {}) if sb.get('director') else {}
    if sb.get('director') and not director:
        errors.append(f"нет режиссёра directors/{sb['director']}.json")
    state: dict = {}
    shots, cues, assets = [], [], {}
    set_id = None
    prev_cam = None
    for sc in sb.get('scenes', []):
        set_id = sc.get('set') or set_id
        _ensure_set(state, b, set_id)
        _apply(state, b, set_id, sc.get('cast'), sc['id'], errors)
        for sh in sc.get('shots', []):
            sh = {**(director.get('defaults') or {}), **sh}  # умолчания режиссёра (штатив, ход камеры…)
            where = f"{sc['id']}/{sh.get('id')}"
            try:
                t0 = round(cue_time(sh['at'], times, src) + (pre if sh['at'] != 'start' else 0), 3)
            except (ValueError, KeyError) as e:
                errors.append(f'{where}: {e}')
                continue
            if sh.get('set'):
                set_id = sh['set']
                if set_id not in (b.get('sets') or {}):
                    errors.append(f'{where}: нет декорации «{set_id}»')
                _ensure_set(state, b, set_id)
            state = {k: _settle(v) for k, v in state.items()}
            _apply(state, b, set_id, sh.get('cast'), where, errors)
            els = []
            for eid, el in state.items():
                if el.get('set') != set_id or el.get('hidden'):
                    continue
                for key in filter(None, (el.get('card'), el.get('card_prev'))):
                    if key not in assets:
                        try:
                            assets[key] = asset_spec(b, key, sdir)
                        except KeyError as e:
                            errors.append(f'{where}: {e}')
                            assets[key] = {'kind': 'cutout', 'h': 10, 'aspect': 1, 'label': key, 'missing': True}
                    for part in (assets[key].get('parts') or {}).values():
                        if part['card'] not in assets:
                            assets[part['card']] = asset_spec(b, part['card'], sdir)
                els.append({'id': eid, **{k: v for k, v in el.items() if k != 'set'}})
            cont = bool(sb.get('cam_continue') and prev_cam and shots and sh.get('cam') == prev_cam['name']
                        and shots[-1]['set'] == set_id and sh.get('in', 'cut') == 'cut' and not sh.get('cam_to'))
            cam = _cam(sb, sh, prev_cam, where, errors, cont)
            if cont:  # только у продолжений: описание кадра других постановок (отпечатки постеров) не меняется
                cam['cont'] = True
            prev_cam = cam
            shots.append({'id': sh.get('id'), 'scene': sc['id'], 'scene_title': sc.get('title', ''), 'at': sh['at'], 't0': t0, 'set': set_id,
                          'in': sh.get('in', 'cut'), 'camera': cam, 'focus': sh.get('focus') or {},
                          'light': _light(sb, b, set_id, sh, where, errors), 'elements': els,
                          'end': sh.get('end'), 'sfx': sh.get('sfx') or [], 'note': sh.get('note', ''),
                          **({'iris': sh['iris']} if sh.get('iris') else {})})
            cues.append((t0, where))
    _smooth_chains(shots)
    for (a, wa), (bb, wb) in zip(cues, cues[1:]):
        if bb <= a:
            errors.append(f'{wb}: начинается не позже {wa} ({bb:.2f} ≤ {a:.2f} с)')
    duration = round(speech_end + float(sb.get('tail', 4)), 3)
    for i, s in enumerate(shots):
        s['t1'] = shots[i + 1]['t0'] if i + 1 < len(shots) else duration
    _title_texts(assets, slug, fm['lang'])
    style = config.read_json(config.STYLES / f"{fm.get('style', 'paper-theatre')}.json", {}) or {}
    for spec in assets.values():  # слои стиля: мягкий край, без тени (кино) — у вырезок
        if spec.get('kind') == 'cutout':
            for k, v in (style.get('layers') or {}).items():
                spec.setdefault(k, v)
    warnings = []
    if director.get('min_shot'):
        warnings += [f"{s['id']}: план {s['t1'] - s['t0']:.1f} с — короче {director['min_shot']} с ({sb['director']})"
                     for s in shots if s['t1'] - s['t0'] < director['min_shot']]
    paras = [{'id': pid, 't0': round(p['t0'] + pre, 3), 't1': round(p['t1'] + pre, 3), **({'take': p['take']} if p.get('take') else {}),
              **({'cuts': p['cuts']} if p.get('cuts') else {})} for pid, p in times.items()]
    out = {'story': slug, 'format': fmt or 'main', 'lang': fm.get('lang'), 'timing': source, 'paragraphs': paras,
           'width': fm.get('width', 1080), 'height': fm.get('height', 1920), 'fps': fm.get('fps', 24),
           'duration': duration, 'preroll': pre, 'speech_end': round(speech_end, 3),
           'stage': style.get('stage', {}), 'subtitle_style': fm['subtitles'], 'assets': assets, 'shots': shots,
           'subtitles': [x for x in subtitles(times, pre, fm['subtitles']['max_chars'])
                         if x['p'].rsplit('-', 1)[-1] not in set(sb.get('no_subtitles') or [])], 'errors': errors,
           **({'fade_out': float(sb['fade_out'])} if sb.get('fade_out') else {}),
           **({'warnings': warnings} if warnings else {})}
    if start == 'demo':  # демо-отрезок раскадровки (demo_start), по умолчанию — финал
        start = sb.get('demo_start', 's12a')
    if start or end:
        out = cut(out, start, end)
    if save:
        t = tag(fmt, name, lang)
        config.write_json(build_dir(slug) / (f'timeline-{t}.json' if t else 'timeline.json'), out)
    return out


ATTR_RE = re.compile(r'\s(?=(?:[A-ZА-ЯЁ]\.\s?)+(?:[A-ZА-ЯЁ][\w-]+\s?)+[.,]\s)')


def _title_texts(assets: dict, slug: str, lang: str) -> None:
    """Интертитры (draw: title) — текст на языке ролика: para — абзац (эпиграф: подпись «Ф. Купер. …» — отдельно),
    story_title — автор и название из story.json."""
    paras = None
    st = config.story(slug)
    for spec in assets.values():
        if spec.get('draw') != 'title':
            continue
        if spec.get('story_title'):
            spec['lines'] = [(st.get('author') or {}).get(lang, ''), (st.get('title') or {}).get(lang, '')]
        elif spec.get('para'):
            if paras is None:
                paras = _paras(prepare.load(slug, lang) or {'sections': []})
            t = (paras.get(f"story-{spec['para']}") or {}).get('text', '')
            parts = ATTR_RE.split(t, maxsplit=1) if spec.get('attr') else [t]
            spec['text'] = parts[0].strip()
            if len(parts) > 1:
                spec['attr'] = parts[1].strip()


def chapters(tl: dict, min_len: float = 10.0) -> list[tuple[float, str]]:
    """Главы для YouTube по сценам: первая — с 0:00, короче min_len — сливаются с предыдущей."""
    out: list[list] = []
    for s in tl['shots']:
        if not out or out[-1][2] != s['scene']:
            out.append([s['t0'], s.get('scene_title') or s['scene'], s['scene']])
    if out:
        out[0][0] = 0.0
    merged: list[list] = []
    for i, c in enumerate(out):
        nxt = out[i + 1][0] if i + 1 < len(out) else tl['duration']
        if merged and nxt - c[0] < min_len:
            continue
        merged.append(c)
    return [(c[0], c[1]) for c in merged]


def srt(tl: dict) -> str:
    def ts(t):
        ms = int(round(t * 1000))
        return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'
    return '\n'.join(f"{i}\n{ts(s['t0'])} --> {ts(s['t1'])}\n{s['text']}\n" for i, s in enumerate(tl['subtitles'], 1))


def cut(tl: dict, start: str | None, end: str | None, lead: float = 1.2) -> dict:
    """Отрезок таймлайна: от кадра start до кадра end (не включая), время — с нуля (затемнение в начале)."""
    ids = [s['id'] for s in tl['shots']]
    i = ids.index(start) if start else 0
    j = ids.index(end) if end else len(ids)
    shots = copy.deepcopy(tl['shots'][i:j])
    off = shots[0]['t0'] - lead
    t_end = (tl['shots'][j]['t0'] if j < len(ids) else tl['duration']) - off
    for s in shots:
        s['t0'] = round(max(0.0, s['t0'] - off), 3)
        s['t1'] = round(s['t1'] - off, 3)
    shots[0]['t0'] = 0.0
    shots[0]['in'] = 'fade'
    sh = lambda xs: [{**x, 't0': round(x['t0'] - off, 3), 't1': round(x['t1'] - off, 3)} for x in xs if x['t1'] > off and x['t0'] - off < t_end]  # noqa: E731
    return {**tl, 'shots': shots, 'duration': round(t_end, 3), 'subtitles': sh(tl['subtitles']),
            'paragraphs': sh(tl['paragraphs']), 'cut': {'start': start, 'end': end, 'offset': round(off, 3)}}
