"""Звук ролика: голос (дубли озвучки на своих местах таймлайна) + фон декораций + музыка + шумы → WAV.

Всё синтезируется здесь же (numpy), детерминированно — без внешних сэмплов:
  фон (storyboard.sound.beds по декорациям; "bed" в кадре — свой фон кадра; смесь — «birds+crowd*0.5»):
    crowd — гомон толпы и шаги, birds — воробьи, трели, шелест листвы, tram — проходящий трамвай и звонок;
    clock — тиканье стенных часов и тишина комнаты,
    crickets — ночной сад, room — просто «воздух», night — тихий гул ночи; rain — дождь за окном (шелест
    и редкие капли по подоконнику), drips — тишина комнаты и капли в таз, wind — ветер, wind-night — ветер в саду
    и редкие сверчки; projector — стрёкот кинопроектора (обтюратор 18 к/с, мотор) — немое кино;
  музыка (storyboard.sound.music — от кадра до кадра): organ — хорал (аккорды «нота+нота:доли», медленная
    атака, орган из гармоник), musicbox — мелодия шкатулки (гребёнка: синус
    с негармоническими обертонами и быстрым затуханием), drone — низкий тянущийся тон (виолончель/фисгармония),
    piano — тапёр: аккорды и ноты «D3+A3:1 F4:0.5 …» на старом, чуть расстроенном пианино (затухающие
    гармоники с негармоничностью струны, молоточек); мелодия и аккомпанемент — две реплики на одном отрезке;
    motor — мотор аэроплана 1910-х (ключи env [[кадр+доля, дБ]] и pitch [[кадр+доля, множитель]]: доплер, пике, обрыв);
  шумы (sfx в кадре: {"name", "at": доля кадра}): click (выключатель), hum (электрический гул 50 Гц — до конца
    кадра), breath (комната «вздыхает»), thump (ладонь о колено), rustle (бумажная карточка), heartbeat, bell (дверной звонок),
    boom (далёкий глухой взрыв), tram-bell (трамвайный звонок).
Музыка и фон приседают под голос (огибающая голоса), итог — громкость под соцсети (−16 LUFS одним усилением, без динамической компрессии).
Свою музыку (файл) тоже можно: {"file": "sound/theme.wav", "from": …}.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config

SR = 48000
NOTE = {n: i for i, n in enumerate(['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'])}


def np():
    import numpy
    return numpy


def hz(name: str) -> float:
    n, octv = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[n] + 12 * (octv + 1) - 69) / 12)


def rng(seed: int):
    return np().random.default_rng(seed)


def db(x: float) -> float:
    return 10 ** (x / 20)


def lowpass(x, cutoff: float):
    """ФНЧ второго порядка в частотной области (быстро, без scipy). Длина FFT — степень двойки: на «неудобных»
    длинах (большие простые множители) pocketfft в разы медленнее."""
    n = np()
    L = len(x)
    N = 1 << max(1, (L - 1).bit_length())
    X = n.fft.rfft(x, N)
    f = n.fft.rfftfreq(N, 1 / SR)
    return n.fft.irfft(X / (1 + (f / cutoff) ** 2), N)[:L]


def smooth(x, win: int):
    """Скользящее среднее (окно win, по центру) через накопленную сумму — как np.convolve(x, ones/win, 'same'),
    но O(N), а не O(N·win)."""
    n = np()
    c = n.concatenate([[0.0], n.cumsum(x)])
    L, h = len(x), win // 2
    lo = n.clip(n.arange(L) - h, 0, L)
    return (c[n.clip(lo + win, 0, L)] - c[lo]) / win


# ---------------------------------------------------------------- инструменты

def musicbox_note(f: float, dur: float = 3.5, vel: float = 1.0, seed: int = 0):
    """Зубец гребёнки шкатулки: основной тон + негармонические обертоны, щелчок атаки, быстрое затухание."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    det = 1 + (r.random() - 0.5) * 0.004
    y = (n.sin(2 * n.pi * f * det * t) * n.exp(-t * 2.2)
         + 0.35 * n.sin(2 * n.pi * f * 2.76 * t) * n.exp(-t * 7)
         + 0.18 * n.sin(2 * n.pi * f * 5.4 * t) * n.exp(-t * 14)
         + 0.08 * n.sin(2 * n.pi * f * 8.9 * t) * n.exp(-t * 25))
    click = r.standard_normal(len(t)) * n.exp(-t * 900) * 0.25
    return (y + click) * vel * n.minimum(1, t * 800)


