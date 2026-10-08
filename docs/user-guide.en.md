# X5 Crop V5 User Guide (Development Preview)

- Scope: unreleased V5 source on repository `main`
- Current public stable release: v4.2.8; its commands and behavior differ, so use the documentation bundled with it
- Intended input: Hasselblad / Imacon X5 holder scans whose format and exposure-slot count are already known

## Product Behavior

X5 Crop uses a known format's design-size prior to establish a bounded physical template for each source; it is not a
general-purpose photo-boundary recognizer.
Official TIFFs are written only when every slot in the source has a directly usable crop that meets the current risk-admission rules. Otherwise the
entire source becomes `needs_review`; individual slots are never salvaged.

Cropping protects photograph content already visible in the input TIFF. Image content hidden by the holder and
absent from the TIFF is outside the recovery scope. Visible content, including tilted corners, must be retained.
Each source TIFF shares one W/H size; every Frame requests one fixed source-space window
of `1.1W × 1.1H`, with a fixed 5% margin on each side. The script selects the window position only and never
adjusts its size. The fixed margin includes base protection; no additional fixed-size border is added.

When credible evidence requires a complete physical envelope that cannot fit inside the fixed box, the whole source
remains in `needs_review`; the highest score cannot force automatic approval. Shared H candidates use the same fixed
box and cannot enlarge it by taking a union. A true TIFF edge may be source-clipped, but an internal lane or other
authority boundary cannot be bypassed by shrinking the window.

### Format And Count

Format is always required. Count may be omitted or explicit:

- omit `--count` to confirm the matched holder's default complete count;
- use `--count N` to confirm exactly N slots, including intermediate blank exposures;
- count must be positive and no greater than the matched-holder capacity;
- `135-dual` is automatic only at 12 slots, six per lane; every other count enters review.

Default complete counts are 135=6, half=12, XPan=3, 120-645=4, and 120-66=3. 120-67 uses 3 on an ordinary holder
and 2 on the short holder. 135-dual uses 12 total.

V5 applies the same physical and safety contract to every format. Current development gold has no real gold source for
`xpan`, `120-645`, or `135-dual`, so these formats are implemented by the Runtime but do not yet have real-sample
accuracy coverage. They receive neither a special disable rule nor a looser acceptance rule.

The program never infers format or real photo count from filenames, picture content, holder capacity, or blank slots.
It does not remove, merge, or reorder blank slots. V5 has no full/partial mode.

### Automatic Approval And Review

V5 first establishes coarse support and a common direction from the whole strip. It then compiles format/count into a
bounded W/H template and makes bounded local measurements only near theoretical outer, separator, and top/bottom
positions. Format dimensions are cross-camera priors, not an identical gate size imposed on every camera. Direct edges
may independently measure that source's common W and H while retaining their native positions.
Pixel evidence aligns or rejects the template; it cannot invent format, count, or placement authority.

A missing start/end side may be inferred only after source W is closed by complete direct Frames or a full-rank set of
independent direct constraints, and that Frame still has its opposite direct side. Inference cannot override an observed
edge or discard counterevidence. A Frame whose two sides are both unseen may be generated only when the calibrated Grid
has a reliable absolute anchor, the corresponding adjacencies were fully checked, and no counterevidence exists; the
complete physical envelope and fixed-box checks still apply. Reliable local W measurements survive incomplete distant
coverage or an unresolved placement. A fully unobserved Frame does not prevent other single-sided Frames from using
common W. Available measurements do not grant automatic output: counterevidence, ambiguity, and risk checks remain.
Direct W and H retain separate evidence. A gold-calibrated
aspect-ratio authority may let W constrain H with full uncertainty. Every
format uses the same physical-millimetre-floor plus relative-ratio method for W/H compatibility, while the propagated
axis guards produce a bounded ratio interval specific to that format. This authority cannot impersonate direct
top/bottom, add independent evidence, or apply the nominal ratio as an exact conversion. Missing calibration, a true
conflict, or inability to fit the fixed box keeps the entire source in review. Direct top/bottom always
retains its native position and priority.

Within one registered window, weak gradient, tone, and texture signals are also checked jointly across height. They may
own a crop coordinate only when three independent height regions agree and uniquely reinforce the same direct edge.
Unbound or multiply explained joint lines remain Debug evidence and cannot create another placement.

The shared top and bottom of the whole strip are also observed as both sharp transitions and broad material changes.
A broad pair can become outer support only when both sides have the correct outward background, consistent polarity within
each side, continuous support across three longitudinal regions, compatible direction, and a span that fully encloses fixed H.
Coarse short-axis measurements retain weak material changes from the original 16-bit data that gray quantization can lose.
All complete boundary interpretations are checked together. When exactly one broad pair is equivalent to the sharp pair,
the sharp native coordinates remain canonical. A single side or multiple distinct explanations keeps the source in review;
signal strength does not choose a winner.

