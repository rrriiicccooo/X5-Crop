# X5 Crop Changelog / 更新日志

This changelog is kept in the repository for development, rollback, and future
debugging. It records detection and workflow decisions in more detail than the
user-facing `README.md`.

这份更新日志会保留在仓库里，用于开发、回滚和之后复盘。它记录的检测逻辑与工作流变化会比面向普通用户的 `README.md` 更详细。

Current active script / 当前 active 脚本：`X5_Crop.py` V3.4.1

Current stable GitHub Release / 当前稳定发布版本：`v3.3.1`

## Version Status / 版本状态

| Version / 版本 | Status / 状态 | Summary / 摘要 |
|---|---|---|
| V3.5 | Paused / rolled back<br>已暂停 / 已回滚 | Hard-gap semantic validation experiment. Removed from the active script after accuracy regressions.<br>红色 hard gap 语义校验实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.2 | Paused / rolled back<br>已暂停 / 已回滚 | Local grid segment experiment. Removed from the active script after accuracy regressions.<br>局部 grid 分段实验。因为准确性回退，已从 active 脚本移除。 |
| V3.4.1 | Current active development version<br>当前 active 开发版 | Strong hard separators stay authoritative when they conflict with robust grid.<br>当强 hard separator 与 robust grid 冲突时，优先保留强 hard separator。 |
| V3.4 | Simplified detection baseline<br>简化检测基线 | Removed low-value enhanced separator logic and simplified candidate generation.<br>移除低收益增强分隔层，并简化候选生成。 |
| V3.3.2 | Development<br>开发版 | Conservative overlap-like gap handling.<br>保守的叠片/近似叠片 gap 处理。 |
| V3.3.1 | Stable Release<br>稳定发布版 | Stable packaged release based on V3/V3.2 style detection plus output-only bleed.<br>稳定打包版本，基于 V3/V3.2 风格检测链路，并加入只在输出阶段生效的 bleed。 |
| V3.3 | Development<br>开发版 | Detection bleed and output bleed separated.<br>检测 bleed 与输出 bleed 分离。 |
| V3.2 | Development<br>开发版 | Returned to V3-style detection after V3.1.x regressions.<br>在 V3.1.x 回退后恢复 V3 风格检测链路。 |
| V3.1.x | Experimental<br>实验版 | Aggressive outer/gap rescue ideas. Not stable enough.<br>激进外框/gap 修复实验，稳定性不足。 |
| V3.0 | Baseline<br>基线版 | Main X5 Crop script and user workflow foundation.<br>X5 Crop 主脚本与用户工作流基础。 |

## Current Active: V3.4.1 / 当前 Active 版本：V3.4.1

V3.4.1 is currently active because later experiments made several previously
good scans less accurate. The active script was temporarily rolled back to this
version after regressions were observed on scans including `X5_00051`,
`X5_00044`, `X5_00038`, and `X5_00022`.

V3.4.1 现在是 active 版本，因为后续实验让一些原本很准的扫描结果变差。观察到 `X5_00051`、`X5_00044`、`X5_00038`、`X5_00022` 等样本出现回退后，active 脚本暂时回滚到这一版。

Main detection behavior / 主要检测行为：

- Keeps the V3/V3.2 style ordinary outer / gap / candidate path.
- 保留 V3/V3.2 风格的普通 outer / gap / candidate 主链路。
- Keeps V3.4 detection simplification: no enhanced separator layer, no independent full-strip content candidate, content as validation rather than a competing full-strip candidate, and `equal-broad-region` folded into ordinary `equal`.
- 保留 V3.4 的检测简化：没有增强分隔层，没有 full strip 独立 content candidate；content 只作为校验，不作为 full strip 的竞争候选；`equal-broad-region` 合并进普通 `equal`。
- Preserves strong hard separator evidence when robust grid disagrees with it.
- 当 robust grid 与强 hard separator 证据冲突时，保留强 hard separator。
- Records hard/grid disagreements in `grid.hard_conflicts`.
- 在 `grid.hard_conflicts` 里记录 hard/grid 的冲突。
- Keeps output bleed outside detection scoring.
- 保持输出 bleed 不参与检测评分。
- Keeps the rule that difficult or weak-evidence scans must not be auto-passed by fallback or rescue logic.
- 坚持困难图、弱证据图不能因为 fallback 或 rescue 逻辑而自动通过。

Why this version is preferred right now / 为什么现在偏向这一版：

