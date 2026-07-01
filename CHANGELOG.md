# X5 Crop 更新日志 / Changelog

## 中文更新日志

这份更新日志用于记录 X5 Crop 的检测逻辑、工作流、回归验证和发布策略变化。它面向继续开发、行为排查、版本比较和必要时的回滚，不作为普通用户的快速使用说明。

如果只是使用脚本，请优先阅读 `快速启动_Quick_Start.md` 和 `README.md`。本文件保留更细的开发背景、实验结论和验证结果。

当前 active 脚本：`X5_Crop.py` V4.7

当前稳定 GitHub Release：`v4.2.8`

### 版本状态

| 版本 | 状态 | 摘要 |
|---|---|---|
| V4.7 | 当前 active 开发版 | Clean-room source rewrite：删除旧 `common.py`、`policy.py`、`core.py` 和根级 `io.py` / `geometry.py` / `regression.py` 兼容层，让 active source 只通过真实职责模块工作。format 参数拆入 `policies/presets/`，registry 只负责 policy resolve/cache；`pipeline.py` 收敛为 detection orchestration，候选构建/运行拆入 `candidate_build.py` / `candidate_run.py`；geometry 拆出 boxes/layout/outer_boxes/gaps/separator_profile/frame_fit/output_adjustment。`FrameFitPolicy`、separator edge-pair、gap search、separator-derived outer gap override、short-axis aspect retry 和 content evidence 参数由 policy / preset 分组拥有，runtime 只消费明确参数对象。七组 V4.5.4 golden core comparison 为 0 diff。 |
| V4.6 | 开发版 | Policy 化重构版：新增 `x5crop/policies/`，把每个 format / strip mode 的 detector、count、outer、separator、content、partial-holder、frame-fit、gate、scoring、selection、postprocess、output 和 diagnostics 策略注册成独立 `DetectionPolicy`；检测 runtime 已通过 policy 驱动 count planning、outer strategy、separator gate、partial-holder gate、candidate selection、postprocess 和 debug panel policy。`workflow.py` 现在承接 read -> deskew -> detect -> postprocess -> export -> report/debug 编排，CLI 回到薄入口。目标是以 V4.5.4 为 golden baseline，把 135、135-dual、half、xpan、120-645、120-66、120-67 的 full / partial 调试入口清晰拆开。 |
| V4.5.4 | 开发版 | 120-66 宽黑条检测改进：partial 的 safe-extra-frames gate 增加 wide-like separator、前缘内容和逐格内容稳定约束；full 在旧 outer 内容形态异常时可让 120-66 宽黑条 outer 候选接管。`Test/120/66` partial 和 full 均为 16 个 `approved_auto` / 0 个 `needs_review`。 |
| V4.5.3 | 开发版 | 半格 full gate 修复：修正候选 detail 读取 `width_cv=0.0` 时被 `or 1.0` 误判成缺失值的问题。`X5_00058.tif` 现在能按既有 `half_wide_geometry_support` 条件通过；135 full 和半格 partial 回归保持 0 diff。 |
| V4.5.2 | 开发版 | 结构收敛版：把只读诊断计算从 Debug 渲染层移入 detection 层，减少检测后处理对 Debug UI 的反向依赖；新增共享常量入口，集中 analysis source、gap method 和主要 review reason；让 `policy.py` 和 detection model 导出直接依赖 common / geometry，而不是绕回 core 兼容层；移除 Debug 渲染对 detection pipeline 的整包导入。检测阈值不主动放宽。 |
| V4.5.1 | 开发版 | 结构收敛版：新增只读 policy view 分组，让 outer / separator / grid / scoring / calibration / partial / diagnostics 等参数有清晰入口；把 detection 后处理从 CLI 移入 `detection/postprocess.py`；把每个 count 的候选生成与最终候选选择拆成明确函数；收敛 active 代码里的旧别名和手写 analysis source 字符串；Debug Analysis 增加 Decision summary 面板，集中显示版本、PASS/REVIEW、confidence、outer strategy、analysis source、auto gate、gap 证据和 review reasons。检测阈值不主动放宽。 |
| V4.5 | 开发版 | Policy 架构整理版：把“可信分隔条 + format 几何反推 outer”的能力整理为通用 `separator_geometry_outer`，增加 full / partial mode policy；抽出共用的 separator band 搜索和 band sequence 工具，让 `separator_first` 与 `separator_geometry` 不再维护两套重复逻辑；为 report/detail 增加 `outer_candidate_strategy`，明确 base / content floating / long-axis edge-anchor / separator-first / separator-geometry 等候选来源；将历史评分字段命名收敛为 gate 语义。当前 active 行为保持保守：只有 `120-66 partial` 使用 `separator_geometry_outer_partial_mode=conditional`，其它 format 默认关闭。验证：`Test/135` full 对比 V4.4.6 为 48 unique rows / 0 diff；`Test/120/66` partial 对比 V4.4.6 为 16 unique rows / 0 diff；半格 full / partial 均 0 diff；120-67 核心输出 0 diff，仅一个旧 review reason 名称归一化。 |
| V4.4.6 | 开发版 | 增加通用的 separator-geometry outer candidate，并只在 `120-66` policy 中开启。它不做 PASS 后修框，而是在常规 partial 候选的画幅比例明显可疑时，用可信宽分隔条和当前 format 几何反推一个新的 outer 候选，再送回原有 separator / edge-pair / content / scoring / review-gate 竞争链路。不会提高 confidence，也不会把证据不足的图从 REVIEW 推成 PASS。验证：`Test/135` full 对比 V4.4.6 既有基线为 48 rows / 0 diff；`Test/120/66` partial 对比 V4.4.5 只有 `X5_test_56.tif` 切换到新的 separator-geometry 候选，status / confidence / review_reasons 不变。 |
| V4.4.5 | 开发版 | 默认输出文件夹从 `split_output/` 回溯性改名为 `x5_crop_output/`。当前源码、文档、快速启动说明以及本地可见 archive 快照均同步使用新目录名；CLI help 也改为 `default input/x5_crop_output`。 |
| V4.4.4 | 开发版 | 命名清理和诊断可读性修复：把 active 代码里的 `v2_*` / `diagnostics_v3_6` 历史命名改成 `candidate_decision` / `candidate_competition` / `diagnostics`；候选校准函数改为 `calibrate_candidate_decision()`，主入口改为 `choose_detection()`；移除未使用的 partial content 旧 policy；2-gap separator-first top-k 排序加入几何误差，避免只按分数过早丢候选；触发 50px output bleed 的诊断记录现在也能在普通 Debug Analysis 中画出对应 cyan tick。 |
| V4.4.3 | 开发版 | 维护噪音和局部性能清理：移除未调用旧常量 / 旧函数接口；`content_detection_for_count()` 复用同图同 format 的 content mask / bbox 中间结果；separator-first band sequence 对 1-gap / 2-gap 场景走更轻的 top-k 路径；Debug Analysis 复用 label 后的 original-gray preview；half full 的 equal-first + wide-retry 路径显式标记。V4.4.3 还把 partial、half 和 120 路径里的诊断叠片风险接入 output-only 50px long-axis bleed。验证：`Test/135` full 对比 V4.4.2 为 48 rows / 0 diff；`Test/半格/full`、`Test/半格/partial` 和 `Test/120/66` partial 仅出现预期的 frame_boxes 长轴 bleed 外扩差异，status / confidence / outer / gaps 不变。 |
| V4.4.2 | 开发版 | 保守性能和旧逻辑清理：彻底移除 content-only partial 的旧自动通过接口；partial 在同一 count 已有 `partial_safe_extra_frames` 自动通过时跳过 content candidate，并停止继续尝试更低 count；separator-first outer proposal 在生成组合时提前剪枝无效 spacing；enhanced separator merge 和 Debug nearby-separator 诊断增加精确缓存。验证：`Test/135` full、`Test/半格/partial`、`Test/120/66` partial、`Test/120/67` full、`Test/半格/full` 对比 V4.4.1 均为 0 diff。 |
| V4.4.1 | 开发版 | V4.4 后的结构清理：partial 的 separator-first 默认从 always 收回到 fallback，只对 `120-66` 和 `xpan` 保持积极模式；content-only partial 不再单独自动通过，必须回到 partial-safe / separator evidence 语义；floating outer 命名清理为通用 outer 逻辑；long-axis edge-anchor 改为按候选 outer 的局部 content bbox 判断贴边；135-dual 显式关闭无效 partial policy。验证：`Test/135` full 对比 V4.4 为 48 rows / 0 diff；`Test/半格/partial` 对比 V4.4 为 5 rows / 0 diff；`Test/120/66` partial 对比 V4.4 为 16 rows / 0 diff；`Test/120/67` full 和 `Test/半格/full` 对比既有基线均为 0 diff。 |
| V4.4 | 开发版 | 重分 full / partial 的 outer proposal 职责：full 回到完整铺满片夹的片条语义，移除 66/xpan full 中“不铺满片夹”假设的 floating / long-axis edge-anchor 主导逻辑；partial 获得 floating outer、separator-first outer、wide retry 和条件 long-axis edge-anchor fallback。`Test/135` full 对比 V4.3 为 48 rows / 0 diff；`Test/半格/partial` 对比 V4.3.1 为 5 rows / 0 diff；`Test/120/66` partial auto 为 15 个 `approved_auto` / 1 个 `needs_review`。 |
| V4.3.1 | 开发版 | partial mode 新增 `partial_safe_extra_frames` 自动通过 gate：当真实照片被稳定覆盖、内容证据正常、画幅几何稳定、没有 equal gap 和明显危险信号时，允许多切出少量空片夹区域，不再仅因 auto count / grid 补位较多而进入 REVIEW。`Test/半格/partial` 从 0 个 `approved_auto` / 5 个 `needs_review` 变为 5 个 `approved_auto` / 0 个 `needs_review`；`Test/135` full 对比 V4.3 为 48 rows / 0 diff。 |
| V4.3 | 开发版 | 整理 full-mode outer proposal layer：normal outer、floating full、separator-first 和 long-axis edge-anchor 都作为 outer 候选生成策略，统一进入原有 separator / edge-pair / content / geometry / review gate。新增 long-axis edge-anchor 用于 full 模式下有效片条沿长轴贴近一端开始的情况；它只提供候选，不直接提高 confidence。`Test/120/66` 对比 V4.2.9 为 0 diff；`Test/半格/full` 对比 V4.2.7 为 0 diff。 |
| V4.2.10 | 开发版 | 低风险缓存优化：全图 separator evidence / profile、content runs、content evidence detail、outer/content alignment、separator-first outer candidates 和 Debug Analysis 预览图在同一次处理中复用。缓存是全局能力，不限于 120-66；只复用完全相同的输入和候选，不做相近 outer 近似复用。`Test/120/66` 对比 V4.2.9 为 0 diff。 |
| V4.2.9 | 开发版 | 120-66 保守调参和 Debug Analysis 可读性改进：66 full 在没有 `wide-separator` 支撑时，会更谨慎地看待低质量普通 `edge-pair`；Separator / Content evidence 面板改为显示整张扫描，并叠加当前 outer / frame，方便检查 outer 外被忽略的证据。 |
| V4.2.8 | 当前稳定发布版 | 启动器交互改进：Mac / Windows 主启动器只在开启 partial mode 后询问 count；直接回车或输入 `auto` 表示自动判断张数，也可以输入当前 format 允许的固定张数。不开启 partial mode 时不再额外询问 count，继续使用完整片条固定张数。检测逻辑不变。 |
| V4.2.7 | 开发版 | 半格 full 稳定 grid 支持：新增 `half_stable_grid_support`，当 hard+grid 覆盖全部 gap、没有 equal、至少 35% gap 有 hard/wide 证据、frame 宽度极稳定、content support 正常且 joint score 达到 half stable-grid 下限时，可以把稳定几何补位视为可靠证据。`Test/半格/full` 为 10 个 `approved_auto` / 0 个 `needs_review`；相比 V4.2.6，`X5_00062`、`X5_00063` 新增通过，框和 gap 不变。 |
| V4.2.6 | 开发版 | 半格 full 宽分隔第二轮调参：`half_wide_geometry_support` 改为 majority-wide 规则，要求 wide/hard gap 覆盖至少 60% 分隔、没有 equal、frame 宽度稳定、内容支撑正常且 joint score 达到半格 wide 下限；content candidate 出现 `content_run_count_mismatch` 且存在可信 separator candidate 时，REVIEW 展示优先选择 separator candidate。`Test/半格/full` 为 8 个 `approved_auto` / 2 个 `needs_review`；相比 V4.2.5，`X5_00056`、`X5_00058` 新增通过，`X5_00063` 仍 REVIEW 但不再显示误导性的 content candidate。 |
| V4.2.5 | 开发版 | 半格 full 宽分隔调参：普通半格路径继续保留原有 equal/grid 行为，只有 wide retry 分支允许用 `wide-separator` 识别较宽黑色片距；新增 `half_wide_geometry_support` 闸门，要求 wide/hard gap 覆盖至少 80% 分隔、没有 equal、frame 宽度稳定、内容支撑正常且 joint score 过阈值。`Test/半格/full` 从 3 个 `approved_auto` / 7 个 `needs_review` 变为 6 个 `approved_auto` / 4 个 `needs_review`，新增通过为 `X5_00059`、`X5_00060`、`X5_00061`；`X5_00056`、`X5_00062` 仍保守 REVIEW。 |
| V4.2.4 | 开发版 | 行为保持的 separator-first fallback 清理：fallback 现在只构建 `separator_first_*` outer 候选，不再重复把普通 outer 候选放进同一轮竞争；没有 separator-first outer 时不写 retry used，直接回到原有 content / review 流程。同时校验 `separator_first_outer_mode` 只能是 `off` / `fallback` / `always`。验证：135、120-67、半格、120-66 对比对应 V4.2.x baseline 均为 0 diff。 |
| V4.2.3 | 开发版 | 将 separator-first outer proposal 从 120-66 专用逻辑推广成 format-aware 框架。120-66 继续 `always` 主动使用；135、half、xpan、120-645、120-67 改为 `fallback`，只在常规 separator / wide retry 未满足 auto gate 时尝试，因此不会覆盖已可靠的正常结果。135-dual 暂不启用。验证：120-66 full 为 16 个 `approved_auto` / 0 个 `needs_review`；135 对比 V4.2.2 为 0 diff，120-67 对比 V4.2.2 为 0 diff，半格对比 V4.2 baseline 为 0 diff。 |
| V4.2.2 | 开发版 | 为 120-66 full 增加 separator-first outer proposal：先从全局清晰黑色分隔带挑出两条内部分隔，再用 3 张 1:1 画幅反推 outer。候选仍走原有 separator / edge-pair / scoring / review gate，content-only 仍不能自动 PASS。当前 `Test/120/66` 为 16 个 `approved_auto` / 0 个 `needs_review`；135 对比 V4.2.1 为 0 diff，120-67 对比 V4.2.1 为 0 diff。 |
| V4.2.1 | 开发版 | 重做 120-66 full 的 outer 候选策略：count 固定为 3，但有效 outer 可以在整张扫描长图内浮动，用 3 张 6x6 画幅加分隔总宽度来解释几何，不再保护旧版 66 输出。120-66 full 测试为 13 个 `approved_auto` / 3 个 `needs_review`；135 对比 V4.2 为 0 diff，120-67 对比 V4.2 为 0 diff。 |
| V4.2 | 开发版 | 建立统一 full-format geometry model：用 `count * frame_aspect + separator_total / outer_short` 解释 outer 比例，并加入保守的阶段 C outer correction retry。当前规则只在完整 hard separator 能解释几何、修正幅度小且不裁内容时移动 outer。全量 135、半格、120-66、120-67 回归对比 V4.1.3 为 0 diff。 |
| V4.1.3 | 当前稳定 Release | 行为保持的结构清理：把 120 hard-full confidence floor 从评分层移到 candidate calibration 层，抽出 120 共享 format policy，统一 outer retry 入口，并让 120-67 短轴 outer 触发条件更语义化。全量 135、半格、120-66、120-67 回归对比 V4.1.2 为 0 diff。 |
| V4.1.2 | 开发版 | 120-67 短轴 outer 窄修复：当 hard separator 可靠、content aspect 正常、但短轴 content slack 明显偏大时，让 120-67 走现有 content-aligned outer retry，解决 `Test/120/67/3.tif` 短轴 outer 偏松的问题。 |
| V4.1.1 | 开发版 | 120-67 窄修复：普通 separator 未过 auto gate 时，允许 120-67 使用保守 `wide-separator` retry，解决 `Test/120/67/2.tif` 第一条宽分隔被退成 equal 的问题。 |
| V4.1 | 开发版 | 120-66 / 120-67 参数校准：66 在可靠 hard separator 下可做短轴 outer 扩展，67 横向比例修正为 5:4，并为 120-67 的 edge-pair / hard separator candidate 提供更合适的 confidence floor。content-only 仍不会自动 PASS。 |
| V4.0.1 | 历史稳定 Release | 135 宽片距兼容调整：默认窄分隔逻辑保持 V4.0 行为；只有普通 separator 候选未通过 auto gate 时，才启用正式 `wide-separator` 分支。目标是兼容清晰但片距较宽的 135 扫描，同时不改变既有 `Test/135` 输出。 |
| V4.0 | 上一个稳定 Release | 大胆模块化重写版：根入口 `X5_Crop.py` 变薄，实际检测、I/O、几何、证据、Debug、report、deskew 和 CLI 职责拆进 `x5crop/` 多个模块，`core.py` 仅保留兼容导出。新增单文件发布版生成器，让 Release 用户仍然只需要脚本本体和启动器。全量 135 default-deskew dry run 对比 V3.9 为 0 diff。 |
| V3.9 | 开发版 | 结构清理版：把剩余 outer mask profiles、post-detection confidence caps、deskew span skip、frame-fit 小像素容忍、separator gate mode 和 outer retry 开关收进 policy / format-aware 配置。全量 135 default-deskew dry run 对比 V3.7 为 0 diff。 |
| V3.7 | 开发版 | 合并 frame-size fit 管线：cuts 级等宽修正改为 geometry fallback，box 级同画幅拟合改为 edge-evidence fit，并通过统一入口选择。目标是让 edge-pair 扩展到各格式后的 frame fit 更清楚，同时保持现有输出不变。 |
| V3.6.12 | 开发版 | 根据 `Test/120` 和半格全量 dry run 调整非 135 edge-pair 参数：120-66 / 120-67 能识别更宽、更低背景的 120 暗带证据，但不会放宽 PASS。 |
| V3.6.11 | 开发版 | 将 `edge-pair` 扩展为 format-aware full-strip 逻辑，135 保持原参数，其它格式保守启用。 |
| V3.6.10 | 开发版 | 低风险清理版：移除未使用函数，修正 CLI help 和诊断旧话术，不改变检测流程。 |
| V3.6.9 | 开发版 | 统一 active grid protection 和 diagnostics 的轻量 hard-gap trust，减少红框可信度双轨冲突。 |
| V3.6.8 | 开发版 | 将 single-anchor 精确组合闸门改成 `lucky_pass_risk_score`，避免规则看起来像为单张图定制。 |
| V3.6.7 | 开发版 | 将 nearby separator 复查提升为很窄的 correction，并新增 single-anchor lucky PASS review gate。 |
| V3.6.6 | 开发版 | 新增 hard gap trust、nearby separator 复查和受限的 strong separator 抗 grid 覆盖规则。 |
| V3.6.5 | 开发版 | 诊断模式允许最多 4 个并行 worker；普通运行仍最多 2 个。检测逻辑不变。 |
| V3.6.4 | 开发版 | 回到 V3.6.2 检测基线，并新增只针对首尾 hard separator 可靠时的单侧长轴白边外框收紧。 |
| V3.6.3 | 已暂停 / 参考方向 | 将叠片 / 近似叠片作为困难图处理：135 full strip 的 strong overlap-risk model gap 会进入 REVIEW。该方向暂时搁置。 |
| V3.6.2 | 稳定发布版 | 合并低收益 `equal-broad-region` method，并把 hard fallback 缩小成 review-only equal split fallback。叠片、近似叠片、局部片距不稳定等困难图仍可能误识别。 |
| V3.6.1 | 开发版 | 继续优化诊断层：诊断报告和 Debug Analysis 诊断 tick 只在显式 `--diagnostics` 时生成；普通启动器不开启诊断。 |
| V3.6 | 开发版 | 从 V3.3.1 输出基线出发做诊断清理，新增只读红框可信度和叠片/连续内容诊断，不改变 V3.3.1 输出。 |
| V3.5 | 已暂停 / 已回滚 | 红色 hard gap 语义校验实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.2 | 已暂停 / 已回滚 | 局部 grid 分段实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.1 | 已暂停 / 参考方向 | 当强 hard separator 与 robust grid 冲突时，优先保留强 hard separator。这个方向仍有参考价值，但当前先回到 V3.3.1 作为稳定基线。 |
| V3.4 | 简化检测实验方向 | 曾尝试移除低收益增强分隔层，并简化候选生成。当前 V3.9 主脚本仍保留 `--analysis` 控制的保守增强分隔辅助。 |
| V3.3.2 | 开发版 | 保守的叠片/近似叠片 gap 处理。 |
| V3.3.1 | 稳定发布版 / V3.6 输出基线 | 稳定打包版本，基于 V3/V3.2 风格检测链路，并加入只在输出阶段生效的 bleed。 |
| V3.3 | 开发版 | 检测 bleed 与输出 bleed 分离。 |
| V3.2 | 开发版 | 在 V3.1.x 回退后恢复 V3 风格检测链路。 |
| V3.1.x | 实验版 | 激进外框/gap 修复实验，稳定性不足。 |
| V3.0 | 基线版 | X5 Crop 主脚本与用户工作流基础。 |

### 当前 Active 版本：V4.7

V4.7 是一次 clean-room source rewrite。它不以主动改变检测阈值为目标，而是在 V4.6 policy 架构基础上移除旧兼容残留，让 active source 只剩真实职责模块，并以 V4.5.4 golden reports 验证行为不漂移。

主要变化：

- 删除旧 `x5crop/common.py`、`x5crop/policy.py`、`x5crop/core.py` 和根级 `x5crop/io.py` / `x5crop/geometry.py` / `x5crop/regression.py` 兼容层。
- `ARCHITECTURE.md` 现在放在仓库根目录，作为中文说明 + English Guide 的开发者架构地图；重复的 `docs/ARCHITECTURE.md` 镜像已移除，避免双处维护。
- `FormatTuning` 已从 active source 移除；`x5crop/policies/parameters.py` 只保留薄 lookup / public export，具体 format 参数拆到 `x5crop/policies/presets/`。
- `FormatParameters` 新增 capability-specific 参数分组：partial counts、separator gate、leading-grid separator failure、separator geometry support、gap search、hard-gap trust、nearby separator correction、robust grid、wide retry、outer strategy、short-axis aspect retry、partial holder、scoring calibration、candidate competition、content evidence、debug gap overlay、nearby separator diagnostics、overlap-risk diagnostics、lucky-pass risk 和 postprocess。policy factory 现在从这些分组构建 `DetectionPolicy`，candidate calibration、wide-retry、content-evidence runtime、Debug Analysis gap overlay、nearby separator diagnostics、overlap-risk diagnostics、gap search、hard-gap trust、nearby separator correction、robust grid、short-axis aspect retry、lucky-pass risk diagnostics、postprocess final caps 和 leading-grid failure gate 也分别从 `ScoringPolicy` / `wide_retry` / `content_evidence` / `DiagnosticsPolicy.debug_gap_overlay` / `DiagnosticsPolicy.nearby_separator` / `DiagnosticsPolicy.overlap_bleed_risk` / `SeparatorPolicy.gap_search` / `SeparatorPolicy.hard_gap_trust` / `SeparatorPolicy.nearby_correction` / `SeparatorPolicy.robust_grid` / `OuterPolicy.short_axis_aspect_retry` / `DiagnosticsPolicy.lucky_pass_risk` / `PostprocessPolicy` / `SeparatorGatePolicy` 读取 caps、weights、retry width、内容证据阈值、诊断叠加线条参数、nearby 搜索阈值、gap 搜索半径/宽度/guard/score、wide separator 接受阈值、nearby correction 阈值、robust-grid 阈值、short-axis aspect retry 误差/目标比例/边距、overlap 风险阈值、trust 阈值、风险评分权重、最终 REVIEW cap 和 gate limits；剩余平面字段只作为 detector / geometry runtime 迁移面保留。
- `x5crop/policies/registry.py` 收敛为 policy resolve/cache；每个 format/mode 的 gate profile、edge-pair、frame-fit、dark-band、diagnostics 和 notes 由对应 `format_*.py` preset 拥有。
- `FrameFitPolicy` 迁入 `x5crop/policies/base.py`，由 `DetectionPolicy.frame_fit` 拥有；geometry 不再构造 `frame_fit_policy(fmt, strip_mode)` fallback。
- `SeparatorEdgePairPolicy` 继续由 `DetectionPolicy.separator` 持有；geometry edge-pair refinement 要求调用方传入 policy 对象，不再保留 `edge_pair_params_for_format()` fallback。
- `detection/pipeline.py` 继续缩小为主流程编排；candidate build/run、cache keys、candidate calibration、hard fallback 和 partial edge hint 已迁出到 `candidate_build.py`、`candidate_run.py`、`cache_keys.py`、`calibration.py`、`fallback.py` 和 `partial.py`。
- `CandidateRunPolicy.content_candidate` / `FallbackPolicy` / `PartialStopPolicy` 现在显式描述 candidate run 的 content-candidate 启用、separator-auto 后跳过 content 的 strip-mode 集合和 reason、fallback outer proposal，以及 partial safe-auto 停止 / 跳过 content 的 strip-mode 集合和 reason；`CandidateRunPolicy.separator_geometry_competition` 接管 conditional separator-geometry 候选是否可竞争的 content-outer strategy scope、strip-mode scope 和 median-aspect 阈值，`CandidateRunPolicy.equal_first_before_wide_retry` 接管 equal-first wide-retry 的 wide-geometry 依赖、strip-mode scope 和 default-count 要求，`CandidateRunPolicy.dark_band_retry` 接管 full/partial dark-band retry 触发条件，`candidate_run.py` 不再隐藏 1.045 / 1.090 常量、full/partial content-skip mode 或 120-66 dark-band retry 分支。
- `OuterCandidate.strategy` 成为 outer 候选类型契约，candidate build / run / calibration 不再靠候选名称 prefix 推断 dark-band、separator-first、edge-anchor 或 retry 行为。
- `separator_gate_120_*` 参数命名收敛为语义化 `separator_gate_*` 字段；separator gate detail reason 也去掉了 `135_` / `half_` / `120_` 格式前缀。
- `SeparatorGatePolicy.leading_grid_failure` 接管 leading weak-grid separator failure 判断；`detection/gates.py` 不再直接读取平面 `leading_grid_failure_*` preset 字段。
- `SeparatorPolicy.hard_gap_trust` 接管 hard-gap trust 的语义阈值；robust-grid hard separator protection 和 `detection/diagnostics.py` 不再直接读取平面 `hard_trust_*` preset 字段。
- `SeparatorPolicy.nearby_correction` 接管 active nearby separator correction 的启用开关、搜索窗口、score / distance / local-geometry 阈值；`candidate_build.py` 和 `geometry/gaps.py` 不再直接读取平面 `nearby_*` preset 字段做候选修正。
- `SeparatorPolicy.robust_grid` 接管 hard-gap 几何约束、robust-grid 拟合、reliable-gap score 和 hard-separator protection 阈值；`geometry/gaps.py`、`geometry/core.py` 和 scoring runtime 不再直接读取平面 `constrain_*` / `robust_*` preset 字段。
- `SeparatorPolicy.gap_search` 接管 base separator gap search 的半径、宽度、guard、score 和 wide separator 接受阈值；`geometry/gaps.py`、`geometry/core.py`、`candidate_build.py`、`candidate_run.py` 和 `outer_retry.py` 不再直接读取平面 `gap_*` / `wide_gap_min_*` preset 字段。
- `SeparatorPolicy.profile` / `edge_refine_profile` 接管 separator profile 和 edge-refine profile 生成阈值、平滑窗口、权重和背景阈值；`geometry/separator_profile.py` 不再直接读取平面 `separator_profile_*` / `edge_refine_*` preset 字段，检测路径和 read-only diagnostics 会显式传入当前 policy，profile / edge-refine 缓存也按当前 policy 分桶。
- `SeparatorPolicy.enhanced` 接管 enhanced separator 辅助层的触发低分阈值、接受分数、宽度和位移限制；`geometry/core.py` 不再直接读取平面 `enhanced_*` preset 字段，policy factory 改为读取 `enhanced_separator` 参数分组。
- `SeparatorPolicy.wide_separator_confidence_cap` 接管包含 wide separator gap 的候选 confidence cap；`calibration.py` 不再直接读取 flat wide-retry confidence-cap 参数。
- `DiagnosticsPolicy.lucky_pass_risk` 接管 lucky-pass risk 的启用开关、评分权重和风险阈值；`detection/diagnostics.py` 不再直接读取平面 `lucky_*` preset 字段计算风险。
- `DiagnosticsPolicy.nearby_separator` 接管 nearby separator diagnostic search 的窗口、排除范围、候选宽度上限和 stronger-candidate 阈值；`nearby_separator_candidate_detail()` 不再直接读取平面 `nearby_*` preset 字段。
- `DiagnosticsPolicy.overlap_bleed_risk` 接管 overlap-bleed diagnostic attachment 和 overlap-risk 阈值；`detection/diagnostics.py` 不再直接读取平面 `diagnostic_overlap_*` preset 字段。
- `DiagnosticsPolicy.debug_panels` / `debug_panel_titles` 接管 Debug Analysis 三栏顺序和标题；渲染层只保留当前 `Original gray`、`Debug boxes`、`Separator evidence` 面板。
- `ReportPolicy` 接管 report schema version 和 section order；`report_schema_for_detection()` 现在从当前 format/mode policy 读取报告 schema，而不是直接使用检测层硬编码常量。
- `ScoringPolicy` 接管 candidate calibration weights、separator source bias、hard-full confidence floor 和 no-auto caps；`calibration.py` / `scoring.py` 不再直接读取 flat `scoring_calibration`。
- `ScoringPolicy.base_detection` 接管 `score_detection()` 的 gap / width / outer / contrast 权重、full-geometry floor、partial caps、outer-too-large cap 和低置信阈值；`score_detection()` 不再直接读取 flat `score_*` 字段。
- `ContentPolicy` 接管 candidate calibration 中 content-support score 的 norm、weight 和 support gate；`content_support_score()` 不再直接读取 flat `content_support_*` 字段。
- `ContentPolicy.evidence` / `profile` / `mask` / `candidate` 接管 content evidence 阈值、content-run profile、content mask outer 和 content-only candidate confidence cap；`detection/content.py` 不再直接读取 flat `content_*` preset 字段或 runtime `FormatParameters`。
- `FormatParameters.content_evidence` / `content_profile` / `content_mask` / `content_candidate` / `content_support` 现在是构建 `ContentPolicy` 的 preset-side 能力视图；policy factory 不再直接读取对应平面 `content_*` 字段。
- `ScoringPolicy.geometry_support` 接管 candidate calibration 中 geometry-support score 的 width、outer、aspect、count norm / weight 和 outer-area bounds；`geometry_support_score()` 不再直接读取 flat `geometry_support_*`、`geometry_width_cv_norm`、`content_support_aspect_norm` 或 score outer-area 字段。
- `FormatParameters.geometry_support_score` 现在是构建 `ScoringPolicy.geometry_support` 的 preset-side 能力视图；policy factory 不再直接读取 geometry-support 相关平面 score 字段。
- `ScoringPolicy.separator_support` 接管 candidate calibration 中 separator-support score 的 hard/model 权重、grid/equal credit 和 single-frame cap；`separator_support_score()` 不再直接读取 flat `separator_model_*` / `separator_support_*` 字段。
- `PartialHolderPolicy` 接管 66 partial strict holder 的 safe-extra-frames strip-mode scope、frame mean / coverage / aspect-error 检查；`partial_holder.py` 不再直接读取 `policy.parameters.content_evidence`。
- 旧 outer mode helper / adapter 已从 active runtime 删除，outer proposal 是否启用由 `DetectionPolicy.outer` 统一决定。
- `x5crop/geometry/core.py` 继续拆分为真实职责模块：`boxes.py`、`layout.py`、`outer_boxes.py`、`gaps.py`、`separator_profile.py`、`frame_fit.py` 和 `output_adjustment.py`。
- `separator_outer_allow_oversized_band` 成为 `OuterPolicy` capability，当前只由 `120-66` full / partial 开启，替代实现层 `tuning.name == "120-66"` 判断。
- `OuterPolicy.separator_gap_search_max_width_ratio` 接管 separator-derived outer 候选的 gap-search 宽度覆盖值；`candidate_run.py` 不再直接读取平面 `separator_first_outer_gap_max_width_ratio`。
- `OuterPolicy.separator_outer_band` / `separator_geometry_outer` 接管 separator-first / separator-geometry outer proposer 的 band、sequence、source、margin 和候选数量参数；`detection/outer.py` 不再直接读取平面 `separator_first_outer_*` / `separator_geometry_outer_*` preset 字段。
- `FormatParameters.content_floating_outer` / `edge_anchor_outer` / `base_outer_candidates` / `separator_outer_band` / `separator_geometry_outer` 现在是构建 outer proposal policy 的 preset-side 能力视图；policy factory 不再直接读取这些 outer proposal 平面字段。
- `OuterPolicy.grid_refine` 接管 full-strip grid-based outer refinement 的 shift 和 width-change 限制；`candidate_build.py` 不再直接读取平面 `grid_outer_refine_*` preset 字段。
- `OuterPolicy.format_geometry_retry` 接管 format-geometry outer retry 的启用开关、比例容差、收缩限制和 content margin；`outer_retry.py` 不再直接读取平面 `format_geometry_outer_retry_*` preset 字段。
- `OuterPolicy.short_axis_aspect_retry` 接管 short-axis aspect outer retry 的误差、目标比例和边距阈值；该 capability 默认关闭，当前只在 `120-66` full policy 中启用，`outer_retry.py` 不再直接读取平面 `short_axis_aspect_retry_*` preset 字段。
- `OuterPolicy.content_alignment` 接管 outer/content alignment 的 slack、white-edge、mismatch gate 和 content-aligned retry margin 阈值；`outer_retry.py` / `postprocess.py` 不再直接读取平面 `outer_align_*` preset 字段。
- `OuterPolicy.base_candidates` 接管 base outer candidate 的 bw / white-x / mask-profile 搜索阈值、margin 和候选面积限制；`geometry/outer_boxes.py` 不再直接读取平面 `outer_*` preset 字段或按 format 名查参数。
- `PartialEdgeHintPolicy` 接管 partial-strip edge hint 的 window ratio / min / max；`detection/partial.py` / `candidate_build.py` 不再直接读取平面 `partial_edge_hint_*` preset 字段。
- `x5crop/io/tiff.py`、`x5crop/image/evidence.py`、`x5crop/image/deskew.py` 和 `x5crop/detection/diagnostics.py` 改为显式 import，不再依赖旧 `common` 星号导入。
- `DiagnosticsPolicy.debug_gap_overlay` 接管 Debug Analysis separator-panel 的 gap overlay 容差、tick 长度和线宽，`debug/render.py` 不再直接读取平面 `debug_gap_*` preset 字段，也不再硬编码 gap tick 长度。
- `PostprocessPolicy` 接管 content aspect、low content、outer mismatch 和 lucky-pass risk 的最终 confidence cap，以及 postprocess 阶段 outer-alignment disabled、likely partial、outer-candidate disagreement 和 deskew uncertainty reason id；`finalize_detection_decision()` 不再通过旧 `tuning` 参数或 runtime 硬编码读取这些字段。
- `PostprocessPolicy.approved_geometry_adjustment` 接管 approved-auto 输出几何微扩的 long-axis limit 和 minimum extension；`geometry/output_adjustment.py` 不再直接读取平面 `approved_adjust_*` preset 字段。
- `OutputPolicy.overlap_risk_long_axis_bleed` 接管 overlap-risk 时输出阶段长轴 bleed 提升值；`postprocess.py` 和缓存复用 workflow 不再硬编码 50px。
- `OutputPolicy.edge_bleed_protection` 接管 full-strip 输出 edge guard 的 ratio / min / max；`geometry/output_adjustment.py` 不再保留硬编码 edge guard。
- `OutputPolicy.detection_long_axis_bleed` / `detection_short_axis_bleed` 接管检测阶段 bleed 配置；默认仍为 0/0，`detection_geometry_config()` 不再硬编码 0/0。
- `OuterPolicy.content_floating_outer` / `edge_anchor_outer` 接管 content-floating 和 long-axis edge-anchor outer proposal 的 threshold、margin、ratio extra 和候选数量；`detection/outer.py` 不再直接读取平面 `floating_outer_*` / `long_axis_edge_anchor_*` preset 字段。
- `x5crop/geometry/__init__.py` 和 `x5crop/io/__init__.py` 改为白名单导出；未使用的纯 re-export wrapper 已删除。
- 评分路径修正为保持 V4.5.4 语义：输出 frame 仍可使用 edge-evidence frame fit，但 nearby separator correction 后的 confidence 只用 geometry fallback score 做窄限制，避免结构迁移把少数 135 样片推到 1.0 或压到 0.88。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.7`。
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/*/*.py x5crop/*/*/*.py` 通过。
- 旧兼容残留扫描没有命中：`common`、`FormatTuning`、`format_tuning`、`separator_gate_mode`、`score_gate_135`、`separator_135`、`separator_half`、`import *`、`edge_pair_params_for_format`、`frame_fit_policy`。
- `git diff --check` 通过。
- policy smoke 确认 14 个 format / strip mode policies resolve。
- `ReportPolicy` smoke 确认 report schema version `v4_7_policy_schema_1` 和 report sections 可通过当前 format / strip mode policy resolve。
- V4.7 content policy runtime 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_content_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff，并生成 103 张 Debug Analysis JPG：
  - `Test/135` full，48 rows，43 approved / 5 review
  - `Test/new_135` full，4 rows，4 approved / 0 review
  - `Test/120/66` full，16 rows，16 approved / 0 review
  - `Test/120/66` partial，16 rows，16 approved / 0 review
  - `Test/120/67` full，4 rows，3 approved / 1 review
  - `Test/半格/full`，10 rows，10 approved / 0 review
  - `Test/半格/partial`，5 rows，5 approved / 0 review