Broad boundary positions come from two-scale measurements on individual sampling traces. Each region requires a majority
of its original traces to support the same material boundary, including after fitting. Missing traces remain in the
denominator. A region's averaged signal is not treated as a measured coordinate on an individual trace.
When measured material peaks admit several valid connections, each interpretation is retained. If association cannot
finish within its computation bound, the whole source enters Review and the report retains the raw measurements and reason.
Variation in broad localization peaks does not remove a physically valid boundary interpretation. Unresolved competition
remains subject to the existing Review conditions.
Association avoids repeated checks so that some safe strips can finish within the original computation bound. Distinct
valid interpretations remain intact. Automatic approval still requires the fixed box to protect all content and complete
evidence.
Edge tracking limits candidate scans to the existing connection range while preserving the same distance, polarity,
missing-trace, and equal-distance ambiguity rules.

When a complete safe output footprint cannot be generated, the whole source enters Review and the diagnostic report
retains the specific reason.

Top and bottom use one signal baseline across the lane's full short axis, so each local query window does not independently
set the scale used to assess edge strength. Boundaries still require complete observations inside their registered windows;
the baseline creates no boundary evidence and does not treat missing regions beyond the source as background.

Direct top and bottom evidence need not occur on the same sampling trace. They may close one complementary direct pair
when each side has at least two independent support regions, their union covers the longitudinal domain of every output
Frame, and direction and fixed H agree. Shared support is still reported as zero. Incomplete coverage, a template-inferred
side, or multiple equally legal pairs keeps the entire source in `needs_review`. A complete pair also cannot win when the
same opposite closes against a strictly farther-out local direct edge. Likewise, one source-spanning edge cannot project
an opposite edge that is visible only locally across the whole strip.

A direct top/bottom pair that already meets shared-support and longitudinal-coverage requirements retains its measured
geometry when one side gains more complete source-spanning support. A local opposite edge must still meet the existing
coverage rules, and multiple legal pairs remain in Review.

When independent evidence uniquely establishes both photo edges, the program uses those measured edges to choose the
fixed-box position rather than replacing the measured height with an inferred height inside the frame. A conflict with a
supported aspect-ratio constraint still requires review. When direct photo edges cannot be established, complete
outer-support evidence can still authorize a crop under the fixed-box policy.

Short fragments of the same photo edge are retained and checked together. They may become an authorized direct boundary
only when the complete measurement supports at least two independent regions; several photo slots covering the same
small fragment do not add evidence strength. Unauthorized fragments remain boundary hypotheses without moving a crop
or preventing further checks of missing edges, and do not consume the global boundary quota. Reports preserve each
direct boundary's original region count and distinguish complete measurements from boundaries used by the global solver.
Existing complete edge groups may also form a crop proposal for review. Every group's original measurements remain
intact. When fragment membership has multiple interpretations, the report records the grouping condition and retains the
new crop for review. The existing primary and runner crops keep their approval conditions. More fragments alone do not
authorize automatic output.

Normal strips use one shared pitch. Every directly proven, ordinal-unique separator may constrain its own wide or narrow
gap; later Frames apply that measured delta once. Multiple proven gap changes still use one bounded pass. An ambiguous
gap, missing authority, inability to reliably choose among legal answers, or an unknown required Frame remains `needs_review`.
A measured narrow gap need not reach the format's nominal gap lower bound. If measured relations cannot independently
determine every template parameter, the existing calibrated bounds test the same placement. Missing or conflicting
calibration keeps the image in Review; authorized direct coordinates remain unchanged.
Fit compatibility uses the current model and direct anchors, not an earlier residual verdict. Local boundary refinements
do not alter the global residual calculation.
A narrow material strip at a film-strip end can lie inside or outside the photo. Existing evidence for both edges is retained;
the strip alone does not force selection of the inner edge.
An edge signal cut off by the source or query range cannot alone provide a precise boundary position;
unmeasured regions are not treated as confirmed background.
Narrow material at a photo edge also preserves existing boundary-role candidates; possible interpretations are checked
against the whole-strip constraints.
When discrete positions remain ambiguous, each candidate's local boundaries are checked independently, and each review
footprint obeys its own jointly supported direct coordinates; this does not remove the Review requirement.
Boundary interpretations with distinct observation identities are retained even at the same position. An incomplete
alternative is not rejected solely because its currently collected support is smaller.
When the same boundaries permit different feasible ranges, each protective range and its evidence are retained for
the safety checks of the whole source.
Shared cross-axis boundaries must meet the existing coverage requirements for each candidate's photo regions independently;
additional candidates do not add evidence strength.
Runtime acceptability scoring is not yet enabled; this is a current selection limit, not a requirement to prove one uniquely true crop.
Reports retain each lane's existing primary and single runner crop footprint, or the specific reason it could not be generated.
If the sequence alternative cannot form a distinct crop, the existing cross-axis alternative is still considered.
At most one additional conditional cross-axis proposal is retained separately from the primary and runner.
When a fit satisfies the physical limits for a complete group of boundary measurements, this proposal can preserve
an interpretation that the original fit could not retain, for manual review. Automatic approval conditions remain unchanged.
When fragment membership is ambiguous, the system preserves the original complete measurement groups and examines
whole-group combinations. If search or batch fitting exceeds its work limit, the report records the reason and retains
the existing crop proposals. An individual conditional combination does not gain automatic approval.
When photo ownership is fixed and multiple complete top/bottom interpretations remain, the report may also record
a common fixed box and the coverage result under each interpretation. Shared H candidates use the same `1.1W × 1.1H`
window and cannot enlarge it by taking a union. Every fully verified interpretation must be protected by that fixed box
and pass all evidence and source-wide safety checks. Incomplete interpretations, a physical envelope that does not fit,
or failed checks still require Review; the highest score cannot replace these conditions.
Local refinement preserves ambiguous measurements and failed fits in the report. An unresolved alternative still
requires Review even when the selected measurements would permit a crop.
Cross-axis crop protection accounts for the relationship between measured position and direction, the statistical fit,
and local edge departures. Top and bottom protection uses the actual reachable longitudinal ends to select the fixed-box
position; the script does not change the fixed window size. Automatic approval still requires complete content protection
and complete evidence.
Development gold analysis evaluates each footprint independently, allows multiple safe results, and separates unsafe from
unavailable geometry. Each retained crop also records its fixed-box position, physical features, provenance, and explicit
missing reasons. These records do not change automatic approval conditions.
Offline development ranking groups evaluation by source image and separates out-of-fold from in-sample results; its scores
are not safety probabilities and do not select actual crops. Contact and overlap are challenge cases, not predetermined
outcomes: the standard detector and Gate may approve them when direct-use admission is satisfied, while safe review remains
correct when evidence is insufficient. V5 does not enable a second detector for them. A proven relation can participate in
the evidence for the adjacent END/START boundaries. The fixed margin cannot establish the relation by itself or enlarge
the fixed box.