- It preserves accurate behavior on known-good scans better than V3.4.2/V3.5.
- 它比 V3.4.2/V3.5 更能保护已知准确样本的结果。
- It avoids allowing grid/local rescue to override correct red hard separator evidence too aggressively.
- 它避免 grid / local rescue 过度覆盖正确的红色 hard separator 证据。
- It keeps the detection chain easier to reason about while future improvements are being redesigned.
- 在重新设计后续优化时，这一版的检测链路更容易理解和维护。

Known limitations / 已知限制：

- It does not contain the later local-grid or hard-gap semantic validation experiments.
- 它不包含后续的 local-grid 或 hard-gap semantic validation 实验。
- Some true internal-edge false positives may still need future treatment.
- 一些真正的内部边缘误判之后可能仍需处理。
- Future fixes should be narrower and should explicitly protect known-good scans before being made active again.
- 之后的修复应该更窄，并且在重新 active 之前必须明确保护已知准确样本。

## V3.5: Hard-Gap Semantic Validation Experiment / V3.5：Hard Gap 语义校验实验

Status / 状态：paused / rolled back from active script；已暂停 / 已从 active 脚本回滚。

Goal / 目标：

- Make red hard separator boxes more trustworthy.
- 让红色 hard separator 框更可信。
- Detect cases where a high-score red edge-pair is actually an internal image edge rather than a real film-frame separator.
- 识别“高分红色 edge-pair 其实是画面内部边缘，而不是真正胶片分隔”的情况。
- Let grid handle only clearly suspicious red gaps without loosening PASS/REVIEW.
- 只让 grid 处理明确可疑的红色 gap，同时不放宽 PASS/REVIEW。

Implementation idea / 实现思路：

- Run a lightweight validation layer after `edge_refine` and before robust grid.
- 在 `edge_refine` 之后、robust grid 之前运行一个轻量校验层。
- Reuse cached content evidence and edge-refine profiles.
- 复用已经缓存的 content evidence 和 edge-refine profiles。
- For each accepted hard gap, inspect small local windows around the gap: gap content, left/right content, content continuity, background/separator profile, and edge/activity profile.
- 对每个已接受的 hard gap，检查 gap 附近的小窗口：gap content、左右 content、content continuity、background/separator profile、edge/activity profile。
- Label hard gaps as strong or suspect.
- 给 hard gap 标记 strong 或 suspect。
- Demote only very narrow, content-continuous, internal-edge-like hard gaps to model gaps.
- 只把非常窄、内容连续、像内部边缘的 hard gap 降级为 model gap。

Why it was paused / 为什么暂停：

- Although it helped explain at least one false hard separator pattern, the active V3.5 behavior made some previously accurate scans worse.
- 它确实解释了至少一种红框误判模式，但 active V3.5 让一些原本准确的扫描变差。
- The user observed regressions on important known-good scans, so this logic was removed from the active script.
- 用户在重要的已知准确样本上观察到回退，因此这套逻辑从 active 脚本移除。

Future notes / 后续注意：

- Do not reintroduce this as a broad rule.
- 不要把它作为宽泛规则直接加回来。
- If revisited, start as report-only diagnostics before it can change gap methods.
- 如果之后重启，先做成只写报告的诊断层，不要立刻改变 gap method。
- It needs stronger safeguards for known-good scans and perhaps a per-gap confidence label that does not immediately alter geometry.
- 它需要更强的已知准确样本保护，也可以考虑先加不直接改变几何的 per-gap confidence label。

## V3.4.2: Local Grid Segment Experiment / V3.4.2：局部 Grid 分段实验

Status / 状态：paused / rolled back from active script；已暂停 / 已从 active 脚本回滚。

Goal / 目标：

- Improve behavior on irregular spacing, near-overlap, or partly unstable strip geometry.
- 改善片距不稳定、近似叠片、局部几何不稳定的情况。
- Let grid remain useful without letting global equal spacing overwrite good red hard separators.
- 让 grid 仍然有用，但不让全局等距模型覆盖正确的红色 hard separator。

Implementation idea / 实现思路：

- Use strong hard separators as local anchors.
- 用强 hard separator 作为局部锚点。
- Reposition only model-only gaps (`grid` / `equal`) between or near those anchors using a local pitch.
- 只用局部 pitch 调整锚点之间或附近的 model-only gaps（`grid` / `equal`）。
- Do not move hard separators.
- 不移动 hard separator。
- Do not increase confidence merely because local grid adjusted a model gap.
- 不因为 local grid 调整了 model gap 就提高置信度。
- Record details in `local_grid`.
- 在 `local_grid` 中记录细节。

