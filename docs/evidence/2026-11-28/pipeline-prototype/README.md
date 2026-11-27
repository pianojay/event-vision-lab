# Pipeline prototype evidence

Recorded on November 28, 2026, on the local Windows notebook. The source revision and canonical LF hashes are embedded in each manifest. Generation happened before publication, so the manifests truthfully record a dirty integration checkout. GPU replay used Godot 4.7.2, Vulkan Mobile, and Intel Iris Plus Graphics. CPU generation uses Python's standard library. These runs measure functional behavior, not throughput.

## Reproduction and retained artifacts

From the repository root:

```powershell
python -B tools/pipeline/validate_pipeline.py --output runs/reproduce-pipeline
python -B tools/pipeline/validate_replay.py --output runs/reproduce-replay
```

The second command requires the shared GPU slot and serializes its Godot processes. Both outputs must be new directories.

- [CPU summary](runs/summary.json) records 15 passing pipeline tests and 15 complete optical-to-capture runs.
- [Replay summary](replay/summary.json) records four successful real-context runs and eight rejected invalid artifacts.
- [Baseline GPU result](baseline/active-lighting-tests.json) preserves the root's pre-change 25/25 sensor check result.
- [Post-change GPU result](baseline-after/active-lighting-tests.json) records another 25/25 sensor checks after implementation.
- [Independent release review](release-qa.md) records source/artifact checks, the decision-log audit, and review limits.
- [Ideal replay screenshot](replay/ideal/replay.png) and [generic replay screenshot](replay/nonideal/replay.png) show emitted event counts.

Each successful run retains its effective configuration, complete manifest, packed optical samples, candidate capture, emitted capture, and ideal truth capture. No referenced optical frames are omitted. The replay validation directories also retain screenshots, reports, and launcher logs. The eight deliberately invalid replay directories retain their altered manifest, event CSV, and failure log.

Git preserves the captured CSV bytes without line-ending normalization so their recorded SHA-256 values survive checkout. Only the repository-root `runs/` directory is ignored; the deliberate run bundles in this evidence directory are retained.

## Exact-area edge timing

The one-pixel edge has dark intensity 1, bright intensity 2, a 10 ms crossing, and ON/OFF thresholds 0.5. Its exact intensity is `I(t)=1+t/10ms` during the crossing. The ideal ON threshold time is `10ms*(exp(0.5)-1)`, about 6.487212707 ms.

| Declared trajectory | Stored ON event | Missing events | Absolute timestamp error |
| --- | --- | --- | --- |
| Exact-area continuous oracle | 6.487213 ms | 0 | 0.293 ns after export quantization |
| Two endpoint samples, log-linear | 7.213475 ms | 0 | 726.262 µs |
| Added 5 ms midpoint sample, log-linear | 6.643045 ms | 0 | 155.832 µs |
| Two endpoint samples, causal left hold | No event | 1 | Not defined |
| 0.1 ms left-held samples | 6.500000 ms | 0 | 12.787 µs |

The causal held adapter passes the left sample to `ReferenceSensor.advance`. It does not pass the future endpoint as though it were present at interval start. The coarse held run therefore remains dark throughout its only interval. The final endpoint does not introduce an extra interval.

One spatial midpoint sample per pixel produces a timestamp around 4.972135 ms in this configuration. Temporal refinement alone cannot remove that spatial integration error. The exact-area fixture isolates the difference.

## Narrow pulse and model comparisons

The pulse rises linearly in intensity from 1 to 2 over 3–4 ms and falls over 4–5 ms. ON/OFF thresholds are 0.2. The exact trajectory has three ON and three OFF events.

| Sampling / reconstruction | Stored events | Missing / extra | Maximum matched timing error |
| --- | --- | --- | --- |
| Uniform endpoints at 0 and 10 ms | 0 | 6 / 0 | Not defined |
| Known pulse boundaries, log-linear | 6 | 0 / 0 | 85.253 µs |
| Exact continuous intensity | 6 | 0 / 0 | 0.302 ns after quantization |

Boundary knowledge restores pulse visibility but does not make log-linear reconstruction exact for a linear-intensity ramp. Matching uses a declared 2 ms gate and reports missing and extra events alongside matched errors.

For the one-pixel generic nonideal edge profile, 1 ms held samples differ from a 10 µs held reference by 475.902 µs. Reducing the interval to 100 µs reduces this difference to 44.882 µs. Each run contains one emitted event. This is a limited same-model sampling comparison, not proof of convergence across all inputs or parity with a camera.

The 32×16 ideal demo records 1,536 emissions. At 160 ms with a 40 ms display window, the real viewer reports 192 visible events on 64 active pixels. The validator independently obtains those counts from integer CSV timestamps. The large-epoch run uses `10^18` ns and produces the same display counts after integer epoch subtraction. The zero-capacity capture produces a blank display with its loss explicitly counted.

The generic 32×16 demo records 1,526 emissions. Its comparison with nominal ideal truth has both missing and extra matches at the 2 ms gate. Count differences and timing shifts reflect the declared response, mismatch, gating, and sampling choices. A complete capture of those emissions does not imply complete physical acquisition.

## Validated boundaries and open gaps

The 15 pipeline tests exercise analytic event times, spatial and temporal aliasing, same-input count errors, in-run resets, independent seeded streams, separate refractory and capture losses, large integer epochs, timestamp quantization, stable event order, serializer rejection, CLI replay of effective configuration, no-overwrite outputs, unsupported mode combinations, resource-bound rejection, positive HDR pulse endpoints, and a long-duration reset endpoint.

The retained component suites add 60 tests: timing 16, sensor 21, rendering 18, and compatibility 5. The root independently ran all 75 tests. The twelve real-context replay checks verify emitted-stage loading, event-window counts, empty captures, integer epoch handling, and rejection of corrupt stage/completeness/epoch/count metadata, invalid metadata types, empty stream identity, and reversed polarity convention. Each successful replay also routes keyboard events through Godot with the Play button focused and checks the visible status/slider for Space resume, autorepeat suppression, Space pause with fixed time, and R restart/resume.

The root's physical interaction check reproduced a focused-button Space double-toggle in the initial implementation. The fix gives Space and R one input owner before GUI dispatch and shares actions with the buttons. A physical retest of the fix was interrupted by the user's Escape stop and was not completed. No further manual UI automation followed. The final control evidence is the routed input checks above.

There is no GPU nonideal acquisition, temporal noise process, leak, readout arbitration, camera calibration, external simulator parity, imported dataset adapter, rich optics, or sustained performance claim. The optical archive is float32 while solver input is binary64 analytic intensity. Replay is event-count visualization, not intensity or geometry reconstruction. Issues #4–#7 remain open.

The [prototype report](../../../development/pipeline-prototype-report.md) maps each open issue to its blocker, the implemented prototype choice, and remaining work.
