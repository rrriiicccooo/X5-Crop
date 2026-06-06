# X5 Crop

X5 Crop is a standalone Python script for splitting long TIFF film-strip scans
from Hasselblad / Imacon X5 holders into individual TIFF frames.

当前 active 脚本版本：V3.6.12

当前稳定发布版本：v3.6.2（GitHub Releases）

Current active script version: V3.6.12

Current stable release: v3.6.2 (GitHub Releases)

## 快速使用

普通使用请优先下载 GitHub Releases 里的稳定版压缩包。仓库 `main`
分支是开发进度，可能比 Release 新，但不一定是稳定发布版。

第一次在新机器上使用：

1. 解压 Release 压缩包。
2. 可以先打开 `快速启动_Quick_Start.md` 看最短步骤；更详细说明看 `README.md` 和 `CHANGELOG.md`。
3. 把下面这些文件和要裁切的 TIFF 长图放在同一个文件夹里：
   - `X5_Crop.py`
   - macOS 用 `X5_Crop_Mac.command`
   - Windows 用 `X5_Crop_win.bat`
4. 双击对应系统的启动器。
5. 先选择胶片格式，再选择是否开启 partial mode 和 Debug Analysis。

常用选择：

- 直接回车或输入 `135`：普通 135，一条 6 张。
- 输入 `dual` 或 `135 dual`：双条 135，一共 12 张。
- 输入 `xpan` / `half` / `645` / `66` / `67`：对应其它格式。
- `partial mode` 直接回车是 `no`，只在片头、片尾或不完整片条时开启。
- `debug analysis` 直接回车是 `no`；输入 `y` 会只生成分析 JPG 和报告，不正式裁切。
- 正常裁切不会生成 report；只有开启 Debug Analysis 时启动器才会写报告。

运行耗时：

- 在当前测试机器和常见 135 TIFF 长图上，普通 dry run / 裁切通常每张约 5-15 秒。
- Debug Analysis 需要额外生成 JPG 分析图，通常每张约 10-30 秒。
- 大尺寸 TIFF、开启 deskew、较慢硬盘或较慢电脑都会更久。
- 终端在处理单张大 TIFF 时可能一段时间没有新的提示；这通常不是出错，而是脚本还在读取、检测、校平或写文件。等它进入下一张图或完成当前图后会继续输出状态。

高置信结果会自动裁切；低置信结果会进入 `needs_review/`，方便人工复核。

## Quick Start

For normal use, download the stable zip package from GitHub Releases. The
repository `main` branch is development progress; it may be newer than the
Release, but it is not necessarily the stable package.

On a new machine:

1. Unzip the Release package.
2. Open `快速启动_Quick_Start.md` for the shortest steps; see `README.md` and
   `CHANGELOG.md` for more detail.
3. Put these files in the same folder as the TIFF long-strip scans:
   - `X5_Crop.py`
   - macOS: `X5_Crop_Mac.command`
   - Windows: `X5_Crop_win.bat`
4. Double-click the launcher for your system.
5. Choose the film format, then choose whether to enable partial mode and Debug
   Analysis.

Common choices:

- Press Return or type `135`: normal 135, 6 frames per strip.
- Type `dual` or `135 dual`: dual-strip 135, 12 frames total.
- Type `xpan` / `half` / `645` / `66` / `67`: other supported formats.
- Press Return for `partial mode` to choose `no`; enable it only for leader,
  tail, or incomplete strips.
- Press Return for `debug analysis` to choose `no`; type `y` to generate only
  analysis JPGs and reports without exporting cropped TIFFs.
- Normal launcher runs do not write reports; launchers write reports only when
  Debug Analysis is enabled.

Runtime:

- On the current test machine with typical 135 TIFF long-strip scans, normal dry
  run / export usually takes about 5-15 seconds per file.
- Debug Analysis also writes JPG analysis images and usually takes about 10-30
  seconds per file.
- Very large TIFFs, deskew, slower disks, or slower computers can take longer.
- The terminal may show no new message for a while while one large TIFF is being
  read, detected, deskewed, or written. This usually does not mean the script has
  failed; it is still running and will print the next status line after the
  current file advances or finishes.

High-confidence results are cropped automatically. Low-confidence results go to
`needs_review/` for manual review.

## 中文说明

### 这个工具做什么

