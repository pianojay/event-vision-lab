# Blinded event-only pulse review

Observer: AI GPT-6.1 Sol. This is an AI visual inspection, not a human comprehension test.

## Initial observations recorded before ledger access

Inputs inspected were only pulse-01.png, pulse-02.png, and pulse-03.png. Each panel has conditions A and B in rows and 300, 375, and 900 ms columns. The supplied protocol declares a fixed 120 ms event window, gain 0.25, and a grayscale ON+OFF display. The declared source-off time is 350 ms. Thus the 375 ms window brackets that change; the source-off time is stimulus metadata, not an optical-truth input. The previous experiment whose windows missed the transition remains a separate retained result.

The visible headings include numerical event counts. This inspection is blinded to the private source mapping, but is not blinded to numerical counts. The statements below distinguish visible spatial patterns from those headings.

### pulse-01

- At 300 and 900 ms, all A and B tiles appear black. The headings report zero events.
- At 375 ms, both conditions show the same broad spatial pattern: a bright central square and a short bright horizontal strip touching the bottom edge of the tile. The central square lies roughly from 29% to 71% of the tile width and from 22% to 79% of its height.
- Both central squares and lower strips appear saturated white. I cannot visually establish a brightness difference between A and B. The headings report more events for B at the transition, so the displayed pattern alone loses that count distinction.
- The bottom-edge strip is clipped by the tile boundary. Its full spatial extent cannot be recovered from this view.

### pulse-02

- A has a central square at all three times. It is visibly lighter at 300 ms and darker at 375 and 900 ms. The two later squares appear similar in brightness and extent.
- B appears black at all three times. Thus the persistent central activity in A distinguishes the conditions before, across, and after the declared source-off time.
- No new spatial structure is visible at 375 ms. A darker square at 375 ms does not by itself show whether the window contains a brief transition burst, fewer repeated events, or a change in polarity balance.

### pulse-03

- At 300 ms, A and B have the same narrow gray vertical region near the left side of the tile, with a slightly stepped upper edge. At 900 ms, both retain a dimmer region in approximately the same place. The rest of these tiles appears black.
- At 375 ms, both rows have a much brighter narrow vertical structure near the left side, a short horizontal line near the lower middle, and a tiny bright mark at the top edge. The gray region immediately to the left of the bright vertical structure remains visible.
- A additionally has a conspicuous irregular bright patch in the upper middle. B has no comparable patch there. This is a visible transition-window difference beyond a uniform brightness change.
- The bright vertical structures have similar placement but their precise widths and intensities are hard to compare because much of each is white. The tiny top-edge mark is clipped, so its complete shape is unknown.

### Interpretation limits

The three examples provide different event signatures: a transition-only shared shape with a heading-count difference, persistent A-only activity, and a transition-specific extra region in A over otherwise similar before/late patterns. These are observations of emitted-event displays. They do not identify material class, lighting direction, geometry, optical intensity, or the mechanism producing any difference.

The grayscale sum hides ON/OFF polarity and does not reveal event ordering within each 120 ms window. Brightness clipping obscures event-density differences. Black regions establish only that no activity is visible at this display setting; a claim of exact zero needs the ledger or the exposed count heading. Equal before/late images do not prove equal signals outside the sampled windows. No private source map, producer documentation, geometry, optical truth, manifest, or other observation report was accessed.

## Ledger verification

After saving the initial observations, I read event-input-ledger.json. Its counts agree with the visible headings in all 18 tiles.

| Trial | A counts at 300 / 375 / 900 ms | B counts at 300 / 375 / 900 ms |
| --- | --- | --- |
| pulse-01 | 0 / 46,344 / 0 | 0 / 64,697 / 0 |
| pulse-02 | 2,312 / 1,156 / 1,156 | 0 / 0 / 0 |
| pulse-03 | 112 / 7,798 / 56 | 112 / 5,068 / 56 |

The ledger repeats one event SHA-256 for each trial/row across the three cursor times. The six recorded source hashes are distinct. These are ledger provenance labels, not independent file-integrity checks. I did not open the underlying event files or recompute their hashes.

| Trial/row | Ledger event SHA-256 |
| --- | --- |
| pulse-01 A | 1d01bf9102f7329185f2ae7e3680a6b146258a79a20be584f0afdbf444ba4a69 |
| pulse-01 B | 749868d9507c0153da25ef42b6f597799b0e00160445497faf33a8700bcd5e17 |
| pulse-02 A | 078e463bab341b625f04a757be808a1f62a4f2293e68c74eab70806a107de5f9 |
| pulse-02 B | 75072856b113465865c614bee77cb84977058aff4b01e07b1a6c244517c751ca |
| pulse-03 A | cb991f36d4a6aeb181b51650ccaa44b07412aeee699b625c24dc8b0658fd5aac |
| pulse-03 B | c44f6c8b576c85b04a759772b9de27a7ef9163d88c5c6789e050325ae5394c8e |

The ledger confirms exact zero counts in pulse-01 before/late and pulse-02 B at the sampled windows. It does not remove the spatial, saturation, polarity, timing, or causal ambiguities noted above.

