# X5 Crop

X5 Crop is a standalone Python script for splitting long TIFF film-strip scans
from Hasselblad / Imacon X5 holders into individual TIFF frames.

当前版本：V3.3.2

Current version: V3.3.2

## 中文说明

### 这个工具做什么

X5 Crop 会处理同一个文件夹里的 `.tif` / `.tiff` 长图，并把高置信结果自动裁切成单张 TIFF。低置信结果不会自动裁切，会写入报告并复制原 TIFF 到 `needs_review/`，方便人工复核。

核心原则：

- 容易样片自动裁切。
- 困难样片进入复核。
- 只有高置信检测结果才自动导出。
- 不为了让困难图片通过而放宽置信规则。
- 最终裁切 TIFF 尽量保持原 TIFF 的画质和元数据属性。

脚本会在你指定的胶片格式和片条模式内，综合外框、分隔、内容和画幅几何证据评分。最终只有高置信结果会自动导出；证据不足、证据互相冲突或画幅状态异常时会进入复核。

当前默认行为：

- 检测阶段不使用 bleed；bleed 只在最终输出和 Debug Analysis 色块里应用。
- 默认输出 bleed 为长轴 20px、短轴 10px。横向长图是左右各 20px、上下各 10px；竖向长图会自动对应旋转。
- 对已经 `approved_auto` 且没有复核原因的结果，会做一个很小的输出几何 polish：只允许长轴最多向外微扩。这一步不改变 PASS/REVIEW 和置信度。
- 对近似叠片、片距局部不稳定、分隔证据不足或内容证据冲突的长图，会保持保守判断，不会为了自动导出而放宽置信规则。

### 下载和文件摆放

推荐从 GitHub Release 下载最新的 `X5-Crop-v3.3.x.zip`。解压后，常用文件是：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
README.md
LICENSE
```

把 `X5_Crop.py`、对应系统的启动器和要裁切的 TIFF 长图放在同一个文件夹里，然后双击启动器运行。

不支持“只把启动器放进 TIFF 文件夹、脚本留在别处”的模式。

### 第一次安装依赖

第一次在新机器上使用时，先运行安装启动器。

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

安装器会使用用户级安装方式安装依赖：

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

这样脚本文件夹可以自由移动，依赖跟随当前用户的 Python，不绑在项目路径上。

macOS 如果遇到新版 Python / Homebrew 的 externally-managed 限制，安装器会提示是否用 `--break-system-packages --user` 重试。这里仍然是用户级安装。

如果机器没有 Python：

- macOS：安装器会优先使用 Homebrew 安装 Python；如果没有 Homebrew，会打开 Python 官网。
- Windows：安装器会优先使用 `winget` 安装 Python 3.12；如果没有 `winget`，会打开 Python 官网。

### 启动器怎么用

macOS:

```text
X5_Crop_Mac.command
```

Windows:

```text
X5_Crop_win.bat
```

启动器会依次询问：

```text
choose film format:
  return or 135 = 135
  dual or 135 dual = 135-dual
  xpan = xpan
  half = half-frame
  645 = 120-645
  66 = 120-66
  67 = 120-67

format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

格式输入：

| 输入 | 格式 |
|---|---|
| 直接回车 / `135` | `135` |
| `dual` / `135 dual` / `135-dual` | 双条 135 |
| `xpan` | XPAN |
| `half` | 半格 |
| `645` | 120-645 |
| `66` | 120-66 |
| `67` | 120-67 |

如果输错格式，启动器会重新让你输入。`partial mode` 和 `debug analysis` 可以输入 `yes` / `no` / `y` / `n`，直接回车等于 `no`。

不开启 partial 时，脚本按完整片条处理，并固定张数：

| 格式 | 张数 |
|---|---:|
| `135` | 6 |
| `135-dual` | 12 |
| `half` | 12 |
| `xpan` | 3 |
| `120-645` | 4 |
| `120-66` | 3 |
| `120-67` | 3 |

开启 partial 时，张数使用 auto，适合片头、片尾、局部片条或没有铺满整条片夹的扫描。`135-dual` 目前只建议用于完整双条 135；partial 下会保守复核。

### Debug Analysis

如果开启 Debug Analysis，脚本只生成分析 JPG 和报告，不输出裁切 TIFF。输出位置：

```text
split_output/_debug_analysis/
```

每张 Debug Analysis JPG 是四联图：

