# 快速启动 / Quick Start

## 中文快速启动

这是一份面向 Release 用户的快速操作卡片，用于完成第一次安装、文件摆放和启动器运行。完整的安装说明、卸载说明、命令行参数和 Debug Analysis 解释，请看 `README.md`；版本差异和开发记录请看 `CHANGELOG.md`。

> **请使用 GitHub Releases 里的 `X5-Crop-vX.X.zip`。**
>
> 不要把 GitHub 自动生成的 `Source code` / 源码压缩包给普通用户使用；源码包是开发源码结构，不是整理好的用户发布包。

> **原始 TIFF 不会被修改。**
>
> 自动裁切会生成新文件；进入 `needs_review/` 的文件也是原 TIFF 的复制粘贴，方便人工处理。

> **第一次使用请先运行安装启动器。**
>
> macOS: 双击 `install/X5_Crop_Mac_install.command`
>
> Windows: 双击 `install/X5_Crop_win_install.bat`
>
> 安装完成后，再把 `X5_Crop.py`、对应系统的主启动器和 TIFF 长图放在同一个文件夹里运行。

> **macOS 如果双击安装启动器打不开，请先用终端启动安装器。**
>
> 打开 Terminal，输入 `cd `，把 X5 Crop 文件夹拖进窗口后按 Return，然后运行：
>
> ```bash
> /bin/bash install/X5_Crop_Mac_install.command
> ```

> **macOS 如果安装完成后双击主启动器打不开，请用终端启动主启动器。**
>
> 打开 Terminal，输入 `cd `，把放有 `X5_Crop.py`、`X5_Crop_Mac.command` 和 TIFF 长图的文件夹拖进窗口后按 Return，然后运行：
>
> ```bash
> /bin/bash X5_Crop_Mac.command
> ```

### Release 包内容

Release 包默认包含：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

Release 里的 `X5_Crop.py` 是单文件发布版，已经内置内部 `x5crop/` 代码。普通用户不需要复制 `x5crop/` 文件夹。

`install/` 里的安装启动器只用于第一次安装依赖；卸载启动器用于清理用户级 Python 依赖。正式裁切时，请使用根目录里的主启动器：

```text
macOS 主启动器: X5_Crop_Mac.command
Windows 主启动器: X5_Crop_win.bat
```

### 文件摆放

把下面这些文件和要裁切的 TIFF 长图放在同一个文件夹里：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

启动器和 `X5_Crop.py` 必须在同一个文件夹里。只移动启动器、不带入口脚本，无法运行。

### 第一次使用

新机器第一次使用时，先运行安装启动器：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器会检查 Python 和依赖库。安装完成后，再运行主启动器。

如果 macOS 双击安装启动器打不开，请打开 Terminal，输入 `cd `，把 X5 Crop 文件夹拖进窗口后按 Return，然后运行：

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

如果安装完成后，双击主启动器 `X5_Crop_Mac.command` 仍然打不开，请打开 Terminal，输入 `cd `，把放有 `X5_Crop.py`、`X5_Crop_Mac.command` 和 TIFF 长图的文件夹拖进窗口后按 Return，然后运行：

```bash
/bin/bash X5_Crop_Mac.command
```

### 启动方式

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

启动器会依次询问：

