# X5 Crop User Guide

- Active development: **V4.9 bounded safe crop**
- Stable release: **v4.2.8**

X5 Crop conservatively crops Hasselblad / Imacon X5 holder-scan TIFFs. You
supply the film format; the program builds frames within holder capacity, a
bounded Grid search, and outward safety envelopes, then writes individual TIFFs
when the safety contract is satisfied.

## Product Goal

Success means not cutting real photo content, not uniquely measuring the true
physical boundary:

- `approved_auto` means the final protected output satisfies the bounded safety
  contract.
- Outputs may be larger than the photo, overlap, or contain a small part of a
  neighboring photo.
- A missing separator, blank slot, inferred Grid, equivalent geometry, no
  deskew, or protection saturated at an authority boundary does not by itself
  require review.
- `needs_review` is reserved for a concrete risk that cannot be absorbed, such
  as competing counts, unresolved ordinal or primary-slot ownership, possible
  inward loss of known content, or geometry outside source/lane authority.
- Read, write, and read-back errors are terminal failures, not review results.

## Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive. Unzip it and run the installer once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer checks `numpy`, `tifffile`, `imagecodecs`, and `Pillow`. On macOS
it prepares only the current Release folder and does not establish system-wide
trust.

Keep the entry script, launcher, and TIFF scans in the same folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

If macOS blocks double-click launch, run this in the folder:

```bash
/bin/bash X5_Crop_Mac.command
```

## Formats, Modes, And Count

| Input | Format | Full count | Partial |
|---|---|---:|---|
| Return / `135` | 135 | 6 | 1..6 or auto |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 | unsupported |
| `half` | half-frame | 12 | 1..12 or auto |
| `xpan` | XPan | 3 | 1..3 or auto |
| `645` | 120-645 | 4 | 1..4 or auto |
| `66` | 120-66 | 3 | 1..3 or auto |
| `67` | 120-67 | 3 | 1..3 or auto |

Format always comes from the user; runtime never guesses it.

There is one count mapping:

- Full normalizes to `fixed_full`. An explicit count is accepted only when it
  equals the format default.
- A partial integer is an authoritative `explicit` count.
- Omitting partial CLI `--count`, passing `--count auto`, or pressing Return in
  the interactive prompt selects `auto`.
- There is no separate `--auto-count` option.
- Auto searches only `1..default_count`, then removes counts that exceed the
  uniquely matched holder capacity.
- A filename annotation such as `X5_<count>` may be used by validation only. It
  never enters detector, prior, score, Gate, or runtime selection.

A partial count describes complete design slots, not a partial photograph.
Blank slots remain in the sequence. `135-dual` first matches the complete canvas
and then creates two canonical lanes; output order is top lane 1..6 followed by
bottom lane 1..6.

## Run

Normal:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial explicit:

```bash
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
```

