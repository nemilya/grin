"""Paper-theatre assets: bible + style → prompts → pictures (Seedream via OpenRouter) → cut-outs with alpha.

stories/<slug>/assets/
    refs/<character>.jpg        the character sheet (turnaround: front, ¾, profile, back) — drawn first,
                                 goes as a reference into every pose of the character: the face and costume stay recognizable
    <character>/<pose>.webp      a pose cut-out (chroma key → alpha, cropped to the silhouette)
    <set>/<piece>.webp           backdrops, floors (textures), furniture
    prop/<prop>.webp
    assets.json                 the manifest: fingerprint (model, prompt, seed, references), price, size
    takes/                      previous variants (not in git)

Status ok / stale (the prompt or the character sheet changed) / pending;
"redo" — a new seed, the previous variant goes to takes/. Procedural cards (stars, the sheet with "10", the chess
cut-out…) are drawn by the stage itself — they are not here.

Cut-outs are generated on a flat chroma key (#00FF00) with a white paper rim around the figure; the key is
by "greenness" (g − max(r, b)), a soft edge and green spill suppression; then a crop by alpha.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .openrouter import _request

MODEL = 'bytedance-seed/seedream-5-0-flash'
COST = 0.018  # $ per 2K picture (usage.cost, if it didn't arrive)
RATIOS = {'1:1': 1, '4:3': 4 / 3, '3:4': 3 / 4, '16:9': 16 / 9, '9:16': 9 / 16, '3:2': 1.5, '2:3': 2 / 3, '21:9': 21 / 9,
          '4:5': 0.8, '5:4': 1.25}
MAX_SIDE = 1600
CUT = '.webp'  # cut-outs: lossless WebP with alpha — the same pixels as PNG at ≈ 45 % of the size
MATCH_GREEN = 50  # key_match: "green" (g − max(r, b)) — a background candidate, in shadow too
MATCH_HUE = 22    # key_match: background — only of the background's hue (±°): yellow-green (a tray, apples) and blue-green are not background
MATCH_HOLE = 0.0005  # key_match: a closed green area inside the figure is a see-through hole if it is at least this share of the picture…
MATCH_SAT = 0.75     # …and nearly as green as the background (share of the background's "greenness"): a hole in shadow — 0.8–1.1, a stroke on clothes — 0.5–0.7.
                     # A chroma-coloured stroke (a stripe on a tray) is covered by keep in the bible, a pale hole — by cut
MAGENTA_BG = ('Isolated on a perfectly flat, uniform pure magenta (#FF00FF) background — nothing else in the image: '
              'no table, no surface, no ground, no shadow.')


def adir(slug: str) -> Path:
    return config.story_dir(slug) / 'assets'


def style(slug: str) -> dict:
    name = config.story(slug).get('film', {}).get('style', 'paper-theatre')
    return config.read_json(config.STYLES / f'{name}.json', {}) or {}


def ratio(aspect: float) -> str:
    return min(RATIOS, key=lambda k: abs(RATIOS[k] / aspect - 1) if aspect else 0)


# ---------------------------------------------------------------- plan

def plan(slug: str, keys: set | None = None) -> list[dict]:
    """What to draw: character sheets → poses and parts → sets and props. keys — only these cards
    (and their characters' sheets)."""
    b = config.read_json(config.story_dir(slug) / 'bible.json', {}) or {}
    st = style(slug)
    # wording for "what this picture is" comes from the style; the default is paper theatre
    piece_kind = st.get('piece') or st.get('cutout', '').replace('puppet', 'piece of toy-theatre scenery')
    sheet_kind = st.get('sheet', 'for a paper toy theatre')
    sheet_each = st.get('sheet_each', 'Each figure is a separate paper cut-out.')
    figure = st.get('figure', 'A single paper cut-out puppet of')
    part_kind = st.get('part', 'One separate jointed limb piece of a paper puppet (only this single piece)')
    world = b.get('world', '')
    no_text = st.get('no_text', '')
    items = []
    want = lambda k: keys is None or k in keys  # noqa: E731

    for cid, ch in (b.get('characters') or {}).items():
        poses = ch.get('poses') or {}
        need = [p for p in poses if want(f'{cid}/{p}')] + [n for p in poses.values() for n in (p.get('parts') or {}) if want(f'{cid}/{n}')]
        if not need:
            continue
        silhouettes = all(p.get('kind') == 'silhouette' for p in poses.values())
        no_ref = all(p.get('ref', True) is False for p in poses.values())  # passers-by in a crowd: one picture each, no sheet
        cutout = ch.get('technique') or st.get('cutout', '')  # technique — the character's own manner (a white coat without rays)
        sheet = None
        if not silhouettes and not no_ref:
            sheet = f'refs/{cid}'
            items.append({'key': sheet, 'kind': 'ref', 'out': f'{sheet}.jpg', 'aspect': '3:2', 'refs': [],
                          'prompt': (f"Character reference sheet (turnaround) of ONE character {sheet_kind} — "
                                     f"{ch.get('name', cid)}, {ch.get('age', '')}: {ch['look']}. Show the same character four times "
                                     f"in a row, full body, evenly spaced, same scale: front view, three-quarter view, side profile, "
                                     f"back view. Neutral standing pose, arms relaxed. {sheet_each} "
                                     f"{cutout} {st.get('sheet_bg', 'On a plain light grey paper background.')} World: {world} {no_text}")})
        for pid, p in poses.items():
            look = ch.get(p['outfit']) if p.get('outfit') else ch['look']
            legend = (f"Image 1 is the character sheet of this same person: keep the face, hair, build and clothing exactly. "
                      if sheet else '')
            if want(f'{cid}/{pid}'):
                if p.get('kind') == 'silhouette':
                    prompt = f"{st.get('silhouette', '')} The silhouette shows: {ch['look']}. Pose: {p['desc']}. {no_text}"
                elif p.get('closeup'):  # a close-up detail (a hand, hands): no figure or appearance — otherwise the model draws the whole person
                    obj = st.get('object') or st.get('cutout', '').replace('puppet', 'object')
                    prompt = f"{obj} ONE single detail only, not a whole person: {p['desc']}. {st.get('cutout_bg', '')} {no_text}"
                else:
                    prompt = (f"{legend}{figure} {ch.get('name', cid)} ({ch.get('age', '')}): {look}. "
                              f"Pose and expression: {p['desc']}. {cutout} {st.get('cutout_bg', '')} {no_text}")
                use = sheet if p.get('ref', True) else None  # ref: false — no sheet (a close-up of hands, etc.)
                if not use:
                    prompt = prompt.replace(legend, '')
                items.append({'key': f'{cid}/{pid}', 'kind': p.get('kind', 'cutout'), 'out': f'{cid}/{pid}{CUT}',
                              'aspect': ratio(p.get('aspect', 0.6)), 'refs': [use] if use else [], 'prompt': prompt,
                              'erase': p.get('erase'), 'keep': p.get('keep'), 'cut': p.get('cut')})
            for n, part in (p.get('parts') or {}).items():
                if want(f'{cid}/{n}'):
                    # without the character sheet: with it the model draws the whole figure instead of the detail
                    items.append({'key': f'{cid}/{n}', 'kind': 'cutout', 'out': f'{cid}/{n}{CUT}', 'aspect': ratio(part.get('aspect', 0.4)),
                                  'refs': [],
                                  'prompt': (f"{part_kind}: {part['desc']}. "
                                             f"Only this single piece, nothing else, vertical. {st.get('cutout', '')} {st.get('cutout_bg', '')} {no_text}")})

    for sid, s in (b.get('sets') or {}).items():
        for pid, pc in (s.get('pieces') or {}).items():
            key = f'{sid}/{pid}'
            if pc.get('kind') == 'procedural' or pc.get('card') or not want(key):  # card — someone else's card, not drawn
                continue
            kind = pc.get('kind', 'cutout')
            aspect = pc['size'][0] / pc['size'][1] if pc.get('size') else pc.get('aspect', 1)
            hole = ' The opening is filled with flat pure chroma green (#00FF00).' if pc.get('hole') else ''
            if kind == 'backdrop':
                ctx = f" World: {world}" if pc.get('world', True) else ''  # world: false — a place outside the story's world (a desert)
                prompt = f"{st.get('backdrop', '')} {pc['desc']}. Setting: {s.get('look', '')}.{hole}{ctx} {no_text}"
            elif kind == 'floor':
                prompt = f"{st.get('texture', '')} {pc['desc']}. {no_text}"
            else:
                if pc.get('hole'):  # a wall with an opening is still a whole piece of the set
                    prompt = (f"{piece_kind} The piece: {pc['desc']}."
                              f"{hole} {st.get('cutout_bg', '')} {no_text}")
                else:  # a separate prop: only it, no room around it
                    prompt = (f"{piece_kind} ONE single object only: "
                              f"{pc['desc']}. Just this object on its own, no room, no walls, no floor, no other furniture. "
                              f"{st.get('cutout_bg', '')} {no_text}")
            items.append({'key': key, 'kind': kind, 'out': f'{key}.{"png" if kind in ("cutout", "silhouette") or pc.get("hole") else "jpg"}',
                          'aspect': ratio(aspect), 'refs': [], 'prompt': prompt, 'hole': bool(pc.get('hole')),
                          'erase': pc.get('erase')})

    for pid, pr in (b.get('props') or {}).items():
        key = f'prop/{pid}'
        if pr.get('kind') == 'procedural' or not want(key):
            continue
        # technique — the prop's own manner (a natural leaf in a painted film); key: magenta — a magenta background for a green prop
        obj = pr.get('technique') or st.get('object') or st.get('cutout', '').replace('puppet', 'object')
        bg = MAGENTA_BG if pr.get('key') == 'magenta' else st.get('cutout_bg', '')
        items.append({'key': key, 'kind': 'cutout', 'out': f'{key}{CUT}', 'aspect': ratio(pr.get('aspect', 1)), 'refs': [],
                      'prompt': f"{obj} The object: {pr['desc']}. {bg} {no_text}", 'key_color': pr.get('key', 'green'),
                      'erase': pr.get('erase'), 'keep': pr.get('keep'), 'cut': pr.get('cut')})  # clean-up (the paper rim in the corners), keep — see key_out

    m = manifest(slug)
    for it in items:
        cur = m['items'].get(it['key'])
        it['seed'] = (cur or {}).get('seed') or int(hashlib.sha256(it['key'].encode()).hexdigest()[:8], 16) % 2147483647
        it['hash'] = _hash(slug, it)
        it['status'] = ('ok' if cur and cur.get('hash') == it['hash'] and (adir(slug) / cur['file']).exists()
                        else 'stale' if cur else 'pending')
    return items


def _hash(slug: str, it: dict) -> str:
    h = hashlib.sha256(json.dumps([MODEL, it['aspect'], it['prompt'], it['seed'], it['kind']]).encode())
    for r in it['refs']:
        f = adir(slug) / f'{r}.jpg'
        h.update(f.read_bytes() if f.exists() else r.encode())
    return h.hexdigest()[:12]


def manifest(slug: str) -> dict:
    return config.read_json(adir(slug) / 'assets.json', {'items': {}}) or {'items': {}}


def used_keys(timeline: dict) -> set:
    """Cards that actually appear in the timeline (with the parts of jointed puppets)."""
    keys = set()
    for s in timeline['shots']:
        for el in s['elements']:
            for k in (el.get('card'), el.get('card_prev')):
                if k:
                    keys.add(k)
                    spec = timeline['assets'].get(k) or {}
                    keys |= {p['card'] for p in (spec.get('parts') or {}).values()}
    return keys


# ---------------------------------------------------------------- generation

def _image(prompt: str, aspect: str, seed: int, refs: list[Path]) -> tuple[bytes, float]:
    body = {'model': MODEL, 'prompt': prompt, 'n': 1, 'seed': seed, 'resolution': '2K', 'aspect_ratio': aspect}
    if refs:
        body['input_references'] = [{'type': 'image_url', 'image_url': {'url': _data_url(f)}} for f in refs]
    raw, _ = _request('/images', body=json.dumps(body).encode(), ctype='application/json', timeout=300)
    r = json.loads(raw)
    img = (r.get('data') or [{}])[0]
    if not img.get('b64_json'):
        raise RuntimeError(f'no picture in the response: {str(r)[:300]}')
    return base64.b64decode(img['b64_json']), float((r.get('usage') or {}).get('cost') or COST)


def _data_url(f: Path) -> str:
    small = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(f), '-vf', "scale='min(1024,iw)':-2", '-q:v', '3',
                            '-f', 'mjpeg', 'pipe:1'], capture_output=True, check=True).stdout
    return 'data:image/jpeg;base64,' + base64.b64encode(small).decode()


