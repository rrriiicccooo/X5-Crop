# X5 Crop User Guide

- Active development: **V4.9 bounded safe crop**
- Stable release: **v4.2.8**

X5 Crop conservatively crops Hasselblad / Imacon X5 holder-scan TIFFs. You
supply the film format; the program uses holder scale and count constraints to
measure four photo edges in source coordinates, reconstruct polygons, and write
individual TIFFs when the safety contract is satisfied.

## Product Goal

Success means not cutting real photo content, not uniquely measuring the true
physical boundary:

- `approved_auto` means the final protected output satisfies the bounded safety
  contract.
- Outputs may be larger than the photo, overlap, or contain a small part of a
  neighboring photo.
- A blank slot, named inference, missing visible separator, or multiple
  protection-equivalent geometries does not by itself require review.
- `needs_review` is reserved for a concrete risk that cannot be absorbed, such
  as unresolved ordinal or primary-slot ownership, possible inward loss of
  known content, geometry outside source/lane authority, or no common observed
  rotation interval.
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
- Auto uniquely matches the scan canvas, then writes every valid slot for the
  current format in that holder. It does not infer or claim the true photo
  count.
- A filename annotation such as `X5_<count>` may be used by validation only. It
  never enters detector, prior, score, Gate, or runtime selection.

Partial slot count describes holder capacity or an explicit user request, not
the number of visible photos. Leading, trailing, and internal blank slots remain
in the sequence. `135-dual` first matches the complete canvas and then creates
two canonical lanes; output order is `lane:0/1..6` followed by
`lane:1/1..6`. Each output records both global and lane-local identity.

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

`--layout auto` is the default. Parallelism defaults to `--jobs 2`; a normal run
may explicitly request up to three workers, while diagnostics may use up to
four. `--jobs 3` is intended for machines with sufficient memory and batches of
at least three TIFFs. It increases peak memory pressure, so it is not the
default. Formal performance certification remains fixed at `--jobs 2`.

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
Pixel observations, physical constraints, and search proposals have distinct
authority:

- two-dimensional pixel measurement creates transitions, fitted lines,
  support, residuals, angles, and measurement uncertainty;
- format, count, scale, the typed `±0.5 mm` aperture tolerance, lane, and
  adjacency only filter or infer geometry;
- Grid, outer, and corridors only bound query domains and order; they never
  become photo edges.

Top/bottom are measured in narrow ScanCanvas/format corridors with complete
halos; each frame retains its own intercept, support, and uncertainty.
Start/end discovery uses seamless tiles covering the entire allowed
translation interval. Any internal or trailing observed edge may anchor the
sequence in either direction, so outer does not have to find the first photo.
Content only assists ownership and containment.

Each non-empty photo becomes a source-coordinate polygon. Candidates are
physically joined into complete `FrameGeometryState` objects before deduplication
and dominance. More than two observed non-dominated states becomes unresolved
before truncation. Ordered DP retains at most two observed states plus one
model-only/blank state per frame and never enumerates auto occupancy.

A photo safety envelope adds, in order:

1. measurement or inference uncertainty;
2. a one-source-pixel interpolation allowance;
3. fixed millimetre protection;
4. source/lane clipping.

Partial-auto empty slots use separate `grid_inferred_blank` geometry and never
pretend to be photo observations. Deskew comes only from the common angle
interval of selected observed top/bottom lines: identity requires shared
zero-angle evidence; otherwise an observed rotation up to `2°` is used. Each
approved ROI is sampled once from the original TIFF through inverse affine.

## Gate, Status, And Reasons

`CandidateGate` records exactly ten ordered candidate facts:

```text
scan_canvas_authority
source_content_measurement
grid_search_coverage
output_slot_count
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
- `requested_count_unfulfilled` for fixed/explicit input
- `capacity_output_slot_count_unfulfilled` for auto
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
  _debug_analysis/
  needs_review/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

Optional outputs:

- `--report` writes current JSONL and CSV.
- `--debug-analysis` writes a four-layer JPG under `_debug_analysis/`: source
  and lane authority; pixel measurements and selected observed lines; selected
  source photo geometry; and protected product output. Review candidates are
  audit-only and explicitly marked `NOT EXPORTABLE`.
- `--diagnostics` is read-only. It enables report and Debug Analysis and
  disables review copies. It preserves the same DecisionGate result and final
  boxes but writes no frame TIFF.
- `--no-copy-review-files` disables source copies for review cases.

Current report:

```text
schema_id       = detection_report
schema_revision = source_coordinate_photo_geometry_v1
```

The report stores count policy, selected profile, measurement coverage, search
proposals, global and lane-local slot identities, observed/inferred provenance,
complete states and competition evidence, both translation assessments,
query/DP/memory receipts, safe/protected envelopes, both Gates, transform,
final boxes, and TIFF-fidelity receipts. Full raw transitions and content
components/row runs are represented by complete coverage, counts, and
a canonical row-run digest plus component derivation rather than expanded
record lists; selected observations and complete candidate states remain
auditable. It is an audit artifact, not a cache.

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
user-confirmed geometry, expanded into 14 fixed/explicit/auto scenarios. Eight
nominal samples may freeze parameters and must pass final acceptance. S098 must
pass safety acceptance but is excluded from nominal calibration. Approved
scenarios require complete confirmed-polygon containment, zero inward loss,
recalculable extra area, and official TIFF readback. S055 review scenarios must
retain both a gold-safe state and a physically feasible, protection-distinct
competitor while producing zero official TIFFs.

The 111-source cohort is `diagnostic_unreviewed` and produces no accuracy
verdict. Filename `pass/unknown` labels and filename counts create no
expectation. Every record must terminate, but only crashes, hangs, invalid
schemas, consumption of incomplete queries, unbounded query/DP/memory work,
damaged official TIFFs, or source/lane authority escape block engineering
acceptance.
The per-input temporary-memory bound is linear:
`10 * source_pixels + 32 MiB`.

Formal performance uses 24 fixed real TIFFs, `--jobs 2`, and 168
status-independent I/O tasks. Each version completes native detection/decision,
then runs the same frozen sampling/write/readback workload; review candidates
are never exported. V4.9's three paired total-wall groups must have a median
`<=5.0 seconds/input` and beat the frozen V4.2.8 commit beyond the MAD noise
floor.

`real_holdout = unavailable`. Uncovered XPan and 120-645 cells have only
physical-rule and synthetic-contract coverage and do not cause runtime review.

## Remove And License

Delete the X5 Crop folder to remove the program and its local outputs. Installed
Python packages may be shared with other programs, so X5 Crop does not include
a bulk dependency uninstaller.

License: MIT. The release root includes `LICENSE`; the
[full text](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE) is also
available on GitHub.
