"""Film sound: the voice (narration takes in their places on the timeline) + set ambience + music + effects → WAV.

Everything is synthesized right here (numpy), deterministically — no external samples:
  ambience (storyboard.sound.beds by set; "bed" in a shot — the shot's own ambience; a mix — "birds+crowd*0.5"):
    crowd — the murmur of a crowd and footsteps, birds — sparrows, trills, rustling leaves, tram — a passing tram and its bell;
    clock — the ticking of a wall clock and the quiet of a room,
    crickets — a garden at night, room — just "air", night — a quiet hum of the night; rain — rain outside the window (a hiss
    and occasional drops on the sill), drips — a quiet room and drops into a basin, wind — wind, wind-night — wind in the garden
    and occasional crickets; projector — the whirr of a film projector (an 18 fps shutter, the motor) — silent cinema;
  music (storyboard.sound.music — from shot to shot): organ — a chorale (chords "note+note:beats", a slow
    attack, an organ built from harmonics), musicbox — a music-box melody (the comb: a sine
    with inharmonic overtones and a fast decay), drone — a low sustained tone (cello/harmonium),
    piano — a silent-film pianist: chords and notes "D3+A3:1 F4:0.5 …" on an old, slightly out-of-tune piano (decaying
    harmonics with string inharmonicity, the hammer); melody and accompaniment — two cues over the same span;
    motor — a 1910s aeroplane engine (keys env [[shot+share, dB]] and pitch [[shot+share, factor]]: Doppler, a dive, a cut-out);
  effects (sfx in a shot: {"name", "at": share of the shot}): click (a light switch), hum (a 50 Hz electric hum — to the end
    of the shot), breath (the room "sighs"), thump (a palm on a knee), rustle (a paper card), heartbeat, bell (a door bell),
    boom (a distant muffled explosion), tram-bell (a tram bell).
Music and ambience duck under the voice (the voice envelope); the result is loudness for social media (−16 LUFS with one gain, no dynamic compression).
Your own music (a file) works too: {"file": "sound/theme.wav", "from": …}.
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
    """A second-order low-pass in the frequency domain (fast, no scipy). The FFT length is a power of two: at "awkward"
    lengths (large prime factors) pocketfft is many times slower."""
    n = np()
    L = len(x)
    N = 1 << max(1, (L - 1).bit_length())
    X = n.fft.rfft(x, N)
    f = n.fft.rfftfreq(N, 1 / SR)
    return n.fft.irfft(X / (1 + (f / cutoff) ** 2), N)[:L]


def smooth(x, win: int):
    """A moving average (window win, centred) via a cumulative sum — like np.convolve(x, ones/win, 'same'),
    but O(N) rather than O(N·win)."""
    n = np()
    c = n.concatenate([[0.0], n.cumsum(x)])
    L, h = len(x), win // 2
    lo = n.clip(n.arange(L) - h, 0, L)
    return (c[n.clip(lo + win, 0, L)] - c[lo]) / win


# ---------------------------------------------------------------- instruments

def musicbox_note(f: float, dur: float = 3.5, vel: float = 1.0, seed: int = 0):
    """A music-box comb tooth: the fundamental + inharmonic overtones, an attack click, a fast decay."""
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
    """A sustained low tone: several saws through a low-pass, the slow "breathing" of a bow."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    y = n.zeros_like(t)
    for f in freqs:
        for d in (-0.15, 0.0, 0.17):  # chorus
            ph = r.random() * 2 * n.pi
            y += ((2 * ((f + d) * t + ph / (2 * n.pi)) % 2) - 1) * 0.2
    y = lowpass(y, 420)
    bow = 0.75 + 0.25 * n.sin(2 * n.pi * 0.09 * t + r.random() * 6)
    return y * bow / max(1, len(freqs))


def clock(dur: float, bpm: float = 54, seed: int = 2):
    """A wall clock: tick-tock (the tick slightly higher), the quiet of the room in between."""
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
        tick += n.sin(2 * n.pi * 780 * tt) * n.exp(-tt * 60) * 0.4  # the clock case
        i = int(t0 * SR)
        out[i:i + L] += tick[:len(out) - i] * 0.5
        k += 1
    return out + room(dur, seed) * 0.6


