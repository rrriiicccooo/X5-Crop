# X5 Crop User Guide

- Latest public stable release: v4.2.8
- Current repository source: current-only V5, not publicly released
- Intended input: Hasselblad / Imacon X5 holder scans whose format, strip mode,
  and required count are already known

## Product Behavior

X5 Crop produces conservative TIFF crops without cutting real photo content.
You provide the film format. The program combines scan pixels, fixed physical
dimensions, holder canvas, count, and order. It writes photos only when content
protection, excess margins, transform, and TIFF output are all safe. Otherwise
the whole source enters `needs_review`; individual slots are never salvaged.

The program does not claim to recover one uniquely true photo boundary and does
not infer format or count from filenames. It independently matches the holder
from the image before obtaining that holder contract's complete slot count.
Full confirms that the film uses the matched holder's complete filled layout,
and the program uses that holder's full count. Partial confirms that the film
does not fill the holder and requires an explicit count, including blank
exposures. Partial may equal `full_count`, but it receives no long-axis
centering or even-layout authority. Thus three 120-66 exposures may be either
full when they use the filled layout, or `partial --count 3` when they do not.

Preflight rejects partial without a count, a non-positive count, or full with a
count. If a partial count exceeds the matched holder's full count, a
non-interactive batch also stops before detection with exit code `2`.
Interactive use lists all holder/count conflicts and returns to the mode/count
step without asking for format or Debug Analysis again; it never rewrites count
one source at a time. Ambiguous holder matching remains `needs_review` instead
of guessing holder identity or count. `135-dual` is full-only: 12 slots total,
six per lane.

Normal spacing is the default in both modes. X5 Crop first places the fixed
format template, then calibrates the current source pitch from at least two
independent adjacencies. A supported template may infer a missing separator and
records that role as inferred. Full never promotes the format gap search prior
into placement authority and never overrides direct contact, overlap, or
wide-gap evidence. A local anomaly must be directly bound to one known
adjacency and shifts the following frames only once.

The format fixes the physical photo rectangle. Detection places those rectangles
from strip direction, top/bottom evidence, dark separator bands, shared dimensions,
and local film advance, then includes only the minimum boundary uncertainty needed
to protect visible content. Every final side must remain within 5% of format width
for start/end and 3% of format height for top/bottom. When photos touch or overlap,
neighboring outputs may deliberately share source pixels; the slot count does not
change.

Content protection does not mean that no content-like pixel may ever cross a
crop line. A tiny corner-only graze, edge alias, or dust speck remains neutral.
Only reliable two-dimensional picture structure that leaves the corner and
continues across the complete boundary-uncertainty interval can veto an
automatic crop. X5 Crop does not enlarge or distort the fixed format rectangle
to preserve an already acceptable corner trace.

Complete counts are 135=6, half=12, XPan=3, 120-645=4, and 120-66=3.
120-67 uses 3 on ordinary holders and 2 on the short holder. 135-dual uses 12
in total, six per lane.

## Install

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

The release package supports Python 3.12–3.14 and freezes these importable
module versions:

```text
numpy       2.5.1
scipy       1.18.0
cv2         5.0.0
tifffile    2026.7.31
imagecodecs 2026.6.26
PIL         12.3.0
```

Run the platform installer:

- macOS: `install/X5_Crop_Mac_install.command`
- Windows: `install/X5_Crop_win_install.bat`

Setup first selects a supported global Python, then checks each importable
module, version, and origin. A usable version is reused unchanged whether it
came from Homebrew, pip, or another provider. Only missing modules receive the
smallest frozen binary-wheel install in that Python's user package site. When
an existing version is wrong, setup uses the confirmed Homebrew or pip owner to
update it. An unknown owner causes a safe stop before any second package can
hide the original environment.

Homebrew is not required and is never installed merely to obtain OpenCV. If
`cv2` is missing, the user-site fallback is
`opencv-python-headless==5.0.0.93`; an already usable Homebrew, pip, or other
OpenCV provider remains untouched. No private `.venv` is created, so the same
Python can run standalone `X5_Crop.py` from any folder. Uninstall removes only
user packages that the receipt proves X5 Crop introduced and that no other
package still uses; it never rolls back pre-existing packages or Homebrew
updates.

## Input Contract

The V5 production domain is:

- one TIFF page;
- unsigned 16-bit samples;
- three-channel RGB with contiguous planar configuration;
- `NONE`, `LZW`, `DEFLATE` / `ADOBE_DEFLATE`, or `ZSTD` lossless compression;
- TIFF Orientation 1–8.

A file outside this domain becomes `runtime_error`; it is not converted or
guessed. Orientation is resolved at decode. Detection, ordering, and cropping
use canonical visual coordinates, and output pixels are written with
`Orientation=1`.

## Run

Graphical launch:

