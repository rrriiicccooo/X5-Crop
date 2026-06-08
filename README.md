# X5 Crop

X5 Crop is a Python entry script plus an internal package for splitting long
TIFF film-strip scans from Hasselblad / Imacon X5 holders into individual TIFF
frames.

当前 active 脚本版本：V4.0

当前稳定发布版本：v4.0（GitHub Releases）

Current active script version: V4.0

Current stable release: v4.0 (GitHub Releases)

## 快速使用

普通用户只需要三步：

1. 第一次使用先运行 `install/` 里的安装启动器。
2. 把 Release 里的 `X5_Crop.py`、对应系统启动器和 TIFF 长图放在同一个文件夹。
3. 双击启动器，按提示选择 format、partial mode 和 Debug Analysis。

请下载 GitHub Releases 里的 `X5-Crop-vX.X.zip`。不要下载 GitHub 自动生成的 `Source code` / 源码压缩包给普通用户使用；源码包是开发结构，不是整理好的用户发布包。

脚本不会修改原始 TIFF。自动裁切会生成新文件；进入 `needs_review/` 的文件也是原 TIFF 的复制粘贴，方便人工处理。

仓库 `main` 分支是开发进度，可能比 Release 新，但不一定是稳定发布版。

第一次在新机器上使用：

1. 解压 Release 压缩包。
2. 可以先打开 `快速启动_Quick_Start.md` 看最短步骤；更详细说明看 `README.md` 和 `CHANGELOG.md`。
3. 第一次使用先运行安装启动器：
   - macOS: `install/X5_Crop_Mac_install.command`
   - Windows: `install/X5_Crop_win_install.bat`
   - macOS 如果双击安装启动器打不开：打开 Terminal，输入 `cd `，把 X5 Crop 文件夹拖进窗口后按 Return，然后运行：

     ```bash
     /bin/bash install/X5_Crop_Mac_install.command
     ```
   - macOS 如果安装完成后双击主启动器 `X5_Crop_Mac.command` 仍打不开：打开 Terminal，输入 `cd `，把放有 TIFF 长图的文件夹拖进窗口后按 Return，然后运行：

     ```bash
     /bin/bash X5_Crop_Mac.command
     ```

4. 把下面这些文件和要裁切的 TIFF 长图放在同一个文件夹里：
   - `X5_Crop.py`
   - macOS 用 `X5_Crop_Mac.command`
   - Windows 用 `X5_Crop_win.bat`
5. 双击对应系统的主启动器：macOS 是 `X5_Crop_Mac.command`，Windows 是 `X5_Crop_win.bat`。
6. 先选择胶片格式，再选择是否开启 partial mode 和 Debug Analysis。

常用选择：

- 直接回车或输入 `135`：普通 135，一条 6 张。
- 输入 `dual` 或 `135 dual`：双条 135，一共 12 张。
- 输入 `xpan` / `half` / `645` / `66` / `67`：对应其它格式。
- `partial mode` 直接回车是 `no`。完整片条请保持 `no`；只有片头、片尾、局部片条、没有铺满片夹或不确定张数时才开启。
- `debug analysis` 直接回车是 `no`；输入 `y` 会只生成分析 JPG 和报告，不正式裁切。
- 正常裁切不会生成 report；只有开启 Debug Analysis 时启动器才会写报告。

格式准确度说明：

- 当前开发版本主要围绕普通 135 长图优化和回归测试。
- `half`、`xpan`、`645`、`66`、`67` 可以选择使用，但没有经过和 135 同等细致的参数调整，效果可能不如 135 稳定。
- 对其它 format 的结果，建议先用 Debug Analysis 检查，确认可靠后再正式裁切。
- 一些高风险修正能力目前只在已验证的 135 路径启用；其它 format 暂时只保留独立参数入口和诊断基础。

运行耗时：

