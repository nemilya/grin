"""Тесты движка без сети: подготовка текста, реплики раскадровки, разворачивание сцены, субтитры, план ассетов."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import align, assets, prepare, text, timeline, translate  # noqa: E402

SLUG = 'mate-in-3'


class TextTest(unittest.TestCase):
    def test_english_sentences(self):
        t = '“Misha!” And I hear. There were two madmen — he and I. His panic grew. ‘Go to the devil!’ Very well, sir.'
        got = [t[a:b] for a, b in text.split_sentences(t)]
        self.assertEqual(got, ['“Misha!”', 'And I hear.', 'There were two madmen — he and I.', 'His panic grew.',
                               '‘Go to the devil!’', 'Very well, sir.'])

    def test_dialogue_dash(self):
        s, _ = text.strip_markdown('- Чем вы больны? - спросил я.')
        self.assertEqual(s, '— Чем вы больны? — спросил я.')


class PrepareTest(unittest.TestCase):
    def test_title_not_spoken(self):
        r = prepare.prepare(SLUG, save=False)
        first = r['sections'][0]['paragraphs'][0]
        self.assertEqual(first['id'], 'story-001')
        self.assertTrue(first['text'].startswith('Случай этот'))  # автор и название (skip: 2) не озвучиваются
        self.assertEqual(r['stats']['paragraphs'], 46)

    def test_translation_complete(self):
        st = translate.status(SLUG, 'en')['story']
        self.assertEqual(st['pending'] + st['stale'], 0)

    def test_libru(self):
        """lib.ru: абзацы по отступу, переносы склеены, эпиграф — курсивом, «I», «II» — заголовки глав."""
        r = prepare.prepare('sila-nepost', save=False)
        ps = r['sections'][0]['paragraphs']
        self.assertEqual(len(ps), 34)
        self.assertTrue(ps[0]['italic'] and ps[0]['text'].endswith('Ф. Купер. «Мерседес-де-Кастилья».'))
        self.assertEqual([(p['id'], p['text'], p['speech']) for p in ps if p['kind'] == 'heading'],
                         [('story-002', 'I', 'Глава первая.'), ('story-009', 'II', 'Глава вторая.')])
        self.assertTrue(ps[2]['text'].startswith('Среди людей, обладающих') and '  ' not in ps[2]['text'])
        self.assertEqual(ps[7]['text'], 'Грациан Дюплэ был скрипач.')
        en = translate.build('sila-nepost', 'en', save=False)['sections'][0]['paragraphs']
        self.assertEqual([(p['text'], p['speech']) for p in en if p['kind'] == 'heading'], [('I', 'Chapter 1.'), ('II', 'Chapter 2.')])

    def test_intertitles(self):
        """Интертитры: текст эпиграфа — на языке ролика, подпись отдельно; заглавная карточка — автор и название."""
        for lang, attr in ((None, 'J. Fenimore Cooper, “Mercedes of Castile”.'), ('ru', 'Ф. Купер. «Мерседес-де-Кастилья».')):
            tl = timeline.build('sila-nepost', save=False, lang=lang)
            self.assertEqual(tl['errors'], [])
            self.assertEqual(tl['assets']['prop/title-epigraph']['attr'], attr)
            self.assertFalse(any(x['p'] == 'story-001' for x in tl['subtitles']))  # эпиграф — титром, без субтитров
        self.assertEqual(tl['assets']['prop/title-main']['lines'], ['Александр Грин', 'Сила непостижимого'])

    def test_quote_across_paragraphs(self):
        """Ответ Посвящения — цитата на несколько строк-абзацев: открывающая и закрывающая кавычки — ёлочки."""
        ps = {p['id']: p['text'] for p in prepare.prepare('leaf-story', save=False)['sections'][0]['paragraphs']}
        self.assertEqual(len(ps), 32)
        self.assertTrue(ps['story-010'].startswith('«Тому, чье имя ныне'))
        self.assertTrue(ps['story-012'].endswith('разрушь и проснись».'))
        self.assertNotIn('"', ''.join(ps.values()))

    def test_align_extra_tail(self):
        """Модель озвучки дочитала абзац и сочинила продолжение — конец «не узнан» (дубль переделывается)."""
        src = 'знать всю сокровенную сущность человеческой личности'.split()
        rec = lambda ws: [{'word': w, 'start': i, 'end': i + 0.5} for i, w in enumerate(ws)]  # noqa: E731
        self.assertEqual(align.align(src, rec(src), 6)[1:], (1.0, True))
        self.assertTrue(align.align(src, rec(src + ['ну']), 7)[2])                        # вдох, междометие — допуск
        self.assertEqual(align.align(src, rec(src + 'если хочешь ты о царь'.split()), 11)[1:], (1.0, False))

    def test_roman(self):
        self.assertEqual([text.roman(x) for x in ('I', 'IV', 'IX', 'XIV', 'Ivan', '')], [1, 4, 9, 14, None, None])


class TimelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = timeline.build(SLUG, save=False)

    def test_no_errors_and_order(self):
        self.assertEqual(self.tl['errors'], [])
        t0 = [s['t0'] for s in self.tl['shots']]
        self.assertEqual(t0, sorted(t0))
        self.assertTrue(all(s['t1'] > s['t0'] for s in self.tl['shots']))

    def test_cue(self):
        times = {'story-018': {'sentences': [[0, 5, 10.0, 12.0], [6, 9, 12.5, 14.5]]}}
        self.assertAlmostEqual(timeline.cue_time('018.1', times), 12.5 - timeline.CUT_LEAD)
        self.assertAlmostEqual(timeline.cue_time('018.1+0.5', times), 13.5)
        with self.assertRaises(ValueError):
            timeline.cue_time('018.7', times)

    def test_state_carries_and_sets_filter(self):
        shots = {s['id']: s for s in self.tl['shots']}
        ids = lambda s: {e['id'] for e in s['elements']}  # noqa: E731
        self.assertIn('doctor', ids(shots['s03a']))                 # доктор остаётся в кабинете
        self.assertNotIn('doctor', ids(shots['s05g']))              # но не виден в чужой декорации (окно)
        self.assertIn('window:room-wall', ids(shots['s05g']))
        pat = next(e for e in shots['s03h']['elements'] if e['id'] == 'patient')
        self.assertEqual(pat['card'], 'patient/seated-up')
        # движение доехало: в следующем кадре стартовая позиция = конечная прошлого
        a = next(e for e in shots['s02a']['elements'] if e['id'] == 'patient')
        b = next(e for e in shots['s02b']['elements'] if e['id'] == 'patient')
        end = a['move']['keys'][-1][1] if a['move'].get('keys') else a['move']['to']
        self.assertEqual(b['pos'], end)                              # маршрут (keys) — с последней точки

    def test_walls_reset(self):
        shots = {s['id']: s for s in self.tl['shots']}
        wall = next(e for e in shots['s10f']['elements'] if e['id'] == 'office:wall')
        self.assertEqual(wall['pos'], timeline.bible(SLUG)['sets']['office']['pieces']['wall']['pos'])
        self.assertNotIn('move', wall)

    def test_subtitles(self):
        subs = self.tl['subtitles']
        self.assertTrue(all(len(s['text']) <= timeline.SUB_MAX_CHARS + 12 for s in subs))
        self.assertTrue(all(b['t0'] >= a['t1'] - 1e-6 for a, b in zip(subs, subs[1:])))

    def test_cut(self):
        c = timeline.cut(self.tl, 's12a', 's13a')
        self.assertEqual(c['shots'][0]['id'], 's12a')
        self.assertEqual(c['shots'][0]['t0'], 0.0)
        self.assertEqual(c['shots'][-1]['id'], 's12h')
        self.assertAlmostEqual(c['shots'][-1]['t1'], c['duration'], places=2)


class GeometryTest(unittest.TestCase):
    def test_settle_fall_grow(self):
        """Лист упал — в следующем кадре лежит, где упал; линия дорисована (grow снят), вращение продолжается."""
        el = timeline._settle({'card': 'prop/leaf', 'pos': [3, 24, -7], 'rot': [0, 0, 25], 'grow': [0, 1],
                               'fall': {'to': [1.6, 7.2, -8.2], 'rot_to': [-62, 20, -12]}, 'spin': {'speed': 90}})
        self.assertEqual((el['pos'], el['rot']), ([1.6, 7.2, -8.2], [-62, 20, -12]))
        self.assertNotIn('fall', el)
        self.assertNotIn('grow', el)
        self.assertIn('spin', el)

    def test_leaf_story(self):
        """Постановка «Отпавшего Листа» собирается; интертитр «I» — в паузе перед первой репликой (002.0-4.5)."""
        tl = timeline.build('leaf-story', save=False)
        self.assertEqual(tl['errors'], [])
        shots = {s['id']: s for s in tl['shots']}
        self.assertAlmostEqual(shots['a01']['t0'] - shots['t02']['t0'], 4.5, places=2)
        self.assertEqual(tl['assets']['prop/fire-ring']['draw'], 'shape')
        self.assertIn('spin', {e['id']: e for e in shots['f05']['elements']}['ring'])

    def test_leaf_story_vertical(self):
        """Вертикаль 9:16 — те же кадры и реплики по времени (звук общий), свои камеры."""
        h = timeline.build('leaf-story', save=False)
        v = timeline.build('leaf-story', save=False, fmt='vertical')
        self.assertEqual(v['errors'], [])
        self.assertEqual((v['width'], v['height']), (1080, 1920))
        self.assertEqual([(s['id'], s['t0']) for s in v['shots']], [(s['id'], s['t0']) for s in h['shots']])
        cam = lambda tl, sid: next(s for s in tl['shots'] if s['id'] == sid)['camera']['from']['pos']  # noqa: E731
        self.assertNotEqual(cam(v, 'f05'), cam(h, 'f05'))      # сфера — дальше: помещается в узкий кадр


class SoundTest(unittest.TestCase):
    def test_beds_and_motor(self):
        """Фоны смешиваются («birds+crowd*0.5»), мотор следует ключам громкости (обрыв — тишина), новые шумы есть."""
        import numpy as np
        from engine import sound
        x = sound.bed('birds+crowd*0.5+tram', 2.0, seed=1)
        self.assertEqual(len(x), 2 * sound.SR)
        self.assertTrue(np.isfinite(x).all() and np.abs(x).max() > 0)
        m = sound.motor(2.0, env=[[0, 0], [0.5, 0], [0.51, -90], [1, -90]])
        half = len(m) // 2
        self.assertLess(np.abs(m[half + 2000:]).max(), np.abs(m[:half]).max() * 1e-3)
        for name in ('boom', 'tram-bell'):
            self.assertGreater(np.abs(sound.sfx(name, 3.0)).max(), 0)


class SoundSignatureTest(unittest.TestCase):
    def test_only_used_code(self):
        """Отпечаток звука — код, который постановка звучит: новый фон или шум для одной постановки не трогает другие."""
        from engine import sound
        sig = {st: sound.signature(timeline.storyboard(st), timeline.build(st, save=False))
               for st in ('mate-in-3', 'sila-nepost', 'leaf-story')}
        for st in ('mate-in-3', 'sila-nepost'):
            for code in ('def crowd', 'def motor', 'def tram', "if name == 'boom'"):
                self.assertNotIn(code, sig[st], st)
        self.assertIn('def clock', sig['mate-in-3'])
        self.assertIn('def room', sig['sila-nepost'])        # projector → room (зависимость по вызову)
        for code in ('def build', 'def crowd', 'def motor', "if name == 'boom'", 'def _bell'):
            self.assertIn(code, sig['leaf-story'])

    def test_comments_do_not_count(self):
        """Comments and docstrings are not part of the fingerprint: translating them doesn't rebuild the sound."""
        from engine import sound
        a = 'def f(x):\n    """Тон."""\n    # громкость\n    return x * 0.5  # половина\n'
        b = 'def f(x):\n    """Tone."""\n    # volume\n\n    return x * 0.5  # half\n'
        self.assertEqual(sound._code_only(a), sound._code_only(b))
        self.assertNotEqual(sound._code_only(a), sound._code_only(a.replace('0.5', '0.6')))
        branch = "    if name == 'click':  # выключатель\n        return 1\n"
        self.assertIn("if name == 'click'", sound._code_only(branch))