def drone(freqs: list[float], dur: float, seed: int = 1):
    """Тянущийся низкий тон: несколько пил через ФНЧ, медленное «дыхание» смычка."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    y = n.zeros_like(t)
    for f in freqs:
        for d in (-0.15, 0.0, 0.17):  # хор
            ph = r.random() * 2 * n.pi
            y += ((2 * ((f + d) * t + ph / (2 * n.pi)) % 2) - 1) * 0.2
    y = lowpass(y, 420)
    bow = 0.75 + 0.25 * n.sin(2 * n.pi * 0.09 * t + r.random() * 6)
    return y * bow / max(1, len(freqs))


def clock(dur: float, bpm: float = 54, seed: int = 2):
    """Стенные часы: тик-так (тик чуть выше), между ними — тишина комнаты."""
    n = np()
    out = n.zeros(int(dur * SR))
    r = rng(seed)
    step = 60 / bpm
    k = 0
    for t0 in n.arange(0.3, dur, step):
        L = int(0.05 * SR)
        tt = n.arange(L) / SR
        f = 2900 if k % 2 == 0 else 2400
        tick = (n.sin(2 * n.pi * f * tt) * 0.5 + r.standard_normal(L) * 0.5) * n.exp(-tt * 140)
        tick += n.sin(2 * n.pi * 780 * tt) * n.exp(-tt * 60) * 0.4  # корпус часов
        i = int(t0 * SR)
        out[i:i + L] += tick[:len(out) - i] * 0.5
        k += 1
    return out + room(dur, seed) * 0.6


def room(dur: float, seed: int = 3):
    """Тишина комнаты: очень тихий тёплый шум."""
    n = np()
    return lowpass(rng(seed).standard_normal(int(dur * SR)), 300) * 0.06


def crickets(dur: float, seed: int = 4):
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    y = n.zeros_like(t)
    for c in range(3):
        f = 4200 + r.random() * 900
        rate = 2.3 + r.random() * 1.5
        gate = (n.sin(2 * n.pi * rate * t + r.random() * 6) > 0.55) * (0.5 + 0.5 * n.sin(2 * n.pi * 38 * t))
        y += n.sin(2 * n.pi * f * t) * gate * (0.04 + 0.03 * r.random())
    return lowpass(y, 6000) + room(dur, seed) * 0.8


def _drops(dur: float, rate: float, seed: int, pitch=(900, 2200), decay=(28, 60), gain=0.5):
    """Капли: короткие тональные «плинки» в случайные моменты (rate — в секунду)."""
    n = np()
    r = rng(seed)
    out = n.zeros(int(dur * SR))
    t = r.exponential(1 / rate)
    while t < dur:
        L = int(0.25 * SR)
        tt = n.arange(L) / SR
        f = pitch[0] + r.random() * (pitch[1] - pitch[0])
        k = decay[0] + r.random() * (decay[1] - decay[0])
        x = (n.sin(2 * n.pi * f * tt * (1 + 0.6 * n.exp(-tt * 40))) * n.exp(-tt * k)) * (0.4 + 0.6 * r.random())
        i = int(t * SR)
        out[i:i + L] += x[:len(out) - i]
        t += r.exponential(1 / rate)
    return out * gain


def rain(dur: float, seed: int = 8):
    """Дождь за стеклом: ровный шелест (шум в полосе) с медленной волной силы и капли по подоконнику."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    hiss = lowpass(r.standard_normal(len(t)), 2400) - lowpass(r.standard_normal(len(t)), 250) * 0.3  # тёмный шелест — не спорит с голосом
    swell = 0.8 + 0.2 * n.sin(2 * n.pi * 0.05 * t + r.random() * 6)
    return hiss * swell * 0.05 + _drops(dur, 2.2, seed + 1, (1200, 3000), (45, 90), 0.07) + room(dur, seed) * 0.5


def drips(dur: float, seed: int = 9):
    """Тишина комнаты и капли с потолка в таз — редкие, гулкие."""
    return room(dur, seed) * 0.9 + _drops(dur, 0.45, seed + 2, (520, 900), (9, 16), 0.35)


