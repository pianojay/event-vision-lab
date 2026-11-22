"""Small CPU sensor oracle for explicitly piecewise-constant optical input.

Independent of the Godot runtime and the eventual shared event-buffer API.
See docs/research/sensor/README.md for semantics and calibration limits.
"""

from dataclasses import dataclass
import math
import random
from typing import Sequence


@dataclass(frozen=True)
class SensorProfile:
    on_threshold: float = 0.2
    off_threshold: float = 0.2
    threshold_sigma: float = 0.0
    minimum_threshold: float = 0.01
    bandwidth_white_hz: float = 0.0  # zero disables photoreceptor filtering
    white_intensity: float = 1.0
    minimum_bandwidth_fraction: float = 0.1
    dark_offset: float = 0.0  # relative intensity units, not calibrated current
    refractory_s: float = 0.0
    seed: int = 1

    def __post_init__(self) -> None:
        for name in (
            "on_threshold", "off_threshold", "threshold_sigma", "minimum_threshold",
            "bandwidth_white_hz", "white_intensity", "minimum_bandwidth_fraction",
            "dark_offset", "refractory_s",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.minimum_threshold <= 0 or self.white_intensity <= 0:
            raise ValueError("minimum_threshold and white_intensity must be positive")
        if min(self.on_threshold, self.off_threshold) < self.minimum_threshold:
            raise ValueError("nominal thresholds must be at least minimum_threshold")
        if not 0 < self.minimum_bandwidth_fraction <= 1:
            raise ValueError("minimum_bandwidth_fraction must be in (0, 1]")
        if not isinstance(self.seed, int):
            raise ValueError("seed must be an integer (including reproducible seed zero)")

    def time_constant(self, intensity: float) -> float:
        """Generic brightness-dependent RC time constant; no camera calibration."""
        if self.bandwidth_white_hz == 0:
            return 0.0
        fraction = min(intensity / self.white_intensity, 1.0)
        gain = self.minimum_bandwidth_fraction + (1 - self.minimum_bandwidth_fraction) * fraction
        tau = (1.0 / (2 * math.pi)) / self.bandwidth_white_hz / gain
        if not math.isfinite(tau) or tau <= 0:
            raise ValueError("bandwidth produces an unrepresentable time constant")
        return tau


@dataclass(frozen=True)
class PixelState:
    reference_log: float
    filtered_log: float
    last_emitted_s: float = -math.inf


@dataclass(frozen=True)
class Crossing:
    x: int
    y: int
    t_s: float
    p: int
    emitted: bool


@dataclass(frozen=True)
class StepResult:
    candidates: tuple[Crossing, ...]

    @property
    def events(self) -> tuple[Crossing, ...]:
        return tuple(event for event in self.candidates if event.emitted)

    @property
    def refractory_suppressed(self) -> int:
        return sum(not event.emitted for event in self.candidates)


class ReferenceSensor:
    """Stateful generic pixel model, intended for small validation fixtures.

    reset(t0, I0) initializes without events. advance(t1, I) means I is held
    constant over [t0,t1), with a possible jump at t0. A filtering-free jump
    produces simultaneous candidates at t0. Filtered crossings solve the RC
    response analytically; there is no interpolation between optical endpoints.
    """

    def __init__(self, width: int, height: int, profile: SensorProfile = SensorProfile(),
                 max_candidates_per_step: int = 1_000_000) -> None:
        for name, value in (("width", width), ("height", height),
                            ("max_candidates_per_step", max_candidates_per_step)):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.width = width
        self.height = height
        self.profile = profile
        self.max_candidates_per_step = max_candidates_per_step
        rng = random.Random(profile.seed)
        self.thresholds = tuple(
            (max(profile.minimum_threshold, rng.gauss(profile.on_threshold, profile.threshold_sigma)),
             max(profile.minimum_threshold, rng.gauss(profile.off_threshold, profile.threshold_sigma)))
            for _ in range(width * height)
        )
        if any(not math.isfinite(value) for pair in self.thresholds for value in pair):
            raise ValueError("threshold distribution produced a nonfinite threshold")
        self.states: tuple[PixelState, ...] = ()
        self.time_s: float | None = None
        self.candidate_total = 0
        self.emitted_total = 0
        self.refractory_suppressed_total = 0

    def _input(self, intensities: Sequence[float]) -> tuple[float, ...]:
        if len(intensities) != self.width * self.height:
            raise ValueError("input must contain width*height row-major intensities")
        result = []
        for intensity in intensities:
            if not math.isfinite(intensity) or intensity < 0:
                raise ValueError("optical intensities must be finite and nonnegative")
            effective = intensity + self.profile.dark_offset
            if not math.isfinite(effective) or effective <= 0:
                raise ValueError("intensity + dark_offset must be finite and positive")
            result.append(effective)
        return tuple(result)

    def reset(self, time_s: float, intensities: Sequence[float]) -> None:
        if not math.isfinite(time_s) or time_s < 0:
            raise ValueError("reset time must be finite and nonnegative")
        values = self._input(intensities)
        self.states = tuple(PixelState(math.log(value), math.log(value)) for value in values)
        self.time_s = time_s
        self.candidate_total = self.emitted_total = self.refractory_suppressed_total = 0

    def advance(self, time_s: float, intensities: Sequence[float]) -> StepResult:
        if self.time_s is None:
            raise ValueError("reset must initialize the sensor first")
        if not math.isfinite(time_s) or time_s <= self.time_s:
            raise ValueError("advance time must be finite and strictly increasing")
        values = self._input(intensities)
        dt = time_s - self.time_s
        pending = []
        candidates = []
        for index, (old, intensity, thresholds) in enumerate(zip(self.states, values, self.thresholds)):
            target = math.log(intensity)
            tau = self.profile.time_constant(intensity)
            change = target - old.filtered_log
            filtered = (target if tau == 0 else
                        old.filtered_log - change * math.expm1(-dt / tau))
            polarity = 1 if filtered >= old.reference_log else -1
            threshold = thresholds[0 if polarity > 0 else 1]
            reference = old.reference_log
            last_emitted = old.last_emitted_s
            # The loop uses reference + k*C (not cumulative increments) to limit drift.
            crossing_index = 1
            while True:
                level = old.reference_log + polarity * crossing_index * threshold
                roundoff = 8 * max(math.ulp(filtered), math.ulp(level))
                if polarity * (filtered - level) < -roundoff:
                    break
                if tau == 0:
                    offset = 0.0
                else:
                    if change == 0:
                        break
                    fraction = (level - old.filtered_log) / change
                    # A finite RC response cannot reach its asymptote in finite time.
                    if fraction >= 1:
                        break
                    offset = -tau * math.log1p(-fraction) if fraction > 0 else 0.0
                    if offset - dt > 8 * max(math.ulp(offset), math.ulp(dt)):
                        break
                    offset = min(offset, dt)
                if len(candidates) >= self.max_candidates_per_step:
                    # State/counters/time commit only after the whole step succeeds.
                    raise OverflowError("candidate capacity exceeded; step was not committed")
                crossing_time = self.time_s + offset
                emitted = crossing_time - last_emitted >= self.profile.refractory_s
                candidates.append(Crossing(index % self.width, index // self.width,
                                           crossing_time, polarity, emitted))
                # Explicit event-gating approximation: consume reference even if suppressed.
                reference = level
                if emitted:
                    last_emitted = crossing_time
                crossing_index += 1
            pending.append(PixelState(reference, filtered, last_emitted))
        candidates.sort(key=lambda event: (event.t_s, event.y, event.x, event.p))
        result = StepResult(tuple(candidates))
        self.states = tuple(pending)
        self.time_s = time_s
        self.candidate_total += len(candidates)
        self.refractory_suppressed_total += result.refractory_suppressed
        self.emitted_total += len(candidates) - result.refractory_suppressed
        return result