```text
format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

### Format 输入

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

`partial mode = no` 时，脚本认为这是一条完整片条，会使用对应 format 的固定张数：

```text
135 = 6
135-dual = 12
half = 12
xpan = 3
645 = 4
66 = 3
67 = 3
```

只有下面这些情况才建议输入 `y`：

- 片头或片尾。
- 只扫到一部分片条。
- 片夹没有被照片铺满。
- 你明确想让脚本自动判断这条里有几张。

开启 partial mode 后，脚本会用 auto count，并且判断更保守。它不是普通完整片条的推荐模式；完整片条请保持 `no`，这样速度和稳定性都更好。

### debug analysis

通常直接回车，等于 `no`。

输入 `y` 会进入 Debug Analysis dry run：

- 不会正式导出裁切 TIFF。
- 会生成 Debug Analysis JPG。
- 会生成 report，之后可以复用分析结果进行裁切。

这里的 `dry run` 是试运行 / 分析模式：脚本会读取 TIFF、执行检测并判断 PASS/REVIEW，但不会导出正式裁切 TIFF，也不会修改原 TIFF。它适合在正式裁切前先检查外框、分隔线和裁切范围。

普通非 Debug Analysis 裁切不会生成 report。

### needs_review 目录

低置信或困难图片会进入复核流程，必要时原 TIFF 会被复制到：

```text
split_output/needs_review/
```

这里的文件是原 TIFF 的复制粘贴。脚本没有对这些复制进去的 TIFF 做裁切、压缩、改色、校平或其它处理。你可以放心在 `needs_review/` 里手动检查、移动、删除或另行处理这些副本。

### 输出位置

脚本会在当前文件夹生成：

```text
split_output/
```

高置信结果会自动裁切。低置信或困难图片会进入复核流程。

默认输出 bleed 是长轴 20px、短轴 10px。如果检测到叠片 / 近似叠片 / 连续内容风险，输出长轴 bleed 会自动提高到 50px；这只影响最终输出范围，不参与检测评分。

### 终端暂时没有新提示

通常不是卡住。大 TIFF 在读取、检测、校平或写入时，终端可能一段时间没有新文字。

最近一次普通 135 启动器实测：48 张 TIFF 全量正式裁切用时 394 秒，平均约 8.2 秒/张。Debug Analysis 通常每张约 10-30 秒。更大的 TIFF、开启 deskew、较慢硬盘或较慢电脑会更久。

### 卸载

X5 Crop 不是 App。脚本本体没有系统级安装，也不会写入应用支持目录。删除 X5 Crop 文件夹就能移除脚本、启动器和这个文件夹里的输出。

如果想同时清理安装过的 Python 依赖，可以运行：

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

卸载脚本只会尝试卸载当前用户 Python 里的 `numpy`、`tifffile`、`imagecodecs`、`Pillow`，并可选清理 pip 下载缓存。它不会自动卸载 Python。卸载 Python 或这些依赖可能影响其它 Python 脚本，请确认没有其它工具依赖它们后再清理。

## English Quick Start

This is a quick operation card for Release users. It covers first-time setup, file placement, and launcher use. For full installation, uninstall, command-line options, and Debug Analysis details, see `README.md`; for version differences and development history, see `CHANGELOG.md`.

> **Use `X5-Crop-vX.X.zip` from GitHub Releases.**
>
> Do not give normal users the auto-generated GitHub `Source code` zip; that is the development source layout, not the prepared user package.

> **Original TIFF files are not modified.**
>
> Auto crops are written as new files; files in `needs_review/` are plain copies of the source TIFFs for manual handling.

> **On first use, run the installer launcher first.**
>
> macOS: double-click `install/X5_Crop_Mac_install.command`
>
> Windows: double-click `install/X5_Crop_win_install.bat`
>
> After installation, put `X5_Crop.py`, the main launcher for your system, and the TIFF long-strip scans in the same folder.

> **On macOS, if double-clicking the installer does not work, start the installer from Terminal first.**
>
> Open Terminal, type `cd `, drag the X5 Crop folder into the window, press Return, then run:
>
> ```bash
> /bin/bash install/X5_Crop_Mac_install.command
> ```

> **On macOS, if the main launcher still will not open after installation, start the main launcher from Terminal.**
>
> Open Terminal, type `cd `, drag the folder containing `X5_Crop.py`, `X5_Crop_Mac.command`, and the TIFF scans into the window, press Return, then run:
>
> ```bash
> /bin/bash X5_Crop_Mac.command
> ```

### Release Package Contents

The Release package normally contains:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

The Release `X5_Crop.py` is a standalone file with the internal `x5crop/` code
embedded. Normal users do not need to copy an `x5crop/` folder.

Installer launchers inside `install/` are only for first-time dependency setup. Uninstall launchers remove user-level Python dependencies. For actual cropping, use the main launcher in the root folder:

```text
macOS main launcher: X5_Crop_Mac.command
Windows main launcher: X5_Crop_win.bat
```

### File Placement

Put these files in the same folder as the TIFF long-strip scans:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

The launcher and `X5_Crop.py` must stay together in the same folder. A launcher by itself cannot run the script.

### First Use

On a new machine, run the installer launcher first:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

The installer checks Python and required libraries. After installation, run the main launcher.

If double-clicking the macOS installer does not work, open Terminal, type
`cd `, drag the X5 Crop folder into the window, press Return, then run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

If the main launcher `X5_Crop_Mac.command` still will not open after
installation, open Terminal, type `cd `, drag the folder containing
`X5_Crop.py`, `X5_Crop_Mac.command`, and the TIFF scans into the window, press
Return, then run:

```bash
/bin/bash X5_Crop_Mac.command
```

### Launch

```text
macOS:   Double-click X5_Crop_Mac.command
Windows: Double-click X5_Crop_win.bat
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

