# X5 Crop 脚本工作区

这个仓库用于把 Hasselblad / Imacon X5 片夹扫描得到的 TIFF 胶片长图裁切成单张 TIFF。

桌面 App、PySide6 GUI、Qt native UI、PyInstaller 打包和发布工作流目前都暂停。除非明确恢复 App 方向，否则后续工作聚焦在独立 Python 脚本。

## 当前推荐脚本

当前主用脚本是：

```text
X5_Crop.py
```

当前版本是 V2。目标仍然是：

```text
容易样片：自动裁切
困难样片：标记复核
debug：快速可见
最终导出：只基于高置信检测结果
```

它只处理单条横向或竖向扫描，不恢复双条 135 自动裁切。当前推荐流程不再自动猜胶片格式，也不再默认寻找片头 / 局部片条：启动器会让你输入格式，并询问是否开启 partial 模式。不开启 partial 时按完整片条处理；开启 partial 时按片头 / 局部片条处理。

V2 检测方向是候选竞争：脚本会在你指定的格式和片条模式内，为可能张数和不同证据来源生成多组候选裁切方案，再用几何、分隔、内容三类证据评分。最终输出的是得分最高且通过自动裁切闸门的候选；如果候选之间竞争接近，或者证据互相冲突，脚本会倾向于 `REVIEW`。

Test 样本复盘后，当前算法不把“内容 run 数量”当作单一真相。真实照片内部的树枝、人物、墙面、窗框和高反差纹理会把一张照片切成多个内容峰；低纹理、欠曝或大面积平滑画面也会把多张照片合并成一个内容峰。

因此脚本会把内容矩形、目标画幅比例、完整/局部片条模型和分隔证据放在一起做联合判断。局部片条可以通过，但必须由启动器里的 partial 模式或命令行 `--strip partial` 明确启用，避免普通完整片条流程被片头模型干扰。

当前联合判断关系：

- 分隔条检测负责切线硬证据。真实黑条、可信双边缘和增强分隔证据可以支持自动裁切；grid / equal 只算模型推断，不单独代表看到了真实分隔。
- 内容检测负责验证裁出来的区域是不是照片。它会检查内容覆盖、综合内容强度、内容 run 和画幅比例，但不会因为自己分数高就无条件自动通过。
- 画幅模型负责约束结果是否像对应格式。`135`、`half`、`xpan`、`120-66`、`120-645`、`120-67` 会按横向/竖向长图自动旋转比例。
- 自动通过需要证据互相担保。常规完整片条最好是“分隔硬证据通过 + 内容验证通过”；内容-only 的 partial 也可以通过，但必须非常强，并且不能有 run、覆盖或比例疑点。
- 如果分隔和内容互相冲突，或者只有 grid / equal 在支撑切线，脚本会优先进入 `REVIEW`。
- 报告里的 `v2_competition` 会记录前几名候选，方便复盘“第一名为什么赢、第二名为什么没赢”。现在这些候选来自指定格式和指定片条模式，不再跨所有 format 自动猜。

## 保留参考脚本

仓库仍保留：

```text
archive/X5_Split_v17.py
archive/X5_Split_v18.py
```

v17 是上一版参考实现，用于对照检测逻辑和回归行为。v18 是 X5_Crop 的早期直接前身，用于回看旧分隔证据逻辑。它们已经归档到 `archive/`，日常新工作优先放在 `X5_Crop.py`。

## 安装依赖

第一次在新机器上使用时，推荐先运行安装启动器：

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

安装启动器会优先使用机器上已有的 Python 3，并用用户级安装方式安装依赖：

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

这样脚本和启动器可以自由移动；依赖跟着当前用户的 Python 走，不绑在项目文件夹路径上。

macOS 上如果遇到新版 Python / Homebrew 的 externally-managed 限制，安装器会提示是否用 `--break-system-packages --user` 重试。这里仍然是用户级安装，不是写入系统目录。

如果机器没有 Python：

- macOS：如果有 Homebrew，安装器可以用 Homebrew 安装 Python；否则会打开 Python 官网下载页，安装 Python 后再运行一次安装器。
- Windows：如果有 `winget`，安装器会尝试安装 Python 3.12；否则会打开 Python 官网下载页，安装 Python 后再运行一次安装器。