X5 Crop 会处理同一个文件夹里的 `.tif` / `.tiff` 长图，并把高置信结果自动裁切成单张 TIFF。低置信结果不会自动裁切，会写入报告并复制原 TIFF 到 `needs_review/`，方便人工复核。

核心原则：

- 容易样片自动裁切。
- 困难样片进入复核。
- 只有高置信检测结果才自动导出。
- 不为了让困难图片通过而放宽置信规则。
- 最终裁切 TIFF 尽量保持原 TIFF 的画质和元数据属性。

脚本会在你指定的胶片格式和片条模式内，综合外框、分隔、内容和画幅几何证据评分。最终只有高置信结果会自动导出；证据不足、证据互相冲突或画幅状态异常时会进入复核。

当前默认行为：

- 检测阶段不使用 bleed；bleed 只在最终输出和 Debug Analysis 色块里应用。
- 默认输出 bleed 为长轴 20px、短轴 10px。横向长图是左右各 20px、上下各 10px；竖向长图会自动对应旋转。
- 对已经 `approved_auto` 且没有复核原因的结果，会做一个很小的输出几何 polish：只允许长轴最多向外微扩。这一步不改变 PASS/REVIEW 和置信度。
- 对近似叠片、片距局部不稳定、分隔证据不足或内容证据冲突的长图，会保持保守判断，不会为了自动导出而放宽置信规则。

### 更新日志

Release 是面向普通用户的稳定版；`main` 分支里的开发版本会继续验证新的检测逻辑。

更详细的本地开发记录见 `CHANGELOG.md`。

