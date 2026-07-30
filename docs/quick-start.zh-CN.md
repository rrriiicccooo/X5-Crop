# X5 Crop 快速启动

本页说明当前 V4.9 source-core 安全基线。项目目标是在用户提供 format 后保守裁切、不切
真实照片内容；full 使用固定张数，未来 partial 同时支持显式与自动 count，而不是唯一测量
照片边界。完整说明见 `README_中文.txt`。

## 1. 下载与安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，解压后运行：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器准备 `numpy`、`tifffile`、`imagecodecs` 与 `Pillow`。

## 2. 放入 TIFF 并启动

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

## 3. 选择格式

支持 `135`、`135-dual`、`half`、`xpan`、`645`、`66` 与 `67`。Full 表示完整设计
张数；partial count 仍只表示完整设计 slot。当前 V4.9 要求显式 partial count；auto count
属于尚未实现的下一阶段 Grid/output 合同。

## 4. 当前结果

当前开发版没有获批的独立 Frame Grid phase authority，因此每张 TIFF 都会：

- 完成 scan-canvas、分轴尺度与 positive-content 审计；
- 返回 `needs_review / frame_grid_authority_unavailable`；
- 不导出 `*_01.tif` 等 frame TIFF；
- 可生成复核副本、current report 与 Debug Analysis。

这不是 fallback；current source-core 没有 active Grid proposal builder，不能直接用
content、设计宽度或旧 detector 补出 frame。它不代表未来自动批准必须唯一证明真实边界。

命令行示例：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip full --diagnostics
```

默认使用 `--jobs 2`。旧 pixel bleed、`--export-review` 与 `--dry-run` 参数已删除。

## 5. 输出

```text
x5_crop_output/
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

原始 TIFF 永不修改。Current runtime 不宣称自动裁切、deskew 物理精度或正式输出性能通过。

## 6. 卸载

删除 X5 Crop 文件夹即可移除程序。清理用户级依赖可运行：

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```