- 最近一次普通 135 启动器实测：48 张 TIFF 全量正式裁切用时 322 秒，平均约 6.7 秒/张。
- Debug Analysis 需要额外生成 JPG 分析图，通常每张约 10-30 秒。
- 大尺寸 TIFF、开启 deskew、较慢硬盘或较慢电脑都会更久。
- 终端在处理单张大 TIFF 时可能一段时间没有新的提示；这通常不是出错，而是脚本还在读取、检测、校平或写文件。等它进入下一张图或完成当前图后会继续输出状态。

高置信结果会自动裁切；低置信结果会进入 `needs_review/`，方便人工复核。`needs_review/` 里的 TIFF 是原文件副本，脚本不会对这些副本做裁切、压缩、改色或校平。

## Quick Start

Normal users only need three steps:

1. On first use, run the installer launcher inside `install/`.
2. Put the Release `X5_Crop.py`, the platform launcher, and TIFF scans in one folder.
3. Double-click the launcher, then choose format, partial mode, and Debug Analysis.

Download `X5-Crop-vX.X.zip` from GitHub Releases. Do not give normal users the
auto-generated GitHub `Source code` zip; that is the development source layout,
not the prepared user package.

The script does not modify original TIFF files. Auto crops are written as new
files; files in `needs_review/` are plain copies of the source TIFFs for manual
handling.

The repository `main` branch is development progress; it may be newer than the
Release, but it is not necessarily the stable package.

On a new machine:

1. Unzip the Release package.
2. Open `快速启动_Quick_Start.md` for the shortest steps; see `README.md` and
   `CHANGELOG.md` for more detail.
3. On first use, run the installer launcher:
   - macOS: `install/X5_Crop_Mac_install.command`
   - Windows: `install/X5_Crop_win_install.bat`
   - If the macOS installer will not open by double-clicking: open Terminal,
     type `cd `, drag the X5 Crop folder into the window, press Return, then
     run:

     ```bash
     /bin/bash install/X5_Crop_Mac_install.command
     ```
   - If the main launcher `X5_Crop_Mac.command` still will not open after
     installation: open Terminal, type `cd `, drag the TIFF folder into the
     window, press Return, then run:

     ```bash
     /bin/bash X5_Crop_Mac.command
     ```

4. Put these files in the same folder as the TIFF long-strip scans:
   - `X5_Crop.py`
   - macOS: `X5_Crop_Mac.command`
   - Windows: `X5_Crop_win.bat`
5. Double-click the main launcher for your system: `X5_Crop_Mac.command` on
   macOS, or `X5_Crop_win.bat` on Windows.
6. Choose the film format, then choose whether to enable partial mode and Debug
   Analysis.

Common choices:

- Press Return or type `135`: normal 135, 6 frames per strip.
- Type `dual` or `135 dual`: dual-strip 135, 12 frames total.
- Type `xpan` / `half` / `645` / `66` / `67`: other supported formats.
- Press Return for `partial mode` to choose `no`. Keep it off for complete
  strips; enable it only for leader, tail, partial strips, scans that do not
  fill the holder, or uncertain frame counts.
- Press Return for `debug analysis` to choose `no`; type `y` to generate only
  analysis JPGs and reports without exporting cropped TIFFs.
- Normal launcher runs do not write reports; launchers write reports only when
  Debug Analysis is enabled.

Format accuracy note:

- The current development version is primarily optimized and regression-tested
  for normal 135 long-strip scans.
- `half`, `xpan`, `645`, `66`, and `67` are available, but they have not been
  tuned as carefully as 135 and may be less stable.
- For non-135 formats, use Debug Analysis first and review the result before a
  final export.
- Some high-risk correction features are currently enabled only on the validated
  135 path. Other formats have separate policy hooks and diagnostic groundwork,
  but those active corrections are not opened yet.

Runtime:

- On the current test machine with typical 135 TIFF long-strip scans, normal
  export was last measured at 322 seconds for 48 TIFF files, or about 6.7
  seconds per file.
- Debug Analysis also writes JPG analysis images and usually takes about 10-30
  seconds per file.
