# X5 Crop 快速启动

当前稳定发布为 **v4.2.8**。

## 1. 下载与安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。解压后运行一次：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

支持 macOS 14 及以上的 Apple Silicon 与 Intel Mac，以及 64 位 Windows；依赖安装到
Python 3.12-3.14 的当前用户 site。

## 2. 放入 TIFF 并启动

把 TIFF 与启动文件放在同一文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

macOS 双击 `X5_Crop_Mac.command`，Windows 双击 `X5_Crop_win.bat`。macOS 无法双击时，
在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 3. 选择格式、模式与张数

支持 `135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 和 `120-67`。

- `full`：使用格式的固定片夹张数。
- `partial` + 整数：严格使用输入的 output slot 数。
- `partial` + `auto`：输出匹配片夹的全部有效 slots，不猜真实照片张数。
- `135-dual` 只支持 `full`。

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

默认使用 `--layout auto` 和 `--jobs 2`。查看全部参数：

```bash
python3 X5_Crop.py --help
```

## 4. 查看结果

- `approved_auto`：在 `x5_crop_output/` 写出正式照片 TIFF。
- `needs_review`：不写正式照片 TIFF；默认把原 TIFF 复制到 `needs_review/`。
- `--diagnostics`：只写 report 与 Debug Analysis，不写照片 TIFF。

原始 TIFF 永不修改。完整设置、输出、诊断与 TIFF 保真说明见
[用户手册](user-guide.zh-CN.md)。

移除前先运行 `install/` 中对应平台的 `X5_Crop_*_uninstall`；它只清理 X5 Crop 独占且仍
安全可删的依赖。