| 版本 | 状态 | 检测逻辑 / 工作流变化 |
|---|---|---|
| V3.6.12 | 当前 active 开发版 | 根据 `Test/120` 和半格全量 dry run 调整 format-aware `edge-pair`：120-66 / 120-67 允许更宽、更低背景的 120 暗带证据，但仍保留内容比例冲突等 REVIEW 闸门；半格参数保持不变。 |
| V3.6.11 | 开发版 | 将 `edge-pair` 从 135 专用扩展为 format-aware full-strip 逻辑：135 保持原参数，其它格式使用各自更保守的搜索窗口、gutter 宽度和质量阈值。 |
| V3.6.10 | 开发版 | 清理 V3.6.9 后的低风险残留：移除未使用的 `grid_protection_trust()` 包装函数，修正 CLI 版本、bleed 默认值、`--analysis` help 和诊断说明旧话术。不改变检测流程。 |
| V3.6.9 | 开发版 | 统一 active grid protection 和 diagnostics 的轻量 hard-gap trust：grid 保护红框前也会识别 nearby conflict、geometry conflict、suspect internal edge / frame border，减少“双轨可信度”冲突。 |
| V3.6.8 | 开发版 | 将 V3.6.7 的 single-anchor 精确组合闸门改成 `lucky_pass_risk_score`：多项弱全局证据、可疑 hard gap、overlap model gap 和几何稳定性共同评分；超过阈值才进入 REVIEW。 |
| V3.6.7 | 开发版 | 将附近更强分隔候选从诊断提升为很窄的 correction：只有候选明显更强、移动后几何更合理、且不提高 confidence 时才拉回红框；同时把 `X5_00041` 这类 single-anchor lucky PASS 形态压进 REVIEW。 |
| V3.6.6 | 开发版 | 新增 hard gap trust 诊断、附近更强分隔候选复查，并让稳定性较弱的 grid 不能覆盖 `strong_separator`；用于观察和保护可信红框。 |
| V3.6.5 | 当前 active 开发版 | 诊断运行的并行上限调到 4；普通运行仍限制为 2。这个改动主要服务本地诊断启动器，不改变检测逻辑。 |
| V3.6.4 | 当前 active 开发版 | 回到 V3.6.2 检测基线；新增很窄的长轴白边外框修正：只有首尾 hard separator 都可靠、内容框完整、单侧边缘几乎全白时，才允许外框收回内容边缘附近。 |
| V3.6.3 | 已暂停 / 参考方向 | 曾尝试将叠片 / 近似叠片视为困难图：135 full strip 中模型 gap 出现 strong overlap risk 时强制进入 REVIEW。该方向暂时搁置，后续先从更细的诊断和更窄的修正规则发展。 |
| V3.6.2 | 稳定 Release | 诊断清理后的第一步逻辑瘦身：`equal-broad-region` 合并为普通 `equal`，`hard_fallback_detection` 缩小为 review-only equal split fallback；目标是减少低收益 method 和报告噪音。叠片、近似叠片、片距局部不稳定等困难图仍可能误识别，建议用 Debug Analysis 人工复核。 |
| V3.6.1 | 开发版 | 继续优化诊断层：诊断报告字段和诊断 tick 改为只在显式 `--diagnostics` 时生成；普通启动器不开启诊断。新增更细的叠片风险分级，仍不改变输出框、置信度或 PASS/REVIEW。 |
| V3.6 | 开发版 | 从 V3.3.1 输出基线出发做诊断清理：新增只读 `diagnostics_v3_6`、红框可信度诊断和叠片/连续内容诊断；不改变 V3.3.1 的 `status`、`outer_box`、`frame_boxes` 或置信度。 |
| V3.5 | 已暂停 / 已回滚的开发尝试 | 尝试新增红色 hard separator 轻量可信度验证。实测会影响原本准确的样片，因此没有进入 V3.6 的实际修正规则。 |
| V3.4.2 | 已暂停 / 已回滚的开发尝试 | 尝试新增保守的局部 grid。实测会影响原本准确的样片，因此没有进入 V3.6 的实际修正规则。 |
| V3.4.1 | 已暂停 / 参考方向 | 尝试让强 hard separator 与 robust grid 冲突时优先保留红色证据。这个方向仍有参考价值，但当前先回到 V3.3.1 作为稳定基线。 |
| V3.4 | 开发版 | 简化检测层：移除增强分隔层，合并宽分隔 fallback 到普通 equal，完整片条只把内容检测作为验证，不再生成单独 content candidate。 |
| V3.3.2 | 开发版 | 加入更保守的 overlap-like gap 标记，疑似叠片/连续内容的模型 gap 不再作为强 same-frame-size 锚点。 |
| V3.3.1 | 稳定 Release / V3.6 输出基线 | 保留 V3 系列较稳定的 outer/gap/candidate 主链路；bleed 只在最终输出、报告和 Debug Analysis 中应用，不参与检测评分；打包为可下载稳定版。 |
| V3.3 | 开发版 | 将检测用 bleed 与输出用 bleed 分离，默认输出 bleed 为长轴 20px、短轴 10px。 |
| V3.2 | 开发版 | 回到 V3 风格的主检测链路，同时保留明显弱证据图进入复核的安全闸门。 |
| V3.1.x | 实验版 | 尝试更积极的外框/分隔修正、局部救援和外扩策略；部分场景有帮助，但可能影响稳定样片，因此没有作为稳定发布。 |
| V3.0 | 基线版 | 建立 X5 Crop 主脚本、格式选择、固定张数 full strip、partial 模式、Debug Analysis 和高置信自动裁切 / 低置信复核的基本框架。 |

### 下载和文件摆放

普通使用推荐从 GitHub Releases 下载最新的稳定版压缩包。Release 是面向用户的稳定更新；仓库里的 `main` 分支可能包含正在验证中的开发进度，适合参与测试或查看最新改动。

Release 压缩包封装脚本本体、两个主启动器、README 和快速启动文档：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
```

把 `X5_Crop.py`、对应系统的启动器和要裁切的 TIFF 长图放在同一个文件夹里，然后双击启动器运行。

不支持“只把启动器放进 TIFF 文件夹、脚本留在别处”的模式。

### 第一次安装依赖

如果新机器缺少依赖，可以从仓库源码里的安装器安装，或者手动安装 Python 依赖。安装器不再放进 Release 压缩包。

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

安装器会使用用户级安装方式安装依赖：

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

这样脚本文件夹可以自由移动，依赖跟随当前用户的 Python，不绑在项目路径上。

主启动器运行时会优先寻找已经能导入 `numpy`、`Pillow` 和 `tifffile` 的 Python；这样即使 macOS 系统自带 Python 或其它空环境排在前面，也会尽量选择真正可用的解释器。

macOS 如果遇到新版 Python / Homebrew 的 externally-managed 限制，安装器会提示是否用 `--break-system-packages --user` 重试。这里仍然是用户级安装。

如果机器没有 Python：

- macOS：安装器会优先使用 Homebrew 安装 Python；如果没有 Homebrew，会打开 Python 官网。
- Windows：安装器会优先使用 `winget` 安装 Python 3.12；如果没有 `winget`，会打开 Python 官网。

### 启动器怎么用

macOS:

```text
X5_Crop_Mac.command
```

Windows:

```text
X5_Crop_win.bat
```

启动器会依次询问：

```text
choose film format:
  return or 135 = 135
  dual or 135 dual = 135-dual
  xpan = xpan
  half = half-frame
  645 = 120-645
  66 = 120-66
  67 = 120-67

