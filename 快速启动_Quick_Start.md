# 快速启动 / Quick Start

## 中文快速启动

这是 X5 Crop 的最短使用说明。更完整的安装、参数、Debug Analysis 和版本变化，请看 `README.md` 和 `CHANGELOG.md`。

### Release 压缩包里有什么

Release 包默认包含：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
```

### 放在哪里

把下面这些文件和要裁切的 TIFF 长图放在同一个文件夹里：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

启动器和 `X5_Crop.py` 必须在同一个文件夹里。只移动启动器、不带脚本本体，不能运行。

### 怎么启动

macOS:

```text
双击 X5_Crop_Mac.command
```

Windows:

```text
双击 X5_Crop_win.bat
```

启动器会依次询问：

```text
format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

### format 怎么填

```text
直接回车 或 135 = 普通 135，一条 6 张
dual 或 135 dual = 双条 135，一共 12 张
xpan = XPAN，一条 3 张
half = 半格，一条 12 张
645 = 120-645，一条 4 张
66 = 120-66，一条 3 张
67 = 120-67，一条 3 张
```

如果打错 format，启动器会让你重新输入。

### partial mode

通常直接回车，等于 `no`。

只有片头、片尾、不完整片条，或者你明确想让脚本自动判断张数时，才输入 `y`。

### debug analysis

通常直接回车，等于 `no`。

输入 `y` 会进入 Debug Analysis dry run：

- 不会正式导出裁切 TIFF。
- 会生成 Debug Analysis JPG。
- 会生成 report，之后可以复用分析结果进行裁切。

普通非 Debug Analysis 裁切不会生成 report。

### 输出在哪里

脚本会在当前文件夹生成：

```text
split_output/
```

高置信结果会自动裁切。低置信或困难图片会进入复核流程，必要时会复制原 TIFF 到 `needs_review/`。

### 运行时没有新提示是不是卡住了

通常不是。大 TIFF 在读取、检测、校平或写入时，终端可能一段时间没有新文字。

常见 135 长图通常每张约 5-15 秒；Debug Analysis 通常每张约 10-30 秒。更大的 TIFF、开启 deskew、较慢硬盘或较慢电脑会更久。

### 新机器缺少依赖怎么办

如果启动器提示找不到可用 Python 或缺少依赖，请看 `README.md` 里的安装依赖说明。

仓库源码里有安装器，但安装器不放进 Release 压缩包。也可以手动安装：

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

## English Quick Start

This is the shortest guide for X5 Crop. For full installation notes, command-line options, Debug Analysis details, and version history, see `README.md` and `CHANGELOG.md`.

### What Is In The Release Zip

The Release package normally contains:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
```

### Where To Put The Files

Put these files in the same folder as the TIFF long-strip scans:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

The launcher and `X5_Crop.py` must stay together in the same folder. A launcher by itself cannot run the script.

### How To Launch

macOS:

```text
Double-click X5_Crop_Mac.command
```

Windows:

```text
Double-click X5_Crop_win.bat
```

The launcher asks:

```text
format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

### Film Format Choices

```text
Return or 135 = normal 135, 6 frames
dual or 135 dual = dual-strip 135, 12 frames total
xpan = XPAN, 3 frames
half = half-frame, 12 frames
645 = 120-645, 4 frames
66 = 120-66, 3 frames
67 = 120-67, 3 frames
```

If you mistype the format, the launcher will ask again.

### Partial Mode

Usually press Return, which means `no`.

Use `y` only for leader, tail, incomplete strips, or when you intentionally want the script to decide the frame count automatically.

### Debug Analysis

Usually press Return, which means `no`.

Type `y` for Debug Analysis dry run:

- It does not export cropped TIFF files.
- It writes Debug Analysis JPGs.
- It writes reports that can be reused later for cropping.

Normal non-Debug-Analysis crop runs do not write reports.

### Output Folder

The script creates:

```text
split_output/
```

High-confidence results are cropped automatically. Low-confidence or difficult scans go to review, and the original TIFF may be copied to `needs_review/`.

### No New Terminal Text

This usually does not mean the script is stuck. Large TIFF files can take time to read, detect, deskew, or write.

Typical 135 long-strip scans take about 5-15 seconds per file. Debug Analysis usually takes about 10-30 seconds per file. Larger TIFF files, deskew, slower disks, or slower computers can take longer.

### Missing Dependencies On A New Machine

If the launcher says no usable Python was found or dependencies are missing, see the dependency installation section in `README.md`.

Installer launchers exist in the source repository, but they are not included in the Release zip. You can also install dependencies manually:

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```