Partial auto:

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
```

For a vertical strip:

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

`--layout auto` is the default. The default is `--jobs 2`; normal runs use at
most two workers and diagnostics at most four.

```bash
python3 X5_Crop.py --help
```

## Detection And Safety Envelopes

Each TIFF produces one base-gray image and one image-statistics measurement.
Scan-canvas candidates are filtered by format and capacity, then pixel aspect
must identify one unique profile; the detector never chooses a nearest profile.
`ScanCanvasEvidence` owns independent long/short px/mm intervals. TIFF DPI/PPI
is output metadata only.

Current holder catalog:

| Profile | Physical size | Format fit and maximum count |
|---|---:|---|
| `135_standard` | `232 × 32.22 mm` | 135 ≤ 6; half ≤ 12; XPan ≤ 3 |
| `135_narrow` | `232 × 25.4 mm` | 135 ≤ 6; half ≤ 12; XPan ≤ 3 |
| `135_dual` | `232 × 63.44 mm` | 135-dual ≤ 12 |
| `120_standard` | `226 × 60 mm` | 645 ≤ 4; 66 ≤ 3; 67 ≤ 3 |
| `120_wide_224_5` | `224.5 × 63.44 mm` | 645 ≤ 4; 66 ≤ 3; 67 ≤ 3 |
| `120_wide_223` | `223 × 63.44 mm` | 645 ≤ 4; 66 ≤ 3; 67 ≤ 3 |
| `120_wide_188_5` | `188.5 × 63.44 mm` | 645 ≤ 4; 66 ≤ 3; 67 ≤ 2 |

Separator measurement and positive-content measurement are independent.
Observed bands, edge pairs, learned one-sided observations, and model-only
corridors may all participate in bounded proposals. A prior constrains search;
it never becomes a physical observation.

Every proposal creates exactly count lane-local slots. A bounded shared interval
from contact or overlap is included in both adjacent safety envelopes. The full
authoritative lane is retained on the short axis by default. Fixed millimetre
protection is then rounded outward using the upper endpoint of each independent
scale interval. Only this protection step may saturate at a source/lane edge.

The current output transform is typed identity. No advanced fit or deskew is
added without a named gap, and the absence of deskew does not cause review.
Selected count, transform, and boxes cannot change after DecisionGate.

## Gate, Status, And Reasons

`CandidateGate` records exactly ten ordered candidate facts:

```text
scan_canvas_authority
source_content_measurement
grid_search_coverage
frame_count
slot_ordinal_assignment
slot_ownership
known_content_containment
source_lane_geometry
output_protection
output_transform
```

Only `DecisionGate` creates `approved_auto`, `needs_review`, and typed reasons.
Common review reasons include:

- `scan_canvas_authority_unavailable`
- `automatic_count_unresolved` or `requested_count_unfulfilled`
- `grid_search_coverage_outcome_risk`
- `slot_ordinal_assignment_unresolved`
- `slot_ownership_unbounded`
- `known_content_containment_unbounded`
- `source_lane_geometry_invalid`
- `output_protection_unavailable`
- `output_transform_unavailable`

## Output, Reports, And Diagnostics

An ordinary approved run may create:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  ...
  _debug/
  _debug_analysis/
  needs_review/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

Optional outputs:

- `--report` writes current JSONL and CSV.
- `--debug` writes a lightweight separator, Grid, and crop preview.
- `--debug-analysis` writes a source, measurement, Grid, Gate, and output
  summary.
- `--diagnostics` is read-only. It enables report and Debug Analysis and
  disables review copies. It preserves the same DecisionGate result and final
  boxes but writes no frame TIFF.
- `--no-copy-review-files` disables source copies for review cases.

Current report:

```text
schema_id       = detection_report
schema_revision = bounded_safe_crop_grid
```

The report stores the count request and candidate range, selected count,
calibration receipt ID, observed/inferred provenance, per-count/lane/component
work, dominance, slots and interactions, safe and protected envelopes, both
Gates, transform, final boxes, and TIFF-fidelity receipt. A report is an audit
artifact, not a detection cache.

## TIFF Fidelity And Errors

The source TIFF is never modified. Each approved ROI is sampled from the source
once, then immediately written and read back. Validation checks:

- dtype, axes, shape, and channel structure;
- Photometric, BitsPerSample, SampleFormat, and planar configuration;
- ICC profile/color space;
- resolution and resolution unit;
- description, datetime, software, and supported metadata tags;
- pixel equality;
- `same` preserves known lossless source compression such as NONE/LZW, while
  `none` writes an uncompressed TIFF.

A read, write, atomic-replace, or read-back error records an independent
`FailedInput` and terminal stage. It never rewrites DecisionGate or creates a
success receipt.

## Validation Boundaries

Accuracy completion currently uses only nine source-SHA-bound samples with
user-confirmed geometry, expanded into 14 fixed/explicit/auto scenarios.
Containment checks only whether the inverse-transformed output source footprint
fully contains each confirmed polygon; larger and overlapping outputs are
allowed.

The 111-record manifest is a non-blocking coverage audit. Duplicate SHA groups
are listed separately, and record count is never presented as independent
real-sample count. `real_holdout = unavailable`; cells without real samples,
including XPan and 120-645, report
`real_sample_coverage = unavailable` without causing review.

Formal performance uses a fixed 24-real-TIFF cohort, `--jobs 2`, and one empty
output root containing `cold` plus `measured-1/2/3`. Every run writes and reads
back frame TIFFs. Certification uses only the three measured runs and requires
their median to be `<= 5.0 seconds/input`.

## Uninstall And License

Delete the X5 Crop folder to remove the program and its local outputs.
Uninstallers remove user-level Python dependencies, not Python itself:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

License: MIT. See
[GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE).
