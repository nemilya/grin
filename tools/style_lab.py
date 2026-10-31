"""Проба стиля: одна сцена «по Тарковскому» в двух изображениях — картонные вырезки и «киноизображение»
(те же слои по глубине, но нарисованные как кадр из фильма: без кромки и бумаги, мягкий край, туман).
Камера, свет, палитра, дождь — общие, различается только то, как нарисованы слои.

    python3 tools/style_lab.py            # недостающие картинки (8 × $0.018) + таймлайны
    python3 tools/style_lab.py --redo doctor   # новый вариант слоя (в обоих изображениях)
    make preview  →  http://127.0.0.1:8720/stage/?story=_lab-tarkovsky&tl=cut   (или &tl=film)
    node tools/capture.mjs stills _lab-tarkovsky --tl cut --at 0.5
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import assets, config  # noqa: E402

LAB = ROOT / 'stories' / '_lab-tarkovsky'
REF = ROOT / 'stories' / 'mate-in-3' / 'assets' / 'refs' / 'doctor.jpg'
DOCTOR = config.read_json(ROOT / 'stories' / 'mate-in-3' / 'bible.json')['characters']['doctor']['look']

MOOD = ('Colour mood of a rainy overcast day: moss and olive greens, wet umber, slate grey, pale cold daylight, '
        'one small warm note of lamplight.')
FILM = ('Painted as part of a frame from a 1970s Soviet art-house film shot on 35mm colour negative, in the manner of '
        "the cinematography of Andrei Tarkovsky's films: photographic realism, natural soft overcast light, deep muted "
        'colours, fine film grain, slight softness. ' + MOOD)
FILM_ISO = ('A single isolated subject on a perfectly flat, uniform pure chroma-green (#00FF00) background — nothing else '
            'in the image: no room, no wall, no window, no floor, no ground, no shadow.')
FILM_LOOK = ('Rendered photographically, like a figure from a 1970s Soviet art-house film shot on 35mm colour negative '
             "(the cinematography of Andrei Tarkovsky's films): natural soft overcast light, muted colours, fine film grain. "
             'Natural photographic edges: no outline, no white border, no paper margin, not a drawing, not a cut-out. ' + MOOD)

# слои сцены: что нарисовать (без стиля), форма, место в сцене
LAYERS = {
    'garden': {'kind': 'plate', 'aspect': '3:4', 'seed': 4101,
               'desc': 'View out into an overgrown provincial garden in steady rain on an overcast day: wet birch trunks '
                       'and old apple trees, tall rain-soaked grass, a weathered wooden fence and a dark shed, puddles, '
                       'low grey sky, mist in the distance. Eye level, wide and deep. No people, no window frame.'},
    'wall': {'kind': 'hole', 'aspect': '9:16', 'seed': 4102,
             'desc': "The inner wall of a modest provincial doctor's study, about 1910, seen straight on: faded olive-green "
                     'wallpaper with damp stains, a tall old wooden window with peeling white paint in the centre of the '
                     'wall, a wide windowsill with a small potted geranium. The window panes are filled with flat pure '
                     'chroma green (#00FF00) — nothing is visible through the glass. No people, no furniture.'},
    'doctor': {'kind': 'cutout', 'aspect': '9:16', 'seed': 4103, 'refs': True,
               'desc': f'{DOCTOR}. Standing seen from behind in a three-quarter back view, looking out of a window, hands '
                       'clasped behind his back, still and thoughtful. The whole figure from head to boots.'},
    'floor': {'kind': 'texture', 'aspect': '4:3', 'seed': 4107,
              'desc': 'Old worn wooden floorboards with flaking brown paint, damp and scuffed, seen straight from above.'},
    'table': {'kind': 'cutout', 'aspect': '4:3', 'seed': 4104,
              'desc': 'The near corner of an old wooden writing table seen from the front at eye level: on it a lit '
                      'kerosene lamp with a glass chimney and a small warm flame, a faceted glass of water, and a wooden '
                      'chessboard with a few chess pieces standing on it. Only the table and these objects, the whole '
                      'table corner visible including the legs. Nothing behind or around the table: no wall, no curtain, no window, '
                      'no plants, no floor.'},
}


def prompt(variant: str, layer: dict) -> str:
    st = assets.style('mate-in-3')
    k = layer['kind']
    if k == 'texture':
        return ' '.join([st['texture'] if variant == 'cut' else
                         'A seamless flat texture seen straight from above, evenly lit, photographic, 35mm film grain.',
                         MOOD, layer['desc'], st['no_text']])
    if variant == 'cut':
        if k == 'cutout':
            cut = st['cutout'] if layer.get('refs') else (st['cutout'].replace('puppet', 'piece of toy-theatre scenery')
                                                          + ' ONE single object only, no people:')
            return ' '.join([cut, MOOD, layer['desc'], st['cutout_bg'], st['no_text']])
        return ' '.join([st['backdrop'], MOOD, layer['desc'], st['no_text']])
    if k == 'cutout':
        return ' '.join([FILM_ISO, layer['desc'], FILM_LOOK, FILM_ISO, st['no_text']])
    return ' '.join([FILM, 'A wide plate with deep perspective and atmospheric haze.' if k == 'plate' else '',
                     layer['desc'], st['no_text']])


def soft_key(data: bytes, out: Path, crop: bool) -> None:
    """Ключ для «кино»: край мягкий (растушёвка), под прозрачным — цвет соседей, а не белая кромка."""
    assets.key_out(data, out, crop=crop, soft=True)


def out_file(variant: str, name: str) -> Path:
    ext = '.jpg' if LAYERS[name]['kind'] in ('plate', 'texture') else '.webp'
    return LAB / 'assets' / variant / f'{name}{ext}'


def make(variant: str, name: str, seed: int) -> float:
    layer = LAYERS[name]
    data, cost = assets._image(prompt(variant, layer), layer['aspect'], seed, [REF] if layer.get('refs') else [])
    (LAB / 'assets' / 'raw').mkdir(parents=True, exist_ok=True)
    (LAB / 'assets' / 'raw' / f'{variant}__{name}.jpg').write_bytes(data)
    out = out_file(variant, name)
    if layer['kind'] in ('plate', 'texture'):
        assets._save_jpg(data, out)
    elif variant == 'cut':
        assets.key_out(data, out, crop=layer['kind'] == 'cutout')
    else:
        soft_key(data, out, crop=layer['kind'] == 'cutout')
    print(f'  ✓ {variant}/{name}  ${cost:.3f}')
    return cost


def size(f: Path) -> tuple[int, int]:
    w, h = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(f)],
                          capture_output=True, text=True, check=True).stdout.strip().split(',')[:2]
    return int(w), int(h)


def timeline(variant: str) -> dict:
    film = variant == 'film'
    ar = {n: (lambda w, h: w / h)(*size(out_file(variant, n))) for n in LAYERS}
    lay = lambda n, **kw: {'kind': 'cutout', 'file': f'assets/{variant}/{out_file(variant, n).name}',  # noqa: E731
                           **({'soft': True, 'cast': False} if film else {}), **kw}
    th = min(14.0, 17 / ar['table'])                                   # стол — ~17 см шириной
    tx, ty, tz = 9.5, -2, 9
    lamp = [tx + (0.29 - 0.5) * th * ar['table'], ty + 0.74 * th, tz + 0.3]   # огонёк лампы на столе
    A = {
        'garden': {'kind': 'backdrop', 'draw': 'screen', 'file': f'assets/{variant}/garden.jpg', 'size': [78, 78 / ar['garden']]},
        'wall': lay('wall', kind='backdrop', size=[46 * ar['wall'], 46], soft=False),
        'doctor': lay('doctor', h=19.5),
        'table': lay('table', h=th),
        'floor': {'kind': 'floor', 'file': f'assets/{variant}/floor.jpg', 'size': [70, 52]},
        'rain': {'kind': 'procedural', 'draw': 'rain'},
    }
    els = [
        {'id': 'garden', 'card': 'garden', 'pos': [-1, -12, -78], 'k': 1.5 if film else 1.35},
        {'id': 'rain', 'card': 'rain', 'pos': [0, 16, -34], 'box': [16, 36, 5], 'n': 1800, 'len': 1.2, 'gain': 0.22 if film else 0.28},
        {'id': 'wall', 'card': 'wall', 'pos': [0, -9, -30]},
        {'id': 'floor', 'card': 'floor', 'pos': [0, 0, -4]},
        {'id': 'doctor', 'card': 'doctor', 'pos': [-2.5, 0, -19]},
        {'id': 'table', 'card': 'table', 'pos': [tx, ty, tz]},
    ]
    for e in els:
        e.setdefault('fx', {}); e.setdefault('glow', None)
    cam = {'name': 'lab', 'from': {'pos': [9, 14, 54], 'look': [-1, 13, -25], 'fov': 30},
           'to': {'pos': [2, 14.5, 47], 'look': [-2.5, 13.5, -25], 'fov': 30}, 'ease': 'inOut', 'hand': 0}
    light = {'key': {'type': 'sun', 'pos': [-30, 50, 40], 'target': [0, 12, -20], 'color': '#d4dde4', 'intensity': 0.75,
                     'shadow': 1.4},
             'fill': {'color': '#8796a3', 'ground': '#3a3328', 'intensity': 0.38},
             'practical': {'pos': lamp, 'color': '#ffa552', 'intensity': 0.12, 'glow': 0.3},
             'bg': '#1b1f22'}
    dur = 16.0
    stage = ({'paper_roughness': 0.95, 'curl': 0, 'paper_normal': False, 'grain': 0.075, 'vignette': 0.6,
              'saturation': 0.72, 'tint': '#eef2e6', 'flicker': 0.5, 'fog': {'color': '#7d878c', 'density': 0.0032},
              'background': '#060403'} if film else
             {**assets.style('mate-in-3')['stage'], 'saturation': 0.8, 'tint': '#f2f3ea'})
    return {
        'story': '_lab-tarkovsky', 'format': variant, 'lang': 'en', 'timing': 'lab', 'paragraphs': [],
        'width': 1080, 'height': 1920, 'fps': 24, 'duration': dur, 'preroll': 0, 'speech_end': dur,
        'stage': stage, 'subtitle_style': {'y': 0.735, 'width': 0.82, 'size': 0.0285, 'max_chars': 64},
        'assets': A, 'subtitles': [], 'errors': [],
        'shots': [{'id': 'lab', 'scene': 'lab', 'scene_title': f'Tarkovsky — {variant}', 'at': '0', 't0': 0.0, 't1': dur,
                   'set': 'lab', 'in': 'fade', 'camera': cam, 'focus': {'on': 'doctor', 'f': 0.7},
                   'light': light, 'end': None, 'sfx': [], 'note': variant, 'elements': els}],
    }


def main() -> None:
    redo = set(sys.argv[sys.argv.index('--redo') + 1].split(',')) if '--redo' in sys.argv else set()
    jobs = []
    for name, layer in LAYERS.items():
        seed = random.randint(1, 2**31 - 2) if name in redo else layer['seed']
        for variant in ('cut', 'film'):
            if name in redo or not out_file(variant, name).exists():
                jobs.append((variant, name, seed))
    if jobs:
        print(f'картинок: {len(jobs)} (≈ ${len(jobs) * assets.COST:.2f})')
        with ThreadPoolExecutor(4) as ex:
            total = sum(ex.map(lambda j: make(*j), jobs))
        print(f'итого ${total:.3f}')
    (LAB / 'build').mkdir(parents=True, exist_ok=True)
    for variant in ('cut', 'film'):
        f = LAB / 'build' / f'timeline-{variant}.json'
        f.write_text(json.dumps(timeline(variant), ensure_ascii=False, indent=1))
        print(f'✓ {f.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
