import hashlib
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

from evaluate_capture import evaluate


class CaptureEvaluationTests(unittest.TestCase):
    def capture(self, directory, intensity, floor=1e-6):
        directory.mkdir(parents=True,exist_ok=True)
        events=b'x,y,t_ns,p,sequence\n'
        payload=struct.pack('<f',intensity)
        (directory/'events.csv').write_bytes(events)
        (directory/'intensity.f32').write_bytes(payload)
        manifest={'schema':'event-lab-pipeline-v1',
            'captures':{'events':{'schema':'event-lab-capture-v1','stage':'pixel-emitted','file':'events.csv',
                'width':1,'height':1,'epoch_ns':'0','duration_ns':1,'stream_id':'test',
                'input_count':0,'stored_count':0,'capacity':0,'overflow_count':0,
                'complete_relative_to_stage_input':True,'polarity':{'on':1,'off':-1},
                'sha256':hashlib.sha256(events).hexdigest()}},
            'effective_config':{'scene':'interaction-stage','station':6,'treatment':False},
            'interaction_stage':{'station':'phosphorescence','treatment':False},
            'optical_input':{'frames':[{'file':'intensity.f32','offset_bytes':0,'length_bytes':4,
                'time_ns':0,'sha256':hashlib.sha256(payload).hexdigest()}]}}
        if floor is not None:
            manifest['optical_input']['intensity_floor']=floor
            manifest['effective_config']['intensity_floor']=floor
        path=directory/'manifest.json'
        path.write_text(json.dumps(manifest))
        return path

    def test_zero_truth_uses_declared_floor_and_retains_actual_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report=evaluate(self.capture(root/'input',0),root/'output')
            self.assertAlmostEqual(report['frames'][0]['log_rmse_no_alignment'],-math.log(1e-6))
            self.assertEqual(report['frames'][0]['floor_applied_pixels'],1)
            self.assertEqual(report['frames'][0]['integrated_count'],0)
            self.assertEqual(report['evaluation_intensity_floor'],1e-6)
            self.assertEqual(report['evaluation_context']['station'],'phosphorescence')
            self.assertFalse(report['evaluation_context']['effective_config']['treatment'])
            self.assertFalse(report['truth_used_for_inference'])
            self.assertNotIn('representative reflective/transmissive station',report['missing_evaluations'])

    def test_changed_truth_and_floor_do_not_change_inferred_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=evaluate(self.capture(root/'first',0,1e-6),root/'a')
            second=evaluate(self.capture(root/'second',0.5,1e-4),root/'b')
            self.assertNotEqual(first['frames'][0]['log_rmse_no_alignment'],second['frames'][0]['log_rmse_no_alignment'])
            self.assertEqual((root/'a/final-relative-intensity.pgm').read_bytes(),
                             (root/'b/final-relative-intensity.pgm').read_bytes())
            self.assertEqual(first['config'],second['config'])

    def test_negative_and_nonfinite_optical_truth_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for intensity in (-1,float('nan'),float('inf')):
                with self.subTest(intensity=intensity),self.assertRaises(ValueError):
                    evaluate(self.capture(root/'input',intensity),root/'output')

    def test_zero_needs_declared_floor_but_positive_legacy_capture_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(ValueError):
                evaluate(self.capture(root/'zero',0,None),root/'output')
            report=evaluate(self.capture(root/'positive',1,None),root/'output')
            self.assertEqual(report['frames'][0]['log_rmse_no_alignment'],0)
            self.assertIsNone(report['evaluation_intensity_floor'])

    def test_invalid_or_inconsistent_floor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for floor in (0,-1,float('nan'),float('inf'),True,'1e-6'):
                with self.subTest(floor=floor),self.assertRaises(ValueError):
                    evaluate(self.capture(root/'input',0,floor),root/'output')
            path=self.capture(root/'input',0)
            manifest=json.loads(path.read_text())
            manifest['effective_config']['intensity_floor']=1e-5
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                evaluate(path,root/'output')


if __name__=='__main__':
    unittest.main()