- V4.7 candidate-run policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_candidate_run_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。本轮没有生成 Debug Analysis JPG。
- V4.7 report policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_report_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。
- V4.7 dark-band candidate-run policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_dark_band_candidate_run_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。
- V4.7 selection policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_selection_policy_20260701_run3`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认只有 `half_full` 启用 `SelectionPolicy.content_mismatch_review`。
- V4.7 content-candidate run policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_content_candidate_run_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认所有 format/mode 都通过 `CandidateRunPolicy.content_candidate` 解析 content candidate 运行规则。
- V4.7 postprocess reason policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_postprocess_reason_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认所有 format/mode 都通过 `PostprocessPolicy` 解析 postprocess review/detail reason id。
- V4.7 Debug panel policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_debug_panel_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认所有 format/mode 都解析到同一组三栏 panel id / title；单张 135 Debug Analysis smoke 写出 1679x876 RGB JPG。
- V4.7 candidate-run mode policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_candidate_run_mode_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认 separator-auto content skip 只给 `full`，partial-safe content skip 只给 `partial`。
- V4.7 selection scope policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_selection_scope_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认只有 `half_full` 启用 `SelectionPolicy.content_mismatch_review`，其 scope 为 `full` 且要求 default count。
- V4.7 dark-band selection scope 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_dark_band_selection_scope_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认只有 `120_66_full` / `120_66_partial` 启用 dark-band full-selection capability，scope 为 `full` 且要求 required count。
- V4.7 dark-band retry scope policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_dark_band_retry_scope_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认只有 `120_66_full` / `120_66_partial` 启用 dark-band，retry scope 为 `full` / `partial`，full retry 要求 default count。
- V4.7 equal-first wide-retry policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_equal_first_wide_retry_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认 equal-first wide-retry policy scope 为 `full` 且要求 default count，实际 wide geometry support 仍只有 `half_full` 开启。
- V4.7 partial-holder scope policy 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_partial_holder_scope_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认 partial-holder safe-extra-frames scope 为 `partial`，strict holder 仍只有 `120_66_partial` 启用。
- V4.7 separator-geometry competition scope 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_separator_geometry_competition_scope_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认 content-outer max median-aspect cap 的 strategy scope 为 `content_outer`、strip-mode scope 为 `partial`。
- V4.7 separator-incomplete reason 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_separator_uncertain_reason_policy_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。14-policy smoke 确认所有 format/mode 都通过 `ScoringPolicy.base_detection` 解析语义化的 `separator_evidence_incomplete` reason id，active runtime 不再保留旧 `120_separator_uncertain` reason 名称。
- V4.7 implicit-135 default 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_no_implicit_135_default_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。底层 deskew、gap、separator profile cache、content profile 和 diagnostics helper 现在要求显式 `format_name`，不再保留 `"135"` 隐式默认值。
- V4.7 dark-band mode-preset 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_dark_band_mode_preset_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。`ModePolicyPreset.dark_band` 现在把 dark-band mode、full-selection 和 oversized separator-band 开关收成单个能力包；14-policy smoke 确认 dark-band / oversized separator-band enablement 仍只给 `120_66_full` 和 `120_66_partial`。
- V4.7 separator-profile parameter-view 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_profile_parameter_views_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。新增 `SeparatorProfileParameters` / `EdgeRefineProfileParameters` 以及 `FormatParameters.separator_profile` / `edge_refine_profile` 能力视图，policy factory 不再直接读取平面 `separator_profile_*` / `edge_refine_*` 字段。
- V4.7 content / geometry-support parameter-view 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_content_parameter_views_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。新增 `ContentProfileParameters` / `ContentMaskParameters` / `ContentCandidateParameters` / `ContentSupportParameters` / `GeometrySupportScoreParameters` 以及对应 `FormatParameters` 能力视图，policy factory 不再直接读取这些 content / geometry-support 平面字段。
- V4.7 outer-proposal parameter-view 清理后的 dry-run regressions 写入 `/private/tmp/x5_v47_outer_parameter_views_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。新增 `ContentFloatingOuterParameters` / `EdgeAnchorOuterParameters` / `BaseOuterCandidateParameters` / `SeparatorOuterBandParameters` / `SeparatorGeometryOuterParameters` 以及对应 `FormatParameters` 能力视图，policy factory 不再直接读取这些 outer proposal 平面字段。
- V4.7 final policy-readiness dry-run regressions 写入 `/private/tmp/x5_v47_final_policy_readiness_20260701_run1`；七组本地 V4.5.4 golden core comparison 在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 上全部 0 diff。新增 `DebugGapOverlayPolicy.tick_length_ratio` / `tick_length_min`，Debug Analysis gap tick 长度现在由 policy 控制。focused Debug Analysis smoke 生成 `/private/tmp/x5_v47_final_debug_smoke_20260701/_debug_analysis/X5_00041_debug_analysis.jpg`，JPG 为 1679x876 RGB，三栏标题和 Debug gap tick 参数均由 policy resolve。
- 默认 golden compare 仍有 196 个 metadata-only diffs，字段为 `detail.policy` / `report_schema`，原因是 V4.5.4 golden reports 没有 V4.7 policy/report-schema 元数据。
- 旧兼容 / 旧命名扫描没有命中：candidate-name `startswith()` strategy inference、旧 outer mode helper、`separator_gate_120_*`、旧格式前缀 gate/scoring reason、`120_separator_uncertain`、`FormatTuning`、`format_tuning`、`import *`、`edge_pair_params_for_format`、`frame_fit_policy`、隐式 `format_name: str = "135"` 默认值。
- policy factory flat-field residue 扫描没有命中 separator gate、score gate、partial-safe holder、candidate competition、calibration caps、outer strategy、wide retry、outer retry、leading-grid failure、nearby separator diagnostics、overlap-risk diagnostics、hard-gap trust、nearby separator correction、robust grid、gap search 或 lucky-pass risk 直接平面字段读取；这些入口已经改为读取 `FormatParameters` 的 capability 分组。
- scoring runtime residue 扫描没有在 active detection / geometry / workflow runtime 命中 `tuning.scoring_calibration`、`policy.parameters.scoring_calibration` 或 `scoring_calibration`；这些路径已经改为读取 `ScoringPolicy`。
- base scoring residue 扫描没有在 `score_detection()` 中命中 `score_*` 直接平面字段读取；这些路径已经改为读取 `ScoringPolicy.base_detection`。
- content-support scoring residue 扫描没有在 `content_support_score()` / candidate calibration 中命中 `content_conf_*` 或 `content_support_*` 直接平面字段读取；这些路径已经改为读取 `ContentPolicy`。
- content runtime residue 扫描没有在 `detection/content.py` 命中 `format_parameters()`、`tuning.content*` 或 `policy.parameters`；content evidence、profile、mask 和 content-only candidate confidence 已经改为读取 `ContentPolicy` 子 policy。
- geometry-support scoring residue 扫描没有在 `geometry_support_score()` / candidate calibration 中命中 `geometry_support_*`、`geometry_width_cv_norm`、`content_support_aspect_norm` 或 score outer-area 直接平面字段读取；这些路径已经改为读取 `ScoringPolicy.geometry_support`。
- separator-support scoring residue 扫描没有在 `separator_support_score()` / candidate calibration 中命中 `separator_model_*` 或 `separator_support_*` 直接平面字段读取；这些路径已经改为读取 `ScoringPolicy.separator_support`。
- wide-retry / content-evidence runtime residue 扫描没有命中 `tuning.wide_retry`、`tuning.wide_gap_retry_*`、`tuning.wide_gap_confidence_cap`、`tuning.content_evidence_*` 或 `format_parameters(...).content_evidence_*` 直接平面字段读取；这些路径已经改为读取 `SeparatorPolicy.wide_separator_confidence_cap`、`wide_retry` 和 `content_evidence` 分组。
- partial-holder frame-content residue 扫描没有在 `x5crop/detection/partial_holder.py` 命中 `policy.parameters.content_evidence`；frame aspect conflict 检查已经改为读取 `PartialHolderPolicy`。
- candidate-run separator outer gap override residue 扫描没有在 `x5crop/detection/candidate_run.py` 命中 `format_parameters()` 或 `separator_first_outer_gap_max_width_ratio` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.separator_gap_search_max_width_ratio`。
- separator-derived outer proposer residue 扫描没有在 `x5crop/detection/outer.py` 命中 `FormatParameters`、`format_parameters()`、`tuning.*`、`separator_first_outer_*` 或 `separator_geometry_outer_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.separator_outer_band`、`OuterPolicy.separator_geometry_outer` 和 `SeparatorPolicy.gap_search`。
- base outer candidate residue 扫描没有在 `x5crop/geometry/outer_boxes.py`、`x5crop/detection/outer.py` 或 `x5crop/detection/dual_lane.py` 命中 `FormatParameters`、`format_parameters()`、`tuning.*` 或 flat `outer_*` candidate-threshold 直接读取；runtime 已经改为读取 `OuterPolicy.base_candidates`。
- separator profile residue 扫描没有在 `x5crop/geometry/separator_profile.py`、`x5crop/detection/candidate_build.py`、`x5crop/detection/outer.py` 或 `x5crop/detection/diagnostics.py` 命中 `format_parameters()`、`tuning.*`、`separator_profile_*` 或 `edge_refine_*` 直接平面字段读取；runtime 已经改为读取 `SeparatorPolicy.profile` 和 `SeparatorPolicy.edge_refine_profile`，缓存 key 也包含当前 profile policy。
- enhanced separator residue 扫描没有在 `x5crop/geometry/core.py` 或 `x5crop/detection/candidate_build.py` 命中 `format_parameters()`、`tuning.*` 或 flat `enhanced_*` 直接平面字段读取；runtime 已经改为读取 `SeparatorPolicy.enhanced`，policy factory 改为读取 `enhanced_separator` 参数分组。
- grid outer-refine residue 扫描没有在 `x5crop/policies/**` 以外命中 `grid_outer_refine_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.grid_refine`。
- format-geometry retry residue 扫描没有在 `x5crop/policies/**` 以外命中 `format_geometry_outer_retry_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.format_geometry_retry`。
- short-axis aspect retry residue 扫描没有在 `x5crop/detection/outer_retry.py` 命中 `short_axis_aspect_retry_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.short_axis_aspect_retry`。
- outer content-alignment residue 扫描没有在 `x5crop/detection/outer_retry.py` 或 `x5crop/detection/postprocess.py` 命中 `outer_align_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.content_alignment`。
- content-floating / edge-anchor outer residue 扫描没有在 `x5crop/detection/outer.py` 命中 `floating_outer_*` 或 `long_axis_edge_anchor_*` 直接平面字段读取；runtime 已经改为读取 `OuterPolicy.content_floating_outer` 和 `OuterPolicy.edge_anchor_outer`。
- partial edge-hint residue 扫描没有在 `x5crop/policies/**` 以外命中 `partial_edge_hint_*` 直接平面字段读取；runtime 已经改为读取 `PartialEdgeHintPolicy`。
- Debug Analysis gap-overlay residue 扫描没有在 `x5crop/debug/render.py` 命中 `format_parameters()`、`debug_gap_*` 直接平面字段读取或硬编码 gap tick 长度；渲染层已经改为读取 `DiagnosticsPolicy.debug_gap_overlay` 的 overlay 容差、tick 长度和线宽。
- Debug Analysis panel residue 扫描没有在 `x5crop/debug/render.py` / `x5crop/policies` 命中旧 `Content evidence` 或 `Decision summary` 面板入口；三栏标题由 `DiagnosticsPolicy.debug_panel_titles` 提供。
- Candidate-run mode residue 扫描没有命中旧 `skip_after_full_separator_auto` / `full_separator_auto_skip_reason` 字段；content skip 的 mode 集合现在由 `CandidateRunPolicy.content_candidate` 和 `PartialStopPolicy` 显式提供。
- Selection scope residue 扫描没有在 `selection.py` 命中 content mismatch review 的硬编码 `best.strip_mode != "full"` / `candidate.strip_mode != "full"`；strip-mode scope 和 default-count 要求现在由 `SelectionPolicy.content_mismatch_review` 显式提供。
- Dark-band selection residue 扫描没有在 `candidate_run.py` 命中 `current_best.strip_mode != "full"`；dark-band full-selection 的 strip-mode scope 和 required-count 要求现在由 `DarkBandOuterPolicy` 显式提供。
- postprocess-cap residue 扫描没有在 `x5crop/detection/postprocess.py` 命中 `tuning.post_*_cap` 直接平面字段读取；最终 decision cap 已经改为读取 `PostprocessPolicy`。
- approved geometry adjustment residue 扫描没有在 `x5crop/policies/**` 以外命中 `approved_adjust_*` 直接平面字段读取；runtime 已经改为读取 `PostprocessPolicy.approved_geometry_adjustment`。
- overlap-risk output bleed residue 扫描没有在 active runtime 命中 `max(int(config.bleed_x), 50)` 硬编码；runtime 已经改为读取 `OutputPolicy.overlap_risk_long_axis_bleed`。
- edge bleed protection residue 扫描没有在 active runtime 命中硬编码 `max(70.0, min(120.0, nominal * 0.0150))` 风格 guard；runtime 已经改为读取 `OutputPolicy.edge_bleed_protection`。
- detection bleed residue 扫描没有在 active runtime 命中 `bleed_x=0` / `bleed_y=0` 硬编码；runtime 已经改为读取 `OutputPolicy.detection_*_bleed`。
- 135 Debug Analysis smoke 生成 `/private/tmp/x5_v47_postprocess_policy_debug_smoke/_debug_analysis/X5_00041_debug_analysis.jpg`，JPEG 1679x876 RGB。

未验证：

- default-deskew export timing。
- `xpan`、`120-645` 和 `135-dual` full sample comparisons，因为本地 golden reports 未列出。
- Release package generation。

### V4.6

V4.6 是一次 policy 化重构。它不以主动改变检测阈值为目标，而是把 V4.5.4 已验证的行为整理成 format / strip mode 明确分离的策略入口，方便后续只调某个格式和模式。

主要变化：

- 目标目录结构已落地：新增 `app.py`、`config.py`、`formats.py`，并把 I/O、image、geometry、detection、diagnostics、export、regression 拆成对应包入口。旧 `x5crop/core.py` 兼容层已移除。
- 新增 `x5crop/policies/` 包，公共接口在 `base.py`，注册入口在 `registry.py`，并为 `135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66`、`120-67` 各保留独立 policy 模块。
- 每个 `DetectionPolicy` 都显式包含 count、outer、separator、content、frame-fit、gate、scoring、selection、postprocess、output 和 diagnostics policy。`120-66/full` 与 `120-66/partial` 的宽黑条语义在 policy 层分开描述。
- `DetectionPolicy` 新增 detector kind 和 partial-holder policy：`135-dual` 通过 `dual_lane` detector kind 进入专用检测路径，unsupported partial 通过 `review_only` 表达；partial safe extra frames 的 wide-like gap、leading-content 和 frame-content 检查统一收敛到 partial-holder policy。
- half 的 wide-geometry / stable-grid 支持现在通过 separator geometry support modes 启用，仍只由 half full policy 打开，不向其它 format 自动推广。
- `x5crop/io.py`、`x5crop/geometry.py` 和 `x5crop/regression.py` 已迁移为 `x5crop/io/tiff.py`、`x5crop/geometry/core.py` 和 `x5crop/regression/compare.py`，包入口继续提供清晰导出。
- detection 层新增 `context.py`、`outer.py`、`separator.py`、`content.py`、`candidates.py`、`scoring.py`、`gates.py`、`selection.py` 和 `schema.py`，将外框候选、证据、候选、评分、gate、选择和报告 schema 的调试入口分开。
- `scoring.py`、`gates.py` 和 `selection.py` 现在承载真实实现，而不是只从 `pipeline.py` re-export：候选支持分数、half geometry support、separator hard-evidence gate、candidate rank 和最终 selection competition 已迁出 pipeline。
- `content.py` 现在承载真实 content evidence / content-primary candidate 实现：`content_evidence_detail()`、content profile runs、content mask outer 和 `content_detection_for_count()` 已从 `pipeline.py` 迁出。
- `outer.py` 现在承载真实 outer proposal 实现，而不是只做 re-export：`OuterProposalStrategy`、policy strategy planning、floating outer、edge-anchor outer、separator-first / separator-geometry outer 和 120-66 dark-band outer proposer 已迁出 pipeline。report/detail 中的 outer strategy 名称同步收敛为 `content_outer`、`edge_anchor_outer`、`separator_outer`、`separator_geometry_outer`、`dark_band_outer`、`content_aligned_retry`、`format_geometry_retry` 和 `short_axis_retry`。
- `candidates.py` 现在承载独立候选 helper：count planning、wide retry 判断和 candidate rank helper 已迁出 pipeline，并通过 policy 读取当前 format / strip-mode 的 count 计划。
- `separator.py` 现在承载 120-66 dark-band gap evidence helper，`dark_band_gaps_for_outer()` 已从 pipeline 迁出。
- detection runtime 现在从 `DetectionPolicy` 取得 full / partial count 计划、outer proposal strategy、dark-band 开关、separator gate mode、partial safe gate 约束、candidate selection 参数和 postprocess policy，保留 V4.5.4 的实际输出行为。
- gate policy 命名进一步收敛：runtime 通过 `SeparatorGatePolicy.profile` 和显式阈值读取 separator gate，不再让 detection 主流程直接读取 `score_gate_135_*` 或 `separator_gate_mode` 作为行为入口；旧 `FormatTuning` 字段仅作为 policy adapter 来源保留。
- selection policy 从 half 专用语义收敛为通用 content-mismatch review
  candidate preference；当前仍只有 half policy 开启。
- frame-fit format branching 迁入 `DetectionPolicy.frame_fit`，`geometry/core.py` 的旧 `frame_fit_policy(fmt, strip_mode)` 仅保留为兼容 adapter；新的 detection 路径向 geometry 传入 policy frame-fit 参数。
- 新增 `SeparatorGeometrySupportPolicy`，把 half full 的 `wide_geometry` / `stable_grid` 支持改成通用 capability；默认 off，当前只由 half full policy 开启，runtime 不再调用 half 命名的 support helper。
- 新增 `SeparatorEdgePairPolicy`，runtime 调用 `refine_gaps_by_edge_pairs()` 时从 `DetectionPolicy.separator.edge_pair` 传入 edge-pair 参数；`edge_pair_params_for_format()` 继续作为 geometry fallback / legacy adapter。
- 新增 `DarkBandOuterPolicy`，把 120-66 dark-band outer / gap helper 的阈值、宽度、pair spacing、source count、candidate count 和 full selection 开关收进 policy；默认 off，当前只给 120-66 full / partial conditional。
- `DiagnosticsPolicy.overlap_bleed_risk` 接管 postprocess overlap bleed 诊断开关，替代 postprocess 里的 partial / half / 120 硬编码判断。
- `DetectorPolicy.dual_lane` 预留 lane count、lane format 和 unsupported partial reason；135-dual full / partial 仍分别通过 `dual_lane` / `review_only` detector kind 进入。
- partial-holder policy 现在显式描述 66 partial 的 strict holder 条件，包括 wide-like gaps、leading content、frame content、hard/equal gap、width CV、joint/content/geometry score 和逐格内容阈值；half / xpan / 645 继续使用轻量默认配置。
- `dual_lane.py`、`partial_holder.py` 和 `outer_retry.py` 已从 pipeline 中拆出 135-dual detector、partial-holder gate helper、outer alignment / retry / fallback 逻辑，使 `pipeline.py` 更接近 orchestration。
- `common.py` 的重力井已开始拆分：domain models 迁入 `domain.py`，format specs 迁入 `format_specs.py`，runtime config/cache 迁入 `runtime.py`；`common.py` 继续 re-export 以保护旧 import。
- `cli.py`、`workflow.py`、`reports.py`、`debug/render.py` 和 `detection/pipeline.py` 已清理为显式导入，不再使用 `from ... import *`。
- 新增 `workflow.py`，把原先放在 CLI 里的单文件处理、报告复用、deskew、检测、postprocess、导出、Debug Analysis 和并行处理编排搬到 workflow 层；`cli.py` 继续负责参数解析、启动摘要和终端进度。
- 选中的 detection 会在 report detail 中写入 `policy`；CLI 启动摘要会显示当前 policy id。Debug Analysis 保持三栏图面，只显示 Original gray、Debug boxes 和 Separator evidence。
- `split_report.jsonl` 每行新增顶层带 `schema_version` 的 `report_schema`，固定包含 `result`、`selected_candidate`、`candidate_table`、`policy`、`evidence`、`gates`、`postprocess` 和 `output`，同时保留旧字段以便回归对比和旧报告复用。
- 新增开发者架构地图（后来在 V4.7 迁移为根目录 `ARCHITECTURE.md`），并新增 `python3 -m x5crop.regression.golden --candidate-root <candidate-root>` 用于把候选报告和本地 V4.5.4 golden reports 按核心字段统一比较。
- CLI 启动摘要会显示当前 policy id，例如 `policy: 120_66_partial`。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/io/*.py x5crop/geometry/*.py x5crop/image/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/diagnostics/*.py x5crop/export/*.py x5crop/policies/*.py x5crop/regression/*.py` 通过。
- `Test/135` full、`Test/new_135` full、`Test/120/66` full / partial、`Test/120/67` full、`Test/半格/full` 和 `Test/半格/partial` 对比本地 V4.5.4 报告，在 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 上均为 0 core diff。
- outer proposer 真实迁移后，上述七组 golden comparison 在 `/private/tmp/x5_v46_outer_impl_*` 下重跑，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 仍全部为 0 core diff。
- candidates helper 迁移后，上述七组 golden comparison 在 `/private/tmp/x5_v46_candidates_split_*` 下重跑，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 仍全部为 0 core diff。
- `dark_band_gaps_for_outer()` 迁出 `separator.py` 后，`Test/120/66` partial 在 `/private/tmp/x5_v46_separator_split_66_partial` 下重跑，对 V4.5.4 partial baseline 的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 为 0 core diff。
- policy convergence cleanup 后，七组 golden reports 在 `/private/tmp/x5_v46_policy_converge_20260630_after_score_policy` 下重跑；`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 仍全部为 0 core diff。包含 `detail.policy` 和 `report_schema` 的完整字段 compare 有 196 个 metadata diff，原因是 V4.5.4 golden rows 缺少 V4.6 的 policy/report schema 元数据；没有裁切框、gap、状态或 confidence diff。
- policy 专用逻辑收敛审核后，七组 golden reports 在 `/private/tmp/x5_v46_policy_audit_20260630_final2` 下重跑；核心字段仍全部为 0 diff。包含 `detail.policy` 和 `report_schema` 的完整字段 compare 仍为 196 个 metadata-only diff，原因同上：V4.5.4 golden rows 缺少 V4.6 policy/report schema 元数据。

### V4.5.4

V4.5.4 是一个 120-66 宽黑条检测改进版。它把这次样片验证得到的规则固化为 format-specific 逻辑：66 的分隔条通常很宽，因此 partial / full 都应优先让宽黑条证据和 1:1 三格几何互相约束，而不是让 content-floating、旧 base outer 或弱 edge-pair 单独主导。

主要变化：

- 新增 `separator_dark_band_outer` 候选来源，用 120-66 的两条宽黑色分隔带和三张 1:1 画幅几何反推 outer。
- 120-66 partial 的 `partial_safe_extra_frames` 不再只看“有强分隔”。它现在要求至少两个 wide-like gap，并检查 content-floating outer 的前缘是否切进内容，以及三张 frame 的逐格 content evidence 是否稳定。
- 120-66 full 也可以使用宽黑条 outer 候选，但不继承 partial 的 extra-holder 容忍。只有当前 full outer 需要帮助，且宽黑条候选自身有正常内容支持、足够 hard gap、没有 equal gap 时，才允许接管。
- Debug / report 的 `outer_candidate_strategy` 会显示 `separator_dark_band_outer`，方便区分这类结果与普通 `separator_first_outer` / `content_floating_outer`。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/120/66` partial dry-run + Debug Analysis + diagnostics：16 ok / 0 failed / 16 approved / 0 review。`X5_test_51.tif` 从 `needs_review` 变为 `approved_auto`。
- `Test/120/66` full dry-run + Debug Analysis + diagnostics：16 ok / 0 failed / 16 approved / 0 review。相比上一轮 full 守卫测试，`X5_test_43.tif`、`X5_test_48.tif` 和 `X5_test_51.tif` 从 review 变为 pass；48 / 51 的旧 outer 内容形态异常由 `separator_dark_band_outer` 接管。
- 全量本地诊断已按命名规则重跑：full 输出目录使用 `4.5.4`，partial 输出目录使用 `4.5.4_partial`。结果为：`Test/135/4.5.4` = 48 ok / 43 approved / 5 review；`Test/new_135/4.5.4` = 4 ok / 4 approved / 0 review；`Test/120/66/4.5.4` = 16 ok / 16 approved / 0 review；`Test/120/66/4.5.4_partial` = 16 ok / 16 approved / 0 review；`Test/120/67/4.5.4` = 4 ok / 3 approved / 1 review；`Test/半格/full/4.5.4` = 10 ok / 10 approved / 0 review；`Test/半格/partial/4.5.4_partial` = 5 ok / 5 approved / 0 review。
- 本次全量诊断总计 103 张，221.31 秒，平均 2.15 秒/张。Codex 沙盒中 process workers 不可用，实际使用 thread workers。

### V4.5.3

V4.5.3 是一个窄修复版，目标是让半格 full 中已经满足宽分隔 + 稳定 grid 证据条件的样片正常通过，而不是放宽半格或其它 format 的整体 PASS 规则。

主要变化：

- 新增安全的 detail 数值读取 helper，避免 `width_cv=0.0` 这类有效数值被 Python 的 truthy / falsy 规则误当成缺失值。
- `half_wide_geometry_support` 和 `half_stable_grid_support` 现在能正确看到完全稳定的 frame width CV。
- `X5_00058.tif` 从 `needs_review` 变为 `approved_auto`，outer、frame boxes 和 gaps 不变。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/135` full 对比 V4.5.2 为 48 rows / 0 diff。
- `Test/半格/partial` 对比 V4.5.2 为 5 rows / 0 diff。
- `Test/半格/full` 对比 V4.5.2 只有 `X5_00058.tif` 的 status / confidence / review reasons 改变：`needs_review` 变为 `approved_auto`，裁切框和 gap 结果没有 diff。

### V4.5.2

V4.5.2 是 V4.5.1 之后的结构收敛版。它继续整理模块职责，不改变检测阈值，也不主动改变 PASS / REVIEW 判断。

主要变化：

- 把只读诊断计算从 `debug/render.py` 移入 `detection/diagnostics.py`。诊断仍然服务 Debug Analysis 和 postprocess，但不再让 detection 后处理反向依赖 Debug UI。
- 新增 `constants.py`，集中管理 analysis source、gap method 和主要 review reason 字符串，减少同一语义在不同模块里手写字符串。
- `policy.py` 直接从 `common.py` / `geometry.py` 暴露 policy 和 frame-fit 入口，不再绕回 `core.py` 兼容导出层。
- `detection/models.py` 直接从 `common.py` 导出数据模型。
- 移除 `debug/render.py` 对 detection pipeline 的整包导入，让 Debug 渲染层依赖更窄。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.5.2`。
- 以 V4.5.1 为基线、`--deskew off` dry-run 对比：`Test/135` full、`Test/120/66` partial、`Test/120/67` full、`Test/半格/full`、`Test/半格/partial` 均保持 0 diff。

### V4.5.1

V4.5.1 是 V4.5 之后的结构收敛版。它的重点不是改变检测阈值，而是把已经稳定下来的检测层次整理成更容易维护的形状。

主要变化：

- 新增只读 policy view 分组，让 `FormatTuning` 里已经存在的参数可以按 outer、content、separator、grid、scoring、calibration、partial、diagnostics、debug 和 deskew 等职责查看。
- 把检测完成后的 content evidence、outer/content alignment、outer retry、review gate、output bleed、edge protection 和 diagnostics attach 从 CLI 移入 `detection/postprocess.py`。
- 把每个 count 的候选生成拆成 `calibrated_candidates_for_count()`，把最终候选排序拆成 `select_detection_candidate()`，让主入口 `choose_detection()` 更像调度层。
- `separator_hard_evidence_ok()` 内部分出 135、half 和 hard-required gate helper，方便以后继续按 format 调 gate，而不让一个函数继续膨胀。
- 收敛 active 代码里的旧兼容别名和手写 `analysis_source` 字符串。
- Debug Analysis 新增 Decision summary 面板，集中显示脚本版本、PASS/REVIEW、confidence、format、strip、count、outer strategy、analysis source、auto gate、gap 证据和 review reasons。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.5.1`。
- 以 V4.5 为基线、`--deskew off` dry-run 对比：`Test/135` full 为
  48 rows / 0 diff；`Test/120/66` partial 为 16 rows / 0 diff；
  `Test/120/67` full 为 4 rows / 0 diff；`Test/半格/full` 为
  10 rows / 0 diff；`Test/半格/partial` 为 5 rows / 0 diff。

### V4.5

V4.5 是 policy 架构整理版。它不主动放宽 PASS 规则，也不把更多 format 推进自动通过；主要目标是把 V4.4 系列积累的 outer proposal、separator geometry、partial 容错和 gate 命名整理清楚。

主要变化：

- 可信分隔条反推 outer 的命名收敛为 `separator_geometry_*`。这条能力的本质是“用可信分隔条 + count + format aspect 反推 outer 候选”，不再写成 partial 专用概念。
- 新增 `separator_geometry_outer_full_mode` / `separator_geometry_outer_partial_mode`。当前只有 `120-66 partial` 设为 `conditional`；其它 format 默认 `off`，后续需要样片验证后再逐个打开。
- 抽出共用的 `collect_separator_outer_bands()` 和 `separator_outer_band_sequences()`，让 `separator_first_outer_candidates()` 和 `separator_geometry_outer_candidates()` 共享黑色分隔带搜索、排序和组合逻辑。
- report/detail 新增 `outer_candidate_strategy`，候选列表也标注 strategy，方便看出结果来自 `base_outer`、`content_floating_outer`、`long_axis_edge_anchor_outer`、`separator_first_outer` 还是 `separator_geometry_outer`。
- 将历史评分字段命名收敛为更清楚的 gate 语义。阈值不变。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/135` full dry-run 对比 V4.4.6：48 unique rows / 0 diff。
- `Test/120/66` partial dry-run 对比 V4.4.6：16 unique rows / 0 diff；`X5_test_56.tif` 仍使用 `separator_geometry_*` outer candidate，`X5_test_51.tif` 仍保持 REVIEW。
- `Test/半格/full` 对比 V4.4.4：10 rows / 0 diff。
- `Test/半格/partial` 对比 V4.4.4：5 rows / 0 diff。
- `Test/120/67` 对比既有 V4.4.2 baseline：status / confidence / outer / frame / gap 无差异；只有一个历史 review reason 名称从 `v2_auto_gate_not_satisfied` 归一化为 `auto_gate_not_satisfied`。

### V4.4.6

V4.4.6 增加通用的 separator-geometry outer candidate，并暂时只在 `120-66` policy 中开启。它不修改已经选出的结果，而是在常规 partial 候选进入最终选择前，额外尝试一个由可信分隔条反推出来的 outer 候选。

触发条件很窄：

- 当前只在 `120-66` policy 中开启；其它 format 默认关闭，之后可以按样片验证后再打开。
- 只适用于 `partial`。
- 只适用于 count=3。
- 只在常规最佳候选的 frame aspect 明显可疑时尝试，避免污染已经稳定的 separator-first 结果。
- 候选必须由足够强的黑色分隔带组合推导，并满足 3 张 1:1 画幅加分隔总宽度的几何关系。

主要变化：

- 对常规 outer 候选判断不好的 66 partial 样片，先从整张长图的可信宽分隔带中挑出两个内部分隔，再按 3 张 6x6 画幅反推 outer。
- 新 outer 只是一个候选，仍然必须回到原有 separator / edge-pair / content / scoring / review-gate 链路中竞争。
- 不提高 confidence，不跳过 review gate，也不会把证据不足的样片强行推过；当前 `X5_test_51.tif` 仍保持 REVIEW。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/135` full dry-run 对比 V4.4.6 既有基线：48 rows / 0 diff。
- `Test/120/66` partial dry-run 对比 V4.4.5：16 rows；只有 `X5_test_56.tif` 切换到新的 `separator_geometry_*` outer 候选，`status`、`confidence`、`review_reasons` 均不变，仍为 15 个 `approved_auto` / 1 个 `needs_review`。

### V4.4.5

V4.4.5 是一次回溯性的默认输出目录改名。默认输出目录从旧的
`split_output/` 改为更明确的 `x5_crop_output/`。

主要变化：

- 当前源码的默认输出目录改为 `x5_crop_output/`。
- CLI help 从 `default input/split_output` 改为
  `default input/x5_crop_output`。
- README、快速启动文档、CHANGELOG 和 AGENTS 里的默认输出路径说明同步更新。
- 本地可见 archive 快照中的对应默认输出目录和 CLI help 也同步更新。
- GitHub 上既有 release zip 资产也已回溯刷新：v4.2.8、v4.1.3、
  v4.0.1、v4.0、v3.6.2、v3.3.1。

验证：

- 除本节和 handoff 中解释“旧名改名”的历史描述外，当前可见源码、用户文档和本地 archive 快照的运行路径均已改为 `x5_crop_output`。
- 重新下载检查所有既有 GitHub release zip：旧目录名 `split_output` 为
  0 命中，包内已包含 `x5_crop_output`。

### V4.4.4

V4.4.4 是 V4.4.3 之后的命名清理和诊断可读性修复版。目标是把 active 代码里的历史版本命名改成和当前检测逻辑一致的语义命名，并修复 V4.4.3 中“50px bleed 已触发但普通 Debug Analysis 不一定画出诊断 tick”的解释断层。

命名规则：

- 候选级评分和 auto gate 结果统一叫 `candidate_decision`。
- 多候选排序和竞争摘要统一叫 `candidate_competition`。
- 诊断报告统一叫 `diagnostics`。
- 主检测入口叫 `choose_detection()`。
- 候选校准入口叫 `calibrate_candidate_decision()`。
- review reason 不再带历史版本号，例如 `auto_gate_not_satisfied`、`candidate_competition_uncertain`。

主要变化：

- active 代码中移除 `v2_*` 和 `diagnostics_v3_6` 命名。
- 移除未使用的 `partial_content_min_count_35mm` / `partial_content_min_count_small` policy 字段。
- `separator_outer_band_sequences()` 的 2-gap top-k 排序加入 spacing geometry error，不再只按 band 分数截断。
- `overlap_bleed_risk_detail()` 会保留触发 output-only 50px bleed 的 gap diagnostics；普通 Debug Analysis 即使没有开启 `--diagnostics`，也可以用 cyan tick 解释 overlap-risk bleed。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.4.4`。
- 全量 `Test/135` 对比 V4.4.3：48 行，只有 5 个 REVIEW 文件的 review reason 从旧的版本号命名改为 `auto_gate_not_satisfied`；status / confidence / outer / frame_boxes / gaps 不变。
- 全量 `Test/半格/full` 对比 V4.4.3：10 行，0 diff。
- 全量 `Test/半格/partial` 对比 V4.4.3：5 行，0 diff。
- `Test/120/66` partial 对比 V4.4.3：16 行，只有 `X5_test_51.tif` 的 review reason 从旧的版本号命名改为 `auto_gate_not_satisfied`；status / confidence / outer / frame_boxes / gaps 不变。

### V4.4.3

V4.4.3 是 V4.4.2 之后的维护噪音清理和局部性能优化版。它不改变 135 full 的检测输出，同时把之前只读诊断里已经能看见的叠片 / 连续内容风险，用到 partial、half 和 120 的输出安全 bleed 上。

主要变化：

- 清理未调用的旧常量和旧函数接口，减少后续维护时误读旧逻辑的可能。
- `content_detection_for_count()` 现在复用同一张图、同一 format 的 content mask / expanded bbox 中间结果，避免 partial 多 count / 多 offset 时反复算同一层内容框。
- `separator_first_outer_candidates()` 的 band sequence 搜索对 1-gap / 2-gap 场景走专门快速路径，并对 2-gap pair 做 top-k 截断，减少 66 partial 这类场景中的无效组合。
- Debug Analysis 的 original-gray panel 复用 label 后 preview，减少同一张图内重复拼装。
- half full 的普通 equal-first + wide-retry 路径显式记录为 `half_full_equal_first`，保持原行为，但让分支语义更清楚。
- partial、half 和 120 路径的诊断叠片风险现在会触发 output-only long-axis bleed=50px。这个变化只影响最终输出框 / 报告 frame_boxes / Debug Analysis 色块，不参与检测评分，也不改变 PASS/REVIEW。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.4.3`。
- `Test/135` full dry-run 对比 V4.4.2：48 rows / 0 diff。
- `Test/半格/full` dry-run 对比 V4.4.2：仅 `X5_00050.tif` 的 `frame_boxes` 因 output-only overlap bleed 从 20px 提到 50px 而长轴外扩；status / confidence / outer / gaps 不变。
- `Test/半格/partial` dry-run 对比 V4.4.2：仅 `X5_00055.tif` 的 `frame_boxes` 因 output-only overlap bleed 外扩；status / confidence / outer / gaps 不变。
- `Test/120/66` partial auto dry-run 对比 V4.4.2：仅 `X5_test_51.tif` 的 `frame_boxes` 因 output-only overlap bleed 外扩；status / confidence / outer / gaps 不变。

### V4.4.2

V4.4.2 是 V4.4.1 之后的保守性能优化和旧逻辑清理版。目标是减少 partial / Debug / enhanced separator 路径的重复计算，同时保持现有检测输出不变。

主要变化：

- 移除 content-only partial 的旧自动通过接口。content candidate 仍可作为候选参与分析，但不会单独触发 auto gate；partial 自动通过继续依赖 `partial_safe_extra_frames` / separator evidence 语义。
- partial 下如果同一 count 已经出现 `partial_safe_extra_frames` 自动通过的 separator candidate，会跳过对应 offset 的 content candidate，并且不再继续尝试更低 count。这个策略保留同一 count 的其它 offset，避免过早错过同 count 的更好位置。
- separator-first outer proposal 不再先枚举所有 band 组合再过滤，而是在组合生成阶段就剪掉 spacing 明显不合格的分支。候选集合保持一致，只减少无效组合。
- enhanced separator merge 增加精确缓存。触发条件和接受阈值不变，只复用相同 outer / gaps / pitch / format 的计算结果。
- Debug / diagnostics 的 nearby-separator 诊断增加精确缓存，减少 Debug Analysis 或诊断叠加重复读取同一 profile。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.4.2`。
- `Test/135` full dry-run 对比 V4.4.1：48 rows / 0 diff。
- `Test/半格/partial` dry-run 对比 V4.4.1：5 rows / 0 diff。
- `Test/120/66` partial auto dry-run 对比 V4.4.1：16 rows / 0 diff。
- `Test/120/67` full dry-run 对比 V4.4.1：4 rows / 0 diff。
- `Test/半格/full` dry-run 对比 V4.4.1：10 rows / 0 diff。

### V4.4.1

V4.4.1 是 V4.4 之后的结构清理版，目标是保留 V4.4 已经验证过的输出，同时让 full / partial 的检测职责更清楚，减少未来调参时的隐性冲突。

主要变化：

- partial 的 `separator-first` 默认从 `always` 收回到 `fallback`。`120-66` 和 `xpan` 因为更常见“不铺满片夹但仍是正常三张”的情况，继续保留更积极的 partial `separator-first`。
- content-only partial 不再单独自动通过。内容证据仍参与 joint score 和 validation，但自动通过必须回到 `partial_safe_extra_frames` / separator evidence 语义，避免只靠内容候选蒙对。
- floating outer 相关代码命名从 `floating_full_*` 清理为更通用的 floating outer，因为它现在同时服务 full 和 partial。
- long-axis edge-anchor 的 partial 贴边判断改为按每个候选 outer 的局部 content bbox 计算，不再用整张扫描的全局 content bbox 直接判断所有候选。
- `135-dual` 显式关闭无效的 partial / floating / wide-retry policy，避免配置看起来支持但真实路径其实走专用逻辑。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.4.1`。
- `Test/135` full dry-run 对比 V4.4：48 rows / 0 diff。
- `Test/半格/partial` dry-run 对比 V4.4：5 rows / 0 diff，仍为 5 个 `approved_auto` / 0 个 `needs_review`。
- `Test/120/66` partial auto dry-run 对比 V4.4：16 rows / 0 diff，仍为 15 个 `approved_auto` / 1 个 `needs_review`。
- `Test/120/67` full dry-run 对比既有 V4.3 基线：4 rows / 0 diff。
- `Test/半格/full` dry-run 对比既有 V4.3 基线：10 rows / 0 diff。

### V4.4

V4.4 把 V4.2 / V4.3 中为了处理“不铺满片夹”而加入的 outer proposal 能力重新分配到更合适的模式里。

新的语义：

- `full`：完整片条 / 铺满片夹 / 固定张数。它继续使用普通 outer、separator / edge-pair、wide separator、content validation、format geometry、outer/content alignment 等对完整片条有帮助的逻辑。
- `partial`：片头、片尾、局部片条，或有效照片区域不铺满片夹、不居中、靠近长轴一端开始的情况。它现在可以使用 floating outer、separator-first outer、wide retry 和条件 long-axis edge-anchor fallback，再交给 V4.3.1 的 `partial_safe_extra_frames` gate 判断是否可以自动通过。

具体整理：

- `120-66` full 不再启用 `floating_full_outer`，也不再把 `long_axis_edge_anchor` 作为 always 逻辑；`separator-first` 从 always 降为 fallback。
- `xpan` full 关闭 long-axis edge-anchor；xpan partial 仍可在 fallback 中使用它。
- partial 下的 `separator-first` 可以对任意 count > 1 生成候选，不再只限 full default count。
- partial 下启用 `floating_partial_*` outer candidate，用于有效照片区域在长图中不居中或没有铺满片夹的情况。
- partial 下启用 wide retry，让较宽片距也有机会成为分隔证据。
- partial 下的 long-axis edge-anchor 只作为 fallback，并且要求内容中心明显偏向长轴一端；内容位于中间时不生成 edge-anchor，避免伤害半格 partial 55 这类中间开始的样片。
- `120-66` 和 `xpan` 的 partial auto count 现在可以包含 default count=3，因为它们可能是“正常三张但不铺满片夹”。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed。
- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.4`。
- `Test/135` full dry-run 对比 V4.3：48 rows / 0 diff。
- `Test/半格/partial` dry-run 对比 V4.3.1：5 rows / 0 diff。
- `Test/120/66` partial auto dry-run：15 个 `approved_auto` / 1 个 `needs_review`。其中多数通过 `separator_first_*` 或 `floating_partial_*` outer candidate，`X5_test_51.tif` 仍因 120 分隔证据不足进入 REVIEW。
- `Test/120/66` full dry-run：13 个 `approved_auto` / 3 个 `needs_review`。这批样片本身更接近“不铺满片夹”的 partial 语义，因此 full 不再作为它们的主要评估模式。

### V4.3.1

V4.3.1 专门调整 partial mode 的自动通过语义。此前 partial mode 会因为 `partial_strip_count_candidate` 和 `separator_hard_evidence_weak` 很容易进入 REVIEW，即使 Debug Analysis 里真实照片已经被稳定框住。这对半格 partial 特别明显：多切出几张空片夹区域的成本很低，但旧规则仍然过于保守。

新的 `partial_safe_extra_frames` gate 只在 partial 候选上生效：

- 只接受 separator candidate，不让 content-only 候选靠猜测自动通过。
- 要求 content evidence 为 `ok`。
- 要求 frame geometry 稳定，width CV 在 policy 限制内。
- 要求没有 `equal` gap；允许一部分 `grid` 作为模型补位。
- 要求至少有少量 hard separator / edge / wide evidence 支撑。
- 如果内容冲突、宽度不稳或其它 hard review reason 存在，仍然 REVIEW。
- 对 partial 的候选竞争惩罚做了例外：多个安全 partial count 很接近时，不再因为 count 竞争本身把结果压回 REVIEW。

这条规则的实际含义是：partial mode 可以“宁可多切几张空片夹，也不要裁坏真实照片”。它推广到所有 format 的 partial，但参数集中在 `FormatTuning` 里，后续可以按 135 / half / xpan / 120 单独收紧或放宽。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed。
- `Test/半格/partial` dry-run + Debug Analysis + diagnostics：5 个 `approved_auto` / 0 个 `needs_review`。
- `Test/135` full dry-run 对比 V4.3：48 rows / 0 diff。

### V4.3

V4.3 把 V4.2 系列新增的 full-mode outer 逻辑整理为统一的 outer proposal layer，而不是继续把新逻辑作为分散的 retry 插进去。

结构上，full-mode 的候选来源现在按同一层处理：

- normal outer：常规外框候选。
- floating full：有效 full strip 可以在长图内浮动，不要求居中或铺满整张扫描。
- separator-first：先找可信黑色分隔带，再用 format count / aspect 反推 outer。
- long-axis edge-anchor：新增。用于 full 模式下有效片条不居中，但沿长轴贴近一端开始的情况。横向长图对应左端 / 右端；纵向长图在 work orientation 内等价处理。

这些 proposal 都只负责生成 outer candidate。最终能不能自动裁切，仍然由原有统一链路决定：

```text
outer candidate
  → separator / edge-pair / wide-separator
  → frame boxes
  → content evidence
  → format geometry
  → candidate calibration
  → review gate
```

format policy：

- `120-66`：long-axis edge-anchor 为 `always`，因为 66 full 的有效三张 6x6 很可能不铺满整张扫描，也可能贴近长轴一端。
- `xpan`：long-axis edge-anchor 为 `fallback`。XPAN 的物理场景和 66 类似，也可能因为胶片无法铺满片夹而贴近长轴一端；但目前缺少样片，先保守接入。
- `135`、`half`、`120-645`、`120-67`、`135-dual`：暂时关闭 long-axis edge-anchor。`half` 验证中发现 `X5_00063` 会被纯 equal 的 edge-anchor fallback 抢成 REVIEW；其它格式先避免在没有明确样本收益前引入额外候选。

安全规则：

- long-axis edge-anchor 不提高 confidence，不直接让结果 PASS。
- long-axis edge-anchor 的 separator candidate 如果没有任何 hard separator，会被 `long_axis_edge_anchor_separator_weak` 压回 REVIEW，避免纯 equal / grid 的模型候选自动通过。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/120/66` dry-run 对比 V4.2.9：16 行，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 为 0 diff。
- `Test/半格/full` dry-run 对比 V4.2.7：10 行，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 为 0 diff。

### V4.2.10

V4.2.10 是一次风险可控的缓存优化，不改变检测策略：

- `AnalysisCache` 现在缓存全图 separator evidence，供全图 Debug Analysis evidence 和 enhanced separator full profile 复用。
- 全图 separator profile 按 format 复用，减少 separator-first、wide retry、Debug Analysis 在同一张图上重复计算完整扫描 profile。
- 内容 run 按 `(format, count, outer)` 复用，避免 content candidate 多次重复扫描同一段 content evidence。
- 内容证据评分按 outer / frame 组合复用，outer/content alignment 按 outer / gap 组合复用。它们只在完全相同 candidate 上命中，并在读取时深拷贝 detail，避免报告或 Debug 后续写入污染缓存。
- separator-first outer candidates 按 format / count / strip mode / base outer candidates 复用，主要服务 120-66，也覆盖其它启用 separator-first fallback 的 format。
- Debug Analysis 的 Original gray、Separator evidence、Content evidence 预览图会在同一次渲染里复用基础缩略图；每次叠加标记前都会复制缓存图，避免 overlay 污染后续面板。
- 这不是 120-66 专用优化，而是所有 format 共用的缓存入口。120-66 / 120 / partial / Debug Analysis 这类候选多、全图证据用得多的场景收益更明显。
- 本版刻意不做相近 outer 的近似缓存、不做 edge profile 大范围切片缓存，也不缓存 deskew 中间结果；这些方向可能有收益，但需要更细回归验证。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- `Test/120/66` dry-run 结果为 9 个 `approved_auto` / 7 个 `needs_review`，与 V4.2.9 的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 对比为 0 diff。
- 单张 120-66 Debug Analysis smoke test 正常生成 JPG。

### V4.2.9

V4.2.9 继续聚焦 120-66 full。根据本地 `Test/120/66` 的人工复核，`45 / 46 / 49 / 50 / 52 / 54` 的红框检测较准确，其它样本即使 PASS 也有明显红框风险。因此本版先做两类保守改进：

- 120-66 full 在没有 `wide-separator` 支撑时，会要求普通 `edge-pair` 具备更高的最低质量。低质量 edge-pair 组合不再直接满足 auto gate。
- 66 的宽黑条仍作为合法分隔证据，但不放宽 separator-first outer 搜索范围，避免 outer 因全局宽黑条组合过度自由而漂移。
- Debug Analysis 的 `Separator evidence` 和 `Content evidence` 不再只显示 outer 内部；现在显示整张扫描证据，并叠加当前 outer / frame，方便检查 outer 外是否存在更合理的黑条或内容证据。

当前 `Test/120/66` V4.2.9 dry-run + Debug Analysis 输出在 `Test/120/66/4.2.9`。结果为 9 个 `approved_auto` / 7 个 `needs_review`：

- 保持 PASS 且属于人工标注准确组：`45 / 46 / 49 / 50 / 52 / 54`。
- 从 V4.2.8 的 PASS 压到 REVIEW：`44 / 47 / 51 / 53 / 55 / 56 / 58`。
- 仍然 PASS 但需要继续观察和后续优化：`43 / 48 / 57`。

### V4.2.8

V4.2.8 是启动器交互改进，检测逻辑不变。Mac / Windows 主启动器现在只在用户开启 partial mode 后追问 count：

```text
partial mode? [y/n, return=no]: y
partial count:
  return or auto = auto
  allowed: ...
count:
```

规则：

- 不开启 partial mode：不询问 count，继续使用所选 format 的 full count。
- 开启 partial mode：直接回车或输入 `auto` 表示自动判断张数。
- 开启 partial mode：输入允许范围内的数字，会把 `--count N` 传给脚本，固定局部片条张数。
- 输入不合法 count 时，启动器会重新询问。

验证：

- `bash -n X5_Crop_Mac.command` 通过。
- Mac 启动器 smoke test：输入 `half` / partial `y` / count `3` / debug `y` 后，启动器显示 `strip mode: partial`、`count: 3`，并调用脚本。项目根目录没有 TIFF，所以最终报 `No TIFF files found`，这是预期的 smoke-test 结果。
- Local ignored test copies were synced for `Test/135`, `Test/new_135`, `Test/120/66`, `Test/120/67`, and `Test/半格/full`.

### V4.2.7

V4.2.7 增加半格 full 的稳定 grid 支持。V4.2.6 后，`X5_00062.tif` 和 `X5_00063.tif` 的裁切框已经很好，但仍因为 hard/wide 数量不足、outer area 偏大和 `auto_gate_not_satisfied` 进入 REVIEW。新的 `half_stable_grid_support` 不单独放宽 outer，而是承认一种更窄的半格 full 形态：

```text
真实 hard/wide 分隔只覆盖一部分
  +
grid 补齐全部 gap
  +
frame width 极稳定
  +
content support 正常
  +
没有 equal fallback
```

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/半格/full` dry-run + Debug Analysis 已输出到 `Test/半格/full/4.2.7`。
- `Test/半格/full` 结果：10 张，10 个 `approved_auto` / 0 个 `needs_review`。
- 相比 V4.2.6，仅 `X5_00062.tif`、`X5_00063.tif` 从 REVIEW 变为 PASS；它们的 outer、frame boxes 和 gaps 不变。
- `X5_00062.tif` 通过 `half_stable_grid_support`，4/11 个 hard/wide，7/11 个 grid。
- `X5_00063.tif` 通过 `half_stable_grid_support`，5/11 个 hard/wide，6/11 个 grid。

### V4.2.6

V4.2.6 继续优化半格 full。V4.2.5 已经让 59/60/61 通过，但 56/58 仍被闸门拦住，63 虽然保持 REVIEW，却显示了一个误导性很强的 content candidate。V4.2.6 做两处更贴近半格 full 的修正：

- `half_wide_geometry_support` 从“至少 80% wide/hard gap”改为“至少 60% wide/hard gap + no equal + frame width 稳定 + content support ok + 半格 wide joint score 下限”。这样 56/58 这类多数分隔明确、但仍有少量 grid 补位的半格 full 可以通过。
- 当 half full 的 content candidate 出现 `content_run_count_mismatch`，且存在较可信 separator candidate 时，REVIEW 展示优先选择 separator candidate。这样 63 继续 REVIEW，但 Debug boxes 不再显示之前那种明显错位的 content 切法。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/半格/full` dry-run + Debug Analysis 已输出到 `Test/半格/full/4.2.6`。
- `Test/半格/full` 结果：10 张，8 个 `approved_auto` / 2 个 `needs_review`。
- 相比 V4.2.5，新增通过：`X5_00056.tif`、`X5_00058.tif`。
- `X5_00050.tif`、`X5_00053.tif`、`X5_00054.tif`、`X5_00059.tif`、`X5_00060.tif`、`X5_00061.tif` 与 V4.2.5 保持稳定。
- `X5_00062.tif` 继续 REVIEW，因为只有 4/11 个 wide/hard gap。
- `X5_00063.tif` 继续 REVIEW，因为只有 5/11 个 wide/hard gap；但最终展示已从 content candidate 改为 separator candidate，避免误导人工复核。

### V4.2.5

V4.2.5 是半格 full 的保守宽分隔调参。用户把半格测试重新拆成 `full` / `partial` 后，`Test/半格/full` 中 56 之后的多张标准半格图仍进入 REVIEW。诊断显示主要原因不是肉眼不可见分隔，而是半格原路径会把 full 模式内部分隔退成 equal/grid；宽黑色片距没有被当成足够可靠的分隔证据。

这版只对 half full 做两处窄改动：

- 普通 half full 路径继续保留原有 equal/grid 行为，避免影响已经稳定的 50/53/54。
- 当普通路径没有通过时，wide retry 分支可以用 `wide-separator` 识别较宽黑色片距；只有 wide/hard gap 覆盖至少 80% 分隔、没有 equal fallback、frame 宽度稳定、内容支撑正常且 joint score 过阈值时，才通过 `half_wide_geometry_support` 自动裁切。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/半格/full` dry-run + Debug Analysis 已输出到 `Test/半格/full/4.2.5`。
- `Test/半格/full` 结果：10 张，6 个 `approved_auto` / 4 个 `needs_review`。
- 相比 V4.2.4，新增通过：`X5_00059.tif`、`X5_00060.tif`、`X5_00061.tif`。
- `X5_00050.tif`、`X5_00053.tif`、`X5_00054.tif` 与 V4.2.4 保持不变。
- `X5_00056.tif` 和 `X5_00062.tif` 已能看到部分 `wide-separator`，但 wide 数量不足，继续 REVIEW；`X5_00058.tif` 和 `X5_00063.tif` 仍是 content-only / content mismatch 形态，继续 REVIEW。

### V4.2.4

V4.2.4 是 V4.2.3 之后的行为保持清理，不改变检测结果，主要修掉 separator-first fallback 的两个维护风险：

- fallback 现在只构建 `separator_first_*` outer 候选。此前 fallback 会重跑一整轮普通 outer + separator-first outer 竞争；如果 separator-first 没有生成有效 outer，也可能出现解释噪音。现在没有 separator-first outer 时，不追加候选、不写 retry used，继续走原有 content / review 流程。
- `separator_first_outer_mode` 现在会校验为 `off` / `fallback` / `always`。如果未来拼写错误，会直接报出无效配置，而不是静默改变检测行为。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 对比 V4.2.3 baseline，全量 `Test/135`：48 行，0 diff。
- 对比 V4.2.3 baseline，全量 `Test/120/67`：4 行，0 diff。
- 对比 V4.2.3 baseline，全量 `Test/半格`：15 行，0 diff。
- 对比 V4.2.2 baseline，全量 `Test/120/66`：16 行，0 diff。

### V4.2.3

V4.2.3 把 V4.2.2 的 120-66 separator-first outer proposal 推广成 format-aware 框架。核心顺序保持不变：

```text
先从全局 separator profile 找可信黑色分隔带
  ↓
按当前 format 的 count 和 frame aspect 挑选可解释的内部分隔组合
  ↓
用 N 张同规格画幅 + 分隔总宽度反推 outer
  ↓
交回原有 separator / edge-pair / scoring / review gate
```

这次不是把 66 的参数直接套给所有格式。V4.2.3 给每个 format 提供独立 policy 入口：

- `120-66` 保持 `always`，因为当前 66 full 的关键问题就是有效 outer 不一定铺满整张扫描，分隔优先路径是主策略。
- `135`、`half`、`xpan`、`120-645`、`120-67` 使用 `fallback`，只有常规 separator / wide retry 候选没有满足自动通过条件时才尝试 separator-first outer proposal。
- `135-dual` 暂不启用，因为双条 135 是上下 / 左右双 lane 的特殊逻辑，不能直接用单条 full-strip outer 模型解释。

这样做的目标是把“可信分隔 + format 几何反推 outer”变成可继续调参的共同框架，同时避免它抢走已经可靠的正常检测路径。尤其是 120-67：实测把 separator-first 强行改成 always 会得到更激进、更窄的 outer，但肉眼并不明显更好，所以 V4.2.3 保持 fallback 模式。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/120/66` full dry-run：16 张，16 个 `approved_auto` / 0 个 `needs_review`。
- 对比 V4.2.2 baseline，全量 `Test/135`：48 行，0 diff。
- 对比 V4.2.2 baseline，全量 `Test/120/67`：4 行，0 diff。
- 对比 V4.2 baseline，全量 `Test/半格`：15 行，0 diff。

### V4.2.2

V4.2.2 继续解决 120-66 full 的核心问题：66 的三张照片不一定铺满整条扫描，也不一定居中，但两条黑色内部分隔往往非常清晰。V4.2.1 已经允许 outer 浮动，但仍然主要是“先有 outer，再在预测位置附近找 gap”。V4.2.2 增加了相反方向的 66 专用 proposal：

```text
全局 separator profile 找强黑色分隔带
  ↓
挑出两条间距接近 6x6 画幅短轴的内部分隔
  ↓
按 3 张 1:1 frame + 两条分隔宽度反推 outer
  ↓
交回原有 separator / edge-pair / scoring / review gate
```

这个分支只在 `120-66`、`full`、`count=3` 时启用。它不会让 content-only candidate 自动 PASS，也不会绕过现有 hard separator evidence gate。对 separator-first candidate，会允许一个有限的宽分隔检测 override，以兼容 66 里肉眼清晰但比普通窄黑条更宽的片距；包含 `wide-separator` 的结果仍受宽分隔置信度上限约束。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/120/66` full dry-run：16 张，16 个 `approved_auto` / 0 个 `needs_review`。
- `X5_test_45.tif`、`X5_test_50.tif`、`X5_test_54.tif` 均从 content-only REVIEW 转为 `separator_candidate`，gap methods 为 `detected` / `edge-pair` / `wide-separator` 组合。
- 对比 V4.2.1 baseline，全量 `Test/135`：48 行，0 diff。
- 对比 V4.2.1 baseline，全量 `Test/120/67`：4 行，0 diff。

### V4.2.1

V4.2.1 专门重做 120-66 full 模式的 outer 候选生成。此前 66 的主要问题不是短轴微调，而是要裁切的三张 6x6 往往没有铺满整张扫描长图，也不一定居中；如果沿用“整条长图就是有效 outer”的假设，后续分隔、等分和画幅拟合都会被错误 outer 带偏。

V4.2.1 的处理方式是把 120-66 full 当作新的检测目标，而不是继续保护旧版 66 输出：

- count 仍固定为 3，partial mode 仍然单独处理。
- 先保留既有 outer 候选，再为 120-66 full 增加 floating full outer candidates。
- floating outer 用 `3 * 1:1 frame + separator total` 的几何比例作为目标，而不是假设照片铺满或居中在整张扫描里。
- 候选会围绕原 outer 和内容 bbox 的左侧、右侧、中心生成有限数量的外框，再交给现有 separator / edge-pair / scoring / review gate 流程竞争。
- 没有可靠分隔证据的 content-only candidate 仍不会自动 PASS。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 全量 `Test/120/66` full dry-run：16 张，13 个 `approved_auto` / 3 个 `needs_review`；仍进 REVIEW 的文件是 `X5_test_45.tif`、`X5_test_50.tif`、`X5_test_54.tif`。
- 对比 V4.2 baseline，全量 `Test/135`：48 行，0 diff。
- 对比 V4.2 baseline，全量 `Test/120/67`：4 行，0 diff。

### V4.2

V4.2 建立了一个统一 full-format geometry model，用同一套公式解释 135、half、xpan、120-66、120-645、120-67 这类 full strip：

```text
outer_long / outer_short = count * frame_aspect + separator_total / outer_short
```

这个模型会写入 report detail，并参与一个保守的阶段 C outer correction retry。它只在以下条件同时满足时尝试移动 outer：

- full strip，且 count 是该 format 的 full count；
- 所有内部分隔都是 hard separator / edge-pair / wide-separator，并且有可测量宽度；
- 当前 outer 多出来的长轴比例不能被已测量 separator total 解释；
- 根据 separator 宽度和 format frame aspect 反推的新 outer 更接近几何模型；
- 修正幅度很小，且不会裁掉 content bbox。

这一步的目标是先把“不同画幅其实共享同一个几何骨架”的框架搭起来，并允许非常窄的 active correction。当前测试集里它没有触发输出变化，说明规则足够保守；120-66 中那些 REVIEW 图主要缺少可靠 hard gap，因此不会被这个阶段 C 规则强行修正或推成 PASS。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 对比 V4.1.3 baseline，全量 `Test/135`：48 行，0 diff。
- 对比 V4.1.3 baseline，全量 `Test/半格`：15 行，0 diff。
- 对比 V4.1.3 baseline，全量 `Test/120/66`：16 行，0 diff。
- 对比 V4.1.3 baseline，全量 `Test/120/67`：4 行，0 diff。
- `Test/new_135` 4 张宽片距样本在 V4.2 下保持 4 个 `approved_auto` / 0 个 `needs_review`。

### V4.1.3

V4.1.3 是 V4.1.2 之后的行为保持清理版，不以改变检测结果为目标。它主要整理前两轮审查指出的语义和维护问题：

- `score_hard_full_confidence_floor` 的角色从 `score_detection()` 移到 `calibrate_candidate_decision()`，并更名为 `calibrate_hard_full_confidence_floor`。它现在明确是 candidate 级别的置信度校准，而不是 separator 分数或几何分数的一部分。
- 120-66 / 120-67 / 120-645 的重复基础参数抽成共享 120 format policy helper，后续调 120 参数时更不容易出现分支漂移。
- 120-67 短轴 outer excess 触发条件从单纯阈值变成语义判断：需要 hard anchor 可靠，并且 content height 明确小于 outer，才进入短轴收紧 retry。
- CLI 里的两个 outer retry 路径合并为一个 outer correction proposal 入口，保持原来的优先级：先短轴 aspect retry，失败后才尝试 content-aligned retry。

验证：

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 与 V4.1.2 baseline 对比，全量 `Test/135`：48 行，`python3 -m x5crop.regression` 为 0 diff。
- 与 V4.1.2 baseline 对比，全量 `Test/半格`：15 行，0 diff。
- 与 V4.1.2 baseline 对比，全量 `Test/120/66`：16 行，0 diff。
- 与 V4.1.2 baseline 对比，全量 `Test/120/67`：4 行，0 diff。

### V4.1.2

V4.1.2 是一个只针对 120-67 短轴 outer 的窄修复。`Test/120/67/3.tif` 的两条分隔已经都是 `edge-pair`，问题不是分隔证据，而是初始 outer 的短轴上下留白偏多。V4.1.2 不新增检测算法，只把 120-67 的短轴 outer excess 判断调得更敏感，让它在 hard separator 可靠、content aspect 正常、短轴 content slack 明显偏大时，复用现有 `content_aligned_outer` retry 收紧短轴。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.1.2`。
- 只跑 `Test/120/67/3.tif`：保持 `approved_auto confidence=1.000`。
- 修复后 `3.tif` 的 outer 从 `top=1, bottom=4009` 收紧为 `top=68, bottom=3974`，两条 gap 仍为 `edge-pair`，`separator_hard_evidence.ok=True`。
- 这次按目标只验证 `3.tif`，没有做全量 135 / 120 回归。

### V4.1.1

V4.1.1 是一个只针对 120-67 宽分隔的窄修复。V4.1 中 `Test/120/67/2.tif` 的右侧分隔能被识别为 `edge-pair`，但左侧真实宽分隔被退回 `equal`，导致 hard separator evidence 不完整。V4.1.1 不改变默认窄分隔路径，只在普通 separator candidate 没过 auto gate 时，为 120-67 启用保守的 `wide-separator` retry，宽度上限为 `0.090 * pitch`。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.1.1`。
- 只跑 `Test/120/67/2.tif`：从 V4.1 的 `needs_review confidence=0.835` 变为 `approved_auto confidence=0.995`。
- 修复后 `2.tif` 的第一条 gap 为 `wide-separator`，第二条 gap 为 `edge-pair`，`equal_gaps=0`，`separator_hard_evidence.ok=True`。
- 这次按要求只验证 `2.tif`，没有做全量 135 / 120 回归。

### V4.1

V4.1 是一个面向 120-66 / 120-67 的参数与 retry 策略更新，不改变 135 的检测路径。它继续保留核心原则：没有分隔证据的 content-only candidate 不能自动通过，避免 120 困难图被“蒙对”。

主要变化：

- 版本号升为 `4.1`。
- 120-66 新增短轴 aspect outer retry：只有在 full strip、separator candidate、hard separator evidence 已通过，并且 content evidence 明确显示画幅因为短轴 outer 过窄而接近“高瘦”时，才尝试向短轴外扩 outer，让单张画幅接近 1:1。这是 66 专用的保守 retry，不会让 content-only 路径自动 PASS。
- 120-67 横向内容比例修正为 5:4。此前 policy 使用 4:5，更像竖向 67，会把横向 67 的正常内容误判为 aspect conflict。
- 120-67 增加适合 120 的 hard-full confidence floor 和 outer-area 容忍：当 full-strip、张数正确、所有 gap 都有 hard separator / edge-pair 证据、没有 equal gap，并且 frame width 稳定时，separator candidate 可以达到自动通过所需的置信度下限。
- 120-66 也使用同类 hard-full confidence floor，但仍要求完整 hard separator evidence；没有分隔证据的 content-only 候选保持 REVIEW。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.1`。
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 120-66 full dry-run + diagnostics：16 张，7 个 `approved_auto` / 9 个 `needs_review`。通过的 7 张都有完整 hard separator evidence；content-only 结果仍保持 `needs_review`。
- 120-67 full dry-run + diagnostics：4 张，2 个 `approved_auto` / 2 个 `needs_review`。其中 `2.tif` 仍因一个 gap 为 equal、分隔证据不完整而 REVIEW；`4.tif` 更接近 partial / 单张图场景，full count=3 下保持 REVIEW。
- 使用 V4.0.1 commit `b9940a8` 作为 baseline，对全量 `Test/135` 做同参数 `deskew off` dry-run。两边都是 48 张、43 个 `approved_auto` / 5 个 `needs_review`，`python3 -m x5crop.regression` 比较 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 为 0 diff。

### V4.0.1

V4.0.1 是 V4.0 之后的一个窄范围检测兼容更新。它不把 135 的 hard gap 最大宽度全局放宽；普通路径仍使用 V4.0 的 `gap_max_width_ratio=0.045`。当普通 separator 候选因为分隔证据不足无法通过 auto gate 时，脚本才会额外启用正式 `wide-separator` 分支，允许宽度上限到 `wide_gap_retry_max_width_ratio=0.060`。

`wide-separator` 不是普通 `detected` 的全局放宽。它只在普通窄分隔失败后介入，并要求宽黑带的均值和相对突出度达标。通过后，gap method 会写成 `wide-separator`，报告会单独记录 `wide_detected_gaps` 和 `wide_gap_retry`，Debug Analysis 里也使用红色系的独立标记。包含宽分隔条的 separator 候选会被轻微限制最高置信度，避免宽黑带把 confidence 直接顶满。

这个设计用于处理肉眼分隔清楚、但黑色片距比旧规则更宽的 135 长图。`wide-separator` 只在普通 135 full strip 上启用；half、xpan、120 和 135-dual 仍保持关闭，避免未调参格式被顺手放宽。

同时新增仓库内的 macOS 诊断启动器 `X5_Crop_Mac_diagnostics.command`。它固定开启 dry run、Debug Analysis、`--diagnostics`、`--no-copy-review-files`、`--no-reuse-analysis` 和 `--jobs 4`，用于本地开发测试。它不是普通用户启动器，不放进 Release 包。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.0.1`。
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- 新增 `Test/new_135` 4 张宽片距样本从 V4.0 的 `needs_review` 变为 4 个 `approved_auto`，且报告中出现 `wide-separator` / `wide_detected_gaps` / `wide_gap_retry.used=true`。
- 全量 `Test/135` default-deskew Debug Analysis dry run 保持 42 个 `approved_auto` / 6 个 `needs_review`。
- 使用 `python3 -m x5crop.regression` 比较既有 `Test/135/x5_crop_output/split_report.jsonl` 和 V4.0.1 临时输出，48 行报告的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。

### V4.0

V4.0 是一次大胆的完整模块化重写，但它仍然遵守“重写结构，保持结果”的约束。它不是新检测算法，也没有引入 OpenCV、scipy 或其它大依赖；这些图像处理后端暂定为未来 V5 方向。V4 的目标是把入口、检测核心、几何证据、I/O、Debug Analysis、report、deskew、CLI 和 regression 真正拆开，同时用全量 135 回归证明输出不变。

主要变化：

- 版本号升为 `4.0`。
- 根目录 `X5_Crop.py` 变成薄入口，只调用 `x5crop.cli.main()`；用户仍然运行同一个入口脚本和同一个启动器。
- `x5crop/core.py` 不再承载完整实现，只保留兼容 re-export，方便旧导入路径继续工作。
- 新增 `x5crop/common.py`：集中 dataclass、format policy、`FormatTuning`、`FrameFitPolicy`、基础数学/几何工具和通用序列化辅助。
- 新增 `x5crop/evidence.py`：负责基础灰度、分析灰度、内容证据图、分隔证据图和证据图归一化。
- 新增 `x5crop/io.py`：负责 TIFF 读取、写出、metadata/ICC/resolution 保持、review copy 和 TIFF profile 校验。
- 新增 `x5crop/geometry.py`：负责 outer 候选、白边/内容对齐、separator profile、gap 搜索、edge-pair、robust grid、frame fit 和几何 polish。
- 新增 `x5crop/detection/pipeline.py`：负责候选生成、content validation、support score、confidence calibration、review gates 和最终检测选择。
- 新增 `x5crop/deskew.py`：负责 deskew 角度估计、旋转和复用报告时的同角度裁切。
- 新增 `x5crop/debug/render.py`：负责 Debug JPG、Debug Analysis 四联图、诊断 overlay、版本标记和可读性渲染。
- 新增 `x5crop/reports.py`：负责 report 写入、report reuse、output-only bleed 复用校正、needs_review 复制和裁切写出。
- 新增 `x5crop/cli.py`：负责参数解析、文件夹并行、单文件处理、终端输出和主流程编排。
- 新增 `x5crop/regression.py`：可以比较两份 `split_report.jsonl`，默认比较 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps`。
- 新增 `tools/build_standalone.py`：发布时把 V4 模块化源码生成一个单文件版 `X5_Crop.py`，让普通用户仍然只需要复制脚本本体和对应系统主启动器，不需要复制 `x5crop/` 文件夹。
- 本地 ignored 测试副本 `Test/135/X5_Crop.py` 和 `Test/135/x5crop/` 已同步到 V4。
- 不改版本号的输出 bleed 调整：默认长轴 bleed 从 35px 改为 20px，短轴仍为 10px；如果检测到叠片、近似叠片或连续内容风险，输出长轴 bleed 自动提高到 50px。这个调整只影响最终输出、报告和 Debug Analysis 色块，不参与检测评分。
- 不改版本号的文档澄清：README 和快速启动文档明确说明自动裁切输出 TIFF 会保留原 TIFF 的画质相关属性，包括但不限于位深、通道结构、ICC / 色彩空间、resolution 和 metadata；裁切不会为了输出而主动降位深、改色、压缩或重采样。
- 不改版本号的发布包文档格式调整：Release zip 内的用户文档改为 `README.txt` 和 `快速启动_Quick_Start.txt`，便于用户在不同系统上直接打开阅读；仓库源文档仍保留 `README.md` 和 `快速启动_Quick_Start.md`。

验证：

- `python3 X5_Crop.py --version` 输出 `X5_Crop.py 4.0`。
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` 通过。
- V3.9 baseline：48 张 TIFF，0 failed，42 个 `approved_auto`，6 个 `needs_review`，default-deskew dry run 用时约 317 秒。
- V4.0 current：48 张 TIFF，0 failed，42 个 `approved_auto`，6 个 `needs_review`，default-deskew dry run 用时约 314 秒。
- 使用 `python3 -m x5crop.regression` 比较 V3.9 和 V4.0 的全量 135 JSONL 报告，48 行报告的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。

### V3.9

V3.9 是 V3.7 之后的结构清理版。它不是一次“变聪明”的检测改写，而是把剩余散落在流程里的策略开关、百分比/clamp 参数、format 分支和将来可以推广到其它 format 的能力，继续收进更清楚的 policy 层。目标是让后续优化 135、half、xpan 或 120 时，不再到处翻魔法数字，也不让低收益 fallback 悄悄改变 PASS/REVIEW。

主要变化：

- 版本号升为 `3.9`。
- 新增 `OuterMaskProfile`，把外框底层 mask 抽取使用的亮度范围、行列最小占比和最小外框尺寸接入 `FormatTuning`。
- post-detection confidence caps 改为 policy 字段，包括内容比例冲突、低内容置信、outer mismatch 和 lucky-pass risk 的置信度上限。
- deskew 的 span skip 门槛改为 `FormatTuning` 控制的比例 + clamp，而不是散落的固定像素判断。
- frame-fit 中剩余的 1px 小容忍改成 ratio + clamp 形式，默认仍等价于旧行为。
- separator hard-evidence gate 改为 `separator_gate_mode`，让 135、half 和 hard-required format 的证据要求从 policy 层表达。
- outer retry 是否启用改为 `outer_retry_enabled`，当前 135-dual 仍关闭，普通 135 保持原行为。
- nearby active correction、lucky-pass risk、leading-grid failure 等高风险能力继续通过 policy 控制；非 135 format 仍只保留入口，不直接套用 135 规则。
- `X5_Crop.py`、本地 `Test/135/X5_Crop.py` 和归档快照 `archive/X5_Crop_v3.9.py` 都同步到 V3.9。

验证：

- 以 V3.7 当前脚本快照作为 baseline，用 default-deskew full 135 dry run 对比 V3.9。两边都是 48 张 TIFF、0 failed、42 个 `approved_auto`、6 个 `needs_review`。
- 对比字段：`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps`。
- 结果：48 条报告全部 0 diff。
- 这次验证使用的是 default deskew 路径，不是 `deskew off` 快速路径，因此覆盖了正常启动器更接近的检测/校平流程。

### V3.7

V3.7 是一次 frame-size fit 管线整理。此前脚本里同时存在两套容易混淆的拟合逻辑：`apply_frame_size_fit()` 在 cuts 层面做等宽几何修正，`same_frame_size_fit_boxes()` 在 box 层面用 `detected` / `edge-pair` 的左右边缘样本做同画幅拟合。随着 `edge-pair` 已经扩展到各个 format，这两套逻辑继续分散维护会让后续判断“红框、grid、equal 到底谁有权修正输出框”变得不够清楚。

V3.7 将它们整理为一个统一入口：`fit_frame_boxes_from_gaps()`。内部先生成基础 frame boxes，然后按 format-aware policy 尝试 edge-evidence fit；如果边缘证据不足，则使用 geometry fallback 或原始 gap 切法。这个版本的目标是结构变清楚，而不是放宽自动裁切。

主要变化：

- 版本号升为 `3.7`。
- `apply_frame_size_fit()` 改名并收窄语义为 `fit_cuts_by_geometry()`，表示它只是 cuts 级 geometry fallback。
- `same_frame_size_fit_boxes()` 改名并收窄语义为 `fit_boxes_by_edge_evidence()`，表示它只负责使用 hard / edge-pair 边缘证据做同画幅拟合。
- 新增 `FrameFitPolicy` 和 `fit_frame_boxes_from_gaps()`，让 frame fit 的 edge evidence、geometry fallback、raw gap fallback 从同一个入口返回。
- 后续整理：`FrameFitPolicy` 已改成真正按 format 区分。135 保持原始阈值；half-frame 要求更多边缘样本；xpan 和各 120 format 有独立的名义宽度范围与 inlier 容差；135-dual 和 partial mode 不启用 edge-evidence fit，但保留 geometry fallback。
- 继续保持“不因为 fallback 或重构而放宽 PASS/REVIEW”的原则。
- 不改版本号的后续配置调整：默认输出长轴 bleed 曾从 20px 改为 35px，短轴仍为 10px；后续 V4.0 稳定版又把默认长轴 bleed 调回 20px，并对叠片 / 连续内容风险图自动使用 50px 长轴输出 bleed。bleed 始终只在输出、报告和 Debug Analysis frame box 阶段应用，不参与检测评分。
- 不改版本号的后续尺度清理：`edge_bleed_protection`、approved geometry polish、outer content alignment、alignment outer correction 和 robust grid hard-gap protection 中的固定 pixel 门槛改为“相对 pitch / outer height 的比例 + pixel clamp”。这些内部阈值不再跟输出 bleed 直接绑定，当前 135 分辨率区间保持旧触发行为。
- 不改版本号的第二轮尺度清理：gap 搜索半径、hard gap 宽度/guard、nearby separator 搜索窗口/移动判断、edge-pair window/gutter/hard-gap movement guard、robust grid shift/tolerance、enhanced separator gap 宽度/位移、partial edge hint 窗口、hard-gap trust 诊断窗口和 deskew span skip 门槛也改为“比例 + clamp”。原来是浮点容差的地方继续使用浮点 clamp，避免引入小数级 grid 漂移。
- 不改版本号的 format policy 整理：新增 `FormatTuning`，把 outer candidate、outer/content alignment、content primary、gap detection、geometry constrain、robust grid、hard-gap trust、nearby separator、enhanced separator、scoring、auto gate、support score、candidate calibration、partial strategy、diagnostics 和 approved geometry polish 的参数集中为 format-aware policy。135 参数保持当前值，其它 format 先使用保守入口，避免这次整理改变自动裁切行为。
- 不改版本号的 format policy 继续推广：content run threshold、content confidence caps、score partial / outer / 135 hard-evidence caps、separator hard-evidence gate、leading-grid failure、content-only partial、nearby active correction 和 lucky-pass risk 都改为 policy 控制。高风险项仍保持保守：nearby active correction、lucky-pass risk 和 leading-grid failure 只在已经验证过的 135 路径启用，其它 format 只保留独立 policy 入口与诊断基础。
- 不改版本号的 policy 继续整理：底层 outer 抽取、separator profile、edge-refine profile、grid outer refine、frame-fit geometry fallback、edge-evidence inlier 容忍、non-auto candidate confidence cap 和 deskew 采样/增强门槛都接入 format-aware policy。135 默认值保持原行为。
- 不改版本号的复用与诊断效率整理：Debug Analysis 报告复用不再把输出 bleed 当成检测签名的一部分；复用正式裁切时会先从旧输出 bleed 还原，再套当前 bleed，避免只改 bleed 后复用旧框出错。诊断层的 nearby separator 复查也复用缓存的 separator profile，减少全量诊断时的重复计算。
- 不改版本号的高层 policy 清理：主评分的 gap/width/outer/contrast 权重、content evidence 阈值、content/geometry/separator support gate、candidate competition margin/cap、hard-gap trust 语义阈值、overlap-risk 诊断阈值和 Debug gap overlay 线条参数也接入 `FormatTuning`。当前 135 默认值保持原行为；这一步主要让之后按 format 调参更集中，不放宽自动裁切。
- 不改版本号的低风险代码清理：移除未使用的 `score_120_require_all_hard` policy 字段；将 `detect_for_count()` 改名为更准确的 `detect_candidate_for_count()`；`lucky_pass_risk_score_detail()` 复用主流程 analysis cache，避免重复生成内容/分隔证据缓存。检测参数和 PASS/REVIEW 行为不变。
- 不改版本号的后续 policy 继续整理：content primary candidate 的 bbox fraction、最小尺寸、percentile、coverage/mean/run/aspect 权重，deskew edge-fit 的外框抽取和 line-fit 容忍，以及 lucky-pass risk 的风险组件权重/阈值也接入 `FormatTuning`。当前默认值保持原行为；`make_content_evidence_gray()` 暂不按 format 分支，以免改变 analysis cache 语义。
- 当前脚本仍保留 `--analysis` 控制的增强分隔辅助层。V3.4 曾经尝试移除这一层，但当前 V3.9 的实际行为是：`auto` 只在弱分隔证据时尝试增强分隔，`always` 每次尝试，`off` 关闭；同一个参数也控制 deskew 的增强角度候选。
- 当前未对其它 format 开放的 active 能力：nearby separator active correction、lucky-pass risk、leading-grid failure。它们有 format policy 入口，但没有直接套用到 half / xpan / 120，因为这些失败形态高度依赖 format。当前版本主要按普通 135 优化；其它 format 虽然可选，但还没有经过同等细致调参，效果可能不如 135 稳定。
- 不改版本号的 hard fallback detail 清理：`hard_fallback_detection()` 继续只是 review-only equal split 防崩兜底，但 detail 只保留 fallback 类型、format/count/layout、work outer 和 pitch，不再输出 `candidate_competition` 或重复的 gap center/score/method 数组。
- 不改版本号的文档与卸载工作流整理：README 和快速启动文档补充了为什么保持脚本 + 启动器而不做 App 封装、如何干净卸载、卸载 Python 或依赖可能影响其它工具、`needs_review/` 里的 TIFF 是未处理的原文件副本，以及 partial mode 更适合片头、片尾、局部片条或不确定张数。Release 包策略增加两个卸载启动器：`install/X5_Crop_Mac_uninstall.command` 和 `install/X5_Crop_win_uninstall.bat`。
- 不改版本号的文档补充：README 和快速启动文档新增 `dry run` 概念解释，说明它是试运行 / 分析模式，会读取 TIFF、执行检测、判断 PASS/REVIEW，并可生成 Debug Analysis JPG 和报告，但不会导出正式裁切 TIFF，也不会修改原 TIFF。
- 不改版本号的文档耗时更新：普通 135 Mac 启动器实测 48 张 TIFF 全量正式裁切用时 394 秒，平均约 8.2 秒/张。README 和快速启动文档已按这个实测值更新普通 135 耗时说明。

验证：

- V3.7 与 V3.6.12 使用相同 `deskew off` dry-run 参数做全量结构对比，`Test/135`、`Test/半格`、`Test/120` 的 120-645 / 120-66 / 120-67 五组对比中，`status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。另用 135 partial mode 做了一张 smoke 对比，同样 0 diff。
- 尺度清理后再次对 `Test/135` 做全量 `deskew off` dry-run，并和清理前基线比较 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps`，结果为 0 diff。
- 第二轮尺度清理后再次对 `Test/135` 做全量 `deskew off` dry-run，并和上一轮 0 diff 基线比较同一组字段，结果仍为 0 diff。
- Format policy 整理后再次对 `Test/135` 做全量 `deskew off` dry-run，并和上一轮 0 diff 基线比较同一组字段，结果仍为 0 diff。
- Format policy 继续推广后再次对 `Test/135` 做全量 `deskew off` dry-run，并和上一轮 0 diff 基线比较同一组字段，结果仍为 0 diff。
- 高层 policy 清理后，从 Git HEAD 临时取出清理前脚本作为基准，再对当前脚本做同参数全量 `Test/135` `deskew off` dry-run。两份报告的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。
- 低风险代码清理后，以清理前的本地脚本快照作为基准，再对当前脚本做同参数全量 `Test/135` `deskew off` dry-run。两份报告的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。
- 后续 policy 继续整理后，以清理前的本地脚本快照作为基准，再对当前脚本做同参数全量 `Test/135` `deskew off` dry-run。两份报告的 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes` 和 `gaps` 均为 0 diff。
- Hard fallback detail 清理后通过 `python3 -m py_compile` 和直接 smoke call 验证；该路径只影响 fallback report/detail，不改变正常 135 检测输出。

### V3.6.12

V3.6.12 是 V3.6.11 format-aware `edge-pair` 的参数优化版。它用本地 `Test/120` 和半格全量 dry run 校准非 135 参数：半格结果已经稳定，因此保持半格参数不变；120-66 / 120-67 的分隔形态更像“宽暗带 + 低背景 profile”，所以放宽 edge-pair 的 120 搜索窗口、gutter 宽度、边缘强度和背景阈值，同时收紧 hard gap 的大位移替换保护。

这次更新只让 120 的分隔证据更容易被画出来和记录下来，不改变“只有高置信才自动裁切”的原则。全量测试中 120-66 / 120-67 的 edge-pair 命中从 0 提高到 16，但 120 样本仍全部保持 REVIEW；半格保持 6 个 `approved_auto` / 9 个 `needs_review`；135 focus 对比 V3.6.11 的结构化结果没有变化。

主要变化：

- 版本号升为 `3.6.12`。
- 120-66 / 120-67 edge-pair 参数改为更适合宽 120 暗带：更大的窗口和 gutter 上限，更低的边缘/背景阈值。
- hard gap 替换保护改为参数化：135 保持旧的严格位移限制；非 135 只允许小幅替换已经存在的 hard gap，避免 edge-pair 大幅挪动原生红框。
- 120-645 参数只做轻微准备性调整；当前 `Test/120` 更像 3-frame 120 样本，不能用它过度校准 645。
- 半格参数不变。
- 后续工作流整理：主启动器在普通非 Debug Analysis 裁切时不再传 `--report`；只有 Debug Analysis dry run 仍生成报告。Release zip 封装策略改为包含 `X5_Crop.py`、`X5_Crop_Mac.command`、`X5_Crop_win.bat`、`README.md`、`快速启动_Quick_Start.md` 和 `install/` 内两个安装启动器，不包含 archive、license 或本地测试输出。macOS 安装器现在会尝试为当前 Release 文件夹里的启动器添加执行权限并移除下载隔离标记；文档补充了双击安装器失败时的 Terminal 启动命令，并说明安装后可以把 `X5_Crop.py` 和对应系统主启动器成对复制到不同 TIFF 文件夹使用：macOS 使用 `X5_Crop_Mac.command`，Windows 使用 `X5_Crop_win.bat`。重新下载或重新解压的新文件夹需要再次运行安装器。

验证：

- 半格 full dry run：15 张，6 `approved_auto` / 9 `needs_review`，与 V3.6.11 相同。
- 120-66 full dry run：16 张，0 `approved_auto` / 16 `needs_review`，edge-pair accepted total 从 0 提高到 16。
- 120-67 full dry run：16 张，0 `approved_auto` / 16 `needs_review`，edge-pair accepted total 从 0 提高到 16。
- 120-645 full dry run：16 张，0 `approved_auto` / 16 `needs_review`，edge-pair accepted total 保持 0。
- 135 focus dry run（`deskew off`）对比 V3.6.11：`X5_00014`、`X5_00026`、`X5_00036`、`X5_00041` 的 status、confidence、outer、frame boxes、gap methods、gap centers 全部一致。

### V3.6.11

V3.6.11 将 `edge-pair` 从 135 full strip 专用扩展为所有格式的 format-aware full-strip 分隔 refine。它保留 135 原参数，避免扰动当前 135 基线；其它格式使用更保守的搜索窗口、gutter 宽度、边缘强度、背景强度和模型 gap 替换质量阈值。这样 120、XPAN、half 等格式在黑条不够理想但照片相邻边缘可信时，也可以获得 edge-pair 分隔证据。

主要变化：

- 版本号升为 `3.6.11`。
- 新增 `EdgePairParams` 和 `edge_pair_params_for_format()`。
- `refine_gaps_by_edge_pairs()` 接收 `format_name`，并在 detail 中记录实际参数。
- full strip 的所有格式都会尝试 edge-pair refine；135 保持原参数，非 135 需要更强质量才会用 edge-pair 替换 grid/equal 这类模型 gap。

### V3.6.10

V3.6.10 是 V3.6.9 之后的低风险清理版，不改变检测流程、PASS/REVIEW 逻辑或输出框。它清理了 `light_hard_gap_trust` 统一后遗留的未使用包装函数，并修正命令行 help 和诊断报告中的旧版本/旧基线话术。

主要变化：

- 版本号升为 `3.6.10`。
- 移除未使用的 `grid_protection_trust()`。
- CLI 描述从 V3.6.8 更新为 V3.6.10。
- `--bleed-x` help 的默认值从旧的 15 修正为当前实际默认 20。
- `--analysis` help 明确说明它同时影响增强分隔辅助和 deskew 增强候选。
- `diagnostics.purpose` 不再写 “without changing V3.3.1 output”，改成更准确的“观察诊断信号且不改变 crop output”。

### V3.6.9

V3.6.9 统一 active correction 和 diagnostics 之间的红框可信度判断。此前 `grid_protection_trust` 只看 score、width 和 grid residual，而 `hard_trust` 会解释 nearby conflict、geometry conflict、suspect internal edge / frame border 等更细信号。V3.6.9 新增共享的轻量 `light_hard_gap_trust`，让 grid protection 在决定“红框是否能抗 grid 覆盖”之前，也能识别这些可疑信号。

这次更新的目标不是改变输出，而是减少 active 层和 Debug Analysis 解释层的双轨判断。验证中，V3.6.9 相对 V3.6.8 全量 `Test/135` dry-run 没有任何结构化输出变化。

主要变化：

- 版本号升为 `3.6.9`。
- 新增共享 `light_hard_gap_trust`。
- `apply_robust_grid` 在保护 hard gap 前会使用共享 trust，并把 `trust_detail` 写进 `protected_hard_gaps` / `overridden_hard_gaps`。
- active grid protection 现在能阻止 `nearby_separator_conflict`、`geometry_conflict`、`suspect_internal_edge`、`suspect_frame_border` 成为 strong anchor。

验证：

- Focus dry-run：`X5_00007`、`X5_00014`、`X5_00023`、`X5_00026`、`X5_00032`、`X5_00035`、`X5_00041`。`X5_00041` 继续 REVIEW，其它目标样本保持 PASS。
- 全量 `Test/135` dry-run：42 `approved_auto` / 6 `needs_review`。
- 与 V3.6.8 全量报告结构化对比：changed `0`。

### V3.6.8

V3.6.8 保留 V3.6.7 的 nearby separator correction，但把 `X5_00041` 相关的 exact single-anchor gate 改成更通用的 `lucky_pass_risk_score`。新的 score 不再要求固定的 `2/1/1/2` 组合，而是把以下信号合成风险分：

- model gap 依赖程度。
- strong hard separator 数量是否偏少。
- 是否存在 suspicious hard gap。
- 是否存在 strong overlap / continuous-content model gap。
- suspicious hard gap 和 overlap model gap 是否同时出现。
- frame width 几何是否足够稳定，稳定时给一部分减分保护。
- strong hard separator 足够多时给一部分减分保护。

当 risk score 达到 `0.80` 时，脚本添加 `lucky_pass_risk` 并把 confidence 压到阈值以下。这仍然只会让可疑 PASS 进入 REVIEW，不会让任何图更容易通过。

验证：

- Focus dry-run：`X5_00007`、`X5_00014`、`X5_00023`、`X5_00026`、`X5_00032`、`X5_00035`、`X5_00041`。只有 `X5_00041` 进入 REVIEW。
- Focus score：`X5_00041` 为 `0.96`，高于阈值 `0.80`；`X5_00007` 为 `0.71`，`X5_00035` 为 `0.74`，均低于阈值。
- 全量 `Test/135` dry-run：42 `approved_auto` / 6 `needs_review`，`X5_00041` 以 `lucky_pass_risk` 进入 REVIEW。

### V3.6.7

V3.6.7 把 V3.6.6 的 nearby separator 复查从诊断层提升为非常窄的修正规则。它只会在附近候选明显更强、移动后局部画幅几何更合理、整体宽度稳定性没有变差时移动红色 hard separator，并且会把 correction 前的 confidence 作为上限，避免靠修正提高自动通过概率。

同时，V3.6.7 新增一个很窄的 single-anchor review gate，用来处理 `X5_00041` 这类“局部锚点看起来成立，但整体更像 lucky PASS”的形态。该闸门要求同时满足：2 个 strong hard gap、1 个 suspicious hard gap、1 个 strong overlap model gap、2 个 model gap。这样可以让 `X5_00041` 进入 REVIEW，同时避免把 `X5_00007`、`X5_00023`、`X5_00035` 这类组合不同的图一起误伤。

主要变化：

- 版本号升为 `3.6.7`。
- 新增 `nearby_separator_correction` detail 字段，记录 accepted / rejected correction、移动距离、候选分数和几何改善。
- correction 只允许降低或保持 confidence，不允许提高 confidence。
- 新增 `single_anchor_review_gate` detail 字段；触发时添加 `single_anchor_pass_risk` 并把 confidence 压到阈值以下。

验证：

- Focus dry-run：`X5_00014`、`X5_00026`、`X5_00032`、`X5_00041`、`X5_00036`。
- 收窄 gate 后 focus dry-run：`X5_00007`、`X5_00014`、`X5_00023`、`X5_00026`、`X5_00032`、`X5_00035`、`X5_00041`，只有 `X5_00041` 进入 REVIEW。
- 全量 `Test/135` dry-run：42 `approved_auto` / 6 `needs_review`。相对 V3.6.6 只有 `X5_00026` 和 `X5_00041` 发生结构变化；`X5_00026` 拉回第一个 red gap，`X5_00041` 进入 REVIEW。

### V3.6.6

V3.6.6 开始把红色 hard separator 从“是否检测到暗边”进一步拆成“是否可信的片间分隔”。这一版重点服务 `X5_00026`、`X5_00032` 和 `X5_00041` 这类红框可疑样本，同时修复 V3.6.4 中正确 hard separator 被 grid 覆盖的问题。

主要变化：

- 每个 hard gap 新增 `hard_trust` 分级：`strong_separator`、`narrow_but_ok`、`suspect_internal_edge`、`suspect_frame_border`、`nearby_separator_conflict`、`geometry_conflict`、`weak_or_ambiguous_separator`。
- 对 hard gap 做 `nearby_separator_candidate` 复查，在 `±4% pitch` 范围内记录附近更强分隔候选。
- Debug Analysis 中用 magenta tick 标记可疑 hard gap。
- 新增 `single_anchor_pass_risk` 诊断，用来标记只有局部锚点可信、其它证据不足但仍 PASS 的风险。
- `apply_robust_grid` 现在会记录 `protected_hard_gaps` 和 `overridden_hard_gaps`。
- 只有当 grid 模型残差偏高时，`strong_separator` 才能阻止 grid 覆盖；这避免稳定 grid 被单个偏离 hard gap 误伤。
- 全量对比 V3.6.4：PASS/REVIEW 仍为 43/5，几何变化只剩 `X5_00014` 和 `X5_00026`。

### V3.6.5：诊断并行上限调整

V3.6.5 不改变检测逻辑，只调整诊断运行的并行能力。普通启动器和普通命令行仍然最多 2 个 worker；只有显式启用 `--diagnostics` 时，`--jobs` 才允许最高到 4。这样本地诊断启动器可以更快跑完 Debug Analysis，而正式裁切路径仍保持更保守的内存占用。

主要变化：

- `--jobs` 上限从固定 2 改为普通运行最多 2、diagnostics 运行最多 4。
- 本地诊断启动器传入 `--jobs 4`。
- 检测逻辑、PASS/REVIEW、输出框、TIFF 输出策略均不改变。

### V3.6.4：单侧白边外框修正

V3.6.4 回到 V3.6.2 检测基线，暂时不采用 V3.6.3 的 strong overlap risk 强制 REVIEW 规则。它优先解决一个更窄的问题：当 135 full strip 的首尾 hard separator 都可靠、内容框完整、并且长轴单侧外框边缘几乎全白时，允许外框收回到内容边缘附近，再进入已有的 gap / frame 计算链路。

主要变化：

- 移除 active 脚本中的 `overlap_review_gate`，V3.6.3 作为暂停参考方向保留在 archive。
- `outer_content_alignment_detail` 新增 `edge_hard_anchors` 和 `white_edge_slack` 诊断字段。
- `white_edge_slack` 只有在首尾 gap 都是 hard separator、内容宽度几乎填满 outer、短轴没有明显异常、且长轴某一侧边缘几乎全白时才触发。
- 触发后走已有 `content_aligned_outer` retry，不直接提高 confidence，也不把困难图变成自动通过路径。
- 该规则主要针对外框长轴单侧纳入明显白边的问题，不处理叠片/近似叠片，也不处理红框内部边缘误判。

### V3.6.3：叠片 REVIEW 闸门实验（已暂停）

V3.6.3 把 V3.6.1/V3.6.2 的叠片诊断升级为保守的 REVIEW 安全闸门。新的判断不尝试修正叠片，也不提高置信度；它只在 135 full strip 中发现 strong overlap-risk model gap 时，把图片视为困难图，避免自动裁切。

主要变化：

- 新增 `overlap_review_gate`。
- 仅作用于 `film_format=135` 且 `strip=full` 的场景。
- 只检查 `grid` / `equal` / `content` 这类模型 gap 上的 strong overlap risk。
- 触发时 confidence cap 到阈值以下，并加入 `overlap_or_near_overlap_review`。
- 该规则不移动 gap、不改变 outer、不改变 frame boxes，只改变 PASS/REVIEW。
- 目标是让叠片、近似叠片、内容连续导致的模型补位不再自动通过。
- 该方向已暂停：后续先搁置“strong overlap risk 直接 REVIEW”的思路，改为逐步建立更细的 grid trust / hard gap trust 诊断与更窄的修正规则。

### V3.6.2：低收益逻辑清理

状态：GitHub 稳定发布版。

Release asset:

- `X5-Crop-v3.6.2.zip`

V3.6.2 是在 V3.6.1 诊断层稳定之后做的第一步检测逻辑瘦身。目标不是引入新的自动修正，而是减少低收益 method 和报告/Debug Analysis 噪音，让之后判断 correction proposal 更容易。

主要变化：

- `equal-broad-region` 不再作为独立 gap method 出现，统一合并为普通 `equal`。
- Debug Analysis 不再为 `equal-broad-region` 保留单独颜色或图例角色。
- `hard_fallback_detection` 保留为防崩的 review-only fallback，但 detail 缩小为 `fallback_kind=review_only_equal_split`，不再模拟完整候选竞争结果。
- 这些改动不应该放宽 PASS/REVIEW，也不应该把 fallback 变成自动通过路径。
- 已作为稳定版发布，但叠片、近似叠片、局部片距非常不稳定、分隔条缺失或画面内容连续的长图，仍可能误识别或裁切不够准确。普通用户遇到这些困难图时应运行 Debug Analysis 并人工复核。

### V3.6.1：显式诊断模式

V3.6.1 继续沿用 V3.3.1 输出基线和 V3.6 的只读诊断方向，但把诊断层改为显式启用。正常启动器不传 `--diagnostics`，因此普通 Debug Analysis 只保留常规四联图，不额外写诊断字段或画诊断 tick。

主要变化：

- 新增 CLI 参数 `--diagnostics`，用于本地测试时写入只读 `diagnostics` 并在 Separator evidence 面板显示诊断 tick。
- 诊断层继续不改变输出框、confidence 或 PASS/REVIEW。
- 叠片 / 连续内容诊断从简单布尔值细分为 `weak`、`medium`、`strong` 风险，只有 `strong` 风险才在 Debug Analysis 中画 cyan tick，减少视觉噪音。
- 本地测试可使用未同步的诊断启动器；它默认 `deskew auto`、`dry run`、`debug analysis` 和 `--diagnostics`。
- 正常 macOS / Windows 启动器不开启诊断。

### V3.6：诊断清理版

目标：

- 从 V3.3.1 输出基线出发，清理报告和 Debug Analysis 的可读性。
- 在不改变输出的情况下，为叠片和红框可信度问题建立观察层。
- 让后续优化可以先看准，再决定是否进入 review-only 或 correction rule。

主要变化：

- 版本号升为 `3.6`。
- 新增 `diagnostics` detail 字段。
- 为每个 gap 标记 method role：separator evidence、enhanced separator evidence、geometry model、broad fallback 或 content model。
- 为 hard gap 记录早期 `hard_trust` 诊断；后续 V3.6.x 已扩展为更细的当前分级，例如 `strong_separator`、`narrow_but_ok`、`suspect_internal_edge`、`suspect_frame_border`、`nearby_separator_conflict` 和 `geometry_conflict`。
- 为 model gap 标记 `overlap_like`，用于提示叠片或连续内容风险。
- Debug Analysis 的 Separator evidence 面板增加轻量诊断 tick：magenta 是可疑 hard gap，cyan 是疑似 overlap / continuous-content model gap。
- 坚持困难图、弱证据图不能因为 fallback、rescue、grid 或语义校验逻辑而自动通过。

已知限制：

- 它仍不主动修正叠片、片距不稳定、红框/grid 冲突或内部边缘误判。
- `diagnostics` 只是观察层；之后要把任何诊断变成实际修正规则，都必须先通过已知准确样本保护。

验证：

- 使用 V3.3.1 回滚提交 `8928f70` 作为基线，对 `Test/135` 48 张图全量 dry run。
- V3.6 与该 V3.3.1 基线相比：`status`、`outer_box`、`frame_boxes`、confidence 全部一致。
- V3.6 全量结果为 43 张 `approved_auto`、5 张 `needs_review`。

### V3.5：Hard Gap 语义校验实验

状态：已暂停 / 已从 active 脚本回滚。

目标：

- 让红色 hard separator 框更可信。
- 识别“高分红色 edge-pair 其实是画面内部边缘，而不是真正胶片分隔”的情况。
- 只让 grid 处理明确可疑的红色 gap，同时不放宽 PASS/REVIEW。

实现思路：

- 在 `edge_refine` 之后、robust grid 之前运行一个轻量校验层。
- 复用已经缓存的 content evidence 和 edge-refine profiles。
- 对每个已接受的 hard gap，检查 gap 附近的小窗口：gap content、左右 content、content continuity、background/separator profile、edge/activity profile。
- 给 hard gap 标记 strong 或 suspect。
- 只把非常窄、内容连续、像内部边缘的 hard gap 降级为 model gap。

为什么暂停：

- 它确实解释了至少一种红框误判模式，但 active V3.5 让一些原本准确的扫描变差。
- 用户在重要的已知准确样本上观察到回退，因此这套逻辑从 active 脚本移除。

后续注意：

- 不要把它作为宽泛规则直接加回来。
- 如果之后重启，先做成只写报告的诊断层，不要立刻改变 gap method。
- 它需要更强的已知准确样本保护，也可以考虑先加不直接改变几何的 per-gap confidence label。

### V3.4.2：局部 Grid 分段实验

状态：已暂停 / 已从 active 脚本回滚。

目标：

- 改善片距不稳定、近似叠片、局部几何不稳定的情况。
- 让 grid 仍然有用，但不让全局等距模型覆盖正确的红色 hard separator。

实现思路：

- 用强 hard separator 作为局部锚点。
- 只用局部 pitch 调整锚点之间或附近的 model-only gaps（`grid` / `equal`）。
- 不移动 hard separator。
- 不因为 local grid 调整了 model gap 就提高置信度。
- 在 `local_grid` 中记录细节。

为什么暂停：

- 它仍然改变了一些原本准确样本的几何结果。
- local grid 可能有价值，但在改变几何前必须更严格证明目标 model gap 的确是错的。

后续注意：

- 如果以后重启，先限制为诊断用途。
- 可以先在 Debug Analysis 里画出 local-grid 建议，但不用于输出框。
- 必须有更强证据证明局部片距确实不规则，并且调整位置真的贴近可见分隔。

### V3.4.1：保留强 Hard Gap

状态：已暂停 / 参考方向。

目标：

- 修复 robust grid 覆盖准确红色 hard separator 的情况。
- 当红色 hard evidence 足够强且合理时，让它具有更高权重。

主要变化：

- 即使 robust grid 预测了不同中心，强 `detected` / `edge-pair` gap 也会被保留。
- grid 仍然可以补全缺失或较弱的 model gap。
- grid/hard 冲突会记录在 `grid.hard_conflicts`。
- 如果完整几何已经被接受，同一组证据不会再被重复算作 `unstable_frame_width`。

为什么重要：

- Separator evidence 面板更容易读，因为正确的红色 hard separator 会保持红色。
- grid 被视为模型辅助，而不是比真实分隔证据更强的来源。

### V3.4：检测简化

状态：V3.4.1 保留的开发基线。下面描述的是当时的实验行为；当前 V3.9 主脚本仍保留 `--analysis` 控制的保守增强分隔辅助层。

目标：

- 移除收益低或容易造成误解的检测层。
- 让 Debug Analysis 更易读。
- 降低维护成本和重复逻辑。

主要变化：

- 从 active separator detection 中移除 enhanced separator 层。
- `--analysis` 不再驱动 enhanced separator 接受逻辑；它仍与 analysis / deskew 行为相关。
- 从 active gap methods 和 README 颜色说明中移除 `enhanced-detected`。
- 将 `equal-broad-region` 合并进普通 `equal`。
- full-strip 检测在 separator/geometric candidate 已经是主路径时，不再创建单独 content candidate；content 只作为校验。
- fallback 路径保持很小且保守。

影响：

- Debug evidence 中重叠颜色和概念更少。
- full-strip 逻辑更容易维护。
- 更少旧链路决策会与 active candidate decision scoring path 竞争。

### V3.3.2：保守的叠片感知 Gap 处理

状态：开发版，回滚后仅作为历史参考。

目标：

- 改善近似叠片或连续内容情况，但不让它们更容易通过。

主要变化：

- 看起来像叠片的 model gap 可以标记为 `overlap_like=true`。
- overlap-like gap 不会被当作强 same-frame-size anchor。
- 这样做是为了减少基于可疑 model gap 的几何修正。

重要原则：

- 叠片处理应该用于解释或约束几何修正，不应该提高置信度，也不应该把困难图推成自动通过。

### V3.3.1：稳定发布版 / V3.6 输出基线

状态：GitHub 稳定发布版 / V3.6 输出基线。

发布包：

- `X5-Crop-v3.3.1.zip`

主要行为：

- 保留稳定的 V3/V3.2 普通 outer / gap / candidate 链路。
- 保留只在输出阶段生效的 bleed 分离。
- 保留保守的 PASS/REVIEW 行为。
- 包含双语 README、启动器、安装脚本、archive 快照和 MIT License。
- GitHub Release note 包含双语快速使用和相对 `v3` 的变化。

为什么它是稳定版：

- 它是在后续开发实验前打包的用户发布版。
- 它优先选择已知稳定的保守行为，而不是较新的未充分验证检测想法。

### V3.3：只在输出阶段应用 Bleed

状态：稳定发布行为的开发祖先版本。

目标：

- 防止 bleed 改变检测决策。

主要变化：

- 检测内部不使用 bleed。
- 输出、报告、Debug Analysis frame box 在之后再应用输出 bleed。
- 默认输出 bleed 是长轴 20px、短轴 10px。
- 横向长图时左右是长轴 bleed；纵向长图时按方向对应旋转解释。

为什么重要：

- 增加输出安全边距不会再改变 outer box、gap selection、confidence 或 PASS/REVIEW。

### V3.2：回到 V3 检测链路

状态：开发版。

目标：

- 在 V3.1.x 实验造成回退后，恢复更可靠的 V3 风格行为。

主要变化：

- 从 active 链路移除激进 content-aligned outer 外扩。
- 从 active 链路移除 separator-derived outer 竞争。
- 从 active 链路移除 local separator rescue。
- 保留针对 leading-grid failure shape 的特殊 REVIEW 安全闸门。

重要原则：

- 回滚恢复普通检测路线，同时保留防止明显猜测通过的安全闸门。

### V3.1.x：激进修正实验

状态：实验版，非 active。

测试过的想法：

- 更激进的 content-aligned outer 修正。
- 当普通 outer detection 较弱或缺失时，用 separator-derived outer box 竞争。
- 在预测 grid 位置附近做 local separator rescue。
- 新救回的 gap 证据触发额外 same-frame-size fitting。

为什么没有保留：

- 这些想法有时能帮助边缘情况，但也会过度改变原本准确的样本。
- 它们增加了困难图因为错误原因看起来高置信的风险。
- 项目的优先级仍然是保守自动裁切：只有高置信检测才应该自动裁切。

经验：

- rescue 逻辑在证明不会伤害已知准确样本前，应该先作为诊断或 review-only。
- 输出安全边距更适合用 output-only bleed 处理，而不是改变检测几何。
- Debug 可视化必须清楚区分真实证据和模型推测。

### V3.0：X5 Crop 基线

状态：基线 archive 快照。

主要能力：

- 独立 `X5_Crop.py` 工作流。
- 支持 135、半格、XPAN、645、66、67、135 dual 等 format-aware 裁切。
- 保守的 PASS/REVIEW 分离。
- Debug Analysis JPG 输出。
- TIFF 画质与 metadata 保持策略。
- macOS 和 Windows 启动器。

### 开发测试说明

默认测试规则：

- 对检测逻辑变化，之后开发测试默认使用 `--deskew off`，除非改动本身涉及 deskew。
- 这样可以让回归检查更快，并且聚焦检测几何本身。
- 我们自己的本地测试 / 诊断测试默认使用 4 张 TIFF 并行处理，也就是在测试命令里显式传入 `--jobs 4`。普通用户启动器和正式裁切默认策略不因此改变。

检测变化后的建议重点样本：

- `X5_00007`
- `X5_00022`
- `X5_00032`
- `X5_00036`
- `X5_00038`
- `X5_00044`
- `X5_00051`
- `X5_00052`

核心回归规则：

- 不要为了改善一个困难样本而破坏已知准确样本。
- 不要让 fallback、rescue、grid 或 semantic validation 逻辑把弱证据图推成自动通过。
- 如果新思路会改变已知准确样本的几何结果，先做成 report-only 或 review-only，再考虑影响输出框。

发布策略：

- GitHub Release 是面向用户的稳定下载。
- 仓库 `main` 分支可能包含 active 开发、实验或回滚工作。
- 每一个命名开发版本都应该在继续往后开发前保存为 `archive/X5_Crop_v*.py` 快照，包括之后被暂停或回滚的实验版本。
- 当某个开发版本足够稳定适合用户使用时，创建新的 GitHub Release，并同步更新 `README.md`、`CHANGELOG.md`、`AGENTS.md`。

---

## English Changelog

This changelog records X5 Crop detector changes, workflow updates, regression checks, and release-policy decisions. It is intended for continued development, behavior investigation, version comparison, and rollback when needed.

If you only want to use the script, start with `快速启动_Quick_Start.md` and `README.md`. This file keeps deeper development context, experiment outcomes, and verification notes.

Current active script: `X5_Crop.py` V4.7

Current stable GitHub Release: `v4.2.8`

### Version Status

| Version | Status | Summary |
|---|---|---|
| V4.7 | Current active development version | Clean-room source rewrite. Removes old `common.py`, `policy.py`, `core.py`, and root-level `io.py` / `geometry.py` / `regression.py` compatibility layers while preserving the V4.6 policy architecture. Active source now works only through real responsibility modules. `FrameFitPolicy`, separator edge-pair, gap-search, separator-derived outer gap override, and short-axis aspect retry parameters are owned by policy; `format_parameters` replaces the old `FormatTuning` surface. Seven V4.5.4 golden core comparisons are 0 diff. |
| V4.6 | Development version | Policy refactor. Adds `x5crop/policies/` and registers each format / strip-mode pair as a `DetectionPolicy` with explicit count, outer, separator, content, gate, scoring, selection, postprocess, output, and diagnostics policy surfaces. The runtime now uses policy for count planning, outer strategy, separator gates, partial-safe gates, candidate selection, and postprocess policy. The target baseline is V4.5.4 behavior. |
| V4.5.4 | Development version | 120-66 wide dark-separator improvement. Partial safe-extra-frames now requires wide-like separator evidence, leading-edge content safety, and stable per-frame content. Full 120-66 can prefer a wide dark-band outer candidate when the old outer has abnormal content geometry. `Test/120/66` partial and full both produce 16 `approved_auto` / 0 `needs_review`. |
| V4.5.3 | Development version | Half-frame full gate fix. Corrects detail-value reads so `width_cv=0.0` is not treated as a missing value through `or 1.0`. `X5_00058.tif` now passes through the existing `half_wide_geometry_support` conditions; full 135 and half-frame partial regressions stay at 0 diff. |
| V4.5.2 | Development version | Structural convergence release. Moves read-only diagnostics calculations from the Debug rendering layer into the detection layer, reducing reverse dependencies from postprocess into Debug UI; adds shared constants for analysis sources, gap methods, and main review reasons; makes `policy.py` and detection model exports depend directly on common / geometry instead of the core compatibility layer; and removes the Debug renderer's broad detection-pipeline import. It does not intentionally loosen detection thresholds. |
| V4.5.1 | Development version | Structural convergence release. Adds read-only policy views so outer / separator / grid / scoring / calibration / partial / diagnostics parameters have clearer entry points; moves post-detection finalization from CLI into `detection/postprocess.py`; splits per-count candidate generation and final candidate selection into explicit functions; removes active-code legacy aliases and hand-written analysis-source strings; and adds a Debug Analysis Decision summary panel with version, PASS/REVIEW, confidence, outer strategy, analysis source, auto gate, gap evidence, and review reasons. It does not intentionally loosen detection thresholds. |
| V4.5 | Development version | Policy architecture cleanup. The trusted-separator-plus-format-geometry outer proposal is now the general `separator_geometry_outer` layer, with full / partial mode policy. `separator_first` and `separator_geometry` now share separator-band collection and band-sequence tools instead of maintaining duplicate search logic. Report detail now records `outer_candidate_strategy`, making base / content floating / long-axis edge-anchor / separator-first / separator-geometry candidates easier to read. Historical score policy names are moved toward gate semantics. Active behavior stays conservative: only `120-66 partial` uses `separator_geometry_outer_partial_mode=conditional`; other formats stay off. Verification: full `Test/135` is 48 unique rows / 0 diff against V4.4.6; `Test/120/66` partial is 16 unique rows / 0 diff against V4.4.6; half-frame full / partial are both 0 diff; 120-67 has no core-output diff, only one legacy review-reason name normalized. |
| V4.4.6 | Development version | Adds a generic separator-geometry outer candidate, enabled only by the `120-66` policy for now. When the regular partial candidate has suspicious frame aspect, it derives an extra outer candidate from trusted dark separator bands and the current format geometry, then sends that candidate back through the existing separator / edge-pair / content / scoring / review-gate path. It does not modify the already selected result, raise confidence, or promote weak-evidence REVIEW files to PASS. Verification: full `Test/135` is 48 rows / 0 diff against the existing V4.4.6 baseline; `Test/120/66` partial differs from V4.4.5 only on `X5_test_56.tif`, with unchanged status / confidence / review reasons. |
| V4.4.5 | Development version | Retroactively renames the default output folder from `split_output/` to `x5_crop_output/`. Current source, documentation, quick-start text, and locally visible archive snapshots now use the new folder name; CLI help now says `default input/x5_crop_output`. |
| V4.4.4 | Development version | Naming cleanup and diagnostic readability fix: active code no longer uses historical `v2_*` / `diagnostics_v3_6` names; candidate scoring results are now `candidate_decision`, candidate ranking summaries are `candidate_competition`, and diagnostic reports are `diagnostics`. The candidate calibration function is now `calibrate_candidate_decision()`, and the main detection entry is `choose_detection()`. Unused partial-content policy fields were removed. 2-gap separator-first top-k ranking now includes geometry error so it does not prune only by score. Diagnostic records that trigger 50px output bleed can now also draw cyan ticks in ordinary Debug Analysis. |
| V4.4.3 | Development version | Maintenance-noise and local performance cleanup: removes unused legacy constants / helper surfaces; reuses same-image / same-format content mask and bbox intermediates in `content_detection_for_count()`; uses lighter top-k sequence paths for 1-gap / 2-gap separator-first band searches; reuses the labeled original-gray Debug Analysis preview; and makes the half full equal-first + wide-retry path explicit. V4.4.3 also lets diagnostic overlap-risk signals from partial, half-frame, and 120-format paths trigger output-only 50px long-axis bleed. Verification: full `Test/135` is 48 rows / 0 diff against V4.4.2; full `Test/半格`, `Test/半格/partial`, and `Test/120/66` partial differ only by the expected long-axis frame-box expansion from output-only overlap bleed, with status / confidence / outer / gaps unchanged. |
| V4.4.2 | Development version | Conservative performance and old-logic cleanup: removes the legacy content-only partial auto-pass interface; skips content candidates and lower-count attempts after a same-count `partial_safe_extra_frames` separator candidate has auto-passed; prunes invalid separator-first band spacing during sequence generation; adds exact caches for enhanced separator merge and Debug nearby-separator diagnostics. Verification: full `Test/135`, `Test/半格/partial`, `Test/120/66` partial, full `Test/120/67`, and full `Test/半格` are all 0 diff against V4.4.1. |
| V4.4.1 | Development version | Structural cleanup after V4.4: partial `separator-first` defaults back to fallback, while `120-66` and `xpan` keep the more active partial path; content-only partial no longer auto-passes by itself and must go through partial-safe / separator-evidence semantics; floating outer naming is now generic; long-axis edge-anchor uses each candidate outer's local content bbox; 135-dual explicitly disables invalid partial policy. Verification: full `Test/135` is 48 rows / 0 diff against V4.4; `Test/半格/partial` is 5 rows / 0 diff against V4.4; `Test/120/66` partial is 16 rows / 0 diff against V4.4; full `Test/120/67` and full `Test/半格` are both 0 diff against their existing baselines. |
| V4.4 | Development version | Separates full / partial outer proposal responsibilities: full returns to the complete-holder-strip meaning, while partial receives floating outer, separator-first outer, wide retry, and conditional long-axis edge-anchor fallback for non-filled or off-center strips. Full `Test/135` is 48 rows / 0 diff against V4.3; `Test/半格/partial` is 5 rows / 0 diff against V4.3.1; `Test/120/66` partial auto is 15 `approved_auto` / 1 `needs_review`. |
| V4.3.1 | Development version | Adds a `partial_safe_extra_frames` auto-pass gate for partial mode: when real frames are safely covered, content evidence is normal, geometry is stable, no equal gaps are used, and no obvious danger signal is present, the script can accept a few extra empty holder frames instead of reviewing solely because auto count or grid support is imperfect. `Test/半格/partial` changed from 0 `approved_auto` / 5 `needs_review` to 5 `approved_auto` / 0 `needs_review`; full `Test/135` is 48 rows / 0 diff against V4.3. |
| V4.3 | Development version | Organizes the full-mode outer proposal layer: normal outer, floating full, separator-first, and long-axis edge-anchor are all outer candidate strategies that enter the existing separator / edge-pair / content / geometry / review-gate pipeline. The new long-axis edge-anchor covers full strips whose valid frames may start near one long-axis end; it proposes candidates only and does not directly raise confidence. `Test/120/66` is 0 diff against V4.2.9; `Test/半格/full` is 0 diff against V4.2.7. |
| V4.2.10 | Development | Low-risk caching optimization: full-scan separator evidence / profiles, content runs, content-evidence detail, outer/content alignment, separator-first outer candidates, and Debug Analysis preview images are reused within a file run. The cache is global across formats, not 120-66-only, and reuses only exact inputs and candidates without approximating nearby outer boxes. `Test/120/66` is 0 diff against V4.2.9. |
| V4.2.9 | Development | Conservative 120-66 tuning and Debug Analysis readability update: 66 full strips treat low-quality ordinary `edge-pair` gaps more cautiously when no `wide-separator` supports the candidate. Separator / Content evidence panels now show the full scan with the current outer / frame overlay, making ignored evidence outside the selected outer easier to inspect. |
| V4.2.8 | Current stable release | Launcher interaction update: Mac / Windows main launchers ask for count only after partial mode is enabled. Return or `auto` keeps automatic count detection; an allowed number fixes the partial frame count. When partial mode is off, the launcher does not ask for count and keeps the full-strip count for the selected format. Detection logic is unchanged. |
| V4.2.7 | Development | Adds half-frame full stable-grid support: `half_stable_grid_support` can accept stable geometric gap fill when hard+grid covers all gaps, no equal fallback is used, at least 35% of gaps have hard/wide evidence, frame widths are very stable, content support is normal, and a half stable-grid joint-score floor is met. `Test/半格/full` is now 10 `approved_auto` / 0 `needs_review`; compared with V4.2.6, only `X5_00062` and `X5_00063` changed from REVIEW to PASS, with unchanged boxes and gaps. |
| V4.2.6 | Development | Second half-frame full-strip wide-separator tuning pass: `half_wide_geometry_support` now uses a majority-wide rule, requiring wide/hard gaps to cover at least 60% of expected separators, no equal fallback, stable frame widths, normal content support, and a half-wide joint-score floor. When a content candidate has `content_run_count_mismatch` and a plausible separator candidate exists, REVIEW display prefers the separator candidate. `Test/半格/full` is now 8 `approved_auto` / 2 `needs_review`; newly approved compared with V4.2.5 are `X5_00056` and `X5_00058`, while `X5_00063` stays REVIEW but no longer shows the misleading content candidate. |
| V4.2.5 | Development | Half-frame full-strip wide-separator tuning: the ordinary half-frame path keeps its existing equal/grid behavior, while the wide retry branch may recognize wider dark gutters as `wide-separator`. The new `half_wide_geometry_support` gate requires wide/hard gaps to cover at least 80% of expected separators, no equal fallback, stable frame widths, normal content support, and a joint score above threshold. `Test/半格/full` changed from 3 `approved_auto` / 7 `needs_review` to 6 `approved_auto` / 4 `needs_review`; newly approved files are `X5_00059`, `X5_00060`, and `X5_00061`; `X5_00056` and `X5_00062` remain conservative REVIEW. |
| V4.2.4 | Development | Behavior-preserving separator-first fallback cleanup: fallback now builds only `separator_first_*` outer candidates instead of rerunning ordinary outer candidates in the same retry. If no separator-first outer is generated, no retry-used marker is written and the detector returns to the existing content / review flow. `separator_first_outer_mode` is now validated as `off` / `fallback` / `always`. Verification: 135, 120-67, half-frame, and 120-66 all have 0 diff against their matching V4.2.x baselines. |
| V4.2.3 | Development | Generalizes the separator-first outer proposal from a 120-66-only path into a format-aware framework. 120-66 keeps using it in `always` mode; 135, half-frame, xpan, 120-645, and 120-67 use `fallback` mode, so it is tried only when the normal separator / wide-retry path does not satisfy the auto gate. 135-dual remains excluded. Verification: 120-66 full is 16 `approved_auto` / 0 `needs_review`; 135 is 0 diff against V4.2.2, 120-67 is 0 diff against V4.2.2, and half-frame is 0 diff against the V4.2 baseline. |
| V4.2.2 | Development | Adds a separator-first outer proposal for 120-66 full: it first chooses two clear internal dark separator bands from the global profile, then infers the outer from three 1:1 frames. The candidate still goes through the existing separator / edge-pair / scoring / review gate, and content-only still cannot auto-pass. Current `Test/120/66` result is 16 `approved_auto` / 0 `needs_review`; 135 is 0 diff against V4.2.1, and 120-67 is 0 diff against V4.2.1. |
| V4.2.1 | Development | Rebuilds 120-66 full outer candidate generation: count stays fixed at 3, but the valid outer may float inside the full scan. Geometry is explained as three 6x6 frames plus total separator width, and old 66 outputs are no longer protected as a baseline. 120-66 full test result was 13 `approved_auto` / 3 `needs_review`; 135 was 0 diff against V4.2, and 120-67 was 0 diff against V4.2. |
| V4.2 | Development | Adds a shared full-format geometry model: `count * frame_aspect + separator_total / outer_short` explains the expected outer ratio. Also adds a conservative stage-C outer correction retry that only moves the outer when complete hard separators explain the geometry, the correction is small, and content is not cut. Full 135, half, 120-66, and 120-67 regression checks are 0 diff against V4.1.3. |
| V4.1.3 | Current Stable Release | Behavior-preserving cleanup: moves the 120 hard-full confidence floor from scoring into candidate calibration, extracts shared 120 format policy, unifies the outer retry entry point, and makes the 120-67 short-axis outer trigger more semantic. Full 135, half, 120-66, and 120-67 regression checks are 0 diff against V4.1.2. |
| V4.1.2 | Development | Narrow 120-67 short-axis outer fix: when hard separators are reliable, content aspect is normal, and short-axis content slack is clearly high, 120-67 can use the existing content-aligned outer retry. This fixes the loose short-axis outer on `Test/120/67/3.tif`. |
| V4.1.1 | Development | Narrow 120-67 fix: when the normal separator candidate fails the auto gate, 120-67 can use a conservative `wide-separator` retry. This fixes `Test/120/67/2.tif`, where the first wide separator had fallen back to equal. |
| V4.1 | Development | 120-66 / 120-67 tuning: 66 can retry short-axis outer expansion when hard separators are reliable, 67 horizontal aspect is corrected to 5:4, and 120-67 edge-pair / hard-separator candidates get a more suitable confidence floor. Content-only still cannot auto-pass. |
| V4.0.1 | Historical Stable Release | 135 wide-spacing compatibility update: the default narrow-separator path keeps V4.0 behavior; only when the normal separator candidate fails the auto gate does the detector enable the formal `wide-separator` branch. The goal is to support clear but wider 135 gutters without changing existing `Test/135` output. |
| V4.0 | Previous Stable Release | Bold modular rewrite: root `X5_Crop.py` is thin, while detection, I/O, geometry, evidence, Debug, report, deskew, and CLI responsibilities now live in dedicated `x5crop/` modules; `core.py` is only a compatibility export surface. Adds a standalone release-script builder so Release users still need only the script and launcher. A full 135 default-deskew dry run compared with V3.9 had 0 diffs. |
| V3.9 | Development | Structural cleanup: moves the remaining outer mask profiles, post-detection confidence caps, deskew span skip, frame-fit small-pixel tolerances, separator gate mode, and outer retry switch into policy / format-aware configuration. A full 135 default-deskew dry run compared with V3.7 had 0 diffs. |
| V3.7 | Development | Merges the frame-size fit pipeline: cuts-level equal-width correction becomes geometry fallback, box-level same-frame fitting becomes edge-evidence fit, and a single entry point chooses the layer. The goal is clearer frame fitting after edge-pair expanded across formats, while preserving existing output. |
| V3.6.12 | Development | Tunes non-135 edge-pair parameters with full `Test/120` and half-frame dry runs: 120-66 / 120-67 can now recognize wider, lower-background 120 separator evidence without loosening PASS. |
| V3.6.11 | Development | Extends `edge-pair` into format-aware full-strip logic; 135 keeps its original parameters, while other formats enable it conservatively. |
| V3.6.10 | Development | Low-risk cleanup: removes unused code, fixes CLI help and stale diagnostic wording, with no detection-flow change. |
| V3.6.9 | Development | Unifies active grid protection and diagnostics around lightweight hard-gap trust, reducing the two-track red-gap trust conflict. |
| V3.6.8 | Development | Replaces the exact single-anchor gate with `lucky_pass_risk_score`, so the rule no longer reads as tailored to one image. |
| V3.6.7 | Development | Promotes nearby separator checks into a narrow correction and adds a single-anchor lucky PASS review gate. |
| V3.6.6 | Development | Adds hard-gap trust, nearby separator checks, and a limited strong-separator anti-grid-override rule. |
| V3.6.5 | Development | Diagnostics mode can use up to 4 workers; normal runs still cap at 2. Detection logic is unchanged. |
| V3.6.4 | Development | Returns to the V3.6.2 detection baseline and adds a narrow one-sided long-axis white-edge outer tightening rule when both end hard separators are reliable. |
| V3.6.3 | Paused / reference direction | Treats overlap / near-overlap as difficult: strong overlap-risk model gaps in 135 full strips are sent to REVIEW. This direction is paused. |
| V3.6.2 | Previous Stable Release | Folds the low-value `equal-broad-region` method into ordinary `equal`, and shrinks hard fallback into a review-only equal split fallback. Overlap, near-overlap, and locally irregular spacing can still be misdetected. |
| V3.6.1 | Development | Continues the diagnostic layer: diagnostic report data and Debug Analysis diagnostic ticks are only generated with explicit `--diagnostics`; normal launchers do not enable diagnostics. |
| V3.6 | Development | Diagnostic cleanup from the V3.3.1 output baseline. Adds read-only hard-gap trust and overlap/continuous-content diagnostics without changing V3.3.1 output. |
| V3.5 | Paused / rolled back | Hard-gap semantic validation experiment. Removed from the active script after accuracy regressions. |
| V3.4.2 | Paused / rolled back | Local grid segment experiment. Removed from the active script after accuracy regressions. |
| V3.4.1 | Paused / reference direction | Strong hard separators stay authoritative when they conflict with robust grid. This direction remains useful, but the active baseline is back to V3.3.1. |
| V3.4 | Simplification experiment direction | Tried removing low-value enhanced separator logic and simplifying candidate generation. The current V3.9 script still keeps the conservative `--analysis` enhanced separator assist. |
| V3.3.2 | Development | Conservative overlap-like gap handling. |
| V3.3.1 | Stable Release / V3.6 output baseline | Stable packaged release based on V3/V3.2 style detection plus output-only bleed. |
| V3.3 | Development | Detection bleed and output bleed separated. |
| V3.2 | Development | Returned to V3-style detection after V3.1.x regressions. |
| V3.1.x | Experimental | Aggressive outer/gap rescue ideas. Not stable enough. |
| V3.0 | Baseline | Main X5 Crop script and user workflow foundation. |

### Current Active: V4.7

V4.7 is a clean-room source rewrite. It does not intentionally loosen detector
thresholds; instead, it removes the old compatibility residue left after the
V4.6 policy refactor and verifies behavior against the V4.5.4 golden reports.

Main changes:

- Adds root-level `ARCHITECTURE.md` as the single bilingual developer
  architecture guide, so the source layout, policy ownership, format/mode
  isolation, and regression boundaries are readable from the GitHub root. The
  redundant `docs/ARCHITECTURE.md` mirror was removed to avoid duplicate
  maintenance.
- Removes old `x5crop/common.py`, `x5crop/policy.py`, `x5crop/core.py`, and
  root-level `x5crop/io.py` / `x5crop/geometry.py` / `x5crop/regression.py`
  compatibility layers.
- Removes `FormatTuning` from active source. `x5crop/policies/parameters.py`
  is now a thin lookup/public export, and concrete format parameters live under
  `x5crop/policies/presets/`.
- Adds capability-specific `FormatParameters` views for partial counts,
  separator gates, leading-grid separator failure, separator geometry support,
  gap search, hard-gap trust, nearby separator correction, robust grid, wide
  retry, outer strategy, short-axis aspect retry, partial holder, scoring
  calibration, candidate competition, content evidence, debug gap overlay, nearby separator
  diagnostics, overlap-risk diagnostics, lucky-pass risk, and postprocess. The
  policy factory now builds `DetectionPolicy` from those grouped views, and
  candidate calibration, wide-retry, content-evidence runtime, Debug Analysis
  gap overlay, nearby separator diagnostics, overlap-risk diagnostics,
  gap search, hard-gap trust, nearby separator correction, robust grid,
  short-axis aspect retry, lucky-pass risk diagnostics, postprocess final caps,
  and leading-grid failure gates read their caps, weights, retry width,
  evidence thresholds, overlay line settings, nearby search thresholds,
  separator search radius/width/guard/score, wide separator acceptance
  thresholds, nearby correction thresholds, robust-grid thresholds, short-axis
  aspect retry error/aspect/margins, overlap risk thresholds, trust thresholds,
  risk weights, final REVIEW caps, and gate limits from grouped policy views;
  remaining flat fields stay only as a detector/geometry runtime migration
  surface.
- Narrows `x5crop/policies/registry.py` to policy resolve/cache. Each
  `format_*.py` module owns its format/mode preset, including gate profile,
  edge-pair, frame-fit, dark-band, diagnostics, and notes.
- Moves `FrameFitPolicy` into `x5crop/policies/base.py`, owned by
  `DetectionPolicy.frame_fit`; geometry no longer builds a
  `frame_fit_policy(fmt, strip_mode)` fallback.
- Keeps `SeparatorEdgePairPolicy` under `DetectionPolicy.separator`; geometry
  edge-pair refinement requires the caller to pass the policy object and no
  longer keeps an `edge_pair_params_for_format()` fallback.
- Shrinks `detection/pipeline.py` to orchestration by moving candidate
  build/run, cache keys, candidate calibration, hard fallback, and partial edge
  hints into focused modules.
- Splits `geometry/core.py` into `boxes.py`, `layout.py`, `outer_boxes.py`,
  `gaps.py`, `separator_profile.py`, `frame_fit.py`, and
  `output_adjustment.py`.
- Moves the 120-66 oversized separator-band behavior behind the
  `OuterPolicy.separator_outer_allow_oversized_band` capability.
- Moves separator-derived outer candidate gap-search width override into
  `OuterPolicy.separator_gap_search_max_width_ratio`; `candidate_run.py` no
  longer reads the flat `separator_first_outer_gap_max_width_ratio` field
  directly.
- Moves separator-first / separator-geometry outer proposer band thresholds,
  sequence limits, source counts, margin ratios, and candidate limits into
  `OuterPolicy.separator_outer_band` / `separator_geometry_outer`;
  `detection/outer.py` no longer reads flat `separator_first_outer_*` or
  `separator_geometry_outer_*` preset fields directly.
- Moves full-strip grid-based outer refinement thresholds into
  `OuterPolicy.grid_refine`; `candidate_build.py` no longer reads flat
  `grid_outer_refine_*` preset fields directly.
- Moves format-geometry outer retry thresholds into
  `OuterPolicy.format_geometry_retry`; `outer_retry.py` no longer reads flat
  `format_geometry_outer_retry_*` preset fields directly.
- Moves short-axis aspect outer retry thresholds into
  `OuterPolicy.short_axis_aspect_retry`. The capability remains off by default
  and is currently active only for 120-66 full; `outer_retry.py` no longer reads
  flat `short_axis_aspect_retry_*` preset fields directly.
- Moves outer/content alignment thresholds into
  `OuterPolicy.content_alignment`; `outer_retry.py` and `postprocess.py` no
  longer read flat `outer_align_*` preset fields directly.
- Moves base outer candidate bw / white-x / mask-profile thresholds, margins,
  and candidate area limits into `OuterPolicy.base_candidates`;
  `geometry/outer_boxes.py` no longer reads flat `outer_*` preset fields or
  resolves parameters by format name.
- Moves partial-strip edge hint thresholds into `PartialEdgeHintPolicy`;
  `detection/partial.py` and `candidate_build.py` no longer read flat
  `partial_edge_hint_*` preset fields directly.
- Makes TIFF I/O, evidence/deskew image helpers, diagnostics, package exports,
  and policy imports explicit instead of relying on old `common` or wildcard
  re-export surfaces.
- Moves Debug Analysis separator-panel gap overlay tolerances, tick length, and
  line widths into `DiagnosticsPolicy.debug_gap_overlay`; `debug/render.py` no
  longer reads flat `debug_gap_*` preset fields or hard-codes gap tick length
  directly.
- Moves overlap-risk diagnostic thresholds into
  `DiagnosticsPolicy.overlap_bleed_risk`; `detection/diagnostics.py` no longer
  reads flat `diagnostic_overlap_*` preset fields directly.
- Moves candidate calibration weights, separator source bias, hard-full
  confidence floor, and no-auto caps into `ScoringPolicy`; `calibration.py` and
  `scoring.py` no longer read flat `scoring_calibration` directly.
- Moves base detector scoring weights, full-geometry floors, partial caps,
  outer-too-large caps, and low-confidence thresholds into
  `ScoringPolicy.base_detection`; `score_detection()` no longer reads flat
  `score_*` fields directly.
- Moves content-support score norms, weights, and support gates used by
  candidate calibration into `ContentPolicy`; `content_support_score()` no
  longer reads flat `content_support_*` fields directly.
- Moves content evidence thresholds, content-run profile, content mask outer,
  and content-only candidate confidence caps into `ContentPolicy.evidence`,
  `profile`, `mask`, and `candidate`; `detection/content.py` no longer reads
  flat `content_*` preset fields or runtime `FormatParameters` directly.
- Adds `FormatParameters.content_evidence`, `content_profile`, `content_mask`,
  `content_candidate`, and `content_support` preset-side capability views for
  constructing `ContentPolicy`; policy construction no longer reads the
  corresponding flat content fields directly.
- Moves geometry-support score width/outer/aspect/count norms, weights, and
  outer-area bounds used by candidate calibration into
  `ScoringPolicy.geometry_support`; `geometry_support_score()` no longer reads
  flat `geometry_support_*`, `geometry_width_cv_norm`,
  `content_support_aspect_norm`, or score outer-area fields directly.
- Adds `FormatParameters.geometry_support_score` as the preset-side capability
  view for constructing `ScoringPolicy.geometry_support`; policy construction
  no longer reads flat geometry-support score fields directly.
- Moves separator-support hard/model weights, grid/equal credit, and
  single-frame cap into `ScoringPolicy.separator_support`;
  `separator_support_score()` no longer reads flat `separator_model_*` or
  `separator_support_*` fields directly.
- Adds `FormatParameters.content_floating_outer`, `edge_anchor_outer`,
  `base_outer_candidates`, `separator_outer_band`, and
  `separator_geometry_outer` preset-side capability views for constructing
  outer proposal policy objects; policy construction no longer reads those flat
  outer proposal fields directly.
- Moves 120-66 partial holder frame mean / coverage / aspect-error checks into
  `PartialHolderPolicy`; `partial_holder.py` no longer reads
  `policy.parameters.content_evidence` directly.
- Moves hard-gap trust thresholds into `SeparatorPolicy.hard_gap_trust`;
  robust-grid hard separator protection and `detection/diagnostics.py` no
  longer read flat `hard_trust_*` preset fields directly.
- Moves active nearby-separator correction thresholds into
  `SeparatorPolicy.nearby_correction`; `candidate_build.py` and
  `geometry/gaps.py` no longer read flat `nearby_*` preset fields to move
  candidate gaps.
- Moves robust-grid and hard-gap constraining thresholds into
  `SeparatorPolicy.robust_grid`; `geometry/gaps.py`, `geometry/core.py`, and
  scoring no longer read flat `constrain_*` / `robust_*` preset fields
  directly.
- Moves base separator gap-search thresholds into
  `SeparatorPolicy.gap_search`; `geometry/gaps.py`, `geometry/core.py`,
  `candidate_build.py`, `candidate_run.py`, and `outer_retry.py` no longer read
  flat `gap_*` / `wide_gap_min_*` preset fields directly.
- Moves separator profile and edge-refine profile generation thresholds into
  `SeparatorPolicy.profile` / `edge_refine_profile`, including smoothing,
  weights, and background thresholds; `geometry/separator_profile.py` no longer
  reads flat `separator_profile_*` / `edge_refine_*` preset fields directly, and
  detection plus read-only diagnostics pass the selected policy explicitly.
  Profile and edge-refine caches are keyed by the selected policy.
- Moves enhanced separator analysis thresholds into `SeparatorPolicy.enhanced`,
  including the low-score trigger, accepted score, width, and shift limits;
  `geometry/core.py` no longer reads flat `enhanced_*` preset fields directly,
  and the policy factory reads the `enhanced_separator` parameter group.
- Moves the confidence cap for candidates containing wide separator gaps into
  `SeparatorPolicy.wide_separator_confidence_cap`; `calibration.py` no longer
  reads flat wide-retry confidence-cap parameters directly.
- Moves final postprocess confidence caps for content aspect conflict, low
  content evidence, outer/content mismatch, and lucky-pass risk into
  `PostprocessPolicy`; `finalize_detection_decision()` no longer accepts a flat
  tuning object for those caps.
- Moves approved-auto output geometry extension limits into
  `PostprocessPolicy.approved_geometry_adjustment`; `geometry/output_adjustment.py`
  no longer reads flat `approved_adjust_*` preset fields directly.
- Moves overlap-risk output long-axis bleed into
  `OutputPolicy.overlap_risk_long_axis_bleed`; postprocess and cached workflow
  reuse no longer hard-code the 50px value.
- Moves full-strip output edge guard ratio and clamp bounds into
  `OutputPolicy.edge_bleed_protection`; `geometry/output_adjustment.py` no
  longer carries hard-coded edge guard values.
- Moves detection-time bleed defaults into
  `OutputPolicy.detection_long_axis_bleed` /
  `detection_short_axis_bleed`; `detection_geometry_config()` no longer
  hard-codes 0/0.
- Moves content-floating and long-axis edge-anchor outer proposal thresholds into
  `OuterPolicy.content_floating_outer` and `edge_anchor_outer`, including content
  thresholds, margins, ratio extras, and candidate limits.
- Preserves V4.5.4 scoring semantics: output frames may still use edge-evidence
  frame fit, while nearby separator correction only uses geometry fallback score
  as a narrow confidence limiter.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.7`.
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/*/*.py x5crop/*/*/*.py` passed.
- The legacy-residue scan has no hits for `common`, `FormatTuning`,
  `format_tuning`, `separator_gate_mode`, `score_gate_135`, `separator_135`,
  `separator_half`, wildcard imports, `edge_pair_params_for_format`, or
  `frame_fit_policy`.
- `git diff --check` passed.
- Policy smoke resolved all 14 format / strip-mode policies.
- V4.7 content policy runtime cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_content_policy_20260701_run1`. The seven local V4.5.4
  golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`, with 103 Debug
  Analysis JPGs generated.
- V4.7 selection policy cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_selection_policy_20260701_run3`. The seven local V4.5.4
  golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. The 14-policy smoke
  confirmed only `half_full` enables `SelectionPolicy.content_mismatch_review`.
