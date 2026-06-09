# X5 Crop

X5 Crop 是一个用于 Hasselblad / Imacon X5 胶片片夹长图的 TIFF 自动裁切工具。它会把同一文件夹里的长条 TIFF 扫描图拆分成单张 TIFF；只有高置信结果会自动导出，低置信或困难图片会进入复核。

当前 active 脚本版本：V4.0.1

当前稳定发布版本：v4.0.1（GitHub Releases）

普通用户请下载 GitHub Releases 里的 `X5-Crop-vX.X.zip`。不要下载 GitHub 自动生成的 `Source code` / 源码压缩包；源码包是开发源码结构，不是整理好的用户发布包。

脚本不会修改原始 TIFF。自动裁切会生成新文件；进入 `needs_review/` 的文件也是原 TIFF 的复制粘贴，方便人工处理。自动裁切输出的 TIFF 会保留原 TIFF 的画质相关属性，包括但不限于位深、通道结构、ICC / 色彩空间、resolution 和 metadata；脚本不会为了裁切而主动降位深、改色、压缩或重采样图像数据。

文档分工：

- `快速启动_Quick_Start.md`：最短上手步骤，适合第一次使用或给他人转交工具。Release 包内对应文件名为 `快速启动_Quick_Start.txt`。
- `README.md`：完整用户手册，说明安装、文件摆放、启动器、Debug Analysis、输出目录和命令行参数。Release 包内对应文件名为 `README.txt`。
- `CHANGELOG.md`：开发记录和版本差异，保留在 GitHub 仓库中，适合排查行为变化、回滚或继续调检测逻辑。

仓库 `main` 分支是开发进度，可能比 Release 新，但不一定是稳定发布版。普通使用以 GitHub Release 为准。

## 中文指南

### 这个工具做什么

X5 Crop 会处理同一个文件夹里的 `.tif` / `.tiff` 长图，并把高置信结果自动裁切成单张 TIFF。低置信结果不会自动裁切；脚本会写入报告，并在需要时把原 TIFF 复制到 `needs_review/`，方便人工复核。

核心原则：

- 只有高置信检测结果才自动导出。
- 不为了让困难图片通过而放宽置信规则。
- 困难样片进入复核，避免靠猜测自动裁切。
- 自动裁切输出 TIFF 会保留原 TIFF 的画质相关属性，包括但不限于位深、通道结构、ICC / 色彩空间、resolution 和 metadata。

脚本会在你指定的胶片格式和片条模式内，综合外框、分隔、内容和画幅几何证据评分。最终只有高置信结果会自动导出；证据不足、证据互相冲突或画幅状态异常时会进入复核。

### 为什么不是 App 封装

X5 Crop 目前保持为脚本 + 启动器，而不是做成传统 App。这个选择主要服务三个目标：轻量、可移动、易清理。

- 不需要系统级 App 安装，也就不会留下应用支持目录、偏好设置、后台服务或卸载残留。
- 删除项目文件夹就能移除脚本本体、启动器和这个文件夹里的输出。
- Python 依赖是用户级依赖，可以用卸载启动器清理；不需要卸载一个 App 再去找散落的残留文件。
- 可以多开：把 Release 里的 `X5_Crop.py` 和对应系统主启动器复制到不同 TIFF 文件夹，就可以同时处理多个文件夹的图片。

代价是第一次使用需要先运行安装启动器，让当前用户的 Python 拥有必要依赖。整体上，它更像一个干净、可移动的工具箱，而不是固定安装在系统里的 App。

当前默认行为：

