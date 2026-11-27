import math
import struct
import unittest
from recorded_input import simulate_frames, compare_events


def f32(x):
    return struct.unpack("<f",struct.pack("<f",x))[0]


def frame(t, values, reset=False, on=0.25, off=0.25):
    params=[0.0]*28
    params[4],params[5]=f32(on),f32(off)
    return t,reset,tuple(f32(x) for x in values),params


class RecordedReferenceTests(unittest.TestCase):
    def test_all_crossings_from_actual_rounded_values(self):
        frames=[frame(0,[1],True),frame(1000,[math.exp(1.1)])]
        events=simulate_frames(frames,1)
        self.assertEqual([e[3] for e in events],[1]*4)
        self.assertEqual([e[2] for e in events],[227,455,682,909])

    def test_reference_really_uses_float_archive(self):
        # This value rounds below the mathematical threshold endpoint.
        value=f32(math.exp(0.5))
        events=simulate_frames([frame(0,[1],True),frame(1_000_000,[value],on=0.5)],1)
        self.assertEqual(events,[])  # Rounded input has not reached the exact threshold.

    def test_reset_preserves_finished_endpoint(self):
        frames=[frame(0,[1],True),frame(1000,[math.exp(1.1)]),frame(1000,[math.exp(1.1)],True),frame(2000,[math.exp(1.1)])]
        self.assertEqual(len(simulate_frames(frames,1)),4)

    def test_pre_floor_zero_silent_and_finite(self):
        self.assertEqual(simulate_frames([frame(0,[0],True),frame(1000,[0])],1),[])

    def test_asymmetric_thresholds_and_signs(self):
        events=simulate_frames([frame(0,[1],True),frame(1000,[math.exp(1.1)],off=0.5),frame(2000,[1],off=0.5)],1)
        self.assertEqual([e[3] for e in events],[1]*4+[-1]*2)

    def test_large_clock_origin_local_offsets(self):
        origin=9_000_000_000_000_000
        events=simulate_frames([frame(origin,[1],True),frame(origin+1000,[math.exp(1.1)])],1)
        self.assertEqual([e[2]-origin for e in events],[227,455,682,909])

    def test_spatial_order_before_quantization(self):
        events=simulate_frames([frame(0,[1,1],True),frame(1,[math.exp(0.26),math.exp(0.51)])],2)
        self.assertEqual([e[0] for e in events],[1,0,1])

    def test_exact_return_after_nine_levels(self):
        initial=f32(math.exp(-3.95))
        events=simulate_frames([frame(0,[initial],True,on=0.2,off=0.2),frame(1000,[math.exp(-2.10)],on=0.2,off=0.2),frame(2000,[initial],on=0.2,off=0.2)],1)
        self.assertEqual([e[3] for e in events],[1]*9+[-1]*9)

    def test_guard_aborts(self):
        with self.assertRaises(OverflowError):
            simulate_frames([frame(0,[1],True),frame(1000,[math.exp(1.1)])],1,limit=3)

    def test_comparison_separates_missing_sign_and_time(self):
        report=compare_events([(0,0,10,1),(0,0,20,-1)],[(0,0,13,1),(0,0,21,1)],2)
        self.assertEqual((report['missing'],report['extra'],report['timestamp_outside_gate']),(1,1,1))
        self.assertFalse(report['passed'])

if __name__=='__main__':
    unittest.main()