- Very large TIFFs, deskew, slower disks, or slower computers can take longer.
- The terminal may show no new message for a while while one large TIFF is being
  read, detected, deskewed, or written. This usually does not mean the script has
  failed; it is still running and will print the next status line after the
  current file advances or finishes.

High-confidence results are cropped automatically. Low-confidence results go to
`needs_review/` for manual review. TIFFs in `needs_review/` are plain copies of
the original files; the script does not crop, compress, recolor, or deskew those
copies.

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

### 为什么不是 App 封装

X5 Crop 目前保持为脚本 + 启动器，而不是做成传统 App，主要是为了让它更轻、更干净：

- 不需要系统级安装，也就不会留下应用支持目录、偏好设置、后台服务或卸载残留。
- 删除项目文件夹就能移除脚本本体、启动器和这个文件夹里的输出。
- Python 依赖是用户级依赖，可以用卸载启动器清理；不需要卸载一个 App 再去找散落的残留文件。
- 可以多开：把 Release 里的 `X5_Crop.py` 和对应系统主启动器复制到不同 TIFF 文件夹，就可以同时处理多个文件夹的图片。

代价是第一次使用需要先运行安装启动器，让当前用户的 Python 拥有必要依赖。这个选择更像一个干净、可移动的工具箱，而不是把一切包进一个固定安装位置的 App。

当前默认行为：

- 检测阶段不使用 bleed；bleed 只在最终输出和 Debug Analysis 色块里应用。
- 默认输出 bleed 为长轴 35px、短轴 10px。横向长图是左右各 35px、上下各 10px；竖向长图会自动对应旋转。
- 对已经 `approved_auto` 且没有复核原因的结果，会做一个很小的输出几何 polish：只允许长轴最多向外微扩。这一步不改变 PASS/REVIEW 和置信度。
- `--analysis` 仍保留一个很保守的增强分隔辅助层：`auto` 只在分隔证据偏弱时尝试，`always` 每次尝试，`off` 关闭。它和 deskew 的增强角度候选共用同一个参数入口。
- 对近似叠片、片距局部不稳定、分隔证据不足或内容证据冲突的长图，会保持保守判断，不会为了自动导出而放宽置信规则。

格式支持状态：

- 当前版本的检测逻辑、参数和回归测试主要服务普通 135。
- 其它 format 已经有 format-aware 参数入口，但还没有像 135 那样逐张细调。
- 未对其它 format 开放的高风险 active 能力包括：nearby separator active correction、lucky-pass risk、leading-grid failure。它们目前只在已验证的 135 路径启用。
- 对 half / xpan / 120 格式，Debug Analysis 里的诊断信息可以辅助判断，但正式自动裁切仍建议人工复核后使用。

### 更新日志

Release 是面向普通用户的稳定版；`main` 分支里的开发版本会继续验证新的检测逻辑。

更详细的本地开发记录见 `CHANGELOG.md`。

