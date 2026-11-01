"""The local admin (view only): what has been made for a film — stories and productions, character sheets, poses,
sets and props (picture, prompt, status, price), the storyboard (shots with stills from out/), narration
(takes with the transcription score and playback), style and director.

    make admin            → http://127.0.0.1:8740/admin/

The server is the standard library: repository files as they are (pictures, take audio, out/…) and two JSON endpoints:
/api/stories — the list of stories, /api/story?slug=… — everything about a story. It writes and generates nothing.
"""
from __future__ import annotations

import json
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import assets, config, timeline, voicing  # noqa: E402

PORT = 8740


def _voicings(slug: str) -> list[dict]:
    st = config.story(slug)
    ids = list(dict.fromkeys([*(st['film'].get('voicings') or {}).values(), st['film'].get('voicing')]))
    out = []
    for vid in filter(None, ids):
        try:
            out.append(voicing.summary(slug, vid))
        except KeyError:
            continue
    return out


def stories() -> list[dict]:
    out = []
    for st in config.stories():
        slug = st['slug']
        items = assets.plan(slug)
        by = {}
        for it in items:
            by[it['status']] = by.get(it['status'], 0) + 1
        try:
            tl = timeline.build(slug, save=False)
            tls = {'shots': len(tl['shots']), 'duration': tl['duration'], 'errors': tl['errors'],
                   'warnings': tl.get('warnings', []), 'timing': tl['timing']}
        except Exception as e:  # noqa: BLE001
            tls = {'error': str(e)}
        out.append({'slug': slug, 'title': st.get('title', {}), 'base': st.get('base'),
                    'style': st['film'].get('style'), 'formats': list(st.get('formats') or {}),
                    'assets': by, 'cost': assets.manifest(slug).get('cost', 0),
                    'voicings': _voicings(slug) if not st.get('base') else [], 'timeline': tls})
    return out


def story(slug: str) -> dict:
    st = config.story(slug)
    sdir = config.story_dir(slug)
    b = config.read_json(sdir / 'bible.json', {}) or {}
    man = assets.manifest(slug)['items']
    plan = {it['key']: it for it in assets.plan(slug)}

    def card(key: str) -> dict:
        it, m = plan.get(key) or {}, man.get(key) or {}
        f = sdir / 'assets' / m['file'] if m.get('file') else None
        return {'key': key, 'status': it.get('status', 'procedural' if not it else 'pending'),
                'file': f'/stories/{slug}/assets/{m["file"]}' if f and f.exists() else None,
                'prompt': it.get('prompt', ''), 'refs': it.get('refs', []), 'cost': m.get('cost'),
                'w': m.get('w'), 'h': m.get('h'), 'at': m.get('at')}

    chars = []
    for cid, ch in (b.get('characters') or {}).items():
        poses = [{'id': pid, 'desc': p.get('desc', ''), **card(f'{cid}/{pid}')} for pid, p in (ch.get('poses') or {}).items()]
        chars.append({'id': cid, 'name': ch.get('name', cid), 'look': ch.get('look', ''), 'sheet': card(f'refs/{cid}'),
                      'poses': poses})
    sets = []
    for sid, s in (b.get('sets') or {}).items():
        pieces = [{'id': pid, 'desc': pc.get('desc', ''), 'kind': pc.get('kind', 'cutout'), 'pos': pc.get('pos'),
                   **card(pc.get('card') or f'{sid}/{pid}')} for pid, pc in (s.get('pieces') or {}).items()]
        sets.append({'id': sid, 'name': s.get('name', sid), 'look': s.get('look', ''), 'light': s.get('light'),
                     'pieces': pieces})
    props = [{'id': pid, 'desc': p.get('desc', ''), **card(f'prop/{pid}')} for pid, p in (b.get('props') or {}).items()]

    shots = []
    try:
        tl = timeline.build(slug, save=False)
        stills = config.OUT / slug / 'stills'
        for s in tl['shots']:
            f = stills / f'{s["id"]}.jpg'
            shots.append({'id': s['id'], 'scene': s['scene'], 'title': s.get('scene_title', ''), 'at': s['at'],
                          't0': s['t0'], 't1': s['t1'], 'set': s['set'], 'cam': s['camera'].get('name'),
                          'note': s.get('note', ''), 'cards': sorted({e['card'] for e in s['elements']}),
                          'still': f'/out/{slug}/stills/{f.name}?v={int(f.stat().st_mtime)}' if f.exists() else None})
        tinfo = {'duration': tl['duration'], 'errors': tl['errors'], 'warnings': tl.get('warnings', []), 'timing': tl['timing']}
    except Exception as e:  # noqa: BLE001
        tinfo = {'error': str(e)}

    vo = []
    if not st.get('base'):
        for v in _voicings(slug):
            items = []
            for sec in voicing.plan(slug, v['id'])['sections']:
                for it in sec['items']:
                    stt = voicing.item_state(slug, v['id'], it['id'])
                    take = voicing.selected_take(stt) or {}
                    items.append({'id': it['id'], 'status': it['status'], 'text': it['text'], 'manner': it.get('manner'),
                                  'score': take.get('score'), 'dur': take.get('dur'), 'transcript': take.get('transcript'),
                                  'takes': len(stt.get('takes', [])),
                                  'audio': f'/stories/{slug}/voicings/{v["id"]}/takes/{take["file"]}' if take.get('file') else None})
            vo.append({**v, 'items': items})

    sb = timeline.storyboard(slug)
    style = config.read_json(config.STYLES / f"{st['film'].get('style', 'paper-theatre')}.json", {})
    director = config.read_json(config.DIRECTORS / f"{sb['director']}.json", {}) if sb.get('director') else None
    return {'slug': slug, 'story': st, 'world': b.get('world', ''), 'characters': chars, 'sets': sets, 'props': props,
            'shots': shots, 'timeline': tinfo, 'voicings': vo, 'style': style, 'director': director,
            'cost': assets.manifest(slug).get('cost', 0)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):  # quiet
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/admin'):
            self.send_response(302)
            self.send_header('Location', '/admin/')
            self.end_headers()
            return
        if u.path.startswith('/api/'):
            try:
                if u.path == '/api/stories':
                    data = stories()
                elif u.path == '/api/story':
                    data = story(parse_qs(u.query)['slug'][0])
                else:
                    raise KeyError(u.path)
                body, code = json.dumps(data, ensure_ascii=False).encode(), 200
            except Exception as e:  # noqa: BLE001
                body, code = json.dumps({'error': str(e)}, ensure_ascii=False).encode(), 500
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'admin: http://127.0.0.1:{port}/admin/  ({time.strftime("%H:%M")}, Ctrl+C — quit)')
    srv.serve_forever()


if __name__ == '__main__':
    main()
