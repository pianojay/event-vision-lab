# Blinded review of emitted-event plots

Observer: gpt6.1sol, AI observer. This is an agent observability inspection, not a human comprehension or usability test.

## Evidence boundary and procedure

Initial observations below were written after viewing trial-01.png through trial-09.png and protocol.json only. No private mapping, scene geometry, optical intensity archive, producer documentation, manifest, or other report was opened. The supplied task identifies the source as integer-pixel emitted events. This review cannot independently establish that provenance from the rendered plots.

Each image has A above B, with 250, 500, and 900 ms columns. Each panel represents a fixed 120 ms window on the same 80 by 60 grid with nearest-neighbor scaling. The display combines ON and OFF counts as grayscale using 1-exp(-0.25*(ON+OFF)). It does not show polarity or timing within a window. Counts are visibly printed in the supplied image headings; they could not be unseen. The initial qualitative observations do not use their numeric values. No separate count metadata was read before this section was saved.

A pattern present at 250 and 900 ms but absent at 500 ms establishes recurrence across these sampled windows, not continuous persistence. A blank panel does not establish the absence of a scene object, its geometry, or its material. No material classes or light directions are inferred.

## Initial visual observations

### Trial 01

- Principal region: A has a narrow clipped patch at the extreme right edge at 250 and 900 ms. Its 500 ms panel is visually almost empty apart from a tiny bottom-edge mark.
- A/B distinction: B contains conspicuous vertical line segments in the interior, approximately left-of-center and right-of-center, plus the right-edge patch. At 500 ms only the right-of-center vertical segment is conspicuous. A lacks these long interior lines.
- Time behavior: B retains a visible interior line at the intermediate time; two separated line segments appear at both outer times. A's edge patch recurs after the sparse intermediate panel.
- Ambiguity/failure: The strongest A feature is clipped by the frame. Neither a complete region outline nor a causal interpretation is recoverable. Tiny edge marks may be difficult to notice.

### Trial 02

- Principal region: Both rows show a compact, roughly rounded central contour, with brighter lower curved boundaries and vertical or streaked interior marks. Small fragments also touch the far right edge.
- A/B distinction: The rows are very similar at this rendering scale. A may have slightly more visible speckling or interior marks, but there is no strong qualitative feature that reliably separates the rows.
- Time behavior: The central contour remains visible at 500 ms but is substantially fainter and less complete, then becomes conspicuous again at 900 ms. Interior detail changes between windows.
- Ambiguity/failure: Similarity of the displayed contours does not establish equality of event streams. The sparse intermediate panel weakens a complete shape reading. No material distinction is supported by visual inspection.

### Trial 03

- Principal region: A rounded central contour appears in both rows, with small peripheral fragments near the left and bottom edges.
- A/B distinction: A has a conspicuous pair of bright interior patches in the upper central portion at 250 and 900 ms. B lacks the same bright pair, retaining mainly the curved contour and vertical interior structure. The distinction at 500 ms is weaker, although A has more scattered interior marks.
- Time behavior: Both rows retain a faint central contour at the intermediate time and return to stronger contours later. A's bright pair recurs at the outer times; it is not equally conspicuous in the intermediate panel.
- Ambiguity/failure: The pair is an event-activity feature rather than evidence of a particular surface or illumination source. Peripheral fragments are incomplete, and the plot loses event polarity.

### Trial 04

- Principal region: A is almost empty in the interior. A horizontal segment lies along the bottom edge at the outer times. B has a centered rectangular patch of repeated vertical and short transverse marks, plus the bottom-edge segment.
- A/B distinction: B's interior striped or grid-like patch is readily distinguishable from A's near-empty interior in all three columns.
- Time behavior: B's central patch remains visible at 500 ms, although fainter and sparser, and is stronger again at 900 ms. A's bottom segment disappears visually at the intermediate time and recurs later.
- Ambiguity/failure: The bottom segment is clipped by the image boundary. Sparse isolated edge pixels do not localize a full region in A. The regular central pattern cannot establish material identity.

### Trial 05

- Principal region: Both rows contain a centered rectangular banded region and a low horizontal strip near the bottom boundary.
- A/B distinction: A's central pattern includes a rounded or hooked left-side outline with a dark interior opening and irregular vertical detail. B's interior feature is a simpler group of nearly straight parallel vertical bands. This geometric appearance separates the rows at the outer times and remains partly visible at 500 ms.
- Time behavior: Both retain central activity at the intermediate time, with lower contrast and fewer visible details. The bottom strip also changes visibility and fragmentation. The broad central differences return clearly at 900 ms.
- Ambiguity/failure: The left-side rounded feature overlaps the banded region in this projection. The lower strip is boundary-adjacent and partly clipped. These windows cannot establish why the patterns differ.

