"""ffmpeg: перевод ответа TTS в моно PCM, обрезка тишины, хранение дублей (opus), сборка дорожек (mp3)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

RATE = 24000  # Гц, моно, s16le — рабочий формат


def ff(*args: str, data: bytes | None = None) -> bytes:
    r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *args], input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(f'ffmpeg: {r.stderr.decode("utf8", "replace")[-500:]}')
    return r.stdout


def to_pcm(raw: bytes, ctype: str) -> bytes:
    """Ответ TTS (pcm с rate=… или любой контейнер) → s16le моно RATE."""
    if 'pcm' in ctype or not ctype:
        rate = re.search(r'rate=(\d+)', ctype)
        src = ['-f', 's16le', '-ar', rate.group(1) if rate else '24000', '-ac', '1']
    else:
        src = []
    return ff(*src, '-i', 'pipe:0', '-f', 's16le', '-ar', str(RATE), '-ac', '1', 'pipe:1', data=raw)


def trim(pcm: bytes, tempo: float = 1.0) -> bytes:
    """Тишина по краям — прочь (паузы между абзацами ставит сборка); tempo — ускорение без смены высоты."""
    af = 'silenceremove=start_periods=1:start_threshold=-50dB,areverse,' \
         'silenceremove=start_periods=1:start_threshold=-50dB,areverse'
    if tempo and tempo != 1:
        af = f'atempo={tempo},{af}'
    return ff('-f', 's16le', '-ar', str(RATE), '-ac', '1', '-i', 'pipe:0', '-af', af,
              '-f', 's16le', '-ar', str(RATE), '-ac', '1', 'pipe:1', data=pcm)


def silence(sec: float) -> bytes:
    return b'\0\0' * int(round(sec * RATE))


def silences(pcm: bytes, db: int = -40, min_len: float = 0.15) -> list[tuple[float, float]]:
    """Паузы в речи: [(начало, конец)] — для разметки предложений, когда распознавание подвело."""
    r = subprocess.run(['ffmpeg', '-v', 'info', '-f', 's16le', '-ar', str(RATE), '-ac', '1', '-i', 'pipe:0',
                        '-af', f'silencedetect=n={db}dB:d={min_len}', '-f', 'null', '-'], input=pcm, capture_output=True)
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', r.stderr.decode())]
    ends = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', r.stderr.decode())]
    return list(zip(starts, ends))


def dur(pcm: bytes) -> float:
    return len(pcm) / 2 / RATE


def save_take(pcm: bytes, path: Path, bitrate: str = '40k') -> None:
    """Дубль абзаца → Opus (речь, ~5 КБ/с): компактно, можно хранить в git."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ff('-f', 's16le', '-ar', str(RATE), '-ac', '1', '-i', 'pipe:0', '-c:a', 'libopus', '-b:a', bitrate,
       '-application', 'voip', str(path), data=pcm)


def save_flac(pcm: bytes, path: Path) -> None:
    ff('-f', 's16le', '-ar', str(RATE), '-ac', '1', '-i', 'pipe:0', '-c:a', 'flac', str(path), data=pcm)


def load(path: Path) -> bytes:
    return ff('-i', str(path), '-f', 's16le', '-ar', str(RATE), '-ac', '1', 'pipe:1')


def encode_mp3(pcm: bytes, path: Path, bitrate: str = '48k', title: str = '', album: str = '', artist: str = '',
               track: str = '') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = []
    for k, v in (('title', title), ('album', album), ('artist', artist), ('track', track)):
        if v:
            meta += ['-metadata', f'{k}={v}']
    ff('-f', 's16le', '-ar', str(RATE), '-ac', '1', '-i', 'pipe:0', '-af', 'loudnorm=I=-18:TP=-1.5:LRA=11',
       '-ar', str(RATE), '-c:a', 'libmp3lame', '-b:a', bitrate, *meta, str(path), data=pcm)
