# X5 Crop

> **下载提示 / Download Notice**
>
> 日常使用请从 GitHub **Releases** 下载整理好的 `X5-Crop-vX.X.zip`。
> 不要下载 GitHub 自动生成的 **Source code** 压缩包；该压缩包是开发源码结构，
> 不是面向日常使用整理的发布包。
>
> Regular users should download the prepared `X5-Crop-vX.X.zip` from GitHub
> **Releases**. Do not use GitHub's auto-generated **Source code** archives;
> those are development source trees, not user-ready release packages.

X5 Crop 是用于 Hasselblad / Imacon X5 胶片片夹长图的 TIFF 自动裁切工具。
它会将同一文件夹里的长条 TIFF 扫描图拆成单张 TIFF。只有裁切几何和安全条件都已
明确解决的结果才会自动导出；其余图片进入复核。

X5 Crop is a TIFF cropper for long film-strip scans from Hasselblad / Imacon X5
holders. It splits long-strip TIFF scans into individual TIFF frames. Only
detections with resolved geometry and final safety approval are exported
automatically; all other cases are sent to review.

当前 active 脚本版本：V4.9

当前稳定发布版本：v4.2.8

Current active script version: V4.9

Current stable release: v4.2.8

## 中文用户手册

### 核心原则

- 原始 TIFF 不会被修改。
- 自动裁切会写出新的单张 TIFF。
- `needs_review/` 里的文件是原始 TIFF 的复制，用于人工处理。
- 自动裁切输出会保留原 TIFF 的位深、通道结构、ICC / 色彩空间、resolution、
  metadata 和已知无损压缩行为。
- 检测阶段依据物理证据决定自动导出或复核；任何未解决的张数、边界或替代裁切方案都会
  保持复核，而不会由置信度或历史输出强行转为自动裁切。

### 推荐下载

日常使用请下载 GitHub Releases 里的 `X5-Crop-vX.X.zip`。Release 包通常包含：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

Release 里的 `X5_Crop.py` 是单文件发布版，已经内置内部 `x5crop/` 代码。
Release 用户不需要复制 `x5crop/` 文件夹。

如果直接从仓库 `main` 分支运行，根目录 `X5_Crop.py` 是开发入口，需要旁边的
`x5crop/` 包。这是开发和测试结构，不是面向使用者的发布包。

### 第一次安装

首次在一台设备上使用时，运行安装启动器：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器会安装或检查 Python 依赖：

```text
numpy
tifffile
imagecodecs
Pillow
```

macOS 安装器还会尝试给当前 Release 文件夹里的启动器添加执行权限，并移除下载隔离
标记。这只作用于当前文件夹，不是系统级信任注册。

如果 macOS 无法通过双击打开安装器，打开 Terminal，输入 `cd `，将 X5 Crop
文件夹拖入窗口后按 Return，然后运行：

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

如果安装后仍无法通过双击打开主启动器，在 Terminal 进入放有 `X5_Crop.py`、
`X5_Crop_Mac.command` 和 TIFF 的文件夹，然后运行：

```bash
/bin/bash X5_Crop_Mac.command
```

### 文件摆放和启动

将入口脚本、对应系统的主启动器和要裁切的 TIFF 长图放在同一个文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

主启动器：

```text
macOS:   X5_Crop_Mac.command
Windows: X5_Crop_win.bat
```

启动器会依次询问：

```text
format:
partial mode? [y/n, return=no]:
count:
debug analysis? [y/n, return=no]:
```

只有开启 partial mode 后才会询问 `count`。按 Return 或输入 `auto` 表示自动判断张数。
检测始终在灰度 workspace 中工作；片夹可以是亮、暗或中间灰度。原始通道、色彩 metadata 和
TIFF DPI/PPI 只由 I/O 与报告保存，不会直接决定裁切几何。

auto count 会从当前格式允许的较大张数开始检查。程序先确定整条片条的安全短轴范围，再联合判断
每张照片的顺序、边界和片间关系。只有张数与裁切几何都已解决、不存在未解决的替代方案、且
输出保护可行时，才会自动输出；否则保持 REVIEW。Full 模式最多允许一个由完整序列唯一推导的
空白位置，缺少内容本身不算证据；两个空白位置或位置不唯一时保持 REVIEW。Partial auto 不会
利用空白区域增加张数。

