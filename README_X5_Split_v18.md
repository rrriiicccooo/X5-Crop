# X5_Split_v18 中文说明

`X5_Split_v18.py` 是临时回到脚本路线后整理出的 X5 单条 TIFF 长图裁切脚本。它面向 Hasselblad / Imacon X5 片夹扫描：自动处理容易的长图，把低置信或困难样片标记为待复核，而不是强行裁错。

当前 v18 仍是独立脚本，不是最终 GUI 工作流。项目长期方向仍然是：

```text
容易样片：自动裁切
困难样片：标记复核
手动修正：快速可见
最终导出：基于确认过的 crop plan
```

## 文件摆放

双击启动器要求这些文件和要裁切的 TIFF 长图放在同一个文件夹：

```text
X5_Split_v18.py
X5_Split_v18_macOS_DoubleClick.command
X5_Split_v18_macOS_Debug_DoubleClick.command
X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command
```

Windows 对应文件：

```text
X5_Split_v18_Windows_DoubleClick.bat
X5_Split_v18_Windows_Debug_DoubleClick.bat
X5_Split_v18_Windows_DebugAnalysis_DoubleClick.bat
```

不再支持“只把启动器放进 TIFF 文件夹、脚本留在仓库里”的模式。这样更直观，也避免不同电脑路径不一致。

## 安装依赖

macOS:

```bash
python3 -m pip install -U numpy tifffile imagecodecs Pillow
```

Windows:

```powershell
py -3 -m pip install -U numpy tifffile imagecodecs Pillow
```

如果 macOS 提示 `.command` 不能打开，先在 Terminal 里运行一次：

```bash
chmod +x X5_Split_v18_macOS_DoubleClick.command
chmod +x X5_Split_v18_macOS_Debug_DoubleClick.command
chmod +x X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command
```

## 双击启动器

普通裁切：

```text
X5_Split_v18_macOS_DoubleClick.command
```

会处理同目录下所有 `.tif` / `.tiff` 文件，自动通过的文件会输出裁切 TIFF。

Debug：

```text
X5_Split_v18_macOS_Debug_DoubleClick.command
```

只做 dry run，不输出裁切 TIFF。它会写报告和裁切预览 JPG，适合先检查检测结果。

Debug Analysis：

```text
X5_Split_v18_macOS_DebugAnalysis_DoubleClick.command
```

也是 dry run。除了裁切预览 JPG，还会写 base / enhanced 两张检测灰度分析图，适合看欠曝、弱分隔、片头片尾等问题。

macOS 启动器运行结束后会显示：

```text
Press Return to close...
```

按回车后脚本会退出，并尝试关闭由 Finder 打开的 Terminal 或 iTerm2 窗口。

## 输出目录

默认输出在 TIFF 文件夹内：

```text
split_output/
```

常见内容：

```text
split_output/
  split_report.jsonl
  split_summary.csv
  *_01.tif
  *_02.tif
  ...
  _debug/
    *_debug.jpg
  _debug_analysis/
    *_base.jpg
    *_enhanced.jpg
  needs_review/
```

说明：

- `split_report.jsonl`：完整机器可读报告。
- `split_summary.csv`：更方便人工浏览的表格。
- `_debug/*.jpg`：绿色外框、红色画幅框、蓝色/黄色等分隔线预览。
- `_debug_analysis/*.jpg`：检测用灰度图，不改变原 TIFF 像素。
- `needs_review/`：只有使用 `--copy-review-files` 时才复制低置信原图。

普通启动器不会覆盖已有输出 TIFF。已有同名裁切文件时，脚本会报错并停止该文件；命令行可用 `--overwrite` 覆盖。

## 自动通过与待复核

v18 会给每个文件一个状态：

```text
approved_auto
needs_review
```

默认置信度阈值：

```text
0.85
```

低于阈值时，默认只写报告和 debug 信息，不输出裁切 TIFF。典型待复核原因包括：

- 欠曝或低反差
- 片头/片尾不完整
- 少于默认张数
- 分隔线弱或缺失
- 画幅间距不稳定
- 外框候选分歧较大
- 自动格式判断不够确定

如果确实想把低置信结果也导出，可以手动运行：

```bash
python3 X5_Split_v18.py . --report --export-review
```

## 支持的格式

格式参数：

```text
--format auto
--format 135
--format half
--format xpan
--format 120-645
--format 120-66
--format 120-67
```

默认 `auto` 会自动区分普通 135 和 120 家族。`half` 和 `xpan` 不参与自动识别，需要手动指定。

默认张数：

| 格式 | 默认张数 | 说明 |
|---|---:|---|
| `135` | 6 | 普通 35mm |
| `half` | 12 | 半格，需要手动指定 |
| `xpan` | 3 | XPAN，需要手动指定 |
| `120-645` | 4 | 120 645 |
| `120-66` | 3 | 120 6x6 |
| `120-67` | 3 | 120 6x7 |

可用 `--count` 覆盖张数，例如片头片尾：

```bash
python3 X5_Split_v18.py . --format 135 --count 4 --report --debug --dry-run
```

布局参数：

```text
--layout auto
--layout horizontal
--layout vertical
```

条带完整性参数：

```text
--strip auto
--strip full
--strip partial
```

`auto` 会先尝试完整条，高置信失败后再尝试 partial 候选。

## 常用命令

先做 debug dry run：

```bash
python3 X5_Split_v18.py . --report --debug --dry-run
```

输出检测分析图：

```bash
python3 X5_Split_v18.py . --report --debug --debug-analysis --dry-run
```

普通自动裁切：

```bash
python3 X5_Split_v18.py . --report
```

手动指定半格：

```bash
python3 X5_Split_v18.py . --format half --report --debug --dry-run
```

手动指定 120 6x6：

```bash
python3 X5_Split_v18.py . --format 120-66 --report --debug --dry-run
```

关闭自动校斜：

```bash
python3 X5_Split_v18.py . --deskew off --report --debug --dry-run
```

复制低置信原图到复核目录：

```bash
python3 X5_Split_v18.py . --report --debug --dry-run --copy-review-files
```

## TIFF 与元数据

v18 的输出目标是尽量保留 TIFF 像素和关键元数据：

- 不做调色、反差、锐化等后期处理。
- 默认 `--compression same`，只保留已知无损压缩；未知或非无损压缩会拒绝保留。
- 写出后会重新读取输出 TIFF，验证像素、形状、位深、Photometric、PlanarConfiguration、Resolution、ICC 等关键项。

Debug JPG 只是预览图，不参与最终 TIFF 输出。

## iTerm2 与 Terminal

双击 `.command` 文件时，Finder 使用的是该文件类型的“打开方式”关联。macOS 默认通常是 Terminal.app。iTerm2 里设置“默认终端 app”不一定会改变 Finder 双击 `.command` 的关联，所以你会看到系统自带 Terminal 被打开。

如果希望双击 `.command` 用 iTerm2，可以在 Finder 里选中一个 `.command` 文件：

```text
显示简介 -> 打开方式 -> 选择 iTerm2 -> 全部更改
```

也可以继续用 Terminal.app。现在启动器在运行结束后按回车会尝试关闭 Terminal 或 iTerm2 窗口。

## 当前限制

- 只处理单条横向或竖向扫描。
- 不恢复双条 135 自动裁切。
- `half` 和 `xpan` 需要手动指定。
- 低置信结果应优先检查 debug JPG 和报告，不建议盲目 `--export-review`。
