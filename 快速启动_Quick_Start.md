# 快速启动 / Quick Start

## 中文快速启动

这是 X5 Crop 的最短使用说明。更完整的安装、参数、Debug Analysis 和版本变化，请看 `README.md` 和 `CHANGELOG.md`。

> 如果双击安装启动器打不开，请打开 Terminal，输入 `cd `，把 X5 Crop 文件夹拖进窗口后按 Return，然后运行：
>
> ```bash
> /bin/bash install/X5_Crop_Mac_install.command
> ```
>
> **macOS 如果双击安装启动器打不开，请先用终端启动安装器。**

> **第一次使用请先运行安装启动器。**
>
> macOS: 双击 `install/X5_Crop_Mac_install.command`
>
> Windows: 双击 `install/X5_Crop_win_install.bat`
>
> 安装完成后，再把 `X5_Crop.py`、对应系统的主启动器和 TIFF 长图放在同一个文件夹里运行。

### Release 压缩包里有什么

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
```

`install/` 只用于第一次安装依赖。正式裁切时使用根目录里的主启动器：

```text
macOS 主启动器: X5_Crop_Mac.command
Windows 主启动器: X5_Crop_win.bat
```

### 放在哪里

把下面这些文件和要裁切的 TIFF 长图放在同一个文件夹里：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

启动器和 `X5_Crop.py` 必须在同一个文件夹里。只移动启动器、不带脚本本体，不能运行。

对应系统的主启动器是：

```text
macOS 主启动器: X5_Crop_Mac.command
Windows 主启动器: X5_Crop_win.bat
```

### 第一次使用

新机器第一次使用时，先运行安装启动器：

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

安装器会检查 Python 和依赖库。安装完成后，再运行主启动器。

macOS 安装器还会尝试为当前 Release 文件夹里的主启动器添加执行权限，并移除下载隔离标记。它不能把脚本永久加入 macOS 的全局可信名单。

安装后，可以把 `X5_Crop.py` 和对应系统的主启动器作为一对复制到不同的 TIFF 文件夹里使用：

```text
macOS: X5_Crop.py + X5_Crop_Mac.command
Windows: X5_Crop.py + X5_Crop_win.bat
```

不要只移动主启动器，因为主启动器必须和 `X5_Crop.py` 放在同一个文件夹里。

如果重新下载、重新解压，或者从网页、网盘、聊天软件又拿到一份新的 Release，那一份新文件夹可能重新带有 macOS 下载隔离标记。请在新的文件夹里再运行一次安装启动器。

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

Release 包里的 `install/` 文件夹有安装器。也可以手动安装：

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

## English Quick Start

This is the shortest guide for X5 Crop. For full installation notes, command-line options, Debug Analysis details, and version history, see `README.md` and `CHANGELOG.md`.

> **On macOS, if double-clicking the installer does not work, start the installer from Terminal first.**
>
> Open Terminal, type `cd `, drag the X5 Crop folder into the window, press Return, then run:
>
> ```bash
> /bin/bash install/X5_Crop_Mac_install.command
> ```

> **On first use, run the installer launcher first.**
>
> macOS: double-click `install/X5_Crop_Mac_install.command`
>
> Windows: double-click `install/X5_Crop_win_install.bat`
>
> After installation, put `X5_Crop.py`, the main launcher for your system, and the TIFF long-strip scans in the same folder.

### What Is In The Release Zip

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
```

`install/` is only for first-time dependency setup. For actual cropping, use the main launcher in the root folder:

```text
macOS main launcher: X5_Crop_Mac.command
Windows main launcher: X5_Crop_win.bat
```

### Where To Put The Files

Put these files in the same folder as the TIFF long-strip scans:

```text
X5_Crop.py
X5_Crop_Mac.command or X5_Crop_win.bat
*.tif / *.tiff
```

The launcher and `X5_Crop.py` must stay together in the same folder. A launcher by itself cannot run the script.

The main launcher for each system is:

```text
macOS main launcher: X5_Crop_Mac.command
Windows main launcher: X5_Crop_win.bat
```

### First Use

On a new machine, run the installer launcher first:

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

The installer checks Python and required libraries. After installation, run the main launcher.

The macOS installer also tries to make the main launcher executable and remove the download quarantine flag from the current Release folder. It cannot permanently add the script to a global macOS trusted list.

After installation, you can copy `X5_Crop.py` and the main launcher for your system as a pair into different TIFF folders:

```text
macOS: X5_Crop.py + X5_Crop_Mac.command
Windows: X5_Crop.py + X5_Crop_win.bat
```

Do not move only the main launcher, because the launcher must stay in the same folder as `X5_Crop.py`.

If you download, unzip, or receive another fresh Release copy from a browser, cloud drive, or chat app, that new folder may have a new macOS quarantine flag. Run the installer again inside that new folder.

If double-clicking the installer does not work, open Terminal, type `cd `, drag the X5 Crop folder into the window, press Return, then run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

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

The Release package includes installer launchers in `install/`. You can also install dependencies manually:

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```