内部物理证据、数据流和权限边界详见 `ARCHITECTURE.md`。

### Format 和张数

| 输入 | 格式 | 完整片条张数 |
|---|---|---:|
| 回车 / `135` | 普通 135 | 6 |
| `dual` / `135 dual` / `135-dual` | 双条 135 | 12 |
| `half` | 半格 | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

如果照片铺满片夹，请保持 `partial mode = no`。该模式通常更快，也更稳定。

建议开启 partial mode 的情况：

- 片头或片尾。
- 只扫到局部片条。
- 片夹没有被照片铺满。
- 你明确想让脚本自动判断这条里有几张。

对 XPAN 和 120-66，完整 3 张胶片有时也不会铺满较长片夹；这种情况仍按
`partial mode = yes` 处理。脚本内部会把“完整张数但未铺满片夹”记录为独立证据，
避免把片夹前后空白误读成胶片不完整。

`135-dual` 主要用于完整双条 135；partial 下会倾向复核。

### Debug Analysis

Debug Analysis 是试运行 / 分析模式。它会读取 TIFF、执行检测、判断 PASS/REVIEW，
并写出分析图和报告，但不会导出正式裁切 TIFF，也不会修改原 TIFF。

输出位置：

```text
x5_crop_output/_debug_analysis/
```

每张 Debug Analysis JPG 固定包含：

- `Original gray context`: 原始灰度上下文。
- `Frame slot geometry`: 共享短轴、有序 frame slots、保守输出包络和最终裁切框；未解决时显示
  `Provisional frame slots - NOT EXPORTABLE`。
- `Boundary and separator evidence`: raw paths/bands、实测边界、尺寸假设和叠片标记。

第三联图的内置图例由当前 diagnostics configuration 生成：

- 白色虚线 `Holder boundary`。
- 黄色 `Raw observation`。
- 红色 `Measured frame / separator edge`。
- 紫色虚线 `Dimension-only provisional edge`。
- 蓝色虚线 `External safety envelope`。
- 青色 `Corroborated overlap`。
- 绿色 `FrameSlot`。
- 黄色虚线 `Sequence-inferred FrameSlot`。
- 蓝色虚线 `FrameCropEnvelope / export-eligible final box`。

详细 evidence、CandidateGate 与 DecisionGate 说明写入 report；Debug Analysis
保持固定三联图，优先服务人工快速审阅。

状态含义：

- `PASS`: 会自动裁切。
- `REVIEW`: 不会自动裁切，需要人工复核。
- `RUNTIME ERROR`: 已产生检测结果，但后续运行阶段失败；manifest 会记录失败阶段，分析图不代表
  可导出的最终结果。

检查 Debug Analysis 时优先确认：

- 全部绿色 `FrameSlot` 是否共用一组安全短轴，长轴顺序、宽度和数量是否合理。
- 黄色虚线 blank slot 是否只出现在唯一可解释的完整序列中，且没有移动相邻真实照片边界。
- 蓝色 `FrameCropEnvelope` 是否覆盖对应 slot 与 boundary uncertainty。
- 半透明裁切色块是否覆盖照片并留出合理 bleed。
- 红色 separator observation 是否落在真实片间间距。
- 紫色 dimension-constrained tick 与青色 overlap tick 是否符合照片物理尺寸。

普通非 Debug Analysis 裁切不会生成报告。Report 只用于审计，不作为 detection cache；每次普通
裁切都会重新检测当前 TIFF。运行内只复用带 typed key 的 exact、count/offset-independent
measurement。

### 输出目录和复核

默认输出目录：

```text
x5_crop_output/
```

常见内容：

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  ...
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

说明：

- 自动裁切 TIFF 是新文件，会保留原 TIFF 的画质相关属性。
- `needs_review/` 存放需要人工处理的原 TIFF 副本。
- `x5_crop_report.jsonl` 是机器可读报告。
- `x5_crop_summary.csv` 是便于人工浏览的摘要表。
- `x5_crop_run_manifest.jsonl` 为每个输入记录最终运行结果、失败阶段、实际写出的文件，以及
  input processing / detection 时间、assessed candidates、solver evaluations 和精确测量 cache 命中。