def wind(dur: float, seed: int = 10):
    """Ветер: шум через ФНЧ, порывы — медленная огибающая."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    low, mid = lowpass(r.standard_normal(len(t)), 220), lowpass(r.standard_normal(len(t)), 900)
    g = 0.5 + 0.5 * n.sin(2 * n.pi * 0.07 * t + r.random() * 6) * n.sin(2 * n.pi * 0.023 * t + r.random() * 6)
    return (low * 0.5 + mid * 0.25 * g) * (0.4 + 0.6 * g) * 0.8


def wind_night(dur: float, seed: int = 11):
    return wind(dur, seed) * 0.8 + crickets(dur, seed) * 0.35


def organ(notes: str, bpm: float, seed: int = 12):
    """Хорал на органе: «D3+A3+F4:4 …» — аккорды, медленная атака и отпускание, гармоники трубы (флейтовый регистр)."""
    n = np()
    spb = 60 / bpm
    ev, t = [], 0.0
    for tok in notes.split():
        name, _, beats = tok.partition(':')
        d = float(beats or 1) * spb
        if name != '-':
            ev.append((t, d, [hz(x) for x in name.split('+')]))
        t += d
    out = n.zeros(int((t + 3) * SR))
    for t0, d, fs in ev:
        L = int((d + 1.2) * SR)
        tt = n.arange(L) / SR
        env = n.minimum(1, tt / 0.35) * n.where(tt > d, n.exp(-(tt - d) * 3.5), 1)
        y = sum(sum(a * n.sin(2 * n.pi * f * h * tt * (1 + 0.0015 * n.sin(2 * n.pi * 4.8 * tt))) for h, a in ((1, 1), (2, 0.45), (3, 0.18), (4, 0.1)))
                for f in fs) / max(1, len(fs))
        i = int(t0 * SR)
        out[i:i + L] += (y * env)[:len(out) - i]
    return lowpass(out, 2400) * 0.5


def piano_note(f: float, dur: float, vel: float = 1.0, seed: int = 0):
    """Нота пианино: гармоники с негармоничностью (B), верхние гаснут быстрее, двухступенчатое затухание,
    две струны чуть врозь (биения старого инструмента), стук молоточка; глушится демпфером после dur."""
    n = np()
    r = rng(seed)
    L = int((dur + 0.6) * SR)
    t = n.arange(L) / SR
    B = 0.0004
    y = n.zeros(L)
    detune = 1 + (r.random() - 0.5) * 0.006
    for k in range(1, 9):
        fk = f * k * (1 + B * k * k) ** 0.5
        if fk > 9000:
            break
        a = 1 / k ** 1.25 * (1.25 if k == 2 else 1)
        decay = (1.1 + 0.55 * k) * (f / 260) ** 0.35
        env = 0.7 * n.exp(-t * decay) + 0.3 * n.exp(-t * decay * 0.18)
        y += a * env * (n.sin(2 * n.pi * fk * t) + 0.8 * n.sin(2 * n.pi * fk * detune * t + r.random()))
    y += lowpass(r.standard_normal(L), 2500) * n.exp(-t * 60) * 0.25  # молоточек
    damper = n.where(t > dur, n.exp(-(t - dur) * 9), 1)
    return y * damper * n.minimum(1, t * 2000) * vel * 0.3


def piano(notes: str, bpm: float, *, rit: float = 0.0, seed: int = 13):
    """Тапёр: «D3+A3+F4:2 E4:0.5 -:1 …» — аккорды (ноты через +, лёгкое арпеджио) с долями; - — пауза.
    rit — замедление к концу. Громкость нот — чуть случайная, бас — мягче."""
    n = np()
    toks = notes.split()
    ev, t = [], 0.0
    for i, tok in enumerate(toks):
        name, _, beats = tok.partition(':')
        d = float(beats or 1) * 60 / bpm * (1 + rit * (i / max(1, len(toks) - 1)) ** 2)
        if name != '-':
            ev.append((t, d, [hz(x) for x in name.split('+')]))
        t += d
    out = n.zeros(int((t + 3) * SR))
    r = rng(seed)
    for k, (t0, d, fs) in enumerate(ev):
        for j, f in enumerate(sorted(fs)):
            x = piano_note(f, max(0.25, d * 1.05), vel=(0.75 + 0.25 * r.random()) * (0.8 if f < 160 else 1), seed=seed + k * 7 + j)
            i = int((t0 + j * 0.012) * SR)
            out[i:i + len(x)] += x[:len(out) - i]
    return lowpass(out, 3800)


def projector(dur: float, seed: int = 14):
    """Кинопроектор в зале: стрёкот обтюратора (18 щелчков в секунду с «механическим» узором), гул мотора."""
    n = np()
    r = rng(seed)
    t = n.arange(int(dur * SR)) / SR
    out = n.zeros_like(t)
    L = int(0.012 * SR)
    tt = n.arange(L) / SR
    click = lowpass(r.standard_normal(L), 3000) * n.exp(-tt * 500)
    for k, t0 in enumerate(n.arange(0.05, dur, 1 / 18)):
        i = int((t0 + (r.random() - 0.5) * 0.004) * SR)
        a = (1.0 if k % 2 == 0 else 0.6) * (0.8 + 0.2 * r.random())
        out[i:i + L] += click[:len(out) - i] * a
    motor = sum(a * n.sin(2 * n.pi * f * t) for f, a in ((54, 0.5), (108, 0.25), (162, 0.1)))
    return lowpass(out, 2600) * 0.09 + motor * 0.012 + room(dur, seed) * 0.5


def bandpass(x, lo: float, hi: float):
    return lowpass(x, hi) - lowpass(x, lo)


def _phrases(L: int, r, on=(1.2, 4.0), off=(0.4, 2.5)):
    """Огибающая «говорит — молчит»: куски речи и паузы случайной длины (мягкие края)."""
    n = np()
    g = n.zeros(L)
    t = r.random() * off[1]
    while t * SR < L:
        a = int(t * SR)
        t += on[0] + r.random() * (on[1] - on[0])
        g[a:min(L, int(t * SR))] = 1
        t += off[0] + r.random() * (off[1] - off[0])
    return smooth(g, int(0.12 * SR))


def crowd(dur: float, seed: int = 15):
    """Гомон толпы на улице: невнятные голоса (тон с плавающей высотой, слоговой ритм 3–6 Гц, фразы и паузы,
    разные расстояния) через полосу «речи» 300–1800 Гц, дыхание толпы и шаги по мостовой."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    t = n.arange(L) / SR
    voiced = n.zeros(L)
    for v in range(16):
        f0 = (105 + r.random() * 60) if v % 2 else (185 + r.random() * 70)       # мужские и женские голоса
        f = f0 * (1 + 0.09 * n.sin(2 * n.pi * (0.2 + r.random() * 0.3) * t + r.random() * 6)
                  + 0.04 * n.sin(2 * n.pi * (1.3 + r.random()) * t + r.random() * 6))  # интонация
        saw = (n.cumsum(f) / SR + r.random()) % 1 * 2 - 1
        syl = (0.5 + 0.5 * n.sin(2 * n.pi * (3.2 + r.random() * 2.6) * t + r.random() * 6)) ** 2
        voiced += saw * syl * _phrases(L, r) * (0.25 + 0.75 * r.random() ** 2)
    voiced = bandpass(bandpass(voiced, 300, 1800), 300, 1800)  # дважды — круче края: голоса глухие, вдали
    hiss = bandpass(bandpass(r.standard_normal(L), 400, 2600), 400, 2600) * (0.6 + 0.4 * n.sin(2 * n.pi * 0.11 * t + r.random() * 6))
    steps = n.zeros(L)
    Ls = int(0.05 * SR)
    ts = n.arange(Ls) / SR
    click = lowpass(r.standard_normal(Ls), 1400) * n.exp(-ts * 70)
    k = r.exponential(1 / 7)
    while k < dur - 0.06:
        i = int(k * SR)
        steps[i:i + Ls] += click * (0.3 + 0.7 * r.random())
        k += r.exponential(1 / 7)
    return voiced * 0.04 + hiss * 0.014 + steps * 0.15 + room(dur, seed) * 0.6