- macOS: put TIFFs beside `X5_Crop_Mac.command` and double-click it.
- Windows: put TIFFs beside `X5_Crop_win.bat` and double-click it.

Command-line example:

```bash
python3 X5_Crop.py /path/to/scans \
  --format 120-66 \
  --strip partial \
  --count 2
```

Command-line options:

- `input`: one TIFF or a directory; defaults to the current directory.
- `--output PATH`: output directory; defaults to `x5_crop_output` beside input.
- `--format`: `135`, `135-dual`, `half`, `xpan`, `120-645`, `120-66`, or `120-67`.
- `--layout`: `auto`, `horizontal`, or `vertical`.
- `--strip`: `full` or `partial`.
- `--count N`: a positive integer used only by partial and required there,
  including intermediate blank exposures; it must not exceed the matched
  holder's complete count. Full rejects `--count`. When count equals
  `full_count`, choose full for a filled layout and partial for a non-filling
  layout. `135-dual` rejects partial.
- `--jobs N`: source concurrency; default 1, maximum 3. The default limits peak
  memory on ordinary computers; when memory is plentiful and processing a batch
  of source TIFFs, you may explicitly use `--jobs 2`. Numerical library threads
  remain fixed at 1.
- `--debug-analysis`: run the complete detector and write a source-adaptive
  three-panel diagnostic JPG, development report, and summary, but no official
  TIFFs or review copy. It is off by default and preserves the full strip aspect
  without cropping the photographs.
- `--interactive`: prompt for format, mode, count, and Debug Analysis; a
  multi-file holder/count preflight covers the whole batch and returns to the
  mode/count step after listing every conflict.

There is no `--overwrite`. The output must be a fresh path that does not exist;
X5 Crop never takes over or deletes an older output.

Debug Analysis and production cropping can be run as two steps:

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2 --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2 --output /path/to/x5_crops
```

Debug Analysis publishes only diagnostic and development facts. A normal run
always performs fresh measurement, physical solving, and Gates from the source
TIFF; an older report is never executable runtime state.

## Status And Exit Codes

Each input has one terminal status:

- `approved_auto`: a normal run writes the complete set of official photo
  TIFFs; a Debug Analysis run records only that the Gate passed.
- `needs_review`: a normal run writes no official photos and copies the source
  into `needs_review/`; a Debug Analysis run records only the reasons.
- `runtime_error`: writes no photos for that input while other inputs continue.

An unresolved holder, a producer bound being reached, no uniquely dominant
physical placement, or reliable content vetoing every placement all remain
`needs_review`; X5 Crop writes no guessed photo TIFFs. The normal JSONL report
retains holder/count authority, final selection, safe envelopes, and root Gate
reasons. Explicit Debug Analysis additionally retains the theoretical template,
observations, fit winner and runner, deviation/inference ledger, content vetoes,
and bounded-work receipt.

Exit codes:

- `0`: published successfully with no `runtime_error`.
- `1`: published with at least one `runtime_error`, or every input failed and
  nothing was published.
- `2`: CLI, input-set, or preflight failure.
- `3`: a fresh output directory could not be published safely.

If every input is `runtime_error`, X5 Crop does not publish an empty replacement;
the previous output remains untouched.

## Output And Safe Publication

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

Photos stay directly in the root. There are no `run-*` or per-source folders.
`needs_review/` and `_debug_analysis/` appear only when needed. A Debug Analysis
run uses its own fresh output directory, containing only diagnostic JPGs,
report, and summary—never official TIFFs or review copies.

Each run first writes a temporary directory beside the target. After all inputs,
required TIFF header checks, and reports finish, one rename publishes it. If the
target already exists or appears during processing, X5 Crop exits with code `3`
without traversing, replacing, taking ownership of, or deleting that directory.
Disk-space, write, or rename failures remove only this run's unpublished staging
and report the actual error; there is no hidden reservation ledger or recovery
state machine.

## TIFF Fidelity And Privacy

Official TIFF I/O is owned exclusively by `tifffile + imagecodecs`. Every output
header is reopened after its write handle closes and checked for 16-bit RGB,
three channels, contiguous planar layout, shape, ICC, resolution, resolution
unit, supported metadata, lossless compression, and `Orientation=1`. Complete
pixel rereads belong to TIFF-contract, named-TIFF, platform, end-to-end, and
release verification rather than every normal output.

Normal runs do not calculate a content SHA for the source TIFF,
inspect Git or test cohorts, create performance receipts, profile, or inject
faults. Pillow is imported lazily only for Debug Analysis.

## Remove And License

Dependency uninstallers:

- macOS: `install/X5_Crop_Mac_uninstall.command`
- Windows: `install/X5_Crop_win_uninstall.bat`

The uninstaller removes only dependencies introduced by X5 Crop whose versions
have not changed and which are no longer required by another package.

License: MIT — [LICENSE](../LICENSE)
