# X5 Crop 更新日志 / Changelog

## 中文更新日志

这份更新日志保留在仓库中，用于开发、回滚和之后复盘。它记录的检测逻辑与工作流变化比面向普通用户的 `README.md` 更详细。

当前 active 脚本：`X5_Crop.py` V3.6.4

当前稳定 GitHub Release：`v3.6.2`

### 版本状态

| 版本 | 状态 | 摘要 |
|---|---|---|
| V3.6.4 | 当前 active 开发版 | 回到 V3.6.2 检测基线，并新增只针对首尾 hard separator 可靠时的单侧长轴白边外框收紧。 |
| V3.6.3 | 已暂停 / 参考方向 | 将叠片 / 近似叠片作为困难图处理：135 full strip 的 strong overlap-risk model gap 会进入 REVIEW。该方向暂时搁置。 |
| V3.6.2 | 稳定发布版 | 合并低收益 `equal-broad-region` method，并把 hard fallback 缩小成 review-only equal split fallback。叠片、近似叠片、局部片距不稳定等困难图仍可能误识别。 |
| V3.6.1 | 开发版 | 继续优化诊断层：诊断报告和 Debug Analysis 诊断 tick 只在显式 `--diagnostics` 时生成；普通启动器不开启诊断。 |
| V3.6 | 开发版 | 从 V3.3.1 输出基线出发做诊断清理，新增只读红框可信度和叠片/连续内容诊断，不改变 V3.3.1 输出。 |
| V3.5 | 已暂停 / 已回滚 | 红色 hard gap 语义校验实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.2 | 已暂停 / 已回滚 | 局部 grid 分段实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.1 | 已暂停 / 参考方向 | 当强 hard separator 与 robust grid 冲突时，优先保留强 hard separator。这个方向仍有参考价值，但当前先回到 V3.3.1 作为稳定基线。 |
| V3.4 | 简化检测基线 | 移除低收益增强分隔层，并简化候选生成。 |
| V3.3.2 | 开发版 | 保守的叠片/近似叠片 gap 处理。 |
| V3.3.1 | 稳定发布版 / V3.6 输出基线 | 稳定打包版本，基于 V3/V3.2 风格检测链路，并加入只在输出阶段生效的 bleed。 |
| V3.3 | 开发版 | 检测 bleed 与输出 bleed 分离。 |
| V3.2 | 开发版 | 在 V3.1.x 回退后恢复 V3 风格检测链路。 |
| V3.1.x | 实验版 | 激进外框/gap 修复实验，稳定性不足。 |
| V3.0 | 基线版 | X5 Crop 主脚本与用户工作流基础。 |

### 当前 Active 版本：V3.6.4

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

V3.6 从 V3.3.1 输出基线出发。它的目标不是立刻让检测“更聪明”，而是先清理诊断结构，让红框可信度、叠片/连续内容和证据/模型角色更容易观察。V3.6 不改变 V3.3.1 的 `status`、`outer_box`、`frame_boxes` 或 confidence。

主要检测行为：

- 保留稳定的 V3/V3.2 风格 ordinary outer / gap / candidate 主链路。
- bleed 只在最终输出、报告和 Debug Analysis 中应用，不参与 outer、gap、confidence 或 PASS/REVIEW。
- 保持保守的 PASS/REVIEW 行为。
- Debug JPG 和 Debug Analysis JPG 顶部状态栏会显示生成脚本版本。
- 新增只读 `diagnostics_v3_6` 报告字段，记录 hard gap trust、overlap-like model gap 和 method roles。
- Separator evidence 面板会用轻量辅助 tick 显示诊断结果：magenta 表示可疑 hard gap，cyan 表示疑似 overlap / continuous-content model gap。这些标记不参与裁切。
- 坚持困难图、弱证据图不能因为 fallback、rescue、grid 或语义校验逻辑而自动通过。

为什么现在偏向这一版：

- 它保留 V3.3.1 的输出结果，同时让后续问题更容易定位。
- 它把“证据”和“模型推测”的角色写进报告，为之后处理叠片和红框可信度做准备。
- 后续优化可以先做成诊断层或 review-only 层，在证明不伤害基线前不改变输出框。

已知限制：

- 它仍不主动修正叠片、片距不稳定、红框/grid 冲突或内部边缘误判。
- `diagnostics_v3_6` 只是观察层；之后要把任何诊断变成实际修正规则，都必须先通过已知准确样本保护。

### V3.6：诊断清理版

状态：当前 active 开发版。

目标：

- 从 V3.3.1 输出基线出发，清理报告和 Debug Analysis 的可读性。
- 在不改变输出的情况下，为叠片和红框可信度问题建立观察层。
- 让后续优化可以先看准，再决定是否进入 review-only 或 correction rule。

主要变化：

- 版本号升为 `3.6`。
- 新增 `diagnostics_v3_6` detail 字段。
- 为每个 gap 标记 method role：separator evidence、enhanced separator evidence、geometry model、broad fallback 或 content model。
- 为 hard gap 记录 `hard_trust`：`strong_separator_evidence`、`uncertain_separator_evidence` 或 `suspect_internal_edge`。
- 为 model gap 标记 `overlap_like`，用于提示叠片或连续内容风险。
- Debug Analysis 的 Separator evidence 面板增加轻量诊断 tick：magenta 是可疑 hard gap，cyan 是疑似 overlap / continuous-content model gap。

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