class FormatTest(unittest.TestCase):
    def test_horizontal_overlay(self):
        h = timeline.build(SLUG, save=False, fmt='horizontal')
        v = timeline.build(SLUG, save=False)
        self.assertEqual(h['errors'], [])
        self.assertEqual((h['width'], h['height']), (1920, 1080))
        self.assertEqual([s['t0'] for s in h['shots']], [s['t0'] for s in v['shots']])  # реплики общие
        hs = {s['id']: s for s in h['shots']}
        vs = {s['id']: s for s in v['shots']}
        self.assertNotEqual(hs['s03a']['camera'], vs['s03a']['camera'])    # камеры 16:9 свои
        self.assertEqual(hs['s05i']['camera']['name'], 'win-wide')          # правка кадра из storyboard-16x9
        self.assertEqual({e['id'] for e in hs['s05g']['elements']}, {e['id'] for e in vs['s05g']['elements']})
        self.assertGreater(h['subtitle_style']['max_chars'], v['subtitle_style']['max_chars'])

    def test_overlay_drop_add(self):
        import json, tempfile, shutil
        from engine import config
        d = config.story_dir(SLUG)
        tmp = d / 'storyboard-test.json'
        tmp.write_text(json.dumps({'extends': 'storyboard.json', 'drop': ['s03b'],
                                   'add': [{'after': 's03c', 'id': 's03c2', 'at': '006.0+0.5', 'cam': 'desk'}]}))
        try:
            st = config.story(SLUG)
            orig = (d / 'story.json').read_text()
            st2 = json.loads(orig)
            st2['formats']['test'] = {'width': 1920, 'height': 1080, 'storyboard': 'storyboard-test.json'}
            (d / 'story.json').write_text(json.dumps(st2, ensure_ascii=False))
            ids = [s['id'] for sc in timeline.storyboard(SLUG, 'test')['scenes'] for s in sc['shots']]
            self.assertNotIn('s03b', ids)
            self.assertEqual(ids[ids.index('s03c') + 1], 's03c2')
        finally:
            (d / 'story.json').write_text(orig)
            tmp.unlink()

    def test_chapters_srt(self):
        tl = timeline.build(SLUG, save=False, fmt='horizontal')
        ch = timeline.chapters(tl)
        self.assertEqual(ch[0][0], 0.0)
        self.assertGreaterEqual(len(ch), 3)
        self.assertTrue(all(b[0] - a[0] >= 10 for a, b in zip(ch, ch[1:])))
        srt = timeline.srt(tl)
        self.assertTrue(srt.startswith('1\n00:00:'))
        self.assertIn(' --> ', srt)


