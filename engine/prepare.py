"""Подготовка: исходник истории → stories/<slug>/prepared/<язык>.json — разделы, абзацы, предложения, слова.

Модель текста — как в mountain-rock (абзац → предложения → слова со смещениями), её используют перевод,
озвучка, раскадровка (якоря кадров — абзац и номер предложения) и субтитры.

Форматы исходника (story.json → source.format):
  text      абзацы через пустую строку, один раздел «story»; первые source.skip блоков (автор, название) —
            не озвучиваются (в ролике их нет)
  markdown  разделы — заголовки «#» (как в mountain-rock), для историй с главами
  libru     текст с lib.ru: строки жёстко перенесены, абзац — со строки с отступом, внутри — двойные пробелы;
            блок, где все строки с большим отступом, — эпиграф (курсив); блок из одной римской цифры — заголовок
            главы (kind heading внутри раздела «story»: в ролике не озвучивается, на сайте — «Глава первая»);
            первые source.skip блоков — автор и название
Id абзацев: «<раздел>-001», …; «-000» зарезервирован под заголовок раздела.
Правки абзацев для озвучки (текст для TTS, манера, пропуск) — overrides/<язык>.json, подготовка их не трогает.
"""
from __future__ import annotations

import hashlib
import re

from . import config, text

TRANSLIT = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
                    ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's',
                     't', 'u', 'f', 'h', 'ts', 'ch', 'sh', 'sch', '', 'y', '', 'e', 'yu', 'ya']))


def section_slug(title: str, used: set) -> str:
    t = title.strip().lower().rstrip('.')
    m = re.fullmatch(r'(?:глава|chapter|часть|part)\s+(\d+)', t)
    slug = f'ch{int(m.group(1)):02d}' if m else (
        re.sub(r'[^a-z0-9]+', '-', ''.join(TRANSLIT.get(c, c) for c in t)).strip('-')[:40] or 'section')
    base, n = slug, 2
    while slug in used:
        slug, n = f'{base}-{n}', n + 1
    used.add(slug)
    return slug


def paragraph(pid: str, kind: str, body: str, *, speech: str | None = None, italic: bool = False) -> dict:
    p = {'id': pid, 'kind': kind, 'text': body,
         'sentences': [list(s) for s in text.split_sentences(body)],
         'words': [list(w) for w in text.split_words(body)]}
    if speech:
        p['speech'] = speech
    if italic:
        p['italic'] = True
    return p


def _blocks(raw: str) -> list[str]:
    """Абзацы текста: через пустую строку; строки внутри абзаца склеиваются."""
    return [re.sub(r'\s*\n\s*', ' ', b).strip() for b in re.split(r'\n\s*\n', raw.replace('\r', '')) if b.strip()]


ROMAN_RE = re.compile(r'[IVXLC]+')
EPIGRAPH_INDENT = 20


def _libru_blocks(raw: str) -> list[tuple[str, str]]:
    """lib.ru → [(вид, текст)]: вид — text, epigraph, heading. Абзац начинается строкой с отступом."""
    out = []
    for group in re.split(r'\n\s*\n', raw.replace('\r', '').replace('\t', '    ')):
        lines = [ln.rstrip() for ln in group.split('\n') if ln.strip()]
        if not lines:
            continue
        if len(lines) == 1 and ROMAN_RE.fullmatch(lines[0].strip()):
            out.append(('heading', lines[0].strip()))
            continue
        if all(len(ln) - len(ln.lstrip()) >= EPIGRAPH_INDENT for ln in lines):
            out.append(('epigraph', ' '.join(ln.strip() for ln in lines)))
            continue
        cur = []
        for ln in lines:
            if ln[:1].isspace() and cur:
                out.append(('text', ' '.join(cur)))
                cur = []
            cur.append(ln.strip())
        out.append(('text', ' '.join(cur)))
    return [(k, _libru_clean(b)) for k, b in out]