- 自动裁切输出 TIFF 以原图数据为基础写出，不会为了裁切而主动降位深、改色、压缩或重采样。脚本会保留原 TIFF 的位深、通道结构、ICC / 色彩空间、resolution 和 metadata 等画质相关属性。
- 检测阶段不使用 bleed；bleed 只在最终输出和 Debug Analysis 色块里应用。
- 默认输出 bleed 为长轴 20px、短轴 10px。横向长图是左右各 20px、上下各 10px；竖向长图会自动对应旋转。
- 如果检测到叠片 / 近似叠片 / 连续内容风险，输出长轴 bleed 会自动提高到 50px，给这类困难图更多安全余量。这个调整只影响最终输出和 Debug Analysis 色块，不参与检测评分。
- 对已经 `approved_auto` 且没有复核原因的结果，会做一个很小的输出几何 polish：只允许长轴最多向外微扩。这一步不改变 PASS/REVIEW 和置信度。
- `--analysis` 仍保留一个很保守的增强分隔辅助层：`auto` 只在分隔证据偏弱时尝试，`always` 每次尝试，`off` 关闭。它和 deskew 的增强角度候选共用同一个参数入口。
- 对近似叠片、片距局部不稳定、分隔证据不足或内容证据冲突的长图，会保持保守判断，不会为了自动导出而放宽置信规则。

格式支持状态：

- 当前版本的检测逻辑、参数和回归测试主要服务普通 135。
- 其它 format 已经有 format-aware 参数入口，但还没有像 135 那样逐张细调。
- 未对其它 format 开放的高风险 active 能力包括：nearby separator active correction、lucky-pass risk、leading-grid failure。它们目前只在已验证的 135 路径启用。
- 对 half / xpan / 120 格式，Debug Analysis 里的诊断信息可以辅助判断，但正式自动裁切仍建议人工复核后使用。

### 运行耗时和终端提示

- 最近一次普通 135 启动器实测：48 张 TIFF 全量正式裁切用时 394 秒，平均约 8.2 秒/张。
- Debug Analysis 需要额外生成 JPG 分析图，通常每张约 10-30 秒。
- 大尺寸 TIFF、开启 deskew、较慢硬盘或较慢电脑都会更久。
- 终端在处理单张大 TIFF 时可能一段时间没有新的提示；这通常不是出错，而是脚本还在读取、检测、校平或写文件。等它进入下一张图或完成当前图后会继续输出状态。

### 下载和文件摆放

普通使用推荐从 GitHub Releases 下载最新的稳定版压缩包。Release 是面向用户的稳定更新；仓库里的 `main` 分支可能包含正在验证中的开发进度，适合参与测试或查看最新改动。

Release 压缩包封装单文件版入口脚本、两个主启动器、TXT 格式用户文档和安装器：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

Release 里的 `X5_Crop.py` 是从 V4 模块化源码自动生成的单文件发布版，已经内置 `x5crop/` 的内部代码。普通用户不需要复制 `x5crop/` 文件夹。Release 包内的用户文档使用 `.txt` 扩展名，便于在不同系统上直接打开阅读；仓库中的维护源文档仍保留为 `.md`。

如果你不是下载 Release，而是直接从仓库 `main` 分支运行开发源码，那么根目录 `X5_Crop.py` 是开发入口，仍然需要旁边的 `x5crop/` 包。这是给开发和测试用的结构，不是普通 Release 用户需要复制的结构。

仓库里还包含 `X5_Crop_Mac_diagnostics.command`，这是给开发和本地测试用的 macOS 诊断启动器。它会固定开启 dry run、Debug Analysis、诊断报告和 `--jobs 4`，不会导出裁切 TIFF，也不会复制 `needs_review/` 文件。它不属于普通用户启动器，也不会放进 Release 包。

对应系统的主启动器是：

```text
macOS 主启动器: X5_Crop_Mac.command
Windows 主启动器: X5_Crop_win.bat
```

`install/` 里的安装启动器用于第一次安装依赖；卸载启动器用于清理用户级 Python 依赖。它们都不是日常裁切用的主启动器。

把 Release 里的 `X5_Crop.py`、对应系统的主启动器和要裁切的 TIFF 长图放在同一个文件夹里，然后双击主启动器运行。

不支持“只把启动器放进 TIFF 文件夹、脚本留在别处”的模式。

### 第一次安装依赖

新机器第一次使用时，先运行 Release 包里 `install/` 文件夹内的安装器，或者手动安装 Python 依赖。

macOS:

```text
install/X5_Crop_Mac_install.command
```

macOS 安装器还会尝试为当前 Release 文件夹里的主启动器添加执行权限，并移除下载隔离标记。它不能把脚本永久加入 macOS 的全局可信名单。

安装后，可以把 Release 里的 `X5_Crop.py` 和对应系统的主启动器作为一组复制到不同的 TIFF 文件夹里使用：

