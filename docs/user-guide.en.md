# X5 Crop V5 User Guide (Development Preview)

- Scope: unreleased current-only V5 source on repository `main`
- Latest public stable release: v4.2.8. Its commands and behavior differ; use
  the documentation bundled with that release
- Intended input: Hasselblad / Imacon X5 holder scans whose film format and
  exposure-slot count are already known

## Product Behavior

X5 Crop treats detection as alignment of a known format template, not as
general-purpose photo-boundary recognition. You provide format and count. The
program places fixed physical rectangles using photo-group outer, separator
bands, source-axis frame geometry, and two-dimensional content protection. It
writes official photos only when every slot of the source is safe. Otherwise
the complete source enters `needs_review`; individual slots are never salvaged.

X5 Crop never infers format or the real photo count from filenames, picture
content, or holder capacity. Count includes intermediate blank exposures. Blank
slots are not removed, merged, or reordered.

### Format And Count

The command line has format and optional count; there is no full/partial mode:

- omit `--count` to confirm the matched holder's default complete count;
- use `--count N` to confirm exactly N slots;
- an explicit count must be positive and no greater than matched-holder capacity;
- `135-dual` defaults to 12, six per lane. Any other explicit count enters
  `needs_review`; lane allocation is never guessed.

Complete counts are 135=6, half=12, XPan=3, 120-645=4, and 120-66=3. 120-67
uses 3 on ordinary holders and 2 on the short holder. 135-dual uses 12 total.

Whether a selected photo group fills the holder is assessed only after
placement. The test asks whether one more format width W fits outside either
outer edge; it adds no gap. This fact never searches for or centers a
placement. A single lane need not be centered. Both lanes of 135-dual must be
confirmed filled before automatic output.

## Detection Path

### Whole Strip To Local Boundaries

V5 inherits the useful behavior of v4.2.8 without copying its old solver:

1. obtain a coarse strip region and local measurement direction from the
   holder, film material edge, or another stable long structure;
2. place a fixed W/H template from format, count, and scale;
3. locate separator material bands and outer inside finite expected corridors;
4. refine only around theoretical boundaries with one bounded local pass;
5. interpret observed-minus-theoretical residuals as translation, small pitch
   correction, or one local advance;
6. stop as soon as placement is unique and all safety facts are complete.

Coarse support answers only where the strip roughly lies and how local queries
should be oriented. It cannot declare a photo boundary or output deskew by
itself. A local pixel observation has no slot, start/end, or top/bottom role
until it is bound to the template. Two edges, a band, and many traces from one
separator remain one physical structure rather than many votes.

An invisible first or last boundary is not automatically a failure. Once
independent internal separator evidence establishes phase, pitch, and ordinal,
the template may project the missing outer. With no direct phase anchor, the
template cannot prove itself.

### Fixed Size, Separators, And Local Exceptions

All frames on one strip share format W/H and source scale. Pixel noise does not
change frame size; a gap changes only position.

Normal strips use one shared pitch. A directly proven wide or narrow adjacency
may authorize at most one local advance: every later frame moves once and then
continues with the shared pitch. An unknown ordinal, more than one required
shift, contact, or overlap remains `needs_review`. V5 has no user-confirmed
overlap golden sample, so it does not automatically approve overlap or enable
special overlap bleed.

### Source-Axis Geometry, Mild Bend, And Optional Deskew

Detection placements have no angle: start/end and aperture top/bottom always
follow the source axes. Local cross direction proves fragment continuity and
side compatibility and contributes only to safety protection. It cannot rotate
a frame, choose a placement, or decide output deskew. A direct aperture edge may
project its short-axis position only within its sampled trace span; uncovered
frames are never extrapolated along the fitted line.

A mild bend does not create a curve model. Per-trace departure belongs only to
selected-placement safety. A directly observed enclosing support may retain its
same-state local slope because that support itself owns final top/bottom. If
required protection exceeds the output budget, the whole source enters review.
Frames do not receive independent detection angles or free quadrilaterals.

Deskew is optional cleanup after the safety decision. X5 Crop reads the
outermost dark edges at 6–24 sparse positions along the strip and robustly fits
each side. It rotates only when both sides agree and both fits are stable. It
does not classify the observed edge as holder, film, or photo. Missing,
conflicting, or out-of-range evidence skips deskew without fabricating `0°`
and without downgrading an otherwise safe source. `--deskew auto` is the
default; `--deskew off` skips observation entirely and preserves orientation.