def _chirp(f1: float, f2: float, d: float, vib: float = 0.0):
    n = np()
    t = n.arange(int(d * SR)) / SR
    f = f1 + (f2 - f1) * t / d + vib * n.sin(2 * n.pi * 38 * t)
    return n.sin(2 * n.pi * n.cumsum(f) / SR) * n.sin(n.pi * t / d) ** 2


def birds(dur: float, seed: int = 16):
    """Летний сквер: воробьи (короткие чирики сериями), изредка трель, шелест листвы на ветру."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    out = n.zeros(L)
    for b in range(4):  # воробьи на разных ветках: своя высота, своя громкость
        base, amp = 3600 + r.random() * 1400, 0.25 + 0.6 * r.random()
        t = r.random() * 3
        while t < dur - 1:
            for _ in range(int(2 + r.random() * 5)):
                d = 0.05 + r.random() * 0.05
                x = _chirp(base * (1.1 + 0.2 * r.random()), base * (0.75 + 0.1 * r.random()), d)
                _place(out, x * amp * (0.6 + 0.4 * r.random()), t)
                t += d + 0.06 + r.random() * 0.12
            t += 1.5 + r.exponential(3)
    t = 4 + r.random() * 6
    while t < dur - 3:  # трель: быстрые ноты вверх-вниз
        f = 2600 + r.random() * 1200
        for i in range(int(6 + r.random() * 8)):
            x = _chirp(f * (1 + 0.25 * ((i % 3) - 1)), f * (1.15 + 0.2 * r.random()), 0.07, vib=180)
            _place(out, x * 0.35, t)
            t += 0.085
        t += 9 + r.exponential(10)
    tt = n.arange(L) / SR
    leaves = bandpass(r.standard_normal(L), 1800, 6000) * (0.3 + 0.7 * (0.5 + 0.5 * n.sin(2 * n.pi * 0.06 * tt + r.random() * 6)) ** 3)
    return lowpass(out, 8000) * 0.14 + leaves * 0.01 + room(dur, seed) * 0.6


def _bell(f: float = 1650, d: float = 1.4):
    """Удар трамвайного колокольчика: негармонические обертоны, звон гаснет."""
    n = np()
    t = n.arange(int(d * SR)) / SR
    y = sum(a * n.sin(2 * n.pi * f * k * t) * n.exp(-t * (3.5 + 3 * k)) for k, a in ((1, 1), (2.4, 0.5), (3.9, 0.3), (5.6, 0.15)))
    return y * n.minimum(1, t * 3000)


def tram(dur: float, seed: int = 17):
    """Улица с трамваем: проходящий вагон (нарастающий и уходящий гул, стук колёс на стыках рельсов, скрип),
    звонок «дзинь-дзинь»; между вагонами — только город."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    tt = n.arange(L) / SR
    out = n.zeros(L)
    rumble = lowpass(r.standard_normal(L), 140) + bandpass(r.standard_normal(L), 300, 900) * 0.25
    env = n.zeros(L)
    t = 2 + r.random() * 8
    while t < dur:
        T = 10 + r.random() * 6  # вагон проходит
        a, b = int(t * SR), min(L, int((t + T) * SR))
        if b > a:
            x = n.arange(b - a) / SR
            env[a:b] = n.maximum(env[a:b], n.sin(n.pi * x / T) ** 2)
            for c in n.arange(1.0, T - 1, 0.95 + r.random() * 0.2):  # стыки: «та-так» — две колёсные пары
                for off in (0, 0.13):
                    k = t + c + off
                    if k < dur - 0.1:
                        click = lowpass(r.standard_normal(int(0.06 * SR)), 900) * n.exp(-n.arange(int(0.06 * SR)) / SR * 60)
                        _place(out, click * 0.6 * n.sin(n.pi * c / T) ** 2, k)
        if r.random() < 0.7 and t + 1 < dur:
            for k in range(2):
                _place(out, _bell(1650 + r.random() * 80) * 0.22, t + 1.5 + k * 0.28)
        t += T + 6 + r.exponential(12)
    return rumble * env * 0.16 + out * 0.25 + room(dur, seed) * 0.5


