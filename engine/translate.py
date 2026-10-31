"""Перевод истории на другой язык: глоссарий → перевод по абзацам (те же id) → prepared/<язык>.json.
(Из mountain-rock: тот же формат и те же правила.)

stories/<slug>/glossary.json              имена, реалии, повторяющиеся формулы — один перевод на всю историю
stories/<slug>/translations/<язык>.json   {id абзаца: {text, src (отпечаток исходного абзаца), model, at}}

Перевод можно сделать и вручную / в сессии Claude Code (skill translate): тот же файл, model — кто переводил;
отпечаток src связывает перевод с исходным абзацем (поменялся абзац — перевод «устарел»).

1. Глоссарий: LLM проходит текст кусками и выписывает собственные имена и особые термины с одним вариантом
   на языке перевода (в основе — герои из библии). Правится руками.
2. Перевод: абзацы раздела идут кусками (~5 тыс. знаков) вместе со статьями глоссария, которые в куске
   встречаются, и двумя предыдущими абзацами с их переводом (связность). Ответ — JSON {id: перевод}.
   Абзац, у которого поменялся исходный текст, — «устаревший» (src), переводится заново.
3. build(): prepared/<язык>.json — те же разделы и id абзацев, текст — перевод, свои предложения и слова;
   заголовки разделов — по шаблону («Глава 1» → «Chapter 1»), вступление (front) — тоже переводится.
Общие id абзацев связывают языки: «этот абзац на другом языке» (переключатель языка на сайте).
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
TITLES = {  # заголовки разделов по шаблону (исходник ru)
    'en': {'предисловие': 'Foreword', 'введение': 'Introduction', 'послесловие': 'Afterword', 'эпилог': 'Epilogue',
           'пролог': 'Prologue', 'глава': 'Chapter'},
}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:10]


def glossary(slug: str) -> dict:
    return config.read_json(config.text_dir(slug) / 'glossary.json', {'terms': []}) or {'terms': []}


def save_glossary(slug: str, g: dict) -> None:
    config.write_json(config.text_dir(slug) / 'glossary.json', g)


_lock = threading.Lock()  # файл переводов пишут параллельные разделы


def translations(slug: str, lang: str) -> dict:
    return config.read_json(config.text_dir(slug) / 'translations' / f'{lang}.json', {}) or {}


def _save_translations(slug: str, lang: str, data: dict) -> None:
    config.write_json(config.text_dir(slug) / 'translations' / f'{lang}.json', data)


# ---------------------------------------------------------------- 1. глоссарий

GLOSSARY_SYSTEM = '''You compile a translation glossary for a story translated from {src} into {dst}.
Extract every proper name and special term that must be translated the same way everywhere: people and spirits,
titles and forms of address, places, events,
period realities (clothing, ranks, institutions), recurring phrases and refrains. Skip ordinary words.
For each: the dictionary (nominative) form in {src}, ONE rendering in {dst} (for transliterated names keep the
established {dst} forms where they exist, e.g. Leipzig; keep refrains word for word),
and a short note (who/what it is). Answer with ONE JSON object only: {{"terms": [{{"src": "…", "dst": "…", "note": "…"}}]}}'''


def build_glossary(slug: str, lang: str, *, model: str = GLOSSARY_MODEL, chunk_chars: int = 60000, log=print) -> float:
    """Глоссарий по всей книге (дополняет существующий: уже утверждённые термины не меняются)."""
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
        log(f'✓ глоссарий, часть {i + 1}/{len(chunks)}: +{added} (всего {len(g["terms"])}), ${c:.4f}')
    return cost


def _stem(word: str) -> str:
    w = word.lower().replace('ё', 'е')
    return w if len(w) <= 3 else w[:max(3, len(w) - 2)]


def terms_for(g: dict, chunk: str) -> list[dict]:
    """Статьи глоссария, которые встречаются в куске (по основе слова — с учётом падежей)."""
    low = chunk.lower().replace('ё', 'е')
    out = []
    for t in g['terms']:
        parts = re.findall(r'\w+', t['src'])
        # часть имени — с начала слова (падежи — по основе); короткие части — только целым словом
        if parts and all(re.search(rf'\b{re.escape(p.lower().replace("ё", "е"))}\b' if len(p) <= 3
                                   else rf'\b{re.escape(_stem(p))}', low) for p in parts):
            out.append({'src': t['src'], 'dst': t['dst']})
    return out


# ---------------------------------------------------------------- 2. перевод

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
    """«Глава 7» → «Chapter 7», «Предисловие» → «Foreword»; не по шаблону — None (переведёт модель)."""
    t = title.strip().lower()
    m = re.fullmatch(r'глава\s+(\d+)', t)
    names = TITLES.get(lang, {})
    if m and 'глава' in names:
        return f"{names['глава']} {m.group(1)}"
    return names.get(t)


def status(slug: str, lang: str) -> dict:
    """Сколько абзацев переведено / устарело / осталось по разделам."""
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
    """Перевести абзацы разделов (непереведённые и устаревшие; force — все). front — и вступление."""
    b = config.story(slug)
    src_lang = b['source']['lang']
    prep = prepare.load(slug, src_lang)
    g = glossary(slug)
    system = SYSTEM.format(src=LANG_NAMES.get(src_lang, src_lang), dst=LANG_NAMES.get(lang, lang),
                           title=b['title'].get(lang) or b['title'].get(src_lang), author=b.get('author', {}).get(lang, ''),
                           context=b.get('art_context', ''))  # noqa: E501
    units = []  # (id раздела, абзацы)
    for s in prep['sections']:
        if s['id'] in sections:
            units.append((s['id'], [p for p in s['paragraphs'] if p['kind'] != 'heading']))
    if front:
        # номера — по текстовым блокам вступления (картинки не считаются), как в status() и build()
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
            # контекст: два предыдущих абзаца раздела с переводом
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
                log(f'  {sid}: нет перевода {", ".join(missing)} — повтор')
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
    """Правка перевода абзаца из админки."""
    src = prepare.load(slug, config.story(slug)['source']['lang'])
    para = next((p for s in src['sections'] for p in s['paragraphs'] if p['id'] == pid), None)
    if para is None:
        front = [x for x in src.get('front', []) if x.get('text')]
        i = int(pid.split('-')[1]) if pid.startswith('front-') else -1
        if not 0 <= i < len(front):
            raise KeyError(f'нет абзаца {pid}')
        para = {'text': front[i]['text']}
    with _lock:
        tr = translations(slug, lang)
        tr[pid] = {'text': text_.strip(), 'src': _sha(para['text']), 'model': 'edited', 'at': time.strftime('%Y-%m-%d %H:%M')}
        _save_translations(slug, lang, tr)
    return tr[pid]


# ---------------------------------------------------------------- 3. подготовленный текст на языке перевода

def build(slug: str, lang: str, *, save: bool = True) -> dict:
    """prepared/<язык>.json из перевода: разделы, где переведены все абзацы; те же id."""
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
                # заголовок раздела (-000) — по шаблону; номер главы внутри раздела («II») — как есть
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
           'sections': sections, 'warnings': [f'{sid}: не переведено абзацев — {n}' for sid, n in missing.items()],
           'front': front if k and len(front) == len(src.get('front', [])) else [],
           'stats': {key: sum(s['stats'][key] for s in sections) for key in ('paragraphs', 'chars', 'words')}}
    if save:
        config.write_json(config.text_dir(slug) / 'prepared' / f'{lang}.json', out)
    return out