```text
macOS: X5_Crop.py + X5_Crop_Mac.command
Windows: X5_Crop.py + X5_Crop_win.bat
```

不要只移动主启动器，也不要只移动 `X5_Crop.py`；主启动器和入口脚本必须放在同一个文件夹里。

如果重新下载、重新解压，或者从网页、网盘、聊天软件又拿到一份新的 Release，那一份新文件夹可能重新带有 macOS 下载隔离标记。请在新的文件夹里再运行一次安装启动器。

如果 macOS 双击安装启动器打不开，请打开 Terminal，输入 `cd `，把 X5 Crop 文件夹拖进窗口后按 Return，然后运行：

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

如果安装完成后，双击主启动器 `X5_Crop_Mac.command` 仍然打不开，请打开 Terminal，输入 `cd `，把放有 `X5_Crop.py`、`X5_Crop_Mac.command` 和 TIFF 长图的文件夹拖进窗口后按 Return，然后运行：

```bash
/bin/bash X5_Crop_Mac.command
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

### 干净卸载

X5 Crop 没有传统 App 安装过程。想移除脚本本体时，直接删除 X5 Crop 文件夹即可。删除前如果要保留裁切结果，请先把 `split_output/` 移到其它位置。

如果想同时清理安装过的 Python 依赖，可以运行对应系统的卸载启动器：

```text
macOS: install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

卸载启动器会询问是否移除这些用户级 Python 包：

```text
numpy
tifffile
imagecodecs
Pillow
```

请注意：这些依赖可能也被你电脑上的其它 Python 脚本或工具使用。卸载它们之后，X5 Crop 和其它依赖这些库的 Python 工具可能无法运行，需要重新安装依赖。卸载启动器不会删除 Python 本体；如果你手动卸载 Python，可能影响所有依赖这个 Python 的脚本、命令行工具或开发环境。

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

partial mode 的意思是“这可能不是一条完整片条，让脚本自己估计张数”。它适合：

- 片头或片尾。
- 只扫到几张的局部片条。
- 120 片夹里没有铺满整条的情况。
- 你不确定应该有几张照片的情况。

不开启 partial 时，脚本会使用上表里的固定张数，速度更快，判断也更稳定。完整片条请优先保持 `partial mode = no`。开启 partial 时，张数使用 auto，脚本会更保守；`135-dual` 目前只建议用于完整双条 135，partial 下会倾向复核。

### Debug Analysis

如果开启 Debug Analysis，脚本只生成分析 JPG 和报告，不输出裁切 TIFF。输出位置：

```text
split_output/_debug_analysis/
```

这里的 `dry run` 是“试运行 / 分析模式”：脚本会读取 TIFF、执行检测、计算 PASS/REVIEW、生成 Debug Analysis JPG 和报告，但不会正式导出裁切后的单张 TIFF。它也不会修改原 TIFF。适合在正式裁切前检查外框、分隔线、裁切范围和置信度。

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

| 颜色 / 标记 | 含义 | 是否直接影响裁切 |
|---|---|---|
| 绿色外框 | 脚本认为整条胶片有效区域的外框 | 会 |
| 不同半透明色块 | 每一张最终输出裁切范围，包含输出 bleed | 会，这是最终输出范围 |

`Separator evidence` 颜色：

| 颜色 / 标记 | 含义 | 是否直接影响裁切 |
|---|---|---|
| 红色框 / 红色线 | 原图中检测到的真实分隔区域，包括黑条和可信双边缘 | 会，是强分隔证据 |
| 黄色短 tick | grid / 全局或局部片距模型推算出的切线，不代表一定看到真实黑条 | 可能会，是模型补位 |
| 紫色短 tick | 证据不足时的等分或 fallback 切线 | 可能会，但通常不会让困难图自动通过 |
| 白色短 tick | 其它未分类切线来源 | 主要用于辅助阅读 |

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
- `needs_review/`：低置信原 TIFF 复核目录。这里的文件是原 TIFF 的复制粘贴，脚本没有对这些复制进去的 TIFF 做裁切、压缩、改色、校平或其它处理。你可以放心在这个文件夹里人工查看、移动、删除或另行处理这些副本。