def _decode(data: bytes) -> tuple[bytes, int, int]:
    """A picture → RGBA (≤ MAX_SIDE on the long side)."""
    w, h = map(int, subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', '-i', 'pipe:0'],
                                   input=data, capture_output=True, check=True).stdout.decode().strip().split(',')[:2])
    k = min(1.0, MAX_SIDE / max(w, h))
    w, h = max(2, round(w * k)), max(2, round(h * k))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-vf', f'scale={w}:{h}:flags=lanczos', '-f', 'rawvideo',
                          '-pix_fmt', 'rgba', 'pipe:1'], input=data, capture_output=True, check=True).stdout
    return raw, w, h


def _blur(x, rad: int):
    """Box blur along both axes (numpy, edges repeated)."""
    import numpy as np
    for ax in (0, 1):
        pad = [(rad + 1, rad) if i == ax else (0, 0) for i in range(x.ndim)]
        c = np.cumsum(np.pad(x, pad, mode='edge'), axis=ax)
        n = c.shape[ax]
        x = (np.take(c, range(2 * rad + 1, n), axis=ax) - np.take(c, range(0, n - 2 * rad - 1), axis=ax)) / (2 * rad + 1)
    return x


def _holes(rest, rgb, bgc, keep=None, cut=None):
    """Closed green areas inside the figure: background holes are not small (≥ MATCH_HOLE of the picture) and almost exactly
    the background colour (≥ MATCH_SAT of its "greenness"); a centre inside a keep rectangle ([[x0, y0, x1, y1]] in picture
    fractions, from the top left) is a stroke on clothes (keep it), inside cut — a hole (cut it). Labels on a 1/4 grid (fast), the mask at full size."""
    import numpy as np
    h, w = rest.shape
    small = rest[::4, ::4]
    lab = np.zeros(small.shape, np.int32)
    out = np.zeros(rest.shape, bool)
    for y0, x0 in zip(*np.nonzero(small)):
        if lab[y0, x0]:
            continue
        lab[y0, x0] = 1
        st, pts = [(y0, x0)], []
        while st:
            y, x = st.pop()
            pts.append((y, x))
            for y2, x2 in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= y2 < small.shape[0] and 0 <= x2 < small.shape[1] and small[y2, x2] and not lab[y2, x2]:
                    lab[y2, x2] = 1
                    st.append((y2, x2))
        ys, xs = np.array(pts).T * 4
        c = rgb[ys, xs].mean(0)
        sat = (c[1] - max(c[0], c[2])) / max(1.0, bgc[1] - max(bgc[0], bgc[2]))
        cy, cx = ys.mean() / h, xs.mean() / w
        inside = lambda boxes: any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in boxes or [])  # noqa: E731
        if not inside(cut) and (len(pts) * 16 < MATCH_HOLE * h * w or sat < MATCH_SAT or inside(keep)):
            continue
        box = np.zeros(small.shape, bool)
        box[ys // 4, xs // 4] = True
        out |= np.repeat(np.repeat(box, 4, 0), 4, 1)[:h, :w] & rest
    return out


def key_out(data: bytes, out: Path, *, crop: bool = True, silhouette: bool = False,
            erase: list | None = None, soft: bool = False, key: str = 'green', match: bool = False,
            keep: list | None = None, cut: list | None = None) -> tuple[int, int]:
    """Chroma key: green background → transparency (soft edge, no green spill), crop to the silhouette → PNG.
    silhouette — a black silhouette: alpha by brightness (the background is green or white, the model draws both).
    soft — the "cinema" layer: a feathered edge, under the transparent part — the neighbours' colour (not a white rim).
    key: magenta — a magenta background (for a green prop: a leaf).
    match — the background is transparent: green of the background's hue connected to the picture's edge, and closed holes of
    the background colour; green strokes on a painted figure's clothes are not cut (style: key_match); keep — where a closed background-coloured area is a stroke (_holes)."""
    import numpy as np
    raw, w, h = _decode(data)
    a = np.frombuffer(raw, np.uint8).reshape(h, w, 4).astype(np.float32)
    if key == 'magenta':  # magenta → green: then the same key; the prop's colour is restored afterwards
        orig = a[..., :3].copy()
        g0, m = orig[..., 1], np.minimum(orig[..., 0], orig[..., 2])
        a[..., 0], a[..., 1], a[..., 2] = g0, m, g0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    green = g - np.maximum(r, b)                       # how "green" a pixel is
    alpha = 1 - np.clip((green - 40) / 70, 0, 1)       # 40 and below — opaque, 110+ — background
    if soft:
        alpha = _blur(1 - np.clip((green - 30) / 80, 0, 1), 2) ** 1.4   # feathering ~4 px, a thinner edge
    wide = 1.0
    if match and not silhouette:
        # background — green of the background's hue connected to the picture's edge; a closed area inside the figure is a hole
        # (between bench legs, an arm and the body) only if it is large and almost exactly the background colour; the rest are strokes
        # on clothes (the model paints them in the chroma colour too: a stripe on a tray, a skirt), not cut
        from PIL import Image, ImageFilter
        mn = np.minimum(r, b)
        hue = 120 + 60 * (b - r) / np.maximum(g - mn, 1)       # the hue where green is the largest
        band = np.zeros(green.shape, bool)
        band[:3], band[-3:], band[:, :3], band[:, -3:] = True, True, True, True
        eg = band & (green > 60)
        bgh = float(np.median(hue[eg])) if eg.sum() > 100 else 115.0               # the background's hue and colour — from the edge
        bgc = np.median(a[..., :3][eg], axis=0) if eg.sum() > 100 else np.array([40, 220, 20], np.float32)
        like = (green > MATCH_GREEN) & (np.abs(hue - bgh) < MATCH_HUE)  # yellow-green apples, emerald strokes — not background
        reach = like & band
        for _ in range(4000):  # reconstruction: grow the background from the edge over "background-like", while it grows
            grown = reach.copy()
            grown[1:] |= reach[:-1]; grown[:-1] |= reach[1:]; grown[:, 1:] |= reach[:, :-1]; grown[:, :-1] |= reach[:, 1:]
            grown &= like
            if grown.sum() == reach.sum():
                break
            reach = grown
        reach |= _holes(like & ~reach, a[..., :3], bgc, keep, cut)
        wide = np.asarray(Image.fromarray((reach * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)), np.float32) / 255  # +2 px — the edge
        t = np.clip((green - (MATCH_GREEN - 15)) / 40, 0, 1) * wide     # near the background a dark shadow is transparent too
        alpha = _blur(1 - t, 2) ** 1.4 if soft else 1 - t
    if silhouette:
        lum = (0.3 * r + 0.59 * g + 0.11 * b) / 255
        alpha = np.clip((0.55 - lum) / 0.25, 0, 1)
        a[..., :3] = np.minimum(a[..., :3], 20)
    if key == 'magenta':
        pink = (np.minimum(orig[..., 0], orig[..., 2]) > orig[..., 1])[..., None]   # spill and shadow on magenta:
        orig = np.where(pink, np.minimum(orig, orig[..., 1:2]), orig)              # r, b no higher than g (grey)
        a[..., :3] = orig
    else:
        spill = np.maximum(r, b)
        sup = np.where(g > spill, spill + (g - spill) * 0.15, g)          # suppress the green spill
        a[..., 1] = sup if not match else g + (sup - g) * wide            # match — only near the background, not on clothes
    if soft:
        hard = (alpha > 0.6).astype(np.float32)
        den = _blur(hard, 12)[..., None]
        fill = np.where(den > 1e-3, _blur(a[..., :3] * hard[..., None], 12) / np.maximum(den, 1e-3), a[..., :3])
        a[..., :3] = np.where((alpha < 0.6)[..., None], fill, a[..., :3])
    else:
        a[..., :3] = np.where((alpha < 0.5)[..., None], np.array([244, 239, 228], np.float32), a[..., :3])  # under the transparent part — the rim colour
    a[..., 3] = alpha * 255
    img = a.clip(0, 255).astype(np.uint8)
    def trim(img):
        ys, xs = np.where(img[..., 3] > 16)
        if not len(xs):
            return img
        pad = 6
        hh, ww = img.shape[:2]
        return img[max(0, ys.min() - pad):min(hh, ys.max() + pad + 1), max(0, xs.min() - pad):min(ww, xs.max() + pad + 1)]
    if crop:
        img = trim(img)
    if erase:  # clean-up: [[x0, y0, x1, y1], …] in fractions of the cropped cut-out (from the bottom left) — erase (a lamp cord, etc.)
        img = img.copy()
        hh, ww = img.shape[:2]
        for x0, y0, x1, y1 in erase:
            img[int((1 - y1) * hh):int((1 - y0) * hh), int(x0 * ww):int(x1 * ww), 3] = 0
        if crop:
            img = trim(img)
    hh, ww = img.shape[:2]
    out.parent.mkdir(parents=True, exist_ok=True)
    save_rgba(np.ascontiguousarray(img), out)
    return ww, hh


def save_rgba(img, out: Path) -> None:
    """RGBA array → file: lossless WebP (exact — RGB of transparent pixels kept too: texture edges don't change), or PNG."""
    from PIL import Image
    im = Image.fromarray(img, 'RGBA')
    if out.suffix == '.webp':
        im.save(out, 'WEBP', lossless=True, exact=True, method=4)
    else:
        im.save(out)


def _save_jpg(data: bytes, out: Path) -> tuple[int, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale='if(gt(iw,ih),min({MAX_SIDE},iw),-2)':'if(gt(iw,ih),-2,min({MAX_SIDE},ih))'"
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', 'pipe:0', '-vf', vf, '-q:v', '3', str(out)], input=data, check=True)
    w, h = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(out)],
                          capture_output=True, text=True).stdout.strip().split(',')[:2]
    return int(w), int(h)


