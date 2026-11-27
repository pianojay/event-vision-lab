import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from event_processor import EventProcessor, load_capture

ROOT = Path(__file__).resolve().parents[2]
ROWS = [[0, 0, 0, 1], [1, 0, 10, 1], [1, 0, 10, -1],
        [2, 1, 11, -1], [4, 2, 20, 1], [4, 2, 21, -1]]


def processor(config=None, rows=ROWS):
    p = EventProcessor(config or {}, (5, 3))
    p.consume(rows)
    return p


def parity_fixtures():
    return [dict(size=[5, 3], config=dict(roi=roi, bin_size=b, polarity=polarity,
                     representation=representation, window_ns=10, tau_ns=10),
                 events=ROWS, cursors=[0, 10, 11, 20, 21, 10],
                 reconfigure=dict(roi=[0, 0, 5, 3], bin_size=1, window_ns=100))
            for roi in ([0, 0, 5, 3], [1, 0, 5, 3], [0, 0, 0, 0])
            for b in (1, 2, 4) for polarity in ('both', 'on', 'off')
            for representation in ('window', 'decay', 'time-surface')]


class ProcessingTests(unittest.TestCase):
    def test_window_lower_exclusive_upper_inclusive_and_ties(self):
        p = processor(dict(window_ns=10))
        self.assertEqual(p.snapshot(10)['visible_count'], 2)
        self.assertEqual(p.snapshot(20)['visible_count'], 2)
        self.assertEqual(p.snapshot(21)['visible_count'], 2)
        self.assertEqual(sum(p.snapshot(20)['on']), 1)
        self.assertEqual(sum(p.snapshot(20)['off']), 1)

    def test_full_and_empty_roi(self):
        p = processor(dict(window_ns=100))
        full = p.snapshot(21)
        self.assertEqual(full['selected_count'], 6)
        p.configure(dict(roi=[0, 0, 0, 0]), (5, 3))
        empty = p.snapshot(21)
        self.assertEqual(empty['incoming_count'], 6)
        self.assertEqual(empty['dimensions'], [0, 0])
        self.assertEqual(empty['on'], [])
        self.assertEqual(empty['selected_count'], 0)
        p.configure(dict(window_ns=100), (5, 3))
        self.assertEqual(p.snapshot(21), full)

    def test_roi_boundary_and_original_origin(self):
        result = processor(dict(roi=[1, 0, 4, 2], bin_size=2)).snapshot(21)
        self.assertEqual(result['origin'], [1, 0])
        self.assertEqual(result['dimensions'], [2, 1])
        self.assertEqual(result['roi_count'], 3)
        self.assertEqual(result['on'], [1, 0])
        self.assertEqual(result['off'], [2, 0])

    def test_partial_bins_conserve_opposite_polarities(self):
        for b, dimensions, areas in ((1, [5,3], [1]*15), (2,[3,2],[4,4,2,2,2,1]),
                                     (4,[2,1],[12,3])):
            result = processor(dict(bin_size=b)).snapshot(21)
            self.assertEqual(result['dimensions'], dimensions)
            self.assertEqual(result['bin_areas'], areas)
            self.assertEqual(sum(result['on']), 3)
            self.assertEqual(sum(result['off']), 3)
            self.assertEqual(result['visible_count'], 6)

    def test_polarity_selection_changes_counts(self):
        for selection, on, off in [('both',3,3),('on',3,0),('off',0,3)]:
            result = processor(dict(polarity=selection)).snapshot(21)
            self.assertEqual((sum(result['on']),sum(result['off'])), (on,off))
            self.assertEqual(result['selected_count'], on+off)
            self.assertEqual(result['incoming_count'], 6)

    def test_decay_weights_every_event_at_its_time(self):
        result = processor(dict(representation='decay',tau_ns=10),
                           [[0,0,0,1],[0,0,10,1],[0,0,10,-1]]).snapshot(20)
        self.assertAlmostEqual(result['on'][0], math.exp(-2)+math.exp(-1))
        self.assertAlmostEqual(result['off'][0], math.exp(-1))

    def test_time_surface_uses_last_event_per_bin_and_polarity(self):
        result = processor(dict(representation='time-surface',tau_ns=10,bin_size=2),
                           [[0,0,0,1],[0,0,5,-1],[1,0,10,1]]).snapshot(20)
        self.assertAlmostEqual(result['on'][0], math.exp(-1))
        self.assertAlmostEqual(result['off'][0], math.exp(-1.5))

    def test_snapshot_pause_scrub_and_configuration_are_deterministic(self):
        p = processor(dict(window_ns=10))
        baseline = p.snapshot(10)
        p.snapshot(21)
        self.assertEqual(p.snapshot(10), baseline)
        self.assertEqual(p.snapshot(10), baseline)
        p.configure(dict(window_ns=10,polarity='off'),(5,3))
        self.assertEqual(p.snapshot(10)['selected_count'],1)
        p.configure(dict(window_ns=10),(5,3))
        self.assertEqual(p.snapshot(10), baseline)

    def test_raw_rows_and_config_are_owned_and_preserved(self):
        rows = copy.deepcopy(ROWS)
        config = dict(roi=[0,0,5,3])
        p = processor(config, rows)
        rows[0][0] = 4
        config['roi'][0] = 4
        result = p.snapshot(21)
        self.assertEqual(result['on'][0],1)
        result['on'][0] = 99
        self.assertEqual(p.snapshot(21)['on'][0],1)

    def test_reset_and_batch_equivalence(self):
        p = processor(rows=[])
        p.consume(ROWS[:2]); p.consume(ROWS[2:])
        self.assertEqual(p.snapshot(21),processor().snapshot(21))
        p.reset()
        self.assertEqual(p.snapshot(21)['incoming_count'],0)
        p.consume(ROWS)
        self.assertEqual(p.snapshot(21),processor().snapshot(21))

    def test_invalid_boundary_inputs(self):
        for cfg in [dict(roi=[0,0,6,3]),dict(roi=[2,0,1,1]),dict(bin_size=3),
                    dict(bin_size=True),dict(window_ns=0),dict(tau_ns=1.5),
                    dict(gain=float('nan')),dict(polarity='color'),dict(unknown=1)]:
            with self.subTest(cfg=cfg), self.assertRaises(ValueError): processor(cfg)
        p = processor()
        for rows in [[[0,0,20,1]],[[5,0,22,1]],[[0,0,22,0]],[[0,0,22.1,1]]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError): p.consume(rows)
        self.assertEqual(p.snapshot(30)['received_count'],6)

    def test_large_integer_clock_and_future_events(self):
        t = 2**60
        p = processor(dict(window_ns=2),[[0,0,t,1],[0,0,t+1,-1],[0,0,t+2,1]])
        self.assertEqual(p.snapshot(t+1)['visible_count'],2)
        self.assertEqual(p.snapshot(t+2)['on'][0],1)
        self.assertEqual(p.snapshot(t+2)['off'][0],1)
        self.assertEqual(p.snapshot(t+1)['incoming_count'],2)

    def test_saved_config_and_existing_capture(self):
        manifest, rows = load_capture(ROOT/'docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json')
        meta = manifest['captures']['events']
        p = EventProcessor(dict(bin_size=4), (meta['width'],meta['height']))
        p.consume(rows)
        q = EventProcessor(json.loads(json.dumps(p.config)),p.sensor_size)
        q.consume(rows)
        self.assertEqual(q.snapshot(meta['duration_ns']),p.snapshot(meta['duration_ns']))
        self.assertEqual(p.snapshot(meta['duration_ns'])['incoming_count'],meta['stored_count'])

    @unittest.skipUnless(os.environ.get('GODOT'), 'Set GODOT for cross-engine behavior comparison')
    def test_godot_matches_python_all_configurations_and_resets(self):
        fixtures = parity_fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'input.json', Path(tmp)/'output.json'
            source.write_text(json.dumps(fixtures))
            command = [os.environ['GODOT'],'--headless','--path',str(ROOT/'prototype'),
                       '--script','res://processing/check_processing.gd','--',
                       '--input='+str(source),'--output='+str(target)]
            result = subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse('SCRIPT ERROR' in result.stderr, result.stderr[:2000])
            actual = json.loads(target.read_text())
        self.assertEqual(len(actual),81)
        for fixture, snapshots in zip(fixtures,actual):
            p = EventProcessor(fixture['config'],fixture['size'])
            p.consume(fixture['events'])
            expected = [p.snapshot(cursor) for cursor in fixture['cursors']]
            p.configure(fixture['reconfigure'],fixture['size'])
            expected.append(p.snapshot(fixture['cursors'][-1]))
            p.reset()
            expected.append(p.snapshot(fixture['cursors'][-1]))
            for left,right in zip(expected,snapshots):
                for key in left:
                    if key in ('on','off'):
                        self.assertEqual(len(left[key]),len(right[key]))
                        for a,b in zip(left[key],right[key]): self.assertAlmostEqual(a,b,places=6)
                    else:
                        self.assertEqual(left[key],right[key], (fixture,key))


if __name__ == '__main__':
    unittest.main(verbosity=2)
