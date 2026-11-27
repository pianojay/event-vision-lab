"""Event-time processing of immutable [x, y, relative_ns, polarity] rows."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys


class EventProcessor:
    def __init__(self, config, sensor_size):
        self.events = []
        self.configure(config, sensor_size)

    def configure(self, config, sensor_size):
        width, height = sensor_size
        if any(type(v) is not int or v < 1 for v in sensor_size):
            raise ValueError("Sensor dimensions must be positive integers")
        if self.events and tuple(sensor_size) != self.sensor_size:
            raise ValueError("Reset before changing sensor dimensions")
        cfg = dict(roi=[0, 0, width, height], bin_size=1, polarity="both",
                   representation="window", window_ns=40_000_000, tau_ns=40_000_000,
                   normalization="count", gain=0.5)
        if set(config) - set(cfg):
            raise ValueError("Unknown processing setting")
        cfg.update(config)
        roi = cfg['roi']
        if (not isinstance(roi, (tuple, list)) or len(roi) != 4
                or any(type(v) is not int for v in roi)
                or not (0 <= roi[0] <= roi[2] <= width and 0 <= roi[1] <= roi[3] <= height)):
            raise ValueError("ROI must be half-open sensor bounds [x0,y0,x1,y1]")
        if type(cfg['bin_size']) is not int or cfg['bin_size'] not in (1, 2, 4):
            raise ValueError("Bin size must be 1, 2 or 4")
        if cfg['polarity'] not in ('both', 'on', 'off'):
            raise ValueError("Invalid polarity")
        if cfg['representation'] not in ('window', 'decay', 'time-surface'):
            raise ValueError("Invalid representation")
        if cfg['normalization'] not in ('count', 'per-pixel'):
            raise ValueError("Invalid display normalization")
        for key in ('window_ns', 'tau_ns'):
            if type(cfg[key]) is not int or not 0 < cfg[key] <= 2**63-1:
                raise ValueError(f"{key} must be positive integer nanoseconds")
        if (type(cfg['gain']) not in (int, float) or not math.isfinite(cfg['gain'])
                or cfg['gain'] <= 0):
            raise ValueError("Gain must be finite and positive")
        self.sensor_size = tuple(sensor_size)
        self.config = dict(cfg, roi=list(roi))

    def consume(self, events):
        incoming = []
        previous = self.events[-1][2] if self.events else 0
        for row in events:
            if len(row) != 4 or any(type(v) is not int for v in row):
                raise ValueError("Events must be four integer fields")
            x, y, timestamp, polarity = row
            if (not 0 <= x < self.sensor_size[0] or not 0 <= y < self.sensor_size[1]
                    or not previous <= timestamp <= 2**63-1 or polarity not in (-1, 1)):
                raise ValueError("Invalid event coordinate, order, time or polarity")
            incoming.append(tuple(row))
            previous = timestamp
        self.events.extend(incoming)

    def reset(self):
        self.events.clear()

    def snapshot(self, cursor_ns):
        if type(cursor_ns) is not int or cursor_ns < 0:
            raise ValueError("Cursor must be nonnegative integer nanoseconds")
        c = self.config
        x0, y0, x1, y1 = c['roi']
        b = c['bin_size']
        width, height = (x1-x0+b-1)//b, (y1-y0+b-1)//b
        on, off = [0]*(width*height), [0]*(width*height)
        incoming = retained = selected = visible = 0
        for x, y, timestamp, polarity in self.events:
            if timestamp > cursor_ns:
                break
            incoming += 1
            if not (x0 <= x < x1 and y0 <= y < y1):
                continue
            retained += 1
            if (c['polarity'] == 'on' and polarity < 0 or
                    c['polarity'] == 'off' and polarity > 0):
                continue
            selected += 1
            age = cursor_ns-timestamp
            if c['representation'] == 'window' and age >= c['window_ns']:
                continue
            visible += 1
            index = ((y-y0)//b)*width+(x-x0)//b
            output = on if polarity > 0 else off
            value = 1 if c['representation'] == 'window' else math.exp(-age/c['tau_ns'])
            if c['representation'] == 'time-surface':
                output[index] = max(output[index], value)
            else:
                output[index] += value
        areas = [min(b, x1-x0-x*b)*min(b, y1-y0-y*b)
                 for y in range(height) for x in range(width)]
        return dict(dimensions=[width, height], origin=[x0, y0], bin_size=b,
                    on=on, off=off, bin_areas=areas, received_count=len(self.events),
                    incoming_count=incoming, roi_count=retained, polarity_count=selected,
                    selected_count=selected, visible_count=visible, cursor_ns=cursor_ns,
                    representation=c['representation'], normalization=c['normalization'])


def load_capture(manifest_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'pipeline'))
    from pipeline import read_capture
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != 'event-lab-pipeline-v1':
        raise ValueError("Unsupported pipeline manifest")
    meta = manifest['captures']['events']
    path = manifest_path.parent/meta['file']
    read_capture(path, meta)
    epoch = int(meta['epoch_ns'])
    with path.open(newline='') as file:
        events = [[int(r['x']), int(r['y']), int(r['t_ns'])-epoch, int(r['p'])]
                  for r in csv.DictReader(file)]
    return manifest, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--cursor-ns', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, events = load_capture(args.manifest)
    meta = manifest['captures']['events']
    config = json.loads(args.config.read_text()) if args.config else {}
    processor = EventProcessor(config, (meta['width'], meta['height']))
    processor.consume(events)
    cursor = args.cursor_ns if args.cursor_ns is not None else meta['duration_ns']
    result = dict(schema='event-lab-processing-v1', source=str(args.manifest),
                  source_sha256=meta['sha256'], config=processor.config,
                  snapshot=processor.snapshot(cursor), reads_ground_truth=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(output=str(args.output), selected=result['snapshot']['selected_count'])))


if __name__ == '__main__':
    main()
