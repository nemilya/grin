"""Text: cleaning a markdown source, splitting into sentences and words.

The text model (shared by display, narration and highlighting):
    paragraph → sentences → words; a word has offsets [a, b) into the paragraph text.
A paragraph is narrated whole (or in several pieces at sentence boundaries if it is very long),
and the timings of words and sentences come from back-transcription (align.py).
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------- cleaning markdown

IMAGE_RE = re.compile(r'!\[[^\]]*\]\[[^\]]*\]|!\[[^\]]*\]\([^)]*\)')
ESCAPE_RE = re.compile(r'\\([\\`*_{}\[\]()#+\-.!:|<>~=])')
EMPH_RE = re.compile(r'(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1')
# a footnote number: digits right after a letter or a closing mark, followed by a space, a mark or the end of the line.
# «лет1 до», «(Ван Чагма)2,», «Дью-ла12» → removed; «800 лет», «V4B», «1949», dates «12.08.1955» — kept
# (digits after "digit." or "digit," are part of a number, not a footnote).
FOOTNOTE_RE = re.compile(r'(?<=[^\W\d_]|[»”")\].,;:!?*])(?<!\d[.,])\d{1,3}(?:,\d{1,3})*(?=[\s.,;:!?»”")\]*\\]|$)')
SPACES_RE = re.compile(r'[ \t ]+')


def strip_markdown(s: str, *, footnotes: bool = True) -> tuple[str, bool]:
    """A markdown line → (clean text, whether the whole paragraph is italic)."""
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
    # a dialogue line: «- Отец!» / «– Отец!» → «— Отец!»
    s = re.sub(r'^[-–]\s', '— ', s)
    s = re.sub(r'\s[-–]\s', ' — ', s)
    return s, italic


# ---------------------------------------------------------------- sentences

# abbreviations after which a period does not end a sentence
ABBR = {
    'г', 'гг', 'в', 'вв', 'т', 'е', 'п', 'н', 'э', 'др', 'см', 'ср', 'им', 'св', 'стр', 'тыс', 'млн', 'ок',
    'mr', 'mrs', 'dr', 'st', 'vs', 'etc', 'e', 'i', 'g',
}
SENT_END_RE = re.compile(r'[.!?…]+[»”’")\]]*(?=\s+)')


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Sentence boundaries [a, b) in a string (the spaces between them are not included)."""
    out, start = [], 0
    for m in SENT_END_RE.finditer(text):
        end = m.end()
        nxt = text[end:].lstrip()
        if not nxt:
            continue
        # a sentence starts with a capital, a dash or a quote
        if not (nxt[0].isupper() or nxt[0] in '—–-«"“‘(' or nxt[0].isdigit()):
            continue
        # «— Отец! — испуганно вскрикнув…» — the author's words after a line of dialogue: the same sentence
        if nxt[0] in '—–-' and nxt[1:].lstrip()[:1].islower():
            continue
        # “Father!” I cried out… / “Wait,” he said — the same in English prose: after a closing quote
        if m.group(0)[-1:] in '”"’' and (nxt[:1].islower() or re.match(r"I\b(?!')", nxt)):
            continue
        if m.group(0).startswith('.') and len(m.group(0).rstrip('»”")]')) == 1:
            word = re.search(r'(\w+)$', text[start:m.start()])
            w = word.group(1) if word else ''
            if w != 'I' and (w.lower() in ABBR or (len(w) == 1 and w.isalpha())):  # "he and I." — an end
                continue
        out.append((start, end))
        start = end + (len(text[end:]) - len(nxt))
    if start < len(text):
        out.append((start, len(text.rstrip())))
    return [(a, b) for a, b in out if text[a:b].strip()]


# ---------------------------------------------------------------- words

WORD_RE = re.compile(r"[\ẃ]+(?:[-‐'’][\ẃ]+)*", re.UNICODE)


def split_words(text: str, a: int = 0, b: int | None = None) -> list[tuple[int, int]]:
    """Words (letters/digits, with hyphens inside) in text[a:b] → offsets into text."""
    b = len(text) if b is None else b
    return [(a + m.start(), a + m.end()) for m in WORD_RE.finditer(text[a:b])]


def norm_word(w: str) -> str:
    """A word for comparison with the transcript: lower case, ё→е, no stress marks or hyphens."""
    w = unicodedata.normalize('NFD', w.lower())
    w = ''.join(c for c in w if unicodedata.category(c) != 'Mn')
    w = unicodedata.normalize('NFC', w).replace('ё', 'е')
    return re.sub(r'[^\w]', '', w)


# ---------------------------------------------------------------- for narration

ORDINAL_F = ['', 'первая', 'вторая', 'третья', 'четвёртая', 'пятая', 'шестая', 'седьмая', 'восьмая', 'девятая',
             'десятая', 'одиннадцатая', 'двенадцатая', 'тринадцатая', 'четырнадцатая', 'пятнадцатая',
             'шестнадцатая', 'семнадцатая', 'восемнадцатая', 'девятнадцатая', 'двадцатая']


ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}


def roman(s: str) -> int | None:
    """A Roman numeral "XIV" → 14; anything else — None."""
    if not s or any(c not in ROMAN for c in s):
        return None
    n = 0
    for a, b in zip(s, s[1:] + ' '):
        n += -ROMAN[a] if ROMAN.get(b, 0) > ROMAN[a] else ROMAN[a]
    return n


def heading_speech(title: str, lang: str) -> str:
    """How to pronounce a heading: «ГЛАВА 1» → «Глава первая.»; a chapter number «II» → «Глава вторая.» / «Chapter 2.»"""
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
    """Pronunciation fixes (narration only): [{"from": regex, "to": str}]."""
    for r in rules or []:
        text = re.sub(r['from'], r['to'], text)
    return text
