# 快速启动 / Quick Start

本页只说明 Release 的首次运行。完整说明见 `README.md` 或 Release 包中的 `README.txt`。

This page covers the first Release run only. See `README.md` or the packaged
`README.txt` for the full guide.

## 1. 下载 / Download

从 GitHub Releases 下载 `X5-Crop-vX.X.zip`；不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from GitHub Releases; do not use the generated
Source code archive.

## 2. 安装 / Install

解压后运行：

After unzipping, run:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

If macOS blocks double-click launch, run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

## 3. 放入 TIFF 并启动 / Add TIFFs And Launch

```text
X5_Crop.py
X5_Crop_Mac.command 或 / or X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   双击 / double-click X5_Crop_Mac.command
Windows: 双击 / double-click X5_Crop_win.bat
```

启动器必须与 `X5_Crop.py` 和 TIFF 位于同一文件夹。

The launcher, `X5_Crop.py`, and TIFF files must stay in the same folder.

## 4. 选择格式 / Choose Format

| 输入 / Input | 格式 / Format | Full 张数 / Count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

## 5. Full、Partial 与 Debug

- 照片铺满片夹：`partial mode = no`。 / Film fills the holder: use full.
- 片头、片尾、局部片条或未铺满：`partial mode = yes`。 / Head, tail, short,
  or unfilled scan: use partial.
- Partial 的 `count` 按 Return 或输入 `auto` 可自动判断。 / In partial mode,
  press Return or enter `auto` for automatic count.
- `debug analysis = yes` 只生成 JPG 与报告，不导出正式裁切。 / Debug Analysis
  writes JPG/report artifacts without exporting final crops.

Detection 会由已知画布自动定标，在分帧前联合真实照片上下边缘，并强制使用同一证据完成
deskew 与共享短轴；未知画布或证据不足保持 REVIEW。

Detection auto-calibrates a known canvas, joins the real top/bottom photo edges
before frame solving, and reuses that evidence for mandatory deskew and the shared
short axis. Unknown or insufficient evidence remains in REVIEW.

## 6. 输出 / Output

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  needs_review/
  _debug_analysis/
```

只有安全解决的结果才导出。`needs_review/` 保存原始 TIFF 副本；原始 TIFF 永不修改。
输出保留位深、通道、ICC、resolution metadata 和其它 metadata。

Only safely resolved results are exported. `needs_review/` contains source-TIFF
copies; originals are never modified. Output preserves bit depth, channels, ICC,
resolution metadata, and other metadata.

## 7. 卸载 / Uninstall

删除 X5 Crop 文件夹即可移除程序。清理用户级依赖可运行：

Delete the X5 Crop folder to remove the program. To remove user-level dependencies:

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
