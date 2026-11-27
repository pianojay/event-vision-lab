import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from event_processor import EventProcessor
from streaming_processor import StreamingProcessor
from test_event_processor import ROWS, parity_fixtures

ROOT=Path(__file__).resolve().parents[2]


def streaming_fixtures():
    fixtures=[]
    for source in parity_fixtures():
        operations=[]
        previous=-1
        for cursor in [0,10,11,20,21,100]:
            operations.append(dict(cursor=cursor,events=[row for row in ROWS if previous<row[2]<=cursor]))
            previous=cursor
        display=dict(source['config'],gain=2,normalization='per-pixel')
        operations.append(dict(config=display,cursor=100))
        operations.append(dict(config=dict(source['config'],roi=[0,0,0,0]),cursor=100))
        operations.append(dict(reset=True,config=source['config'],events=ROWS,cursor=21))
        fixtures.append(dict(size=source['size'],config=source['config'],operations=operations))
    fixtures.append(dict(size=[5,3],config=dict(window_capacity=2,window_ns=10),operations=[
        dict(events=[[0,0,0,1],[0,0,0,-1],[0,0,0,1]],cursor=0),
        dict(events=[[1,0,10,-1]],cursor=10),dict(cursor=20)]))
    for mode in ['window','decay','time-surface']:
        fixtures.append(dict(size=[5,3],config=dict(window_capacity=16,window_ns=10,tau_ns=10,representation=mode),
            operations=[dict(events=[[i%5,(i//5)%3,i,1 if i%2 else -1] for i in range(20000)],cursor=20000)]))
    return fixtures


class StreamingTests(unittest.TestCase):
    def test_forward_stream_matches_offline_reference_across_all_settings(self):
        for fixture in parity_fixtures():
            with self.subTest(config=fixture['config']):
                stream=StreamingProcessor(fixture['config'],fixture['size'])
                reference=EventProcessor(fixture['config'],fixture['size'])
                reference.consume(ROWS)
                previous=-1
                for cursor in [0,10,11,20,21,100]:
                    stream.consume([row for row in ROWS if previous<row[2]<=cursor]);previous=cursor
                    actual,expected=stream.snapshot(cursor),reference.snapshot(cursor)
                    for key in expected:
                        if key=='received_count':continue
                        if key in ('on','off'):
                            for a,b in zip(actual[key],expected[key]):self.assertAlmostEqual(a,b,places=12)
                        else:self.assertEqual(actual[key],expected[key])

    def test_drop_newest_overflow_is_counted_and_expires_without_cancellation(self):
        stream=StreamingProcessor(dict(window_capacity=2,window_ns=10),(2,1))
        rows=[[0,0,0,1],[0,0,0,-1],[1,0,0,1]]
        stream.consume(rows)
        result=stream.snapshot(0)
        self.assertEqual(result['on'],[1,0]);self.assertEqual(result['off'],[1,0])
        self.assertEqual(result['selected_count'],3)
        self.assertEqual(result['resident_event_count'],2)
        self.assertEqual(result['window_overflow_count'],1)
        self.assertFalse(result['complete_since_reset'])
        stream.consume([[1,0,10,-1]])
        result=stream.snapshot(10)
        self.assertEqual(result['off'],[0,1]);self.assertEqual(result['on'],[0,0])
        self.assertEqual(result['resident_event_count'],1)
        self.assertEqual(result['window_overflow_count'],1)
        self.assertEqual(stream.snapshot(20)['visible_count'],0)
        self.assertEqual(rows,[[0,0,0,1],[0,0,0,-1],[1,0,0,1]])

    def test_window_memory_remains_bounded_during_long_stream(self):
        stream=StreamingProcessor(dict(window_ns=10**9,window_capacity=32),(5,3))
        for batch in range(100):
            stream.consume([[i%5,0,i,1] for i in range(batch*100,(batch+1)*100)])
            self.assertLessEqual(len(stream.window),32)
        result=stream.snapshot(10000)
        self.assertEqual(result['incoming_count'],10000)
        self.assertEqual(result['window_overflow_count'],9968)
        self.assertEqual(result['resident_event_count'],32)
        self.assertEqual(result['state_cells'],60)
        self.assertEqual(sum(result['on']),32)

    def test_exponential_modes_keep_no_event_queue(self):
        for mode in ('decay','time-surface'):
            stream=StreamingProcessor(dict(representation=mode,tau_ns=10),(1,1))
            for batch in range(100):
                stream.consume([[0,0,i,1] for i in range(batch*100,(batch+1)*100)])
            result=stream.snapshot(10000)
            self.assertEqual(result['resident_event_count'],0)
            self.assertEqual(result['state_cells'],4)
            self.assertEqual(result['window_overflow_count'],0)
            expected=sum(math.exp(-i/10) for i in range(1,10001)) if mode=='decay' else math.exp(-.1)
            self.assertAlmostEqual(result['on'][0],expected,places=12)

    def test_display_changes_retain_state_processing_changes_clear_only_processor(self):
        stream=StreamingProcessor(dict(window_ns=100),(5,3));stream.consume(ROWS)
        before=stream.snapshot(21)
        display=dict(stream.config,gain=2,normalization='per-pixel')
        stream.configure(display,(5,3))
        result=stream.snapshot(21)
        self.assertEqual(result['on'],before['on']);self.assertEqual(result['off'],before['off'])
        self.assertEqual(result['configuration_generation'],before['configuration_generation'])
        stream.configure(dict(display,bin_size=2),(5,3))
        cleared=stream.snapshot(21)
        self.assertEqual(cleared['incoming_count'],0)
        self.assertEqual(cleared['configuration_generation'],before['configuration_generation']+1)
        self.assertEqual(cleared['dimensions'],[3,2])
        stream.consume([[0,0,22,1]])
        self.assertEqual(stream.snapshot(22)['on'][0],1)

    def test_late_events_and_backward_scrub_require_offline_reference(self):
        stream=StreamingProcessor({},(2,1));stream.consume([[0,0,10,1]])
        stream.snapshot(20)
        with self.assertRaises(ValueError):stream.snapshot(19)
        with self.assertRaises(ValueError):stream.consume([[0,0,19,1]])
        self.assertEqual(stream.snapshot(20)['incoming_count'],1)
        stream.reset();stream.consume([[0,0,0,-1]])
        self.assertEqual(stream.snapshot(0)['off'][0],1)

    def test_invalid_batches_do_not_partially_mutate_state(self):
        stream=StreamingProcessor({},(1,1))
        with self.assertRaises(ValueError):stream.consume([[0,0,1,1],[1,0,2,1]])
        self.assertEqual(stream.snapshot(0)['incoming_count'],0)
        for capacity in (0,1.5,True,1000001):
            with self.assertRaises(ValueError):StreamingProcessor(dict(window_capacity=capacity),(1,1))

    def test_batching_and_idle_expiration(self):
        for mode in ('window','decay','time-surface'):
            config=dict(representation=mode,window_ns=10,tau_ns=10)
            a,b=StreamingProcessor(config,(5,3)),StreamingProcessor(config,(5,3))
            a.consume(ROWS)
            for row in ROWS:
                b.consume([row]);b.snapshot(row[2])
            self.assertEqual(a.snapshot(21),b.snapshot(21))
            result=a.snapshot(1000)
            self.assertEqual(result['resident_event_count'],0)
            self.assertLess(sum(result['on'])+sum(result['off']),1e-40)

    @unittest.skipUnless(os.environ.get('GODOT'),'Set GODOT for bounded streaming parity')
    def test_godot_matches_reference_including_overflow_reset_and_long_stream(self):
        fixtures=streaming_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            source,target=Path(tmp)/'input.json',Path(tmp)/'output.json'
            source.write_text(json.dumps(fixtures))
            result=subprocess.run([os.environ['GODOT'],'--headless','--path',str(ROOT/'prototype'),
                '--script','res://processing/check_streaming.gd','--','--input='+str(source),'--output='+str(target)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr[:2000])
            self.assertFalse('SCRIPT ERROR' in result.stderr,result.stderr[:2000])
            actual=json.loads(target.read_text())
        self.assertEqual(len(actual),85)
        for fixture,snapshots in zip(fixtures,actual):
            stream=StreamingProcessor(fixture['config'],fixture['size'])
            self.assertEqual(len(snapshots),len(fixture['operations']))
            for operation,result in zip(fixture['operations'],snapshots):
                if 'config' in operation:stream.configure(operation['config'],fixture['size'])
                if 'reset' in operation:stream.reset()
                stream.consume(operation.get('events',[]))
                expected=stream.snapshot(operation['cursor'])
                for key in expected:
                    if key in ('on','off'):
                        self.assertEqual(len(result[key]),len(expected[key]))
                        for a,b in zip(result[key],expected[key]):self.assertAlmostEqual(a,b,places=6)
                    else:self.assertEqual(result[key],expected[key],(key,fixture['config']))


if __name__=='__main__':
    unittest.main(verbosity=2)
