import json
from pathlib import Path
import tempfile
import unittest
from tools.stage.experiment import prepare, event_task, GATES
class ExperimentTests(unittest.TestCase):
    def test_protocol_declares_controls_before_capture(self):
        with tempfile.TemporaryDirectory() as parent:
            path=Path(parent)/"trial"
            protocol=prepare(path)
            self.assertEqual(protocol["schema"],"event-lab-stage-experiment-v2")
            self.assertEqual(protocol["gates"],GATES)
            self.assertEqual(len(protocol["runs"]),45)
            for station in range(9):
                runs=[r for r in protocol["runs"] if r["station"]==station]
                self.assertEqual({r["variant"] for r in runs},{"treatment","control","static","spatial","temporal"})
                self.assertFalse(any(Path(r["output"]).exists() for r in runs))
                configs={r["variant"]:json.loads(Path(r["config"]).read_text()) for r in runs}
                control=dict(configs["control"],treatment=True)
                self.assertEqual(control,configs["treatment"])
                if station in (3,4):
                    self.assertEqual(configs["treatment"]["stage_action"],"stripe")
                    self.assertEqual(configs["static"]["stage_action"],"static")
            with self.assertRaises(FileExistsError): prepare(path)
    def test_event_task_locates_without_truth(self):
        events=[(40,30,10,1),(41,31,11,-1),(42,32,12,1)]
        result=event_task(events,80,60)
        self.assertEqual(result["central_fraction"],1)
        self.assertEqual(result["on"],2)
        self.assertEqual(result["off"],1)
        self.assertEqual(result["centroid"],[41,31])
    def test_empty_event_task_retains_failure(self):
        result=event_task([],80,60)
        self.assertEqual(result["events"],0)
        self.assertIsNone(result["peak_cell"])
        self.assertIsNone(result["centroid"])
if __name__=="__main__": unittest.main()