format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

格式输入：

| 输入 | 格式 |
|---|---|
| 直接回车 / `135` | `135` |
| `dual` / `135 dual` / `135-dual` | 双条 135 |
| `xpan` | XPAN |
| `half` | 半格 |
| `645` | 120-645 |
| `66` | 120-66 |
| `67` | 120-67 |

如果输错格式，启动器会重新让你输入。`partial mode` 和 `debug analysis` 可以输入 `yes` / `no` / `y` / `n`，直接回车等于 `no`。

不开启 partial 时，脚本按完整片条处理，并固定张数：

| 格式 | 张数 |
|---|---:|
| `135` | 6 |
| `135-dual` | 12 |
| `half` | 12 |
| `xpan` | 3 |
| `120-645` | 4 |
| `120-66` | 3 |
| `120-67` | 3 |

开启 partial 时，张数使用 auto，适合片头、片尾、局部片条或没有铺满整条片夹的扫描。`135-dual` 目前只建议用于完整双条 135；partial 下会保守复核。

### Debug Analysis

如果开启 Debug Analysis，脚本只生成分析 JPG 和报告，不输出裁切 TIFF。输出位置：

```text
split_output/_debug_analysis/
```

每张 Debug Analysis JPG 是四联图：

- `Original gray`：原始灰度图。
- `Debug boxes`：外框和最终输出裁切范围。
- `Separator evidence`：分隔证据。
- `Content evidence`：内容证据。

横向长图会把四联图上下排列；竖向长图会横向排列，方便最大化利用屏幕空间。

顶部状态栏会显示：

```text
PASS confidence 0.987 >= threshold 0.850
REVIEW confidence 0.676 < threshold 0.850
```

`PASS` 表示会自动裁切；`REVIEW` 表示不会自动裁切，需要人工复核。

`Debug boxes` 颜色：

| 颜色 | 含义 |
|---|---|
| 绿色外框 | 脚本认为整条胶片有效区域的外框 |
| 不同半透明色块 | 每一张最终输出裁切范围，包含输出 bleed |

`Separator evidence` 颜色：

| 颜色 | 含义 |
|---|---|
| 红色框 / 红色线 | 原图中检测到的真实分隔区域，包括黑条和可信双边缘 |
| 黄色短 tick | grid / 全局或局部片距模型推算出的切线，不代表一定看到真实黑条 |
| 紫色短 tick | 证据不足时的等分或 fallback 切线 |
| 白色短 tick | 其它未分类切线来源 |

看 Debug Analysis 时建议优先检查：

- 绿色外框有没有吃进画面或把白边留太多。
- 半透明裁切色块有没有覆盖照片并留出合理 bleed。
- 红色分隔证据是否落在真实黑条或真实片间空隙。
- 黄色 / 紫色 tick 是否只是模型猜测。

### 复用 Debug Analysis 结果裁切

如果已经对同一批 TIFF 跑过 Debug Analysis dry run，之后普通裁切时脚本会优先复用 `split_report.jsonl`：

- `approved_auto` 会跳过重新检测，直接按报告里的裁切框导出 TIFF。
- `needs_review` 会直接跳过，不会重新检测后碰运气裁切。
- 如果原 TIFF 的文件大小、修改时间、页码、图像形状、脚本版本或关键参数不匹配，会自动重新检测。
- 如果 Debug Analysis 那次做过 deskew，复用时会按同一角度重新旋转后再裁切，避免裁切框偏移。

命令行可用 `--no-reuse-analysis` 强制重新检测。

### 输出目录

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
- `split_summary.csv`：方便人工浏览的表格。
- `_debug_analysis/*_debug_analysis.jpg`：四联 Debug Analysis 图。
- `needs_review/`：低置信原 TIFF 复核目录。