_lock = __import__('threading').Lock()


def generate(slug: str, it: dict, *, redo: bool = False, log=print) -> float:
    d = adir(slug)
    if it['status'] == 'ok' and not redo:
        return 0.0
    if redo:
        it['seed'] = random.randint(1, 2147483646)
        it['hash'] = _hash(slug, it)
    missing = [r for r in it['refs'] if not (d / f'{r}.jpg').exists()]
    if missing:
        raise RuntimeError(f'no sheets: {", ".join(missing)} — draw them first')
    data, cost = _image(it['prompt'], it['aspect'], it['seed'], [d / f'{r}.jpg' for r in it['refs']])
    out = d / it['out']
    if out.exists():  # the previous variant goes to drafts
        t = d / 'takes' / f"{it['key'].replace('/', '__')}@{int(time.time())}{out.suffix}"
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, t)
    (d / 'raw').mkdir(parents=True, exist_ok=True)
    (d / 'raw' / f"{it['key'].replace('/', '__')}.jpg").write_bytes(data)  # the source before keying (not in git)
    if out.suffix != '.jpg':
        w, h = key_out(data, out, crop=not it.get('hole'), silhouette=it['kind'] == 'silhouette', erase=it.get('erase'),
                       soft=style(slug).get('key') == 'soft', key=it.get('key_color', 'green'), match=bool(style(slug).get('key_match')),
                       keep=it.get('keep'), cut=it.get('cut'))
    else:
        w, h = _save_jpg(data, out)
    with _lock:
        m = manifest(slug)
        m['items'][it['key']] = {'file': it['out'], 'hash': it['hash'], 'seed': it['seed'], 'cost': round(cost, 4),
                                 'w': w, 'h': h, 'refs': it['refs'], 'at': time.strftime('%Y-%m-%d %H:%M')}
        m['cost'] = round(m.get('cost', 0) + cost, 4)
        config.write_json(d / 'assets.json', m)
    log(f"✓ {it['key']} ({w}×{h}), ${cost:.3f}")
    return cost