def _keys(keys, x, default: float = 0.0):
    """Ключи [[доля, значение], …] → значения в точках x (линейно, края — по крайним ключам)."""
    n = np()
    if not keys:
        return n.full_like(x, default)
    ks = sorted(keys)
    return n.interp(x, [k[0] for k in ks], [k[1] for k in ks])


def motor(dur: float, pitch=None, env=None, seed: int = 18):
    """Аэроплан 1910-х: ротативный мотор — «сверлящее» тарахтение (вспышки цилиндров ~45 Гц с пропусками),
    гул выхлопа и свист винта. pitch, env — ключи [[доля, множитель]], [[доля, дБ]]: доплер на пролёте,
    вой в пике, обрыв."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    u = n.arange(L) / max(1, L - 1)
    p = _keys(pitch, u, 1.0)
    cyc = n.cumsum(45 * p) / SR                                   # вспышки цилиндров
    idx = cyc.astype(int)
    jitter = 0.55 + 0.45 * r.random(idx[-1] + 2)                  # неровная работа, пропуски
    jitter[r.random(len(jitter)) < 0.06] = 0.15
    frac = cyc % 1
    pulse = n.exp(-frac * 9) * jitter[idx]
    bark = lowpass(pulse - pulse.mean(), 2400)
    exhaust = bandpass(r.standard_normal(L), 200, 1500) * smooth(pulse, int(0.004 * SR))
    prop = bandpass(r.standard_normal(L), 900, 3200) * (0.6 + 0.4 * n.sin(2 * n.pi * n.cumsum(30 * p) / SR))
    hum = sum(a * n.sin(2 * n.pi * n.cumsum(f * p) / SR) for f, a in ((90, 0.3), (180, 0.4), (270, 0.35), (360, 0.3), (540, 0.2), (720, 0.1)))
    y = bark * 0.7 + exhaust * 0.3 + prop * 0.05 + hum * 0.16
    return y * db(_keys(env, u, 0.0))


BEDS = {'clock': clock, 'crickets': crickets, 'room': room, 'rain': rain, 'drips': drips, 'wind': wind,
        'wind-night': wind_night, 'projector': projector, 'crowd': crowd, 'birds': birds, 'tram': tram}


def bed(kind: str, dur: float, seed: int = 0):
    """Фон: одно имя или смесь «birds+crowd*0.5» (множитель — громкость слагаемого)."""
    out = None
    for part in kind.split('+'):
        name, _, k = part.strip().partition('*')
        x = BEDS.get(name, room)(dur, seed=seed) * float(k or 1)
        out = x if out is None else out + x
    return out


def sfx(name: str, dur: float, seed: int = 5):
    n = np()
    r = rng(seed)
    if name == 'click':  # выключатель: щелчок + короткий металлический призвук
        L = int(0.12 * SR)
        t = n.arange(L) / SR
        return (r.standard_normal(L) * n.exp(-t * 400) + n.sin(2 * n.pi * 1900 * t) * n.exp(-t * 90) * 0.5) * 0.8
    if name == 'hum':  # электрический свет: 50 Гц с гармониками, лёгкое дрожание
        t = n.arange(int(dur * SR)) / SR
        y = sum(a * n.sin(2 * n.pi * 50 * k * t) for k, a in ((1, 0.5), (2, 0.35), (3, 0.2), (4, 0.12), (6, 0.06)))
        return y * (0.9 + 0.1 * n.sin(2 * n.pi * 0.7 * t)) * n.minimum(1, t / 0.08) * 0.12
    if name == 'breath':  # комната вздыхает: шум через ФНЧ, вдох-выдох
        t = n.arange(int(min(dur, 4.5) * SR)) / SR
        env = n.sin(n.pi * n.clip(t / 2.2, 0, 1)) ** 2 * 0.8 + n.sin(n.pi * n.clip((t - 2.2) / 2.3, 0, 1)) ** 2
        return lowpass(r.standard_normal(len(t)), 900) * env * 0.5
    if name == 'thump':
        L = int(0.4 * SR)
        t = n.arange(L) / SR
        return (n.sin(2 * n.pi * 70 * t) * n.exp(-t * 18) + lowpass(r.standard_normal(L), 400) * n.exp(-t * 30) * 0.6) * 0.9
    if name == 'rustle':  # бумага: короткие полосы шума
        L = int(0.5 * SR)
        t = n.arange(L) / SR
        g = (r.random(L) < 0.02).astype(float)
        return lowpass(r.standard_normal(L) * (0.3 + g * 3), 3500) * n.exp(-t * 6) * 0.35
    if name == 'bell':  # электрический дверной звонок: молоточек по чашке ~22 раза в секунду, ~1.3 с
        t = n.arange(int(1.4 * SR)) / SR
        strike = (n.sin(2 * n.pi * 22 * t) > 0.6).astype(float)
        tone = n.sin(2 * n.pi * 1180 * t) + 0.6 * n.sin(2 * n.pi * 2950 * t) + 0.3 * n.sin(2 * n.pi * 4400 * t)
        env = n.minimum(1, t / 0.01) * n.where(t > 1.25, n.exp(-(t - 1.25) * 25), 1)
        return lowpass(tone * (0.35 + 0.65 * smooth(strike, 120)) * env, 5000) * 0.35
    if name == 'heartbeat':
        t = n.arange(int(dur * SR)) / SR
        y = n.zeros_like(t)
        for b in n.arange(0.1, dur, 0.86):
            for off, a in ((0, 1), (0.22, 0.7)):
                i = int((b + off) * SR)
                L = min(int(0.25 * SR), len(y) - i)
                if L > 0:
                    tt = n.arange(L) / SR
                    y[i:i + L] += n.sin(2 * n.pi * 55 * tt) * n.exp(-tt * 22) * a
        return y * 0.9
    if name == 'boom':  # далёкий глухой взрыв: удар, низкий раскат, гаснущий гул
        t = n.arange(int(min(dur, 5) * SR)) / SR
        crack = lowpass(r.standard_normal(len(t)), 900) * n.exp(-t * 25)
        roll = lowpass(r.standard_normal(len(t)), 110) * n.minimum(1, t / 0.03) * n.exp(-t * 0.9) * (1 + 0.3 * n.sin(2 * n.pi * 3 * t))
        return (crack * 0.5 + roll * 3.5) * 0.6
    if name == 'tram-bell':  # трамвайный звонок «дзинь-дзинь»
        y = n.zeros(int(1.9 * SR))
        for k in range(2):
            _place(y, _bell(1660), k * 0.28)
        return y * 0.4
    raise KeyError(f'нет шума {name}')


def melody(notes: str, bpm: float, *, rit: float = 0.0, seed: int = 7):
    """«A4:1 D5:2 -:1 …» — нота:доли (- — пауза). rit — замедление к концу (шкатулка заводом кончается)."""
    n = np()
    ev, t = [], 0.0
    toks = notes.split()
    for i, tok in enumerate(toks):
        name, _, beats = tok.partition(':')
        b = float(beats or 1)
        slow = 1 + rit * (i / max(1, len(toks) - 1)) ** 2
        if name != '-':
            for nm in name.split('+'):
                ev.append((t, hz(nm)))
        t += b * 60 / bpm * slow
    out = n.zeros(int((t + 4) * SR))
    for k, (t0, f) in enumerate(ev):
        x = musicbox_note(f, seed=seed + k, vel=0.8 + 0.2 * rng(seed + k).random())
        i = int(t0 * SR)
        out[i:i + len(x)] += x[:len(out) - i]
    return out


# ---------------------------------------------------------------- отпечаток

MUSIC = {'organ': 'organ', 'piano': 'piano', 'drone': 'drone', 'motor': 'motor'}  # прочее (без file) — melody (шкатулка)


def signature(sb: dict, tl: dict) -> str:
    """Код, от которого зависит звук постановки: сведение + генераторы её фонов, музыки и шумов (с зависимостями).
    Отпечаток звука на сайте — от него, а не от всего файла: новый фон или шум для одной постановки не пересчитывает
    звук остальных."""
    import inspect
    import re
    import sys
    mod = sys.modules[__name__]
    funcs = {k: v for k, v in vars(mod).items() if inspect.isfunction(v) and v.__module__ == __name__}
    per_kind = {'bed', 'sfx', 'melody', *MUSIC.values(), *(f.__name__ for f in BEDS.values())}
    parts, seen = [], set()

    def add(key: str, src: str | None = None):
        if key in seen:
            return
        seen.add(key)
        src = src or inspect.getsource(funcs[key])
        parts.append(src)
        skip = per_kind if key in ('build', 'bed') else {'sfx'}  # диспетчеры зовут все генераторы — берём только нужные
        for dep in sorted(set(re.findall(r'\b([A-Za-z_]\w*)\(', src))):  # вызовы (локальная переменная motor — не функция)
            if dep in funcs and dep not in skip:
                add(dep)
    add('build')
    snd = sb.get('sound') or {}
    kinds = set((snd.get('beds') or {}).values()) | {sh['bed'] for sc in sb.get('scenes') or [] for sh in sc.get('shots') or [] if sh.get('bed')}
    for kind in sorted(k for k in kinds if k):
        add('bed')
        add('room')  # запасной фон bed() — без вызова в коде
        for part in kind.split('+'):
            name = part.strip().partition('*')[0]
            add(BEDS.get(name, room).__name__)
    for cue in snd.get('music') or []:
        if not cue.get('file'):
            add(MUSIC.get(cue.get('kind'), 'melody'))
    names = sorted({e['name'] for s in tl.get('shots') or [] for e in s.get('sfx') or []})
    if names:  # шумы — одна функция с ветками: берём заголовок и ветки нужных шумов
        lines = inspect.getsource(sfx).split('\n')
        starts = [i for i, ln in enumerate(lines) if re.match(r"    if name == '", ln)] + [len(lines)]
        add('sfx:head', '\n'.join(lines[:starts[0]]))
        for a, b in zip(starts, starts[1:]):
            name = re.match(r"    if name == '([^']+)'", lines[a]).group(1)
            if name in names:
                add(f'sfx:{name}', '\n'.join(lines[a:b]))
    return '\n'.join(_code_only(p) for p in parts)


def _code_only(src: str) -> str:
    """Code without comments and docstrings: translating or editing them doesn't change the sound fingerprint."""
    import io
    import tokenize
    import textwrap
    skip = {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER}
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(textwrap.dedent(src)).readline) if t.type not in skip]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src
    out = []
    for i, t in enumerate(toks):
        stmt_start = i == 0 or toks[i - 1].type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
        stmt_end = i + 1 == len(toks) or toks[i + 1].type == tokenize.NEWLINE
        if t.type == tokenize.STRING and stmt_start and stmt_end:
            continue  # a bare string statement — a docstring
        out.append({tokenize.NEWLINE: '\n', tokenize.INDENT: '>', tokenize.DEDENT: '<'}.get(t.type, t.string))
    return ' '.join(out)


