import argparse
import json
import math
from pathlib import Path

from event_processor import EventProcessor,load_capture
from streaming_processor import StreamingProcessor


def compare(manifest_path,output):
    manifest,events=load_capture(manifest_path)
    meta=manifest['captures']['events'];size=(meta['width'],meta['height'])
    cursors=sorted(set(int(frame['time_ns']) for frame in manifest['optical_input']['frames']))
    results=[]
    for representation in ('window','decay','time-surface'):
        for b in (1,2,4):
            for roi in ([0,0,*size],[size[0]//2,0,*size]):
                config=dict(representation=representation,bin_size=b,roi=roi,window_ns=40_000_000,tau_ns=40_000_000)
                reference=EventProcessor(config,size);reference.consume(events)
                stream=StreamingProcessor(config,size)
                index=0;peak=0;error=0.0
                for cursor in cursors:
                    end=index
                    while end<len(events) and events[end][2]<=cursor:end+=1
                    stream.consume(events[index:end]);index=end
                    actual,expected=stream.snapshot(cursor),reference.snapshot(cursor)
                    peak=max(peak,actual['resident_event_count'])
                    for key in ['incoming_count','roi_count','selected_count','visible_count','dimensions','origin','bin_areas']:
                        if actual[key]!=expected[key]:raise AssertionError((key,actual[key],expected[key]))
                    for key in ('on','off'):
                        for a,b_value in zip(actual[key],expected[key]):
                            error=max(error,abs(a-b_value))
                            if not math.isclose(a,b_value,rel_tol=1e-12,abs_tol=1e-12):
                                raise AssertionError((key,a,b_value))
                results.append(dict(config=stream.config,snapshots=len(cursors),max_absolute_activity_error=error,
                                    peak_resident_events=peak,final_selected_count=actual['selected_count'],
                                    window_overflow_count=actual['window_overflow_count'],state_cells=actual['state_cells']))
    report=dict(schema='event-lab-stream-comparison-v1',source=str(manifest_path),source_sha256=meta['sha256'],
                events=len(events),comparisons=results,passed=True,reads_optical_intensity=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=compare(args.manifest,args.output)
    print(json.dumps(dict(events=report['events'],configurations=len(report['comparisons']),passed=report['passed'])))
