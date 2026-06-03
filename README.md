# X5 Crop 脚本工作区

这个仓库现在收敛为一个干净的脚本工作区，用于把 Hasselblad / Imacon X5 片夹扫描得到的 TIFF 胶片长图裁切成单张 TIFF。

桌面 App、PySide6 GUI、Qt native UI、PyInstaller 打包和发布工作流目前都暂停。除非明确恢复 App 方向，否则后续工作聚焦在独立 Python 脚本。

## 当前推荐脚本

当前主用脚本是：

```text
X5_Split_v18.py
```

v18 的目标是：

```text
容易样片：自动裁切
困难样片：标记复核
debug：快速可见
最终导出：只基于高置信检测结果
```

它只处理单条横向或竖向扫描，不恢复双条 135 自动裁切。`half` 和 `xpan` 需要手动指定。

## 保留参考脚本

仓库仍保留：

```text
X5_Split_v17.py
```

v17 是上一版参考实现，用于对照检测逻辑和回归行为。日常新工作优先放在 v18；不要删除 v17，除非明确决定不再需要这个参考。

## 安装依赖

macOS:

```bash
python3 -m pip install -U numpy tifffile imagecodecs Pillow
```

Windows PowerShell:

```powershell
py -3 -m pip install -U numpy tifffile imagecodecs Pillow
```

## 文件摆放

启动器要求脚本、启动器和要裁切的 TIFF 长图在同一个文件夹。

macOS 常用文件：

```text
X5_Split_v18.py
X5_Split_v18_macOS.command
X5_Split_v18_macOS_Debug.command
X5_Split_v18_macOS_DebugAnalysis.command
```

Windows 常用文件：

```text
X5_Split_v18.py
X5_Split_v18_Windows.bat
X5_Split_v18_Windows_Debug.bat
X5_Split_v18_Windows_DebugAnalysis.bat
```

不支持“只把启动器放进 TIFF 文件夹、脚本留在仓库里”的模式。

如果 macOS 提示 `.command` 不能打开，先在 Terminal 里运行一次：

```bash
chmod +x X5_Split_v18_macOS.command
chmod +x X5_Split_v18_macOS_Debug.command
chmod +x X5_Split_v18_macOS_DebugAnalysis.command
```

## 启动器

普通裁切：

```text
X5_Split_v18_macOS.command
```

会处理同目录下所有 `.tif` / `.tiff` 文件，自动通过的文件会输出裁切 TIFF。

Debug：

```text
X5_Split_v18_macOS_Debug.command
```

只做 dry run，不输出裁切 TIFF。它会写报告和裁切预览 JPG，适合先检查检测结果。

Debug Analysis：

```text
X5_Split_v18_macOS_DebugAnalysis.command
```

也是 dry run。它会在一张 JPG 里生成三块内容：带框 debug 图、原始灰度图、增强后灰度图；横向长图上下排列，竖向长图左右排列，适合看欠曝、弱分隔、片头片尾等问题。

macOS 启动器运行结束后会显示：

```text
Press Return to close...
```

按回车后脚本会退出，并尝试关闭由 Finder 打开的 Terminal 或 iTerm2 窗口。

## 命令行常用法

先做 debug dry run：

```bash
python3 X5_Split_v18.py . --report --debug --dry-run
```

输出检测分析图：

```bash
python3 X5_Split_v18.py . --report --debug-analysis --dry-run
```

普通自动裁切：

```bash
python3 X5_Split_v18.py . --report
```

默认导出的裁切 TIFF 会像 v17 一样在每张四周保留 10px bleed。可用 `--bleed`、`--bleed-x`、`--bleed-y` 调整，例如：

```bash
python3 X5_Split_v18.py . --report --bleed 10
```

关闭自动校斜：

```bash
python3 X5_Split_v18.py . --deskew off --report --debug --dry-run
```

把低置信原图复制到复核目录：

```bash
python3 X5_Split_v18.py . --report --debug --dry-run --copy-review-files
```

默认已经会复制低置信原图；上面这个参数只是显式写出行为。如果只想写报告、不复制原 TIFF：

```bash
python3 X5_Split_v18.py . --report --debug --dry-run --no-copy-review-files
```

低置信结果也强制导出：

```bash
python3 X5_Split_v18.py . --report --export-review
```

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
    *_debug_analysis.jpg
  needs_review/