### Trial 06

- Principal region: No active region can be located visually in either row; all six panel interiors appear black.
- A/B distinction: None is visible.
- Time behavior: No visible activity is present in any sampled window.
- Ambiguity/failure: This is a complete localization and discrimination failure for these displays. It does not show whether any scene object exists, nor distinguish inactivity from other upstream causes.

### Trial 07

- Principal region: A has a filled central rectangular region at 250 and 900 ms. B appears blank throughout.
- A/B distinction: The central filled block in A provides a clear distinction at the outer times. Both rows appear blank at 500 ms, so the distinction is unavailable in that window.
- Time behavior: A's region recurs at 900 ms with lower displayed brightness than at 250 ms, after no visible activity at 500 ms. This is not continuous persistence.
- Ambiguity/failure: The filled patch contains little internal structure and cannot identify an underlying texture or material. The intermediate window alone would fail both localization and discrimination.

### Trial 08

- Principal region: A has a broad central rectangular active region interrupted by narrow vertical dark gaps or strips. A separate vertical strip touches the far left edge. B has only that far-left boundary strip at the outer times.
- A/B distinction: A's broad central region clearly separates it from B in all three columns. At 500 ms the A region is darker but still recognizable, while B is visually blank.
- Time behavior: A retains central activity across all sampled windows, with a conspicuous reduction at 500 ms and stronger activity at 900 ms. The left-edge strip is not conspicuous at 500 ms in either row, then recurs at 900 ms.
- Ambiguity/failure: B does not provide an interior region to localize. Its remaining feature is clipped at the boundary. The narrow central gaps do not establish physical geometry or optical causes.

### Trial 09

- Principal region: Both rows have a small left-of-center, vertically elongated patch at 250 and 900 ms. It is well inside the panel but close to its left side. Both intermediate panels appear blank.
- A/B distinction: The patches look essentially the same in position, outline, and brightness at this scale. No reliable visual discriminator is apparent.
- Time behavior: The small patch recurs more faintly at 900 ms after disappearing visually at 500 ms. Continuous persistence is not established.
- Ambiguity/failure: Localization is limited to a small fragment. It does not reveal a complete region or establish the equivalence of the underlying streams. A/B discrimination fails on these plots.

## Scope of inference

The strongest visible A/B differences are the interior line structure in trial 01, the paired interior patches in trial 03, the central patch in trial 04, the internal band/outline pattern in trial 05, and the presence of broad central regions in trials 07 and 08. Trial 02 offers weak visual separation, trial 09 offers no reliable visual separation, and trial 06 offers neither localization nor separation. These are qualitative observations from these particular event windows. They do not score material recognition, establish physical fidelity, or demonstrate human understanding.

## Post-observation metadata check

The allowed ledger was read only after the initial observations were saved. It contains 54 entries covering nine trials, two rows, and three cursor times. The table reports its event counts in 250 / 500 / 900 ms order. These counts support the observed reductions at the middle time and the zero-activity cases; they do not supply spatial interpretation.

| Trial | A event counts | B event counts |
| --- | --- | --- |
| trial-01 | 155 / 6 / 178 | 393 / 108 / 416 |
| trial-02 | 2562 / 762 / 2336 | 2413 / 717 / 2202 |
| trial-03 | 2728 / 787 / 2516 | 2348 / 679 / 2120 |
| trial-04 | 136 / 1 / 69 | 876 / 181 / 759 |
| trial-05 | 1498 / 430 / 1378 | 1604 / 494 / 1502 |
| trial-06 | 0 / 0 / 0 | 0 / 0 / 0 |
| trial-07 | 2312 / 0 / 1156 | 0 / 0 / 0 |
| trial-08 | 4828 / 1020 / 3978 | 204 / 0 / 102 |
| trial-09 | 112 / 0 / 56 | 112 / 0 / 56 |

Every row has a single repeated event_sha256 value across its three cursor windows. A and B carry different ledger hash values in every trial, including trial 06 (all sampled windows empty) and trial 09 (equal sampled counts). The ledger therefore labels different row inputs; equal visual appearance or sampled counts do not establish identical source inputs. Hashes were inspected as metadata fields only. Underlying source files were not opened or rehashed, and the scope of the hashed content is not established by this inspection.

The private mapping remains unopened. Initial observations above were not revised after the ledger check.