自动裁切输出的单张 TIFF 是新文件，并会沿用原 TIFF 的画质相关属性，包括位深、通道结构、ICC / 色彩空间、resolution 和 metadata。裁切过程不会主动把图像转成更低位深、改变色彩空间、压缩或重采样。

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

`--diagnostics` 只写诊断报告字段并在 Separator evidence 面板画诊断 tick，不改变裁切框、置信度或 PASS/REVIEW。普通启动器不会开启它。仓库里的 `X5_Crop_Mac_diagnostics.command` 可以双击运行同类本地诊断流程，但它是开发/测试工具，不随 Release 包分发。

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

Current active script version: V4.0.1

Current stable release: v4.0.1 (GitHub Releases)

Download `X5-Crop-vX.X.zip` from GitHub Releases. Do not give normal users the
auto-generated GitHub `Source code` zip; that is the development source layout,
not the prepared user package.

The script does not modify original TIFF files. Auto crops are written as new
files; files in `needs_review/` are plain copies of the source TIFFs for manual
handling. Auto-cropped TIFF output preserves source-TIFF quality-related
attributes, including but not limited to bit depth, channel
layout, ICC / color space, resolution, and metadata. Cropping does not
intentionally lower bit depth, recolor, compress, or resample image data.

Document map:

- `快速启动_Quick_Start.md`: shortest first-use instructions. In the Release
  package, this file is named `快速启动_Quick_Start.txt`.
- `README.md`: complete user manual for setup, file placement, launchers,
  Debug Analysis, outputs, and command-line usage. In the Release package, this
  file is named `README.txt`.
- `CHANGELOG.md`: development notes and version differences for regression
  checks, rollback, and detector work. It is kept in the GitHub repository.

The repository `main` branch tracks development progress. It may be newer than
the Release, but it is not necessarily the stable user package. For normal use,
prefer GitHub Releases.

### What This Tool Does

X5 Crop processes `.tif` / `.tiff` long film-strip scans in the same folder and
exports individual TIFF frames only when the detection confidence is high.
Low-confidence files are reported as `needs_review`; when needed, the original
TIFF is copied to `needs_review/` for manual inspection.

Core rules:

- Only high-confidence detections are exported automatically.
- Fallbacks must not make difficult images pass by accident.
- Difficult scans are sent to review instead of being guessed through.
- Auto-cropped TIFF output preserves source-TIFF quality-related attributes,
  including bit depth, channel layout, ICC / color space, resolution, and
  metadata.

X5 Crop scores candidates inside the film format and strip mode you choose,
using outer-frame geometry, separator evidence, content evidence, and expected
aspect ratios together. Only high-confidence results are exported
automatically. Weak, conflicting, or unusual cases are sent to review.

### Why This Is Not Packaged As An App

X5 Crop currently stays as a script plus launchers instead of a traditional app
package to keep it lightweight, portable, and clean:

- There is no system-level app installation, so there are no app support
  folders, preferences, background services, or app-uninstall leftovers.
- Deleting the X5 Crop folder removes the script, launchers, and outputs inside
  that folder.
- Python dependencies are user-level packages and can be cleaned with the
  uninstall launcher; you do not need to uninstall an app and then hunt for
  scattered leftovers.
- You can run multiple folders at once: copy the Release `X5_Crop.py` and the
  matching main launcher into different TIFF folders and launch each folder
  separately.

The tradeoff is that first use requires running the installer launcher so the
current user's Python has the required dependencies. In practice, X5 Crop is a
movable toolkit rather than a fixed-location app install.

Current default behavior:

- Auto-cropped TIFFs are written from the source image data and are not
  intentionally lowered in bit depth, recolored, compressed, or resampled for
  cropping. X5 Crop preserves source-TIFF quality-related attributes such as
  bit depth, channel layout, ICC / color space, resolution, and metadata.
- Detection uses no bleed when scoring outer boxes, gaps, confidence, or
  PASS/REVIEW.
- Output bleed defaults to 20px on the long axis and 10px on the short axis.
- Horizontal strips use 20px left/right and 10px top/bottom. Vertical strips are
  rotated accordingly.