```

说明：

- `split_report.jsonl`：完整机器可读报告。
- `split_summary.csv`：更方便人工浏览的表格。
- `_debug/*.jpg`：带外框、画幅框和分隔线的检测预览。
- `_debug_analysis/*_debug_analysis.jpg`：三联图，已经包含带框 debug 图。运行 `--debug-analysis` 时不会再重复生成 `_debug/` 文件夹和单独 debug JPG。
- `needs_review/`：低置信 `needs_review` 原 TIFF 会默认复制到这里，方便人工集中处理。

普通启动器不会覆盖已有输出 TIFF。已有同名裁切文件时，脚本会报错并停止该文件；命令行可用 `--overwrite` 覆盖。

## 如何看 debug 图

`_debug/*.jpg` 和 `_debug_analysis/*_debug_analysis.jpg` 里的带框 debug 图使用这些颜色：

| 颜色 | 含义 |
|---|---|
| 绿色外框 | 脚本认为整条胶片有效区域的外框 |
| 蓝色框 | 每一张将要输出的裁切框，包含默认 10px bleed |
| 红色框 / 红色线 | 从图像证据中检测到的真实分隔区域。黑条有宽有窄时会画成区域框，而不是只画单线 |
| 黄色短 tick | v18 新增：由全局片距 / grid 模型推算出的切线，不代表一定看到了真实黑条 |
| 紫色短 tick | v18 新增：证据不足时使用的等分或宽区域 fallback 切线 |
| 白色短 tick | v18 新增：其它未分类的切线来源 |

debug 图顶部会在图片外显示状态栏，说明是否通过当前置信度阈值：

```text
PASS confidence 0.987 >= threshold 0.850
REVIEW confidence 0.676 < threshold 0.850
```

`PASS` 表示会按默认规则自动输出裁切；`REVIEW` 表示不会自动输出裁切，并会进入复核流程。

看图时优先检查三件事：

- 绿色外框有没有吃掉片头、片尾或画面边缘。
- 蓝色裁切框是否覆盖每张照片，并在四周留出合理 bleed。
- 红色检测区域是否覆盖真实黑条；如果没有红色、只有黄色或紫色，说明这部分更依赖推断，应该更谨慎。
- 黄色/紫色短 tick 是否落在真实片间空隙，而不是落进画面内容。

Debug Analysis 三联图的用途：

- “Debug boxes”：同 `_debug` 预览，用来看裁切计划。
- “Original gray”：原始检测灰度图，用来看源扫描本身的明暗和分隔可见度。
- “Enhanced gray”：增强后的检测灰度图，用来看脚本是否借助增强图找到了弱分隔。增强图只用于检测坐标，不会写进最终 TIFF。

横向胶片长图的三联图顺序是从上到下：`Debug boxes`、`Original gray`、`Enhanced gray`。竖向胶片长图的三联图顺序是从左到右：`Debug boxes`、`Original gray`、`Enhanced gray`。

## 自动通过与待复核

v18 会给每个文件一个状态：

```text
approved_auto
needs_review
```

默认置信度阈值是 `0.85`。低于阈值时，默认只写报告和 debug 信息，不输出裁切 TIFF，并把原 TIFF 复制到 `split_output/needs_review/` 方便人工复核。重复运行时，如果同名文件已经在复核目录里，脚本会复用已有文件，不再连续生成 `_02`、`_03` 副本。

典型待复核原因：

- 欠曝或低反差
- 片头/片尾不完整
- 少于默认张数
- 分隔线弱或缺失
- 画幅间距不稳定
- 外框候选分歧较大
- 自动格式判断不够确定

如果不想复制待复核原文件，可以加：

```bash
--no-copy-review-files
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

| 格式 | 默认张数 | 说明 |
|---|---:|---|
| `135` | 6 | 普通 35mm |
| `half` | 12 | 半格，需要手动指定 |
| `xpan` | 3 | XPAN，需要手动指定 |
| `120-645` | 4 | 120 645 |
| `120-66` | 3 | 120 6x6 |
| `120-67` | 3 | 120 6x7 |

可用 `--count` 覆盖张数，例如：

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

## TIFF 与元数据

v18 的输出目标是尽量保留 TIFF 像素和关键元数据：

- 不做调色、反差、锐化等后期处理。
- 默认 `--compression same`，只保留已知无损压缩；未知或非无损压缩会拒绝保留。
- 写出后会重新读取输出 TIFF，验证像素、形状、位深、Photometric、PlanarConfiguration、Resolution、ICC 等关键项。

Debug JPG 只是预览图，不参与最终 TIFF 输出。

## iTerm2 与 Terminal

双击 `.command` 文件时，Finder 使用的是该文件类型的“打开方式”关联。macOS 默认通常是 Terminal.app。iTerm2 里设置“默认终端 app”不一定会改变 Finder 双击 `.command` 的关联。

如果希望双击 `.command` 用 iTerm2，可以在 Finder 里选中一个 `.command` 文件：

```text
显示简介 -> 打开方式 -> 选择 iTerm2 -> 全部更改
```

继续用 Terminal.app 也可以。现在启动器在运行结束后按回车会尝试关闭 Terminal 或 iTerm2 窗口。

## 本地文件与协作

这些本地文件和输出目录默认不提交：

```text
Test/
downloaded_apps/
split_output/
__pycache__/
.venv/
build/
dist/
release/
```

大 TIFF 样片只有在明确决定作为正式 fixture，并配置 Git LFS 后才提交。

这个文件夹可能通过 NAS 在多台电脑之间同步。GitHub 是源码和文档的准确信源，NAS 只作为本地文件传输层。

跨电脑或跨 Codex 会话继续工作前：

```bash
git status --short
git branch --show-current
git fetch origin
```

Codex 规则和 handoff 记录见 `AGENTS.md`。
