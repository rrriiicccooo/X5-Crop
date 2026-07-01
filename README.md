# X5 Crop

> **下载提示 / Download Notice**
>
> 普通用户请从 GitHub **Releases** 下载整理好的 `X5-Crop-vX.X.zip`。不要点击 GitHub 仓库页面里的 **Code > Download ZIP**，也不要下载自动生成的 **Source code** 压缩包；那些是开发源码结构，不是面向使用者整理好的发布包。
>
> Regular users should download the prepared `X5-Crop-vX.X.zip` from GitHub **Releases**. Do not use **Code > Download ZIP** on the repository page, and do not download GitHub's auto-generated **Source code** archives; those are development source trees, not user-ready release packages.

X5 Crop 是一个用于 Hasselblad / Imacon X5 胶片片夹长图的 TIFF 自动裁切工具。它会把同一文件夹里的长条 TIFF 扫描图拆分成单张 TIFF；只有高置信结果会自动导出，低置信或困难图片会进入复核。

当前 active 脚本版本：V4.7

当前稳定发布版本：v4.2.8（GitHub Releases）

脚本不会修改原始 TIFF。自动裁切会生成新文件；进入 `needs_review/` 的文件也是原 TIFF 的复制粘贴，方便人工处理。自动裁切输出的 TIFF 会保留原 TIFF 的画质相关属性，包括但不限于位深、通道结构、ICC / 色彩空间、resolution 和 metadata；脚本不会为了裁切而主动降位深、改色、压缩或重采样图像数据。

文档分工：

- `快速启动_Quick_Start.md`：最短上手步骤，适合第一次使用或给他人转交工具。Release 包内对应文件名为 `快速启动_Quick_Start.txt`。
- `README.md`：完整用户手册，说明安装、文件摆放、启动器、Debug Analysis、输出目录和命令行参数。Release 包内对应文件名为 `README.txt`。
- `CHANGELOG.md`：开发记录和版本差异，保留在 GitHub 仓库中，适合排查行为变化、回滚或继续调检测逻辑。
- `ARCHITECTURE.md`：开发者架构地图，说明源码层级、policy 归属、format / mode 隔离规则和回归验证边界。`docs/ARCHITECTURE.md` 保留同内容镜像。

仓库 `main` 分支是开发进度，可能比 Release 新，但不一定是稳定发布版。普通使用以 GitHub Release 为准。

## 中文指南

### 这个工具做什么

X5 Crop 会处理同一个文件夹里的 `.tif` / `.tiff` 长图，并把高置信结果自动裁切成单张 TIFF。低置信结果不会自动裁切；脚本会写入报告，并在需要时把原 TIFF 复制到 `needs_review/`，方便人工复核。

核心原则：

- 只有高置信检测结果才自动导出。
- 不为了让困难图片通过而放宽置信规则。
- 困难样片进入复核，避免靠猜测自动裁切。
- 自动裁切输出 TIFF 会保留原 TIFF 的画质相关属性，包括但不限于位深、通道结构、ICC / 色彩空间、resolution 和 metadata。

脚本会在你指定的胶片格式和片条模式内，综合外框、分隔、内容和画幅几何证据评分。最终只有高置信结果会自动导出；证据不足、证据互相冲突或画幅状态异常时会进入复核。V4.7 保留每个 format / strip mode 的明确 detection policy，例如 `135_full`、`120_66_partial`。检测流程会通过当前 policy 决定 count planning、outer proposal、separator/content gate、candidate selection 和 postprocess 开关。报告会写出当前 policy id、outer 候选来源、analysis source、auto gate、gap 证据和 review reasons；Debug Analysis 保持三栏图面，只显示原图灰度、裁切框和分隔证据，方便更快读图。V4.7 以 V4.5.4 输出为 golden baseline，不主动放宽 PASS 规则；120-66 的宽黑条逻辑仍只作用于 120-66 的物理特征。

### 为什么不是 App 封装

X5 Crop 目前保持为脚本 + 启动器，而不是做成传统 App。这个选择主要服务三个目标：轻量、可移动、易清理。

- 不需要系统级 App 安装，也就不会留下应用支持目录、偏好设置、后台服务或卸载残留。
- 删除项目文件夹就能移除脚本本体、启动器和这个文件夹里的输出。
- Python 依赖是用户级依赖，可以用卸载启动器清理；不需要卸载一个 App 再去找散落的残留文件。
- 可以多开：把 Release 里的 `X5_Crop.py` 和对应系统主启动器复制到不同 TIFF 文件夹，就可以同时处理多个文件夹的图片。