- 普通启动器不会覆盖已有裁切 TIFF；命令行可用 `--overwrite` 覆盖。

默认输出 bleed 为长轴 20px、短轴 10px。只有独立观测的 signed spacing 确认叠片时，
相邻两张 frame 的对应侧才会增加到所需宽度。可用保护范围是基础 frame 到其
holder canvas 或所属 lane `frame_output_bounds` 的实际几何余量；任一侧余量不足时进入复核。
`FrameCropEnvelope` 是单个 `FrameSlot` 与共享短轴 uncertainty 的保守输出范围，不包含用户 bleed。
Bleed 只影响最终输出，不能改变 candidate geometry 或 Gate 结果。

### 常用命令行

查看完整参数：

```bash
python3 X5_Crop.py --help
```

启动和双击启动器相同的交互式流程：

```bash
python3 X5_Crop.py --interactive
```

普通自动裁切：

```bash
python3 X5_Crop.py . --format 135 --strip full
```

Debug Analysis dry run：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

局部片条：

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

关闭自动校斜：

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off
```

关闭 deskew fallback：

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew-fallback off
```

关闭并行：

```bash
python3 X5_Crop.py . --format 135 --strip full --jobs 1
```

强制导出几何已解决且输出保护可行的 `REVIEW` 结果；未解决的 provisional geometry 或
未解决的 overlap 输出保护永远不会导出：

```bash
python3 X5_Crop.py . --format 135 --strip full --export-review
```

### 卸载

X5 Crop 不是传统 App。删除 X5 Crop 文件夹即可移除脚本、启动器和该文件夹里的输出。

如需同时清理用户级 Python 依赖，运行：

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

卸载器不会自动删除 Python。卸载依赖可能影响其它 Python 工具，请确认后再清理。

### License

本项目以 MIT License 开源，详见 `LICENSE`。

## English User Guide

### Core Rules

- Original TIFF files are never modified.
- Auto crops are written as new TIFF files.
- Files in `needs_review/` are source-TIFF copies for manual handling.
- Auto-cropped TIFF output preserves source quality attributes, including bit
  depth, channel layout, ICC / color space, resolution, metadata, and known
  lossless compression behavior.
- Detection uses physical evidence. Confirmed content loss, unresolved geometry,
  or physically inconsistent frame dimensions go to review.
- Detection uses one grayscale workspace. Holder polarity is not assumed, and
  TIFF resolution metadata is used only after independent physical-scale
  corroboration. Original channels and color metadata remain an I/O concern.
- Automatic output requires resolved geometry and a final safety decision.
  Historical confidence or output parity is not used.

### Download

Use `X5-Crop-vX.X.zip` from GitHub Releases. The Release package normally
contains:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

The Release `X5_Crop.py` is a standalone file with the internal `x5crop/`
package bundled into it. Regular users do not need to copy the `x5crop/`
folder.

If you run from the repository `main` branch, root `X5_Crop.py` is a development
entry and requires the adjacent `x5crop/` package.

### First Install

On a new machine, run the installer first:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer checks or installs:

```text
numpy
tifffile
imagecodecs
Pillow
```

If macOS does not open the installer by double-clicking, open Terminal, type
`cd `, drag the X5 Crop folder into the window, press Return, then run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

If the main launcher still does not open after installation, enter the folder
that contains `X5_Crop.py`, `X5_Crop_Mac.command`, and your TIFF files, then run:

```bash
/bin/bash X5_Crop_Mac.command
```

### File Placement And Launch

Place the entry script, platform launcher, and TIFF scans in the same folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

Main launchers:

```text
macOS:   X5_Crop_Mac.command
Windows: X5_Crop_win.bat
```

The launcher asks:

```text
format:
partial mode? [y/n, return=no]:
count:
debug analysis? [y/n, return=no]:
```

It asks for `count` only when partial mode is enabled. Press Return or type
`auto` to let the script estimate the partial count.
Detection uses a grayscale workspace; source channels, color metadata, and TIFF
DPI/PPI remain I/O and report data rather than direct crop geometry.