class ProductionTest(unittest.TestCase):
    """Постановка: текст и голос — базовой истории, свои библия/раскадровка/стиль; паузы; режиссёр."""
    P = 'mate-in-3-tarkovsky'

    def test_base_and_style(self):
        from engine import config
        st = config.story(self.P)
        self.assertEqual(st['source'], config.story(SLUG)['source'])           # текст — базовой истории
        self.assertEqual(st['film']['voicing'], 'narrator-en')                 # голос — тоже
        self.assertEqual(st['film']['style'], 'tarkovsky-film')
        self.assertEqual(config.text_dir(self.P), config.story_dir(SLUG))
        pl = {it['key']: it for it in assets.plan(self.P)}
        self.assertNotIn('paper cut-out puppet', pl['doctor/seated']['prompt'])   # формулировки стиля, не театра
        self.assertIn('isolated figure', pl['doctor/seated']['prompt'])
        self.assertNotIn('window/floor', pl)                                    # card — чужая карточка, не рисуем

    def test_holds_and_director(self):
        tl = timeline.build(self.P, save=False)
        base = timeline.build(SLUG, save=False)
        self.assertEqual(tl['errors'], [])
        self.assertGreater(tl['duration'], base['duration'] + 60)              # паузы удлиняют фильм
        p18 = next(p for p in tl['paragraphs'] if p['id'] == 'story-018')
        self.assertEqual(p18['cuts'][0][1], 3.0)                               # пауза внутри абзаца → разрез дубля
        self.assertTrue(all(s['camera']['hand'] == 0 for s in tl['shots']))     # штатив — умолчание режиссёра
        doc = tl['assets']['doctor/seated']
        self.assertTrue(doc['soft'] and doc['cast'] is False)                  # слои стиля: мягкий край, без тени

    def test_horizontal(self):
        h = timeline.build(self.P, save=False, fmt='horizontal')
        v = timeline.build(self.P, save=False)
        self.assertEqual(h['errors'], [])
        self.assertEqual((h['width'], h['height']), (1920, 1080))
        self.assertEqual([s['t0'] for s in h['shots']], [s['t0'] for s in v['shots']])   # паузы и реплики общие
        self.assertNotEqual(h['shots'][0]['camera'], v['shots'][0]['camera'])            # камеры 16:9 свои

    def test_holds_shift_sentences(self):
        t0, _ = timeline.speech_times(SLUG)
        t1, _ = timeline.speech_times(SLUG, {'018.16': 3, '018': 2})
        a, b = t0['story-018']['sentences'], t1['story-018']['sentences']
        self.assertEqual(a[16], b[16])                                         # до паузы — как было
        self.assertAlmostEqual(b[17][2] - a[17][2], 3, places=2)               # после — сдвиг на паузу
        self.assertAlmostEqual(t1['story-019']['t0'] - t0['story-019']['t0'], 5, places=2)


