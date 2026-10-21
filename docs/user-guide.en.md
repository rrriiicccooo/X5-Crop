# X5 Crop V5 User Guide (Development Preview)

- Scope: unreleased V5 source on repository `main`
- Current public stable release: v4.2.8; its commands and behavior differ, so use the documentation bundled with it
- Intended input: Hasselblad / Imacon X5 holder scans whose format and exposure-slot count are already known

## Product Behavior

X5 Crop uses a known format's design-size prior to establish a bounded physical template for each source; it is not a
general-purpose photo-boundary recognizer. Official TIFFs are written only when every slot in the source has a directly
usable crop that meets the current safety rules. Otherwise the entire source becomes `needs_review`; individual slots
are never salvaged.

Cropping protects photograph content already visible in the input TIFF. Image content hidden by the holder and absent
from the TIFF is outside the recovery scope. Visible content, including tilted corners, must be retained.

### Format and Count

Format is always required. Count may be omitted or explicit:

- omit `--count` to confirm the matched holder's default complete count;
- use `--count N` to confirm exactly N slots, including intermediate blank exposures;
- count must be positive and no greater than the matched-holder capacity;
- `135-dual` is automatic only at 12 slots, six per lane; every other count enters review.

Default complete counts are 135=6, half=12, XPan=3, 120-645=4, and 120-66=3. 120-67 uses 3 on an ordinary holder
and 2 on the short holder. 135-dual uses 12 total.

V5 applies the same physical and safety contract to every format. Current development gold has no real gold source for
`xpan`, `120-645`, or `135-dual`, so these formats are implemented by the Runtime without real-sample accuracy
coverage. They receive neither a special disable rule nor a looser acceptance rule.

The program never infers format or real photo count from filenames, picture content, holder capacity, or blank slots. It
does not remove, merge, or reorder blank slots. V5 has no full/partial mode.

### Automatic Approval and Review

The program builds a physical template with a common W/H from the supplied format/count, then locates it using whole-strip
and local-edge evidence. Directly observed photo boundaries retain their native coordinates. Missing boundaries may be
inferred only from established common dimensions, position anchors, and checked adjacency relations. Aspect-ratio
information or outer support may help locate the crop, but cannot impersonate a direct photo boundary or override
counterevidence.

When the allowed common-width interval narrows, inferred boundaries use the updated range. Placement ambiguity and
competing interpretations still require every safety check.
Position anchors, common width, and pitch vary together while retaining the complete measurement ranges of direct
boundaries. Distinct legal contact or overlap interpretations still require review; more local support alone does not
exclude another interpretation. When position or contact relations remain ambiguous, each interpretation keeps its own
native boundaries and allowed position ranges for review.
Reports retain direct-boundary proposals, calibrated-template proposals, and diagnostic proposals blocked by evidence,
with each proposal's geometric basis and unresolved reason. Counterevidence remains attached to diagnostic proposals,
which still require manual review.
The primary and retained competing interpretation each check their own boundaries and relations between adjacent photos.
Reports show evidence for registered partners and physical conflicts. Incomplete coverage of competing interpretations
requires manual review; fitting two proposals into one window alone does not qualify the result for automatic output.
Reports retain all competing members from each positioning stage and check each member's own width, height,
top/bottom association, and protection budget. Members with missing qualification evidence remain in the set;
when prerequisites are unmet, their evidence remains and output geometry and budget are explicitly marked unevaluated.
Registered adjacency relations are jointly checked against each member's original boundaries. Missing independent
facts or an inability to preserve the original boundary assignments require manual review.
Reports retain separate proofs for actual native-to-template boundary associations and original/current range admission.
Classification as clipping at a true source edge does not automatically grant range admission.
Reports list the native pairs and measured adjacencies used in joint validation, roles lacking qualification,
and the original observation, when present, for each model coordinate outside the admitted range.
When a calibrated template has not been established, reports still list the original positioning anchors and their
qualification gaps. Raw observations with incomplete associations continue to require manual review.
Original complete-photo boundaries independently accepted by every interpretation can establish common dimensions;
each interpretation retains its own dimension ranges and protection requirements. Reports distinguish a positioning
stage's common window from the complete historical set. Passing some stages still requires manual review.
For overlapping photos, top/bottom support is partitioned at the native boundaries and checked against the proven overlap range.
Manual review continues until the complete set has a compliant window under the same fixed dimensions.