- V4.7 content-candidate run policy cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_content_candidate_run_policy_20260701_run1`. The seven
  local V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. The 14-policy smoke
  confirmed every format/mode resolves `CandidateRunPolicy.content_candidate`.
- V4.7 postprocess reason policy cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_postprocess_reason_policy_20260701_run1`. The seven local
  V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. The 14-policy smoke
  confirmed every format/mode resolves postprocess review/detail reasons through
  `PostprocessPolicy`.
- V4.7 separator-incomplete reason cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_separator_uncertain_reason_policy_20260701_run1`. The
  seven local V4.5.4 golden core comparisons were 0 diff for `status`,
  `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. The
  14-policy smoke confirmed every format/mode resolves the semantic
  `separator_evidence_incomplete` reason id through
  `ScoringPolicy.base_detection`; active runtime no longer emits the old
  `120_separator_uncertain` reason name.
- V4.7 implicit-135 default cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_no_implicit_135_default_20260701_run1`. The seven local
  V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. Low-level deskew,
  gap, separator profile cache, content profile, and diagnostics helpers now
  require explicit `format_name` and no longer keep an implicit `"135"` default.
- V4.7 dark-band mode-preset cleanup dry-run regressions were written to
  `/private/tmp/x5_v47_dark_band_mode_preset_20260701_run1`. The seven local
  V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. `ModePolicyPreset.dark_band`
  now groups dark-band mode, full-selection, and oversized separator-band
  enablement; the 14-policy smoke confirmed it still resolves only for
  `120_66_full` and `120_66_partial`.
- V4.7 separator-profile parameter-view cleanup dry-run regressions were written
  to `/private/tmp/x5_v47_profile_parameter_views_20260701_run1`. The seven
  local V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. Added
  `SeparatorProfileParameters` / `EdgeRefineProfileParameters` plus
  `FormatParameters.separator_profile` / `edge_refine_profile` capability views,
  so policy construction no longer reads flat `separator_profile_*` /
  `edge_refine_*` fields directly.
- V4.7 content / geometry-support parameter-view cleanup dry-run regressions
  were written to `/private/tmp/x5_v47_content_parameter_views_20260701_run1`.
  The seven local V4.5.4 golden core comparisons were 0 diff for `status`,
  `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. Added
  `ContentProfileParameters` / `ContentMaskParameters` /
  `ContentCandidateParameters` / `ContentSupportParameters` /
  `GeometrySupportScoreParameters` plus the matching `FormatParameters`
  capability views, so policy construction no longer reads those flat content /
  geometry-support fields directly.