也可以手动安装依赖。

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
X5_Crop.py
X5_Crop_Mac.command
install/X5_Crop_Mac_install.command
```

Windows 常用文件：

```text
X5_Crop.py
X5_Crop_win.bat
install/X5_Crop_win_install.bat
```

不支持“只把启动器放进 TIFF 文件夹、脚本留在仓库里”的模式。

如果 macOS 提示 `.command` 不能打开，先在 Terminal 里运行一次：

```bash
chmod +x X5_Crop_Mac.command install/X5_Crop_Mac_install.command
```

## 启动器

主启动器：

```text
X5_Crop_Mac.command
```

会处理同目录下所有 `.tif` / `.tiff` 文件，自动通过的文件会输出裁切 TIFF。它会先问 `format:`，再问 `partial mode? [y/n, return=no]:`，最后问 `debug analysis? [y/n, return=no]:`。后两个问题都可以输入 `yes` / `no` / `y` / `n`，直接回车等于 `no`。

如果开启 Debug Analysis，它不会写裁切 TIFF。它会在一张 JPG 里生成四块内容：带框 debug 图、原始灰度图、分隔证据图、内容证据图。横向长图上下排列，竖向长图左右排列，适合看欠曝、弱分隔、片头片尾和未铺满整条片夹的情况。

如果同一批 TIFF 已经先运行过 Debug Analysis dry run，之后再用普通裁切运行同样的 format、partial/count、bleed、deskew 和阈值参数时，脚本会优先复用 `split_report.jsonl` 里的分析结果：

- 已经是 `approved_auto` 的文件会跳过重新检测，直接按报告里的裁切框输出 TIFF。
- 已经是 `needs_review` 的文件会直接跳过，不会第二次重新检测后碰运气裁切。
- 如果原 TIFF 的文件大小、修改时间、页码、图像形状、脚本版本或关键参数不匹配，脚本会放弃复用并重新检测。
- 如果 Debug Analysis 那次实际做过 deskew，复用时会按报告中记录的同一个角度重新旋转后再裁切，保证裁切框和当时分析图一致。

命令行可以加 `--no-reuse-analysis` 强制重新检测。

Windows 对应把 `Mac` 换成 `win`，后缀是 `.bat`：

```text
X5_Crop_win.bat
```

启动器运行后会让你输入格式：

| 输入 | 格式 |
|---|---|
| 直接回车 / `135` | `135` |
| `xpan` | `xpan` |
| `half` | `half` 半格 |
| `645` | `120-645` |
| `66` | `120-66` |
| `67` | `120-67` |

这个启动器方式的目的不是让困难图片更容易 `PASS`，而是减少脚本在错误格式、错误片头模型之间自由竞争的机会。普通完整片条用完整片条模型；片头和局部片条由 partial 模式单独进入。

普通完整片条启动器会固定张数，不再使用 count auto：

| 格式 | 固定张数 |
|---|---:|
| `135` | 6 |
| `half` | 12 |
| `xpan` | 3 |
| `120-645` | 4 |
| `120-66` | 3 |
| `120-67` | 3 |

只有开启 partial 模式时，count 才会保持 auto，用来处理片头、片尾或局部片条。

macOS 启动器运行结束后会显示：

```text
Press Return to close...
```

按回车后脚本会退出，并尝试关闭由 Finder 打开的 Terminal 或 iTerm2 窗口。Finder 双击 `.command` 默认由 macOS 的 Terminal 打开，这是系统文件关联行为；脚本本身会兼容 Terminal 和 iTerm2 的窗口关闭。

## 命令行常用法

输出检测分析图：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

普通自动裁切：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

片头 / 局部片条：

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

默认导出的裁切 TIFF 会像 v17 一样保留 bleed。默认值按长图方向理解：

- 横向长图：左右各 15px，上下各 10px。
- 纵向长图：上下各 15px，左右各 10px。

之后文档和设计讨论里如果只写“左右 / 上下”，默认都是指横向长图；纵向长图会按方向旋转对应过去。

可用 `--bleed`、`--bleed-x`、`--bleed-y` 调整。其中 `--bleed-x` 是长轴 bleed，`--bleed-y` 是短轴 bleed。例如：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 15 --bleed-y 10
```

关闭自动校斜：

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off --report --debug-analysis --dry-run
```

把低置信原图复制到复核目录：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run --copy-review-files
```

默认已经会复制低置信原图；上面这个参数只是显式写出行为。如果只想写报告、不复制原 TIFF：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run --no-copy-review-files
```

低置信结果也强制导出：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --export-review
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
  _debug_analysis/
    *_debug_analysis.jpg
  needs_review/
```

说明：