Why it was paused / 为什么暂停：

- It still changed geometry on scans that were previously accurate.
- 它仍然改变了一些原本准确样本的几何结果。
- Local grid can be useful, but it needs stricter proof that the target model gap is genuinely wrong before it changes geometry.
- local grid 可能有价值，但在改变几何前必须更严格证明目标 model gap 的确是错的。

Future notes / 后续注意：

- If revived, keep it limited to diagnostics first.
- 如果以后重启，先限制为诊断用途。
- Consider drawing local-grid suggestions in Debug Analysis without using them for output boxes.
- 可以先在 Debug Analysis 里画出 local-grid 建议，但不用于输出框。
- Require stronger evidence that local spacing is actually irregular and that the adjusted position aligns with visual separators.
- 必须有更强证据证明局部片距确实不规则，并且调整位置真的贴近可见分隔。

## V3.4.1: Preserve Strong Hard Gaps / V3.4.1：保留强 Hard Gap

Status / 状态：current active development version；当前 active 开发版。

Goal / 目标：

- Fix cases where robust grid overwrote an accurate red hard separator.
- 修复 robust grid 覆盖准确红色 hard separator 的情况。
- Make red hard evidence authoritative when it is strong and plausible.
- 当红色 hard evidence 足够强且合理时，让它具有更高权重。

Main changes / 主要变化：

- Strong `detected` / `edge-pair` gaps are preserved even if robust grid predicts a different center.
- 即使 robust grid 预测了不同中心，强 `detected` / `edge-pair` gap 也会被保留。
- Grid can still fill missing or weak model gaps.
- grid 仍然可以补全缺失或较弱的 model gap。
- Grid/hard conflicts are recorded in `grid.hard_conflicts`.
- grid/hard 冲突会记录在 `grid.hard_conflicts`。
- If full geometry is already accepted, the same evidence is not double-counted as `unstable_frame_width`.
- 如果完整几何已经被接受，同一组证据不会再被重复算作 `unstable_frame_width`。

Why it matters / 为什么重要：

- The separator evidence panel becomes easier to interpret because a correct red hard separator remains red.
- Separator evidence 面板更容易读，因为正确的红色 hard separator 会保持红色。
- Grid is treated as model support, not as a stronger source than real separator evidence.
- grid 被视为模型辅助，而不是比真实分隔证据更强的来源。

## V3.4: Detection Simplification / V3.4：检测简化

Status / 状态：development baseline retained by V3.4.1；V3.4.1 保留的开发基线。

Goal / 目标：

- Remove low-value or confusing detection layers.
- 移除收益低或容易造成误解的检测层。
- Make Debug Analysis easier to read.
- 让 Debug Analysis 更易读。
- Reduce maintenance cost and duplicated logic.
- 降低维护成本和重复逻辑。

Main changes / 主要变化：

- Removed the enhanced separator layer from active separator detection.
- 从 active separator detection 中移除 enhanced separator 层。
- `--analysis` no longer drives enhanced separator acceptance; it remains relevant to analysis/deskew behavior.
- `--analysis` 不再驱动 enhanced separator 接受逻辑；它仍与 analysis / deskew 行为相关。
- Removed `enhanced-detected` from active gap methods and README color semantics.
- 从 active gap methods 和 README 颜色说明中移除 `enhanced-detected`。
- Folded `equal-broad-region` into ordinary `equal`.
- 将 `equal-broad-region` 合并进普通 `equal`。
- Full-strip detection no longer creates a separate content candidate when the separator/geometric candidate is already the main path; content is validation.
- full-strip 检测在 separator/geometric candidate 已经是主路径时，不再创建单独 content candidate；content 只作为校验。
- The fallback path remains small and conservative.
- fallback 路径保持很小且保守。

Effect / 影响：

- Debug evidence uses fewer overlapping colors and concepts.
- Debug evidence 中重叠颜色和概念更少。
- Full-strip logic is easier to maintain.
- full-strip 逻辑更容易维护。
- Fewer old-chain decisions compete with the active V2 candidate scoring path.
- 更少旧链路决策会与 active V2 candidate scoring path 竞争。

## V3.3.2: Conservative Overlap-Aware Gap Handling / V3.3.2：保守的叠片感知 Gap 处理

