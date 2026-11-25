"""Confidence-aware temporal smoothing for landmark tracks (spec section 12).

Three filters are implemented so they can be compared on the same signals
(`tests/test_smoothing.py`): exponential moving average, One-Euro, and Savitzky-Golay.
The pipeline uses One-Euro: it removes jitter when a joint is nearly still and follows fast
choreography with little lag because its cutoff rises with speed.

All filters work on a 1-D series `values` with a boolean `reliable` mask; unreliable samples
are left as NaN and restart the filter (never smoothed through). Gap filling is separate
(`fill_short_gaps`) and always marks what it invented.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


def _runs(mask: BoolArray) -> list[tuple[int, int]]:
    """[start, end) index ranges where mask is True."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, m in enumerate(mask.tolist()):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def ema(values: FloatArray, reliable: BoolArray, alpha: float = 0.5) -> FloatArray:
    out = np.full_like(values, np.nan)
    for s, e in _runs(reliable):
        acc = values[s]
        for i in range(s, e):
            acc = alpha * values[i] + (1 - alpha) * acc
            out[i] = acc
    return out


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


def one_euro(
    values: FloatArray,
    times: FloatArray,
    reliable: BoolArray,
    *,
    min_cutoff: float = 1.7,
    beta: float = 0.3,
    d_cutoff: float = 1.0,
) -> FloatArray:
    """One-Euro filter (Casiez et al. 2012). `times` in seconds, strictly increasing."""
    out = np.full_like(values, np.nan)
    for s, e in _runs(reliable):
        x_prev = float(values[s])
        dx_prev = 0.0
        out[s] = x_prev
        for i in range(s + 1, e):
            dt = max(float(times[i] - times[i - 1]), 1e-6)
            dx = (float(values[i]) - x_prev) / dt
            a_d = _alpha(d_cutoff, dt)
            dx_hat = a_d * dx + (1 - a_d) * dx_prev
            cutoff = min_cutoff + beta * abs(dx_hat)
            a = _alpha(cutoff, dt)
            x_hat = a * float(values[i]) + (1 - a) * x_prev
            out[i] = x_hat
            x_prev, dx_prev = x_hat, dx_hat
    return out


def savitzky_golay(
    values: FloatArray, reliable: BoolArray, window: int = 5, order: int = 2
) -> FloatArray:
    """Centered polynomial smoothing inside each reliable run (runs shorter than the window
    are passed through unchanged)."""
    from scipy.signal import savgol_filter

    out = np.full_like(values, np.nan)
    for s, e in _runs(reliable):
        seg = values[s:e]
        if e - s >= window:
            out[s:e] = savgol_filter(seg, window, order, mode="interp")
        else:
            out[s:e] = seg
    return out


def fill_short_gaps(
    values: FloatArray, reliable: BoolArray, max_gap: int
) -> tuple[FloatArray, BoolArray]:
    """Linearly bridge gaps of at most `max_gap` samples that have reliable samples on both
    sides. Returns (values, interpolated_mask). Longer gaps stay NaN: never invent long spans."""
    out = values.copy()
    out[~reliable] = np.nan
    interp = np.zeros(len(values), dtype=bool)
    runs = _runs(~reliable)
    for s, e in runs:
        if s == 0 or e == len(values) or (e - s) > max_gap:
            continue
        a, b = out[s - 1], out[e]
        for k, i in enumerate(range(s, e), start=1):
            t = k / (e - s + 1)
            out[i] = a + (b - a) * t
            interp[i] = True
    return out, interp
