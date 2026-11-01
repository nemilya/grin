"""Narration — the harness: settings (model, voice, manner) + the paragraphs of the chosen sections → takes.

stories/<story>/voicings/<id>/
    voicing.json        settings
    items/<paragraph>.json  a paragraph's takes: word timings, transcript, score, cost; the selected one, approved
    takes/<paragraph>-<n>.opus  the takes' audio

A paragraph is narrated whole (one intonation); a very long one in pieces at sentence boundaries
(no longer than max_chars), joined with a short pause. Every piece is transcribed back:
skips and cut-offs → synthesize again (up to verify.retries times). The transcribed words give the time of every
word and sentence (align.py) for highlighting on the site.

Paragraph status: pending — no take for the current text and settings; stale — there is a take, but the text or
settings changed; warn — a take with a low score; ok; approved — approved.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
import threading
import time
from pathlib import Path

from . import align, audio, config, openrouter, prepare, pricing, text

DEFAULTS = {
    'name': '',
    'lang': 'ru',
    'model': pricing.DEFAULT_MODEL,
    'voice': 'Charon',
    'instructions': '',
    'speed': 1.0,
    'tempo': 1.0,
    'max_chars': 2500,
    'gaps': {'heading': 1.4, 'paragraph': 0.8, 'chunk': 0.3},
    'verify': {'enabled': True, 'model': pricing.DEFAULT_VERIFY_MODEL, 'min_score': 0.85, 'retries': 3},
    'sections': [],
    'mode': 'single',  # single — one voice; roles — voice tracks per role (later, see README)
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def vdir(slug: str, vid: str) -> Path:
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', vid or ''):
        raise KeyError(f'no narration {vid}')
    return config.text_dir(slug) / 'voicings' / vid


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in (patch or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def settings(slug: str, vid: str) -> dict:
    v = config.read_json(vdir(slug, vid) / 'voicing.json')
    if v is None:
        raise KeyError(f'no narration {vid}')
    v = _merge(DEFAULTS, v)
    v['id'] = vid
    v['instructions'] = v['instructions'] or pricing.DEFAULT_INSTRUCTIONS.get(v['lang'], '')
    return v


def list_voicings(slug: str) -> list[dict]:
    d = config.text_dir(slug) / 'voicings'
    if not d.exists():
        return []
    return [summary(slug, x.name) for x in sorted(d.iterdir()) if (x / 'voicing.json').exists()]


def create(slug: str, data: dict) -> str:
    name = (data.get('name') or '').strip() or f"{data.get('voice', 'voice')} {time.strftime('%Y-%m-%d')}"
    base = re.sub(r'[^a-z0-9]+', '-', ''.join(prepare.TRANSLIT.get(c, c) for c in name.lower())).strip('-') or 'v'
    vid, n = base[:40], 2
    while (config.text_dir(slug) / 'voicings' / vid).exists():
        vid, n = f'{base[:36]}-{n}', n + 1
    keep = {k: data[k] for k in DEFAULTS if k in data}
    keep['name'] = name
    keep['created'] = time.strftime('%Y-%m-%d %H:%M')
    config.write_json(vdir(slug, vid) / 'voicing.json', keep)
    return vid


def update(slug: str, vid: str, patch: dict) -> dict:
    path = vdir(slug, vid) / 'voicing.json'
    cur = config.read_json(path, {})
    cur = _merge(cur, {k: v for k, v in patch.items() if k in DEFAULTS})
    config.write_json(path, cur)
    return settings(slug, vid)


# ---------------------------------------------------------------- plan: paragraphs and their status

def with_manner(v: dict, ov: dict | None) -> dict:
    """A paragraph's manner (an edit from the admin: an epigraph — plainer, a letter — quieter…) is appended to the narration's manner."""
    manner = (ov or {}).get('manner')
    # the lead is Russian-language data for Russian takes: changing it makes every Russian take stale
    lead = 'This passage:' if v.get('lang') == 'en' else 'Этот фрагмент:'
    if (ov or {}).get('max_chars'):  # a long paragraph the model stumbles on — shorter pieces (by sentence)
        v = {**v, 'max_chars': int(ov['max_chars'])}
    return {**v, 'instructions': f"{v['instructions']} {lead} {manner}"} if manner else v


def _key(v: dict, speech: str) -> str:
    sig = [v['model'], v['voice'], v['instructions'], v['speed'], v['tempo'], v['max_chars'], speech]
    return hashlib.sha256(repr(sig).encode()).hexdigest()[:12]


def passed(score: float | None, words: int, tail: bool | None, min_score: float) -> bool:
    """A take is good: the end is not cut off and the match is at or above the threshold, or at most one word differs
    (in a short paragraph one "wrongly" transcribed word — numbers, names — is no reason to redo it)."""
    if score is None:
        return True
    misses = round((1 - score) * words)
    return tail is not False and (score >= min_score or misses <= 1)


def chunks(speech: str, max_chars: int) -> list[str]:
    """Paragraph text → pieces at sentence boundaries, each no longer than max_chars (when possible)."""
    if len(speech) <= max_chars:
        return [speech]
    sents = [speech[a:b] for a, b in text.split_sentences(speech)]
    n = -(-len(speech) // max_chars)  # how many pieces are needed
    target = len(speech) / n          # pieces of roughly equal length
    out, cur = [], ''
    for s in sents:
        if cur and (len(cur) + 1 + len(s) > max_chars or len(cur) >= target):
            out.append(cur)
            cur = s
        else:
            cur = f'{cur} {s}' if cur else s
    if cur:
        out.append(cur)
    return out


def item_state(slug: str, vid: str, pid: str) -> dict:
    return config.read_json(vdir(slug, vid) / 'items' / f'{pid}.json', {'takes': []})


def _save_state(slug: str, vid: str, pid: str, st: dict) -> None:
    config.write_json(vdir(slug, vid) / 'items' / f'{pid}.json', st)


def selected_take(st: dict) -> dict | None:
    for t in st.get('takes', []):
        if t['n'] == st.get('selected'):
            return t
    return None


def plan(slug: str, vid: str, sections: list[str] | None = None) -> dict:
    """The work list: sections → paragraphs with the text to narrate, the key and the status."""
    v = settings(slug, vid)
    b = config.story(slug)
    prep = prepare.load(slug, v['lang'])
    if not prep:
        raise RuntimeError('the story is not prepared: run make prepare first')
    ov = prepare.overrides(slug, v['lang'])
    want = sections or v['sections'] or [s['id'] for s in prep['sections']]
    out = []
    for s in prep['sections']:
        if s['id'] not in want:
            continue
        items = []
        for p in s['paragraphs']:
            o = ov.get(p['id'], {})
            speech = prepare.speech_text(b, p, o)
            st = item_state(slug, vid, p['id'])
            take = selected_take(st)
            key = _key(with_manner(v, o), speech)
            if o.get('skip'):
                status = 'skip'
            elif not take:
                status = 'pending'
            elif take['key'] != key:
                status = 'stale'
            elif st.get('approved'):
                status = 'approved'
            elif not passed(take.get('score'), len(p['words']), take.get('tail'), v['verify']['min_score']):
                status = 'warn'
            else:
                status = 'ok'
            items.append({
                'id': p['id'], 'kind': p['kind'], 'text': p['text'], 'speech': speech,
                'edited': bool(o.get('speech')), 'manner': o.get('manner', ''), 'chars': len(speech), 'chunks': len(chunks(speech, with_manner(v, o)['max_chars'])),
                'key': key, 'status': status, 'approved': bool(st.get('approved')),
                'selected': st.get('selected'), 'takes': [_take_brief(slug, vid, t) for t in st.get('takes', [])],
                # for checking the highlighting in the admin: the paragraph's words and their times in the selected take
                'words': p['words'], 'times': take['words'] if take else None,
            })
        out.append({'id': s['id'], 'title': s['title'], 'items': items})
    return {'voicing': v, 'sections': out}


def _take_brief(slug: str, vid: str, t: dict) -> dict:
    return {k: t.get(k) for k in ('n', 'key', 'dur', 'score', 'tail', 'transcript', 'cost', 'created', 'attempts')} | {
        'file': f'voicings/{vid}/takes/{t["file"]}'}


def summary(slug: str, vid: str) -> dict:
    v = settings(slug, vid)
    counts, cost, dur = {}, 0.0, 0.0
    try:
        pl = plan(slug, vid)
    except RuntimeError:
        pl = {'sections': []}
    for s in pl['sections']:
        for it in s['items']:
            counts[it['status']] = counts.get(it['status'], 0) + 1
            for t in it['takes']:
                cost += sum((t.get('cost') or {}).values())
                if t['n'] == it['selected']:
                    dur += t.get('dur') or 0
    return {'id': vid, 'name': v['name'], 'lang': v['lang'], 'model': v['model'], 'voice': v['voice'],
            'sections': v['sections'], 'counts': counts, 'cost': round(cost, 4), 'duration': round(dur, 1),
            'created': v.get('created')}


def chars_per_sec(slug: str, vid: str) -> float | None:
    """The pace from finished takes (for an accurate estimate of the rest)."""
    d = vdir(slug, vid) / 'items'
    chars = sec = 0.0
    if d.exists():
        for f in d.glob('*.json'):
            st = config.read_json(f, {})
            t = selected_take(st)
            if t and t.get('dur') and t.get('chars'):
                chars += t['chars']
                sec += t['dur']
    return chars / sec if sec > 30 else None


def estimate(slug: str, vid: str, sections: list[str] | None = None, only_missing: bool = True) -> dict:
    v = settings(slug, vid)
    pl = plan(slug, vid, sections)
    todo = [it for s in pl['sections'] for it in s['items']
            if it['status'] != 'skip' and (not only_missing or it['status'] in ('pending', 'stale'))]
    chars = sum(it['chars'] for it in todo)
    n = sum(it['chunks'] for it in todo)
    est = pricing.estimate(v['model'], chars, v['lang'], v['instructions'], n, v['verify']['enabled'],
                           chars_per_sec(slug, vid))
    # retries after a failed check — a ~10% margin
    est['total_with_retries'] = round(est['total'] * 1.1, 4)
    est['items'] = len(todo)
    return est


# ---------------------------------------------------------------- generating a take

def _transcribe(pcm: bytes, v: dict, log=print, tries: int = 3) -> tuple[dict, float]:
    """Transcribe the audio; broken word timings (align.timing_ok) — transcribe again (up to tries)."""
    ver, cost, best = v['verify'], 0.0, None
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / 'chunk.flac'
        audio.save_flac(pcm, f)
        for k in range(tries):
            rec = openrouter.transcribe(str(f), model=ver['model'], language=v['lang'])
            cost += float((rec.get('usage') or {}).get('cost') or audio.dur(pcm) / 60 * pricing.STT_PER_MIN)
            best = best or rec
            if align.timing_ok(rec.get('words') or []):
                return rec, cost
            log(f'  ⚠ broken word timings — transcribing again ({k + 1})')
    return best, cost


def _word_times(para: dict, rec_words: list[dict], pcm: bytes) -> list[list[float]]:
    """A paragraph's word timings: from the transcription; if the marks stay broken — from pauses in the audio."""
    src = [para['text'][a:b] for a, b in para['words']]
    times, _, _ = align.align(src, rec_words, audio.dur(pcm))
    if align.bad_spans(times) or not align.timing_ok(rec_words):
        times = align.by_pauses(para['text'], para['words'], para['sentences'], audio.silences(pcm), audio.dur(pcm))
    return times


