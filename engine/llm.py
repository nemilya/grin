"""Текстовая модель через OpenRouter (/chat/completions): глоссарий, перевод, анализ."""
from __future__ import annotations

import json
import re

from .openrouter import ApiError, _request

DEFAULT_MODEL = 'anthropic/claude-haiku-5.5'
MODELS = ['anthropic/claude-haiku-5.5', 'anthropic/claude-sonnet-5.5', 'anthropic/claude-opus-5.5']


def chat(messages: list[dict], *, model: str = DEFAULT_MODEL, max_tokens: int = 8000,
         temperature: float = 0.3) -> tuple[str, float]:
    """→ (текст ответа, стоимость $)."""
    body = {'model': model, 'messages': messages, 'max_tokens': max_tokens, 'temperature': temperature}
    raw, _ = _request('/chat/completions', body=json.dumps(body).encode(), ctype='application/json')
    r = json.loads(raw)
    if 'choices' not in r:
        raise ApiError(f'chat: {str(r)[:300]}')
    return r['choices'][0]['message']['content'] or '', float((r.get('usage') or {}).get('cost') or 0)


def chat_json(messages: list[dict], *, retries: int = 2, **kw) -> tuple[dict, float]:
    """Ответ — JSON-объект (из ```json …``` или первого {…}); при неразборчивом ответе — повтор."""
    cost, last = 0.0, ''
    for _ in range(retries + 1):
        text, c = chat(messages, **kw)
        cost += c
        m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S) or re.search(r'(\{.*\})', text, re.S)
        if m:
            try:
                return json.loads(m.group(1)), cost
            except json.JSONDecodeError as e:
                last = f'{e}: {text[:200]}'
        else:
            last = text[:200]
    raise ApiError(f'модель не вернула JSON: {last}')