- When overlap, near-overlap, or continuous-content risk is detected, long-axis
  output bleed is automatically raised to 50px for extra safety. This affects
  final output and Debug Analysis crop blocks only, not detection scoring.
- A small PASS-only geometry polish may slightly expand long-axis output edges.
- `--analysis` still keeps a conservative enhanced separator assist: `auto`
  tries it only on weak separator evidence, `always` tries it every time, and
  `off` disables it. The same option also controls enhanced deskew angle
  candidates.
- If both end separators are reliable, the content box is complete, and one
  long-axis outer edge is nearly all white, the outer box may be pulled inward
  slightly before the final output bleed is applied.
  It does not change confidence or PASS/REVIEW.
- Overlapped frames, irregular frame spacing, weak separators, or conflicting
  content evidence are handled conservatively. The script should not loosen
  confidence rules just to export automatically.
- In 135 full-strip mode, overlap-risk and lucky-pass-risk signals can reduce
  confidence or send suspicious scans to REVIEW, but they are not used to make
  difficult images easier to approve.

### Runtime And Terminal Output

- The latest normal 135 launcher measurement was 394 seconds for 48 TIFF files,
  or about 8.2 seconds per file.
- Debug Analysis also writes JPG analysis images and usually takes about 10-30
  seconds per file.
- Very large TIFFs, deskew, slower disks, or slower computers can take longer.
- The terminal may show no new message for a while while one large TIFF is being
  read, detected, deskewed, or written. This usually does not mean the script has
  failed; it is still running and will print the next status line after the
  current file advances or finishes.

### Download And Layout

For normal use, download the latest stable zip package from GitHub Releases.
Releases are the user-facing stable updates. The repository `main` branch may
contain in-progress development changes that are useful for testing or reviewing
the latest work.

The Release zip contains the standalone entry script, the two main launchers,
TXT user documents, and installer launchers:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.txt
快速启动_Quick_Start.txt
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

The Release `X5_Crop.py` is generated from the modular V4 source tree as a
standalone file. It embeds the internal `x5crop/` code, so normal users do not
need to copy an `x5crop/` folder.

User documents inside the Release package use `.txt` filenames so they can be
opened easily across systems. The repository source documents remain `.md` for
maintenance and GitHub rendering.

The repository also includes `X5_Crop_Mac_diagnostics.command`, a macOS
diagnostic launcher for development and local testing. It always enables dry
run, Debug Analysis, diagnostics, and `--jobs 4`; it does not export cropped
TIFFs and does not copy `needs_review/` files. It is not a normal user launcher
and is not included in the Release package.

If you run directly from the repository `main` branch instead of a Release
package, root `X5_Crop.py` is the development entry point and still needs the
neighboring `x5crop/` package. That structure is for development and testing,
not the normal Release copy workflow.

The main launcher for each system is:

```text
macOS main launcher: X5_Crop_Mac.command
Windows main launcher: X5_Crop_win.bat
```

Installer launchers inside `install/` are for first-time dependency setup.
Uninstall launchers are for removing user-level Python dependencies. They are
not the main launchers used for everyday cropping.

Put the Release `X5_Crop.py`, the main launcher for your system, and the TIFF
scans in the same folder. Then double-click the main launcher.

The launcher-only workflow is not supported. The launcher and `X5_Crop.py` must
travel together.

### Install Dependencies

If a new machine is missing dependencies, run the installer in the Release
package's `install/` folder first, or install the Python dependencies manually.

macOS:

```text
install/X5_Crop_Mac_install.command
```

The macOS installer also tries to make the main launcher executable and remove
the download quarantine flag from the current Release folder. It cannot
permanently add the script to a global macOS trusted list.

After installation, you can copy the Release `X5_Crop.py` and the main launcher
for your system as a set into different TIFF folders:

```text
macOS: X5_Crop.py + X5_Crop_Mac.command
Windows: X5_Crop.py + X5_Crop_win.bat
```

Do not move only the main launcher, because the launcher must stay in the same
folder as `X5_Crop.py`.

If you download, unzip, or receive another fresh Release copy from a browser,
cloud drive, or chat app, that new folder may have a new macOS quarantine flag.
Run the installer again inside that new folder.