def retime(slug: str, vid: str, pid: str, log=print) -> dict:
    """Re-mark the word timings of the selected take (no synthesis): transcribe its audio again."""
    v = settings(slug, vid)
    prep = prepare.load(slug, v['lang'])
    para = next(p for s in prep['sections'] for p in s['paragraphs'] if p['id'] == pid)
    with _lock(f'{slug}/{vid}/{pid}'):
        st = item_state(slug, vid, pid)
        take = selected_take(st)
        pcm = audio.load(vdir(slug, vid) / 'takes' / take['file'])
        rec, cost = _transcribe(pcm, v, log)
        take['words'] = _word_times(para, rec.get('words') or [], pcm)
        take['cost']['verify'] = round(take['cost'].get('verify', 0) + cost, 5)
        take['retimed'] = time.strftime('%Y-%m-%d %H:%M:%S')
        _save_state(slug, vid, pid, st)
        return st


def synth_chunk(v: dict, speech: str, log=print) -> tuple[bytes, dict | None, dict]:
    """A piece of text → (pcm, transcription, cost). With checking and retries."""
    ver = v['verify']
    tries = max(1, int(ver.get('retries', 3))) if ver['enabled'] else 1
    best, cost = None, {}  # the best attempt; cost — of all attempts
    for attempt in range(1, tries + 1):
        raw, ctype = openrouter.speech(speech, model=v['model'], voice=v['voice'], instructions=v['instructions'],
                                       speed=v['speed'])
        pcm = audio.trim(audio.to_pcm(raw, ctype), v['tempo'])
        sec = audio.dur(pcm)
        cost['tts'] = cost.get('tts', 0) + pricing.tts_cost(v['model'], len(speech), sec, v['instructions'])
        if not ver['enabled']:
            return pcm, None, cost
        rec, c = _transcribe(pcm, v, log)
        cost['verify'] = cost.get('verify', 0) + c
        words = [speech[a:b] for a, b in text.split_words(speech)]
        _, score, tail = align.align(words, rec.get('words') or [], sec)
        rec.update(score=score, tail=tail, attempts=attempt)
        rank = score + (0.5 if tail else 0)
        if best is None or rank > best[0]:
            best = (rank, pcm, rec)
        if passed(score, len(words), tail, ver['min_score']):
            break
        log(f'  ⚠ attempt {attempt}: match {score}{"" if tail else ", end cut off"}')
    best[2]['attempts'] = attempt
    return best[1], best[2], cost


