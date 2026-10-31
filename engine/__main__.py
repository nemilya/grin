"""Харнес ролика: этапы и их статус. python -m engine <команда> [история] [опции] (обёртки — в Makefile).

  status     что готово по этапам: текст → перевод → библия/раскадровка → ассеты → озвучка → таймлайн → звук
  prepare    исходник → prepared/<язык>.json
  glossary   глоссарий перевода (LLM)          translate  перевод абзацев (LLM; можно и в сессии Claude Code)
  assets     сгенерировать недостающие ассеты (Seedream); --used — только те, что в таймлайне; --keys a,b;
             --redo a,b — новый вариант (прежний — в takes/); --accept a,b — устаревшее принять как есть;
             --rekey a,b — пересобрать вырезку из исходника (ключ, подчистка erase из библии), без генерации
  voice      озвучить абзацы (TTS + проверка распознаванием); --from 040 --to 046 — диапазон абзацев
  timeline   раскадровка + время речи → build/timeline.json; --start s12a --end s14c --name demo — отрезок;
             --format horizontal — другой формат (story.json → formats) → build/timeline-horizontal[-demo].json
  sound      звук для таймлайна → build/sound[-формат][-name].wav
  youtube    субтитры .srt и главы по сценам для описания → out/<история>/<история>[-формат].srt, -chapters.txt
Рендер — браузером: node tools/capture.mjs stills|video (см. README).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from . import assets, config, media, prepare, timeline, translate, voicing


def status(slug: str) -> None:
    st = config.story(slug)
    film = st.get('film', {})
    lang, src = film.get('lang', 'en'), st['source']['lang']
    p = prepare.load(slug, src)
    print(f"{slug}: «{st['title'].get(lang) or st['title'].get(src)}» → {lang}, {film.get('width')}×{film.get('height')} @ {film.get('fps')}")
    print(f"  1 текст        {'✓ ' + str(p['stats']['paragraphs']) + ' абз., ' + str(p['stats']['chars']) + ' зн.' if p else '— make prepare'}")
    if lang != src and p:
        s = translate.status(slug, lang)
        done = sum(v.get('done', 0) for k, v in s.items() if k != 'front')
        rest = sum(v.get('stale', 0) + v.get('pending', 0) for k, v in s.items() if k != 'front')
        print(f"  2 перевод      {done} готово, {rest} осталось/устарело" + (' ✓' if not rest else ''))
    b = timeline.bible(slug)
    sb = timeline.storyboard(slug)
    n_shots = sum(len(s['shots']) for s in sb.get('scenes', []))
    print(f"  3 библия       {len(b.get('characters', {}))} героев, "
          f"{sum(len(c.get('poses', {})) for c in b.get('characters', {}).values())} поз, {len(b.get('sets', {}))} декораций")
    print(f"    раскадровка  {len(sb.get('scenes', []))} сцен, {n_shots} кадров")
    for fmt in (st.get('formats') or {}):
        try:
            th = timeline.build(slug, save=False, fmt=fmt)
            print(f"    формат {fmt:10} {th['width']}×{th['height']}, {len(th['shots'])} кадров, ошибок {len(th['errors'])}"
                  f" (make timeline F={fmt})")
        except Exception as e:  # noqa: BLE001
            print(f'    ✗ формат {fmt}: {e}')
    try:
        tl = timeline.build(slug, save=False)
    except Exception as e:  # noqa: BLE001
        print(f'    ✗ таймлайн: {e}')
        return
    used = assets.used_keys(tl)
    pl = assets.plan(slug)
    by = {}
    for it in pl:
        if it['key'] in used or it['kind'] == 'ref':
            by[it['status']] = by.get(it['status'], 0) + 1
    print(f"  4 ассеты       {by.get('ok', 0)} готово, {by.get('stale', 0)} устарело, {by.get('pending', 0)} заглушек "
          f"(в таймлайне карточек {len(used)}), потрачено ${assets.manifest(slug).get('cost', 0):.2f}")
    vid = film.get('voicing')
    if vid and (config.text_dir(slug) / 'voicings' / vid / 'voicing.json').exists():
        s = voicing.summary(slug, vid)
        print(f"  5 озвучка      {vid}: {s['counts']}, {s['duration'] / 60:.1f} мин, ${s['cost']:.3f}")
    else:
        print('  5 озвучка      —')
    print(f"  6 таймлайн     {tl['duration'] / 60:.1f} мин, время: {tl['timing']}, ошибок {len(tl['errors'])}")
    media.status()
    for e in tl['errors'][:10]:
        print('      ✗', e)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog='python -m engine')
    ap.add_argument('cmd')
    ap.add_argument('story', nargs='?', default='mate-in-3')
    ap.add_argument('--lang')
    ap.add_argument('--used', action='store_true')
    ap.add_argument('--keys')
    ap.add_argument('--from', dest='frm')
    ap.add_argument('--to')
    ap.add_argument('--start')
    ap.add_argument('--end')
    ap.add_argument('--name')
    ap.add_argument('--format', dest='fmt')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--redo')
    ap.add_argument('--accept')
    ap.add_argument('--rekey')
    a = ap.parse_args(argv)
    config.load_env()
    slug = a.story
    film = config.story(slug).get('film', {})
    if a.cmd in ('assets', 'voice', 'site') and not (a.accept or a.rekey):
        media.check()  # pictures and narration listed in media.rev must be pulled, not generated again (paid)
    if a.cmd == 'status':
        status(slug)
    elif a.cmd == 'prepare':
        r = prepare.prepare(slug)
        print(f"✓ {r['stats']['paragraphs']} абз., {r['stats']['chars']} знаков")
        lang = film.get('lang')
        if lang and lang != r['lang'] and translate.translations(slug, lang):
            translate.build(slug, lang)
            print(f'✓ prepared/{lang}.json из перевода')
    elif a.cmd == 'glossary':
        translate.build_glossary(slug, a.lang or film['lang'])
    elif a.cmd == 'translate':
        lang = a.lang or film['lang']
        prep = prepare.load(slug, config.story(slug)['source']['lang'])
        translate.translate_sections(slug, lang, [s['id'] for s in prep['sections']], force=a.force)
        translate.build(slug, lang)
    elif a.cmd == 'assets':
        if a.accept:
            assets.accept(slug, a.accept.split(','))
            return
        if a.rekey:
            assets.rekey(slug, a.rekey.split(','))
            return
        if a.redo:
            items = {it['key']: it for it in assets.plan(slug, set(a.redo.split(',')))}
            print(f"потрачено ${sum(assets.generate(slug, items[k], redo=True) for k in a.redo.split(',') if k in items):.3f}")
            return
        if a.keys:
            keys = set(a.keys.split(','))
        elif a.used:  # карточки всех форматов
            st = config.story(slug)
            keys = set().union(*(assets.used_keys(timeline.build(slug, save=False, fmt=f))
                                 for f in [None, *(st.get('formats') or {})]))
        else:
            keys = None
        print(f'потрачено ${assets.generate_all(slug, keys):.3f}')
    elif a.cmd == 'voice':
        vid = (film.get('voicings') or {}).get(a.lang) if a.lang else film['voicing']  # --lang ru — озвучка языка
        if not vid:
            sys.exit(f'нет озвучки для {a.lang}: story.json → film.voicings')
        pl = voicing.plan(slug, vid)
        ids = [it['id'] for s in pl['sections'] for it in s['items'] if it['status'] in ('pending', 'stale') or a.force]
        if a.frm or a.to:
            lo, hi = int(a.frm or 0), int(a.to or 999)
            ids = [i for i in ids if lo <= int(i.rsplit('-', 1)[1]) <= hi]
        est = voicing.estimate(slug, vid)
        print(f"абзацев {len(ids)}; оценка всего недостающего: {est['minutes']} мин, ${est['total_with_retries']}")
        failed = []
        for pid in ids:
            try:
                stt = voicing.generate_item(slug, vid, pid, force=a.force)
            except Exception as e:  # noqa: BLE001 — сбой провайдера (429, пустой звук): дальше, этот — в повтор
                print(f'✗ {pid}: {e}', flush=True)
                failed.append(pid)
                time.sleep(3)
                continue
            t = voicing.selected_take(stt)
            print(f"✓ {pid} {t['dur']:.1f} с, совпадение {t['score']}, ${sum(t['cost'].values()):.4f}", flush=True)
        if failed:
            sys.exit(f"не озвучены: {', '.join(failed)} — запустить ещё раз")
    elif a.cmd == 'site':
        from . import site
        site.build()
    elif a.cmd == 'timeline':
        L = a.lang if a.lang and a.lang != timeline.film(slug)['lang'] else None  # --lang ru — ролик на другом языке
        tl = timeline.build(slug, start=a.start, end=a.end, name=a.name, fmt=a.fmt, lang=L)
        t = timeline.tag(a.fmt, a.name, L)
        print(f"✓ build/timeline{'-' + t if t else ''}.json: {tl['width']}×{tl['height']}, {tl['duration'] / 60:.1f} мин, "
              f"{len(tl['shots'])} кадров, время: {tl['timing']}")
        for w in tl.get('warnings', []):
            print('  ·', w)
        for e in tl['errors']:
            print('  ✗', e)
        if tl['errors']:
            sys.exit(1)
    elif a.cmd in ('sound', 'youtube'):
        L = a.lang if a.lang and a.lang != timeline.film(slug)['lang'] else None
        t = timeline.tag(a.fmt, a.name, L)
        tl = json.loads((timeline.build_dir(slug) / (f'timeline-{t}.json' if t else 'timeline.json')).read_text(encoding='utf8'))
        if a.cmd == 'sound':
            from . import sound
            sound.build(slug, tl, timeline.build_dir(slug) / (f'sound-{t}.wav' if t else 'sound.wav'))
        else:
            out = config.OUT / slug
            out.mkdir(parents=True, exist_ok=True)
            base = f'{slug}-{t}' if t else slug
            (out / f'{base}.srt').write_text(timeline.srt(tl), encoding='utf8')
            ch = timeline.chapters(tl)
            fmt_t = lambda x: f'{int(x // 60)}:{int(x % 60):02d}'  # noqa: E731
            (out / f'{base}-chapters.txt').write_text('\n'.join(f'{fmt_t(t0)} {title}' for t0, title in ch) + '\n', encoding='utf8')
            print(f'✓ out/{slug}/{base}.srt ({len(tl["subtitles"])} субтитров), {base}-chapters.txt ({len(ch)} глав):')
            for t0, title in ch:
                print(f'   {fmt_t(t0)} {title}')
            if tl.get('timing') != 'voicing':
                print(f"   ⚠ время — {tl.get('timing')}: озвучьте всё (make voice) и пересоберите, иначе главы и субтитры разойдутся с роликом")
    else:
        ap.error(f'нет команды {a.cmd}')


if __name__ == '__main__':
    main()