Status / 状态：development, not active after rollback except as historical reference；开发版，回滚后仅作为历史参考。

Goal / 目标：

- Improve near-overlap or continuous-content cases without making them pass more easily.
- 改善近似叠片或连续内容情况，但不让它们更容易通过。

Main changes / 主要变化：

- Model gaps that look overlap-like can be marked `overlap_like=true`.
- 看起来像叠片的 model gap 可以标记为 `overlap_like=true`。
- Overlap-like gaps are not used as strong same-frame-size anchors.
- overlap-like gap 不会被当作强 same-frame-size anchor。
- This is intended to reduce geometry correction based on suspect model gaps.
- 这样做是为了减少基于可疑 model gap 的几何修正。

Important principle / 重要原则：

- Overlap handling should explain or restrain geometry correction. It should not increase confidence or push difficult scans into auto-pass.
- 叠片处理应该用于解释或约束几何修正，不应该提高置信度，也不应该把困难图推成自动通过。

## V3.3.1: Stable Release / V3.3.1：稳定发布版

Status / 状态：stable GitHub Release；GitHub 稳定发布版。

Release asset / 发布包：

- `X5-Crop-v3.3.1.zip`

Main behavior / 主要行为：

- Keeps the stable V3/V3.2 ordinary outer / gap / candidate chain.
- 保留稳定的 V3/V3.2 普通 outer / gap / candidate 链路。
- Keeps output-only bleed separation.
- 保留只在输出阶段生效的 bleed 分离。
- Preserves conservative PASS/REVIEW behavior.
- 保留保守的 PASS/REVIEW 行为。
- Includes bilingual README, launchers, install scripts, archive snapshots, and MIT License.
- 包含双语 README、启动器、安装脚本、archive 快照和 MIT License。
- GitHub Release notes include bilingual quick start and changes since `v3`.
- GitHub Release note 包含双语快速使用和相对 `v3` 的变化。

Why it is stable / 为什么它是稳定版：

- It was packaged as the user-facing release before later development experiments.
- 它是在后续开发实验前打包的用户发布版。
- It favors conservative known-good behavior over newer unproven detection ideas.
- 它优先选择已知稳定的保守行为，而不是较新的未充分验证检测想法。

## V3.3: Output-Only Bleed Separation / V3.3：只在输出阶段应用 Bleed

Status / 状态：development ancestor of stable release behavior；稳定发布行为的开发祖先版本。

Goal / 目标：

- Prevent bleed from changing detection decisions.
- 防止 bleed 改变检测决策。

Main changes / 主要变化：

- Detection uses no bleed internally.
- 检测内部不使用 bleed。
- Output/report/Debug Analysis frame boxes apply output bleed afterward.
- 输出、报告、Debug Analysis frame box 在之后再应用输出 bleed。
- Default output bleed is long axis 20px and short axis 10px.
- 默认输出 bleed 是长轴 20px、短轴 10px。
- Horizontal strips use left/right as long-axis bleed; vertical strips rotate the interpretation accordingly.
- 横向长图时左右是长轴 bleed；纵向长图时按方向对应旋转解释。

Why it matters / 为什么重要：

- Increasing output safety margin no longer changes outer boxes, gap selection, confidence, or PASS/REVIEW.
- 增加输出安全边距不会再改变 outer box、gap selection、confidence 或 PASS/REVIEW。

## V3.2: Return To V3 Detection Chain / V3.2：回到 V3 检测链路

Status / 状态：development；开发版。

Goal / 目标：

- Restore the more reliable V3-style behavior after V3.1.x experiments caused regressions.
- 在 V3.1.x 实验造成回退后，恢复更可靠的 V3 风格行为。

Main changes / 主要变化：

- Removed aggressive content-aligned outer expansion from the active chain.
- 从 active 链路移除激进 content-aligned outer 外扩。
- Removed separator-derived outer competition from the active chain.
- 从 active 链路移除 separator-derived outer 竞争。
- Removed local separator rescue from the active chain.
- 从 active 链路移除 local separator rescue。
- Kept the special REVIEW guard for the known leading-grid failure shape.
- 保留针对 leading-grid failure shape 的特殊 REVIEW 安全闸门。

Important principle / 重要原则：

- Rollback restored the ordinary detection route while keeping safety gates that prevent obvious guesses from passing.
- 回滚恢复普通检测路线，同时保留防止明显猜测通过的安全闸门。

