# X5 Crop 更新日志 / Changelog

## 中文更新日志

这份更新日志保留在仓库中，用于开发、回滚和之后复盘。它记录的检测逻辑与工作流变化比面向普通用户的 `README.md` 更详细。

当前 active 脚本：`X5_Crop.py` V3.4.1

当前稳定 GitHub Release：`v3.3.1`

### 版本状态

| 版本 | 状态 | 摘要 |
|---|---|---|
| V3.5 | 已暂停 / 已回滚 | 红色 hard gap 语义校验实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.2 | 已暂停 / 已回滚 | 局部 grid 分段实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.1 | 当前 active 开发版 | 当强 hard separator 与 robust grid 冲突时，优先保留强 hard separator。 |
| V3.4 | 简化检测基线 | 移除低收益增强分隔层，并简化候选生成。 |
| V3.3.2 | 开发版 | 保守的叠片/近似叠片 gap 处理。 |
| V3.3.1 | 稳定发布版 | 稳定打包版本，基于 V3/V3.2 风格检测链路，并加入只在输出阶段生效的 bleed。 |
| V3.3 | 开发版 | 检测 bleed 与输出 bleed 分离。 |
| V3.2 | 开发版 | 在 V3.1.x 回退后恢复 V3 风格检测链路。 |
| V3.1.x | 实验版 | 激进外框/gap 修复实验，稳定性不足。 |
| V3.0 | 基线版 | X5 Crop 主脚本与用户工作流基础。 |

### 当前 Active 版本：V3.4.1

V3.4.1 现在是 active 版本，因为后续实验让一些原本很准的扫描结果变差。观察到 `X5_00051`、`X5_00044`、`X5_00038`、`X5_00022` 等样本出现回退后，active 脚本暂时回滚到这一版。

主要检测行为：

- 保留 V3/V3.2 风格的普通 outer / gap / candidate 主链路。
- 保留 V3.4 的检测简化：没有增强分隔层，没有 full strip 独立 content candidate；content 只作为校验，不作为 full strip 的竞争候选；`equal-broad-region` 合并进普通 `equal`。
- 当 robust grid 与强 hard separator 证据冲突时，保留强 hard separator。
- 在 `grid.hard_conflicts` 里记录 hard/grid 的冲突。
- 保持输出 bleed 不参与检测评分。
- 坚持困难图、弱证据图不能因为 fallback 或 rescue 逻辑而自动通过。

为什么现在偏向这一版：

- 它比 V3.4.2/V3.5 更能保护已知准确样本的结果。
- 它避免 grid / local rescue 过度覆盖正确的红色 hard separator 证据。
- 在重新设计后续优化时，这一版的检测链路更容易理解和维护。

已知限制：

- 它不包含后续的 local-grid 或 hard-gap semantic validation 实验。
- 一些真正的内部边缘误判之后可能仍需处理。
- 之后的修复应该更窄，并且在重新 active 之前必须明确保护已知准确样本。

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

状态：当前 active 开发版。

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

### V3.3.1：稳定发布版

状态：GitHub 稳定发布版。

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

Current active script: `X5_Crop.py` V3.4.1

Current stable GitHub Release: `v3.3.1`

### Version Status

| Version | Status | Summary |
|---|---|---|
| V3.5 | Paused / rolled back | Hard-gap semantic validation experiment. Removed from the active script after accuracy regressions. |
| V3.4.2 | Paused / rolled back | Local grid segment experiment. Removed from the active script after accuracy regressions. |
| V3.4.1 | Current active development version | Strong hard separators stay authoritative when they conflict with robust grid. |
| V3.4 | Simplified detection baseline | Removed low-value enhanced separator logic and simplified candidate generation. |
| V3.3.2 | Development | Conservative overlap-like gap handling. |
| V3.3.1 | Stable Release | Stable packaged release based on V3/V3.2 style detection plus output-only bleed. |
| V3.3 | Development | Detection bleed and output bleed separated. |
| V3.2 | Development | Returned to V3-style detection after V3.1.x regressions. |
| V3.1.x | Experimental | Aggressive outer/gap rescue ideas. Not stable enough. |
| V3.0 | Baseline | Main X5 Crop script and user workflow foundation. |

### Current Active: V3.4.1

V3.4.1 is currently active because later experiments made several previously good scans less accurate. The active script was temporarily rolled back to this version after regressions were observed on scans including `X5_00051`, `X5_00044`, `X5_00038`, and `X5_00022`.

Main detection behavior:

- Keeps the V3/V3.2 style ordinary outer / gap / candidate path.
- Keeps V3.4 detection simplification: no enhanced separator layer, no independent full-strip content candidate, content as validation rather than a competing full-strip candidate, and `equal-broad-region` folded into ordinary `equal`.
- Preserves strong hard separator evidence when robust grid disagrees with it.
- Records hard/grid disagreements in `grid.hard_conflicts`.
- Keeps output bleed outside detection scoring.
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed by fallback or rescue logic.

Why this version is preferred right now:

- It preserves accurate behavior on known-good scans better than V3.4.2/V3.5.
- It avoids allowing grid/local rescue to override correct red hard separator evidence too aggressively.
- It keeps the detection chain easier to reason about while future improvements are being redesigned.

Known limitations:

- It does not contain the later local-grid or hard-gap semantic validation experiments.
- Some true internal-edge false positives may still need future treatment.
- Future fixes should be narrower and should explicitly protect known-good scans before being made active again.

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

Status: current active development version.

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

### V3.3.1: Stable Release

Status: stable GitHub Release.

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