- `split_report.jsonl`：完整机器可读报告。
- `split_summary.csv`：更方便人工浏览的表格。
- `_debug_analysis/*_debug_analysis.jpg`：四联图，已经包含带框 debug 图。运行 `--debug-analysis` 时不会再重复生成 `_debug/` 文件夹和单独 debug JPG。
- `needs_review/`：低置信 `needs_review` 原 TIFF 会默认复制到这里，方便人工集中处理。

普通启动器不会覆盖已有输出 TIFF。已有同名裁切文件时，脚本会报错并停止该文件；命令行可用 `--overwrite` 覆盖。

## 如何看 Debug Analysis

`_debug_analysis/*_debug_analysis.jpg` 里的 `Debug boxes` 面板只显示：

| 颜色 | 含义 |
|---|---|
| 绿色外框 | 脚本认为整条胶片有效区域的外框 |
| 不同半透明色块 | 每一张将要输出的裁切范围，包含默认长轴 15px、短轴 10px bleed |

四联图顶部会在图片外显示状态栏，说明是否通过当前置信度阈值。`PASS` / `REVIEW` 会用不同颜色和更醒目的字号显示：

```text
PASS confidence 0.987 >= threshold 0.850
REVIEW confidence 0.676 < threshold 0.850
```

`PASS` 表示会按默认规则自动输出裁切；`REVIEW` 表示不会自动输出裁切，并会进入复核流程。

`Separator evidence` 面板负责显示分隔证据和彩色标记：

| 颜色 | 含义 |
|---|---|
| 红色框 / 红色线 | 从原图证据中检测到的真实分隔区域，包括黑条区域和可信双边缘 `edge-pair`。黑条有宽有窄时会画成区域框，而不是只画单线 |
| 橙色框 / 橙色线 | 在固定外框内由分隔证据层补充检测到的分隔区域 |
| 黄色短 tick | 由全局片距 / grid 模型推算出的切线，不代表一定看到了真实黑条 |
| 紫色短 tick | 证据不足时使用的等分或宽区域 fallback 切线 |
| 白色短 tick | 其它未分类的切线来源 |

看图时优先检查四件事：

- 绿色外框有没有吃掉片头、片尾或画面边缘。
- 每个半透明裁切色块是否覆盖对应照片，并在四周留出合理 bleed。
- Separator evidence 里的红色检测区域是否覆盖真实黑条；如果没有红色、只有黄色或紫色，说明这部分更依赖推断，应该更谨慎。
- Separator evidence 里的黄色/紫色短 tick 是否落在真实片间空隙，而不是落进画面内容。

## 如何看 Debug Analysis 四联图

Debug Analysis 的四块内容：

- `Original gray`：原始检测灰度图，用来看源扫描本身的明暗和分隔可见度。
- `Debug boxes`：显示绿色外框和不同半透明色块，用来看裁切计划。
- `Separator evidence`：只在已确认的外框内部生成的分隔证据图，并集中绘制红色、橙色、黄色、紫色、白色分隔标记。它只补充分隔候选，不会重新决定外框，也不会写进最终 TIFF。
- `Content evidence`：内容证据图，用综合分显示哪里更像真实照片信息。综合分由局部梯度、四邻域纹理、局部对比和少量调性存在感组成，不依赖单一亮度或单一梯度。

横向胶片长图的四联图顺序是从上到下：`Original gray`、`Debug boxes`、`Separator evidence`、`Content evidence`。竖向胶片长图的四联图顺序是从左到右：`Original gray`、`Debug boxes`、`Separator evidence`、`Content evidence`。

内容证据用于检查“有信息的照片矩形”是否支持当前裁切框。横向长图下，脚本使用这些常见画幅比例作为参考：

| 格式 | 横向长图里的单张照片比例 |
|---|---|
| `135` | `3:2` |
| `half` | `2:3` |
| `xpan` | `65:24` |
| `120-66` | `1:1` |
| `120-645` | `3:4` |
| `120-67` | `4:5` |

如果是竖向长图，上表比例会自动反过来。内容证据当前主要用于 debug 和保守降级：当内容矩形和画幅比例明显冲突，或内容覆盖明显不足时，脚本会倾向于 `REVIEW`；它不会单独把困难图片提升为自动通过。

## 自动通过与待复核

脚本会给每个文件一个状态：

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
- 内容 run 数量和目标张数不一致
- 内容矩形和预期画幅比例冲突
- 指定格式或指定完整 / 片头模式和实际扫描不一致