状态：V3.4.1 保留的开发基线。

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

This changelog is kept in the repository for development, rollback, and future debugging. It records detection and workflow decisions in more detail than the user-facing `README.md`.

Current active script: `X5_Crop.py` V3.6.4

Current stable GitHub Release: `v3.6.2`

### Version Status

| Version | Status | Summary |
|---|---|---|
| V3.6.4 | Current active development | Returns to the V3.6.2 detection baseline and adds a narrow one-sided long-axis white-edge outer tightening rule when both end hard separators are reliable. |
| V3.6.3 | Paused / reference direction | Treats overlap / near-overlap as difficult: strong overlap-risk model gaps in 135 full strips are sent to REVIEW. This direction is paused. |
| V3.6.2 | Stable Release | Folds the low-value `equal-broad-region` method into ordinary `equal`, and shrinks hard fallback into a review-only equal split fallback. Overlap, near-overlap, and locally irregular spacing can still be misdetected. |
| V3.6.1 | Development | Continues the diagnostic layer: diagnostic report data and Debug Analysis diagnostic ticks are only generated with explicit `--diagnostics`; normal launchers do not enable diagnostics. |
| V3.6 | Development | Diagnostic cleanup from the V3.3.1 output baseline. Adds read-only hard-gap trust and overlap/continuous-content diagnostics without changing V3.3.1 output. |
| V3.5 | Paused / rolled back | Hard-gap semantic validation experiment. Removed from the active script after accuracy regressions. |
| V3.4.2 | Paused / rolled back | Local grid segment experiment. Removed from the active script after accuracy regressions. |
| V3.4.1 | Paused / reference direction | Strong hard separators stay authoritative when they conflict with robust grid. This direction remains useful, but the active baseline is back to V3.3.1. |
| V3.4 | Simplified detection baseline | Removed low-value enhanced separator logic and simplified candidate generation. |
| V3.3.2 | Development | Conservative overlap-like gap handling. |
| V3.3.1 | Stable Release / V3.6 output baseline | Stable packaged release based on V3/V3.2 style detection plus output-only bleed. |
| V3.3 | Development | Detection bleed and output bleed separated. |
| V3.2 | Development | Returned to V3-style detection after V3.1.x regressions. |
| V3.1.x | Experimental | Aggressive outer/gap rescue ideas. Not stable enough. |
| V3.0 | Baseline | Main X5 Crop script and user workflow foundation. |

### Current Active: V3.6.4

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

V3.6 starts from the V3.3.1 output baseline. Its goal is not to make detection smarter immediately; it first makes diagnostics easier to read so hard-gap trust, overlap/continuous-content risk, and evidence/model roles can be observed. V3.6 does not change V3.3.1 `status`, `outer_box`, `frame_boxes`, or confidence.

Main detection behavior:

- Keeps the stable V3/V3.2 style ordinary outer / gap / candidate path.
- Applies bleed only to final output, reports, and Debug Analysis, not to outer boxes, gaps, confidence, or PASS/REVIEW.
- Preserves conservative PASS/REVIEW behavior.
- Shows the generating script version in Debug JPG and Debug Analysis JPG status bars.
- Adds the read-only `diagnostics_v3_6` report field for hard-gap trust, overlap-like model gaps, and method roles.
- Adds lightweight diagnostic ticks to the Separator evidence panel: magenta means suspect hard gap, cyan means overlap / continuous-content model-gap risk. These marks do not participate in cropping.
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed by fallback, rescue, grid, or semantic validation logic.

Why this version is preferred right now:

- It preserves the V3.3.1 output result while making future problems easier to locate.
- It records evidence/model roles in the report, preparing the ground for future overlap and hard-gap trust work.
- Future improvements can start as diagnostics or review-only layers before they are allowed to alter output boxes.

Known limitations:

- It still does not actively correct overlap, irregular spacing, red/grid conflict, or internal-edge false positives.
- `diagnostics_v3_6` is observation-only; any future diagnostic-to-correction promotion must first protect known-good scans.

### V3.6: Diagnostic Cleanup

Status: current active development version.

Goal:

- Start from the V3.3.1 output baseline and make reports / Debug Analysis easier to read.
- Build an observation layer for overlap and hard-gap trust without changing output.
- Let future improvements first prove themselves visually before becoming review-only or correction rules.

Main changes:

- Bumps the script version to `3.6`.
- Adds `diagnostics_v3_6` to report detail.
- Labels each gap method role: separator evidence, enhanced separator evidence, geometry model, broad fallback, or content model.
- Records `hard_trust` for hard gaps: `strong_separator_evidence`, `uncertain_separator_evidence`, or `suspect_internal_edge`.
- Marks model gaps as `overlap_like` when they look like overlap or continuous content risk.
- Adds lightweight Debug Analysis ticks in the Separator evidence panel: magenta for suspect hard gaps and cyan for overlap / continuous-content model gaps.

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

Status: development baseline retained by V3.4.1.

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
