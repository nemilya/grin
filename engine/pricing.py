"""Models, voices and narration cost estimates."""
from __future__ import annotations

from . import openrouter

DEFAULT_MODEL = 'google/gemini-3.8-flash-lite-tts'
DEFAULT_VERIFY_MODEL = 'google/gemini-3.5-transcribe'
CHARS_PER_SEC = {'ru': 14.0, 'en': 15.0}  # default reading pace (refined from finished takes)
GEMINI_AUDIO_TOKENS_PER_SEC = 25
STT_PER_MIN = 0.0058  # $ per minute of transcription (from usage.cost of gemini-3.5-transcribe)

# Gemini TTS voices (the same for all gemini-*-tts models)
GEMINI_VOICES = [
    ('Charon', 'm', 'informative'), ('Orus', 'm', 'firm'), ('Iapetus', 'm', 'clear'),
    ('Puck', 'm', 'upbeat'), ('Fenrir', 'm', 'excitable'), ('Enceladus', 'm', 'breathy'),
    ('Algieba', 'm', 'smooth'), ('Algenib', 'm', 'gravelly'), ('Rasalgethi', 'm', 'informative'),
    ('Alnilam', 'm', 'firm'), ('Schedar', 'm', 'even'), ('Achird', 'm', 'friendly'),
    ('Zubenelgenubi', 'm', 'casual'), ('Sadachbia', 'm', 'lively'), ('Sadaltager', 'm', 'knowledgeable'),
    ('Umbriel', 'm', 'easy-going'),
    ('Kore', 'f', 'firm'), ('Aoede', 'f', 'breezy'), ('Leda', 'f', 'youthful'), ('Zephyr', 'f', 'bright'),
    ('Callirrhoe', 'f', 'easy-going'), ('Autonoe', 'f', 'bright'), ('Despina', 'f', 'smooth'),
    ('Erinome', 'f', 'clear'), ('Laomedeia', 'f', 'upbeat'), ('Achernar', 'f', 'soft'),
    ('Gacrux', 'f', 'mature'), ('Pulcherrima', 'f', 'forward'), ('Vindemiatrix', 'f', 'gentle'),
    ('Sulafat', 'f', 'warm'),
]

# The narrator's default manner per language. The Russian one is Russian-language data, not prose: it enters
# the take key — changing it makes every Russian take stale.
DEFAULT_INSTRUCTIONS = {
    'ru': 'Ты — чтец аудиокниги. Читай по-русски спокойно и выразительно, как опытный рассказчик: '
          'естественные паузы на знаках препинания, реплики героев чуть живее авторского текста, '
          'без театральности и без пафоса. Читай текст ровно как написан, ничего не пропуская и не добавляя.',
    'en': 'You are an audiobook narrator. Read in calm, expressive English like an experienced storyteller: '
          'natural pauses at punctuation, dialogue slightly livelier than narration, never theatrical. '
          'Read the text exactly as written, without skipping or adding anything.',
}


def model_pricing(model: str) -> dict:
    try:
        for m in openrouter.speech_models():
            if m['id'] == model:
                return {k: float(v) for k, v in m['pricing'].items() if _num(v)}
    except Exception:
        pass
    return {'prompt': 0.0000005, 'completion': 0.000006} if 'gemini' in model else {}


def _num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def tts_cost(model: str, chars: int, seconds: float, instructions: str = '') -> float:
    """Synthesis cost. Gemini: input — tokens of the text and the manner (≈ 1 token per 3 Cyrillic characters),
    output — audio at 25 tokens/s. Other models — a price per character (prompt)."""
    p = model_pricing(model)
    if p.get('completion'):
        tokens_in = (chars + len(instructions or '')) / 3
        return tokens_in * p.get('prompt', 0) + seconds * GEMINI_AUDIO_TOKENS_PER_SEC * p['completion']
    return chars * p.get('prompt', 0)


def estimate(model: str, chars: int, lang: str, instructions: str = '', chunks: int = 1, verify: bool = True,
             chars_per_sec: float | None = None) -> dict:
    sec = chars / (chars_per_sec or CHARS_PER_SEC.get(lang, 14.0))
    # the manner (instructions) goes with every request
    tts = tts_cost(model, chars, sec, (instructions or '') * max(chunks, 1))
    stt = sec / 60 * STT_PER_MIN if verify else 0
    return {'chars': chars, 'seconds': round(sec), 'minutes': round(sec / 60, 1),
            'tts': round(tts, 4), 'verify': round(stt, 4), 'total': round(tts + stt, 4)}