普通启动器不会覆盖已有裁切 TIFF。命令行可用 `--overwrite` 覆盖。

### 命令行

Debug Analysis dry run:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

本地诊断测试：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run --diagnostics
```

`--diagnostics` 只写诊断报告字段并在 Separator evidence 面板画诊断 tick，不改变裁切框、置信度或 PASS/REVIEW。普通启动器不会开启它。

普通自动裁切：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

片头 / 局部片条：

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

关闭并行：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --jobs 1
```

默认并行最多处理 2 张 TIFF。报告仍由主进程写入，避免多个 worker 同时写报告文件。

调整输出 bleed：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 20 --bleed-y 10
```

`--bleed-x` 是长轴 bleed，`--bleed-y` 是短轴 bleed。

关闭自动校斜：

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off --report --debug-analysis --dry-run
```

低置信结果也强制导出：

```bash
python3 X5_Crop.py . --format 135 --strip full --report --export-review
```

### License

本项目以 MIT License 开源，详见 `LICENSE`。

## English Guide

### What This Tool Does

X5 Crop processes `.tif` / `.tiff` long film-strip scans in the same folder and
exports individual TIFF frames only when the detection confidence is high.
Low-confidence files are reported as `needs_review` and the original TIFF is
copied to `needs_review/` for manual inspection.

Core rules:

- Easy scans are cropped automatically.
- Difficult scans are sent to review.
- Only high-confidence detections are exported automatically.
- Fallbacks must not make difficult images pass by accident.
- Output TIFF quality and metadata behavior should stay as close to the source
  TIFF as possible.

X5 Crop scores candidates inside the film format and strip mode you choose,
using outer-frame geometry, separator evidence, content evidence, and expected
aspect ratios together. Only high-confidence results are exported
automatically. Weak, conflicting, or unusual cases are sent to review.

V3.6.4 keeps bleed outside detection and adds a narrow white-edge outer alignment correction:

- Detection uses no bleed when scoring outer boxes, gaps, confidence, or
  PASS/REVIEW.
- Output bleed defaults to 20px on the long axis and 10px on the short axis.
- Horizontal strips use 20px left/right and 10px top/bottom. Vertical strips are
  rotated accordingly.
- A small PASS-only geometry polish may slightly expand long-axis output edges.
- If both end separators are reliable, the content box is complete, and one
  long-axis outer edge is nearly all white, the outer box may be pulled inward
  slightly before the final output bleed is applied.
  It does not change confidence or PASS/REVIEW.
- Overlapped frames, irregular frame spacing, weak separators, or conflicting
  content evidence are handled conservatively. The script should not loosen
  confidence rules just to export automatically.
- In 135 full-strip mode, a strong overlap-risk model gap sends the scan to
  REVIEW instead of automatic export.

### Changelog

Releases are stable packages for normal use. The `main` branch may contain
development versions that are still being validated.

For the more detailed local development record, see `CHANGELOG.md`.