| 版本 | 状态 | 检测逻辑 / 工作流变化 |
|---|---|---|
| V4.0 | 稳定 Release / 当前 active 开发版 | 大胆模块化重写版：根目录 `X5_Crop.py` 只保留薄入口，实际责任拆进 `x5crop/` 包。`common.py` 管模型、配置和通用工具，`evidence.py` 管灰度/证据图，`io.py` 管 TIFF 读取写出和 metadata，`geometry.py` 管外框、分隔、edge-pair、grid 和 frame fit，`detection/pipeline.py` 管检测主链路和评分，`deskew.py` 管校平，`debug/render.py` 管 Debug Analysis，`reports.py` 管报告复用和裁切写出，`cli.py` 管命令行、并行和单文件流程，`core.py` 只保留兼容导出。同时新增单文件发布版生成器，Release 用户仍然只需要 `X5_Crop.py` 和对应系统启动器。目标不是保守换壳，而是在完整重写结构后保持旧结果：全量 135 default-deskew dry run 对比 V3.9，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 为 0 diff。OpenCV / scipy 等大依赖后端暂定为未来 V5 方向。 |
| V3.9 | 开发版 | 结构清理版：把剩余 outer mask profiles、post-detection confidence caps、deskew span skip、frame-fit 小像素容忍、separator gate mode 和 outer retry 开关收进 policy / format-aware 配置。目标是让“适合百分比 + clamp 的参数、需要按 format 分支的参数、可以推广到其它 format 的能力”都集中管理。全量 135 default-deskew dry run 对比 V3.7，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 为 0 diff。 |
| V3.7 | 开发版 | 合并 frame-size fit 管线：将 cuts 级几何拟合整理为 geometry fallback，将 box 级同画幅拟合整理为 edge-evidence fit，并由统一入口决定使用哪一层。后续继续把高层评分权重、内容证据阈值、诊断语义和 Debug 展示参数收进 format-aware policy。目标是让 `edge-pair` 扩展到各格式之后的检测结构更清楚，同时保持现有 PASS/REVIEW 和输出框不变。 |
| V3.6.12 | 开发版 | 根据 `Test/120` 和半格全量 dry run 调整 format-aware `edge-pair`：120-66 / 120-67 允许更宽、更低背景的 120 暗带证据，但仍保留内容比例冲突等 REVIEW 闸门；半格参数保持不变。 |
| V3.6.11 | 开发版 | 将 `edge-pair` 从 135 专用扩展为 format-aware full-strip 逻辑：135 保持原参数，其它格式使用各自更保守的搜索窗口、gutter 宽度和质量阈值。 |
| V3.6.10 | 开发版 | 清理 V3.6.9 后的低风险残留：移除未使用的 `grid_protection_trust()` 包装函数，修正 CLI 版本、bleed 默认值、`--analysis` help 和诊断说明旧话术。不改变检测流程。 |
| V3.6.9 | 开发版 | 统一 active grid protection 和 diagnostics 的轻量 hard-gap trust：grid 保护红框前也会识别 nearby conflict、geometry conflict、suspect internal edge / frame border，减少“双轨可信度”冲突。 |
| V3.6.8 | 开发版 | 将 V3.6.7 的 single-anchor 精确组合闸门改成 `lucky_pass_risk_score`：多项弱全局证据、可疑 hard gap、overlap model gap 和几何稳定性共同评分；超过阈值才进入 REVIEW。 |
| V3.6.7 | 开发版 | 将附近更强分隔候选从诊断提升为很窄的 correction：只有候选明显更强、移动后几何更合理、且不提高 confidence 时才拉回红框；同时把 `X5_00041` 这类 single-anchor lucky PASS 形态压进 REVIEW。 |
| V3.6.6 | 开发版 | 新增 hard gap trust 诊断、附近更强分隔候选复查，并让稳定性较弱的 grid 不能覆盖 `strong_separator`；用于观察和保护可信红框。 |
| V3.6.5 | 开发版 | 诊断运行的并行上限调到 4；普通运行仍限制为 2。这个改动主要服务本地诊断启动器，不改变检测逻辑。 |
| V3.6.4 | 开发版 | 回到 V3.6.2 检测基线；新增很窄的长轴白边外框修正：只有首尾 hard separator 都可靠、内容框完整、单侧边缘几乎全白时，才允许外框收回内容边缘附近。 |
| V3.6.3 | 已暂停 / 参考方向 | 曾尝试将叠片 / 近似叠片视为困难图：135 full strip 中模型 gap 出现 strong overlap risk 时强制进入 REVIEW。该方向暂时搁置，后续先从更细的诊断和更窄的修正规则发展。 |
| V3.6.2 | 上一稳定 Release | 诊断清理后的第一步逻辑瘦身：`equal-broad-region` 合并为普通 `equal`，`hard_fallback_detection` 缩小为 review-only equal split fallback；目标是减少低收益 method 和报告噪音。叠片、近似叠片、片距局部不稳定等困难图仍可能误识别，建议用 Debug Analysis 人工复核。 |
| V3.6.1 | 开发版 | 继续优化诊断层：诊断报告字段和诊断 tick 改为只在显式 `--diagnostics` 时生成；普通启动器不开启诊断。新增更细的叠片风险分级，仍不改变输出框、置信度或 PASS/REVIEW。 |
| V3.6 | 开发版 | 从 V3.3.1 输出基线出发做诊断清理：新增只读 `diagnostics_v3_6`、红框可信度诊断和叠片/连续内容诊断；不改变 V3.3.1 的 `status`、`outer_box`、`frame_boxes` 或置信度。 |
| V3.5 | 已暂停 / 已回滚的开发尝试 | 尝试新增红色 hard separator 轻量可信度验证。实测会影响原本准确的样片，因此没有进入 V3.6 的实际修正规则。 |
| V3.4.2 | 已暂停 / 已回滚的开发尝试 | 尝试新增保守的局部 grid。实测会影响原本准确的样片，因此没有进入 V3.6 的实际修正规则。 |
| V3.4.1 | 已暂停 / 参考方向 | 尝试让强 hard separator 与 robust grid 冲突时优先保留红色证据。这个方向仍有参考价值，但当前先回到 V3.3.1 作为稳定基线。 |
| V3.4 | 开发版 | 简化检测层的实验方向：曾尝试移除增强分隔层、合并宽分隔 fallback 到普通 equal，并让完整片条只把内容检测作为验证。当前 V3.9 主脚本仍保留 `--analysis` 控制的保守增强分隔辅助。 |
| V3.3.2 | 开发版 | 加入更保守的 overlap-like gap 标记，疑似叠片/连续内容的模型 gap 不再作为强 same-frame-size 锚点。 |
| V3.3.1 | 稳定 Release / V3.6 输出基线 | 保留 V3 系列较稳定的 outer/gap/candidate 主链路；bleed 只在最终输出、报告和 Debug Analysis 中应用，不参与检测评分；打包为可下载稳定版。 |
| V3.3 | 开发版 | 将检测用 bleed 与输出用 bleed 分离，默认输出 bleed 为长轴 20px、短轴 10px。 |
| V3.2 | 开发版 | 回到 V3 风格的主检测链路，同时保留明显弱证据图进入复核的安全闸门。 |
| V3.1.x | 实验版 | 尝试更积极的外框/分隔修正、局部救援和外扩策略；部分场景有帮助，但可能影响稳定样片，因此没有作为稳定发布。 |
| V3.0 | 基线版 | 建立 X5 Crop 主脚本、格式选择、固定张数 full strip、partial 模式、Debug Analysis 和高置信自动裁切 / 低置信复核的基本框架。 |