- V4.7 outer-proposal parameter-view cleanup dry-run regressions were written
  to `/private/tmp/x5_v47_outer_parameter_views_20260701_run1`. The seven local
  V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. Added
  `ContentFloatingOuterParameters` / `EdgeAnchorOuterParameters` /
  `BaseOuterCandidateParameters` / `SeparatorOuterBandParameters` /
  `SeparatorGeometryOuterParameters` plus the matching `FormatParameters`
  capability views, so policy construction no longer reads those flat outer
  proposal fields directly.
- V4.7 final policy-readiness dry-run regressions were written to
  `/private/tmp/x5_v47_final_policy_readiness_20260701_run1`. The seven local
  V4.5.4 golden core comparisons were 0 diff for `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`. Added
  `DebugGapOverlayPolicy.tick_length_ratio` / `tick_length_min`, so Debug
  Analysis gap tick length is policy-owned. A focused Debug Analysis smoke wrote
  `/private/tmp/x5_v47_final_debug_smoke_20260701/_debug_analysis/X5_00041_debug_analysis.jpg`
  as a 1679x876 RGB JPEG, with the three panel titles and Debug gap tick
  parameters resolved through policy.
- Default golden compare still reports 196 metadata-only diffs in
  `detail.policy` / `report_schema`, because V4.5.4 golden rows do not contain
  V4.7 policy/report-schema metadata.
