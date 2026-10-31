"""Текст: очистка markdown-источника, деление на предложения и слова.

Модель текста (общая для показа, озвучки и подсветки):
    абзац → предложения → слова; у слова — смещения в тексте абзаца [a, b).
Озвучивается абзац целиком (или несколькими кусками по границам предложений, если он очень длинный),
а время слов и предложений находится обратным распознаванием (align.py).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- очистка markdown

IMAGE_RE = re.compile(r'!\[[^\]]*\]\[[^\]]*\]|!\[[^\]]*\]\([^)]*\)')
ESCAPE_RE = re.compile(r'\\([\\`*_{}\[\]()#+\-.!:|<>~=])')
EMPH_RE = re.compile(r'(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1')
# номер сноски: цифры сразу после буквы или закрывающего знака, дальше — пробел, знак или конец строки.
# «лет1 до», «(Ван Чагма)2,», «Дью-ла12» → убираются; «800 лет», «V4B», «1949», даты «12.08.1955» — остаются
# (цифры после «цифра.» или «цифра,» — часть числа, не сноска).
FOOTNOTE_RE = re.compile(r'(?<=[^\W\d_]|[»”")\].,;:!?*])(?<!\d[.,])\d{1,3}(?:,\d{1,3})*(?=[\s.,;:!?»”")\]*\\]|$)')
SPACES_RE = re.compile(r'[ \t ]+')


def strip_markdown(s: str, *, footnotes: bool = True) -> tuple[str, bool]:
    """Строка markdown → (чистый текст, весь ли абзац курсивом)."""
    s = IMAGE_RE.sub(' ', s)
    if footnotes:
        s = FOOTNOTE_RE.sub('', s)
    s = ESCAPE_RE.sub(r'\1', s)
    plain = s.strip()
    italic = bool(re.fullmatch(r'\*[^*].*[^*]\*|_[^_].*[^_]_', plain))
    for _ in range(2):
        s = EMPH_RE.sub(r'\2', s)
    s = s.replace('**', '')
    s = SPACES_RE.sub(' ', s).strip()
    # реплика диалога: «- Отец!» / «– Отец!» → «— Отец!»
    s = re.sub(r'^[-–]\s', '— ', s)
    s = re.sub(r'\s[-–]\s', ' — ', s)
    return s, italic


# ---------------------------------------------------------------- предложения

# сокращения, после которых точка не конец предложения
ABBR = {
    'г', 'гг', 'в', 'вв', 'т', 'е', 'п', 'н', 'э', 'др', 'см', 'ср', 'им', 'св', 'стр', 'тыс', 'млн', 'ок',
    'mr', 'mrs', 'dr', 'st', 'vs', 'etc', 'e', 'i', 'g',
}
SENT_END_RE = re.compile(r'[.!?…]+[»”’")\]]*(?=\s+)')


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Границы предложений [a, b) в строке (пробелы между ними не входят)."""
    out, start = [], 0
    for m in SENT_END_RE.finditer(text):
        end = m.end()
        nxt = text[end:].lstrip()
        if not nxt:
            continue
        # предложение начинается с заглавной, тире или кавычки
        if not (nxt[0].isupper() or nxt[0] in '—–-«"“‘(' or nxt[0].isdigit()):
            continue
        # «— Отец! — испуганно вскрикнув…» — слова автора после реплики: то же предложение
        if nxt[0] in '—–-' and nxt[1:].lstrip()[:1].islower():
            continue
        # “Father!” I cried out… / “Wait,” he said — то же в английской прозе: после закрывающей кавычки
        if m.group(0)[-1:] in '”"’' and (nxt[:1].islower() or re.match(r"I\b(?!')", nxt)):
            continue
        if m.group(0).startswith('.') and len(m.group(0).rstrip('»”")]')) == 1:
            word = re.search(r'(\w+)$', text[start:m.start()])
            w = word.group(1) if word else ''
            if w != 'I' and (w.lower() in ABBR or (len(w) == 1 and w.isalpha())):  # «he and I.» — конец
                continue
        out.append((start, end))
        start = end + (len(text[end:]) - len(nxt))
    if start < len(text):
        out.append((start, len(text.rstrip())))
    return [(a, b) for a, b in out if text[a:b].strip()]


# ---------------------------------------------------------------- слова

WORD_RE = re.compile(r"[\ẃ]+(?:[-‐'’][\ẃ]+)*", re.UNICODE)


def split_words(text: str, a: int = 0, b: int | None = None) -> list[tuple[int, int]]:
    """Слова (буквы/цифры, с дефисами внутри) в text[a:b] → смещения в text."""
    b = len(text) if b is None else b
    return [(a + m.start(), a + m.end()) for m in WORD_RE.finditer(text[a:b])]


def norm_word(w: str) -> str:
    """Слово для сравнения с распознанным: нижний регистр, ё→е, без ударений и дефисов."""
    w = unicodedata.normalize('NFD', w.lower())
    w = ''.join(c for c in w if unicodedata.category(c) != 'Mn')
    w = unicodedata.normalize('NFC', w).replace('ё', 'е')
    return re.sub(r'[^\w]', '', w)


# ---------------------------------------------------------------- для озвучки

ORDINAL_F = ['', 'первая', 'вторая', 'третья', 'четвёртая', 'пятая', 'шестая', 'седьмая', 'восьмая', 'девятая',
             'десятая', 'одиннадцатая', 'двенадцатая', 'тринадцатая', 'четырнадцатая', 'пятнадцатая',
             'шестнадцатая', 'семнадцатая', 'восемнадцатая', 'девятнадцатая', 'двадцатая']


ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}


def roman(s: str) -> int | None:
    """«XIV» → 14; не римское число — None."""
    if not s or any(c not in ROMAN for c in s):
        return None
    n = 0
    for a, b in zip(s, s[1:] + ' '):
        n += -ROMAN[a] if ROMAN.get(b, 0) > ROMAN[a] else ROMAN[a]
    return n


def heading_speech(title: str, lang: str) -> str:
    """Как произнести заголовок: «ГЛАВА 1» → «Глава первая.»; номер главы «II» → «Глава вторая.» / «Chapter 2.»"""
    t = title.strip().rstrip('.')
    n = roman(t)
    if n:
        t = f'Глава {n}' if lang == 'ru' else f'Chapter {n}'
    m = re.fullmatch(r'(?i)глава\s+(\d+)', t)
    if lang == 'ru' and m and int(m.group(1)) < len(ORDINAL_F):
        return f'Глава {ORDINAL_F[int(m.group(1))]}.'
    m = re.fullmatch(r'(?i)chapter\s+(\d+)', t)
    if m:
        return f'Chapter {m.group(1)}.'
    return t[:1].upper() + t[1:].lower() + '.' if t.isupper() else t + '.'


def heading_display(title: str) -> str:
    t = title.strip()
    return t[:1].upper() + t[1:].lower() if t.isupper() else t


def apply_replacements(text: str, rules: list[dict]) -> str:
    """Поправки произношения (только для озвучки): [{"from": regex, "to": str}]."""
    for r in rules or []:
        text = re.sub(r['from'], r['to'], text)
    return text