代价是第一次使用需要先运行安装启动器，让当前用户的 Python 拥有必要依赖。整体上，它更像一个干净、可移动的工具箱，而不是固定安装在系统里的 App。

### 当前默认行为

- 自动裁切输出 TIFF 以原图数据为基础写出，不会为了裁切而主动降位深、改色、压缩或重采样。脚本会保留原 TIFF 的位深、通道结构、ICC / 色彩空间、resolution 和 metadata 等画质相关属性。
- 检测阶段不使用 bleed；bleed 只在最终输出和 Debug Analysis 色块里应用。
- 默认输出 bleed 为长轴 20px、短轴 10px。横向长图是左右各 20px、上下各 10px；竖向长图会自动对应旋转。
- 如果检测到叠片 / 近似叠片 / 连续内容风险，输出长轴 bleed 会自动提高到 50px，给这类困难图更多安全余量。V4.4.3 起，这个输出安全边距也会参考 partial、half 和 120 路径里的诊断叠片风险。这个调整只影响最终输出和 Debug Analysis 色块，不参与检测评分。
- 对已经 `approved_auto` 且没有复核原因的结果，会做一个很小的输出几何调整：只允许长轴最多向外微扩。这一步不改变 PASS/REVIEW 和置信度。
- `--analysis` 仍保留一个很保守的增强分隔辅助层：`auto` 只在分隔证据偏弱时尝试，`always` 每次尝试，`off` 关闭。它和 deskew 的增强角度候选共用同一个参数入口。
- 对近似叠片、片距局部不稳定、分隔证据不足或内容证据冲突的长图，会保持保守判断，不会为了自动导出而放宽置信规则。

### V4.7 开发结构

V4.7 把开发源码整理成干净的按职责分层结构：`app.py` / `config.py` / `formats.py` 负责应用入口、运行配置和格式定义；`workflow.py` 负责 read -> deskew -> detect -> postprocess -> export -> report/debug 的单文件和批处理编排；`io/`、`image/`、`geometry/`、`detection/`、`diagnostics/`、`export/` 和 `regression/` 分别负责 TIFF I/O、灰度/证据图、几何、检测、诊断图、导出和回归比较；`policies/` 按格式和 full / partial 模式注册 `DetectionPolicy`。

当前 runtime 已经通过 policy 驱动 detector kind、count planning、outer strategy、separator gate、candidate-run behavior、partial-holder safety、candidate selection、postprocess 和 diagnostics panel/title policy；旧 `common.py`、`policy.py`、`core.py` 和根级 `io.py` / `geometry.py` / `regression.py` 兼容层已移除。`policies/parameters.py` 现在只是薄 lookup，具体 format 参数在 `policies/presets/`；policy 构建层通过 separator gate、leading-grid separator failure、separator geometry support、gap search、hard-gap trust、nearby separator correction、robust grid、outer strategy、short-axis aspect retry、partial holder、scoring calibration、candidate competition、content evidence、debug gap overlay、nearby separator diagnostics、overlap-risk diagnostics、lucky-pass risk 和 postprocess 等能力分组读取参数，candidate calibration、wide-retry、content-evidence runtime、Debug Analysis gap overlay、nearby separator diagnostics、overlap-risk diagnostics、gap search、hard-gap trust、nearby separator correction、robust grid、short-axis aspect retry、lucky-pass risk diagnostics 和 postprocess final caps 也从 `ScoringPolicy` / `wide_retry` / `content_evidence` / `DiagnosticsPolicy.debug_gap_overlay` / `DiagnosticsPolicy.nearby_separator` / `DiagnosticsPolicy.overlap_bleed_risk` / `SeparatorPolicy.gap_search` / `SeparatorPolicy.hard_gap_trust` / `SeparatorPolicy.nearby_correction` / `SeparatorPolicy.robust_grid` / `OuterPolicy.short_axis_aspect_retry` / `DiagnosticsPolicy.lucky_pass_risk` / `PostprocessPolicy` 分组读取 caps、weights、retry width、内容证据阈值、诊断叠加线条参数、nearby 搜索阈值、gap 搜索半径/宽度/guard/score、wide separator 接受阈值、nearby correction 阈值、robust-grid 阈值、short-axis aspect retry 误差/目标比例/边距、overlap 风险阈值、trust 阈值、风险评分权重和最终 REVIEW cap；separator-derived outer 候选的 gap-search 宽度覆盖值由 `OuterPolicy.separator_gap_search_max_width_ratio` 描述；separator hard-evidence gate 的 leading-grid failure 也由 `SeparatorGatePolicy` 描述，底层检测/几何仍可逐步迁出剩余平面字段。`policies/registry.py` 只负责 resolve/cache policy，具体 format/mode preset 由对应 `format_*.py` 拥有。`detection/pipeline.py` 只保留主编排，候选构建、候选运行、候选校准、fallback、cache key、partial hint 等职责已拆到 `candidate_build.py`、`candidate_run.py` 等专门模块。候选类型由 `OuterCandidate.strategy` 显式记录，不再靠候选名称前缀推断；content 跳过、fallback outer proposal、partial safe-auto 停止规则和 conditional separator-geometry 候选竞争阈值由 `CandidateRunPolicy` / `FallbackPolicy` / `PartialStopPolicy` / `separator_geometry_competition` 描述。`geometry/core.py` 也缩到 separator/cache-heavy 核心，通用 box、layout、outer box、gap/grid、separator profile、frame fit 和 output adjustment 已拆成独立模块。报告中的 `report_schema` 带 schema version，并按固定结构写出 result、candidate、policy、evidence、gates、postprocess 和 output，方便按格式调试。开发者可用 `python3 -m x5crop.regression.golden --candidate-root <candidate-root>` 对候选报告和本地 V4.5.4 golden reports 做统一比较。

