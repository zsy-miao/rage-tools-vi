#!/usr/bin/env python3
"""Spectral success-case test: harmonic speech/control vs noise candidate."""
import math
import sys
import wave
from pathlib import Path

import numpy as np


def read_wav(path, seconds=15):
    with wave.open(str(path), 'rb') as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(int(rate * seconds))
    if width == 2:
        x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    else:
        raise ValueError(f'unsupported width {width}')
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    return x, rate


def metrics(x, rate):
    if len(x) < 1024:
        raise ValueError('too short')
    x = x[: rate * 2]
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2 + 1e-20
    f = np.fft.rfftfreq(len(x), 1 / rate)
    band = (f >= 20) & (f <= 20000)
    p = p[band]
    flat = float(np.exp(np.mean(np.log(p))) / np.mean(p))
    share = float(np.max(p) / np.sum(p))
    peak = float(np.max(p) / (np.median(p) + 1e-20))
    ac = np.correlate(x, x, 'full')[len(x)-1:]
    ac = ac / (ac[0] + 1e-20)
    harmonic = float(np.max(ac[rate // 2000: rate // 50])) if len(ac) > rate // 50 else 0.0
    return {'flatness': flat, 'max_bin_share': share, 'peak_over_median': peak, 'harmonic': harmonic}


def synthetic_control(rate=48000, seconds=2):
    t = np.arange(rate * seconds) / rate
    return 0.5 * np.sin(2 * math.pi * 220 * t) + 0.25 * np.sin(2 * math.pi * 440 * t) + 0.1 * np.sin(2 * math.pi * 660 * t)


def main():
    rate = 48000
    actual_paths = [
        Path('output/marshall-15s.wav'),
        Path('output/audio-tests/bink/large-binkaudio_dct-ch1-0s.wav'),
    ]
    # synthetic controls
    speech = synthetic_control(rate)
    noise = np.random.default_rng(1).normal(0, 0.2, rate * 2).astype(np.float32)
    sm = metrics(speech, rate)
    nm = metrics(noise, rate)
    print('synthetic harmonic', sm)
    print('synthetic noise   ', nm)
    assert sm['flatness'] < 0.2, sm
    assert nm['flatness'] > 0.4, nm
    assert sm['harmonic'] > nm['harmonic'], (sm, nm)

    if actual_paths[0].is_file():
        x, r = read_wav(actual_paths[0])
        mm = metrics(x, r)
        print('real speech control', mm)
        assert mm['flatness'] < nm['flatness'], mm
        assert mm['harmonic'] > 0.05, mm
    if actual_paths[1].is_file():
        x, r = read_wav(actual_paths[1])
        bm = metrics(x, r)
        print('bink candidate    ', bm)
        assert bm['flatness'] > 0.4, bm
        assert bm['flatness'] > sm['flatness'], bm
    print('PASS: harmonic control is tonal; noise/candidate is broadband')


if __name__ == '__main__':
    main()