When `partial mode = no`, the script treats the scan as a complete strip and uses the fixed frame count for the selected format:

```text
135 = 6
135-dual = 12
half = 12
xpan = 3
645 = 4
66 = 3
67 = 3
```

Use `y` only for:

- leader or tail scans.
- incomplete strips.
- holders that are not filled by frames.
- cases where you intentionally want the script to decide the frame count automatically.

With partial mode enabled, the script uses auto count and behaves more conservatively. It is not recommended for normal complete strips; keep it at `no` for better speed and stability.

### Debug Analysis

Usually press Return, which means `no`.

Type `y` for Debug Analysis dry run:

- It does not export cropped TIFF files.
- It writes Debug Analysis JPGs.
- It writes reports that can be reused later for cropping.

Here, `dry run` means test/analyze only: the script reads the TIFF, runs
detection, and decides PASS/REVIEW, but does not export cropped TIFFs and does
not modify the original TIFF. Use it before real export to inspect the outer
box, separators, and crop boxes.

Normal non-Debug-Analysis crop runs do not write reports.

### needs_review Folder

Low-confidence or difficult scans may be copied to:

```text
split_output/needs_review/
```

Files in this folder are plain copies of the original TIFF files. The script does not crop, compress, recolor, deskew, or otherwise process those copied TIFFs. You can safely inspect, move, delete, or manually process the copies in `needs_review/`.

### Output Location

The script creates:

```text
split_output/
```

High-confidence results are cropped automatically. Low-confidence or difficult scans go to review.

Default output bleed is 20px on the long axis and 10px on the short axis. When overlap, near-overlap, or continuous-content risk is detected, long-axis output bleed is automatically raised to 50px. This affects final output only, not detection scoring.

### No New Terminal Text

This usually does not mean the script is stuck. Large TIFF files can take time to read, detect, deskew, or write.

The latest normal 135 launcher measurement was 394 seconds for 48 TIFF files, or about 8.2 seconds per file. Debug Analysis usually takes about 10-30 seconds per file. Larger TIFF files, deskew, slower disks, or slower computers can take longer.

### Uninstall

X5 Crop is not an app. The script itself has no system-level app install and does not write to application-support folders. Delete the X5 Crop folder to remove the script, launchers, and outputs in that folder.

To also remove Python dependencies installed for X5 Crop, run:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

The uninstall helper only tries to remove `numpy`, `tifffile`, `imagecodecs`, and `Pillow` from the current user's Python, and can optionally purge the pip download cache. It does not uninstall Python itself. Removing Python or these packages may affect other Python scripts, so only remove them if you are sure no other tool needs them.
