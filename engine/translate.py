"""Translating a story into another language: glossary → paragraph-by-paragraph translation (same ids) → prepared/<lang>.json.

stories/<slug>/glossary.json              names, realia, recurring formulas — one translation for the whole story
stories/<slug>/translations/<lang>.json   {paragraph id: {text, src (fingerprint of the source paragraph), model, at}}

A translation can also be done by hand / in a Claude Code session: the same file, model — whoever translated;
the src fingerprint ties a translation to its source paragraph (the paragraph changed — the translation is "stale").

1. Glossary: an LLM walks the text in chunks and lists proper names and special terms with a single rendering
   in the target language (seeded with the characters from the bible). Edited by hand.
2. Translation: a section's paragraphs go in chunks (~5k chars) together with the glossary entries that occur
   in the chunk and the two previous paragraphs with their translation (coherence). The response is JSON {id: translation}.
   A paragraph whose source text changed is "stale" (src) and gets translated again.
3. build(): prepared/<lang>.json — the same sections and paragraph ids, the text is the translation, with its own sentences and words;
   section headings follow a template («Глава 1» → "Chapter 1"); the front matter is translated too.
Shared paragraph ids link the languages: "this paragraph in the other language" (the site's language switch).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time

from . import config, llm, prepare, text

MODEL = 'anthropic/claude-opus-5.5'
GLOSSARY_MODEL = 'anthropic/claude-sonnet-5.5'
LANG_NAMES = {'en': 'English', 'ru': 'Russian', 'de': 'German', 'fr': 'French', 'es': 'Spanish'}
TITLES = {  # section headings by template (source in ru)
    'en': {'предисловие': 'Foreword', 'введение': 'Introduction', 'послесловие': 'Afterword', 'эпилог': 'Epilogue',
           'пролог': 'Prologue', 'глава': 'Chapter'},
}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:10]


def glossary(slug: str) -> dict:
    return config.read_json(config.text_dir(slug) / 'glossary.json', {'terms': []}) or {'terms': []}


def save_glossary(slug: str, g: dict) -> None:
    config.write_json(config.text_dir(slug) / 'glossary.json', g)


_lock = threading.Lock()  # parallel sections write the translations file


def translations(slug: str, lang: str) -> dict:
    return config.read_json(config.text_dir(slug) / 'translations' / f'{lang}.json', {}) or {}


def _save_translations(slug: str, lang: str, data: dict) -> None:
    config.write_json(config.text_dir(slug) / 'translations' / f'{lang}.json', data)


# ---------------------------------------------------------------- 1. glossary

GLOSSARY_SYSTEM = '''You compile a translation glossary for a story translated from {src} into {dst}.
Extract every proper name and special term that must be translated the same way everywhere: people and spirits,
titles and forms of address, places, events,
period realities (clothing, ranks, institutions), recurring phrases and refrains. Skip ordinary words.
For each: the dictionary (nominative) form in {src}, ONE rendering in {dst} (for transliterated names keep the
established {dst} forms where they exist, e.g. Leipzig; keep refrains word for word),
and a short note (who/what it is). Answer with ONE JSON object only: {{"terms": [{{"src": "…", "dst": "…", "note": "…"}}]}}'''


def build_glossary(slug: str, lang: str, *, model: str = GLOSSARY_MODEL, chunk_chars: int = 60000, log=print) -> float:
    """A glossary over the whole book (extends the existing one: already approved terms don't change)."""
    b = config.story(slug)
    src_lang = b['source']['lang']
    prep = prepare.load(slug, src_lang)
    g = glossary(slug)
    known = {t['src'].lower(): t for t in g['terms']}
    bible = config.read_json(config.story_dir(slug) / 'bible.json', {}) or {}
    seed = [{'src': c.get('name_src', ''), 'dst': c.get('name', ''), 'note': c.get('role', '')}
            for c in (bible.get('characters') or {}).values() if c.get('name_src')]
    text_all = [f"{p['text']}" for s in prep['sections'] for p in s['paragraphs']]
    text_all += [x['text'] for x in prep.get('front', []) if x.get('text')]
    chunks, cur = [], ''
    for t in text_all:
        if len(cur) + len(t) > chunk_chars and cur:
            chunks.append(cur)
            cur = ''
        cur += t + '\n'
    if cur:
        chunks.append(cur)
    system = GLOSSARY_SYSTEM.format(src=LANG_NAMES.get(src_lang, src_lang), dst=LANG_NAMES.get(lang, lang))
    cost = 0.0
    for i, ch in enumerate(chunks):
        have = [{'src': t['src'], 'dst': t['dst']} for t in g['terms']] or seed
        user = (f"Terms already in the glossary (reuse exactly, do not repeat them):\n{json.dumps(have, ensure_ascii=False)}\n\n"
                f"Text (part {i + 1} of {len(chunks)}):\n{ch}")
        r, c = llm.chat_json([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                             model=model, max_tokens=12000, temperature=0.2)
        cost += c
        added = 0
        for t in r.get('terms') or []:
            k = (t.get('src') or '').strip().lower()
            if k and t.get('dst') and k not in known:
                known[k] = {'src': t['src'].strip(), 'dst': t['dst'].strip(), 'note': (t.get('note') or '').strip()}
                g['terms'].append(known[k])
                added += 1
        g['log'] = {'model': model, 'cost': round(g.get('log', {}).get('cost', 0) + c, 4), 'at': time.strftime('%Y-%m-%d %H:%M')}
        save_glossary(slug, g)
        log(f'✓ glossary, part {i + 1}/{len(chunks)}: +{added} (total {len(g["terms"])}), ${c:.4f}')
    return cost


def _stem(word: str) -> str:
    w = word.lower().replace('ё', 'е')
    return w if len(w) <= 3 else w[:max(3, len(w) - 2)]


def terms_for(g: dict, chunk: str) -> list[dict]:
    """Glossary entries that occur in a chunk (by word stem — so inflected forms match)."""
    low = chunk.lower().replace('ё', 'е')
    out = []
    for t in g['terms']:
        parts = re.findall(r'\w+', t['src'])
        # a part of a name — from the start of a word (inflections — by stem); short parts — only as a whole word
        if parts and all(re.search(rf'\b{re.escape(p.lower().replace("ё", "е"))}\b' if len(p) <= 3
                                   else rf'\b{re.escape(_stem(p))}', low) for p in parts):
            out.append({'src': t['src'], 'dst': t['dst']})
    return out


# ---------------------------------------------------------------- 2. translation

SYSTEM = '''You are a literary translator. Translate a {src} story into {dst} for narration (voice-over and subtitles).
The story: «{title}» by {author} — {context}
Render it as fine, natural literary {dst}: faithful in meaning, imagery, rhythm and tone (the period voice of the
original — hesitations, ellipses, old-fashioned politeness), never paraphrased or shortened, without modern slang. Keep every paragraph as one paragraph — the ids must map one to one.
Dialogue: use {dst} quotation conventions (for English: “double curly quotes”, speech tags as in English prose).
Keep ellipses and exclamations where they carry emotion. Use the glossary renderings EXACTLY for names and terms.
Numbers as in the text. No notes, no comments, no brackets with explanations.
Answer with ONE JSON object only: {{"<paragraph id>": "<translation>", …}} for all given ids.'''


def chunks(paras: list[dict], max_chars: int = 5000) -> list[list[dict]]:
    out, cur, n = [], [], 0
    for p in paras:
        if cur and n + len(p['text']) > max_chars:
            out.append(cur)
            cur, n = [], 0
        cur.append(p)
        n += len(p['text'])
    if cur:
        out.append(cur)
    return out


def section_title(title: str, lang: str) -> str | None:
    """«Глава 7» → "Chapter 7", «Предисловие» → "Foreword"; not matching a template — None (the model translates it)."""
    t = title.strip().lower()
    m = re.fullmatch(r'глава\s+(\d+)', t)
    names = TITLES.get(lang, {})
    if m and 'глава' in names:
        return f"{names['глава']} {m.group(1)}"
    return names.get(t)


def status(slug: str, lang: str) -> dict:
    """How many paragraphs are translated / stale / pending, per section."""
    src = prepare.load(slug, config.story(slug)['source']['lang'])
    tr = translations(slug, lang)
    out = {}
    for s in src['sections']:
        c = {'done': 0, 'stale': 0, 'pending': 0, 'chars': 0}
        for p in s['paragraphs']:
            if p['kind'] == 'heading':
                continue
            t = tr.get(p['id'])
            k = 'pending' if not t else ('stale' if t.get('src') != _sha(p['text']) else 'done')
            c[k] += 1
            if k != 'done':
                c['chars'] += len(p['text'])
        out[s['id']] = c
    front = [x for x in src.get('front', []) if x.get('text')]
    out['front'] = {'done': sum(1 for i, x in enumerate(front) if tr.get(f'front-{i:03d}', {}).get('src') == _sha(x['text'])),
                    'total': len(front)}
    return out


def translate_sections(slug: str, lang: str, sections: list[str], *, model: str = MODEL, force: bool = False,
                       front: bool = False, job=None, log=print) -> float:
    """Translate the paragraphs of sections (untranslated and stale; force — all). front — the front matter too."""
    b = config.story(slug)
    src_lang = b['source']['lang']
    prep = prepare.load(slug, src_lang)
    g = glossary(slug)
    system = SYSTEM.format(src=LANG_NAMES.get(src_lang, src_lang), dst=LANG_NAMES.get(lang, lang),
                           title=b['title'].get(lang) or b['title'].get(src_lang), author=b.get('author', {}).get(lang, ''),
                           context=b.get('art_context', ''))  # noqa: E501
    units = []  # (section id, paragraphs)
    for s in prep['sections']:
        if s['id'] in sections:
            units.append((s['id'], [p for p in s['paragraphs'] if p['kind'] != 'heading']))
    if front:
        # numbering — by the text blocks of the front matter (pictures don't count), as in status() and build()
        fr = [{'id': f'front-{i:03d}', 'text': x['text']}
              for i, x in enumerate([x for x in prep.get('front', []) if x.get('text')])]
        units.insert(0, ('front', fr))
    cost = 0.0
    for sid, paras in units:
        tr = translations(slug, lang)
        todo = [p for p in paras if force or tr.get(p['id'], {}).get('src') != _sha(p['text'])]
        if not todo:
            continue
        parts = chunks(todo)
        if job:
            job.total += len(parts)
        for part in parts:
            if job:
                job.check()
            ids = [p['id'] for p in part]
            # context: the two previous paragraphs of the section with their translation
            first = next(i for i, p in enumerate(paras) if p['id'] == ids[0])
            ctx = [{'id': p['id'], 'src': p['text'], 'translation': tr[p['id']]['text']}
                   for p in paras[max(0, first - 2):first] if p['id'] in tr]
            body = '\n\n'.join(f"[{p['id']}] {p['text']}" for p in part)
            user = (f"Glossary for this passage:\n{json.dumps(terms_for(g, body), ensure_ascii=False)}\n\n"
                    + (f"Previous paragraphs (already translated, for continuity):\n{json.dumps(ctx, ensure_ascii=False)}\n\n" if ctx else '')
                    + f"Translate these paragraphs ({len(part)}):\n{body}")
            got, c = {}, 0.0
            for attempt in range(3):
                r, c1 = llm.chat_json([{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                                      model=model, max_tokens=16000, temperature=0.3)
                c += c1
                got.update({k: v for k, v in r.items() if k in ids and isinstance(v, str) and v.strip()})
                missing = [i for i in ids if i not in got]
                if not missing:
                    break
                log(f'  {sid}: no translation for {", ".join(missing)} — retrying')
                user = user.rsplit('Translate these paragraphs', 1)[0] + 'Translate these paragraphs ({}):\n{}'.format(
                    len(missing), '\n\n'.join(f"[{p['id']}] {p['text']}" for p in part if p['id'] in missing))
            with _lock:
                tr = translations(slug, lang)
                for p in part:
                    if p['id'] in got:
                        tr[p['id']] = {'text': got[p['id']].strip(), 'src': _sha(p['text']), 'model': model,
                                       'at': time.strftime('%Y-%m-%d %H:%M')}
                _save_translations(slug, lang, tr)
            cost += c
            if job:
                job.step(len(got) == len(ids), c)
            log(f'✓ {sid}: {ids[0]}…{ids[-1]} ({len(got)}/{len(ids)}), ${c:.4f}')
    return cost


def set_translation(slug: str, lang: str, pid: str, text_: str) -> dict:
    """Edit a paragraph's translation from the admin."""
    src = prepare.load(slug, config.story(slug)['source']['lang'])
    para = next((p for s in src['sections'] for p in s['paragraphs'] if p['id'] == pid), None)
    if para is None:
        front = [x for x in src.get('front', []) if x.get('text')]
        i = int(pid.split('-')[1]) if pid.startswith('front-') else -1
        if not 0 <= i < len(front):
            raise KeyError(f'no paragraph {pid}')
        para = {'text': front[i]['text']}
    with _lock:
        tr = translations(slug, lang)
        tr[pid] = {'text': text_.strip(), 'src': _sha(para['text']), 'model': 'edited', 'at': time.strftime('%Y-%m-%d %H:%M')}
        _save_translations(slug, lang, tr)
    return tr[pid]


# ---------------------------------------------------------------- 3. the prepared text in the target language

def build(slug: str, lang: str, *, save: bool = True) -> dict:
    """prepared/<lang>.json from the translation: sections where every paragraph is translated; the same ids."""
    b = config.story(slug)
    src = prepare.load(slug, b['source']['lang'])
    tr = translations(slug, lang)
    sections, missing = [], {}
    for s in src['sections']:
        title = section_title(s['title'], lang) or (tr.get(s['paragraphs'][0]['id']) or {}).get('text') \
            or (b.get('title') or {}).get(lang) or s['title']
        paras, ok = [], True
        for p in s['paragraphs']:
            if p['kind'] == 'heading':
                # the section heading (-000) — by template; a chapter number inside a section ("II") — as is
                h = title if p['id'].endswith('-000') else (section_title(p['text'], lang) or p['text'])
                paras.append(prepare.paragraph(p['id'], 'heading', h, speech=text.heading_speech(h, lang)))
                continue
            t = tr.get(p['id'])
            if not t:
                ok = False
                missing[s['id']] = missing.get(s['id'], 0) + 1
                continue
            paras.append(prepare.paragraph(p['id'], p['kind'], t['text'], italic=p.get('italic', False)))
        if ok:
            st = {'paragraphs': len(paras), 'chars': sum(len(p['text']) for p in paras), 'words': sum(len(p['words']) for p in paras)}
            sections.append({'id': s['id'], 'title': title, 'paragraphs': paras, 'stats': st})
    front = []
    k = 0
    for x in src.get('front', []):
        if x.get('text'):
            t = tr.get(f'front-{k:03d}')
            k += 1
            if t:
                front.append({**x, 'text': t['text']})
        else:
            front.append(x)
    out = {'story': slug, 'lang': lang, 'source': f"translation:{b['source']['lang']}", 'source_sha': src['source_sha'],
           'sections': sections, 'warnings': [f'{sid}: untranslated paragraphs — {n}' for sid, n in missing.items()],
           'front': front if k and len(front) == len(src.get('front', [])) else [],
           'stats': {key: sum(s['stats'][key] for s in sections) for key in ('paragraphs', 'chars', 'words')}}
    if save:
        config.write_json(config.text_dir(slug) / 'prepared' / f'{lang}.json', out)
    return out
