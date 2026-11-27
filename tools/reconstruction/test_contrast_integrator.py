import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from contrast_integrator import ContrastIntegrator, load_capture

ROOT=Path(__file__).resolve().parents[2]


class ReconstructionTests(unittest.TestCase):
    def model(self, config=None, rows=()):
        model=ContrastIntegrator(config or {},(2,1));model.consume(rows)
        return model

    def test_silent_pixels_keep_constant_prior(self):
        result=self.model(dict(initial_log_intensity=math.log(3))).snapshot(100)
        self.assertEqual(result['observed_pixels'],0)
        self.assertEqual(result['integrated_count'],0)
        self.assertIsNone(result['latest_event_age_ns'])
        for value in result['relative_intensity']:self.assertAlmostEqual(value,3)

    def test_independent_on_off_thresholds_and_timestamp_ties(self):
        result=self.model(dict(on_threshold=.3,off_threshold=.1),
                          [[0,0,0,1],[0,0,10,1],[0,0,10,-1],[1,0,11,-1]]).snapshot(10)
        self.assertAlmostEqual(result['log_intensity'][0],.5)
        self.assertEqual(result['log_intensity'][1],0)
        self.assertEqual(result['integrated_count'],3)
        self.assertEqual(result['support'],[3,0])

    def test_unknown_scale_is_not_recovered(self):
        rows=[[0,0,10,1]]
        first=self.model(rows=rows).snapshot(20)
        second=self.model(dict(initial_log_intensity=math.log(5)),rows).snapshot(20)
        for a,b in zip(first['relative_intensity'],second['relative_intensity']):
            self.assertAlmostEqual(b/a,5)
        self.assertEqual(first['support'],second['support'])

    def test_reset_excludes_past_and_exact_reset_timestamp(self):
        rows=[[0,0,0,1],[0,0,10,1],[1,0,11,-1]]
        model=self.model(rows=rows)
        model.reset(10);model.consume(rows)
        result=model.snapshot(11)
        self.assertEqual(result['integrated_count'],1)
        self.assertEqual(result['log_intensity'],[0,-.2])
        self.assertEqual(model.snapshot(5)['integrated_count'],0)
        model.reset();model.consume(rows)
        self.assertEqual(model.snapshot(11)['integrated_count'],3)

    def test_backward_scrub_batching_and_static_hold(self):
        model=self.model(rows=[[0,0,5,1]])
        reference=model.snapshot(10)
        model.snapshot(100)
        self.assertEqual(reference,model.snapshot(10))
        self.assertEqual(model.snapshot(100)['log_intensity'],reference['log_intensity'])
        self.assertEqual(model.snapshot(100)['latest_event_age_ns'],95)
        model.consume([[1,0,20,-1]])
        self.assertEqual(model.snapshot(20), self.model(rows=[[0,0,5,1],[1,0,20,-1]]).snapshot(20))

    def test_clipping_is_reported_and_log_state_preserved(self):
        result=self.model(dict(on_threshold=100),[[0,0,1,1]]).snapshot(2)
        self.assertEqual(result['clipped_intensity_pixels'],1)
        self.assertEqual(result['log_intensity'],[100,0])
        self.assertEqual(result['relative_intensity'][0],math.exp(80))

    def test_configuration_recomputes_retained_raw(self):
        model=self.model(rows=[[0,0,1,1],[1,0,2,-1]])
        model.configure(dict(on_threshold=.4,off_threshold=.3),(2,1))
        self.assertEqual(model.snapshot(2)['log_intensity'],[.4,-.3])

    def test_invalid_settings_and_events(self):
        for config in [dict(on_threshold=0),dict(off_threshold=-1),dict(initial_log_intensity=float('nan')),
                       dict(initial_log_intensity=True),dict(rgb=[]),dict(on_threshold='0.2')]:
            with self.subTest(config=config),self.assertRaises(ValueError):self.model(config)
        with self.assertRaises(ValueError):self.model(rows=[[2,0,1,1]])
        with self.assertRaises(ValueError):self.model().reset(-2)

    def test_truth_and_candidate_capture_stages_are_rejected(self):
        path=ROOT/'docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo/manifest.json'
        manifest=json.loads(path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            for stage in ('sensor-candidate','ideal-optical-truth'):
                manifest['captures']['events']['stage']=stage
                target=Path(tmp)/'manifest.json';target.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):load_capture(target)

    def test_cli_reads_only_event_capture_and_declared_parameters(self):
        source=ROOT/'docs/evidence/2026-11-28/pipeline-prototype/runs/viewer-demo'
        with tempfile.TemporaryDirectory() as tmp:
            isolated=Path(tmp)/'input';isolated.mkdir()
            for name in ('manifest.json','events.csv'):
                (isolated/name).write_bytes((source/name).read_bytes())
            command=[os.sys.executable,'-B',str(Path(__file__).with_name('contrast_integrator.py')),
                     '--manifest',str(isolated/'manifest.json'),'--output',str(Path(tmp)/'output'),
                     '--on-threshold','.2','--off-threshold','.2']
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads((Path(tmp)/'output/reconstruction.json').read_text())
            self.assertFalse(data['snapshot']['reads_ground_truth'])
            self.assertFalse(data['initial_intensity_observed'])
            self.assertFalse(data['scale_alignment'])
            self.assertEqual(data['snapshot']['integrated_count'],1536)
            self.assertTrue((Path(tmp)/'output/relative-intensity.pgm').read_bytes().startswith(b'P5'))

    @unittest.skipUnless(os.environ.get('GODOT'),'Set GODOT for cross-engine reconstruction comparison')
    def test_godot_matches_reference_prior_threshold_reset_and_scrub(self):
        fixtures=[dict(size=[2,1],config=dict(initial_log_intensity=prior,on_threshold=on,off_threshold=off),
                       events=[[0,0,0,1],[0,0,10,-1],[1,0,20,1]],cursors=[0,10,100,20,10],reset_ns=reset)
                  for prior in (0,.7) for on,off in ((.2,.2),(.3,.1)) for reset in (-1,0,10)]
        with tempfile.TemporaryDirectory() as tmp:
            source,target=Path(tmp)/'input.json',Path(tmp)/'output.json'
            source.write_text(json.dumps(fixtures))
            result=subprocess.run([os.environ['GODOT'],'--headless','--path',str(ROOT/'prototype'),
                '--script','res://processing/check_reconstruction.gd','--','--input='+str(source),'--output='+str(target)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse('SCRIPT ERROR' in result.stderr,result.stderr[:2000])
            actual=json.loads(target.read_text())
        for fixture,snapshots in zip(fixtures,actual):
            model=ContrastIntegrator(fixture['config'],fixture['size']);model.consume(fixture['events'])
            expected=[model.snapshot(cursor) for cursor in fixture['cursors']]
            model.reset(fixture['reset_ns']);model.consume(fixture['events'])
            expected.append(model.snapshot(fixture['cursors'][-1]))
            self.assertEqual(len(snapshots),len(expected))
            for a,b in zip(expected,snapshots):
                for key in a:
                    if key in ('log_intensity','relative_intensity'):
                        for x,y in zip(a[key],b[key]):self.assertAlmostEqual(x,y,places=6)
                    else:self.assertEqual(a[key],b[key])


if __name__ == '__main__':
    unittest.main(verbosity=2)
