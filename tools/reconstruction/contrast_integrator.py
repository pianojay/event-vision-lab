"""Event-only contrast integration with a declared constant log-intensity prior."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'processing'))
from event_processor import EventProcessor, load_capture


class ContrastIntegrator:
    def __init__(self, config, sensor_size):
        self.history = EventProcessor({}, sensor_size)
        self.reset_ns = -1
        self.configure(config, sensor_size)

    def configure(self, config, sensor_size):
        settings = dict(initial_log_intensity=0.0,on_threshold=0.2,off_threshold=0.2)
        if set(config)-set(settings):
            raise ValueError("Unknown reconstruction setting")
        settings.update(config)
        for key,value in settings.items():
            if type(value) not in (int,float) or not math.isfinite(value):
                raise ValueError("Reconstruction parameters must be finite numbers")
            if key != 'initial_log_intensity' and value <= 0:
                raise ValueError("Contrast thresholds must be positive")
        self.history.configure({},sensor_size)
        self.config = settings

    def consume(self, events):
        self.history.consume(events)

    def reset(self, reset_ns=-1):
        if type(reset_ns) is not int or reset_ns < -1:
            raise ValueError("Reset time must be -1 or nonnegative integer nanoseconds")
        self.reset_ns = reset_ns
        self.history.reset()

    def snapshot(self, cursor_ns):
        if type(cursor_ns) is not int or cursor_ns < 0:
            raise ValueError("Cursor must be nonnegative integer nanoseconds")
        width,height = self.history.sensor_size
        log_intensity = [float(self.config['initial_log_intensity'])]*(width*height)
        support = [0]*(width*height)
        integrated = 0
        latest = None
        for x,y,t,p in self.history.events:
            if t > cursor_ns:
                break
            if t <= self.reset_ns:
                continue
            index = y*width+x
            log_intensity[index] += self.config['on_threshold'] if p == 1 else -self.config['off_threshold']
            support[index] += 1
            integrated += 1
            latest = t
        clipped = sum(not -80 <= value <= 80 for value in log_intensity)
        return dict(dimensions=[width,height],cursor_ns=cursor_ns,reset_ns=self.reset_ns,
                    log_intensity=log_intensity,
                    relative_intensity=[math.exp(max(-80,min(80,value))) for value in log_intensity],
                    support=support,integrated_count=integrated,
                    observed_pixels=sum(value>0 for value in support),
                    latest_event_age_ns=None if latest is None else cursor_ns-latest,
                    elapsed_since_reset_ns=max(0,cursor_ns-max(0,self.reset_ns)),
                    clipped_intensity_pixels=clipped,reads_ground_truth=False)


def write_pgm(path, snapshot):
    width,height = snapshot['dimensions']
    pixels=bytes(round(255*value/(1+value)) for value in snapshot['relative_intensity'])
    path.write_bytes(f'P5\n{width} {height}\n255\n'.encode()+pixels)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cursor-ns',type=int)
    parser.add_argument('--reset-ns',type=int,default=-1)
    parser.add_argument('--initial-log-intensity',type=float,default=0.0)
    parser.add_argument('--on-threshold',type=float,required=True)
    parser.add_argument('--off-threshold',type=float,required=True)
    args=parser.parse_args()
    manifest,events=load_capture(args.manifest)
    meta=manifest['captures']['events']
    config=dict(initial_log_intensity=args.initial_log_intensity,
                on_threshold=args.on_threshold,off_threshold=args.off_threshold)
    model=ContrastIntegrator(config,(meta['width'],meta['height']))
    model.reset(args.reset_ns)
    model.consume(events)
    cursor=args.cursor_ns if args.cursor_ns is not None else meta['duration_ns']
    snapshot=model.snapshot(cursor)
    report=dict(schema='event-lab-contrast-integration-v1',method='constant-prior contrast integration',
                source=str(args.manifest),source_sha256=meta['sha256'],config=config,
                capture_loss=meta['overflow_count'],initial_intensity_observed=False,
                scale_alignment=False,additional_observations=[],snapshot=snapshot,
                display_mapping='I/(1+I), fixed arbitrary exposure')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'reconstruction.json').write_text(json.dumps(report,indent=2)+'\n')
    write_pgm(args.output/'relative-intensity.pgm',snapshot)
    print(json.dumps(dict(output=str(args.output),integrated=snapshot['integrated_count'],
                          clipped=snapshot['clipped_intensity_pixels'])))


if __name__ == '__main__':
    main()