`OuterPolicy.content_alignment` 现在接管 outer/content alignment 的 slack、white-edge 判断、mismatch gate 和 content-aligned retry margin；`outer_retry.py` 和 `postprocess.py` 不再直接读取平面 `outer_align_*` preset 字段。
`ScoringPolicy` 现在接管候选 calibration weights、separator source bias、hard-full confidence floor 和 no-auto caps；`calibration.py` / `scoring.py` 不再直接读取 flat `scoring_calibration`。
`ScoringPolicy.base_detection` 现在接管 `score_detection()` 的 gap / width / outer / contrast 权重、full-geometry floor、partial caps、outer-too-large cap、低置信阈值和分隔证据不足 reason id；`score_detection()` 不再直接读取 flat `score_*` 字段，也不再保留旧 `120_separator_uncertain` 这类 format 前缀 reason 名称。
`ContentPolicy` 现在接管 candidate calibration 中 content-support score 的 norm、weight 和 support gate；`content_support_score()` 不再直接读取 flat `content_support_*` 字段。
`ContentPolicy.evidence` / `profile` / `mask` / `candidate` 现在接管 content evidence 阈值、content-run profile、content mask outer 和 content-only candidate confidence cap；`detection/content.py` 不再直接读取 flat `content_*` preset 字段或 runtime `FormatParameters`。
`FormatParameters.content_evidence` / `content_profile` / `content_mask` / `content_candidate` / `content_support` 现在是 policy factory 构建 `ContentPolicy` 的 preset-side 能力视图；factory 不再直接读取对应平面 `content_*` 字段。
`ScoringPolicy.geometry_support` 现在接管 candidate calibration 中 geometry-support score 的 width、outer、aspect、count norm / weight 和 outer-area bounds；`geometry_support_score()` 不再直接读取 flat `geometry_support_*` / `geometry_width_cv_norm` / `content_support_aspect_norm` 字段。
`FormatParameters.geometry_support_score` 现在是 policy factory 构建 `ScoringPolicy.geometry_support` 的 preset-side 能力视图；factory 不再直接读取 geometry-support 相关平面 score 字段。
`ScoringPolicy.separator_support` 现在接管 candidate calibration 中 separator-support score 的 hard/model 权重、grid/equal credit 和 single-frame cap；`separator_support_score()` 不再直接读取 flat `separator_model_*` / `separator_support_*` 字段。
`OuterPolicy.base_candidates` 现在接管 base outer candidate 的 bw / white-x / mask-profile 搜索阈值、margin 和候选面积限制；`geometry/outer_boxes.py` 不再直接读取 flat `outer_*` preset 字段或按 format 名查参数。
`OuterPolicy.separator_outer_band` 和 `separator_geometry_outer` 现在接管 separator-first / separator-geometry outer proposer 的 band、sequence、source、margin 和候选数量参数；`detection/outer.py` 不再直接读取 flat `separator_first_outer_*` / `separator_geometry_outer_*` 字段。
`FormatParameters.content_floating_outer` / `edge_anchor_outer` / `base_outer_candidates` / `separator_outer_band` / `separator_geometry_outer` 现在是 policy factory 构建 outer proposal policy 的 preset-side 能力视图；factory 不再直接读取这些 outer proposal 平面字段。
`SeparatorPolicy.profile` / `edge_refine_profile` 现在接管 separator profile 和 edge-refine profile 的生成阈值、平滑窗口、权重和背景阈值；policy factory 通过 `FormatParameters.separator_profile` / `edge_refine_profile` 能力分组读取这些参数，`geometry/separator_profile.py` 不再直接读取 flat `separator_profile_*` / `edge_refine_*` preset 字段，检测路径和 diagnostics nearby separator 复查都会显式传入当前 policy，profile / edge-refine 缓存也按当前 policy 分桶。
`SeparatorPolicy.enhanced` 现在接管 enhanced separator 辅助层的触发低分阈值、接受分数、宽度和位移限制；`geometry/core.py` 不再直接读取 flat `enhanced_*` preset 字段。
`SeparatorPolicy.wide_separator_confidence_cap` 现在接管包含 wide separator gap 的候选 confidence cap；`calibration.py` 不再直接读取 flat wide-retry confidence-cap 参数。
`PartialHolderPolicy` 现在接管 66 partial strict holder 的 safe-extra-frames strip-mode scope、frame mean / coverage / aspect-error 检查；`partial_holder.py` 不再直接读取 `policy.parameters.content_evidence`。
`PartialEdgeHintPolicy` 现在接管 partial-strip edge hint 的 window ratio / min / max；`detection/partial.py` 和 `candidate_build.py` 不再直接读取平面 `partial_edge_hint_*` preset 字段。
`OuterPolicy.format_geometry_retry` 现在接管 format-geometry outer retry 的启用开关、比例容差、收缩限制和 content margin；`outer_retry.py` 不再直接读取平面 `format_geometry_outer_retry_*` preset 字段。
`OuterPolicy.grid_refine` 现在接管 full-strip grid-based outer refinement 的 shift 和 width-change 限制；`candidate_build.py` 不再直接读取平面 `grid_outer_refine_*` preset 字段。
`PostprocessPolicy` 现在接管 postprocess 阶段的 outer-alignment disabled、likely partial、outer-candidate disagreement 和 deskew uncertainty reason id。
`PostprocessPolicy.approved_geometry_adjustment` 现在接管 approved-auto 输出几何微扩的 long-axis limit 和 minimum extension；`geometry/output_adjustment.py` 不再直接读取平面 `approved_adjust_*` preset 字段。
`OutputPolicy.overlap_risk_long_axis_bleed` 现在接管 overlap-risk 时输出阶段长轴 bleed 提升值；`postprocess.py` 和缓存复用 workflow 不再硬编码 50px。
`OutputPolicy.edge_bleed_protection` 现在接管 full-strip 输出 edge guard 的 ratio / min / max；`geometry/output_adjustment.py` 不再保留硬编码 edge guard。
`OutputPolicy.detection_long_axis_bleed` / `detection_short_axis_bleed` 现在接管检测阶段 bleed 配置；默认仍为 0/0，`detection_geometry_config()` 不再硬编码 0/0。
`OuterPolicy.content_floating_outer` / `edge_anchor_outer` 现在接管 content-floating 和 long-axis edge-anchor outer proposal 的 threshold、margin、ratio extra 和候选数量；`detection/outer.py` 不再直接读取平面 `floating_outer_*` / `long_axis_edge_anchor_*` preset 字段。
`ReportPolicy` 现在接管 report schema version 和 section order；`report_schema_for_detection()` 会通过当前 format / strip mode policy 生成报告 schema。
`DiagnosticsPolicy.debug_gap_overlay` 现在接管 Debug Analysis separator-panel 的 gap overlay 容差、tick 长度和线宽；`debug/render.py` 不再保留硬编码 gap tick 长度。
`DiagnosticsPolicy.debug_panels` / `debug_panel_titles` 现在接管 Debug Analysis 的三栏顺序和标题；渲染层只支持 `Original gray`、`Debug boxes`、`Separator evidence` 这三个当前面板。
`CandidateRunPolicy.content_candidate` 现在接管 content candidate 是否运行、separator auto 后跳过 content 的 strip-mode 集合和 report reason；默认仍只让 full mode 在 separator auto 通过后跳过 content。`PartialStopPolicy` 接管 partial safe-auto 后跳过 content 的 strip-mode 集合和 reason，默认仍只给 partial mode。
`CandidateRunPolicy.separator_geometry_competition` 现在接管 separator-geometry candidate competition 的 content-outer strategy scope、strip-mode scope 和 median-aspect 阈值；默认仍只让 `content_outer` + `partial` 走 content-outer max-aspect cap。
`CandidateRunPolicy.equal_first_before_wide_retry` 现在接管 equal-first wide-retry 的启用、wide-geometry 依赖、strip-mode scope 和 default-count 要求；默认 scope 仍只允许 full/default-count，实际触发还必须由对应 format/mode 启用 wide geometry support。
`ModePolicyPreset.dark_band` 现在把 dark-band mode、full-selection 和 oversized separator-band 开关收成一个能力包；`CandidateRunPolicy.dark_band_retry` 接管 full / partial dark-band retry 的 strip-mode scope、full default-count 要求和 partial retry 触发条件；`DarkBandOuterPolicy` 接管 dark-band full-selection 的 strip-mode scope 和 required-count 要求。接口是通用的，但实际运行仍必须由 `OuterPolicy.dark_band` 开启，目前只给 `120-66` full / partial。
`SelectionPolicy.content_mismatch_review` 现在接管 content-count mismatch 时优先展示 separator review 候选的条件、strip-mode scope 和 default-count 要求；接口是通用的，默认关闭，目前只由 `half_full` 开启。
底层 deskew、gap、separator profile cache、content profile 和 diagnostics helper 的 `format_name` 现在必须由调用方显式传入，不再用 `"135"` 作为隐式默认值。

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