Auto count checks the larger allowed counts first. The program resolves one safe
short-axis span for the strip, then evaluates the frame order, boundaries, and
spacing together. It exports automatically only when the count and crop geometry
are resolved with no outstanding alternative and output protection is feasible.
Full mode may uniquely infer one
blank position from a complete sequence, but missing content is not evidence by
itself. Two blank positions or ambiguous placement remain in review, and partial
auto count never grows from a blank-looking region.

See `ARCHITECTURE.md` for internal evidence, data flow, and authority boundaries.

`--export-review` exports REVIEW crops only when geometry is resolved and output
protection is feasible. Unresolved provisional geometry or overlap protection is
never exportable.

### Formats

| Input | Format | Full-strip count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

Use `partial mode = no` when film fills the holder. Use partial mode when it does
not, including heads, tails, short scans, or cases that require automatic count
estimation. `135-dual` is intended for complete dual-lane 135 strips.

### Debug Analysis

Debug Analysis is a dry run. It detects, decides PASS/REVIEW, and writes report
and JPG analysis files, but it does not export crop TIFFs or modify originals.

Output:

```text
x5_crop_output/_debug_analysis/
```

Each JPG contains the fixed panels:

- `Original gray context`: source gray context.
- `Frame slot geometry`: shared short-axis span, ordered frame slots,
  conservative output envelopes, and final crop boxes; unresolved results are
  labeled `Provisional frame slots - NOT EXPORTABLE`.
- `Boundary and separator evidence`: raw paths/bands, measured boundaries,
  dimension hypotheses, and overlap markers.

The third panel carries a legend derived from the current diagnostics configuration:

- white dashed: `Holder boundary`;
- yellow: `Raw observation`;
- red: `Measured frame / separator edge`;
- purple dashed: `Dimension-only provisional edge`;
- blue dashed: `External safety envelope`;
- cyan: `Corroborated overlap`;
- green: `FrameSlot`;
- yellow dashed: `Sequence-inferred FrameSlot`;
- blue dashed: `FrameCropEnvelope / export-eligible final box`.

Detailed evidence, CandidateGate, and DecisionGate explanations are written to
the report. Debug Analysis remains a fixed three-panel image for fast human review.
Reports are audit artifacts, never a detection cache. Every normal crop run detects
the current TIFF; only exact, count/offset-independent measurements are reused
within that run through typed keys.

`PASS` means the file will be cropped automatically. `REVIEW` means it needs
manual review. `RUNTIME ERROR` means detection existed but a later runtime stage
failed; the run manifest records the failing stage and actual outputs.

### Output And Review

Default output folder:

```text
x5_crop_output/
```

Common contents:

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  ...
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

`x5_crop_run_manifest.jsonl` contains one terminal record per input, including
the report/debug/output files that were actually written and read-only runtime
metrics for processing, detection, assessed candidates, solver evaluations, and
exact measurement-cache lookups.

Default output bleed is 20px on the long axis and 10px on the short axis. Only
independently observed overlap, or overlap uniquely corroborated by measured
sequence edges and the remaining observed spacings, can expand the corresponding
sides of the two adjacent frames. Corroborated overlap
cannot prove its own conservation equation. Available protection is the actual geometric slack between
each base frame and its holder or lane `frame_output_bounds`. `FrameCropEnvelope`
is the conservative output envelope around one `FrameSlot` and the shared
short-axis span, before user
bleed. If either side lacks enough output space,
the result goes to review. Bleed affects final output only and cannot change
candidate geometry or Gate results.

### Command Line

Full help:

```bash
python3 X5_Crop.py --help
```

Interactive launcher flow:

```bash
python3 X5_Crop.py --interactive
```

Normal crop:

```bash
python3 X5_Crop.py . --format 135 --strip full
```

Debug Analysis dry run:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

Partial strip:

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

Disable deskew:

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off
```

Disable deskew fallback:

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew-fallback off
```

### Uninstall

X5 Crop is not a traditional app. Delete the X5 Crop folder to remove the
script, launchers, and outputs in that folder.

To remove user-level Python dependencies, run:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

The uninstallers do not remove Python itself. Removing dependencies can affect
other Python tools.

### License

This project is licensed under the MIT License. See `LICENSE`.
