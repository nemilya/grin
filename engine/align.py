"""Обратная обработка: распознанные слова со временем → время каждого слова и предложения исходного текста.

Распознанный текст почти совпадает с исходным, но не дословно (числа словами, «Джомо-Лун-Гама» →
«Джома-Лунгма», ё/е). Сопоставляем последовательности нормализованных слов (difflib); совпавшие
получают время распознанных, расхождения — время своего блока пропорционально длине, пропущенные —
промежуток между соседями. Доля совпавших слов — оценка качества дубля (пропуски, обрывы).
"""
from __future__ import annotations

import difflib

from .text import norm_word


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


MAX_WORD = 2.5   # с: слово дольше — метка распознавателя сбилась
MIN_WORD = 0.03  # с: три и больше слов подряд короче — «слиплись» в одну точку


def bad_spans(times: list[list[float]]) -> list[tuple[int, int]]:
    """Куски [i, j) со сбитыми метками: слишком длинное слово или 3+ слова подряд нулевой длины."""
    n = len(times)
    bad = [b - a > MAX_WORD for a, b in times]
    k = 0
    while k < n:
        j = k
        while j < n and times[j][1] - times[j][0] < MIN_WORD:
            j += 1
        if j - k >= 3:
            for x in range(k, j):
                bad[x] = True
        k = max(j, k + 1)
    spans, k = [], 0
    while k < n:
        if bad[k]:
            j = k
            while j < n and bad[j]:
                j += 1
            spans.append((k, j))
            k = j
        else:
            k += 1
    return spans


def timing_ok(words: list[dict]) -> bool:
    """Метки распознанных слов без сбоев (для решения «распознать ещё раз»)."""
    return not bad_spans([[float(w.get('start', 0)), float(w.get('end', 0))] for w in words])


def repair(src: list[str], times: list[list[float]]) -> list[list[float]]:
    """Сбитые куски — время между соседними нормальными словами, пропорционально длине слов."""
    times = [list(t) for t in times]
    for i, j in bad_spans(times):
        t0 = times[i - 1][1] if i > 0 else times[i][0]
        t1 = times[j][0] if j < len(times) else times[j - 1][1]
        if t1 - t0 < 0.05 * (j - i):  # некуда распределять — расширить до соседних
            t1 = max(t1, t0 + 0.3 * (j - i))
        total = sum(max(len(w), 1) for w in src[i:j])
        t = t0
        for k in range(i, j):
            d = (t1 - t0) * max(len(src[k]), 1) / total
            times[k] = [t, t + d * 0.92]  # небольшой зазор между словами
            t += d
    return times


def by_pauses(text: str, words: list[list[int]], sentences: list[list[int]], pauses: list[tuple[float, float]],
              duration: float) -> list[list[float]]:
    """Время слов без распознавания: границы предложений — по паузам в звуке (ближайшие к ожидаемым по
    доле текста), слова внутри предложения — пропорционально длине. Запасной путь при сбитых метках."""
    total = max(len(text), 1)
    cuts, used = [], set()
    for a, b in sentences[:-1]:  # граница после каждого предложения, кроме последнего
        want = b / total * duration
        cand = [k for k, (s, e) in enumerate(pauses) if k not in used and (not cuts or s > cuts[-1][1])]
        k = min(cand, key=lambda k: abs((pauses[k][0] + pauses[k][1]) / 2 - want), default=None)
        if k is not None and abs((pauses[k][0] + pauses[k][1]) / 2 - want) < duration * 0.15:
            used.add(k)
            cuts.append(pauses[k])
        else:
            cuts.append((want, want))
    spans, t = [], 0.0
    for i, (a, b) in enumerate(sentences):
        end = cuts[i][0] if i < len(cuts) else duration
        spans.append((a, b, t, max(end, t)))
        t = cuts[i][1] if i < len(cuts) else duration
    out = []
    for wa, wb in words:
        a, b, t0, t1 = next(((a, b, t0, t1) for a, b, t0, t1 in spans if a <= wa < b), spans[-1])
        ws = [w for w in words if a <= w[0] < b]
        chars = sum(w[1] - w[0] for w in ws) or 1
        before = sum(w[1] - w[0] for w in ws if w[0] < wa)
        s = t0 + (t1 - t0) * before / chars
        out.append([round(s, 3), round(s + (t1 - t0) * (wb - wa) / chars * 0.92, 3)])
    return out


MAX_EXTRA = 3  # лишних слов после текста — допуск (междометие, вдох, распознанный шум)


def align(src: list[str], rec: list[dict], duration: float) -> tuple[list[list[float]], float, bool]:
    """src — слова текста; rec — [{word, start, end}] распознавания.
    → (время слов [[t0, t1]], доля узнанных слов, узнан ли конец). Конец не узнан и тогда, когда после текста
    звучит лишнее: модель озвучки, дочитав абзац, бывает, сочиняет продолжение (MAX_EXTRA слов — допуск)."""
    a = [norm_word(w) for w in src]
    b = [norm_word(w['word']) for w in rec]
    rt = [(float(w.get('start', 0)), float(w.get('end', 0))) for w in rec]
    times: list[list[float] | None] = [None] * len(a)
    hit = [False] * len(a)
    last = -1  # последнее слово распознавания, совпавшее с текстом

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for k in range(i2 - i1):
                times[i1 + k] = list(rt[j1 + k])
                hit[i1 + k] = True
            last = max(last, j2 - 1)
        elif op == 'replace':
            t0, t1 = rt[j1][0], rt[j2 - 1][1]
            if i2 - i1 == j2 - j1:
                for k in range(i2 - i1):
                    times[i1 + k] = list(rt[j1 + k])
                    hit[i1 + k] = similar(a[i1 + k], b[j1 + k]) >= 0.6
            else:
                # блок слов ↔ блок распознанного: время делим по длине слов
                total = sum(max(len(x), 1) for x in a[i1:i2])
                joined = ''.join(b[j1:j2])
                t = t0
                for k in range(i1, i2):
                    d = (t1 - t0) * max(len(a[k]), 1) / total
                    times[k] = [t, t + d]
                    hit[k] = a[k] in joined or any(similar(a[k], x) >= 0.6 for x in b[j1:j2])
                    t += d
            if any(hit[i1:i2]):
                last = max(last, j2 - 1)

    # пропущенные слова — в промежуток между соседями, пропорционально длине
    i = 0
    while i < len(a):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(a) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(a) else max(duration, t0)
        total = sum(max(len(x), 1) for x in a[i:j])
        t = t0
        for k in range(i, j):
            d = (t1 - t0) * max(len(a[k]), 1) / total
            times[k] = [t, t + d]
            t += d
        i = j

    # монотонность и без перекрытий
    prev = 0.0
    for k, tt in enumerate(times):
        tt[0] = max(tt[0], prev)
        tt[1] = max(tt[1], tt[0])
        if k + 1 < len(times) and times[k + 1] is not None:
            tt[1] = min(tt[1], max(times[k + 1][0], tt[0]))
        prev = tt[1]
    times = repair(a, times)
    times = [[round(x, 3) for x in tt] for tt in times]

    score = sum(hit) / max(len(a), 1)
    tail = not a or any(hit[-2:]) or any(similar(a[-1], x) >= 0.6 for x in b[-3:])
    tail = tail and len(b) - 1 - last <= MAX_EXTRA
    return times, round(score, 3), tail
