"""OpenRouter: speech synthesis (/audio/speech), transcription with word timings (/audio/transcriptions), model prices.

The key comes only from the environment OPENROUTER_API_KEY (or .env / local.mk, see config.load_env) and is never written.
Proxy — OPENROUTER_PROXY (socks5h://…, http://…): requests then go through curl,
the key in a temporary curl config (mode 600), not in the command arguments. Retries on 429, 5xx and dropped connections — up to 4 attempts.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ENDPOINT = os.environ.get('OPENROUTER_ENDPOINT', 'https://openrouter.ai/api/v1')


class ApiError(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get('OPENROUTER_API_KEY')
    if not key:
        raise ApiError('no OPENROUTER_API_KEY: set it in the environment, in .env or local.mk (see README)')
    return key


def proxy() -> str:
    """OPENROUTER_PROXY — read on every request (local.mk / .env are loaded after import)."""
    return (os.environ.get('OPENROUTER_PROXY') or '').strip()


def _send(url: str, headers: dict, body: bytes | None, method: str, timeout: int) -> tuple[int, str, bytes]:
    """One request → (HTTP status, content-type, body). A dropped connection — ConnectionError."""
    if not proxy():
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.headers.get('content-type', ''), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('content-type', ''), e.read()
        except (urllib.error.URLError, TimeoutError) as e:
            raise ConnectionError(str(e)) from None
    q = lambda v: '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'  # noqa: E731
    with tempfile.TemporaryDirectory(prefix='pt-or-') as tmp:
        conf, out = os.path.join(tmp, 'curl.conf'), os.path.join(tmp, 'body')
        lines = [f'url = {q(url)}', f'proxy = {q(proxy())}', f'request = {q(method)}', 'silent', 'show-error',
                 f'max-time = {timeout}', f'output = {q(out)}', 'write-out = "%{http_code} %{content_type}"',
                 *(['data-binary = "@-"'] if body is not None else []),
                 *(f'header = {q(f"{k}: {v}")}' for k, v in headers.items())]
        fd = os.open(conf, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        r = subprocess.run(['curl', '--config', conf], input=body or b'', capture_output=True)
        if r.returncode:
            raise ConnectionError(f'curl via {proxy()}: {r.stderr.decode("utf8", "replace").strip()[:300]}')
        code, _, ctype = r.stdout.decode().strip().partition(' ')
        data = open(out, 'rb').read() if os.path.exists(out) else b''
        return int(code or 0), ctype, data


def _request(path: str, *, body: bytes | None = None, ctype: str | None = None, method: str = 'POST',
             auth: bool = True, timeout: int = 600) -> tuple[bytes, str]:
    headers = {'x-title': 'grin', 'http-referer': 'https://github.com/nemilya/grin'}
    if auth:
        headers['authorization'] = f'Bearer {_key()}'
    if ctype:
        headers['content-type'] = ctype
    last = None
    for attempt in range(1, 5):
        try:
            status, rtype, data = _send(f'{ENDPOINT}{path}', headers, body, method, timeout)
        except (ConnectionError, TimeoutError, OSError) as e:
            last = f'{path}: {e}'
        else:
            if 200 <= status < 300:
                return data, rtype
            last = f'{path}: HTTP {status} {data[:400].decode("utf8", "replace")}'
            if status != 429 and status < 500:
                raise ApiError(last)
        time.sleep(5 * attempt)
    raise ApiError(last)


def speech(text: str, *, model: str, voice: str, instructions: str | None = None, speed: float | None = None,
           response_format: str = 'pcm') -> tuple[bytes, str]:
    """Synthesis → (bytes, content-type). For pcm the type looks like audio/pcm;rate=24000;channels=1."""
    payload = {'model': model, 'input': text, 'voice': voice, 'response_format': response_format}
    if instructions:
        payload['instructions'] = instructions
    if speed and speed != 1:
        payload['speed'] = speed
    return _request('/audio/speech', body=json.dumps(payload).encode(), ctype='application/json')


def transcribe(path: str, *, model: str, language: str | None = None) -> dict:
    """Transcribe a file → {text, words: [{word, start, end}], usage: {cost}}."""
    fields = {'model': model, 'response_format': 'verbose_json', 'timestamp_granularities[]': 'word'}
    if language:
        fields['language'] = language
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    name = os.path.basename(path)
    with open(path, 'rb') as f:
        data = f.read()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    raw, _ = _request('/audio/transcriptions', body=b''.join(parts), ctype=f'multipart/form-data; boundary={boundary}')
    return json.loads(raw)


_models_cache: dict = {}


def speech_models() -> list[dict]:
    """Speech synthesis models with prices (cached for an hour)."""
    now = time.time()
    if _models_cache.get('t', 0) > now - 3600:
        return _models_cache['data']
    raw, _ = _request('/models?output_modalities=speech', method='GET', auth=False, timeout=60)
    data = [{'id': m['id'], 'name': m.get('name', m['id']), 'pricing': m.get('pricing', {}),
             'description': (m.get('description') or '')[:300]}
            for m in json.loads(raw).get('data', [])]
    _models_cache.update(t=now, data=data)
    return data