Holder fill is assessed only after placement by asking whether another W fits beyond either outer. It never searches
for or centers a placement. Both lanes of 135-dual must be complete.

## Fixed Source-Space Window, Content Protection, And Deskew

Each source TIFF uses one common W/H size. Every Frame requests one fixed window:

```text
source-space window = 1.1W × 1.1H
per-side margin = 5%
```

The fixed box permits the script to select a position only; measurement, residual, direction, or score cannot change
its size. It must contain all visible TIFF content, including tilted corners. When credible evidence requires a complete
physical envelope that cannot fit inside the box, the whole source enters `needs_review`. In-box offset is not separately
penalized, and development gold no longer uses actual per-side expansion relative to the true boundary as a 5% blocking
criterion. V5 remains an unreleased development preview. Release acceptance still requires zero false accepts,
safe automatic approval of all nominal tasks, and performance and platform validation.

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

## Install The Development Source

Use a complete repository checkout. Do not copy only `X5_Crop.py`, and do not treat GitHub's generated Source code
archive as a stable release package. Regular users should download v4.2.8 from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases).

The V5 development source supports Python 3.12–3.14:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a future V5 Release package.

Setup reuses a suitable global Python and existing dependencies and installs only what is missing. Unknown ownership
stops before any write. It creates no private `.venv` and does not require Homebrew.

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

Graphical launch:

- macOS: place TIFFs beside `X5_Crop_Mac.command` and double-click it;
- Windows: place TIFFs beside `X5_Crop_win.bat` and double-click it.

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
cropping; an official run always rereads the source TIFF.
If another operation creates the target during processing, it is preserved and publication reports an output error;
retry with a new directory. Publication also stops if the filesystem cannot guarantee atomic no-replace behavior.
The current macOS exFAT implementation was found to reject this publication operation. Write to a fresh directory on
APFS/HFS+; if needed, copy the completed output directory to exFAT afterward.

## Status, Output, And Exit Codes

Each input has exactly one terminal state:

- `approved_auto`: writes the complete official TIFF set;
- `needs_review`: writes no photos and retains the minimum missing fact and suggested action;
- `runtime_error`: this input failed while other inputs continue.

Debug Analysis shows the template, observations, winner/runner, raw and guarded aspect-ratio intervals, inferred H,
the fixed source-space window's size and position, content-protection evidence, and first blocking reason. A shared
support slope is counted once in its joint state rather than again as a residual. It also shows
plus `DESKEW APPLIED`, `ROTATION NOT NEEDED`, or a typed `DESKEW SKIPPED`. It reads the same detection facts and
never solves geometry again.

The development report also records exterior color continuity, weak signals, and measurement availability.
These observations help inspect exterior material. An available measurement does not establish holder identity
or authorize a crop by itself.

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
resolution, supported metadata, lossless compression, and `Orientation=1`. Each run writes staging first and publishes
with one rename; an existing target is never traversed, replaced, or deleted.

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
