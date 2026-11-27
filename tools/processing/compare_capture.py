import argparse
import hashlib
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

from event_processor import EventProcessor, load_capture


def compare(manifest_path, output):
    manifest, rows = load_capture(manifest_path)
    meta = manifest['captures']['events']
    before_hash = hashlib.sha256((manifest_path.parent/'events.csv').read_bytes()).hexdigest()
    cursor = meta['duration_ns']//2
    results, panels = [], []
    for window in (10_000_000,40_000_000):
        for representation in ('window','decay','time-surface'):
            for polarity in ('both','on','off'):
                for b in (1,2,4):
                    config = dict(bin_size=b,polarity=polarity,representation=representation,
                                  window_ns=window,tau_ns=window)
                    p = EventProcessor(config,(meta['width'],meta['height']))
                    p.consume(rows)
                    s = p.snapshot(cursor)
                    summary = {key:value for key,value in s.items() if key not in ('on','off','bin_areas')}
                    summary.update(on_sum=sum(s['on']),off_sum=sum(s['off']),
                                   active_bins=sum(a+b>0 for a,b in zip(s['on'],s['off'])))
                    results.append(dict(config=p.config,snapshot=summary))
                    if polarity == 'both' and representation == 'window':
                        panels.append((f'{window/1e6:g} ms, {b}x{b} bins',s))
    sparse = [[1,1,1,1],[2,1,1,-1],[4,1,1,1],[4,1,2,1]]
    detail = []
    for b in (1,2,4):
        p = EventProcessor(dict(bin_size=b,window_ns=10),(7,3)); p.consume(sparse)
        detail.append(dict(config=p.config,snapshot=p.snapshot(2)))
    after_hash = hashlib.sha256((manifest_path.parent/'events.csv').read_bytes()).hexdigest()
    assert before_hash == after_hash
    report = dict(schema='event-lab-processing-comparison-v1',source=str(manifest_path),
                  source_sha256=before_hash,raw_unchanged=True,cursor_ns=cursor,
                  capture_count=meta['stored_count'],capture_loss=meta['overflow_count'],
                  comparisons=results,declared_sparse_fixture=dict(size=[7,3],events=sparse,comparisons=detail))
    output.mkdir(parents=True,exist_ok=True)
    (output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">',
           '<rect width="960" height="540" fill="#142030"/>']
    for index,(label,s) in enumerate(panels):
        px,py = (index%3)*320+12,(index//3)*270+30
        width,height=s['dimensions']
        scale=min(292/max(1,width),190/max(1,height))
        svg.append(f'<text x="{px}" y="{py}" fill="white" font-family="sans-serif" font-size="16">{escape(label)}</text>')
        for i,(on,off) in enumerate(zip(s['on'],s['off'])):
            level=round(255*(1-math.exp(-(on+off)*0.5)))
            svg.append(f'<rect x="{px+(i%width)*scale}" y="{py+15+(i//width)*scale}" width="{scale}" height="{scale}" fill="rgb({level},{level},{level})"/>')
        active=sum(a+b>0 for a,b in zip(s['on'],s['off']))
        svg.append(f'<text x="{px}" y="{py+235}" fill="white" font-family="sans-serif" font-size="13">{s["visible_count"]} events; {active} bins; fixed gain 0.5</text>')
    svg.append('</svg>')
    (output/'comparison.svg').write_text('\n'.join(svg))
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=compare(args.manifest,args.output)
    print(json.dumps(dict(comparisons=len(report['comparisons']),raw_unchanged=report['raw_unchanged'],events=report['capture_count'])))