### 下载和文件摆放

普通使用推荐从 GitHub Releases 下载最新的稳定版压缩包。Release 是面向用户的稳定更新；仓库里的 `main` 分支可能包含正在验证中的开发进度，适合参与测试或查看最新改动。

Release 压缩包封装单文件版入口脚本、两个主启动器、README、快速启动文档和安装器：

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

Release 里的 `X5_Crop.py` 是从 V4 模块化源码自动生成的单文件发布版，已经内置 `x5crop/` 的内部代码。普通用户不需要复制 `x5crop/` 文件夹。

如果你不是下载 Release，而是直接从仓库 `main` 分支运行开发源码，那么根目录 `X5_Crop.py` 是开发入口，仍然需要旁边的 `x5crop/` 包。这是给开发和测试用的结构，不是普通 Release 用户需要复制的结构。

对应系统的主启动器是：

```text
macOS 主启动器: X5_Crop_Mac.command
Windows 主启动器: X5_Crop_win.bat
```

`install/` 里的安装启动器用于第一次安装依赖；卸载启动器用于清理用户级 Python 依赖。它们都不是日常裁切用的主启动器。

把 Release 里的 `X5_Crop.py`、对应系统的主启动器和要裁切的 TIFF 长图放在同一个文件夹里，然后双击主启动器运行。

不支持“只把启动器放进 TIFF 文件夹、脚本留在别处”的模式。