`auto` inherits the release thresholds for dark support, outer extent, 6–24
traces, minimum dark content per trace, robust fitting, two-side slope, and
residual. It leaves orientation unchanged below `0.03°` or below the
length-dependent 3–12 px minimum displacement. It also skips rather than
rotates above `0.35°` or 120 px end-to-end displacement. The `2°` observation
limit rejects implausible measurements; it is not permission for a large output
rotation.

When deskew is applied, the image and every already-safe frame polygon receive
the same rotation. The output box is the axis-aligned envelope of that rotated
polygon, never a fixed W×H crop. A small angle error can therefore leave slight
tilt or extra border but cannot cut confirmed content. Envelope corners outside
the polygon may be black; these are representational corners, not detection
failures.

## Top/Bottom And Acceptable Outer

X5 Crop need not distinguish whether an outer support is a holder edge or film
material edge, but it distinguishes two final uses.

### Photo Aperture

A local observation may represent the real photo top or bottom only when its
finite position, locally compatible direction, inside/outside relation, and
fixed-H closure agree. Direction proves this cross evidence; it never becomes a
placement angle. Valid evidence can be:

- direct top and bottom;
- one source-wide direct side with the opposite side inferred by fixed H;
- one role-authorized direct side with a direct trace in each selected frame
  domain (with at least three selected domains); it may own fixed-H single-side
  placement even when its independent-support ledger reports only two regions;
- multiple well-separated fragments on one side that demonstrably belong to
  the same line.

A short internal picture line, fragments joined merely because coordinates are
close, or two different legal outer positions cannot determine the crop. Two
discrete answers are never averaged or resolved only by stronger gradient. The
single-side exception still requires complete direction and one binding with a
direct trace in each selected domain; fewer than three selected domains, a
missing domain, two disconnected fragments whose union covers the domains,
unauthorized role, or incomplete direction remains review. Holder short-axis
center is only a compatibility fact, not a required authority; fixed H still
infers the opposite side and local departure remains in the output budget.

### Enclosing Support

When aperture evidence is unavailable, a directly observed, continuous pair of
outer supports may own top and bottom if it fully encloses fixed H and its total
height is no more than `1.1 × H`. This permits a holder or film-material edge
to define the output while retaining an acceptable small dark border.

That height is the worst directly observed span of the support pair. X5 Crop
does not combine top and bottom extremes from different feasible states of the
same placement into a larger height that was never physically observed.

Both sides must use the same meaning: one aperture side can never be mixed with
one enclosing-support side. A unique aperture closed by direct observations on
both sides is preferred. When aperture evidence is one-sided with a
fixed-height inferred opposite, or when distinct aperture answers remain, one
unique directly proven enclosing-support pair may be the stronger output
boundary. Enclosing support is a separately proven complete output boundary,
not a relaxed guess.

## Bleed, Joint Safety, And The 5% Budget

Bleed is deterministic product margin. It is not measurement confidence and
never helps choose placement.

For photo-aperture output:

```text
start/end bleed = max(0.15 mm, 0.7% W)
top/bottom bleed = 0.25 mm
```

X5 Crop first retains all jointly feasible states of the one selected
placement—phase, pitch, cross position, one local advance, and straight-line
residual. A direct enclosing pair also retains its own same-state slope. Bleed
is added afterward. X5 Crop does not add independent maxima that cannot occur
together and never absorbs a runner-up.

Automatic aperture output allows at most 5% expansion per side relative to the
corresponding format dimension. Measurement uncertainty, straight residual,
and bleed all consume that limit, and sides cannot borrow from one another. For
135, normal 0.252 mm start/end bleed uses 14% of the 1.8 mm per-side limit.
Cross bleed of 0.25 mm uses about 20.8% of the 1.2 mm per-side limit.

Enclosing-support output adds no 0.25 mm top/bottom bleed and does not use the
aperture's cross-side 5% test. Its independent rule is that the directly
observed total height must not exceed 1.1H. Start/end still use normal bleed and
the 5% per-side limit.

