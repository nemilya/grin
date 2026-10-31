"""Модели, голоса и оценка стоимости озвучки."""
from __future__ import annotations

from . import openrouter

DEFAULT_MODEL = 'google/gemini-3.8-flash-lite-tts'
DEFAULT_VERIFY_MODEL = 'google/gemini-3.5-transcribe'
CHARS_PER_SEC = {'ru': 14.0, 'en': 15.0}  # темп чтения по умолчанию (уточняется по готовым дублям)
GEMINI_AUDIO_TOKENS_PER_SEC = 25
STT_PER_MIN = 0.0058  # $ за минуту распознавания (по usage.cost gemini-3.5-transcribe)

# Голоса Gemini TTS (одинаковы для всех моделей gemini-*-tts)
GEMINI_VOICES = [
    ('Charon', 'м', 'информативный'), ('Orus', 'м', 'твёрдый'), ('Iapetus', 'м', 'ясный'),
    ('Puck', 'м', 'бодрый'), ('Fenrir', 'м', 'возбуждённый'), ('Enceladus', 'м', 'с придыханием'),
    ('Algieba', 'м', 'мягкий'), ('Algenib', 'м', 'с хрипотцой'), ('Rasalgethi', 'м', 'информативный'),
    ('Alnilam', 'м', 'твёрдый'), ('Schedar', 'м', 'ровный'), ('Achird', 'м', 'дружелюбный'),
    ('Zubenelgenubi', 'м', 'непринуждённый'), ('Sadachbia', 'м', 'живой'), ('Sadaltager', 'м', 'знающий'),
    ('Umbriel', 'м', 'лёгкий'),
    ('Kore', 'ж', 'твёрдый'), ('Aoede', 'ж', 'лёгкий'), ('Leda', 'ж', 'юный'), ('Zephyr', 'ж', 'яркий'),
    ('Callirrhoe', 'ж', 'спокойный'), ('Autonoe', 'ж', 'яркий'), ('Despina', 'ж', 'плавный'),
    ('Erinome', 'ж', 'чёткий'), ('Laomedeia', 'ж', 'бодрый'), ('Achernar', 'ж', 'мягкий'),
    ('Gacrux', 'ж', 'зрелый'), ('Pulcherrima', 'ж', 'уверенный'), ('Vindemiatrix', 'ж', 'нежный'),
    ('Sulafat', 'ж', 'тёплый'),
]

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
    """Стоимость синтеза. Gemini: вход — токены текста и манеры (≈ 1 токен на 3 знака кириллицы),
    выход — аудио 25 токенов/с. Прочие модели — цена за знак (prompt)."""
    p = model_pricing(model)
    if p.get('completion'):
        tokens_in = (chars + len(instructions or '')) / 3
        return tokens_in * p.get('prompt', 0) + seconds * GEMINI_AUDIO_TOKENS_PER_SEC * p['completion']
    return chars * p.get('prompt', 0)


def estimate(model: str, chars: int, lang: str, instructions: str = '', chunks: int = 1, verify: bool = True,
             chars_per_sec: float | None = None) -> dict:
    sec = chars / (chars_per_sec or CHARS_PER_SEC.get(lang, 14.0))
    # манера (instructions) уходит с каждым запросом
    tts = tts_cost(model, chars, sec, (instructions or '') * max(chunks, 1))
    stt = sec / 60 * STT_PER_MIN if verify else 0
    return {'chars': chars, 'seconds': round(sec), 'minutes': round(sec / 60, 1),
            'tts': round(tts, 4), 'verify': round(stt, 4), 'total': round(tts + stt, 4)}