X5 Crop 没有传统 App 安装过程。想移除脚本本体时，直接删除 X5 Crop 文件夹即可。删除前如果要保留裁切结果，请先把 `x5_crop_output/` 移到其它位置。

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
count:
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

如果输错格式，启动器会重新让你输入。`partial mode` 和 `debug analysis` 可以输入 `yes` / `no` / `y` / `n`，直接回车等于 `no`。只有开启 partial mode 后，启动器才会继续询问 `count`；直接回车或输入 `auto` 等于自动判断张数，也可以输入当前 format 允许的具体张数。

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

partial mode 的意思是“这可能不是一条完整片条，可以让脚本估计张数，或者由你指定局部片条张数”。它适合：

- 片头或片尾。
- 只扫到几张的局部片条。
- 120 片夹里没有铺满整条的情况。
- 你不确定应该有几张照片的情况。

不开启 partial 时，脚本会使用上表里的固定张数，速度更快，判断也更稳定。完整片条请优先保持 `partial mode = no`。开启 partial 时，启动器会继续询问 count：直接回车或输入 `auto` 代表自动判断；输入具体数字则固定局部张数。

partial mode 的自动通过逻辑更强调“不要裁坏真实照片”。如果真实照片被稳定覆盖、画幅几何正常、内容证据正常，并且至少有一定分隔 / 边缘证据支撑，脚本可以接受多切出少量空片夹区域。这类额外 frame 删除成本很低，因此不必因为 count 可能多估而一律进入复核。相反，如果只是 content-only 候选、内容或几何证据冲突，或者切线明显缺少支撑，仍会进入 `needs_review/`。

