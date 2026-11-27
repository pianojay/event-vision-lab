"""Generic, uncalibrated background activity composed with the held-input oracle."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, replace
import math
import random

from reference_sensor import ReferenceSensor, SensorProfile


@dataclass(frozen=True)
class ActivityProfile:
    leak_log_per_s: float = 0.0
    temporal_on_hz: float = 0.0
    temporal_off_hz: float = 0.0
    seed: int = 1

    def __post_init__(self):
        for name in ("leak_log_per_s", "temporal_on_hz", "temporal_off_hz"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if type(self.seed) is not int:
            raise ValueError("activity seed must be an integer")


@dataclass(frozen=True)
class Candidate:
    x: int
    y: int
    t_s: float
    p: int
    origin: str
    emitted: bool


@dataclass(frozen=True)
class ActivityStep:
    candidates: tuple[Candidate, ...]

    @property
    def events(self):
        return tuple(event for event in self.candidates if event.emitted)


class GenericSensor:
    """Optical crossings + periodic ON leak + independent Poisson ON/OFF activity.

    Synthetic activity is added at the comparator-candidate boundary. It does
    not modify the optical contrast reference or add analog/threshold noise.
    All origins share one refractory gate. This is a phenomenological model.
    """

    def __init__(self, width, height, pixel=SensorProfile(), activity=ActivityProfile(),
                 max_candidates_per_step=1_000_000):
        self.pixel = pixel
        self.activity = activity
        self.optical = ReferenceSensor(width, height, replace(pixel, refractory_s=0.0),
                                       max_candidates_per_step)
        self.width, self.height = width, height
        self.limit = max_candidates_per_step
        self.time_s = None

    def reset(self, time_s, intensities):
        self.optical.reset(time_s, intensities)
        self.time_s = self.start_s = time_s
        self.last_emitted = [-math.inf] * (self.width * self.height)
        self.leak_indices = [1] * len(self.last_emitted)
        self.generators, self.next_noise = [], []
        # Independent per-pixel/polarity streams keep unrelated mechanisms stable.
        for index in range(len(self.last_emitted)):
            generators, arrivals = [], []
            for polarity, rate in enumerate((self.activity.temporal_on_hz,
                                             self.activity.temporal_off_hz)):
                rng = random.Random(f"event-lab-poisson-v1:{self.activity.seed}:{index}:{polarity}")
                generators.append(rng)
                arrivals.append(time_s + rng.expovariate(rate) if rate else math.inf)
            self.generators.append(generators)
            self.next_noise.append(arrivals)
        self.counters = {name: 0 for name in (
            "optical_candidates", "leak_candidates", "temporal_candidates",
            "sensor_candidates", "pixel_emitted", "refractory_suppressed")}

    def advance(self, time_s, intensities):
        # A resource limit aborts the complete interval, including RNG state.
        trial = copy.deepcopy(self)
        step = trial._advance(time_s, intensities)
        self.__dict__.update(trial.__dict__)
        return step

    def _advance(self, time_s, intensities):
        optical = self.optical.advance(time_s, intensities)
        candidates = [(e.t_s, e.y, e.x, e.p, "optical") for e in optical.candidates]
        for index, thresholds in enumerate(self.optical.thresholds):
            y, x = divmod(index, self.width)
            if self.activity.leak_log_per_s:
                period = thresholds[0] / self.activity.leak_log_per_s
                while True:
                    arrival = self.start_s + self.leak_indices[index] * period
                    if arrival > time_s:
                        break
                    candidates.append((arrival, y, x, 1, "leak"))
                    self.leak_indices[index] += 1
                    if len(candidates) > self.limit:
                        raise OverflowError("candidate capacity exceeded; interval not committed")
            for k, rate in enumerate((self.activity.temporal_on_hz, self.activity.temporal_off_hz)):
                if not rate:
                    continue
                while self.next_noise[index][k] <= time_s:
                    arrival = self.next_noise[index][k]
                    candidates.append((arrival, y, x, 1 if k == 0 else -1, "temporal"))
                    following = arrival + self.generators[index][k].expovariate(rate)
                    if following <= arrival:
                        raise ValueError("noise interval is below timestamp precision")
                    self.next_noise[index][k] = following
                    if len(candidates) > self.limit:
                        raise OverflowError("candidate capacity exceeded; interval not committed")
        # Explicit tie order. Origins are diagnostic labels, not causality claims.
        origin_order = {"optical": 0, "leak": 1, "temporal": 2}
        candidates.sort(key=lambda e: (*e[:4], origin_order[e[4]]))
        result = []
        for time, y, x, polarity, origin in candidates:
            index = y * self.width + x
            emitted = time - self.last_emitted[index] >= self.pixel.refractory_s
            if emitted:
                self.last_emitted[index] = time
            self.counters[f"{origin}_candidates"] += 1
            self.counters["sensor_candidates"] += 1
            self.counters["pixel_emitted" if emitted else "refractory_suppressed"] += 1
            result.append(Candidate(x, y, time, polarity, origin, emitted))
        self.time_s = time_s
        return ActivityStep(tuple(result))

    def effective(self):
        return {
            "model": "generic-composed-held-v1", "calibration": "none",
            "width": self.width, "height": self.height,
            "pixel": asdict(self.pixel), "activity": asdict(self.activity),
            "max_candidates_per_step": self.limit,
            "trajectory": "left-sample held, exact RC optical crossings",
            "leak": "periodic ON candidates; period=C_on/leak_log_per_s; phase zero at reset",
            "temporal": "independent per-pixel/polarity homogeneous Poisson candidates",
            "noise_insertion": "candidate boundary; no analog or threshold-noise addition",
            "refractory": "shared event gate; optical reference consumes suppressed crossings",
            "synthetic_reference_effect": "none",
            "reset": "retain threshold map; restart activity seeds/phase and gate",
            "ordering": "time,y,x,p,origin(optical,leak,temporal); stable ties",
        }