- A policy-factory flat-field residue scan has no direct hits for separator
  gate, score gate, partial-safe holder, candidate competition, calibration
  caps, outer strategy, wide retry, outer retry, leading-grid failure, nearby
  separator diagnostics, overlap-risk diagnostics, hard-gap trust, nearby
  separator correction, robust grid, gap search, or lucky-pass risk
  parameters; those entries now come from grouped
  `FormatParameters` capability views.
- A scoring runtime residue scan has no direct hits for
  `tuning.scoring_calibration`, `policy.parameters.scoring_calibration`, or
  `scoring_calibration` under active detection / geometry / workflow runtime;
  those paths now read `ScoringPolicy`.
- A base scoring residue scan has no direct `score_*` flat-field reads in
  `score_detection()`; those paths now read `ScoringPolicy.base_detection`.
- A content-support scoring residue scan has no direct hits for
  `content_conf_*` or `content_support_*` flat-field reads in
  `content_support_score()` / candidate calibration; those paths now read
  `ContentPolicy`.
- A content runtime residue scan has no hits in `detection/content.py` for
  `format_parameters()`, `tuning.content*`, or `policy.parameters`; content
  evidence, profile, mask, and content-only candidate confidence now read
  `ContentPolicy` sub-policies.
- A geometry-support scoring residue scan has no direct hits for
  `geometry_support_*`, `geometry_width_cv_norm`,
  `content_support_aspect_norm`, or score outer-area flat-field reads in
  `geometry_support_score()` / candidate calibration; those paths now read
  `ScoringPolicy.geometry_support`.
