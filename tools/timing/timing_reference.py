"""Offline ideal event timing reference; Python stdlib only, no GPU claims.

Input is natural-log relative intensity. Times are run-relative seconds (binary64).
The continuous oracle uses known monotone intervals, not sampled-image interpolation.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import csv
import math
from pathlib import Path
from typing import Callable, Iterable


LOG_TOL = 1e-12  # Numeric endpoint allowance, NOT the shader's +1e-5 count bias.


@dataclass(frozen=True)
class Event:
    t: float
    p: int
    x: int = 0
    y: int = 0

    def __post_init__(self):
        if not math.isfinite(self.t) or self.t < 0:
            raise ValueError("event time must be finite, run-relative and nonnegative")
        if self.p not in (-1, 1) or type(self.p) is not int:
            raise ValueError("polarity must be integer -1 or +1")
        if any(type(v) is not int or v < 0 for v in (self.x, self.y)):
            raise ValueError("pixel coordinates must be nonnegative integers")


def thresholds(on: float, off: float) -> None:
    if any(not math.isfinite(v) or v <= LOG_TOL for v in (on, off)):
        raise ValueError("thresholds must be finite and greater than numeric tolerance")


class SampledPixel:
    """Persistent ideal pixel driven by log samples, linear between each pair.

    feed() returns all crossings; a reset initializes the reference without events.
    Display batching has no role. Not a bit-exact emulation of FP32 Godot code.
    """

    def __init__(self, on: float = 0.2, off: float = 0.2):
        thresholds(on, off)
        self.on, self.off = on, off
        self.time = self.value = self.reference = None

    def feed(self, t: float, log_i: float, *, reset: bool = False) -> list[Event]:
        if not math.isfinite(t) or t < 0 or not math.isfinite(log_i):
            raise ValueError("samples need finite nonnegative time and finite log intensity")
        if log_i + self.on == log_i or log_i - self.off == log_i:
            raise ValueError("threshold is below floating-point resolution at this log intensity")
        if self.time is not None and t <= self.time:
            raise ValueError("sample timestamps must strictly increase, including resets")
        if reset or self.time is None:
            self.time, self.value, self.reference = t, log_i, log_i
            return []
        difference = log_i - self.reference
        p = 1 if difference >= 0 else -1
        threshold = self.on if p == 1 else self.off
        n = math.floor((abs(difference) + LOG_TOL) / threshold)
        events = []
        for k in range(1, n + 1):
            level = self.reference + p * k * threshold
            fraction = (level - self.value) / (log_i - self.value)
            t_event = self.time + min(1.0, max(0.0, fraction)) * (t - self.time)
            events.append(Event(t_event, p))
        self.reference += p * n * threshold
        self.time, self.value = t, log_i
        return events


class PiecewiseLogSignal:
    """Continuous piecewise-linear log intensity, including finite-rise pulses."""

    def __init__(self, knots: Iterable[tuple[float, float]]):
        self.knots = list(knots)
        if len(self.knots) < 2:
            raise ValueError("at least two knots required")
        self.times = [t for t, _ in self.knots]
        if self.times[0] != 0 or any(not math.isfinite(v) for k in self.knots for v in k):
            raise ValueError("finite knots must start at run-relative zero")
        if any(b <= a for a, b in zip(self.times, self.times[1:])):
            raise ValueError("knot times must strictly increase")
        self.duration = self.times[-1]
        self.slope_bound = max(abs((v1 - v0) / (t1 - t0))
                               for (t0, v0), (t1, v1) in zip(self.knots, self.knots[1:]))

    def __call__(self, t: float) -> float:
        if not 0 <= t <= self.duration:
            raise ValueError("time outside signal")
        i = min(bisect_right(self.times, t) - 1, len(self.knots) - 2)
        (a, va), (b, vb) = self.knots[i:i + 2]
        return va + (vb - va) * (t - a) / (b - a)

    def monotone_times(self) -> list[float]:
        return self.times[:]


class SineLogSignal:
    def __init__(self, duration: float, frequency: float, amplitude: float = 0.7,
                 phase: float = 0):
        if any(not math.isfinite(v) for v in (duration, frequency, amplitude, phase)):
            raise ValueError("sine parameters must be finite")
        if duration <= 0 or frequency <= 0 or amplitude <= 0:
            raise ValueError("duration, frequency and amplitude must be positive")
        self.duration, self.frequency, self.amplitude, self.phase = duration, frequency, amplitude, phase
        self.slope_bound = amplitude * math.tau * frequency

    def __call__(self, t: float) -> float:
        if not 0 <= t <= self.duration:
            raise ValueError("time outside signal")
        return self.amplitude * math.sin(math.tau * self.frequency * t + self.phase)

    def monotone_times(self) -> list[float]:
        # cos(omega*t+phase)=0; exact extrema partition for the continuous oracle.
        first = math.floor((self.phase - math.pi / 2) / math.pi) - 1
        last = math.ceil((math.tau * self.frequency * self.duration + self.phase - math.pi / 2) / math.pi) + 1
        inner = [(math.pi / 2 + k * math.pi - self.phase) / (math.tau * self.frequency)
                 for k in range(first, last + 1)]
        return [0.0] + [t for t in inner if 0 < t < self.duration] + [self.duration]


def continuous_events(signal, on: float = 0.2, off: float = 0.2) -> list[Event]:
    """Invert each next threshold on known monotone segments (60 bisections).

    This oracle knows the analytic trajectory/extrema; a real sampler does not.
    Reference updates at events and retains residuals through reversals.
    Each segment owns (start,end]; a turning-point event is counted once.
    """
    thresholds(on, off)
    reference = signal(0.0)
    events = []
    times = signal.monotone_times()
    for start, end in zip(times, times[1:]):
        va, vb = signal(start), signal(end)
        if abs(vb - va) <= LOG_TOL:
            continue
        p = 1 if vb > va else -1
        while True:
            level = reference + (on if p == 1 else -off)
            if not math.isfinite(level) or level == reference:
                raise ValueError("threshold cannot advance the floating-point reference")
            if p * (vb - level) < -LOG_TOL:
                break
            if abs(vb - level) <= LOG_TOL:
                # At a tangent extremum, floating-point sin can equal its peak
                # over a tiny interval. Honor the known endpoint exactly rather
                # than invert that numerically flat neighborhood.
                events.append(Event(end, p))
                reference = level
                continue
            lo, hi = start, end
            for _ in range(60):
                mid = (lo + hi) / 2
                if p * (signal(mid) - level) < 0:
                    lo = mid
                else:
                    hi = mid
            events.append(Event((lo + hi) / 2, p))
            reference = level
    return events


def uniform_times(duration: float, hz: float) -> list[float]:
    if not all(math.isfinite(v) and v > 0 for v in (duration, hz)):
        raise ValueError("duration and sample rate must be positive and finite")
    times = [i / hz for i in range(math.ceil(duration * hz))]
    return times + [duration]


def sampled_events(signal: Callable, times: Iterable[float], on: float = 0.2,
                   off: float = 0.2) -> list[Event]:
    pixel = SampledPixel(on, off)
    return [e for t in times for e in pixel.feed(t, signal(t))]


def percentile(values: list[float], q: float):
    """Nearest-rank percentile; None means no matched observations."""
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)]


def compare(reference: list[Event], observed: list[Event], tolerance_s: float) -> dict:
    """Chronological one-to-one matching per pixel/polarity within a fixed gate.

    Earliest-compatible ordered matching maximizes cardinality for this gate;
    it does not minimize timing error over alternative assignments.
    """
    if not math.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError("matching gate must be finite and nonnegative")
    keys = {(e.x, e.y, e.p) for e in reference + observed}
    errors, signed_errors = [], []
    missing = extra = 0
    for x, y, p in keys:
        a = sorted(e.t for e in reference if (e.x, e.y, e.p) == (x, y, p))
        b = sorted(e.t for e in observed if (e.x, e.y, e.p) == (x, y, p))
        i = j = 0
        while i < len(a) and j < len(b):
            error = b[j] - a[i]
            if abs(error) <= tolerance_s:
                signed_errors.append(error)
                errors.append(abs(error))
                i, j = i + 1, j + 1
            elif error < 0:
                extra, j = extra + 1, j + 1
            else:
                missing, i = missing + 1, i + 1
        missing += len(a) - i
        extra += len(b) - j
    return {
        "reference_events": len(reference), "observed_events": len(observed),
        "reference_on": sum(e.p == 1 for e in reference),
        "observed_on": sum(e.p == 1 for e in observed),
        "matched": len(errors), "missing": missing, "extra": extra,
        "abs_error_median_s": percentile(errors, 0.5),
        "abs_error_p95_s": percentile(errors, 0.95),
        "abs_error_max_s": max(errors) if errors else None,
        "signed_error_mean_s": sum(signed_errors) / len(signed_errors) if signed_errors else None,
    }


FIELDS = ["x", "y", "t_ns", "p", "sequence"]


def write_events(path: Path, events: Iterable[Event], *, capacity: int,
                 epoch_ns: int = 0) -> dict:
    """Bounded CSV capture of an already chronologically ordered event iterable.

    Consume ALL candidates, drop newest beyond capacity, count every overflow.
    No sensor state is reset/delayed by capture loss. Upstream generation memory
    is not bounded by this sink. Caller owns deterministic ordering for ties.
    """
    if type(capacity) is not int or capacity < 0 or type(epoch_ns) is not int or epoch_ns < 0:
        raise ValueError("capacity and epoch_ns must be nonnegative integers")
    total = 0
    previous = -1.0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for e in events:
            if e.t < previous:
                raise ValueError("event input must be chronological")
            previous = e.t
            if total < capacity:
                writer.writerow([e.x, e.y, epoch_ns + round(e.t * 1e9), e.p, total])
            total += 1
    return {"schema": "event-lab-timing-csv-v1", "time_unit": "ns",
            "epoch_ns": epoch_ns, "candidate_events": total,
            "stored_events": min(total, capacity), "overflow_events": max(0, total - capacity),
            "capacity": capacity, "complete": total <= capacity,
            "overflow_policy": "drop-newest; generation continues", "rounding": "nearest ties-to-even"}


def read_events(path: Path, *, epoch_ns: int = 0) -> list[Event]:
    """Read the v1 CSV; subtract integer epoch BEFORE float conversion."""
    if type(epoch_ns) is not int or epoch_ns < 0:
        raise ValueError("epoch_ns must be a nonnegative integer")
    events = []
    previous_ns = -1
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("unknown event CSV fields")
        for index, row in enumerate(reader):
            if None in row or any(v is None for v in row.values()):
                raise ValueError("malformed event row")
            x, y, t_ns, p, sequence = (int(row[k]) for k in FIELDS)
            if sequence != index or t_ns < previous_ns or t_ns < epoch_ns:
                raise ValueError("invalid ordering, sequence or time epoch")
            events.append(Event((t_ns - epoch_ns) / 1e9, p, x, y))
            previous_ns = t_ns
    return events