# ---------------------------------------------------------------- сведение

def _place(buf, x, t0: float, gain: float = 1.0):
    i = int(round(t0 * SR))
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    if j > i:
        buf[i:j] += x[:j - i] * gain


def _load(path: Path):
    n = np()
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', str(SR), 'pipe:1'],
                         capture_output=True, check=True).stdout
    return n.frombuffer(raw, n.float32).astype(n.float64)


def _fade(x, fin: float, fout: float):
    n = np()
    L = len(x)
    env = n.ones(L)
    a, b = int(fin * SR), int(fout * SR)
    if a:
        env[:min(a, L)] = n.linspace(0, 1, min(a, L))
    if b:
        env[max(0, L - b):] *= n.linspace(1, 0, L - max(0, L - b))
    return x * env


def build(slug: str, tl: dict, out: Path, *, log=print) -> Path:
    n = np()
    sdir = config.story_dir(slug)
    sb = config.read_json(sdir / 'storyboard.json', {}) or {}
    snd = sb.get('sound') or {}
    dur = tl['duration']
    L = int(dur * SR) + SR
    voice, bed_, music, fx = n.zeros(L), n.zeros(L), n.zeros(L), n.zeros(L)

    for p in tl['paragraphs']:  # голос: дубли на своих местах
        if p.get('take'):
            x, at, shift = _load(config.text_dir(slug) / p['take']), 0, 0.0
            for cut, hold in p.get('cuts') or []:   # паузы внутри абзаца: дубль режется между предложениями
                i = int(round(cut * SR))
                _place(voice, x[at:i], p['t0'] + shift + at / SR)
                at, shift = i, shift + hold
            _place(voice, x[at:], p['t0'] + shift + at / SR)
    peak = n.abs(voice).max() or 1
    voice *= db(-3) / peak

    shots = tl['shots']
    by_id = {s['id']: s for s in shots}
    # фон декораций: непрерывно, пока декорация на экране; стык — короткий кроссфейд
    beds = snd.get('beds') or {}
    own = {sh['id']: sh['bed'] for sc in sb.get('scenes') or [] for sh in sc.get('shots') or [] if 'bed' in sh}  # фон кадра
    kind_of = lambda s: own.get(s['id'], beds.get(s['set']))  # noqa: E731
    k = 0
    while k < len(shots):  # подряд идущие кадры с тем же фоном — один непрерывный кусок
        kind = kind_of(shots[k])
        j = k
        while j + 1 < len(shots) and kind_of(shots[j + 1]) == kind:
            j += 1
        if kind:
            t0, t1 = shots[k]['t0'], shots[j]['t1']
            _place(bed_, _fade(bed(kind, t1 - t0 + 0.4, seed=k), 0.3, 0.4), t0)
        k = j + 1

    def span(cue):
        a = by_id.get(cue.get('from')) or shots[0]
        b = by_id.get(cue.get('to'))
        return a['t0'] + float(cue.get('offset', 0)), (b['t0'] if b else dur)

    for cue in snd.get('music') or []:
        if cue.get('from') and cue['from'] not in by_id and cue.get('to') not in by_id:
            continue
        t0, t1 = span(cue)
        if t1 <= t0:
            continue
        if cue.get('file'):
            x = _load(sdir / cue['file'])[: int((t1 - t0) * SR)]
        elif cue.get('kind') == 'organ':
            x = organ(cue.get('notes', ''), cue.get('bpm', 40))
            x = x[: int((t1 - t0) * SR)] if cue.get('cut', True) else x
        elif cue.get('kind') == 'piano':
            x = piano(cue.get('notes', ''), cue.get('bpm', 60), rit=cue.get('rit', 0), seed=sum(map(ord, cue.get('from', 'x'))))
            if cue.get('loop'):  # тапёр играет, пока идёт отрезок: фраза повторяется
                x = n.tile(x[: int(len(x) - 3 * SR)], int((t1 - t0) // max(1, len(x) / SR - 3)) + 1)
            x = x[: int((t1 - t0) * SR)]
        elif cue.get('kind') == 'motor':  # ключи — доля отрезка или «кадр+доля»: доплер, пике, обрыв на ударе
            at = lambda key: (key if isinstance(key, (int, float)) else (lambda sid, _, f: (  # noqa: E731
                by_id[sid]['t0'] + float(f or 0) * (by_id[sid]['t1'] - by_id[sid]['t0']) - t0) / (t1 - t0))(*key.partition('+')))
            x = motor(t1 - t0, pitch=[[at(a), v] for a, v in cue.get('pitch') or []],
                      env=[[at(a), v] for a, v in cue.get('env') or []], seed=sum(map(ord, cue.get('from', 'x'))))
        elif cue.get('kind') == 'drone':
            x = drone([hz(f) for f in cue.get('notes', ['D2', 'A2'])], t1 - t0, seed=sum(map(ord, cue.get('from', 'x'))))
        else:
            x = melody(cue.get('notes', ''), cue.get('bpm', 60), rit=cue.get('rit', 0))
            x = x[: int((t1 - t0) * SR)] if cue.get('cut', True) else x
        x = _fade(x, cue.get('fade_in', 0.8), cue.get('fade_out', 1.5))
        x = x[: int((t1 - t0 + cue.get('tail', 0)) * SR)]
        _place(music, x, t0, db(cue.get('gain', -20)))

    for s in shots:  # шумы в кадрах: at — доля кадра, before_end — секунд до конца кадра
        for e in s.get('sfx') or []:
            t0 = s['t1'] - float(e['before_end']) if 'before_end' in e else s['t0'] + (s['t1'] - s['t0']) * float(e.get('at', 0))
            if e.get('stop_all'):  # дальше — тишина (кроме самого шума)
                i = int(t0 * SR)
                for buf in (bed_, music, fx):
                    buf[i:] *= 0
            length = (s['t1'] - t0) if e.get('to_end') else (dur - t0)
            _place(fx, sfx(e['name'], max(0.2, length), seed=sum(map(ord, s['id']))), t0, db(e.get('gain', -12)))

    # музыка и фон приседают под голос
    win = int(0.25 * SR)
    env = n.sqrt(n.maximum(smooth(voice ** 2, win), 0))
    duck = 1 - 0.55 * n.clip(env / 0.05, 0, 1)
    duck = smooth(duck, win)
    bd = float(snd.get('bed_duck', 0.4))  # насколько фон приседает под голос (0 — не приседает)
    mix = voice + (music * duck) + bed_ * db(snd.get('bed_gain', -8)) * (1 - bd + bd * duck) + fx
    mix = mix[: int(dur * SR)]
    fo = int(float(tl.get('fade_out') or 0) * SR)  # затухание в конце фильма (вместе с картинкой)
    if fo:
        mix[-fo:] *= n.cos(n.linspace(0, n.pi / 2, fo)) ** 2
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.raw.wav')
    pcm = (n.clip(mix / max(1.0, n.abs(mix).max()), -1, 1) * 32767).astype(n.int16)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', str(tmp)],
                   input=pcm.tobytes(), check=True)
    # громкость −16 LUFS одним общим усилением (замер → volume → ограничитель пиков): однопроходный loudnorm
    # динамический — он подтягивал тихое (дождь в паузах, вступление, финал) почти до уровня голоса
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(tmp), '-af', 'loudnorm=I=-16:TP=-1.5:print_format=json',
                        '-f', 'null', '-'], capture_output=True, text=True, check=True)
    measured = float(json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])['input_i'])
    gain = -16.0 - measured if measured > -70 else 0.0
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(tmp), '-af', f'volume={gain:.2f}dB,alimiter=limit=0.84:level=false',
                    '-ar', str(SR), '-ac', '2', str(out)], check=True)
    tmp.unlink()
    log(f'✓ звук → {out.relative_to(config.ROOT)} ({dur:.1f} с)')
    return out