- `Original gray`：原始灰度图。
- `Debug boxes`：外框和最终输出裁切范围。
- `Separator evidence`：分隔证据。
- `Content evidence`：内容证据。

横向长图会把四联图上下排列；竖向长图会横向排列，方便最大化利用屏幕空间。

顶部状态栏会显示：

```text
PASS confidence 0.987 >= threshold 0.850
REVIEW confidence 0.676 < threshold 0.850
```

`PASS` 表示会自动裁切；`REVIEW` 表示不会自动裁切，需要人工复核。

`Debug boxes` 颜色：

| 颜色 | 含义 |
|---|---|
| 绿色外框 | 脚本认为整条胶片有效区域的外框 |
| 不同半透明色块 | 每一张最终输出裁切范围，包含输出 bleed |

`Separator evidence` 颜色：

| 颜色 | 含义 |
|---|---|
| 红色框 / 红色线 | 原图中检测到的真实分隔区域，包括黑条和可信双边缘 |
| 橙色框 / 橙色线 | 增强分隔证据层补充检测到的分隔区域 |
| 黄色短 tick | grid / 全局片距模型推算出的切线，不代表一定看到真实黑条 |
| 紫色短 tick | 证据不足时的等分或 fallback 切线 |
| 白色短 tick | 其它未分类切线来源 |

看 Debug Analysis 时建议优先检查：

- 绿色外框有没有吃进画面或把白边留太多。
- 半透明裁切色块有没有覆盖照片并留出合理 bleed。
- 红色分隔证据是否落在真实黑条或真实片间空隙。
- 黄色 / 紫色 tick 是否只是模型猜测。

### 复用 Debug Analysis 结果裁切

如果已经对同一批 TIFF 跑过 Debug Analysis dry run，之后普通裁切时脚本会优先复用 `split_report.jsonl`：

- `approved_auto` 会跳过重新检测，直接按报告里的裁切框导出 TIFF。
- `needs_review` 会直接跳过，不会重新检测后碰运气裁切。
- 如果原 TIFF 的文件大小、修改时间、页码、图像形状、脚本版本或关键参数不匹配，会自动重新检测。
- 如果 Debug Analysis 那次做过 deskew，复用时会按同一角度重新旋转后再裁切，避免裁切框偏移。

命令行可用 `--no-reuse-analysis` 强制重新检测。

### 输出目录

默认输出在 TIFF 文件夹内：

```text
split_output/
```

常见内容：

```text
split_output/
  split_report.jsonl
  split_summary.csv
  *_01.tif
  *_02.tif
  ...
  _debug_analysis/
    *_debug_analysis.jpg
  needs_review/
```

说明：

- `split_report.jsonl`：完整机器可读报告。
- `split_summary.csv`：方便人工浏览的表格。
- `_debug_analysis/*_debug_analysis.jpg`：四联 Debug Analysis 图。
- `needs_review/`：低置信原 TIFF 复核目录。

普通启动器不会覆盖已有裁切 TIFF。命令行可用 `--overwrite` 覆盖。

### 命令行

Debug Analysis dry run:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

普通自动裁切：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

片头 / 局部片条：

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

关闭并行：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --jobs 1
```

默认并行最多处理 2 张 TIFF。报告仍由主进程写入，避免多个 worker 同时写报告文件。

调整输出 bleed：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 20 --bleed-y 10
```

`--bleed-x` 是长轴 bleed，`--bleed-y` 是短轴 bleed。

关闭自动校斜：

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off --report --debug-analysis --dry-run
```

低置信结果也强制导出：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --export-review
```

### License

本项目以 MIT License 开源，详见 `LICENSE`。

## English Guide

### What This Tool Does

X5 Crop processes `.tif` / `.tiff` long film-strip scans in the same folder and
exports individual TIFF frames only when the detection confidence is high.
Low-confidence files are reported as `needs_review` and the original TIFF is
copied to `needs_review/` for manual inspection.

Core rules:

- Easy scans are cropped automatically.
- Difficult scans are sent to review.
- Only high-confidence detections are exported automatically.
- Fallbacks must not make difficult images pass by accident.
- Output TIFF quality and metadata behavior should stay as close to the source
  TIFF as possible.

X5 Crop scores candidates inside the film format and strip mode you choose,
using outer-frame geometry, separator evidence, content evidence, and expected
aspect ratios together. Only high-confidence results are exported
automatically. Weak, conflicting, or unusual cases are sent to review.

V3.3.2 keeps bleed outside detection:

