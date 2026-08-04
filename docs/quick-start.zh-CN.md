# X5 Crop 快速启动

当前稳定发布为 **v4.2.8**。仓库中的 V4.9 仍在开发和验证。

## 1. 下载与安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。解压后运行一次：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器会准备 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。

## 2. 放入 TIFF 并启动

把 TIFF 与启动文件放在同一文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

- macOS：双击 `X5_Crop_Mac.command`
- Windows：双击 `X5_Crop_win.bat`

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 3. 选择格式、模式与张数

支持 `135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 和 `120-67`。

- `full`：使用该格式的固定片夹张数。
- `partial` + 整数：严格使用你输入的输出 slot 数。
- `partial` + `auto`：输出匹配片夹对该格式的全部有效 slots，不猜真实照片张数。
- `135-dual` 只支持 `full`。

命令行示例：

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

- `approved_auto`：写出正式照片 TIFF。
- `needs_review`：不写正式照片 TIFF；默认把原 TIFF 复制到 `needs_review/`。
- `--no-copy-review-files`：关闭 review 原图复制。
- `--diagnostics`：只写 report 与 Debug Analysis，不写照片 TIFF，也不复制 review 文件。

默认输出目录为 `x5_crop_output/`。启用 `--report` 时还会写：

```text
x5_crop_report.jsonl
x5_crop_summary.csv
x5_crop_run_manifest.jsonl
```

## 5. TIFF 安全

原始 TIFF 永不修改。程序从原图采样每个已批准输出，并在写出后复读检查像素、位深、通道、
ICC、resolution、metadata 和已支持的无损压缩。读取、写出或复读失败属于错误，不会伪装成
`needs_review`。

## 6. 移除

删除 X5 Crop 文件夹即可。Python packages 可能被其它程序共用，因此发布包不提供批量依赖
卸载脚本。