## V3.1.x: Aggressive Correction Experiments / V3.1.x：激进修正实验

Status / 状态：experimental, not active；实验版，非 active。

Ideas tested / 测试过的想法：

- More aggressive content-aligned outer correction.
- 更激进的 content-aligned outer 修正。
- Separator-derived outer boxes when ordinary outer detection was weak or missing.
- 当普通 outer detection 较弱或缺失时，用 separator-derived outer box 竞争。
- Local separator rescue near predicted grid positions.
- 在预测 grid 位置附近做 local separator rescue。
- Extra same-frame-size fitting triggered by newly rescued gap evidence.
- 新救回的 gap 证据触发额外 same-frame-size fitting。

Why not kept / 为什么没有保留：

- These ideas sometimes helped edge cases but also changed good scans too much.
- 这些想法有时能帮助边缘情况，但也会过度改变原本准确的样本。
- They increased the risk that difficult images would appear high-confidence for the wrong reason.
- 它们增加了困难图因为错误原因看起来高置信的风险。
- The project priority remains conservative auto-cropping: only high-confidence detections should auto-crop.
- 项目的优先级仍然是保守自动裁切：只有高置信检测才应该自动裁切。

Lessons / 经验：

- Rescue logic should be diagnostic or review-only until it proves it does not harm known-good scans.
- rescue 逻辑在证明不会伤害已知准确样本前，应该先作为诊断或 review-only。
- Output safety margin is better handled as output-only bleed, not detection geometry.
- 输出安全边距更适合用 output-only bleed 处理，而不是改变检测几何。
- Debug visuals must clearly distinguish evidence from model guesses.
- Debug 可视化必须清楚区分真实证据和模型推测。

## V3.0: Baseline X5 Crop / V3.0：X5 Crop 基线

Status / 状态：baseline archived snapshot；基线 archive 快照。

Main capabilities / 主要能力：

- Standalone `X5_Crop.py` workflow.
- 独立 `X5_Crop.py` 工作流。
- Format-aware cropping for 135, half-frame, XPAN, 645, 66, 67, and 135 dual.
- 支持 135、半格、XPAN、645、66、67、135 dual 等 format-aware 裁切。
- Conservative PASS/REVIEW separation.
- 保守的 PASS/REVIEW 分离。
- Debug Analysis JPG output.
- Debug Analysis JPG 输出。
- TIFF quality and metadata preservation policy.
- TIFF 画质与 metadata 保持策略。
- macOS and Windows launchers.
- macOS 和 Windows 启动器。

## Development Testing Notes / 开发测试说明

Default testing rule / 默认测试规则：

- For detection logic changes, future development tests should use `--deskew off` unless the change specifically touches deskew.
- 对检测逻辑变化，之后开发测试默认使用 `--deskew off`，除非改动本身涉及 deskew。
- This keeps regression checks faster and focuses them on detection geometry.
- 这样可以让回归检查更快，并且聚焦检测几何本身。

Suggested focus set after detection changes / 检测变化后的建议重点样本：

- `X5_00007`
- `X5_00022`
- `X5_00032`
- `X5_00036`
- `X5_00038`
- `X5_00044`
- `X5_00051`
- `X5_00052`

Core regression rule / 核心回归规则：

- Do not improve one difficult case by damaging known-good cases.
- 不要为了改善一个困难样本而破坏已知准确样本。
- Do not let fallback, rescue, grid, or semantic validation logic make weak-evidence images auto-pass.
- 不要让 fallback、rescue、grid 或 semantic validation 逻辑把弱证据图推成自动通过。
- If a new idea changes geometry on known-good scans, first make it report-only or review-only before letting it affect output boxes.
- 如果新思路会改变已知准确样本的几何结果，先做成 report-only 或 review-only，再考虑影响输出框。

Release policy / 发布策略：

- GitHub Releases are the stable user-facing downloads.
- GitHub Release 是面向用户的稳定下载。
- The repository `main` branch may contain active development, experiments, or rollback work.
- 仓库 `main` 分支可能包含 active 开发、实验或回滚工作。
- When a development version becomes stable enough for users, create a new GitHub Release and update `README.md`, `CHANGELOG.md`, and `AGENTS.md` together.
- 当某个开发版本足够稳定适合用户使用时，创建新的 GitHub Release，并同步更新 `README.md`、`CHANGELOG.md`、`AGENTS.md`。