def rekey(slug: str, keys: list[str], log=print) -> None:
    """Rebuild a cut-out from its source image (assets/raw) with the current settings: key, erase clean-up. No generation."""
    d = adir(slug)
    items = {it['key']: it for it in plan(slug, set(keys))}
    m = manifest(slug)
    for k in keys:
        it, raw = items.get(k), d / 'raw' / f"{k.replace('/', '__')}.jpg"
        if not it or not raw.exists() or it['out'].endswith('.jpg'):
            log(f'✗ {k}: no source image, or not a cut-out')
            continue
        w, h = key_out(raw.read_bytes(), d / it['out'], crop=not it.get('hole'), silhouette=it['kind'] == 'silhouette',
                       erase=it.get('erase'), soft=style(slug).get('key') == 'soft', key=it.get('key_color', 'green'),
                       match=bool(style(slug).get('key_match')), keep=it.get('keep'), cut=it.get('cut'))
        m['items'][k].update(w=w, h=h)
        log(f'✓ {k}: rebuilt ({w}×{h})')
    config.write_json(d / 'assets.json', m)


def accept(slug: str, keys: list[str], log=print) -> None:
    """Accept the current picture as current (stale → ok): the prompt changed, but there is no reason to redraw it."""
    items = {it['key']: it for it in plan(slug, set(keys))}
    with _lock:
        m = manifest(slug)
        for k in keys:
            if k in m['items'] and k in items:
                m['items'][k]['hash'] = items[k]['hash']
                log(f'✓ {k}: accepted as is')
            else:
                log(f'✗ {k}: no picture')
        config.write_json(adir(slug) / 'assets.json', m)


def generate_all(slug: str, keys: set | None = None, *, workers: int = 4, log=print) -> float:
    """Missing and stale ones: character sheets first, then everything else (in parallel)."""
    total = 0.0
    for stage in ('ref', 'rest'):
        todo = [it for it in plan(slug, keys) if it['status'] != 'ok' and ((it['kind'] == 'ref') == (stage == 'ref'))]

        def one(it):
            try:
                return generate(slug, it, log=log)
            except Exception as e:  # noqa: BLE001
                log(f"✗ {it['key']}: {e}")
                return 0.0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            total += sum(ex.map(one, todo))
    return total
