# X5 Crop 更新日志 / Changelog

## 中文更新日志

这份更新日志用于记录 X5 Crop 的检测逻辑、工作流、回归验证和发布策略变化。它面向继续开发、行为排查、版本比较和必要时的回滚，不作为普通用户的快速使用说明。

如果只是使用脚本，请优先阅读 `快速启动_Quick_Start.md` 和 `README.md`。本文件保留更细的开发背景、实验结论和验证结果。

当前 active 脚本：`X5_Crop.py` V4.0

当前稳定 GitHub Release：`v4.0`

### 版本状态

| 版本 | 状态 | 摘要 |
|---|---|---|
| V4.0 | 稳定 Release / 当前 active 开发版 | 大胆模块化重写版：根入口 `X5_Crop.py` 变薄，实际检测、I/O、几何、证据、Debug、report、deskew 和 CLI 职责拆进 `x5crop/` 多个模块，`core.py` 仅保留兼容导出。新增单文件发布版生成器，让 Release 用户仍然只需要脚本本体和启动器。全量 135 default-deskew dry run 对比 V3.9 为 0 diff。 |
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

### 当前 Active 版本：V4.0

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
- 不改版本号的 hard fallback detail 清理：`hard_fallback_detection()` 继续只是 review-only equal split 防崩兜底，但 detail 只保留 fallback 类型、format/count/layout、work outer 和 pitch，不再输出 `v2_competition` 或重复的 gap center/score/method 数组。
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
- `diagnostics_v3_6.purpose` 不再写 “without changing V3.3.1 output”，改成更准确的“观察诊断信号且不改变 crop output”。

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

- 新增 CLI 参数 `--diagnostics`，用于本地测试时写入只读 `diagnostics_v3_6` 并在 Separator evidence 面板显示诊断 tick。
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
- 新增 `diagnostics_v3_6` detail 字段。
- 为每个 gap 标记 method role：separator evidence、enhanced separator evidence、geometry model、broad fallback 或 content model。
- 为 hard gap 记录早期 `hard_trust` 诊断；后续 V3.6.x 已扩展为更细的当前分级，例如 `strong_separator`、`narrow_but_ok`、`suspect_internal_edge`、`suspect_frame_border`、`nearby_separator_conflict` 和 `geometry_conflict`。
- 为 model gap 标记 `overlap_like`，用于提示叠片或连续内容风险。
- Debug Analysis 的 Separator evidence 面板增加轻量诊断 tick：magenta 是可疑 hard gap，cyan 是疑似 overlap / continuous-content model gap。
- 坚持困难图、弱证据图不能因为 fallback、rescue、grid 或语义校验逻辑而自动通过。

已知限制：

- 它仍不主动修正叠片、片距不稳定、红框/grid 冲突或内部边缘误判。
- `diagnostics_v3_6` 只是观察层；之后要把任何诊断变成实际修正规则，都必须先通过已知准确样本保护。

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
- 更少旧链路决策会与 active V2 candidate scoring path 竞争。

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

Current active script: `X5_Crop.py` V4.0

Current stable GitHub Release: `v4.0`

### Version Status

| Version | Status | Summary |
|---|---|---|
| V4.0 | Stable Release / Current active development | Bold modular rewrite: root `X5_Crop.py` is thin, while detection, I/O, geometry, evidence, Debug, report, deskew, and CLI responsibilities now live in dedicated `x5crop/` modules; `core.py` is only a compatibility export surface. Adds a standalone release-script builder so Release users still need only the script and launcher. A full 135 default-deskew dry run compared with V3.9 had 0 diffs. |
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

### Current Active: V4.0

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
- Hard-fallback detail cleanup without a version bump: `hard_fallback_detection()` remains a review-only equal-split crash-prevention fallback, but its detail now keeps only fallback type, format/count/layout, work outer, and pitch. It no longer emits `v2_competition` or duplicate gap center/score/method arrays.

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
- Updates `diagnostics_v3_6.purpose` so it no longer says “without changing V3.3.1 output”; it now says diagnostics observe signals without changing crop output.

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

- Adds CLI flag `--diagnostics` for local testing; it writes read-only `diagnostics_v3_6` data and diagnostic ticks in the Separator evidence panel.
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
- Adds `diagnostics_v3_6` to report detail.
- Labels each gap method role: separator evidence, enhanced separator evidence, geometry model, broad fallback, or content model.
- Records early `hard_trust` diagnostics for hard gaps; later V3.6.x versions expand this into the current finer labels, such as `strong_separator`, `narrow_but_ok`, `suspect_internal_edge`, `suspect_frame_border`, `nearby_separator_conflict`, and `geometry_conflict`.
- Marks model gaps as `overlap_like` when they look like overlap or continuous content risk.
- Adds lightweight Debug Analysis ticks in the Separator evidence panel: magenta for suspect hard gaps and cyan for overlap / continuous-content model gaps.
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed by fallback, rescue, grid, or semantic validation logic.

Known limitations:

- It still does not actively correct overlap, irregular spacing, red/grid conflict, or internal-edge false positives.
- `diagnostics_v3_6` is observation-only; any future diagnostic-to-correction promotion must first protect known-good scans.

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
- Fewer old-chain decisions compete with the active V2 candidate scoring path.

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