class LangTest(unittest.TestCase):
    """Ролик на другом языке: реплики и паузы раскадровки (по английским предложениям) переносятся по доле текста."""

    def test_time_at_and_cue(self):
        para = {'text': 'aaaa bbbb cccc dddd', 't1': 20.0,
                'words': [[0, 4, 10.0, 11.0], [5, 9, 11.5, 12.5], [10, 14, 13.0, 14.0], [15, 19, 14.5, 15.5]],
                'sentences': [[0, 9, 10.0, 12.5], [10, 19, 13.0, 15.5]]}
        self.assertAlmostEqual(timeline._time_at(para, 0.0), 10.0)
        self.assertAlmostEqual(timeline._time_at(para, 10 / 19), 13.0)                # начало третьего слова
        src = {'story-001': {'text': 'Xx yy. Zz ww.', 'sentences': [[0, 6], [7, 13]]}}
        times = {'story-001': para}
        t = timeline.cue_time('001.1+0.5', times, src)                                 # середина 2-го англ. предложения
        self.assertTrue(13.0 <= t <= 15.5)

    def test_map_holds(self):
        prep_ru = {'sections': [{'paragraphs': [{'id': 'story-018', 'text': 'А б. В г. Д е.',
                                                 'sentences': [[0, 4], [5, 9], [10, 14]]}]}]}
        got = timeline._map_holds({'018': 2}, SLUG, 'en', 'ru', prep_ru)
        self.assertEqual(got, {'018': 2})                                               # паузы после абзаца — как есть

    def test_tag(self):
        self.assertEqual(timeline.tag(), '')
        self.assertEqual(timeline.tag('horizontal', 'demo', 'ru'), 'horizontal-ru-demo')