从 V4.4 开始，full 和 partial 的物理语义更清楚：`full` 用于完整铺满片夹的片条；`partial` 用于片头、片尾、局部片条，或有效照片区域没有铺满片夹、在长图里不居中、靠近一端开始的情况。对 `120-66` 和 `xpan` 这类正常张数也是 3 张的格式，如果三张照片没有铺满片夹，建议开启 partial mode；如果你确定就是 3 张，可以在 partial count 里输入 `3`，或者让支持该格式的 auto count 自行判断。

`135-dual` 目前只建议用于完整双条 135，partial 下会倾向复核。

### Debug Analysis

如果开启 Debug Analysis，脚本只生成分析 JPG 和报告，不输出裁切 TIFF。输出位置：

```text
x5_crop_output/_debug_analysis/
```

这里的 `dry run` 是“试运行 / 分析模式”：脚本会读取 TIFF、执行检测、计算 PASS/REVIEW、生成 Debug Analysis JPG 和报告，但不会正式导出裁切后的单张 TIFF。它也不会修改原 TIFF。适合在正式裁切前检查外框、分隔线、裁切范围和置信度。

每张 Debug Analysis JPG 现在包含三个面板：

- `Original gray`：原始灰度图。
- `Debug boxes`：外框和最终输出裁切范围。
- `Separator evidence`：整张扫描的分隔证据，并叠加当前 outer 和分隔标记。

