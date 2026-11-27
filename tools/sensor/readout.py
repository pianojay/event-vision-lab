"""Bounded FIFO camera readout, independent of pixel dynamics and capture loss."""
from collections import deque
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReadoutProfile:
    capacity_events: int = 1024
    service_ns: int = 1000
    latency_ns: int = 0

    def __post_init__(self):
        for name in ("capacity_events", "service_ns", "latency_ns"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True)
class ReadoutEvent:
    x: int
    y: int
    t_ns: int
    p: int
    origin: str = "optical"

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in (self.x, self.y, self.t_ns)):
            raise ValueError("event coordinates/time must be nonnegative integers")
        if type(self.p) is not int or self.p not in (-1, 1):
            raise ValueError("polarity must be -1 or +1")


@dataclass(frozen=True)
class Delivery:
    event: ReadoutEvent
    delivered_ns: int


class ReadoutQueue:
    """Drop newest on full. Capacity includes service and propagation latency.

    Events retain sensor timestamps. A second timestamp records delivery. FIFO
    serialization takes service_ns; fixed latency follows serialization, may
    overlap the next event's service, and still occupies one capacity slot.
    """

    def __init__(self, profile=ReadoutProfile()):
        self.profile = profile
        self.pending = deque()
        self.watermark_ns = 0
        self.service_end_ns = 0
        self.counters = dict(readout_input=0, readout_accepted=0, readout_dropped=0,
                             readout_delivered=0, readout_peak_occupancy=0)

    def advance(self, events, until_ns):
        events = tuple(events)
        if type(until_ns) is not int or until_ns < self.watermark_ns:
            raise ValueError("readout watermark must be a nondecreasing integer")
        previous = self.watermark_ns
        for event in events:
            if not isinstance(event, ReadoutEvent) or not previous <= event.t_ns <= until_ns:
                raise ValueError("readout input must be ordered within the current interval")
            previous = event.t_ns
        deliveries = []

        def drain(time_ns):
            while self.pending and self.pending[0].delivered_ns <= time_ns:
                deliveries.append(self.pending.popleft())
                self.counters["readout_delivered"] += 1

        for event in events:
            drain(event.t_ns)
            self.counters["readout_input"] += 1
            if len(self.pending) >= self.profile.capacity_events:
                self.counters["readout_dropped"] += 1
                continue
            self.service_end_ns = max(event.t_ns, self.service_end_ns) + self.profile.service_ns
            self.pending.append(Delivery(event, self.service_end_ns + self.profile.latency_ns))
            self.counters["readout_accepted"] += 1
            self.counters["readout_peak_occupancy"] = max(
                self.counters["readout_peak_occupancy"], len(self.pending))
        drain(until_ns)
        self.watermark_ns = until_ns
        return tuple(deliveries)

    def snapshot(self):
        return {**self.counters, "readout_pending": len(self.pending),
                "watermark_ns": self.watermark_ns}

    def effective(self):
        return {"model": "bounded-fifo-readout-v1", **asdict(self.profile),
                "overflow": "drop-newest", "capacity_scope": "accepted but not delivered",
                "tie_rule": "deliver completed events before admitting arrivals at the same time",
                "timestamp": "preserve pixel event time; retain separate delivered_ns"}