### 第一次安装依赖

如果新机器缺少依赖，先运行 Release 包里 `install/` 文件夹内的安装器，或者手动安装 Python 依赖。

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
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 35 --bleed-y 10
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

### Why This Is Not Packaged As An App

X5 Crop currently stays as a script plus launchers instead of a traditional app
package so it can stay lightweight, portable, and clean:

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
current user's Python has the required dependencies. This keeps X5 Crop closer
to a clean movable toolkit than a fixed-location app install.

Current default behavior:

- Detection uses no bleed when scoring outer boxes, gaps, confidence, or
  PASS/REVIEW.
- Output bleed defaults to 35px on the long axis and 10px on the short axis.
- Horizontal strips use 35px left/right and 10px top/bottom. Vertical strips are
  rotated accordingly.
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
- In 135 full-strip mode, a strong overlap-risk model gap sends the scan to
  REVIEW instead of automatic export.

### Changelog

Releases are stable packages for normal use. The `main` branch may contain
development versions that are still being validated.

For the more detailed local development record, see `CHANGELOG.md`.

| Version | Status | Detection / Workflow Changes |
|---|---|---|
| V4.0 | Stable Release / Current active development | Bold modular rewrite: root `X5_Crop.py` is only a thin entry point, and real responsibilities now live in the `x5crop/` package. `common.py` owns models, config, and helpers; `evidence.py` owns gray/evidence images; `io.py` owns TIFF read/write and metadata; `geometry.py` owns outer boxes, separators, edge-pair, grid, and frame fitting; `detection/pipeline.py` owns the detection and scoring pipeline; `deskew.py` owns leveling; `debug/render.py` owns Debug Analysis; `reports.py` owns report reuse and crop export; `cli.py` owns command-line, parallel, and per-file orchestration; `core.py` remains only as a compatibility export surface. It also adds a standalone release-script builder, so Release users still need only `X5_Crop.py` plus the platform launcher. This is not a conservative wrapper swap: it is a full structural rewrite that preserves old results. A full 135 default-deskew dry run compared with V3.9 had 0 diffs for `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. OpenCV / scipy-style heavy backends are deferred to a future V5 direction. |
| V3.9 | Development | Structural cleanup: moves the remaining outer mask profiles, post-detection confidence caps, deskew span skip, frame-fit small-pixel tolerances, separator gate mode, and outer retry switch into policy / format-aware configuration. The goal is to keep percentage + clamp parameters, format-specific branches, and future cross-format promotion points centralized. A full 135 default-deskew dry run compared with V3.7 had 0 diffs for `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. |
| V3.7 | Development | Merges the frame-size fit pipeline: cuts-level fitting is now the geometry fallback, box-level same-frame fitting is now edge-evidence fit, and a single entry point chooses the layer. Later cleanups also move high-level scoring weights, content-evidence thresholds, diagnostic semantics, and Debug display parameters into format-aware policy. The goal is clearer detection structure after format-aware `edge-pair` expansion while preserving existing PASS/REVIEW and output boxes. |
| V3.6.12 | Development | Tunes format-aware `edge-pair` with full `Test/120` and half-frame dry runs: 120-66 / 120-67 now accept wider, lower-background 120 separator evidence while content/aspect REVIEW gates remain conservative; half-frame parameters are unchanged. |
| V3.6.11 | Development | Extends `edge-pair` from 135-only to format-aware full-strip logic: 135 keeps its original parameters, while other formats use more conservative search windows, gutter widths, and quality thresholds. |
| V3.6.10 | Development | Cleans low-risk V3.6.9 leftovers: removes the unused `grid_protection_trust()` wrapper, fixes CLI version text, bleed defaults, `--analysis` help, and stale diagnostic wording. Detection flow is unchanged. |
| V3.6.9 | Development | Unifies active grid protection with lightweight diagnostic hard-gap trust: before grid can protect a red gap, it can now detect nearby conflicts, geometry conflicts, and suspected internal edge / frame border cases. |
| V3.6.8 | Development | Replaces V3.6.7's exact single-anchor gate with `lucky_pass_risk_score`: weak global evidence, suspicious hard gaps, overlap model gaps, and geometry stability are scored together; only scores above the threshold go to REVIEW. |
| V3.6.7 | Development | Promotes nearby stronger separator checks into a narrow correction: a red separator is moved only when the nearby candidate is clearly stronger, geometry improves, and confidence is not increased. It also sends `X5_00041`-like single-anchor lucky PASS shapes to REVIEW. |
| V3.6.6 | Development | Adds hard-gap trust diagnostics, nearby stronger separator checks, and prevents weaker grid fits from overriding `strong_separator` gaps. This is for observing and protecting reliable red separators. |
| V3.6.5 | Development | Raises the diagnostics-run worker cap to 4 while normal runs still cap at 2. This mainly supports the local diagnostics launcher and does not change detection logic. |
| V3.6.4 | Development | Returns to the V3.6.2 detection baseline. Adds a narrow long-axis white-edge outer correction: only when both end hard separators are reliable, the content box is complete, and one edge is nearly all white can the outer box be pulled inward near the content edge. |
| V3.6.3 | Paused / reference direction | Tried treating overlap / near-overlap as difficult: in 135 full-strip mode, strong overlap risk on a model gap forced REVIEW instead of automatic export. This direction is paused while future work starts from narrower diagnostics and corrections. |
| V3.6.2 | Previous Stable Release | First cleanup step after diagnostic stabilization: folds `equal-broad-region` into ordinary `equal`, and shrinks `hard_fallback_detection` to a review-only equal split fallback to reduce low-value methods and report noise. Overlap, near-overlap, and locally irregular spacing can still be misdetected, so use Debug Analysis for manual review on difficult scans. |
| V3.6.1 | Development | Continues the diagnostic layer: diagnostic report fields and diagnostic ticks are generated only with explicit `--diagnostics`; normal launchers do not enable diagnostics. Adds finer overlap-risk levels while still not changing output boxes, confidence, or PASS/REVIEW. |
| V3.6 | Development | Diagnostic cleanup from the V3.3.1 output baseline: adds read-only `diagnostics_v3_6`, hard-gap trust diagnostics, and overlap/continuous-content diagnostics. It does not change V3.3.1 `status`, `outer_box`, `frame_boxes`, or confidence. |
| V3.5 | Paused / rolled-back development attempt | Tried lightweight semantic validation for red hard separators. Testing affected previously accurate scans, so it is not active as a V3.6 correction rule. |
| V3.4.2 | Paused / rolled-back development attempt | Tried conservative local grid segments. Testing affected previously accurate scans, so it is not active as a V3.6 correction rule. |
| V3.4.1 | Paused / reference direction | Tried keeping strong hard separators authoritative when they conflict with robust grid. The direction remains useful, but the active baseline is back to V3.3.1. |
| V3.4 | Development | Experimental simplification direction: tried removing the enhanced separator layer, folding broad-region fallback into ordinary equal gaps, and using content detection only as validation for full strips. The current V3.9 script still keeps the conservative `--analysis` enhanced separator assist. |
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

The Release zip contains the standalone entry script, the two main launchers,
README, the quick-start guide, and installer launchers:

```text
X5_Crop.py
X5_Crop_Mac.command
X5_Crop_win.bat
README.md
快速启动_Quick_Start.md
install/
  X5_Crop_Mac_install.command
  X5_Crop_win_install.bat
  X5_Crop_Mac_uninstall.command
  X5_Crop_win_uninstall.bat
```

The Release `X5_Crop.py` is generated from the modular V4 source tree as a
standalone file. It embeds the internal `x5crop/` code, so normal users do not
need to copy an `x5crop/` folder.

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
python3 X5_Crop.py . --format 135 --strip full --report --bleed-x 35 --bleed-y 10
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

### License

This project is open source under the MIT License. See `LICENSE`.
