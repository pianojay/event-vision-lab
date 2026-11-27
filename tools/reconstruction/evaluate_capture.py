import argparse
import base64
import zlib
import cProfile
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import pstats
import statistics
import struct
import time
import tracemalloc
from xml.sax.saxutils import escape

from contrast_integrator import ContrastIntegrator, load_capture, write_pgm


def evaluate(manifest_path, output):
    manifest,events=load_capture(manifest_path)
    meta=manifest['captures']['events']
    parameters=manifest['effective_config'].get('sensor_parameters',manifest['effective_config'])
    floors={name:section['intensity_floor'] for name,section in
            [('optical_input',manifest['optical_input']),('effective_config',manifest['effective_config'])]
            if 'intensity_floor' in section}
    if any(type(value) not in (int,float) or not math.isfinite(value) or value<=0 for value in floors.values()):
        raise ValueError('Declared intensity floor must be a finite positive number')
    if len(set(floors.values()))>1:
        raise ValueError('Optical archive and effective sensor intensity floors disagree')
    intensity_floor=next(iter(floors.values()),None)
    config=dict(initial_log_intensity=0.0,on_threshold=parameters.get('on_threshold',.2),
                off_threshold=parameters.get('off_threshold',.2))
    model=ContrastIntegrator(config,(meta['width'],meta['height']))
    model.consume(events)
    frames=manifest['optical_input']['frames']
    snapshots=[model.snapshot(int(frame['time_ns'])) for frame in frames]
    expected_work=sum(sum(row[2]<=int(frame['time_ns']) for row in events) for frame in frames)
    assert sum(s['integrated_count'] for s in snapshots)==expected_work
    measurements=[]
    for repeat in range(5):
        started=time.perf_counter_ns()
        values=[model.snapshot(int(frame['time_ns'])) for frame in frames]
        elapsed=time.perf_counter_ns()-started
        assert sum(s['integrated_count'] for s in values)==expected_work
        measurements.append(elapsed/1e6)
    tracemalloc.start()
    measured_model=ContrastIntegrator(config,model.history.sensor_size)
    measured_model.consume(events)
    measured=[measured_model.snapshot(int(frame['time_ns'])) for frame in frames]
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert sum(s['integrated_count'] for s in measured)==expected_work
    profiler=cProfile.Profile()
    profiler.enable()
    for frame in frames:model.snapshot(int(frame['time_ns']))
    profiler.disable()
    profile_output=io.StringIO()
    pstats.Stats(profiler,stream=profile_output).sort_stats('cumulative').print_stats(8)
    evaluation=[]
    sampled=[]
    for index,(frame,snapshot) in enumerate(zip(frames,snapshots)):
        archive=manifest_path.parent/frame['file']
        with archive.open('rb') as file:
            file.seek(frame['offset_bytes']);payload=file.read(frame['length_bytes'])
        if hashlib.sha256(payload).hexdigest()!=frame['sha256']:
            raise ValueError('Optical evaluation archive hash mismatch')
        truth=struct.unpack('<'+'f'*(len(payload)//4),payload)
        if len(truth)!=len(snapshot['log_intensity']) or any(not math.isfinite(x) or x<0 for x in truth):
            raise ValueError('Evaluation expects finite nonnegative scalar FP32 intensity per pixel')
        if intensity_floor is None and any(x==0 for x in truth):
            raise ValueError('Zero optical intensity requires a declared sensor intensity floor')
        log_truth=[math.log(max(value,intensity_floor)) if intensity_floor is not None else math.log(value)
                   for value in truth]
        errors=[prediction-value for prediction,value in zip(snapshot['log_intensity'],log_truth)]
        offset=sum(errors)/len(errors)
        evaluation.append(dict(cursor_ns=frame['time_ns'],integrated_count=snapshot['integrated_count'],
            floor_applied_pixels=sum(value<intensity_floor for value in truth) if intensity_floor is not None else 0,
            observed_pixels=snapshot['observed_pixels'],latest_event_age_ns=snapshot['latest_event_age_ns'],
            log_rmse_no_alignment=math.sqrt(sum(e*e for e in errors)/len(errors)),
            global_log_offset_fitted_for_evaluation=offset,
            log_rmse_after_explicit_global_alignment=math.sqrt(sum((e-offset)**2 for e in errors)/len(errors))))
        if index in {0,len(frames)//2,len(frames)-1}:
            sampled.append((snapshot,truth))
    report=dict(schema='event-lab-reconstruction-evaluation-v1',source=str(manifest_path),
        source_sha256=meta['sha256'],config=config,method='constant-prior contrast integration',
        inference_inputs=['pixel-emitted events','dimensions','nominal ON/OFF thresholds','constant prior'],
        initial_intensity_observed=False,truth_used_for_inference=False,
        truth_used_for_evaluation='archived FP32 optical samples; separately read after all inference',
        evaluation_intensity_floor=intensity_floor,evaluation_intensity_floor_sources=list(floors),
        evaluation_log_transform='log(max(archived_intensity, declared_sensor_floor))' if intensity_floor is not None
            else 'log(archived_intensity); no floor declared',
        evaluation_context=dict(scene=manifest['effective_config'].get('scene'),
            station=manifest.get('interaction_stage',{}).get('station',manifest['effective_config'].get('station')),
            treatment=manifest['effective_config'].get('treatment'),effective_config=manifest['effective_config'],
            interaction_stage=manifest.get('interaction_stage'),capture_source=manifest.get('source')),
        scale_alignment='none for output; explicit global-log-offset fit reported separately for evaluation',
        capture_count=len(events),capture_loss=meta['overflow_count'],frame_count=len(frames),frames=evaluation,
        offline_latency=dict(repeats=5,sequence_ms=measurements,median_sequence_ms=statistics.median(measurements),
            median_snapshot_ms=statistics.median(measurements)/len(frames),
            snapshot_range_ms=[min(measurements)/len(frames),max(measurements)/len(frames)],
            integrated_events_counted_across_snapshots=expected_work,failures=0,
            timing_scope='full-history snapshots including log, intensity, support arrays; excludes load, render, and truth evaluation',
            allocation_peak_bytes_separate_tracemalloc_run=peak,
            limitation='offline single-process CPU measurements during concurrent project development; no live backlog guarantee'),
        sustained_live_backlog=None,host=dict(python=platform.python_version(),platform=platform.platform(),
            processor=platform.processor(),logical_cpus=os.cpu_count()),
        missing_evaluations=['sustained concurrent live acquisition'],
        evaluation_scope='this recorded capture only; no inference about unrecorded stations or live throughput')
    output.mkdir(parents=True,exist_ok=True)
    (output/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'profile.txt').write_text(profile_output.getvalue().rstrip()+'\n')
    write_pgm(output/'final-relative-intensity.pgm',snapshots[-1])
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650">',
         '<rect width="1000" height="650" fill="#142030"/>']
    width,height=meta['width'],meta['height']
    scale=min(300/width,230/height)
    for column,(snapshot,truth) in enumerate(sampled):
        for row,(label,values) in enumerate([('Inferred, constant prior',snapshot['relative_intensity']),('Truth, evaluation only',truth)]):
            x,y=column*330+10,row*310+30
            svg.append(f'<text x="{x}" y="{y}" fill="white" font-family="sans-serif" font-size="15">{escape(label)} at {snapshot["cursor_ns"]/1e6:g} ms</text>')
            pixels=bytes(round(255*value/(1+value)) for value in values)
            def chunk(name,data):
                return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
            scanlines=b''.join(b'\x00'+pixels[i*width:(i+1)*width] for i in range(height))
            png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))
                 +chunk(b'IDAT',zlib.compress(scanlines))+chunk(b'IEND',b''))
            uri='data:image/png;base64,'+base64.b64encode(png).decode()
            svg.append(f'<image x="{x}" y="{y+15}" width="{width*scale}" height="{height*scale}" href="{uri}" style="image-rendering:pixelated"/>')
    svg.append('</svg>')
    (output/'comparison.svg').write_text('\n'.join(svg))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=evaluate(args.manifest,args.output)
    print(json.dumps(dict(events=report['capture_count'],frames=report['frame_count'],
                          final_log_rmse=report['frames'][-1]['log_rmse_no_alignment'],
                          median_snapshot_ms=report['offline_latency']['median_snapshot_ms'])))