- A separator-support scoring residue scan has no direct hits for
  `separator_model_*` or `separator_support_*` flat-field reads in
  `separator_support_score()` / candidate calibration; those paths now read
  `ScoringPolicy.separator_support`.
- A wide-retry / content-evidence runtime residue scan has no direct hits for
  `tuning.wide_retry`, `tuning.wide_gap_retry_*`,
  `tuning.wide_gap_confidence_cap`, `tuning.content_evidence_*`, or
  `format_parameters(...).content_evidence_*`; those paths now read
  `SeparatorPolicy.wide_separator_confidence_cap`, `wide_retry`, and
  `content_evidence` grouped views.
- A partial-holder frame-content residue scan has no direct
  `policy.parameters.content_evidence` hits in
  `x5crop/detection/partial_holder.py`; frame aspect conflict checks now read
  `PartialHolderPolicy`.
- A candidate-run separator outer gap override residue scan has no direct
  `format_parameters()` or `separator_first_outer_gap_max_width_ratio` hits in
  `x5crop/detection/candidate_run.py`; runtime now reads
  `OuterPolicy.separator_gap_search_max_width_ratio`.
- A separator-derived outer proposer residue scan has no direct
  `FormatParameters`, `format_parameters()`, `tuning.*`,
  `separator_first_outer_*`, or `separator_geometry_outer_*` flat-field reads in
  `x5crop/detection/outer.py`; runtime now reads
  `OuterPolicy.separator_outer_band`, `OuterPolicy.separator_geometry_outer`,
  and `SeparatorPolicy.gap_search`.
- A base outer candidate residue scan has no direct `FormatParameters`,
  `format_parameters()`, `tuning.*`, or flat `outer_*` candidate-threshold reads
  in `x5crop/geometry/outer_boxes.py`, `x5crop/detection/outer.py`, or
  `x5crop/detection/dual_lane.py`; runtime now reads
  `OuterPolicy.base_candidates`.
- A separator profile residue scan has no direct `format_parameters()`,
  `tuning.*`, `separator_profile_*`, or `edge_refine_*` flat-field reads in
  `x5crop/geometry/separator_profile.py`, `x5crop/detection/candidate_build.py`,
  `x5crop/detection/outer.py`, or `x5crop/detection/diagnostics.py`; runtime now
  reads `SeparatorPolicy.profile` and `SeparatorPolicy.edge_refine_profile`, and
  cache keys include the selected profile policy.
- An enhanced separator residue scan has no direct `format_parameters()`,
  `tuning.*`, or flat `enhanced_*` preset-field reads in `x5crop/geometry/core.py`
  or `x5crop/detection/candidate_build.py`; runtime now reads
  `SeparatorPolicy.enhanced`, and the policy factory reads the
  `enhanced_separator` parameter group.
- A grid outer-refine residue scan has no direct `grid_outer_refine_*` hits
  outside `x5crop/policies/**`; runtime now reads `OuterPolicy.grid_refine`.
- A format-geometry retry residue scan has no direct
  `format_geometry_outer_retry_*` hits outside `x5crop/policies/**`; runtime
  now reads `OuterPolicy.format_geometry_retry`.
- A short-axis aspect retry residue scan has no direct
  `short_axis_aspect_retry_*` hits in `x5crop/detection/outer_retry.py`;
  runtime now reads `OuterPolicy.short_axis_aspect_retry`.
- An outer content-alignment residue scan has no direct `outer_align_*` hits in
  `x5crop/detection/outer_retry.py` or `x5crop/detection/postprocess.py`;
  runtime now reads `OuterPolicy.content_alignment`.
- A content-floating / edge-anchor outer residue scan has no direct
  `floating_outer_*` or `long_axis_edge_anchor_*` hits in
  `x5crop/detection/outer.py`; runtime now reads
  `OuterPolicy.content_floating_outer` and `OuterPolicy.edge_anchor_outer`.
- A partial edge-hint residue scan has no direct `partial_edge_hint_*` hits
  outside `x5crop/policies/**`; runtime now reads `PartialEdgeHintPolicy`.
- A Debug Analysis gap-overlay residue scan has no direct `format_parameters()`,
  `debug_gap_*`, or hard-coded gap tick-length hits in
  `x5crop/debug/render.py`; rendering now reads
  `DiagnosticsPolicy.debug_gap_overlay`.
- A postprocess-cap residue scan has no direct `tuning.post_*_cap` hits in
  `x5crop/detection/postprocess.py`; final decision caps now read from
  `PostprocessPolicy`.
- An approved geometry adjustment residue scan has no direct
  `approved_adjust_*` hits outside `x5crop/policies/**`; runtime now reads
  `PostprocessPolicy.approved_geometry_adjustment`.
- An overlap-risk output bleed residue scan has no active-runtime
  `max(int(config.bleed_x), 50)` hard-code; runtime now reads
  `OutputPolicy.overlap_risk_long_axis_bleed`.
- An edge bleed protection residue scan has no active-runtime hard-coded
  `max(70.0, min(120.0, nominal * 0.0150))` style guard; runtime now reads
  `OutputPolicy.edge_bleed_protection`.
- A detection bleed residue scan has no active-runtime `bleed_x=0` /
  `bleed_y=0` hard-code; runtime now reads `OutputPolicy.detection_*_bleed`.
- A 135 Debug Analysis smoke generated
  `/private/tmp/x5_v47_final_debug_smoke_20260701/_debug_analysis/X5_00041_debug_analysis.jpg`
  as a 1679x876 RGB JPEG with policy-owned three-panel titles and Debug gap
  tick parameters.

Not verified:

- Default-deskew export timing.
- `xpan`, `120-645`, and `135-dual` full sample comparisons, because local
  golden reports were not listed.
- Release package generation.

### V4.6

V4.6 is a policy refactor. It does not intentionally loosen detector
thresholds; instead, it organizes the verified V4.5.4 behavior behind explicit
format / strip-mode policy surfaces so future tuning can focus on one format
and mode at a time.

Main changes:

- The target module layout now exists: `app.py`, `config.py`, `formats.py`,
  plus package entry points for I/O, image, geometry, detection, diagnostics,
  export, and regression. The old `x5crop/core.py` compatibility layer has
  been removed.
- Adds the `x5crop/policies/` package. Shared interfaces live in `base.py`,
  the registry lives in `registry.py`, and each supported format has a small
  dedicated policy module.
- Each `DetectionPolicy` explicitly contains count, outer, separator, content,
  frame-fit, gate, scoring, selection, postprocess, output, and diagnostics
  policy surfaces.
- `x5crop/io.py`, `x5crop/geometry.py`, and `x5crop/regression.py` are now
  `x5crop/io/tiff.py`, `x5crop/geometry/core.py`, and
  `x5crop/regression/compare.py`.
- Detection now has focused entry modules for context, outer proposals,
  separator evidence, content evidence, candidates, scoring, gates, selection,
  and report schema.
- `scoring.py`, `gates.py`, and `selection.py` now own real implementation
  instead of only re-exporting from `pipeline.py`: candidate support scoring,
  half geometry support, separator hard-evidence gates, candidate ranking, and
  final selection competition have moved out of the pipeline module.
- `content.py` now owns real content evidence and content-primary candidate
  implementation: `content_evidence_detail()`, content profile runs, content
  mask outer, and `content_detection_for_count()` have moved out of
  `pipeline.py`.
- `outer.py` now owns real outer proposal implementation instead of only
  re-exporting from `pipeline.py`: `OuterProposalStrategy`, policy strategy
  planning, floating outer, edge-anchor outer, separator-first /
  separator-geometry outer, and 120-66 dark-band outer proposers have moved
  out of the pipeline module. Report/detail outer strategy names now use
  `content_outer`, `edge_anchor_outer`, `separator_outer`,
  `separator_geometry_outer`, `dark_band_outer`, `content_aligned_retry`,
  `format_geometry_retry`, and `short_axis_retry`.
- `candidates.py` now owns independent candidate helpers: count planning, wide
  retry checks, and candidate rank helpers have moved out of `pipeline.py` and
  read count plans from the current format / strip-mode policy.
- `separator.py` now owns the 120-66 dark-band gap evidence helper;
  `dark_band_gaps_for_outer()` has moved out of `pipeline.py`.
- The detection runtime now gets full / partial count plans, outer proposal
  strategy, dark-band enablement, separator gate mode, partial-safe gate
  constraints, candidate-selection parameters, and postprocess policy from
  `DetectionPolicy`, while preserving V4.5.4 output behavior.
- Selected detections write `detail.policy` to reports, and the CLI startup
  summary prints the active policy id, such as `120_66_partial`.
- Debug Analysis keeps a compact three-panel layout with Original gray, Debug
  boxes, and Separator evidence.