def generate_item(slug: str, vid: str, pid: str, *, force: bool = False, log=print) -> dict:
    """A new take of a paragraph (if there is no take for the current text and settings, or force)."""
    v = settings(slug, vid)
    b = config.story(slug)
    prep = prepare.load(slug, v['lang'])
    para = next((p for s in prep['sections'] for p in s['paragraphs'] if p['id'] == pid), None)
    if para is None:
        raise KeyError(f'no paragraph {pid}')
    o = prepare.overrides(slug, v['lang']).get(pid)
    speech = prepare.speech_text(b, para, o)
    v = with_manner(v, o)
    key = _key(v, speech)
    with _lock(f'{slug}/{vid}/{pid}'):
        st = item_state(slug, vid, pid)
        cur = selected_take(st)
        if cur and cur['key'] == key and not force:
            return st
        parts = chunks(speech, v['max_chars'])
        pcm_all, rec_words, cost, attempts, transcript, scores, tails = b'', [], {}, 0, [], [], []
        for i, part in enumerate(parts):
            if i:
                pcm_all += audio.silence(v['gaps']['chunk'])
            off = audio.dur(pcm_all)
            pcm, rec, c = synth_chunk(v, part, log)
            for k, x in c.items():
                cost[k] = cost.get(k, 0) + x
            if rec:
                rec_words += [{**w, 'start': w['start'] + off, 'end': w['end'] + off} for w in rec.get('words') or []]
                transcript.append(rec.get('text', ''))
                scores.append(rec['score'] * len(part))
                tails.append(rec['tail'])
                attempts = max(attempts, rec.get('attempts', 1))
            pcm_all += pcm
        sec = audio.dur(pcm_all)
        src_words = [para['text'][a:c] for a, c in para['words']]
        if rec_words:
            times = _word_times(para, rec_words, pcm_all)
        else:  # no check — word timings by text share
            times = _proportional(para, sec)
        n = max([t['n'] for t in st['takes']], default=0) + 1
        fname = f'{pid}-{n}.opus'
        audio.save_take(pcm_all, vdir(slug, vid) / 'takes' / fname)
        take = {
            'n': n, 'key': key, 'file': fname, 'dur': round(sec, 3), 'chars': len(speech),
            'speech': speech, 'words': times,
            'score': round(sum(scores) / len(speech), 3) if scores else None,
            'tail': all(tails) if tails else None,
            'transcript': ' '.join(transcript) if transcript else None,
            'attempts': attempts or 1, 'chunks': len(parts),
            'cost': {k: round(x, 5) for k, x in cost.items()},
            'model': v['model'], 'voice': v['voice'], 'created': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        st['takes'].append(take)
        st['selected'] = n
        st['approved'] = False
        _save_state(slug, vid, pid, st)
        return st


def _proportional(para: dict, sec: float) -> list[list[float]]:
    total = len(para['text']) or 1
    return [[round(a / total * sec, 3), round(b / total * sec, 3)] for a, b in para['words']]


def set_item(slug: str, vid: str, pid: str, *, selected: int | None = None, approved: bool | None = None) -> dict:
    with _lock(f'{slug}/{vid}/{pid}'):
        st = item_state(slug, vid, pid)
        if selected is not None:
            if not any(t['n'] == selected for t in st['takes']):
                raise KeyError(f'no take {selected}')
            if selected != st.get('selected'):
                st['approved'] = False
            st['selected'] = selected
        if approved is not None:
            st['approved'] = bool(approved) and st.get('selected') is not None
        _save_state(slug, vid, pid, st)
        return st


def delete_take(slug: str, vid: str, pid: str, n: int) -> dict:
    with _lock(f'{slug}/{vid}/{pid}'):
        st = item_state(slug, vid, pid)
        t = next((t for t in st['takes'] if t['n'] == n), None)
        if t:
            (vdir(slug, vid) / 'takes' / t['file']).unlink(missing_ok=True)
            st['takes'].remove(t)
            if st.get('selected') == n:
                st['selected'] = st['takes'][-1]['n'] if st['takes'] else None
                st['approved'] = False
            _save_state(slug, vid, pid, st)
        return st


# ---------------------------------------------------------------- the section track (for the site)

def section_track(slug: str, vid: str, sid: str, *, require_all: bool = True, with_audio: bool = True) -> tuple[bytes, dict] | None:
    """Joins the selected takes of a section → (pcm, timing marks: paragraphs, sentences, words).
    None if not every paragraph has a current take (require_all). with_audio=False — only the marks
    (take durations come from the data, no audio is decoded; pcm is empty but of the same length in time)."""
    pl = plan(slug, vid, [sid])
    if not pl['sections']:
        return None
    sec = pl['sections'][0]
    v = pl['voicing']
    gaps = v['gaps']
    prep = prepare.load(slug, v['lang'])
    paras = {p['id']: p for s in prep['sections'] if s['id'] == sid for p in s['paragraphs']}
    pcm, out = b'', []
    for it in sec['items']:
        if it['status'] == 'skip':
            continue
        if it['status'] in ('pending', 'stale'):
            if require_all:
                return None
            continue
        st = item_state(slug, vid, it['id'])
        take = selected_take(st)
        if pcm:
            pcm += audio.silence(gaps['heading'] if out and out[-1]['kind'] == 'heading' else gaps['paragraph'])
        t0 = audio.dur(pcm)
        clip = audio.load(vdir(slug, vid) / 'takes' / take['file']) if with_audio else audio.silence(take['dur'])
        pcm += clip
        p = paras[it['id']]
        words = [[a, b, round(t0 + w[0], 3), round(t0 + w[1], 3)] for (a, b), w in zip(p['words'], take['words'])]
        sents = []
        for a, b in p['sentences']:
            ws = [w for w in words if w[0] >= a and w[1] <= b]
            sents.append([a, b, ws[0][2] if ws else round(t0, 3), ws[-1][3] if ws else round(t0 + audio.dur(clip), 3)])
        out.append({'id': p['id'], 'kind': p['kind'], 'text': p['text'], 'italic': p.get('italic', False),
                    't0': round(t0, 3), 't1': round(t0 + audio.dur(clip), 3), 'sentences': sents, 'words': words})
    if not out:
        return None
    return pcm, {'id': sid, 'title': sec['title'], 'duration': round(audio.dur(pcm), 3), 'paragraphs': out}