def _libru_clean(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b([А-ЯЁA-Z])\.(?=[А-ЯЁA-Z][а-яёa-z])', r'\1. ', s)   # «Ф.Купер» → «Ф. Купер»
    s = re.sub(r'"([^"]*)"', r'«\1»', s)                             # прямые кавычки → ёлочки
    s = re.sub(r'^"', '«', s)                                        # цитата на несколько абзацев:
    s = re.sub(r'"(?=[.,!?…]*$)', '»', s)                            # открыта в одном, закрыта в другом
    return s


def prepare(slug: str, *, save: bool = True) -> dict:
    st = config.story(slug)
    src = st['source']
    lang = src['lang']
    raw = (config.ROOT / src['file']).read_text(encoding='utf8')
    sections, used = [], set()
    if src.get('format', 'text') == 'markdown':
        head_re = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
        cur = None
        for b in _blocks(raw):
            m = head_re.match(b)
            if m:
                title = text.strip_markdown(m.group(2), footnotes=False)[0]
                sid = section_slug(title, used)
                cur = {'id': sid, 'title': text.heading_display(title),
                       'paragraphs': [paragraph(f'{sid}-000', 'heading', text.heading_display(title),
                                                speech=text.heading_speech(title, lang))]}
                sections.append(cur)
                continue
            if cur is None:
                continue
            body, italic = text.strip_markdown(b, footnotes=src.get('remove_footnotes', False))
            if re.search(r'\w', body):
                cur['paragraphs'].append(paragraph(f"{cur['id']}-{len(cur['paragraphs']):03d}", 'text', body, italic=italic))
    elif src.get('format') == 'libru':
        cur = {'id': 'story', 'title': (st.get('title') or {}).get(lang, slug), 'paragraphs': []}
        for kind, b in _libru_blocks(raw)[int(src.get('skip', 0)):]:
            body = text.strip_markdown(b, footnotes=False)[0]
            pid = f"story-{len(cur['paragraphs']) + 1:03d}"
            if kind == 'heading':
                cur['paragraphs'].append(paragraph(pid, 'heading', body, speech=text.heading_speech(body, lang)))
            elif re.search(r'\w', body):
                cur['paragraphs'].append(paragraph(pid, 'text', body, italic=kind == 'epigraph'))
        sections.append(cur)
    else:
        blocks = _blocks(raw)[int(src.get('skip', 0)):]
        cur = {'id': 'story', 'title': (st.get('title') or {}).get(lang, slug), 'paragraphs': []}
        for b in blocks:
            body, italic = text.strip_markdown(b, footnotes=False)
            if re.search(r'\w', body):
                cur['paragraphs'].append(paragraph(f"story-{len(cur['paragraphs']) + 1:03d}", 'text', body, italic=italic))
        sections.append(cur)
    for s in sections:
        ps = s['paragraphs']
        s['stats'] = {'paragraphs': len(ps), 'chars': sum(len(p['text']) for p in ps),
                      'words': sum(len(p['words']) for p in ps)}
    out = {'story': slug, 'lang': lang, 'source': src['file'],
           'source_sha': hashlib.sha256(raw.encode()).hexdigest()[:16], 'sections': sections, 'warnings': [],
           'stats': {k: sum(s['stats'][k] for s in sections) for k in ('paragraphs', 'chars', 'words')}}
    if save:
        config.write_json(config.text_dir(slug) / 'prepared' / f'{lang}.json', out)
    return out


def load(slug: str, lang: str) -> dict | None:
    return config.read_json(config.text_dir(slug) / 'prepared' / f'{lang}.json')


def paragraphs(slug: str, lang: str) -> dict[str, dict]:
    """{id: абзац} по всем разделам."""
    prep = load(slug, lang) or {'sections': []}
    return {p['id']: p for s in prep['sections'] for p in s['paragraphs']}


def overrides(slug: str, lang: str) -> dict:
    return config.read_json(config.text_dir(slug) / 'overrides' / f'{lang}.json', {}) or {}


def set_override(slug: str, lang: str, pid: str, patch: dict) -> dict:
    data = overrides(slug, lang)
    cur = {k: v for k, v in {**data.get(pid, {}), **patch}.items() if v not in (None, '', False)}
    if cur:
        data[pid] = cur
    else:
        data.pop(pid, None)
    config.write_json(config.text_dir(slug) / 'overrides' / f'{lang}.json', data)
    return cur


def speech_text(story: dict, para: dict, ov: dict | None = None) -> str:
    """Текст, который уходит в TTS: правка (overrides), иначе текст абзаца с поправками произношения."""
    if ov and ov.get('speech'):
        return ov['speech']
    return text.apply_replacements(para.get('speech') or para['text'], story.get('speech_replacements', []))


if __name__ == '__main__':
    import sys
    for slug in sys.argv[1:] or [s['slug'] for s in config.stories()]:
        r = prepare(slug)
        print(f"{slug}: {len(r['sections'])} разд., {r['stats']['paragraphs']} абз., {r['stats']['chars']} знаков")
