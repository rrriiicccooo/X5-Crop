# X5 Crop

> **下载提示 / Download Notice**
>
> 普通用户请从 GitHub **Releases** 下载整理好的 `X5-Crop-vX.X.zip`。
> 不要下载 GitHub 自动生成的 **Source code** 压缩包；该压缩包是开发源码结构，
> 不是面向日常使用整理的发布包。
>
> Regular users should download the prepared `X5-Crop-vX.X.zip` from GitHub
> **Releases**. Do not use GitHub's auto-generated **Source code** archives;
> those are development source trees, not user-ready release packages.

X5 Crop 是用于 Hasselblad / Imacon X5 胶片片夹长图的 TIFF 自动裁切工具。
它会将同一文件夹里的长条 TIFF 扫描图拆成单张 TIFF。只有高置信结果会自动导出；
低置信或证据冲突的图片会进入复核。

X5 Crop is a TIFF cropper for long film-strip scans from Hasselblad / Imacon X5
holders. It splits long-strip TIFF scans into individual TIFF frames. Only
high-confidence detections are exported automatically; weak or conflicting cases
are sent to review.

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
- 检测阶段保持保守；证据不足、证据冲突、疑似叠片或局部片距异常时进入复核。
- 当前 active policy 更保守；旧版本可 PASS 的困难图片如果
  证据组合不足，可能改为 `REVIEW`。

### 推荐下载

普通用户请下载 GitHub Releases 里的 `X5-Crop-vX.X.zip`。Release 包通常包含：

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
普通用户不需要复制 `x5crop/` 文件夹。

如果直接从仓库 `main` 分支运行，根目录 `X5_Crop.py` 是开发入口，需要旁边的
`x5crop/` 包。这是开发和测试结构，不是普通用户发布包。

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

完整片条请保持 `partial mode = no`。该模式通常更快，也更稳定。

建议开启 partial mode 的情况：

- 片头或片尾。
- 只扫到局部片条。
- 片夹没有被照片铺满。
- 你明确想让脚本自动判断这条里有几张。

`135-dual` 主要用于完整双条 135；partial 下会倾向复核。

### Debug Analysis

Debug Analysis 是试运行 / 分析模式。它会读取 TIFF、执行检测、判断 PASS/REVIEW，
并写出分析图和报告，但不会导出正式裁切 TIFF，也不会修改原 TIFF。

输出位置：

```text
x5_crop_output/_debug_analysis/
```

每张 Debug Analysis JPG 的面板由 runtime diagnostics policy 控制，默认包含：

- `Original gray context`: 原始灰度上下文。
- `Debug boxes`: 当前 outer、frame 和裁切框。
- `Separator evidence`: 分隔证据、当前 outer 和切线标记。

详细 evidence / risk / decision 说明写入 report；Debug Analysis
默认保持三联图，优先服务人工快速读图。

状态含义：

- `PASS`: 会自动裁切。
- `REVIEW`: 不会自动裁切，需要人工复核。

看图时优先检查：

- 绿色外框是否裁入画面，或保留过多白边。
- 半透明裁切色块是否覆盖照片并留出合理 bleed。
- 红色分隔证据是否落在真实片间空隙或真实黑条。
- 黄色 / 紫色 tick 是否只是模型补位。

普通非 Debug Analysis 裁切不会生成报告。同一批 TIFF 已执行 Debug Analysis 后，
普通裁切时可复用匹配的 `x5_crop_report.jsonl`；如果文件大小、修改时间、图像形状、
脚本版本或关键参数不匹配，会自动重新检测。

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
```

说明：

- 自动裁切 TIFF 是新文件，会保留原 TIFF 的画质相关属性。
- `needs_review/` 存放需要人工处理的原 TIFF 副本。
- `x5_crop_report.jsonl` 是机器可读报告。
- `x5_crop_summary.csv` 是便于人工浏览的摘要表。
- 普通启动器不会覆盖已有裁切 TIFF；命令行可用 `--overwrite` 覆盖。

默认输出 bleed 为长轴 20px、短轴 10px。若检测到叠片、近似叠片或连续内容风险，
输出长轴 bleed 会提高到 50px。这个调整只影响最终输出范围，不参与检测评分。

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

关闭并行：

```bash
python3 X5_Crop.py . --format 135 --strip full --jobs 1
```

低置信结果也强制导出：

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
- Detection stays conservative. Weak evidence, conflicting evidence, possible
  overlap, or unstable local spacing goes to review.
- The current active policy is more conservative. Difficult files
  that passed in older development versions may now go to `REVIEW` when
  combined evidence is insufficient.

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

Use `partial mode = no` for complete strips. Use partial mode for heads, tails,
short scans, holders that are not filled, or cases that require automatic count
estimation. `135-dual` is intended for complete dual-lane 135 strips.

### Debug Analysis

Debug Analysis is a dry run. It detects, decides PASS/REVIEW, and writes report
and JPG analysis files, but it does not export crop TIFFs or modify originals.

Output:

```text
x5_crop_output/_debug_analysis/
```

Each JPG is controlled by runtime diagnostics policy and defaults to:

- `Original gray context`: source gray context.
- `Debug boxes`: current outer, frames, and crop boxes.
- `Separator evidence`: separator evidence, current outer, and cut markers.

Detailed evidence / risk / decision explanations are written to the
report. Debug Analysis defaults to a three-panel image for fast human review.

`PASS` means the file will be cropped automatically. `REVIEW` means it needs
manual review.

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
```

Default output bleed is 20px on the long axis and 10px on the short axis. When
overlap, near-overlap, or continuous-content risk is detected, long-axis output
bleed is raised to 50px. This affects final output geometry only, not detection
scoring.

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
