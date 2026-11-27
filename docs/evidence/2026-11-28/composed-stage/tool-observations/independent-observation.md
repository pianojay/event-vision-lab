# Independent event-only observation

Observer is an AI agent, not a human participant. This is a qualitative image reading, not a user comprehension test. Initial observations below were written after viewing only `same-capture-tools.png` and the supplied panel settings, before opening capture metadata, producer documentation, intensity images, or scene geometry.

## Blinded visual observations

All panels show activity in a small central region against black. The 10 ms row shows two isolated dim marks, without enough connected evidence for a contour. Coarser count bins make the marks larger and easier to locate, but do not reveal a coherent boundary. The 4x4 per-pixel version is extremely faint at the fixed gain.

The 40 ms row contains a small, broken cluster. At 1x1, several separated marks suggest a short near-vertical run with adjacent offsets. This is a candidate fragment rather than a closed or recognizable outline. The 2x2 and 4x4 count panels make the cluster more conspicuous while combining some distinct marks into larger blocks. The 4x4 per-pixel panel retains much less visible contrast, with parts barely distinguishable from the background.

The 160 ms row reveals two strong, roughly parallel vertical strokes. A weaker broken arc or bulging contour appears to their right, with a short weaker fragment to their left. At 1x1, the thin strokes and the individual offsets on the right can be distinguished. At 2x2, the right fragment is more connected but blockier. At 4x4 count, the large blocks obscure smaller gaps and nearby structures begin to merge into a broad bright region. The 4x4 per-pixel panel reduces brightness and differentiates the strong strokes from weaker adjacent activity, but remains spatially coarse.

Across rows, increasing the integration interval changes visibility from sparse marks to a more coherent candidate contour. It also accumulates additional spatial traces. A single still does not establish whether these traces are motion trails, distinct boundaries, repeated events, or some combination. There is little distributed background clutter in these particular panels, so they do not establish clutter robustness. More visible and thicker does not mean more accurate.

The image alone cannot establish object identity, geometry, material, optical brightness, motion direction or speed, sensor calibration, event correctness, detection accuracy, or how a human user would understand the result. A dark region cannot be interpreted as an absent object. The contour is a pattern of accumulated activity, not verified optical truth.

## Panel labels transcribed before metadata inspection

| Interval | Events in every column | Active bins 1x1 / 2x2 / 4x4 count / 4x4 per-pixel |
| --- | ---: | --- |
| 10 ms | 2 | 2 / 2 / 2 / 2 |
| 40 ms | 36 | 11 / 6 / 5 / 5 |
| 160 ms | 1148 | 80 / 44 / 20 / 20 |

These are displayed label counts, not an independent recount at this stage. All panels use a cursor of 500 ms and fixed gain 0.5.

## Event metadata checks after the blinded observations

The following checks use `same-capture-tools.json` and the retained `events.csv` only. No manifest contents, optical intensity, geometry, or producer documentation was read. These are deterministic checks of one retained capture, not runtime or sensor performance measurements.

The CSV has 5,787 emitted-event rows. Its independently computed SHA256 is `b0852a486cb23c36977e6556d686448c8de6f3f469b526ae752d9b1a1639e2b1`, which matches `source_event_sha256`. Metadata also states `raw_unchanged = true`. This establishes a match to the recorded hash at inspection time. It is not an independent before-and-after production audit.

At the 500 ms cursor, 3,807 events have arrived. The window selects 2 events at 10 ms, 36 at 40 ms, and 1,148 at 160 ms. Their ON/OFF totals are respectively 0/2, 24/12, and 554/594. The 5,787 retained count includes events after the cursor. It must not be confused with the number visible in one integration window.

For all 12 bin/window snapshots, an independent sum of the ON and OFF arrays equals `visible_count`. Independently summing each 1x1 array into 2x2 and 4x4 bins exactly reproduces the corresponding arrays. Count and per-pixel configurations retain identical raw ON/OFF arrays. Their brightness difference therefore comes after event selection and accumulation. Every 4x4 bin has area 16 pixels in this full-frame example. The panel comparison demonstrates a display-normalization tradeoff, not increased event sensitivity.

For all 21 snapshots, direct filtering of the raw CSV reproduces the recorded received, incoming, ROI, selected, and visible counts. The check uses timestamps in `(cursor - window, cursor]` and half-open ROI bounds. These data do not test an event exactly on every boundary, so the successful recount alone does not prove the implementation's general boundary convention.

### ROI and polarity counts at 160 ms

| ROI | Polarity | Incoming | After ROI | Selected before window | Visible in window | Active bins |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [0, 0, 80, 60] | Both | 3807 | 3807 | 3807 | 1148 | 80 |
| [0, 0, 80, 60] | ON | 3807 | 3807 | 1861 | 554 | 34 |
| [0, 0, 80, 60] | OFF | 3807 | 3807 | 1946 | 594 | 49 |
| [16, 12, 64, 48] | Both | 3807 | 3807 | 3807 | 1148 | 80 |
| [16, 12, 64, 48] | ON | 3807 | 3807 | 1861 | 554 | 34 |
| [16, 12, 64, 48] | OFF | 3807 | 3807 | 1946 | 594 | 49 |
| [0, 0, 0, 0] | Both | 3807 | 0 | 0 | 0 | 0 |
| [0, 0, 0, 0] | ON | 3807 | 0 | 0 | 0 | 0 |
| [0, 0, 0, 0] | OFF | 3807 | 0 | 0 | 0 | 0 |

The central ROI retains every arrived event in this capture. It demonstrates selection without losing the observed activity, but supplies no evidence of background-clutter rejection. The empty ROI removes everything from the view while preserving the incoming counter. This makes the difference between no arrivals and a view that excludes arrivals inspectable.

The ON and OFF windows sum to the both-polarity count, 554 + 594 = 1148. Their active-bin totals sum to 83 while the union has 80, so 3 pixels contain both polarities during this interval. A single-polarity view separates sign contributions but omits roughly half the window's events here. No separate polarity image was inspected, so this report makes no visual claim about which contour fragments each sign reveals.

## Practical usefulness and limits

This capture supports using a longer integration window to inspect spatial coherence that a sparse short window hides. Coarse count bins make small activity patches more conspicuous and trade spatial precision for that visibility. The unchanged event totals prevent mistaking that display choice for more events. A per-pixel view makes count density more comparable across bin sizes but can hide sparse activity at this gain. ROI and polarity counters expose evidence excluded by view settings.

The same evidence does not establish object reconstruction, geometry or material classification, motion estimation, human comprehension, or robustness in clutter. Two strong accumulated strokes are observable. Their physical cause remains unverified. Only one capture and one cursor were examined.

The Prove It Works principle led to inspecting the actual image and recounting retained event arrays and CSV rows. Explain the Number led to separating retained, arrived, selected, and visible event counts, and limiting the findings to this single capture.