Acceptance concerns the final crops: correct slot correspondence, no missing or duplicate photos, full protection of
confirmed content, and compliance with fixed dimensions, source bounds, and risk budgets. Internal boundary names need
not match human labels. For touching photos, one physical boundary may end the previous slot and start the next while
anchoring their common template. It remains one physical observation.
Every slot still needs sufficient position and protection evidence. The entire source enters `needs_review` if content
is missing, an internal boundary is crossed, necessary evidence is absent, or a competing interpretation cannot be fully
verified and protected. A score cannot replace these conditions or enlarge the fixed box.
The program checks complete separator material already identified in the scan. An interpretation is rejected if it
omits the other side of that material and thereby requires a photo wider than the format's physical upper limit.
Other interpretations must independently pass every safety check.

When photo ownership is established and several complete top/bottom interpretations remain, one fixed box may protect
them all. Automatic approval requires every interpretation to pass content containment and source-wide safety checks.
Touching or overlapping photos use the same checks and remain in review when evidence is insufficient.

Development reports retain the original material bands and boundary sources behind outer-material candidates.
Photo ordinals and the true first and last boundaries still require independent evidence.

Separator material is checked for adjacency using the actual coordinates on each scan line. A line with an intervening
boundary does not support the outer pair. Local and source-wide separator relationships are checked separately; relations
with insufficient evidence remain subject to review.

Debug Analysis shows the primary, runner, and retained proposals with their evidence, coverage results, and blocking
reasons for inspection. Reports preserve the original evidence and failure reason for each displayed interpretation;
displaying one does not grant crop or automatic-output authority. The current Runtime does not use development ranking
scores to select crops.

Holder fill is assessed only after placement by asking whether another W fits beyond either outer. It never searches for
or centers a placement. Both lanes of 135-dual must be complete.

## Fixed Source-Space Window, Content Protection, and Deskew

Each source TIFF uses one common W/H size. Every Frame requests one fixed window:

```text
source-space window = 1.1W × 1.1H
per-side margin = 5%
```

The fixed box permits the script to select a position only; measurement, residual, direction, or score cannot change
its size. It must contain all visible TIFF content, including tilted corners. When credible evidence requires a complete
physical envelope that cannot fit inside the fixed box, the whole source enters `needs_review`. An offset within the
fixed box is not independently rejected when all visible photograph content remains protected.

When independent evidence uniquely establishes both photo edges, the program uses those coordinates to choose the fixed
box position rather than replacing the measured height with an inferred height inside the frame. Continuous outer support
can provide position evidence only when the credible complete physical envelope fits in the fixed box; local support does
not authorize extrapolating the whole strip, and calibration does not turn support into a photo boundary. Missing,
conflicting, or unresolved evidence still requires Review.

A true TIFF edge may be source-clipped, and the report records that fact. Edge clipping is limited to source pixels that
actually exist; it never expands or shrinks an internal photo boundary. Crossing an internal lane or other authority
boundary still enters review and cannot be bypassed by shrinking the window. The fixed box cannot be enlarged by taking a
union.

Two-dimensional content is a conservative veto on the final fixed box: reliable content crossing its boundary blocks
automatic output, while an in-box offset does not independently move the position. When one edge and the common width
infer the opposite edge, the complete allowed position range is used to select the fixed box; the window is not shrunk and
content protection is not bypassed. Local boundaries with established coordinate support remain available when weak
boundaries are reassessed.