If double-clicking the macOS installer does not work, open Terminal, type
`cd `, drag the X5 Crop folder into the window, press Return, then run:

```bash
/bin/bash install/X5_Crop_Mac_install.command
```

If the main launcher `X5_Crop_Mac.command` still will not open after
installation, open Terminal, type `cd `, drag the folder containing
`X5_Crop.py`, `X5_Crop_Mac.command`, and the TIFF scans into the window, press
Return, then run:

```bash
/bin/bash X5_Crop_Mac.command
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

### Clean Uninstall

X5 Crop has no traditional app installation. To remove the script itself, delete
the X5 Crop folder. If you want to keep cropped output, move `split_output/`
somewhere else before deleting the folder.

To also remove the Python dependencies that were installed for X5 Crop, run the
uninstall launcher for your system:

```text
macOS: install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

The uninstall launcher asks before removing these user-level Python packages:

```text
numpy
tifffile
imagecodecs
Pillow
```

These packages may also be used by other Python scripts or tools on your
computer. After uninstalling them, X5 Crop and any other Python tool that
depends on them may stop working until the dependencies are installed again.
The uninstall launcher does not remove Python itself. If you manually uninstall
Python, that can affect every script, command-line tool, or development
environment that depends on that Python installation.

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

Partial mode means “this may not be a complete strip, so let the script estimate
the frame count.” Use it for:

- Leader or tail scans.
- Partial strips with only a few frames.
- 120 holder scans that do not fill the whole holder.
- Cases where you are not sure how many frames should be present.

When partial mode is off, the script uses the fixed counts above. That is faster
and more stable for complete strips. Keep `partial mode = no` for normal full
strips. When partial mode is enabled, count is auto and the script behaves more
conservatively. `135-dual` is currently recommended only for complete dual 135
strips; partial dual-strip cases tend to be reviewed.

### Debug Analysis

Debug Analysis is a dry run. It writes analysis JPGs and reports, but no cropped
TIFFs.

In this project, `dry run` means “test/analyze only.” The script reads the TIFF,
runs detection, decides PASS/REVIEW, and can write Debug Analysis JPGs and
reports, but it does not export cropped frame TIFFs. It also does not modify the
original TIFF. Use it before real export to inspect the outer box, separators,
crop boxes, and confidence.

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

| Color / mark | Meaning | Directly affects crop? |
|---|---|---|
| Green outer box | Detected usable film-strip area | Yes |
| Semi-transparent color blocks | Final output crop boxes, including output bleed | Yes, this is the final output area |

`Separator evidence` colors:

| Color / mark | Meaning | Directly affects crop? |
|---|---|---|
| Red box / line | Real separator evidence detected from the original image | Yes, strong separator evidence |
| Yellow tick | Global or local grid / pitch-model cut line, not necessarily a visible separator | Sometimes, as model fill-in |
| Purple tick | Equal/fallback cut line with weak evidence | Sometimes, but normally does not make difficult scans auto-pass |
| White tick | Other separator source | Mainly for reading the debug image |

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

`--diagnostics` only writes diagnostic report fields and diagnostic ticks in the Separator evidence panel. It does not change crop boxes, confidence, or PASS/REVIEW. Normal launchers do not enable it. The repository `X5_Crop_Mac_diagnostics.command` runs the same kind of local diagnostic workflow from a double-clickable macOS launcher, but it is a development/testing tool and is not shipped in the Release package.

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

Notes:

- `split_report.jsonl`: complete machine-readable report.
- `split_summary.csv`: table for quick human review.
- `_debug_analysis/*_debug_analysis.jpg`: four-panel Debug Analysis images.
- `needs_review/`: low-confidence original TIFF review folder. Files here are
  plain copies of the source TIFFs. The script does not crop, compress, recolor,
  deskew, or otherwise process these copied TIFFs, so you can safely inspect,
  move, delete, or manually process the copies.

Auto-cropped frame TIFFs are new files, and X5 Crop preserves source-TIFF
quality-related attributes, including bit depth, channel
layout, ICC / color space, resolution, and metadata. Cropping does not
intentionally convert the image to a lower bit depth, change its color space,
compress it, or resample it.

### License

This project is open source under the MIT License. See `LICENSE`.