| Version | Status | Detection / Workflow Changes |
|---|---|---|
| V3.6.12 | Current active development | Tunes format-aware `edge-pair` with full `Test/120` and half-frame dry runs: 120-66 / 120-67 now accept wider, lower-background 120 separator evidence while content/aspect REVIEW gates remain conservative; half-frame parameters are unchanged. |
| V3.6.11 | Development | Extends `edge-pair` from 135-only to format-aware full-strip logic: 135 keeps its original parameters, while other formats use more conservative search windows, gutter widths, and quality thresholds. |
| V3.6.10 | Development | Cleans low-risk V3.6.9 leftovers: removes the unused `grid_protection_trust()` wrapper, fixes CLI version text, bleed defaults, `--analysis` help, and stale diagnostic wording. Detection flow is unchanged. |
| V3.6.9 | Development | Unifies active grid protection with lightweight diagnostic hard-gap trust: before grid can protect a red gap, it can now detect nearby conflicts, geometry conflicts, and suspected internal edge / frame border cases. |
| V3.6.8 | Development | Replaces V3.6.7's exact single-anchor gate with `lucky_pass_risk_score`: weak global evidence, suspicious hard gaps, overlap model gaps, and geometry stability are scored together; only scores above the threshold go to REVIEW. |
| V3.6.7 | Development | Promotes nearby stronger separator checks into a narrow correction: a red separator is moved only when the nearby candidate is clearly stronger, geometry improves, and confidence is not increased. It also sends `X5_00041`-like single-anchor lucky PASS shapes to REVIEW. |
| V3.6.6 | Development | Adds hard-gap trust diagnostics, nearby stronger separator checks, and prevents weaker grid fits from overriding `strong_separator` gaps. This is for observing and protecting reliable red separators. |
| V3.6.5 | Current active development | Raises the diagnostics-run worker cap to 4 while normal runs still cap at 2. This mainly supports the local diagnostics launcher and does not change detection logic. |
| V3.6.4 | Current active development | Returns to the V3.6.2 detection baseline. Adds a narrow long-axis white-edge outer correction: only when both end hard separators are reliable, the content box is complete, and one edge is nearly all white can the outer box be pulled inward near the content edge. |
| V3.6.3 | Paused / reference direction | Tried treating overlap / near-overlap as difficult: in 135 full-strip mode, strong overlap risk on a model gap forced REVIEW instead of automatic export. This direction is paused while future work starts from narrower diagnostics and corrections. |
| V3.6.2 | Stable Release | First cleanup step after diagnostic stabilization: folds `equal-broad-region` into ordinary `equal`, and shrinks `hard_fallback_detection` to a review-only equal split fallback to reduce low-value methods and report noise. Overlap, near-overlap, and locally irregular spacing can still be misdetected, so use Debug Analysis for manual review on difficult scans. |
| V3.6.1 | Development | Continues the diagnostic layer: diagnostic report fields and diagnostic ticks are generated only with explicit `--diagnostics`; normal launchers do not enable diagnostics. Adds finer overlap-risk levels while still not changing output boxes, confidence, or PASS/REVIEW. |
| V3.6 | Development | Diagnostic cleanup from the V3.3.1 output baseline: adds read-only `diagnostics_v3_6`, hard-gap trust diagnostics, and overlap/continuous-content diagnostics. It does not change V3.3.1 `status`, `outer_box`, `frame_boxes`, or confidence. |
| V3.5 | Paused / rolled-back development attempt | Tried lightweight semantic validation for red hard separators. Testing affected previously accurate scans, so it is not active as a V3.6 correction rule. |
| V3.4.2 | Paused / rolled-back development attempt | Tried conservative local grid segments. Testing affected previously accurate scans, so it is not active as a V3.6 correction rule. |
| V3.4.1 | Paused / reference direction | Tried keeping strong hard separators authoritative when they conflict with robust grid. The direction remains useful, but the active baseline is back to V3.3.1. |
| V3.4 | Development | Simplifies detection: removes the enhanced separator layer, folds broad-region fallback into ordinary equal gaps, and uses content detection only as validation for full strips. |
| V3.3.2 | Development | Adds conservative overlap-like gap marking so suspected overlap/continuous-content model gaps are not used as strong same-frame-size anchors. |
| V3.3.1 | Stable Release / V3.6 output baseline | Keeps the stable V3-style outer/gap/candidate chain. Bleed is applied only to final output, reports, and Debug Analysis, not detection scoring. Packaged as the stable downloadable release. |
| V3.3 | Development | Separates detection bleed from output bleed. Default output bleed is 20px on the long axis and 10px on the short axis. |
| V3.2 | Development | Returns to the V3-style main detection chain while keeping safety gates that send clearly weak-evidence scans to review. |
| V3.1.x | Experimental | Tried more aggressive outer/gap correction, local rescue, and expansion strategies. Some cases improved, but stability on already-good scans could be affected, so these were not promoted as stable. |
| V3.0 | Baseline | Establishes the main X5 Crop script, format selection, fixed-count full-strip mode, partial mode, Debug Analysis, and high-confidence auto-crop / low-confidence review workflow. |

### Download And Layout

For normal use, download the latest stable zip package from GitHub Releases.
Releases are the user-facing stable updates. The repository `main` branch may
contain in-progress development changes that are useful for testing or reviewing
the latest work.

