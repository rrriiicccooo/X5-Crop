# X5 Crop 快速启动

本页只说明 Release 的首次运行。完整说明见 `README_中文.txt`。

## 1. 下载

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`；不要下载 GitHub 自动生成的 Source code。

## 2. 安装

解压后运行：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

## 3. 放入 TIFF 并启动

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

启动器必须与 `X5_Crop.py` 和 TIFF 位于同一文件夹。

## 4. 选择格式

| 输入 | 格式 | Full 张数 |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | 135 双条 | 12 |
| `half` | 半格 | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

## 5. Full、Partial 与 Debug

- 照片铺满片夹：`partial mode = no`。
- 片头、片尾、局部片条或未铺满：`partial mode = yes`。
- Partial 的 `count` 按 Return 或输入 `auto` 可自动判断。
- `debug analysis = yes` 只生成 JPG 与报告，不导出正式裁切。

Detection 会由已知画布自动定标，在分帧前联合真实照片共享边缘，并强制使用同一证据完成
deskew 与共享短轴；未知画布或证据不足保持 REVIEW。

## 6. 输出

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  needs_review/
  _debug_analysis/
```

只有安全解决的结果才导出。`needs_review/` 保存原始 TIFF 副本；原始 TIFF 永不修改。
输出保留位深、通道、ICC、resolution metadata 和其它 metadata。

## 7. 卸载

删除 X5 Crop 文件夹即可移除程序。清理用户级依赖可运行：

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
