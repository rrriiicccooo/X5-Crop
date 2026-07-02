# 快速启动 / Quick Start

本文件是面向 Release 用户的快速操作指南，覆盖首次安装、文件摆放和启动器选择。
完整说明请参阅 `README.md` 或 Release 包里的 `README.txt`。

This is the short operation guide for Release users. It covers first install,
file placement, and launcher choices. For full details, read `README.md` or
`README.txt` in the Release package.

## 中文快速启动

### 1. 下载 Release 包

从 GitHub Releases 下载 `X5-Crop-vX.X.zip`。

不要下载 GitHub 自动生成的 `Source code` 压缩包；该压缩包是开发源码结构，
不是用户发布包。

### 2. 安装依赖

解压后运行安装启动器：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

macOS 如果无法通过双击打开安装器，打开 Terminal，输入 `cd `，将 X5 Crop
文件夹拖入窗口，按 Return，然后运行：

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

### 3. 文件摆放

将以下文件和要裁切的 TIFF 长图放在同一个文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

启动器和 `X5_Crop.py` 必须位于同一个文件夹。单独移动启动器无法运行。

### 4. 启动

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

如果 macOS 主启动器无法通过双击打开，在同一个 TIFF 文件夹里运行：

```bash
/bin/bash X5_Crop_Mac.command
```

### 5. 选择格式

| 输入 | 格式 | 完整片条张数 |
|---|---|---:|
| 回车 / `135` | 普通 135 | 6 |
| `dual` / `135 dual` / `135-dual` | 双条 135 | 12 |
| `half` | 半格 | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

### 6. partial mode

完整片条：按 Return，保持 `no`。

片头、片尾、局部片条、片夹没有铺满：输入 `y`。

开启 partial mode 后会询问 `count`。按 Return 或输入 `auto` 表示自动判断张数；
也可以输入当前格式允许的具体张数。

### 7. Debug Analysis

默认按 Return，保持 `no`。

输入 `y` 会进入试运行：

- 不导出正式裁切 TIFF。
- 生成 Debug Analysis JPG。
- 生成 `x5_crop_report.jsonl` 和 `x5_crop_summary.csv`。

适合正式裁切前检查外框、分隔线和裁切范围。

### 8. 输出和复核

输出目录：

```text
x5_crop_output/
```

高置信结果会导出为新的单张 TIFF。低置信或困难图片会进入：

```text
x5_crop_output/needs_review/
```

`needs_review/` 里的文件是原始 TIFF 副本。原始 TIFF 不会被修改。

自动裁切输出会保留原 TIFF 的位深、通道结构、ICC / 色彩空间、resolution 和
metadata。裁切不会主动降位深、改色、压缩或重采样。

### 9. 卸载

删除 X5 Crop 文件夹即可移除脚本和本文件夹里的输出。

如需清理用户级 Python 依赖，运行：

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

## English Quick Start

### 1. Download Release Package

Download `X5-Crop-vX.X.zip` from GitHub Releases.

Do not use GitHub's auto-generated `Source code` zip. That is the development
source layout, not the user package.

### 2. Install Dependencies

After unzipping, run the installer:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

If macOS does not open the installer by double-clicking, open Terminal, type
`cd `, drag the X5 Crop folder into the window, press Return, then run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

### 3. File Placement

Put these files and the TIFF scans in the same folder:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

The launcher and `X5_Crop.py` must stay together. A launcher moved by itself
cannot run.

### 4. Launch

```text
macOS:   double-click X5_Crop_Mac.command
Windows: double-click X5_Crop_win.bat
```

If macOS does not open the launcher by double-clicking, run this inside the same
TIFF folder:

```bash
/bin/bash X5_Crop_Mac.command
```

### 5. Choose Format

| Input | Format | Full-strip count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

### 6. Partial Mode

Complete strip: press Return and keep `no`.

Head, tail, short scan, or holder not filled: type `y`.

When partial mode is enabled, the launcher asks for `count`. Press Return or
type `auto` to let the script estimate it. You can also enter a valid count for
the selected format.

### 7. Debug Analysis

Default: press Return and keep `no`.

Type `y` for a dry run:

- It does not export final crop TIFFs.
- It writes Debug Analysis JPGs.
- It writes `x5_crop_report.jsonl` and `x5_crop_summary.csv`.

Use it before final cropping to inspect the outer box, separators, and crop
range.

### 8. Output And Review

Output folder:

```text
x5_crop_output/
```

High-confidence results are exported as new TIFF files. Weak or difficult files
go to:

```text
x5_crop_output/needs_review/
```

Files in `needs_review/` are source-TIFF copies. Original TIFF files are not
modified.

Auto-cropped TIFF output preserves source bit depth, channel layout, ICC /
color space, resolution, and metadata. Cropping does not intentionally lower bit
depth, recolor, compress, or resample.

### 9. Uninstall

Delete the X5 Crop folder to remove the script and outputs in that folder.

To remove user-level Python dependencies, run:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