The Release zip contains the script, the two main launchers, README, and the
quick-start guide:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
```

Put `X5_Crop.py`, the launcher for your system, and the TIFF scans in the same
folder. Then double-click the launcher.

The launcher-only workflow is not supported. The launcher and `X5_Crop.py` must
travel together.

### Install Dependencies

If a new machine is missing dependencies, install them from the installer files
in the source repository, or install the Python dependencies manually. Installer
launchers are no longer included in the Release zip.

macOS:

```text
install/X5_Crop_Mac_install.command
```

Windows:

```text
install/X5_Crop_win_install.bat
```

The installer uses user-level Python packages:

```bash
python3 -m pip install --user -U numpy tifffile imagecodecs Pillow
```

This keeps the project folder movable. Dependencies belong to the current
user's Python installation, not to this folder.

The main launchers prefer a Python that can already import `numpy`, `Pillow`,
and `tifffile`. This helps avoid accidentally using the macOS system Python or
another empty Python environment when a dependency-ready Python is available.

### Launcher Flow

macOS:

```text
X5_Crop_Mac.command
```

Windows:

```text
X5_Crop_win.bat
```

The launcher asks:

```text
format:
partial mode? [y/n, return=no]:
debug analysis? [y/n, return=no]:
```

Format choices:

| Input | Format |
|---|---|
| Return / `135` | `135` |
| `dual` / `135 dual` / `135-dual` | dual-strip 135 |
| `xpan` | XPAN |
| `half` | half-frame |
| `645` | 120-645 |
| `66` | 120-66 |
| `67` | 120-67 |

Unknown formats are rejected and the launcher asks again. For `partial mode` and
`debug analysis`, use `yes` / `no` / `y` / `n`; Return means `no`.

Full-strip mode uses fixed frame counts:

| Format | Count |
|---|---:|
| `135` | 6 |
| `135-dual` | 12 |
| `half` | 12 |
| `xpan` | 3 |
| `120-645` | 4 |
| `120-66` | 3 |
| `120-67` | 3 |

Partial mode uses auto count and is intended for leader, tail, partial strips,
or scans that do not fill the whole holder.

### Debug Analysis

Debug Analysis is a dry run. It writes analysis JPGs and reports, but no cropped
TIFFs.

Each Debug Analysis JPG has four panels:

- `Original gray`: original grayscale detection image.
- `Debug boxes`: outer box and final output crop boxes.
- `Separator evidence`: separator evidence.
- `Content evidence`: content evidence.

Horizontal strips are stacked vertically; vertical strips are laid out
horizontally.

The top status line shows either `PASS` or `REVIEW`. `PASS` means the file would
be cropped automatically. `REVIEW` means it will not be auto-exported.

`Debug boxes` colors:

| Color | Meaning |
|---|---|
| Green outer box | Detected usable film-strip area |
| Semi-transparent color blocks | Final output crop boxes, including output bleed |

`Separator evidence` colors:

| Color | Meaning |
|---|---|
| Red box / line | Real separator evidence detected from the original image |
| Yellow tick | Global or local grid / pitch-model cut line, not necessarily a visible separator |
| Purple tick | Equal/fallback cut line with weak evidence |
| White tick | Other separator source |

### Reusing Debug Analysis For Export

If you run Debug Analysis first and then run normal export with the same key
settings, X5 Crop reuses `split_report.jsonl`:

- `approved_auto` files are cropped from the cached crop boxes.
- `needs_review` files are skipped.
- Changed TIFF size, modification time, page shape, script version, or key
  parameters will force a fresh detection.
- If Debug Analysis used deskew, export reuses the same angle before cropping.

Use `--no-reuse-analysis` to force a fresh detection.

### Command Line

Debug Analysis dry run:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run
```

Local diagnostic test:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run --diagnostics
```

`--diagnostics` only writes diagnostic report fields and diagnostic ticks in the Separator evidence panel. It does not change crop boxes, confidence, or PASS/REVIEW. Normal launchers do not enable it.

Normal auto export:

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial strip:

```bash
python3 X5_Crop.py . --format 135 --strip partial --report
```

Disable parallel processing:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --jobs 1
```

Set output bleed:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 20 --bleed-y 10
```

Disable deskew:

```bash
python3 X5_Crop.py . --format 135 --strip full --deskew off --report --debug-analysis --dry-run
```

Force export of review files:

```bash
python3 X5_Crop.py . --format 135 --strip full --report --export-review
```

### Output Folder

Default output:

```text
split_output/
```

Common contents:

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

### License

This project is open source under the MIT License. See `LICENSE`.