横向长图会把面板上下排列；竖向长图会横向排列，方便最大化利用屏幕空间。

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
x5_crop_output/
```

常见内容：

```text
x5_crop_output/
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
- `_debug_analysis/*_debug_analysis.jpg`：Debug Analysis 分析图。
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

Current active script version: V4.7

Current stable release: v4.2.8 (GitHub Releases)

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
- `ARCHITECTURE.md`: developer architecture map for source layers, policy
  ownership, format / mode isolation, and regression boundaries.
  `docs/ARCHITECTURE.md` keeps the same mirrored content.

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
V4.7 keeps an explicit detection policy for every format / strip-mode pair,
such as `135_full` or `120_66_partial`. The detector reads that policy for count
planning, outer proposals, separator/content gates, candidate selection, and
postprocess switches. Reports include the policy id, outer-candidate strategy,
analysis source, auto gate, gap evidence, and review reasons; Debug Analysis
keeps a compact three-panel image with original gray, crop boxes, and separator
evidence. V4.7 uses V4.5.4 output as its golden baseline and does not
intentionally loosen PASS rules; the 120-66 wide-dark-separator behavior remains
format-specific.

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

### Current Default Behavior

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
  output bleed is automatically raised to 50px for extra safety. Starting with
  V4.4.3, this output safety margin also uses diagnostic overlap-risk signals
  from partial, half-frame, and 120-format paths. This affects final output and
  Debug Analysis crop blocks only, not detection scoring.
- A small PASS-only geometry adjustment may slightly expand long-axis output edges.
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

### V4.7 Development Structure