- `split_report.jsonl` rows now include a top-level `report_schema` object with
  `result`, `selected_candidate`, `candidate_table`, `policy`, `evidence`,
  `gates`, `postprocess`, and `output`, while retaining the previous fields for
  regression comparison and cache reuse.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/io/*.py x5crop/geometry/*.py x5crop/image/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/diagnostics/*.py x5crop/export/*.py x5crop/policies/*.py x5crop/regression/*.py` passed.
- After the real outer proposer migration, the seven V4.5.4 golden comparisons
  were rerun under `/private/tmp/x5_v46_outer_impl_*`; `status`, `confidence`,
  `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` all remained 0 core
  diff.
- After the candidates helper migration, the same seven V4.5.4 golden
  comparisons were rerun under `/private/tmp/x5_v46_candidates_split_*`;
  `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and
  `gaps` all remained 0 core diff.
- After moving `dark_band_gaps_for_outer()` to `separator.py`, `Test/120/66`
  partial was rerun under `/private/tmp/x5_v46_separator_split_66_partial`;
  the same core fields remained 0 diff against the V4.5.4 partial baseline.

### V4.5.4

V4.5.4 is a 120-66 wide dark-separator improvement. It turns the current sample
findings into format-specific behavior: because 66 separators are usually broad
dark bands, partial and full 120-66 detections should let those bands and the
three 1:1 frame geometry constrain each other instead of letting
content-floating, the old base outer, or weak edge-pair evidence dominate by
itself.

Main changes:

- Adds the `separator_dark_band_outer` candidate source, deriving a 120-66
  outer from two broad dark separator bands and three square frames.
- Tightens 120-66 partial `partial_safe_extra_frames`: it now requires at least
  two wide-like gaps, checks whether content-floating candidates cut into
  leading-edge content, and verifies per-frame content evidence for all three
  frames.
- Lets 120-66 full use the same wide dark-band outer candidate without using
  partial's extra-holder tolerance. The dark-band candidate can take over only
  when the current full outer needs help and the dark-band candidate has normal
  content support, enough hard gaps, and no equal gap.
- Reports and Debug Analysis can now show `separator_dark_band_outer` as an
  outer-candidate strategy.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `Test/120/66` partial dry run with Debug Analysis and diagnostics: 16 ok / 0 failed / 16 approved / 0 review. `X5_test_51.tif` moves from `needs_review` to `approved_auto`.
- `Test/120/66` full dry run with Debug Analysis and diagnostics: 16 ok / 0 failed / 16 approved / 0 review. Compared with the previous full guard run, `X5_test_43.tif`, `X5_test_48.tif`, and `X5_test_51.tif` move from review to pass; 48 / 51 are taken over by `separator_dark_band_outer` because the old outer had abnormal content geometry.
- Full local diagnostics were rerun using the naming rule: full outputs use `4.5.4`, partial outputs use `4.5.4_partial`. Results: `Test/135/4.5.4` = 48 ok / 43 approved / 5 review; `Test/new_135/4.5.4` = 4 ok / 4 approved / 0 review; `Test/120/66/4.5.4` = 16 ok / 16 approved / 0 review; `Test/120/66/4.5.4_partial` = 16 ok / 16 approved / 0 review; `Test/120/67/4.5.4` = 4 ok / 3 approved / 1 review; `Test/半格/full/4.5.4` = 10 ok / 10 approved / 0 review; `Test/半格/partial/4.5.4_partial` = 5 ok / 5 approved / 0 review.
- The full diagnostic run processed 103 files in 221.31 seconds, averaging 2.15 seconds/file. Process workers were unavailable in the Codex sandbox, so the script used thread workers.

### V4.5.3

V4.5.3 is a narrow fix for half-frame full strips whose broad separator and
stable-grid evidence already satisfies the existing gate. It does not loosen
the general PASS rule for half-frame or other formats.

Main changes:

- Adds a safe detail-value reader so valid values such as `width_cv=0.0` are
  not mistaken for missing values by Python truthy / falsy logic.
- `half_wide_geometry_support` and `half_stable_grid_support` now correctly see
  perfectly stable frame width CV values.
- `X5_00058.tif` changes from `needs_review` to `approved_auto`, with unchanged
  outer, frame boxes, and gap results.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/135` is 48 rows / 0 diff against V4.5.2.
- `Test/半格/partial` is 5 rows / 0 diff against V4.5.2.
- Full `Test/半格` differs from V4.5.2 only on `X5_00058.tif` status /
  confidence / review reasons: `needs_review` becomes `approved_auto`; crop
  boxes and gaps have no diff.

### V4.5.2

V4.5.2 is a structural convergence release after V4.5.1. It continues to clean
up module responsibilities without changing detector thresholds or
intentionally changing PASS / REVIEW decisions.

Main changes:

- Moves read-only diagnostics calculations from `debug/render.py` into
  `detection/diagnostics.py`. Diagnostics still support Debug Analysis and
  postprocess, but detection finalization no longer depends backward on the
  Debug UI layer.
- Adds `constants.py` for analysis-source, gap-method, and main review-reason
  strings, reducing repeated handwritten literals across modules.
- Makes `policy.py` expose policy and frame-fit entry points directly from
  `common.py` / `geometry.py` instead of going through the `core.py`
  compatibility export surface.
- Makes `detection/models.py` export data models directly from `common.py`.
- Removes the broad detection-pipeline import from `debug/render.py`, narrowing
  the Debug rendering layer's dependencies.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.5.2`.
- Dry-run regressions against V4.5.1 with `--deskew off`: full `Test/135`,
  `Test/120/66` partial, full `Test/120/67`, full `Test/半格`, and
  `Test/半格/partial` all stayed at 0 diff.

### V4.5.1

V4.5.1 is a structural convergence release after V4.5. Its goal is not to
change detector thresholds, but to make the already-stable detection layers
easier to maintain.

Main changes:

- Adds read-only policy view groups over the existing `FormatTuning` fields:
  outer, content, separator, grid, scoring, calibration, partial, diagnostics,
  debug, and deskew.
- Moves post-detection finalization from CLI into `detection/postprocess.py`:
  content evidence, outer/content alignment, outer retry, review gates, output
  bleed, edge protection, and diagnostics attachment now live together.
- Splits per-count candidate generation into `calibrated_candidates_for_count()`
  and final candidate selection into `select_detection_candidate()`, so
  `choose_detection()` reads more like orchestration.
- Splits `separator_hard_evidence_ok()` into smaller 135, half-frame, and
  hard-required gate helpers.
- Removes active-code legacy aliases and hand-written `analysis_source`
  strings.
- Adds a Debug Analysis Decision summary panel with script version,
  PASS/REVIEW, confidence, format, strip, count, outer strategy, analysis
  source, auto gate, gap evidence, and review reasons.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.5.1`.
- Dry-run regressions against V4.5 with `--deskew off`: full `Test/135` is
  48 rows / 0 diff; `Test/120/66` partial is 16 rows / 0 diff; full
  `Test/120/67` is 4 rows / 0 diff; full `Test/半格` is 10 rows / 0 diff;
  `Test/半格/partial` is 5 rows / 0 diff.

### V4.5

V4.5 is a policy architecture cleanup. It does not loosen PASS rules or open more formats to automatic approval. Its main goal is to make the V4.4 outer-proposal, separator-geometry, partial-tolerance, and gate naming layers easier to reason about.

Main changes:

- The trusted-separator outer proposal is named as the general `separator_geometry_*` layer. The feature is now described as deriving an outer candidate from trusted separators, count, and format aspect, not as a partial-only concept.
- Adds `separator_geometry_outer_full_mode` and `separator_geometry_outer_partial_mode`. Only `120-66 partial` is currently `conditional`; other formats stay `off` until sample-based verification justifies opening them.
- Extracts shared `collect_separator_outer_bands()` and `separator_outer_band_sequences()` helpers so `separator_first_outer_candidates()` and `separator_geometry_outer_candidates()` share the same dark-band search, ranking, and sequence logic.
- Adds `outer_candidate_strategy` to report/detail output, and labels candidate-list entries with their strategy: `base_outer`, `content_floating_outer`, `long_axis_edge_anchor_outer`, `separator_first_outer`, or `separator_geometry_outer`.
- Renames historical score policy fields toward clearer gate semantics. Threshold values are unchanged.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/135` dry run against V4.4.6: 48 unique rows / 0 diff.
- `Test/120/66` partial dry run against V4.4.6: 16 unique rows / 0 diff; `X5_test_56.tif` still uses the `separator_geometry_*` outer candidate, and `X5_test_51.tif` remains REVIEW.
- Full `Test/半格/full` against V4.4.4: 10 rows / 0 diff.
- `Test/半格/partial` against V4.4.4: 5 rows / 0 diff.
- `Test/120/67` against the existing V4.4.2 baseline: no status / confidence / outer / frame / gap diff; one legacy review reason name is normalized from `v2_auto_gate_not_satisfied` to `auto_gate_not_satisfied`.

### V4.4.6

V4.4.6 adds a generic separator-geometry outer candidate, enabled only by the `120-66` policy for now. Before final candidate selection, it may add one extra outer candidate inferred from trusted separator bands.

The trigger is intentionally narrow:

- currently enabled only by the `120-66` policy; other formats stay disabled until sample-based verification says otherwise.
- `partial` only.
- count=3 only.
- the regular best candidate must have suspicious frame aspect before the extra candidate is considered, so stable separator-first results are not polluted.
- the candidate must come from strong dark separator bands and match the geometry of three 1:1 frames plus total separator width.

Main changes:

- For difficult 66 partial samples whose regular outer is poorly explained, the detector chooses two trusted internal separator bands from the full scan and infers the outer from three 6x6 frames.
- The inferred outer is only a candidate. It still has to compete through the existing separator / edge-pair / content / scoring / review-gate pipeline.
- It does not raise confidence, skip review gates, or promote weak-evidence files; the current `X5_test_51.tif` remains REVIEW.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/135` dry run against the existing V4.4.6 baseline: 48 rows / 0 diff.
- `Test/120/66` partial dry run against V4.4.5: 16 rows. Only `X5_test_56.tif` switched to the new `separator_geometry_*` outer candidate; `status`, `confidence`, and `review_reasons` are unchanged, still 15 `approved_auto` / 1 `needs_review`.

### V4.4.5

V4.4.5 is a retroactive default output folder rename. The default output folder
changes from the old `split_output/` name to the clearer `x5_crop_output/`.

Main changes:

- Current source now writes default output to `x5_crop_output/`.
- CLI help changed from `default input/split_output` to
  `default input/x5_crop_output`.
- README, quick-start documentation, CHANGELOG, and AGENTS path references are
  updated to the new default output folder.
- Locally visible archive snapshots have also been updated to the new default
  folder name and CLI help text.
- Existing GitHub release zip assets were refreshed retroactively: v4.2.8,
  v4.1.3, v4.0.1, v4.0, v3.6.2, and v3.3.1.

Verification:

- Apart from this section and the handoff text that explain the old-to-new
  rename, runtime paths in the currently visible source, user docs, and local
  archive snapshots now use `x5_crop_output`.
- Re-downloaded verification of all existing GitHub release zips found 0
  `split_output` hits and confirmed `x5_crop_output` is present in each package.

### V4.4.4

V4.4.4 is a naming cleanup and diagnostic readability fix after V4.4.3. Its
goal is to make active code names match the current detection model, and to fix
the V4.4.3 explanation gap where 50px bleed could be triggered without ordinary
Debug Analysis showing the corresponding diagnostic tick.

Naming rules:

- Candidate-level scoring and auto-gate results are called `candidate_decision`.
- Candidate ranking and competition summaries are called `candidate_competition`.
- Diagnostic reports are called `diagnostics`.
- The main detection entry point is `choose_detection()`.
- The candidate calibration entry point is `calibrate_candidate_decision()`.
- Review reasons no longer carry historical version names, for example
  `auto_gate_not_satisfied` and `candidate_competition_uncertain`.

Main changes:

- Removes active-code `v2_*` and `diagnostics_v3_6` naming.
- Removes unused `partial_content_min_count_35mm` /
  `partial_content_min_count_small` policy fields.
- Adds spacing geometry error to 2-gap `separator_outer_band_sequences()` top-k
  ranking, so candidate pruning is not based on band score alone.
- `overlap_bleed_risk_detail()` keeps the gap diagnostics that triggered
  output-only 50px bleed. Ordinary Debug Analysis can now draw cyan ticks for
  those overlap-risk gaps even when `--diagnostics` is not enabled.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.4.4`.
- Full `Test/135` against V4.4.3: 48 rows. The only diffs are 5 REVIEW rows
  where the review reason changed from the old version-coded name to
  `auto_gate_not_satisfied`; status / confidence / outer / frame boxes / gaps
  are unchanged.
- Full `Test/半格/full` against V4.4.3: 10 rows / 0 diff.
- Full `Test/半格/partial` against V4.4.3: 5 rows / 0 diff.
- `Test/120/66` partial against V4.4.3: 16 rows. The only diff is
  `X5_test_51.tif`, where the review reason changed from the old version-coded
  name to `auto_gate_not_satisfied`; status / confidence / outer / frame boxes /
  gaps are unchanged.

### V4.4.3

V4.4.3 is a maintenance-noise cleanup and local performance pass after V4.4.2.
It preserves full 135 detection output while allowing overlap / continuous
content risk that was already visible in read-only diagnostics to drive a safer
output-only bleed for partial, half-frame, and 120-format paths.

Main changes:

- Removes unused legacy constants and helper surfaces so future maintenance is
  less likely to confuse old paths with active logic.
- `content_detection_for_count()` now reuses same-image / same-format content
  mask and expanded-bbox intermediates, reducing repeated work across partial
  counts and offsets.
- `separator_first_outer_candidates()` uses exact lightweight sequence paths
  for 1-gap / 2-gap cases, with a top-k cap on 2-gap pair combinations. This is
  especially useful for 66 partial-style searches.
- Debug Analysis reuses the labeled original-gray preview instead of rebuilding
  that panel each time.
- The half full equal-first + wide-retry path is marked explicitly as
  `half_full_equal_first`. Behavior is preserved, but the branch is easier to
  understand.
- Diagnostic overlap-risk signals in partial, half-frame, and 120-format paths
  now trigger output-only 50px long-axis bleed. This only changes final output
  boxes / report frame boxes / Debug Analysis crop blocks; it does not
  participate in detection scoring or PASS/REVIEW decisions.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.4.3`.
- Full `Test/135` dry run is 48 rows / 0 diff against V4.4.2.
- Full `Test/半格` dry run differs from V4.4.2 only on `X5_00050.tif`
  `frame_boxes`, where output-only overlap bleed expands the long axis from
  20px to 50px; status / confidence / outer / gaps are unchanged.
- `Test/半格/partial` dry run differs from V4.4.2 only on `X5_00055.tif`
  `frame_boxes` for the same output-only overlap bleed reason; status /
  confidence / outer / gaps are unchanged.
- `Test/120/66` partial auto dry run differs from V4.4.2 only on
  `X5_test_51.tif` `frame_boxes` for the same output-only overlap bleed reason;
  status / confidence / outer / gaps are unchanged.

### V4.4.2

V4.4.2 is a conservative performance and old-logic cleanup pass after V4.4.1.
Its goal is to reduce repeated work in partial / Debug / enhanced separator
paths while preserving existing detector output.

Changes:

- Removes the legacy content-only partial auto-pass interface. Content
  candidates can still be analyzed, but they no longer trigger auto gate by
  themselves; partial auto-pass continues to rely on `partial_safe_extra_frames`
  / separator-evidence semantics.
- In partial mode, once a same-count separator candidate has auto-passed through
  `partial_safe_extra_frames`, the detector skips the corresponding content
  candidate and stops trying lower counts. Other offsets for the same count are
  still evaluated.
- Separator-first outer proposal now prunes invalid spacing while building band
  sequences instead of enumerating every combination first. The accepted
  candidate set is intended to remain identical while doing less invalid work.
- Enhanced separator merge now has an exact cache. Trigger conditions and
  acceptance thresholds are unchanged; identical outer / gaps / pitch / format
  calculations are reused.
- Debug / diagnostics nearby-separator detail now has an exact cache, reducing
  repeated profile checks during Debug Analysis or diagnostics overlays.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.4.2`.
- Full `Test/135` dry run is 48 rows / 0 diff against V4.4.1.
- `Test/半格/partial` dry run is 5 rows / 0 diff against V4.4.1.
- `Test/120/66` partial auto dry run is 16 rows / 0 diff against V4.4.1.
- Full `Test/120/67` dry run is 4 rows / 0 diff against V4.4.1.
- Full `Test/半格` dry run is 10 rows / 0 diff against V4.4.1.

### V4.4.1

V4.4.1 is a structural cleanup after V4.4. Its goal is to preserve the verified
V4.4 outputs while making full / partial responsibilities clearer and reducing
hidden conflicts for future tuning.

Changes:

- Partial `separator-first` now defaults back to `fallback`. `120-66` and
  `xpan` keep the more active partial `separator-first` path because these
  formats more often have normal three-frame scans that do not fill the holder.
- Content-only partial candidates no longer auto-pass by themselves. Content
  evidence still contributes to joint score and validation, but auto-pass now
  returns to `partial_safe_extra_frames` / separator-evidence semantics.
- Floating outer code naming was cleaned from `floating_full_*` to generic
  floating outer terminology because the same candidate family now serves both
  full and partial modes.
- Partial long-axis edge-anchor now judges edge bias from the local content bbox
  inside each candidate outer, instead of using one global content bbox for the
  whole scan.
- `135-dual` explicitly disables invalid partial / floating / wide-retry policy
  fields so the policy table no longer suggests support that the dedicated
  dual-lane path does not provide.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.4.1`.
- Full `Test/135` dry run is 48 rows / 0 diff against V4.4.
- `Test/半格/partial` dry run is 5 rows / 0 diff against V4.4 and remains 5
  `approved_auto` / 0 `needs_review`.
- `Test/120/66` partial auto dry run is 16 rows / 0 diff against V4.4 and
  remains 15 `approved_auto` / 1 `needs_review`.
- Full `Test/120/67` dry run is 4 rows / 0 diff against the existing V4.3
  baseline.
- Full `Test/半格` dry run is 10 rows / 0 diff against the existing V4.3
  baseline.

### V4.4

V4.4 redistributes the outer proposal logic added in V4.2 / V4.3 for
non-filled holder scans into the mode where it belongs.

New semantics:

- `full`: complete strip, filled holder, fixed count. It keeps normal outer,
  separator / edge-pair, wide separator, content validation, format geometry,
  and outer/content alignment logic that help complete strips.
- `partial`: leader, tail, local strip, or valid frames that do not fill the
  holder, are off-center, or start near one long-axis end. It can now use
  floating outer, separator-first outer, wide retry, and conditional long-axis
  edge-anchor fallback, then pass through the V4.3.1
  `partial_safe_extra_frames` gate.

Changes:

- `120-66` full no longer enables `floating_full_outer`, and
  `long_axis_edge_anchor` is no longer an always-on full-mode assumption;
  `separator-first` is reduced from always to fallback.
- `xpan` full disables long-axis edge-anchor; xpan partial can still use it as
  fallback.
- Partial `separator-first` can generate candidates for any count > 1 instead
  of only full default count.
- Partial now has `floating_partial_*` outer candidates for valid frame
  sequences that are off-center or do not fill the holder.
- Partial wide retry is enabled so wider gutters can become separator evidence.
- Partial long-axis edge-anchor is fallback-only and requires content to be
  clearly biased toward one long-axis end. If content is centered, no
  edge-anchor candidate is generated; this protects cases such as half-frame
  partial 55.
- `120-66` and `xpan` partial auto count may include default count=3 because
  they can be normal three-frame scans that still do not fill the holder.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.4`.
- Full `Test/135` dry-run against V4.3: 48 rows / 0 diff.
- `Test/半格/partial` dry-run against V4.3.1: 5 rows / 0 diff.
- `Test/120/66` partial auto dry-run: 15 `approved_auto` / 1
  `needs_review`. Most passing files selected `separator_first_*` or
  `floating_partial_*` outer candidates; `X5_test_51.tif` still reviewed due
  to weak 120 separator evidence.
- `Test/120/66` full dry-run: 13 `approved_auto` / 3 `needs_review`. This
  sample set is closer to the new partial meaning because the frames do not
  fill the holder, so full is no longer the main evaluation mode for it.

### V4.3.1

V4.3.1 adjusts the auto-pass semantics for partial mode. Previously, partial
runs could be pushed into REVIEW by `partial_strip_count_candidate` and
`separator_hard_evidence_weak` even when Debug Analysis showed that the real
frames were covered cleanly. This was especially visible on half-frame partial
strips, where a few extra empty holder crops are cheap to delete but the old
rules were still too conservative.

The new `partial_safe_extra_frames` gate applies only to partial candidates:

- It accepts separator candidates only; content-only candidates still cannot
  auto-pass by guessing.
- Content evidence must be `ok`.
- Frame geometry must be stable, with width CV under the policy limit.
- No `equal` gap may be used; some `grid` support is allowed as model fill.
- There must still be at least a small amount of hard separator / edge / wide
  evidence.
- Content conflicts, unstable widths, or other hard review reasons still force
  REVIEW.
- Candidate-competition demotion now skips safe partial candidates, because
  several close partial counts are expected when extra holder frames are
  acceptable.

In practical terms, partial mode may now crop a few extra empty holder frames if
that is safer than risking damage to real frames. The gate is available to all
formats in partial mode, with its thresholds centralized in `FormatTuning` so
135 / half / xpan / 120 can be tuned independently later.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `Test/半格/partial` dry-run + Debug Analysis + diagnostics: 5
  `approved_auto` / 0 `needs_review`.
- Full `Test/135` dry-run against V4.3: 48 rows / 0 diff.

### V4.3

V4.3 reorganizes the full-mode outer logic added throughout V4.2 into a single
outer proposal layer, instead of continuing to add separate retry branches.

Full-mode outer candidates now come from one layer:

- normal outer: ordinary outer candidates.
- floating full: a valid full strip may float inside the scan instead of being
  centered or filling the whole scan.
- separator-first: trusted dark separator bands plus format count / aspect infer
  the outer.
- long-axis edge-anchor: new. It covers full strips whose valid frame sequence
  is not centered but starts near one long-axis end. Horizontal strips use left
  / right anchors; vertical strips are handled in work orientation.

All proposals only generate outer candidates. Auto-cropping still depends on
the unified pipeline:

```text
outer candidate
  → separator / edge-pair / wide-separator
  → frame boxes
  → content evidence
  → format geometry
  → candidate calibration
  → review gate
```

Format policy:

- `120-66`: long-axis edge-anchor is `always`, because three valid 6x6 frames
  may not fill the scan and may start near one long-axis end.
- `xpan`: long-axis edge-anchor is `fallback`. XPAN is physically similar to
  66 in that film may not fill the holder and may start near one long-axis end,
  but it still needs real samples before tuning.
- `135`, `half`, `120-645`, `120-67`, and `135-dual`: currently off. Half-frame
  testing showed `X5_00063` could be pulled into a pure-equal edge-anchor REVIEW
  candidate; the other formats avoid extra candidates until clear sample benefit
  exists.

Safety rule:

- Long-axis edge-anchor does not raise confidence by itself.
- A long-axis edge-anchor separator candidate with no hard separator is forced
  below auto-pass with `long_axis_edge_anchor_separator_weak`, preventing pure
  equal / grid model candidates from passing.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `Test/120/66` dry run was 0 diff against V4.2.9 for `status`,
  `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`.
- `Test/半格/full` dry run was 0 diff against V4.2.7 for the same fields.

### V4.2.10

V4.2.10 is a risk-controlled caching update. It does not change detector policy:

- `AnalysisCache` now stores full-scan separator evidence for reuse by full-scan
  Debug Analysis evidence and enhanced full-profile paths.
- Full-scan separator profiles are cached per format, reducing repeated full
  profile work during separator-first, wide retry, and Debug Analysis paths.
- Content runs are cached by `(format, count, outer)`, avoiding repeated scans
  of the same content-evidence segment.
- Content-evidence scoring is cached by outer / frame combination, and
  outer/content alignment is cached by outer / gap combination. These caches
  only hit on identical candidates, and cached detail is deep-copied on read so
  later report or Debug writes cannot mutate the stored value.
- Separator-first outer candidates are cached by format / count / strip mode /
  base outer candidates. This mainly helps 120-66 and also covers other formats
  that use separator-first fallback.
- Debug Analysis reuses base preview images for Original gray, Separator
  evidence, and Content evidence within the same render. Cached images are
  copied before overlays are drawn, so panel annotations cannot pollute later
  panels.
- This is global across formats, not specific to 120-66. The largest practical
  benefit is expected on 120-66 / 120 / partial / Debug Analysis runs where
  more candidate outers and full-scan evidence views are involved.
- This version intentionally does not add approximate nearby-outer caching,
  broad edge-profile slice caching, or deskew intermediate caching. Those may
  be useful later, but need separate regression checks.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- `Test/120/66` dry-run stayed at 9 `approved_auto` / 7 `needs_review`; compared
  with V4.2.9, `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps` were 0 diff.
- A single 120-66 Debug Analysis smoke test generated its JPG normally.

### V4.2.9

V4.2.9 continues focused 120-66 full-strip tuning. Based on local manual review
of `Test/120/66`, `45 / 46 / 49 / 50 / 52 / 54` had accurate red separator
boxes, while the other samples still had visible separator risk even when they
passed. This version makes two conservative changes:

- 120-66 full strips require stronger ordinary `edge-pair` quality when no
  `wide-separator` supports the candidate. Low-quality edge-pair combinations
  no longer satisfy the auto gate by themselves.
- Wide 66 dark gutters remain valid separator evidence, but separator-first
  outer search is not broadly loosened, avoiding extra outer drift.
- Debug Analysis `Separator evidence` and `Content evidence` now show full-scan
  evidence instead of only the selected outer. The current outer / frame overlay
  is drawn on top so ignored evidence outside the selected outer can be reviewed.

Current V4.2.9 dry-run + Debug Analysis output for `Test/120/66` is saved in
`Test/120/66/4.2.9`. Result: 9 `approved_auto` / 7 `needs_review`:

- Still PASS and in the manually accurate group: `45 / 46 / 49 / 50 / 52 / 54`.
- Changed from V4.2.8 PASS to REVIEW: `44 / 47 / 51 / 53 / 55 / 56 / 58`.
- Still PASS and needs further review / future tuning: `43 / 48 / 57`.

### V4.2.8

V4.2.8 is a launcher interaction update; detection logic is unchanged. The
Mac / Windows main launchers now ask for count only after partial mode is
enabled:

```text
partial mode? [y/n, return=no]: y
partial count:
  return or auto = auto
  allowed: ...
count:
```

Rules:

- If partial mode is off, the launcher does not ask for count and keeps the
  selected format's full-strip count.
- If partial mode is on, Return or `auto` means automatic count detection.
- If partial mode is on, an allowed number is passed as `--count N`, fixing the
  partial frame count.
- Invalid count input is rejected and the launcher asks again.

Verification:

- `bash -n X5_Crop_Mac.command` passed.
- Mac launcher smoke test: entering `half` / partial `y` / count `3` / debug
  `y` showed `strip mode: partial` and `count: 3`, then invoked the script. The
  project root has no TIFF files, so the final `No TIFF files found` message is
  expected for this smoke test.
- Local ignored test copies were synced for `Test/135`, `Test/new_135`,
  `Test/120/66`, `Test/120/67`, and `Test/半格/full`.

### V4.2.7

V4.2.7 adds half-frame full stable-grid support. After V4.2.6,
`X5_00062.tif` and `X5_00063.tif` already had good crop boxes, but they still
went to REVIEW because hard/wide evidence was below the majority-wide gate,
outer area was large, and the candidate auto gate was not satisfied. The new
`half_stable_grid_support` does not loosen outer area by itself. Instead, it
recognizes a narrow half-frame full pattern:

```text
real hard/wide separators cover part of the strip
  +
grid fills the remaining gaps
  +
frame width is very stable
  +
content support is normal
  +
no equal fallback is used
```

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/半格/full` dry-run + Debug Analysis output was written to `Test/半格/full/4.2.7`.
- `Test/半格/full` result: 10 files, 10 `approved_auto` / 0 `needs_review`.
- Compared with V4.2.6, only `X5_00062.tif` and `X5_00063.tif` changed from REVIEW to PASS; their outer boxes, frame boxes, and gaps are unchanged.
- `X5_00062.tif` passes via `half_stable_grid_support`, with 4/11 hard/wide gaps and 7/11 grid gaps.
- `X5_00063.tif` passes via `half_stable_grid_support`, with 5/11 hard/wide gaps and 6/11 grid gaps.

### V4.2.6

V4.2.6 continues the half-frame full-strip tuning. V4.2.5 already allowed
59/60/61 to pass, but 56/58 were still blocked by the gate, and 63 stayed REVIEW
while showing a misleading content candidate. V4.2.6 makes two half-frame
full-specific changes:

- `half_wide_geometry_support` now uses a majority-wide rule: at least 60% of
  expected gaps must be wide/hard, no equal fallback may be used, frame widths
  must be stable, content support must be normal, and the candidate must reach a
  half-wide joint-score floor. This lets 56/58 pass while keeping weaker cases
  in REVIEW.
- When a half-frame full content candidate has `content_run_count_mismatch` and
  a plausible separator candidate exists, REVIEW display prefers the separator
  candidate. This keeps 63 in REVIEW but avoids the previously misleading
  content-based crop boxes.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/半格/full` dry-run + Debug Analysis output was written to `Test/半格/full/4.2.6`.
- `Test/半格/full` result: 10 files, 8 `approved_auto` / 2 `needs_review`.
- Newly approved compared with V4.2.5: `X5_00056.tif` and `X5_00058.tif`.
- `X5_00050.tif`, `X5_00053.tif`, `X5_00054.tif`, `X5_00059.tif`, `X5_00060.tif`, and `X5_00061.tif` remain stable from V4.2.5.
- `X5_00062.tif` stays REVIEW because it has only 4/11 wide/hard gaps.
- `X5_00063.tif` stays REVIEW because it has only 5/11 wide/hard gaps, but final display now uses the separator candidate instead of the misleading content candidate.

### V4.2.5

V4.2.5 is conservative half-frame full-strip wide-separator tuning. After the
half-frame tests were split into `full` and `partial`, several standard-looking
full half-frame scans from 56 onward still went to REVIEW. Diagnostics showed
that the issue was not invisible separators; the half-frame full path was
falling back to equal/grid behavior, so wider dark gutters were not being
treated as reliable separator evidence.

This version makes two narrow half-frame-only changes:

- The ordinary half-frame full path keeps its existing equal/grid behavior, so
  stable existing files such as 50/53/54 are not disturbed.
- When the ordinary path does not pass, the wide retry branch may use
  `wide-separator` for wider dark gutters. Auto-crop is allowed only when
  wide/hard gaps cover at least 80% of expected separators, no equal fallback
  is used, frame widths are stable, content support is normal, and the joint
  score is above threshold.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/半格/full` dry-run + Debug Analysis output was written to `Test/半格/full/4.2.5`.
- `Test/半格/full` result: 10 files, 6 `approved_auto` / 4 `needs_review`.
- Newly approved compared with V4.2.4: `X5_00059.tif`, `X5_00060.tif`, and `X5_00061.tif`.
- `X5_00050.tif`, `X5_00053.tif`, and `X5_00054.tif` remain unchanged from V4.2.4.
- `X5_00056.tif` and `X5_00062.tif` now show some `wide-separator` evidence but still do not have enough wide coverage, so they stay REVIEW. `X5_00058.tif` and `X5_00063.tif` remain content-only / content-mismatch REVIEW cases.

### V4.2.4

V4.2.4 is a behavior-preserving cleanup after V4.2.3. It addresses two
maintenance risks in the separator-first fallback path:

- Fallback now builds only `separator_first_*` outer candidates. Previously, the
  fallback retry reran ordinary outer candidates and separator-first candidates
  together; if separator-first produced no valid outer, that could waste work
  and make report details harder to interpret. Now, when no separator-first
  outer is generated, no retry-used marker is written and the detector returns
  to the existing content / review flow.
- `separator_first_outer_mode` is now validated as `off`, `fallback`, or
  `always`. Future typos will fail loudly instead of silently changing detector
  behavior.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Compared against the V4.2.3 baseline, full `Test/135`: 48 rows, 0 diff.
- Compared against the V4.2.3 baseline, full `Test/120/67`: 4 rows, 0 diff.
- Compared against the V4.2.3 baseline, full `Test/半格`: 15 rows, 0 diff.
- Compared against the V4.2.2 baseline, full `Test/120/66`: 16 rows, 0 diff.

### V4.2.3

V4.2.3 generalizes the V4.2.2 120-66 separator-first outer proposal into a
format-aware framework. The core order stays the same:

```text
Find trusted dark separator bands in the global separator profile
  ↓
Choose internal separator combinations that match the current format count and frame aspect
  ↓
Infer the outer from N equal-format frames plus total separator width
  ↓
Send the candidate back through the existing separator / edge-pair / scoring / review gate
```

This is not a direct copy of the 66 parameters into every format. V4.2.3 gives
each format its own policy entry:

- `120-66` stays in `always` mode because the central 66 full-strip problem is
  that the valid outer may not fill the full scan, and the separator-first path
  is the main strategy.
- `135`, `half`, `xpan`, `120-645`, and `120-67` use `fallback` mode. They try
  separator-first outer proposals only when the normal separator / wide-retry
  candidate does not satisfy the auto-pass gate.
- `135-dual` remains disabled because dual 135 has two-lane strip logic and
  should not be interpreted with the single-lane full-strip outer model.

The goal is to turn "trusted separators + format geometry infer outer" into a
shared framework for future tuning without stealing already reliable normal
detections. This matters for 120-67: forcing separator-first into `always` mode
gave a more aggressive, tighter outer, but visual review did not show a clear
improvement, so V4.2.3 keeps 120-67 in fallback mode.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/120/66` full-strip dry run: 16 files, 16 `approved_auto`, 0
  `needs_review`.
- Compared against the V4.2.2 baseline, full `Test/135`: 48 rows, 0 diff.
- Compared against the V4.2.2 baseline, full `Test/120/67`: 4 rows, 0 diff.
- Compared against the V4.2 baseline, full `Test/半格`: 15 rows, 0 diff.

### V4.2.2

V4.2.2 continues the 120-66 full-strip work. In these scans, the three 6x6
frames do not necessarily fill the full long scan or sit centered inside it,
but the two internal dark separators are often very clear. V4.2.1 allowed the
outer to float, but it still mostly followed the order "choose an outer first,
then search near predicted gap positions." V4.2.2 adds a 66-specific proposal in
the opposite direction:

```text
Find strong dark separator bands in the global separator profile
  ↓
Choose two internal separators whose spacing matches a 6x6 short axis
  ↓
Infer the outer from 3 x 1:1 frames plus the two separator widths
  ↓
Send the candidate back through the existing separator / edge-pair / scoring / review gate
```

This branch is enabled only for `120-66`, `full`, `count=3`. It does not let
content-only candidates auto-pass, and it does not bypass the existing hard
separator evidence gate. Separator-first candidates get a limited wide-gap
override so that 66 scans with visibly clear but wider dark gaps can still be
recognized; results containing `wide-separator` remain capped by the wide-gap
confidence cap.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/120/66` full-strip dry run: 16 files, 16 `approved_auto`, 0
  `needs_review`.
- `X5_test_45.tif`, `X5_test_50.tif`, and `X5_test_54.tif` changed from
  content-only REVIEW to `separator_candidate`, with gap methods using
  `detected` / `edge-pair` / `wide-separator` combinations.
- Compared against the V4.2.1 baseline, full `Test/135`: 48 rows, 0 diff.
- Compared against the V4.2.1 baseline, full `Test/120/67`: 4 rows, 0 diff.

### V4.2.1

V4.2.1 focuses on 120-66 full-strip outer candidate generation. The main 66
problem was not a small short-axis tweak: in many scans, the three 6x6 frames do
not fill the full long scan and are not necessarily centered. If the detector
starts from the assumption that the whole scan is the valid outer, separator,
equal-split, and frame-fit logic can all be pulled off by the wrong outer.

V4.2.1 treats 120-66 full as a new target instead of protecting the old 66
output as a baseline:

- Count remains fixed at 3; partial mode is still separate.
- Existing outer candidates are kept, and 120-66 full adds floating full outer
  candidates.
- Floating outers use the expected geometry of `3 * 1:1 frame + total separator
  width`, instead of assuming that the frames fill or sit centered in the whole
  scan.
- Candidates are anchored around the original outer and content bbox left edge,
  right edge, and center, then compete through the existing separator /
  edge-pair / scoring / review-gate pipeline.
- Content-only candidates still cannot auto-pass without reliable separator
  evidence.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- Full `Test/120/66` full-strip dry run: 16 files, 13 `approved_auto`, 3
  `needs_review`; the remaining review files are `X5_test_45.tif`,
  `X5_test_50.tif`, and `X5_test_54.tif`.
- Compared against the V4.2 baseline, full `Test/135`: 48 rows, 0 diff.
- Compared against the V4.2 baseline, full `Test/120/67`: 4 rows, 0 diff.

### V4.2

V4.2 adds a shared full-format geometry model for full-strip detection across
135, half-frame, xpan, 120-66, 120-645, and 120-67:

```text
outer_long / outer_short = count * frame_aspect + separator_total / outer_short
```

The model is written into report detail and is also used by a conservative
stage-C outer correction retry. The retry only tries to move the outer when all
of these are true:

- the candidate is a full strip with the format's full count;
- every internal separator is hard / edge-pair / wide-separator and has a
  measurable width;
- the current outer has extra long-axis ratio that cannot be explained by the
  measured separator total;
- the separator widths and format frame aspect can infer a corrected outer that
  is closer to the geometry model;
- the correction is small and does not cut the content bbox.

The goal is to establish one shared geometry language for all formats while
allowing only a narrow active correction. On the current test set, this rule did
not change output, which confirms it is conservative. The 120-66 REVIEW images
mostly lack reliable hard gaps, so this stage-C rule does not force-correct
them or push them into PASS.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py
  x5crop/debug/*.py` passed.
- Compared against the V4.1.3 baseline, full `Test/135`: 48 rows, 0 diff.
- Compared against the V4.1.3 baseline, full `Test/半格`: 15 rows, 0 diff.
- Compared against the V4.1.3 baseline, full `Test/120/66`: 16 rows, 0 diff.
- Compared against the V4.1.3 baseline, full `Test/120/67`: 4 rows, 0 diff.
- `Test/new_135` kept 4 `approved_auto` / 0 `needs_review` in V4.2.

### V4.1.3

V4.1.3 is a behavior-preserving cleanup after V4.1.2. It is not intended to
change detection output. It addresses the semantic and maintenance issues found
in the previous review:

- The old `score_hard_full_confidence_floor` role moved out of
  `score_detection()` and into `calibrate_candidate_decision()` as
  `calibrate_hard_full_confidence_floor`. It is now explicitly candidate-level
  confidence calibration, not separator scoring or geometry scoring.
- Shared base parameters for 120-66 / 120-67 / 120-645 are now collected in one
  120 format policy helper, reducing branch drift when future 120 tuning
  changes.
- The 120-67 short-axis outer excess trigger is more semantic: it requires
  reliable hard anchors and content height clearly below the outer before
  short-axis tightening is proposed.
- The CLI now calls one outer correction proposal entry point instead of
  manually chaining two retry paths. The original priority is preserved:
  short-axis aspect retry first, then content-aligned retry.

Verification:

- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py
  x5crop/debug/*.py` passed.
- Compared against the V4.1.2 baseline, full `Test/135`: 48 rows,
  `python3 -m x5crop.regression` reported 0 diff.
- Compared against the V4.1.2 baseline, full `Test/半格`: 15 rows, 0 diff.
- Compared against the V4.1.2 baseline, full `Test/120/66`: 16 rows, 0 diff.
- Compared against the V4.1.2 baseline, full `Test/120/67`: 4 rows, 0 diff.

### V4.1.2

V4.1.2 is a narrow 120-67 short-axis outer fix. In
`Test/120/67/3.tif`, both separators were already `edge-pair`; the issue was
not separator evidence, but extra top/bottom slack in the initial outer. V4.1.2
does not add a new detection algorithm. It makes 120-67 short-axis outer excess
slightly more sensitive so the existing `content_aligned_outer` retry can
tighten the short axis when hard separators are reliable, content aspect is
normal, and short-axis content slack is clearly high.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.1.2`.
- Running only `Test/120/67/3.tif` kept it as `approved_auto confidence=1.000`.
- After the fix, `3.tif` outer changed from `top=1, bottom=4009` to `top=68,
  bottom=3974`; both gaps remain `edge-pair`, and
  `separator_hard_evidence.ok=True`.
- Per target, this update was verified only on `3.tif`; no full 135 / 120
  regression was run.

### V4.1.1

V4.1.1 is a narrow 120-67 wide-separator fix. In V4.1,
`Test/120/67/2.tif` had a reliable right separator as `edge-pair`, but the left
wide separator fell back to `equal`, so hard separator evidence was incomplete.
V4.1.1 does not change the default narrow-separator path. It only enables a
conservative 120-67 `wide-separator` retry when the normal separator candidate
fails the auto gate, with the retry width capped at `0.090 * pitch`.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.1.1`.
- Running only `Test/120/67/2.tif` changed it from V4.1
  `needs_review confidence=0.835` to `approved_auto confidence=0.995`.
- After the fix, `2.tif` has the first gap as `wide-separator`, the second gap
  as `edge-pair`, `equal_gaps=0`, and `separator_hard_evidence.ok=True`.
- Per request, this update was verified only on `2.tif`; no full 135 / 120
  regression was run.

### V4.1

V4.1 is a focused policy and retry-strategy update for 120-66 and 120-67. It
does not change the 135 detection path. It keeps the central safety rule:
content-only candidates still cannot auto-pass, so difficult 120 scans are not
approved just because the content layout looks plausible.

Main changes:

- Bumps the script version to `4.1`.
- Adds a 120-66 short-axis aspect outer retry. It runs only for full-strip
  separator candidates when hard separator evidence already passes and content
  evidence clearly says the frame is too tall/narrow because the short-axis
  outer is too tight. The retry expands the short-axis outer so each 66 frame is
  closer to 1:1. This is a conservative 66-specific retry and does not make
  content-only results auto-pass.
- Corrects horizontal 120-67 content aspect to 5:4. The previous policy used
  4:5, which matched vertical 67 more closely and could mark normal horizontal
  67 scans as aspect conflicts.
- Adds a 120-oriented hard-full confidence floor and outer-area tolerance for
  120-67. When a full-strip candidate has the right count, every gap has hard
  separator / edge-pair evidence, no equal gaps, and stable frame widths, it can
  reach the confidence floor needed for auto approval.
- Applies the same hard-full confidence floor idea to 120-66, while still
  requiring complete hard separator evidence. Content-only candidates remain
  REVIEW.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.1`.
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- 120-66 full dry run + diagnostics: 16 files, 7 `approved_auto` / 9
  `needs_review`. The 7 approved files all have complete hard separator
  evidence; content-only results remain `needs_review`.
- 120-67 full dry run + diagnostics: 4 files, 2 `approved_auto` / 2
  `needs_review`. `2.tif` remains REVIEW because one gap is still equal and
  separator evidence is incomplete; `4.tif` looks closer to a partial /
  single-frame case and remains REVIEW under full count=3.
- A full `Test/135` `deskew off` dry run was compared with V4.0.1 commit
  `b9940a8` as the baseline. Both runs processed 48 files with 43
  `approved_auto` / 5 `needs_review`, and `python3 -m x5crop.regression`
  reported 0 diffs across `status`, `confidence`, `review_reasons`,
  `outer_box`, `frame_boxes`, and `gaps`.

### V4.0.1

V4.0.1 is a narrow compatibility update after V4.0. It does not globally loosen
the maximum hard-gap width for 135. The normal path still uses the V4.0
`gap_max_width_ratio=0.045`. When the normal separator candidate cannot satisfy
the auto gate because separator evidence is too weak, the detector enables the
formal `wide-separator` branch, allowing the width limit to reach
`wide_gap_retry_max_width_ratio=0.060`.

`wide-separator` is not a global loosening of ordinary `detected` gaps. It only
runs after the narrow separator path fails, and the wide dark band must satisfy
mean-score and relative-prominence requirements. Accepted gaps are written as
the `wide-separator` method, reports separately record `wide_detected_gaps` and
`wide_gap_retry`, and Debug Analysis draws them with a distinct red-family mark.
Separator candidates that contain wide separators have a light confidence cap so
wide dark gutters do not automatically push confidence to the maximum.

This is meant for 135 strips where the gutter is visually clear but wider than
the old rule allowed. `wide-separator` is enabled only for normal 135 full
strips. It remains disabled for half-frame, xpan, 120 formats, and 135-dual so
untuned formats are not loosened accidentally.

The repository also adds the macOS diagnostic launcher
`X5_Crop_Mac_diagnostics.command`. It always enables dry run, Debug Analysis,
`--diagnostics`, `--no-copy-review-files`, `--no-reuse-analysis`, and
`--jobs 4` for local development testing. It is not a normal user launcher and
is not included in Release packages.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.0.1`.
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py` passed.
- The 4 new `Test/new_135` wide-gutter samples changed from V4.0 `needs_review`
  to 4 `approved_auto`, with `wide-separator`, `wide_detected_gaps`, and
  `wide_gap_retry.used=true` recorded in the reports.
- A full `Test/135` default-deskew Debug Analysis dry run remained 42
  `approved_auto` / 6 `needs_review`.
- `python3 -m x5crop.regression` compared the existing
  `Test/135/x5_crop_output/split_report.jsonl` with the V4.0.1 temporary output;
  all 48 rows had 0 diffs for `status`, `confidence`, `review_reasons`,
  `outer_box`, `frame_boxes`, and `gaps`.

### V4.0

V4.0 is a bold full modular rewrite, while still following the constraint:
rewrite the structure, preserve the result. It is not a new detection algorithm,
and it does not introduce OpenCV, scipy, or other heavy dependencies; those
image-processing backends are reserved for a future V5 direction. V4 splits the
entry point, detection core, geometry evidence, I/O, Debug Analysis, reports,
deskew, CLI orchestration, and regression tooling into real modules, then proves
with a full 135 regression that output is unchanged.

Main changes:

- Bumps the script version to `4.0`.
- Makes root `X5_Crop.py` a thin entry point that calls `x5crop.cli.main()`.
  Users still run the same script name and the same launchers.
- Keeps `x5crop/core.py` only as a compatibility re-export surface for old
  import paths.
- Adds `x5crop/common.py` for dataclasses, format policy, `FormatTuning`,
  `FrameFitPolicy`, base math/geometry helpers, and serialization helpers.
- Adds `x5crop/evidence.py` for base gray, analysis gray, content evidence,
  separator evidence, and evidence normalization.
- Adds `x5crop/io.py` for TIFF reading, writing, metadata/ICC/resolution
  preservation, review-copy behavior, and TIFF profile validation.
- Adds `x5crop/geometry.py` for outer candidates, white/content alignment,
  separator profiles, gap search, edge-pair, robust grid, frame fitting, and
  geometry polish.
- Adds `x5crop/detection/pipeline.py` for candidate generation, content
  validation, support scoring, confidence calibration, review gates, and final
  detection selection.
- Adds `x5crop/deskew.py` for deskew angle estimation, rotation, and same-angle
  report-reuse crops.
- Adds `x5crop/debug/render.py` for Debug JPG, Debug Analysis panels,
  diagnostic overlays, version labels, and readable rendering.
- Adds `x5crop/reports.py` for report writing, report reuse, output-only bleed
  normalization, needs_review copying, and crop export.
- Adds `x5crop/cli.py` for argument parsing, folder parallelism, per-file
  processing, terminal output, and main orchestration.
- Adds `x5crop/regression.py`, which compares two `split_report.jsonl` files.
  By default it compares `status`, `confidence`, `review_reasons`, `outer_box`,
  `frame_boxes`, and `gaps`.
- Adds `tools/build_standalone.py`, which turns the modular V4 source tree into
  a standalone Release `X5_Crop.py`. Normal users can still copy only the script
  and the platform-matching launcher; they do not need to copy an `x5crop/`
  folder.
- Syncs the ignored local test copies under `Test/135/` to include both
  `Test/135/X5_Crop.py` and `Test/135/x5crop/`.
- Documentation clarification without a version bump: README and the quick-start
  guide now state that auto-cropped TIFF output preserves source-TIFF
  quality-related attributes including but not limited to
  bit depth, channel layout, ICC / color space, resolution, and metadata.
  Cropping does not intentionally lower bit depth, recolor, compress, or
  resample image data.
- Release package document-format change without a version bump: user documents
  inside the Release zip now ship as `README.txt` and
  `快速启动_Quick_Start.txt` for easier reading across systems. Repository source
  documents remain `README.md` and `快速启动_Quick_Start.md`.
- Output bleed update without a version bump: default long-axis bleed changed
  from 35px to 20px, while short-axis bleed remains 10px. When overlap,
  near-overlap, or continuous-content risk is detected, long-axis output bleed
  is automatically raised to 50px. This affects final output, reports, and
  Debug Analysis crop blocks only, not detection scoring.

Verification:

- `python3 X5_Crop.py --version` prints `X5_Crop.py 4.0`.
- `python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py
  x5crop/debug/*.py` passed.
- V3.9 baseline: 48 TIFF files, 0 failed, 42 `approved_auto`, 6
  `needs_review`, default-deskew dry run in about 317 seconds.
- V4.0 current: 48 TIFF files, 0 failed, 42 `approved_auto`, 6 `needs_review`,
  default-deskew dry run in about 314 seconds.
- `python3 -m x5crop.regression` compared the V3.9 and V4.0 full 135 JSONL
  reports. Across all 48 rows, `status`, `confidence`, `review_reasons`,
  `outer_box`, `frame_boxes`, and `gaps` had 0 diffs.

### V3.9

V3.9 is a structural cleanup after V3.7. It is not a smarter detector rewrite; it continues moving scattered workflow switches, percentage/clamp parameters, format branches, and future cross-format promotion points into clearer policy layers. The goal is to make future 135, half, xpan, and 120 tuning easier without letting low-value fallback quietly change PASS/REVIEW.

Main changes:

- Bumps the script version to `3.9`.
- Adds `OuterMaskProfile`, wiring low-level outer mask brightness ranges, row/column minimum fractions, and minimum outer size into `FormatTuning`.
- Moves post-detection confidence caps into policy fields, including caps for content aspect conflict, low content confidence, outer mismatch, and lucky-pass risk.
- Moves the deskew span skip threshold into `FormatTuning` as a ratio plus clamp instead of a scattered fixed-pixel check.
- Converts the remaining frame-fit 1px tolerances into ratio plus clamp form while keeping the default behavior equivalent.
- Adds `separator_gate_mode`, so 135, half, and hard-required formats express their hard-evidence requirements through policy.
- Adds `outer_retry_enabled`; 135-dual still disables outer retry, while normal 135 keeps the previous behavior.
- Keeps high-risk behavior such as nearby active correction, lucky-pass risk, and leading-grid failure policy-gated. Non-135 formats keep hooks only; they do not directly inherit 135 rules.
- Syncs `X5_Crop.py`, the local `Test/135/X5_Crop.py` copy, and the archive snapshot `archive/X5_Crop_v3.9.py` to V3.9.

Verification:

- V3.9 was compared against a V3.7 current-script snapshot with a full 135 default-deskew dry run. Both runs processed 48 TIFF files with 0 failed, 42 `approved_auto`, and 6 `needs_review`.
- Compared fields: `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps`.
- Result: 0 diffs across all 48 report rows.
- This verification used the default deskew path, not a faster `deskew off` path, so it is closer to the normal launcher workflow.

### V3.7

V3.7 is a frame-size fit pipeline cleanup. The script previously had two easy-to-confuse fit paths: `apply_frame_size_fit()` adjusted cuts with equal-width geometry, while `same_frame_size_fit_boxes()` used `detected` / `edge-pair` left and right edge samples to fit same-size frame boxes. Now that `edge-pair` is format-aware, keeping those paths scattered makes it harder to reason about whether red gaps, grid, or equal fallback should be allowed to shape output boxes.

V3.7 organizes them behind one entry point: `fit_frame_boxes_from_gaps()`. It builds base frame boxes, tries format-aware edge-evidence fit when available, and otherwise falls back to geometry or raw gaps. This version is meant to make the structure clearer, not to loosen auto-cropping.

Main changes:

- Bumps the script version to `3.7`.
- Renames and narrows `apply_frame_size_fit()` into `fit_cuts_by_geometry()`, making it explicitly a cuts-level geometry fallback.
- Renames and narrows `same_frame_size_fit_boxes()` into `fit_boxes_by_edge_evidence()`, making it responsible only for hard / edge-pair evidence.
- Adds `FrameFitPolicy` and `fit_frame_boxes_from_gaps()` so edge evidence, geometry fallback, and raw-gap fallback return through one path.
- Follow-up cleanup: `FrameFitPolicy` is now actually format-aware. 135 keeps the original thresholds; half-frame requires more edge samples; xpan and each 120 format have their own nominal-width range and inlier tolerance; 135-dual and partial mode keep edge-evidence fit disabled while preserving geometry fallback.
- Keeps the principle that fallback and refactoring must not loosen PASS/REVIEW.
- Follow-up configuration change without a version bump: default output long-axis bleed once changed from 20px to 35px, while short-axis bleed remained 10px. A later V4.0 stable update changed the default long-axis bleed back to 20px and uses 50px long-axis output bleed automatically for overlap / continuous-content risk. Bleed is still applied only to output/report/Debug Analysis frame boxes and does not participate in detection scoring.
- Follow-up scale cleanup without a version bump: fixed pixel thresholds in `edge_bleed_protection`, approved geometry polish, outer content alignment, alignment-based outer correction, and robust-grid hard-gap protection now use pitch / outer-height ratios plus pixel clamps. These internal thresholds are no longer directly tied to output bleed, while the current 135 resolution range keeps the previous trigger behavior.
- Second follow-up scale cleanup without a version bump: gap search radius, hard-gap width / guard values, nearby separator search windows and movement checks, edge-pair window / gutter / hard-gap movement guards, robust-grid shift / tolerance, enhanced-separator gap width / movement, partial edge-hint windows, hard-gap trust diagnostic windows, and deskew span skipping now also use ratios plus clamps. Thresholds that were originally floating-point tolerances now use floating-point clamps to avoid sub-pixel grid drift.
- Format-policy cleanup without a version bump: added `FormatTuning` and centralized parameters for outer candidates, outer/content alignment, content-primary detection, gap detection, geometry constrain, robust grid, hard-gap trust, nearby separator, enhanced separator, scoring, auto gates, support scores, candidate calibration, partial strategy, diagnostics, and approved geometry polish. 135 keeps the current values; other formats get conservative policy entry points so this cleanup does not loosen auto-cropping.
- Follow-up format-policy expansion without a version bump: content-run thresholds, content confidence caps, score caps for partial / outer / 135 hard evidence, separator hard-evidence gates, leading-grid failure, content-only partial passing, nearby active correction, and lucky-pass risk are now controlled by policy. High-risk behavior remains conservative: nearby active correction, lucky-pass risk, and leading-grid failure stay enabled only on the already validated 135 path; other formats keep separate policy hooks and diagnostic groundwork.
- Further policy cleanup without a version bump: low-level outer extraction, separator profiles, edge-refine profiles, grid outer refinement, frame-fit geometry fallback, edge-evidence inlier tolerance, non-auto candidate confidence caps, and deskew sampling / enhanced-quality gates are now wired through format-aware policy. 135 defaults preserve the previous behavior.
- Reuse and diagnostics efficiency cleanup without a version bump: Debug Analysis report reuse no longer treats output bleed as part of the detection signature. When a normal export reuses an old report, cached output frames are first normalized from their previous output bleed and then rebuilt with the current bleed, so changing bleed alone does not reuse the wrong crop boxes. Diagnostics also reuse cached separator profiles for nearby-separator checks, reducing repeated profile work in full diagnostic runs.
- High-level policy cleanup without a version bump: main gap/width/outer/contrast scoring weights, content-evidence thresholds, content/geometry/separator support gates, candidate competition margin/cap, hard-gap trust semantic thresholds, overlap-risk diagnostic thresholds, and Debug gap-overlay line parameters are now wired through `FormatTuning`. Current 135 defaults preserve the previous behavior; this mainly makes future format-specific tuning more centralized without loosening auto-cropping.
- Low-risk code cleanup without a version bump: removed the unused `score_120_require_all_hard` policy field; renamed `detect_for_count()` to the clearer `detect_candidate_for_count()`; and made `lucky_pass_risk_score_detail()` reuse the main analysis cache instead of rebuilding content/separator evidence. Detection parameters and PASS/REVIEW behavior are unchanged.
- Further policy expansion without a version bump: content-primary candidate bbox fractions, minimum sizes, percentiles, coverage/mean/run/aspect weights, deskew edge-fit outer extraction and line-fit tolerance, and lucky-pass risk component weights/thresholds are now wired through `FormatTuning`. Current defaults preserve the previous behavior; `make_content_evidence_gray()` intentionally remains format-neutral for now so the analysis-cache semantics do not change.
- The current script still keeps the `--analysis` enhanced separator assist. V3.4 experimented with removing that layer, but V3.7's actual behavior is: `auto` tries enhanced separators only on weak separator evidence, `always` tries them every time, and `off` disables them. The same option also controls enhanced deskew angle candidates.
- Documentation and uninstall workflow cleanup without a version bump: README and the quick-start guide now explain why X5 Crop stays as a script plus launchers instead of an app package, how to uninstall cleanly, how removing Python or dependencies can affect other tools, that TIFFs in `needs_review/` are unprocessed source-file copies, and when partial mode should be used. The Release package policy now includes two uninstall launchers: `install/X5_Crop_Mac_uninstall.command` and `install/X5_Crop_win_uninstall.bat`.
- Documentation update without a version bump: README and the quick-start guide now explain the `dry run` concept. It is a test/analyze mode that reads TIFFs, runs detection, decides PASS/REVIEW, and may write Debug Analysis JPGs and reports, but does not export cropped frame TIFFs or modify the original TIFF.
- Runtime documentation update without a version bump: a normal 135 macOS launcher run measured 394 seconds for 48 TIFF files, or about 8.2 seconds per file. README and the quick-start guide now use this measured normal 135 runtime.
- Active features not yet opened to other formats: nearby separator active correction, lucky-pass risk, and leading-grid failure. They have format-policy hooks, but are not applied directly to half / xpan / 120 because those failure shapes are format-dependent. The current version is mainly optimized for normal 135 scans; other formats are selectable but have not been tuned as carefully and may be less stable than 135.
- Hard-fallback detail cleanup without a version bump: `hard_fallback_detection()` remains a review-only equal-split crash-prevention fallback, but its detail now keeps only fallback type, format/count/layout, work outer, and pitch. It no longer emits `candidate_competition` or duplicate gap center/score/method arrays.

Verification:

- V3.7 was compared against V3.6.12 with identical `deskew off` full dry-run settings. Across `Test/135`, `Test/半格`, and `Test/120` as 120-645 / 120-66 / 120-67, `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` all had 0 diffs. One 135 partial-mode smoke comparison also had 0 diffs.
- After the scale-threshold cleanup, a full `Test/135` `deskew off` dry run was compared against the pre-cleanup baseline. `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` had 0 diffs.
- After the second scale-threshold cleanup, another full `Test/135` `deskew off` dry run was compared against the previous 0-diff baseline with the same fields, and again had 0 diffs.
- After the format-policy cleanup, another full `Test/135` `deskew off` dry run was compared against the previous 0-diff baseline with the same fields, and again had 0 diffs.
- After the follow-up format-policy expansion, another full `Test/135` `deskew off` dry run was compared against the previous 0-diff baseline with the same fields, and again had 0 diffs.
- After the high-level policy cleanup, the pre-cleanup script was extracted from Git HEAD as a temporary baseline and compared against the current script with identical full `Test/135` `deskew off` dry-run settings. `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` all had 0 diffs.
- After the low-risk code cleanup, the pre-cleanup local script snapshot was used as a temporary baseline and compared against the current script with identical full `Test/135` `deskew off` dry-run settings. `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` all had 0 diffs.
- After the further policy expansion, the pre-cleanup local script snapshot was used as a temporary baseline and compared against the current script with identical full `Test/135` `deskew off` dry-run settings. `status`, `confidence`, `review_reasons`, `outer_box`, `frame_boxes`, and `gaps` all had 0 diffs.
- After the hard-fallback detail cleanup, `python3 -m py_compile` and a direct smoke call passed. This path only affects fallback report/detail and does not change normal 135 detection output.

### V3.6.12

V3.6.12 tunes the V3.6.11 format-aware `edge-pair` parameters. It uses full local `Test/120` and half-frame dry runs to calibrate non-135 behavior: half-frame results were already stable, so half-frame parameters are unchanged; 120-66 / 120-67 separators behave more like wide dark bands with low background-profile values, so their edge-pair search window, gutter width, edge threshold, and background threshold were relaxed while hard-gap replacement movement was tightened.

This update makes 120 separator evidence easier to record and visualize, but it does not loosen the core rule that only high-confidence detections may auto-crop. In full tests, 120-66 / 120-67 edge-pair accepted totals increased from 0 to 16, while all 120 samples still remained REVIEW; half-frame stayed at 6 `approved_auto` / 9 `needs_review`; a 135 focus comparison against V3.6.11 had no structural output changes.

Main changes:

- Bumps the script version to `3.6.12`.
- Tunes 120-66 / 120-67 edge-pair parameters for wider 120 dark bands: larger windows and gutter limits, lower edge/background thresholds.
- Parameterizes hard-gap replacement protection: 135 keeps the old strict shift guard; non-135 can only replace existing hard gaps with small movement, preventing edge-pair from moving native red separators too aggressively.
- Makes only a light preparatory adjustment for 120-645; the current `Test/120` set looks more like 3-frame 120 material, so it should not over-tune 645.
- Leaves half-frame parameters unchanged.
- Follow-up workflow cleanup: main launchers no longer pass `--report` for normal non-Debug-Analysis crop runs; only Debug Analysis dry runs still write reports. Release zip packaging now includes `X5_Crop.py`, `X5_Crop_Mac.command`, `X5_Crop_win.bat`, `README.md`, `快速启动_Quick_Start.md`, and the two installer launchers under `install/`, and excludes archive snapshots, license, and local test/output folders. The macOS installer now tries to make launchers executable and remove the download quarantine flag from the current Release folder; docs now include a Terminal command for cases where double-clicking the installer fails and clarify that after install users can copy `X5_Crop.py` plus the platform-matching main launcher as a pair into different TIFF folders: `X5_Crop_Mac.command` for macOS or `X5_Crop_win.bat` for Windows. A newly downloaded or unzipped folder needs the installer run again.

Verification:

- Half-frame full dry run: 15 files, 6 `approved_auto` / 9 `needs_review`, unchanged from V3.6.11.
- 120-66 full dry run: 16 files, 0 `approved_auto` / 16 `needs_review`, edge-pair accepted total increased from 0 to 16.
- 120-67 full dry run: 16 files, 0 `approved_auto` / 16 `needs_review`, edge-pair accepted total increased from 0 to 16.
- 120-645 full dry run: 16 files, 0 `approved_auto` / 16 `needs_review`, edge-pair accepted total stayed at 0.
- 135 focus dry run (`deskew off`) against V3.6.11: `X5_00014`, `X5_00026`, `X5_00036`, and `X5_00041` kept identical status, confidence, outer boxes, frame boxes, gap methods, and gap centers.

### V3.6.11

V3.6.11 extends `edge-pair` from 135 full strips to format-aware full-strip separator refinement across all formats. It preserves the original 135 parameters to avoid disturbing the current 135 baseline. Other formats use more conservative search windows, gutter widths, edge strength, background strength, and model-gap replacement quality thresholds. This lets 120, XPAN, half-frame, and other formats gain edge-pair separator evidence when black bars are imperfect but adjacent frame edges are reliable.

Main changes:

- Bumps the script version to `3.6.11`.
- Adds `EdgePairParams` and `edge_pair_params_for_format()`.
- `refine_gaps_by_edge_pairs()` now receives `format_name` and records the chosen parameters in detail.
- All full-strip formats now try edge-pair refinement. 135 keeps the original parameters; non-135 formats require stronger quality before edge-pair may replace model gaps such as grid/equal.

### V3.6.10

V3.6.10 is a low-risk cleanup after V3.6.9. It does not change detection flow, PASS/REVIEW logic, or output boxes. It removes an unused wrapper left after `light_hard_gap_trust` became the shared trust path, and fixes stale command-line help and diagnostic wording.

Main changes:

- Bumps the script version to `3.6.10`.
- Removes unused `grid_protection_trust()`.
- Updates the CLI description from V3.6.8 to V3.6.10.
- Fixes `--bleed-x` help from the old default 15 to the current default 20.
- Clarifies that `--analysis` affects both enhanced separator assist and enhanced deskew angle selection.
- Updates `diagnostics.purpose` so it no longer says “without changing V3.3.1 output”; it now says diagnostics observe signals without changing crop output.

### V3.6.9

V3.6.9 unifies red-gap trust between active correction and diagnostics. Previously, `grid_protection_trust` only looked at score, width, and grid residual, while `hard_trust` explained nearby conflicts, geometry conflicts, suspected internal edges, and suspected frame borders. V3.6.9 adds shared lightweight `light_hard_gap_trust`, so grid protection can recognize these suspicious signals before deciding whether a red gap may resist grid override.

This update is meant to reduce two-track logic rather than change output. In verification, V3.6.9 had no structured output changes compared with V3.6.8 on the full `Test/135` dry-run.

Main changes:

- Bumps the script version to `3.6.9`.
- Adds shared `light_hard_gap_trust`.
- `apply_robust_grid` uses shared trust before protecting hard gaps and records `trust_detail` in `protected_hard_gaps` / `overridden_hard_gaps`.
- Active grid protection can now prevent `nearby_separator_conflict`, `geometry_conflict`, `suspect_internal_edge`, and `suspect_frame_border` from becoming strong anchors.

Verification:

- Focus dry-run on `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`, `X5_00032`, `X5_00035`, and `X5_00041`; `X5_00041` stayed REVIEW and the other target samples stayed PASS.
- Full `Test/135` dry-run produced 42 `approved_auto` / 6 `needs_review`.
- Structured comparison against the V3.6.8 full report: changed `0`.

### V3.6.8

V3.6.8 keeps V3.6.7's nearby separator correction, but replaces the `X5_00041` exact single-anchor gate with a more general `lucky_pass_risk_score`. The score no longer requires the fixed `2/1/1/2` evidence mix. Instead, it combines these signals:

- Dependence on model gaps.
- Whether strong hard separator evidence is limited.
- Whether suspicious hard gaps are present.
- Whether strong overlap / continuous-content model gaps are present.
- Whether suspicious hard gaps and overlap model gaps appear together.
- Whether frame width geometry is stable enough to deserve a protective credit.
- Whether enough strong hard separators exist to deserve a protective credit.

When the risk score reaches `0.80`, the script adds `lucky_pass_risk` and caps confidence below the approval threshold. This still only sends suspicious PASS cases to REVIEW; it cannot make any image easier to approve.

Verification:

- Focus dry-run on `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`, `X5_00032`, `X5_00035`, and `X5_00041`; only `X5_00041` went to REVIEW.
- Focus scores: `X5_00041` scored `0.96`, above the `0.80` threshold; `X5_00007` scored `0.71`, and `X5_00035` scored `0.74`, both below threshold.
- Full `Test/135` dry-run produced 42 `approved_auto` / 6 `needs_review`, with `X5_00041` entering REVIEW as `lucky_pass_risk`.

### V3.6.7

V3.6.7 promotes V3.6.6's nearby separator check from diagnostics into a very narrow correction rule. It only moves a red hard separator when the nearby candidate is clearly stronger, local frame geometry improves, and overall width stability does not get worse. The pre-correction confidence is kept as a cap, so this correction cannot increase the chance of automatic approval.

V3.6.7 also adds a narrow single-anchor review gate for `X5_00041`-like lucky PASS shapes. The gate requires exactly this evidence mix: 2 strong hard gaps, 1 suspicious hard gap, 1 strong overlap model gap, and 2 model gaps. This sends `X5_00041` to REVIEW while avoiding collateral REVIEW changes on `X5_00007`, `X5_00023`, and `X5_00035`.

Main changes:

- Bumps the script version to `3.6.7`.
- Adds `nearby_separator_correction` detail data with accepted / rejected corrections, movement, candidate score, and geometry improvement.
- The correction can only keep or lower confidence; it cannot raise confidence.
- Adds `single_anchor_review_gate`; when triggered, it adds `single_anchor_pass_risk` and caps confidence below the approval threshold.

Verification:

- Focus dry-run on `X5_00014`, `X5_00026`, `X5_00032`, `X5_00041`, and `X5_00036`.
- After narrowing the gate, focus dry-run on `X5_00007`, `X5_00014`, `X5_00023`, `X5_00026`, `X5_00032`, `X5_00035`, and `X5_00041`, with only `X5_00041` going to REVIEW.
- Full `Test/135` dry-run produced 42 `approved_auto` / 6 `needs_review`. Compared with V3.6.6, only `X5_00026` and `X5_00041` changed structurally: `X5_00026` pulls back the first red gap, and `X5_00041` goes to REVIEW.

### V3.6.6

V3.6.6 starts separating red hard separators into "detected dark edge" versus "trustworthy frame separator." It focuses on samples where red separators can be wrong, while also preventing correct hard separators from being swallowed by grid.

Main changes:

- Adds `hard_trust` levels for every hard gap: `strong_separator`, `narrow_but_ok`, `suspect_internal_edge`, `suspect_frame_border`, `nearby_separator_conflict`, `geometry_conflict`, and `weak_or_ambiguous_separator`.
- Adds `nearby_separator_candidate` checks for hard gaps within `±4% pitch`.
- Marks suspicious hard gaps with magenta ticks in Debug Analysis.
- Adds `single_anchor_pass_risk` diagnostics for scans that have only local trustworthy anchors while other evidence remains weak.
- `apply_robust_grid` now records `protected_hard_gaps` and `overridden_hard_gaps`.
- `strong_separator` can block grid override only when the grid model residual is high. This avoids letting one off-model hard gap damage otherwise stable grid fits.
- Full comparison against V3.6.4 kept PASS/REVIEW at 43/5, with geometry changes only on `X5_00014` and `X5_00026`.

### V3.6.5: Diagnostics Worker Cap

V3.6.5 does not change detection logic. It only tunes parallelism for diagnostic runs. Normal launchers and normal command-line runs still cap at 2 workers; only explicit `--diagnostics` runs can use up to 4 workers. This lets the local diagnostics launcher finish Debug Analysis faster while keeping normal crop runs more conservative on memory.

Main changes:

- Changes the `--jobs` cap from a fixed 2 to 2 for normal runs and 4 for diagnostics runs.
- The local diagnostics launcher passes `--jobs 4`.
- Detection logic, PASS/REVIEW, output boxes, and TIFF output behavior are unchanged.

### V3.6.4: One-Sided White-Edge Outer Correction

V3.6.4 returns to the V3.6.2 detection baseline and does not use V3.6.3's strong-overlap-risk REVIEW gate. It solves a narrower issue first: when a 135 full strip has reliable hard separators at both ends, a complete content box, and a nearly all-white long-axis outer edge, the outer box may be pulled inward near the content edge before the existing gap / frame calculation continues.

Main changes:

- Removes `overlap_review_gate` from the active script; V3.6.3 remains archived as a paused reference direction.
- Adds `edge_hard_anchors` and `white_edge_slack` diagnostic fields to `outer_content_alignment_detail`.
- `white_edge_slack` only triggers when both end gaps are hard separators, content width nearly fills the outer box, the short axis is not suspicious, and one long-axis edge is nearly all white.
- When triggered, the existing `content_aligned_outer` retry is used. It does not raise confidence and does not make difficult scans pass automatically.
- This targets one-sided long-axis white-border excess only. It does not handle overlap / near-overlap or internal-edge hard-gap mistakes.

### V3.6.3: Overlap REVIEW Gate Experiment (Paused)

V3.6.3 promotes the overlap diagnostics from V3.6.1/V3.6.2 into a conservative REVIEW safety gate. It does not try to correct overlap and does not raise confidence; when a 135 full strip has strong overlap risk on a model gap, the scan is treated as difficult and is not auto-exported.

Main changes:

- Adds `overlap_review_gate`.
- Applies only to `film_format=135` and `strip=full`.
- Checks strong overlap risk only on model gaps: `grid`, `equal`, or `content`.
- When triggered, caps confidence below the threshold and adds `overlap_or_near_overlap_review`.
- The rule does not move gaps, change outer boxes, or change frame boxes; it only changes PASS/REVIEW.
- The goal is to prevent overlap, near-overlap, and content-continuity model fills from passing automatically.
- This direction is now paused: future work should first build finer grid trust / hard gap trust diagnostics and narrower correction rules instead of sending every strong-overlap model gap directly to REVIEW.

### V3.6.2: Low-Value Logic Cleanup

Status: stable GitHub Release.

Release asset:

- `X5-Crop-v3.6.2.zip`

V3.6.2 is the first detection cleanup step after V3.6.1 stabilized the diagnostic layer. It does not introduce a new automatic correction path; it reduces low-value methods and report / Debug Analysis noise so later correction proposals are easier to judge.

Main changes:

- `equal-broad-region` no longer appears as a separate gap method; it is folded into ordinary `equal`.
- Debug Analysis no longer keeps a separate color or role label for `equal-broad-region`.
- `hard_fallback_detection` remains as a crash-prevention review-only fallback, but its detail is smaller: `fallback_kind=review_only_equal_split`, without simulating a full candidate competition result.
- These changes should not loosen PASS/REVIEW and should not let fallback become an auto-pass path.
- It is released as stable, but overlapped frames, near-overlap, highly irregular local frame spacing, missing separators, or continuous image content can still be misdetected or cropped inaccurately. For these difficult scans, normal users should run Debug Analysis and review crop boxes manually.

### V3.6.1: Explicit Diagnostics Mode

V3.6.1 keeps the V3.3.1 output baseline and the V3.6 read-only diagnostic direction, but makes diagnostics explicit. Normal launchers do not pass `--diagnostics`, so ordinary Debug Analysis keeps the standard four-panel view without extra diagnostic report fields or diagnostic ticks.

Main changes:

- Adds CLI flag `--diagnostics` for local testing; it writes read-only `diagnostics` data and diagnostic ticks in the Separator evidence panel.
- Diagnostics still do not change output boxes, confidence, or PASS/REVIEW.
- Overlap / continuous-content diagnostics now use `weak`, `medium`, and `strong` risk levels. Only `strong` risk is drawn as cyan ticks in Debug Analysis, reducing visual noise.
- A local-only diagnostic launcher can be used for testing; it defaults to `deskew auto`, `dry run`, `debug analysis`, and `--diagnostics`.
- Normal macOS / Windows launchers do not enable diagnostics.

### V3.6: Diagnostic Cleanup

Goal:

- Start from the V3.3.1 output baseline and make reports / Debug Analysis easier to read.
- Build an observation layer for overlap and hard-gap trust without changing output.
- Let future improvements first prove themselves visually before becoming review-only or correction rules.

Main changes:

- Bumps the script version to `3.6`.
- Adds `diagnostics` to report detail.
- Labels each gap method role: separator evidence, enhanced separator evidence, geometry model, broad fallback, or content model.
- Records early `hard_trust` diagnostics for hard gaps; later V3.6.x versions expand this into the current finer labels, such as `strong_separator`, `narrow_but_ok`, `suspect_internal_edge`, `suspect_frame_border`, `nearby_separator_conflict`, and `geometry_conflict`.
- Marks model gaps as `overlap_like` when they look like overlap or continuous content risk.
- Adds lightweight Debug Analysis ticks in the Separator evidence panel: magenta for suspect hard gaps and cyan for overlap / continuous-content model gaps.
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed by fallback, rescue, grid, or semantic validation logic.

Known limitations:

- It still does not actively correct overlap, irregular spacing, red/grid conflict, or internal-edge false positives.
- `diagnostics` is observation-only; any future diagnostic-to-correction promotion must first protect known-good scans.

Verification:

- Used rollback commit `8928f70` as the V3.3.1 baseline and ran a full `Test/135` dry run over 48 files.
- Compared V3.6 against that V3.3.1 baseline: `status`, `outer_box`, `frame_boxes`, and confidence are all identical.
- V3.6 full result is 43 `approved_auto` and 5 `needs_review`.

### V3.5: Hard-Gap Semantic Validation Experiment

Status: paused / rolled back from active script.

Goal:

- Make red hard separator boxes more trustworthy.
- Detect cases where a high-score red edge-pair is actually an internal image edge rather than a real film-frame separator.
- Let grid handle only clearly suspicious red gaps without loosening PASS/REVIEW.

Implementation idea:

- Run a lightweight validation layer after `edge_refine` and before robust grid.
- Reuse cached content evidence and edge-refine profiles.
- For each accepted hard gap, inspect small local windows around the gap: gap content, left/right content, content continuity, background/separator profile, and edge/activity profile.
- Label hard gaps as strong or suspect.
- Demote only very narrow, content-continuous, internal-edge-like hard gaps to model gaps.

Why it was paused:

- Although it helped explain at least one false hard separator pattern, the active V3.5 behavior made some previously accurate scans worse.
- The user observed regressions on important known-good scans, so this logic was removed from the active script.

Future notes:

- Do not reintroduce this as a broad rule.
- If revisited, start as report-only diagnostics before it can change gap methods.
- It needs stronger safeguards for known-good scans and perhaps a per-gap confidence label that does not immediately alter geometry.

### V3.4.2: Local Grid Segment Experiment

Status: paused / rolled back from active script.

Goal:

- Improve behavior on irregular spacing, near-overlap, or partly unstable strip geometry.
- Let grid remain useful without letting global equal spacing overwrite good red hard separators.

Implementation idea:

- Use strong hard separators as local anchors.
- Reposition only model-only gaps (`grid` / `equal`) between or near those anchors using a local pitch.
- Do not move hard separators.
- Do not increase confidence merely because local grid adjusted a model gap.
- Record details in `local_grid`.

Why it was paused:

- It still changed geometry on scans that were previously accurate.
- Local grid can be useful, but it needs stricter proof that the target model gap is genuinely wrong before it changes geometry.

Future notes:

- If revived, keep it limited to diagnostics first.
- Consider drawing local-grid suggestions in Debug Analysis without using them for output boxes.
- Require stronger evidence that local spacing is actually irregular and that the adjusted position aligns with visual separators.

### V3.4.1: Preserve Strong Hard Gaps

Status: paused / reference direction.

Goal:

- Fix cases where robust grid overwrote an accurate red hard separator.
- Make red hard evidence authoritative when it is strong and plausible.

Main changes:

- Strong `detected` / `edge-pair` gaps are preserved even if robust grid predicts a different center.
- Grid can still fill missing or weak model gaps.
- Grid/hard conflicts are recorded in `grid.hard_conflicts`.
- If full geometry is already accepted, the same evidence is not double-counted as `unstable_frame_width`.

Why it matters:

- The separator evidence panel becomes easier to interpret because a correct red hard separator remains red.
- Grid is treated as model support, not as a stronger source than real separator evidence.

### V3.4: Detection Simplification

Status: development baseline retained by V3.4.1. The notes below describe that experiment's behavior; the current V3.9 script still keeps the conservative `--analysis` enhanced separator assist.

Goal:

- Remove low-value or confusing detection layers.
- Make Debug Analysis easier to read.
- Reduce maintenance cost and duplicated logic.

Main changes:

- Removed the enhanced separator layer from active separator detection.
- `--analysis` no longer drives enhanced separator acceptance; it remains relevant to analysis/deskew behavior.
- Removed `enhanced-detected` from active gap methods and README color semantics.
- Folded `equal-broad-region` into ordinary `equal`.
- Full-strip detection no longer creates a separate content candidate when the separator/geometric candidate is already the main path; content is validation.
- The fallback path remains small and conservative.

Effect:

- Debug evidence uses fewer overlapping colors and concepts.
- Full-strip logic is easier to maintain.
- Fewer old-chain decisions compete with the active candidate decision scoring path.

### V3.3.2: Conservative Overlap-Aware Gap Handling

Status: development, not active after rollback except as historical reference.

Goal:

- Improve near-overlap or continuous-content cases without making them pass more easily.

Main changes:

- Model gaps that look overlap-like can be marked `overlap_like=true`.
- Overlap-like gaps are not used as strong same-frame-size anchors.
- This is intended to reduce geometry correction based on suspect model gaps.

Important principle:

- Overlap handling should explain or restrain geometry correction. It should not increase confidence or push difficult scans into auto-pass.

### V3.3.1: Stable Release / V3.6 Output Baseline

Status: stable GitHub Release / V3.6 output baseline.

Release asset:

- `X5-Crop-v3.3.1.zip`

Main behavior:

- Keeps the stable V3/V3.2 ordinary outer / gap / candidate chain.
- Keeps output-only bleed separation.
- Preserves conservative PASS/REVIEW behavior.
- Includes bilingual README, launchers, install scripts, archive snapshots, and MIT License.
- GitHub Release notes include bilingual quick start and changes since `v3`.

Why it is stable:

- It was packaged as the user-facing release before later development experiments.
- It favors conservative known-good behavior over newer unproven detection ideas.

### V3.3: Output-Only Bleed Separation

Status: development ancestor of stable release behavior.

Goal:

- Prevent bleed from changing detection decisions.

Main changes:

- Detection uses no bleed internally.
- Output/report/Debug Analysis frame boxes apply output bleed afterward.
- Default output bleed is long axis 20px and short axis 10px.
- Horizontal strips use left/right as long-axis bleed; vertical strips rotate the interpretation accordingly.

Why it matters:

- Increasing output safety margin no longer changes outer boxes, gap selection, confidence, or PASS/REVIEW.

### V3.2: Return To V3 Detection Chain

Status: development.

Goal:

- Restore the more reliable V3-style behavior after V3.1.x experiments caused regressions.

Main changes:

- Removed aggressive content-aligned outer expansion from the active chain.
- Removed separator-derived outer competition from the active chain.
- Removed local separator rescue from the active chain.
- Kept the special REVIEW guard for the known leading-grid failure shape.

Important principle:

- Rollback restored the ordinary detection route while keeping safety gates that prevent obvious guesses from passing.

### V3.1.x: Aggressive Correction Experiments

Status: experimental, not active.

Ideas tested:

- More aggressive content-aligned outer correction.
- Separator-derived outer boxes when ordinary outer detection was weak or missing.
- Local separator rescue near predicted grid positions.
- Extra same-frame-size fitting triggered by newly rescued gap evidence.

Why not kept:

- These ideas sometimes helped edge cases but also changed good scans too much.
- They increased the risk that difficult images would appear high-confidence for the wrong reason.
- The project priority remains conservative auto-cropping: only high-confidence detections should auto-crop.

Lessons:

- Rescue logic should be diagnostic or review-only until it proves it does not harm known-good scans.
- Output safety margin is better handled as output-only bleed, not detection geometry.
- Debug visuals must clearly distinguish evidence from model guesses.

### V3.0: Baseline X5 Crop

Status: baseline archived snapshot.

Main capabilities:

- Standalone `X5_Crop.py` workflow.
- Format-aware cropping for 135, half-frame, XPAN, 645, 66, 67, and 135 dual.
- Conservative PASS/REVIEW separation.
- Debug Analysis JPG output.
- TIFF quality and metadata preservation policy.
- macOS and Windows launchers.

### Development Testing Notes

Default testing rule:

- For detection logic changes, future development tests should use `--deskew off` unless the change specifically touches deskew.
- This keeps regression checks faster and focuses them on detection geometry.

Suggested focus set after detection changes:

- `X5_00007`
- `X5_00022`
- `X5_00032`
- `X5_00036`
- `X5_00038`
- `X5_00044`
- `X5_00051`
- `X5_00052`

Core regression rule:

- Do not improve one difficult case by damaging known-good cases.
- Do not let fallback, rescue, grid, or semantic validation logic make weak-evidence images auto-pass.
- If a new idea changes geometry on known-good scans, first make it report-only or review-only before letting it affect output boxes.

Release policy:

- GitHub Releases are the stable user-facing downloads.
- The repository `main` branch may contain active development, experiments, or rollback work.
- Every named development version should be preserved as an `archive/X5_Crop_v*.py` snapshot before moving on, including experiments that are later paused or rolled back.
- When a development version becomes stable enough for users, create a new GitHub Release and update `README.md`, `CHANGELOG.md`, and `AGENTS.md` together.