class SiteTest(unittest.TestCase):
    def test_site_json(self):
        """site.json: рассказы, озвучки, постановки и кадры постеров существуют; адрес — grin.nemilya.me."""
        from engine import config
        cfg = config.site_config()
        self.assertEqual(cfg['url'], 'https://grin.nemilya.me')
        self.assertEqual(cfg['default_lang'], 'en')
        for item in cfg['stories']:
            st = config.story(item['story'])
            for lang, vid in item['voicings'].items():
                self.assertTrue((config.text_dir(item['story']) / 'voicings' / vid / 'voicing.json').exists(), vid)
            self.assertNotIn('summary', item)  # без пересказа на сайте — никаких спойлеров
            for v in item['videos']:
                self.assertTrue(v['about']['en'] and v['about']['ru'] and len(v['about']['en']) < 120)  # о стиле — коротко
                self.assertEqual(config.story(v['production']).get('base', item['story']), item['story'])
                ids = {s['id'] for sc in timeline.storyboard(v['production'])['scenes'] for s in sc['shots']}
                self.assertIn(v['poster'][0], ids)
            self.assertTrue(st['title'].get('en') and st['title'].get('ru'))


class AssetsTest(unittest.TestCase):
    def test_plan(self):
        pl = {it['key']: it for it in assets.plan(SLUG)}
        self.assertEqual(pl['patient/seated']['refs'], ['refs/patient'])   # позы — с листом героя
        self.assertEqual(pl['patient/arm-upper']['refs'], [])               # детали куклы — без
        self.assertIn('#00FF00', pl['patient/seated']['prompt'])
        self.assertNotIn('office/stars', pl)                                 # процедурное рисует сцена
        self.assertNotIn('refs/funeral', pl)                                 # у силуэтов нет листа
        self.assertEqual(assets.ratio(0.5), '9:16')

    def test_match_key(self):
        """key_match: фон и просвет цвета фона (в тени) — прозрачны; зелёный мазок на одежде (бледнее фона) — нет;
        keep — мазок цвета фона по месту (полоса на подносе) — тоже нет."""
        import subprocess
        import tempfile
        import numpy as np
        img = np.zeros((200, 200, 3), np.uint8)
        img[:] = (40, 225, 20)                                              # фон
        img[20:180, 20:180] = (200, 60, 50)                                 # фигура
        img[40:60, 30:90] = (80, 170, 75)                                   # мазок на одежде: бледнее фона
        img[100:140, 100:160] = (35, 190, 25)                               # просвет в тени (между ножками скамьи)
        img[100:120, 30:80] = (40, 225, 20)                                 # мазок цвета фона — под keep
        png = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '200x200', '-i', 'pipe:0',
                              '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                             input=img.tobytes(), capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'f.png'
            assets.key_out(png, out, crop=False, match=True, keep=[[0.1, 0.45, 0.45, 0.65]])
            a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(out), '-f', 'rawvideo', '-pix_fmt', 'rgba',
                                              'pipe:1'], capture_output=True, check=True).stdout, np.uint8).reshape(200, 200, 4)
        self.assertEqual(a[5, 5, 3], 0)                                     # фон
        self.assertEqual(a[50, 60, 3], 255)                                 # мазок на одежде
        self.assertLess(a[120, 130, 3], 30)                                 # просвет
        self.assertEqual(a[110, 55, 3], 255)                                # keep

    def test_magenta_key(self):
        """Зелёный предмет (лист) — на мадженте: фон прозрачный, предмет цел, на краю нет розового."""
        import subprocess
        import tempfile
        import numpy as np
        img = np.zeros((64, 64, 3), np.uint8)
        img[:] = (255, 0, 255)
        img[16:48, 16:48] = (60, 150, 40)                                   # лист
        img[48:52, 16:48] = (140, 10, 120)                                  # тень на мадженте
        png = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '64x64', '-i', 'pipe:0',
                              '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                             input=img.tobytes(), capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'leaf.png'
            assets.key_out(png, out, crop=False, key='magenta')
            a = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(out), '-f', 'rawvideo', '-pix_fmt', 'rgba',
                                              'pipe:1'], capture_output=True, check=True).stdout, np.uint8).reshape(64, 64, 4)
        self.assertEqual(a[2, 2, 3], 0)                                     # фон
        self.assertEqual(tuple(a[32, 32]), (60, 150, 40, 255))              # лист не тронут
        vis = a[..., 3] > 16
        self.assertFalse((vis & (a[..., 0] > a[..., 1] + 8) & (a[..., 2] > a[..., 1] + 8)).any())   # без розового ореола


if __name__ == '__main__':
    unittest.main()