V4.7 organizes the development source by responsibility: `app.py`,
`config.py`, and `formats.py` cover orchestration, runtime configuration, and
format definitions; `io/`, `image/`, `geometry/`, `detection/`,
`diagnostics/`, `export/`, and `regression/` cover TIFF I/O, grayscale/evidence
images, geometry, detection, diagnostic images, export, and report comparison;
and `policies/` registers each format plus full / partial mode as a
`DetectionPolicy`. The current runtime uses policy for count planning, outer
strategy, separator gates, candidate-run behavior, partial-safe gates,
candidate selection, and postprocess policy. Explicit outer-candidate strategy
metadata drives candidate behavior instead of candidate-name prefixes. Format
parameters live in `policies/presets/`. Policy construction reads those
parameters through capability groups such as separator gate, separator geometry
support, gap search, outer strategy, short-axis aspect retry, partial holder,
scoring calibration, candidate competition, content evidence, debug gap
overlay, diagnostics panel titles, and postprocess.
Candidate calibration, wide-retry, content-evidence runtime, Debug Analysis gap
overlay, gap search, short-axis aspect retry, and postprocess final caps now
read their caps, weights, retry width, content thresholds, overlay line
settings including tick length, separator search radius/width/guard/score, wide separator acceptance
thresholds, short-axis aspect retry error/aspect/margins, and final REVIEW caps
from
`ScoringPolicy` / `wide_retry` / `content_evidence` /
`DiagnosticsPolicy.debug_gap_overlay` / `DiagnosticsPolicy.debug_panels` /
`DiagnosticsPolicy.debug_panel_titles` / `SeparatorPolicy.gap_search` /
`OuterPolicy.short_axis_aspect_retry` / `PostprocessPolicy`; lower-level
detection and geometry helpers can continue migrating off the remaining flat
fields incrementally.
Base outer candidates use `OuterPolicy.base_candidates` for bw / white-x /
mask-profile thresholds, margins, and candidate area limits; `geometry/outer_boxes.py`
no longer reads flat `outer_*` preset fields or resolves parameters by format name.
Separator-derived outer candidates use
`OuterPolicy.separator_gap_search_max_width_ratio` for their gap-search width
override, so candidate runtime does not read the old flat separator-first outer
gap field directly.
Separator-derived outer proposers use `OuterPolicy.separator_outer_band` and
`separator_geometry_outer` for band thresholds, sequence limits, source counts,
margin ratios, and candidate limits; `detection/outer.py` no longer reads flat
`separator_first_outer_*` or `separator_geometry_outer_*` preset fields directly.
Separator profile and edge-refine profile generation use
`SeparatorPolicy.profile` / `edge_refine_profile`, including thresholds, smooth
windows, weights, and background thresholds; `geometry/separator_profile.py` no
longer reads flat `separator_profile_*` / `edge_refine_*` preset fields, and the
policy factory reads them through `FormatParameters.separator_profile` /
`edge_refine_profile` capability views. The detection path plus diagnostics
nearby-separator checks pass the selected policy explicitly. Profile and
edge-refine caches are keyed by the selected policy.
Enhanced separator analysis uses `SeparatorPolicy.enhanced` for its low-score
trigger, accepted score, width, and shift limits; `geometry/core.py` no longer
reads flat `enhanced_*` preset fields directly.
Short-axis aspect retry uses `OuterPolicy.short_axis_aspect_retry`; it remains
off by default and is currently active only for 120-66 full, matching the
runtime's full-strip-only correction path.
Outer/content alignment uses `OuterPolicy.content_alignment`, including
white-edge slack detection, mismatch gates, and content-aligned retry margins.
Candidate calibration weights, separator source bias, hard-full confidence
floor, and no-auto caps use `ScoringPolicy`.
Base detector scoring weights, full-geometry floors, partial caps,
outer-too-large caps, and the separator-incomplete reason id use
`ScoringPolicy.base_detection`; active runtime no longer emits the old
format-prefixed `120_separator_uncertain` reason name.
Content-support score norms, weights, and support gates use `ContentPolicy`.
Content evidence thresholds, content-run profile, content mask outer, and
content-only candidate confidence caps use `ContentPolicy.evidence`, `profile`,
`mask`, and `candidate`; `detection/content.py` no longer reads flat
`content_*` preset fields or runtime `FormatParameters`.
Geometry-support score width/outer/aspect/count norms, weights, and outer-area
bounds use `ScoringPolicy.geometry_support`.
Separator-support hard/model weights and grid/equal credit use
`ScoringPolicy.separator_support`.
Partial-holder safe-extra-frames strip-mode scope, frame mean, coverage, and
aspect-error checks use `PartialHolderPolicy`.
Wide separator confidence caps use
`SeparatorPolicy.wide_separator_confidence_cap`, keeping calibration on the
selected policy surface.
Partial-strip edge hints use `PartialEdgeHintPolicy`, including the edge-window
ratio and clamp bounds.
Format-geometry outer retry uses `OuterPolicy.format_geometry_retry`, including
ratio tolerance, shrink limits, and content margins.
Full-strip grid-based outer refinement uses `OuterPolicy.grid_refine`, including
shift and width-change limits.
Postprocess review/detail reason ids for outer-alignment disabled, likely
partial, outer-candidate disagreement, and deskew uncertainty now use
`PostprocessPolicy`.
Approved-auto output geometry adjustment uses
`PostprocessPolicy.approved_geometry_adjustment`, including long-axis expansion
limits and minimum extension clamps.
Overlap-risk output bleed uses `OutputPolicy.overlap_risk_long_axis_bleed`,
including cached-report export reuse.
Full-strip output edge protection uses `OutputPolicy.edge_bleed_protection`,
including edge-guard ratio and clamp bounds.
Detection-time bleed uses `OutputPolicy.detection_long_axis_bleed` and
`detection_short_axis_bleed`, keeping detection geometry explicitly policy-owned
with the default still at 0/0.
Content-floating and long-axis edge-anchor outer proposal thresholds now use
`OuterPolicy.content_floating_outer` and `edge_anchor_outer`, including content
thresholds, margins, ratio extras, and candidate limits.
Content candidate run and skip behavior now uses
`CandidateRunPolicy.content_candidate`; partial safe-auto content-skip mode and
reason are owned by `PartialStopPolicy`.
Separator-geometry candidate competition uses
`CandidateRunPolicy.separator_geometry_competition`; content-outer strategy
scope, strip-mode scope, and median-aspect caps are policy fields.
Equal-first wide-retry behavior uses
`CandidateRunPolicy.equal_first_before_wide_retry`; its wide-geometry dependency,
strip-mode scope, and default-count requirement are policy fields.
`ModePolicyPreset.dark_band` groups dark-band mode, full-selection, and
oversized separator-band enablement into one isolated capability preset.
Dark-band retry behavior uses `CandidateRunPolicy.dark_band_retry`, including
retry strip-mode scope and full default-count checks. Dark-band full-selection
scope and required-count checks are owned by `DarkBandOuterPolicy`.
Content-count mismatch review candidate preference now uses
`SelectionPolicy.content_mismatch_review`; its strip-mode scope and default-count
requirement are policy fields. The interface is general, but only `half_full`
enables it.
Low-level deskew, gap, separator profile cache, content profile, and diagnostics
helpers now require an explicit `format_name`; they no longer fall back to an
implicit `"135"` default.
`policies/registry.py` only resolves and caches the selected policy. The
detection pipeline now delegates candidate building, candidate running,
calibration, fallback detection, cache keys, partial hints, outer candidates,
content evidence, scoring, gates, and selection to focused modules. Geometry is
split into `boxes.py`, `layout.py`,
`outer_boxes.py`, `gaps.py`, `separator_profile.py`, `frame_fit.py`, and
`output_adjustment.py`, with `core.py` left for cache-heavy separator helpers.
The old `common.py`, `policy.py`, `core.py`, and root-level `io.py` /
`geometry.py` / `regression.py` compatibility layers are gone. Reports include a
stable `report_schema` with result, candidate, policy, evidence, gates,
postprocess, and output sections for format-specific debugging.

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
the X5 Crop folder. If you want to keep cropped output, move `x5_crop_output/`
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
count:
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
`debug analysis`, use `yes` / `no` / `y` / `n`; Return means `no`. The launcher
asks for `count` only after partial mode is enabled. Return or `auto` means
automatic count detection; you may also enter an allowed count for the selected
format.

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
the frame count or let me specify the partial count.” Use it for:

- Leader or tail scans.
- Partial strips with only a few frames.
- 120 holder scans that do not fill the whole holder.
- Cases where you are not sure how many frames should be present.

When partial mode is off, the script uses the fixed counts above. That is faster
and more stable for complete strips. Keep `partial mode = no` for normal full
strips. When partial mode is enabled, the launcher asks for count: Return or
`auto` means automatic count detection, while a number fixes the partial frame
count.

Partial mode is judged by a safer practical rule: do not damage real frames. If
the real frames are covered reliably, frame geometry is stable, content evidence
is normal, and there is at least some separator / edge evidence, the script may
accept a few extra empty holder frames instead of forcing review only because
the count may be slightly high. Those extra crops are easy to delete. If the
candidate is content-only, content or geometry conflicts, or the cut lines are
poorly supported, the file still goes to `needs_review/`.

Starting with V4.4, full and partial have clearer physical meanings. `full`
means a complete strip that fills the holder area; `partial` means leader, tail,
local strip, or a valid frame sequence that does not fill the holder, is not
centered, or starts near one long-axis end. For formats such as `120-66` and
`xpan`, where a normal scan may still contain three frames, use partial mode
when those three frames do not fill the holder. If you know the scan contains
three frames, enter `3` as the partial count, or use auto count where supported.

`135-dual` is currently recommended only for complete dual 135 strips; partial
dual-strip cases tend to be reviewed.

### Debug Analysis

Debug Analysis is a dry run. It writes analysis JPGs and reports, but no cropped
TIFFs.

In this project, `dry run` means “test/analyze only.” The script reads the TIFF,
runs detection, decides PASS/REVIEW, and can write Debug Analysis JPGs and
reports, but it does not export cropped frame TIFFs. It also does not modify the
original TIFF. Use it before real export to inspect the outer box, separators,
crop boxes, and confidence.

Each Debug Analysis JPG now has three panels:

- `Original gray`: original grayscale detection image.
- `Debug boxes`: outer box and final output crop boxes.
- `Separator evidence`: full-scan separator evidence with the current outer and
  separator marks overlaid.

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
x5_crop_output/
```

Common contents:

```text
x5_crop_output/
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
- `_debug_analysis/*_debug_analysis.jpg`: Debug Analysis images.
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