Before the safety decision, the required source-space footprint is never silently
clipped to source or lane bounds. Any truly required polygon area outside
authority, or any exceeded limit, sends the complete source to `needs_review`.
Representational envelope corners introduced by post-decision deskew do not
change that safety result.

Two-dimensional content is queried against the final post-residual, post-bleed
polygon. Picture structure outside the nominal frame but still inside bleed may
pass; only reliable content crossing the final crop boundary can veto automatic
output. Content cannot move boundaries, split frames, create a placement, or
score a competitor. Tiny corner grazes, aliasing, and dust remain neutral.

## Install The Development Source

Obtain a complete repository checkout. Do not copy only `X5_Crop.py`, and do
not treat GitHub's generated Source code archive as a stable release package.
Regular users should download v4.2.8 from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) and follow
its bundled documentation.

The V5 development source supports Python 3.12–3.14. From the repository root,
run:

- macOS: `tools/install/X5_Crop_Mac_install.command`
- Windows: `tools/install/X5_Crop_win_install.bat`

The same installers are under `install/`, without the `tools/` prefix, in a
future V5 release package. Setup reuses a suitable global Python and existing
dependencies, installing only missing items. Unknown ownership stops before any
change. Homebrew is not required, and no private `.venv` is created. Uninstall
removes only receipt-proven dependencies introduced by X5 Crop that no other
package needs.

## Input Contract

The V5 production domain is:

- one TIFF page;
- unsigned 16-bit samples;
- three-channel RGB with contiguous planar configuration;
- `NONE`, `LZW`, `DEFLATE` / `ADOBE_DEFLATE`, or `ZSTD` lossless compression;
- TIFF Orientation 1–8.

A file outside this domain becomes `runtime_error`; it is not silently
converted. Orientation is normalized on read and outputs use `Orientation=1`.

## Run

Graphical launch:

- macOS: put TIFFs beside `X5_Crop_Mac.command` and double-click it;
- Windows: put TIFFs beside `X5_Crop_win.bat` and double-click it.

Command-line example:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

Main options:

- `input`: one TIFF or a directory; defaults to the current directory;
- `--output PATH`: a fresh output directory;
- `--format`: `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, or `120-67`;
- `-n, --count N`: optional positive slot count; omit it to confirm the
  matched-holder default;
- `--layout`: `auto`, `horizontal`, or `vertical`;
- `--deskew`: `auto` (default, bounded cleanup after approval) or `off`
  (preserve source orientation);
- `--jobs N`: source concurrency, default 1 and maximum 3;
- `--debug-analysis`: write 1,800 px wide, height-adaptive three-panel
  diagnostic JPGs, development report, and summary, but no official TIFF or
  review copy;
- `--interactive`: prompt for format, count, deskew, and Debug Analysis.

Interactive mode displays count for every format. Press Return to confirm the
matched-holder complete count, or type another valid count to confirm it
explicitly. `135-dual` uses the same interaction, but any value other than 12
enters review.

There is no `--overwrite`. The target must not exist. Use different fresh
paths for Debug Analysis and normal cropping; a normal run always reads the
source TIFF again.

## Status, Output, And Exit Codes

Each input has one terminal status:

- `approved_auto`: writes the complete official TIFF set;
- `needs_review`: writes no photos and retains the source with the minimum
  missing fact and a suggested action;
- `runtime_error`: this input failed while others continue.

Debug Analysis shows the theoretical template, observations, residual pattern,
direct and inferred boundaries, winner/runner difference, final output
footprint, budget use, first blocking reason, and either `DESKEW APPLIED`,
`ROTATION NOT NEEDED`, or typed `DESKEW SKIPPED`. Reports also record
`deskew_applied`, observed angle, applied rotation, and skip reason. Failures
distinguish user-correctable input, remeasurement-recoverable evidence, and
cases the system must not guess. The third panel fills each actual final output
footprint with its frame color and a translucent overlay plus a matching solid
edge; it no longer layers placement/feasible ranges or a white dashed box.
Debug reads the same detection facts and never solves geometry again.

Default layout:

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

Official TIFFs are written only by `tifffile + imagecodecs`. Bit depth,
channels, ICC, resolution, supported metadata, lossless compression, and
`Orientation=1` are checked. Each run writes staging first and publishes with
one rename; an existing target is never traversed, replaced, or deleted.

License: MIT — [LICENSE](../LICENSE)