- Detection uses no bleed when scoring outer boxes, gaps, confidence, or
  PASS/REVIEW.
- Output bleed defaults to 20px on the long axis and 10px on the short axis.
- Horizontal strips use 20px left/right and 10px top/bottom. Vertical strips are
  rotated accordingly.
- A small PASS-only geometry polish may slightly expand long-axis output edges.
  It does not change confidence or PASS/REVIEW.
- Overlapped frames, irregular frame spacing, weak separators, or conflicting
  content evidence are handled conservatively. The script should not loosen
  confidence rules just to export automatically.

### Download And Layout

Download the latest `X5-Crop-v3.3.x.zip` from GitHub Releases. After unzipping, the common
files are:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
README.md
LICENSE
```

Put `X5_Crop.py`, the launcher for your system, and the TIFF scans in the same
folder. Then double-click the launcher.

The launcher-only workflow is not supported. The launcher and `X5_Crop.py` must
travel together.

### Install Dependencies

On a new machine, run the installer first.

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

The installer uses user-level Python packages:

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

This keeps the project folder movable. Dependencies belong to the current
user's Python installation, not to this folder.

### Launcher Flow

macOS:

```text
X5_Crop_Mac.command
```

Windows:

```text
X5_Crop_win.bat
```

The launcher asks:

```text
format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

Format choices:

| Input | Format |
|---|---|
| Return / `135` | `135` |
| `dual` / `135 dual` / `135-dual` | dual-strip 135 |
| `xpan` | XPAN |
| `half` | half-frame |
| `645` | 120-645 |
| `66` | 120-66 |
| `67` | 120-67 |

Unknown formats are rejected and the launcher asks again. For `partial mode` and
`debug analysis`, use `yes` / `no` / `y` / `n`; Return means `no`.

Full-strip mode uses fixed frame counts:

| Format | Count |
|---|---:|
| `135` | 6 |
| `135-dual` | 12 |
| `half` | 12 |
| `xpan` | 3 |
| `120-645` | 4 |
| `120-66` | 3 |
| `120-67` | 3 |

Partial mode uses auto count and is intended for leader, tail, partial strips,
or scans that do not fill the whole holder.

### Debug Analysis

Debug Analysis is a dry run. It writes analysis JPGs and reports, but no cropped
TIFFs.

Each Debug Analysis JPG has four panels:

- `Original gray`: original grayscale detection image.
- `Debug boxes`: outer box and final output crop boxes.
- `Separator evidence`: separator evidence.
- `Content evidence`: content evidence.

Horizontal strips are stacked vertically; vertical strips are laid out
horizontally.

The top status line shows either `PASS` or `REVIEW`. `PASS` means the file would
be cropped automatically. `REVIEW` means it will not be auto-exported.

`Debug boxes` colors:

| Color | Meaning |
|---|---|
| Green outer box | Detected usable film-strip area |
| Semi-transparent color blocks | Final output crop boxes, including output bleed |

`Separator evidence` colors:

| Color | Meaning |
|---|---|
| Red box / line | Real separator evidence detected from the original image |
| Orange box / line | Separator evidence added by the enhanced separator layer |
| Yellow tick | Grid / pitch-model cut line, not necessarily a visible separator |
| Purple tick | Equal/fallback cut line with weak evidence |
| White tick | Other separator source |

### Reusing Debug Analysis For Export

If you run Debug Analysis first and then run normal export with the same key
settings, X5 Crop reuses `split_report.jsonl`:

- `approved_auto` files are cropped from the cached crop boxes.
- `needs_review` files are skipped.
- Changed TIFF size, modification time, page shape, script version, or key
  parameters will force a fresh detection.
- If Debug Analysis used deskew, export reuses the same angle before cropping.

Use `--no-reuse-analysis` to force a fresh detection.

### Command Line

Debug Analysis dry run:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

Normal auto export:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial strip:

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

Disable parallel processing:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --jobs 1
```

Set output bleed:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 20 --bleed-y 10
```

Disable deskew:

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off --report --debug-analysis --dry-run
```

Force export of review files:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --export-review
```

### Output Folder

Default output:

```text
split_output/
```

Common contents:

```text
split_output/
  split_report.jsonl
  split_summary.csv
  *_01.tif
  *_02.tif
  ...
  _debug_analysis/
    *_debug_analysis.jpg
  needs_review/
```

### License

This project is open source under the MIT License. See `LICENSE`.