def room(dur: float, seed: int = 3):
    """The quiet of a room: a very soft warm noise."""
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
    """Drops: short tonal "plinks" at random moments (rate — per second)."""
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
    """Rain behind the glass: an even hiss (band noise) with a slow wave of intensity, and drops on the sill."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    hiss = lowpass(r.standard_normal(len(t)), 2400) - lowpass(r.standard_normal(len(t)), 250) * 0.3  # a dark hiss — doesn't fight the voice
    swell = 0.8 + 0.2 * n.sin(2 * n.pi * 0.05 * t + r.random() * 6)
    return hiss * swell * 0.05 + _drops(dur, 2.2, seed + 1, (1200, 3000), (45, 90), 0.07) + room(dur, seed) * 0.5


def drips(dur: float, seed: int = 9):
    """The quiet of a room and drops from the ceiling into a basin — rare, resonant."""
    return room(dur, seed) * 0.9 + _drops(dur, 0.45, seed + 2, (520, 900), (9, 16), 0.35)


def wind(dur: float, seed: int = 10):
    """Wind: noise through a low-pass, gusts — a slow envelope."""
    n = np()
    t = n.arange(int(dur * SR)) / SR
    r = rng(seed)
    low, mid = lowpass(r.standard_normal(len(t)), 220), lowpass(r.standard_normal(len(t)), 900)
    g = 0.5 + 0.5 * n.sin(2 * n.pi * 0.07 * t + r.random() * 6) * n.sin(2 * n.pi * 0.023 * t + r.random() * 6)
    return (low * 0.5 + mid * 0.25 * g) * (0.4 + 0.6 * g) * 0.8


def wind_night(dur: float, seed: int = 11):
    return wind(dur, seed) * 0.8 + crickets(dur, seed) * 0.35


def organ(notes: str, bpm: float, seed: int = 12):
    """An organ chorale: "D3+A3+F4:4 …" — chords, slow attack and release, pipe harmonics (a flute register)."""
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
    """A piano note: harmonics with inharmonicity (B), the upper ones decay faster, a two-stage decay,
    two strings slightly apart (the beating of an old instrument), the hammer knock; damped after dur."""
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
    y += lowpass(r.standard_normal(L), 2500) * n.exp(-t * 60) * 0.25  # the hammer
    damper = n.where(t > dur, n.exp(-(t - dur) * 9), 1)
    return y * damper * n.minimum(1, t * 2000) * vel * 0.3


def piano(notes: str, bpm: float, *, rit: float = 0.0, seed: int = 13):
    """A silent-film pianist: "D3+A3+F4:2 E4:0.5 -:1 …" — chords (notes joined by +, a light arpeggio) with beats; - — a rest.
    rit — slowing towards the end. Note loudness is slightly random, the bass is softer."""
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
    """A projector in the hall: the whirr of the shutter (18 clicks a second with a "mechanical" pattern), the motor's hum."""
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
    """A "talking — silent" envelope: spans of speech and pauses of random length (soft edges)."""
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
    """The murmur of a street crowd: indistinct voices (a tone with drifting pitch, a syllable rhythm of 3–6 Hz, phrases and pauses,
    different distances) through a 300–1800 Hz "speech" band, the breathing of the crowd and steps on the pavement."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    t = n.arange(L) / SR
    voiced = n.zeros(L)
    for v in range(16):
        f0 = (105 + r.random() * 60) if v % 2 else (185 + r.random() * 70)       # male and female voices
        f = f0 * (1 + 0.09 * n.sin(2 * n.pi * (0.2 + r.random() * 0.3) * t + r.random() * 6)
                  + 0.04 * n.sin(2 * n.pi * (1.3 + r.random()) * t + r.random() * 6))  # intonation
        saw = (n.cumsum(f) / SR + r.random()) % 1 * 2 - 1
        syl = (0.5 + 0.5 * n.sin(2 * n.pi * (3.2 + r.random() * 2.6) * t + r.random() * 6)) ** 2
        voiced += saw * syl * _phrases(L, r) * (0.25 + 0.75 * r.random() ** 2)
    voiced = bandpass(bandpass(voiced, 300, 1800), 300, 1800)  # twice — steeper edges: the voices are muffled, distant
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
    """A summer square: sparrows (short chirps in series), an occasional trill, leaves rustling in the wind."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    out = n.zeros(L)
    for b in range(4):  # sparrows on different branches: each its own pitch and loudness
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
    while t < dur - 3:  # a trill: fast notes up and down
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
    """A strike of a tram bell: inharmonic overtones, the ring fades."""
    n = np()
    t = n.arange(int(d * SR)) / SR
    y = sum(a * n.sin(2 * n.pi * f * k * t) * n.exp(-t * (3.5 + 3 * k)) for k, a in ((1, 1), (2.4, 0.5), (3.9, 0.3), (5.6, 0.15)))
    return y * n.minimum(1, t * 3000)