Deskew is optional cleanup after automatic approval and never participates in detection or the Gate. `--deskew auto`
rotates only when both sides support one stable small angle; missing, conflicting, or excessive evidence preserves the
source orientation. `--deskew off` skips observation. When rotation is applied, the source and already-safe polygons use
the same affine transform before an axis-aligned envelope is taken. Small black no-data corners may remain, but protected
content cannot be cut. Deskew's axis-aligned envelope, true-TIFF edge clipping, and integer rounding can change final
pixel width and height. The fixed dimensions apply in source coordinates.

## Install the Development Source

Use a complete repository checkout. Do not copy only `X5_Crop.py`, and do not treat GitHub's generated Source code
archive as a stable release package. Regular users should download v4.2.8 from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases).

The V5 development source supports Python 3.12–3.14:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a future V5 Release package.

Setup finds 64-bit Python 3.12–3.14, reuses dependencies that meet the required versions, and installs or updates the rest
through their recognized package manager. Unknown ownership stops before changes. Homebrew is not required, and no private
environment is created.

## Input Contract

V5 production input must be:

- a one-page TIFF;
- unsigned 16-bit samples;
- three-channel RGB with contiguous planar configuration;
- `NONE`, `LZW`, `DEFLATE` / `ADOBE_DEFLATE`, or `ZSTD` lossless compression;
- TIFF Orientation 1–8.

An out-of-domain file becomes `runtime_error`; it is never silently converted. Orientation is normalized on read and
official output uses `Orientation=1`.

## Run

In the repository root, run the command with one TIFF or a scan directory. Use `python3 X5_Crop.py --interactive` to
process TIFFs in the current directory interactively. A future V5 release package provides macOS and Windows double-click
launchers.

Command-line example:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

Main options:

- `input`: one TIFF or a directory; defaults to the current directory;
- `--output PATH`: a fresh output directory;
- `--format`: `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, or `120-67`;
- `-n, --count N`: explicit slot count; omit it to confirm the default complete count;
- `--layout`: `auto`, `horizontal`, or `vertical`;
- `--deskew`: `auto` (default) or `off`;
- `--jobs N`: source concurrency, default 1 and maximum 3;
- `--debug-analysis`: write 1,800 px wide, height-adaptive three-panel diagnostic JPGs, a development report, and a
  summary, but no official TIFFs;
- `--interactive`: prompt for format, count, deskew, and Debug Analysis.

There is no `--overwrite`. The target must not exist. Use different fresh directories for Debug Analysis and official
cropping; an official run always rereads the source TIFF. If another operation creates the target during processing, it is
preserved and publication reports an output error. Publication also stops if the filesystem cannot guarantee atomic
no-replace behavior. On macOS, write to a fresh directory on an APFS/HFS+ volume that supports atomic no-replace
publication. If needed, copy the completed output directory to exFAT afterward.

## Status, Output, and Exit Codes

Each input has exactly one terminal state:

- `approved_auto`: writes the complete official TIFF set;
- `needs_review`: writes no photos and retains the minimum missing fact and suggested action;
- `runtime_error`: this input failed while other inputs continue.

Debug Analysis shows the template, observations, winner/runner, raw and guarded aspect-ratio intervals, inferred H, the
fixed source-space window's size and position, content-protection evidence, and first blocking reason. It also shows
`DESKEW APPLIED`, `ROTATION NOT NEEDED`, or a typed `DESKEW SKIPPED`. It reads the same detection facts and never solves
geometry again. The development report also records exterior color continuity, weak signals, and measurement
availability; an available measurement does not establish holder identity or authorize a crop by itself.

Default output:

```text
x5_crop_output/
  source_name_01.tif
  source_name_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

Exit codes:

- `0`: published successfully with no `runtime_error`;
- `1`: published with a runtime error, or every input failed;
- `2`: CLI, input-set, or preflight failure;
- `3`: a fresh output directory could not be published safely.

Official TIFFs are read and written only by `tifffile + imagecodecs`, with checks for bit depth, channels, ICC,
resolution, supported metadata, lossless compression, and `Orientation=1`. Each run writes staging and publishes with one
rename; an existing target is never traversed, replaced, or deleted.

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