def tram(dur: float, seed: int = 17):
    """A street with a tram: a passing car (a rising and receding rumble, wheels knocking on rail joints, a squeal),
    the bell "ding-ding"; between cars — only the city."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    tt = n.arange(L) / SR
    out = n.zeros(L)
    rumble = lowpass(r.standard_normal(L), 140) + bandpass(r.standard_normal(L), 300, 900) * 0.25
    env = n.zeros(L)
    t = 2 + r.random() * 8
    while t < dur:
        T = 10 + r.random() * 6  # a car passes
        a, b = int(t * SR), min(L, int((t + T) * SR))
        if b > a:
            x = n.arange(b - a) / SR
            env[a:b] = n.maximum(env[a:b], n.sin(n.pi * x / T) ** 2)
            for c in n.arange(1.0, T - 1, 0.95 + r.random() * 0.2):  # rail joints: "ta-tak" — two wheelsets
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
    """Keys [[share, value], …] → values at points x (linear, the edges — by the outermost keys)."""
    n = np()
    if not keys:
        return n.full_like(x, default)
    ks = sorted(keys)
    return n.interp(x, [k[0] for k in ks], [k[1] for k in ks])


def motor(dur: float, pitch=None, env=None, seed: int = 18):
    """A 1910s aeroplane: a rotary engine — a "drilling" rattle (cylinder firings ~45 Hz with misfires),
    the exhaust's rumble and the propeller's whistle. pitch, env — keys [[share, factor]], [[share, dB]]: Doppler on a fly-by,
    a howl in a dive, a cut-out."""
    n = np()
    r = rng(seed)
    L = int(dur * SR)
    u = n.arange(L) / max(1, L - 1)
    p = _keys(pitch, u, 1.0)
    cyc = n.cumsum(45 * p) / SR                                   # cylinder firings
    idx = cyc.astype(int)
    jitter = 0.55 + 0.45 * r.random(idx[-1] + 2)                  # uneven running, misfires
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
    """Ambience: one name or a mix "birds+crowd*0.5" (the factor is the term's loudness)."""
    out = None
    for part in kind.split('+'):
        name, _, k = part.strip().partition('*')
        x = BEDS.get(name, room)(dur, seed=seed) * float(k or 1)
        out = x if out is None else out + x
    return out


def sfx(name: str, dur: float, seed: int = 5):
    n = np()
    r = rng(seed)
    if name == 'click':  # a light switch: a click + a short metallic ring
        L = int(0.12 * SR)
        t = n.arange(L) / SR
        return (r.standard_normal(L) * n.exp(-t * 400) + n.sin(2 * n.pi * 1900 * t) * n.exp(-t * 90) * 0.5) * 0.8
    if name == 'hum':  # electric light: 50 Hz with harmonics, a slight flutter
        t = n.arange(int(dur * SR)) / SR
        y = sum(a * n.sin(2 * n.pi * 50 * k * t) for k, a in ((1, 0.5), (2, 0.35), (3, 0.2), (4, 0.12), (6, 0.06)))
        return y * (0.9 + 0.1 * n.sin(2 * n.pi * 0.7 * t)) * n.minimum(1, t / 0.08) * 0.12
    if name == 'breath':  # the room sighs: noise through a low-pass, in and out
        t = n.arange(int(min(dur, 4.5) * SR)) / SR
        env = n.sin(n.pi * n.clip(t / 2.2, 0, 1)) ** 2 * 0.8 + n.sin(n.pi * n.clip((t - 2.2) / 2.3, 0, 1)) ** 2
        return lowpass(r.standard_normal(len(t)), 900) * env * 0.5
    if name == 'thump':
        L = int(0.4 * SR)
        t = n.arange(L) / SR
        return (n.sin(2 * n.pi * 70 * t) * n.exp(-t * 18) + lowpass(r.standard_normal(L), 400) * n.exp(-t * 30) * 0.6) * 0.9
    if name == 'rustle':  # paper: short bands of noise
        L = int(0.5 * SR)
        t = n.arange(L) / SR
        g = (r.random(L) < 0.02).astype(float)
        return lowpass(r.standard_normal(L) * (0.3 + g * 3), 3500) * n.exp(-t * 6) * 0.35
    if name == 'bell':  # an electric door bell: a hammer on a gong ~22 times a second, ~1.3 s
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
    if name == 'boom':  # a distant muffled explosion: a thud, a low roll, a fading rumble
        t = n.arange(int(min(dur, 5) * SR)) / SR
        crack = lowpass(r.standard_normal(len(t)), 900) * n.exp(-t * 25)
        roll = lowpass(r.standard_normal(len(t)), 110) * n.minimum(1, t / 0.03) * n.exp(-t * 0.9) * (1 + 0.3 * n.sin(2 * n.pi * 3 * t))
        return (crack * 0.5 + roll * 3.5) * 0.6
    if name == 'tram-bell':  # a tram bell "ding-ding"
        y = n.zeros(int(1.9 * SR))
        for k in range(2):
            _place(y, _bell(1660), k * 0.28)
        return y * 0.4
    raise KeyError(f'no sound effect {name}')


def melody(notes: str, bpm: float, *, rit: float = 0.0, seed: int = 7):
    """A melody "A4:1 D5:2 -:1 …" — note:beats (- — a rest). rit — slowing towards the end (the music box winding down)."""
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


# ---------------------------------------------------------------- fingerprint

MUSIC = {'organ': 'organ', 'piano': 'piano', 'drone': 'drone', 'motor': 'motor'}  # everything else (without a file) — melody (the music box)


def signature(sb: dict, tl: dict) -> str:
    """The code a production's sound depends on: the mix + the generators of its ambience, music and effects (with dependencies).
    The site's sound fingerprint is taken from it, not from the whole file: a new ambience or effect for one production doesn't
    recompute the others' sound."""
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
        skip = per_kind if key in ('build', 'bed') else {'sfx'}  # dispatchers call every generator — take only the needed ones
        for dep in sorted(set(re.findall(r'\b([A-Za-z_]\w*)\(', src))):  # calls (the local variable motor is not a function)
            if dep in funcs and dep not in skip:
                add(dep)
    add('build')
    snd = sb.get('sound') or {}
    kinds = set((snd.get('beds') or {}).values()) | {sh['bed'] for sc in sb.get('scenes') or [] for sh in sc.get('shots') or [] if sh.get('bed')}
    for kind in sorted(k for k in kinds if k):
        add('bed')
        add('room')  # bed()'s fallback ambience — not called by name in the code
        for part in kind.split('+'):
            name = part.strip().partition('*')[0]
            add(BEDS.get(name, room).__name__)
    for cue in snd.get('music') or []:
        if not cue.get('file'):
            add(MUSIC.get(cue.get('kind'), 'melody'))
    names = sorted({e['name'] for s in tl.get('shots') or [] for e in s.get('sfx') or []})
    if names:  # effects are one function with branches: take its head and the branches of the needed effects
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


# ---------------------------------------------------------------- the mix

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

    for p in tl['paragraphs']:  # the voice: takes in their places
        if p.get('take'):
            x, at, shift = _load(config.text_dir(slug) / p['take']), 0, 0.0
            for cut, hold in p.get('cuts') or []:   # pauses inside a paragraph: the take is cut between sentences
                i = int(round(cut * SR))
                _place(voice, x[at:i], p['t0'] + shift + at / SR)
                at, shift = i, shift + hold
            _place(voice, x[at:], p['t0'] + shift + at / SR)
    peak = n.abs(voice).max() or 1
    voice *= db(-3) / peak

    shots = tl['shots']
    by_id = {s['id']: s for s in shots}
    # set ambience: continuous while the set is on screen; a join — a short crossfade
    beds = snd.get('beds') or {}
    own = {sh['id']: sh['bed'] for sc in sb.get('scenes') or [] for sh in sc.get('shots') or [] if 'bed' in sh}  # the shot's ambience
    kind_of = lambda s: own.get(s['id'], beds.get(s['set']))  # noqa: E731
    k = 0
    while k < len(shots):  # consecutive shots with the same ambience — one continuous piece
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
            if cue.get('loop'):  # the pianist plays while the span lasts: the phrase repeats
                x = n.tile(x[: int(len(x) - 3 * SR)], int((t1 - t0) // max(1, len(x) / SR - 3)) + 1)
            x = x[: int((t1 - t0) * SR)]
        elif cue.get('kind') == 'motor':  # keys — a share of the span or "shot+share": Doppler, a dive, a cut-out on impact
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

    for s in shots:  # effects in shots: at — a share of the shot, before_end — seconds before the shot's end
        for e in s.get('sfx') or []:
            t0 = s['t1'] - float(e['before_end']) if 'before_end' in e else s['t0'] + (s['t1'] - s['t0']) * float(e.get('at', 0))
            if e.get('stop_all'):  # silence afterwards (except the effect itself)
                i = int(t0 * SR)
                for buf in (bed_, music, fx):
                    buf[i:] *= 0
            length = (s['t1'] - t0) if e.get('to_end') else (dur - t0)
            _place(fx, sfx(e['name'], max(0.2, length), seed=sum(map(ord, s['id']))), t0, db(e.get('gain', -12)))

    # music and ambience duck under the voice
    win = int(0.25 * SR)
    env = n.sqrt(n.maximum(smooth(voice ** 2, win), 0))
    duck = 1 - 0.55 * n.clip(env / 0.05, 0, 1)
    duck = smooth(duck, win)
    bd = float(snd.get('bed_duck', 0.4))  # how much the ambience ducks under the voice (0 — not at all)
    mix = voice + (music * duck) + bed_ * db(snd.get('bed_gain', -8)) * (1 - bd + bd * duck) + fx
    mix = mix[: int(dur * SR)]
    fo = int(float(tl.get('fade_out') or 0) * SR)  # the fade at the end of the film (together with the picture)
    if fo:
        mix[-fo:] *= n.cos(n.linspace(0, n.pi / 2, fo)) ** 2
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.raw.wav')
    pcm = (n.clip(mix / max(1.0, n.abs(mix).max()), -1, 1) * 32767).astype(n.int16)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', str(tmp)],
                   input=pcm.tobytes(), check=True)
    # loudness −16 LUFS with one overall gain (measure → volume → peak limiter): single-pass loudnorm
    # is dynamic — it pulled the quiet parts (rain in pauses, the opening, the finale) almost up to the voice
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(tmp), '-af', 'loudnorm=I=-16:TP=-1.5:print_format=json',
                        '-f', 'null', '-'], capture_output=True, text=True, check=True)
    measured = float(json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])['input_i'])
    gain = -16.0 - measured if measured > -70 else 0.0
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(tmp), '-af', f'volume={gain:.2f}dB,alimiter=limit=0.84:level=false',
                    '-ar', str(SR), '-ac', '2', str(out)], check=True)
    tmp.unlink()
    log(f'✓ sound → {out.relative_to(config.ROOT)} ({dur:.1f} s)')
    return out
