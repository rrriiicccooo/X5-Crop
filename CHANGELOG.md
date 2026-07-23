# X5 Crop 更新日志 / Changelog

本文件只记录版本级行为、验证范围和回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`README.md`，跨会话任务状态见 `PROJECT_MEMORY.md`。

This file records version-level behavior, validation scope, and rollback context
only. See `ARCHITECTURE.md` for the current design, `README.md` for user guidance,
and `PROJECT_MEMORY.md` for the rolling task checkpoint.

当前开发版本 / Active development: **V4.9**
当前稳定发布 / Stable release: **v4.2.8**

## V4.9 当前开发线 / Current Development Line

V4.9 是破坏性、current-only 的物理模型与源码重构。历史 PASS/REVIEW、报告字段和裁切几何不是
兼容目标；真实 TIFF、当前报告、Debug Analysis 与当前合同才是验证依据。

V4.9 is a breaking, current-only physical-model and source rewrite. Historical
PASS/REVIEW outcomes, report fields, and crop geometry are not compatibility
targets; real TIFFs, current reports, Debug Analysis, and current contracts are
the validation evidence.

### 2026-07-23 — 片夹物理画布与照片边缘证据 / Physical Canvas And Photo-Edge Evidence

- Added the sole `ScanCanvasPhysicalSpec` catalog for `135_standard`
  (32.22 × 232 mm), `135_narrow` (25.4 × 232 mm), `120_standard`
  (60 × 226 mm), `120_wide` (63.44 × 224.5 mm), and
  `120_66_three_frame` (63.44 × 188.5 mm). A format-compatible profile is
  selected from source pixel aspect with a 0.5% limit, then becomes the sole
  `CanvasPixelScale`; no TIFF DPI interpretation or final-geometry scale
  inference remains. / 新增唯一 `ScanCanvasPhysicalSpec` 目录，按 format 兼容集合与原图
  像素长短比在 0.5% 限制内唯一匹配片夹画布，再生成唯一 `CanvasPixelScale`；TIFF DPI
  不再被解释，也不再从最终几何反推尺度。
- `FramePhysicalSpec` now keeps photo facts separate from holder-scan facts.
  120-645, 120-66, and 120-67 retain discrete 54 mm / 56 mm short-axis options;
  no 55 mm average is generated. The sole centered-band formula is
  `(canvas_short_mm - photo_short_mm) / 2`, and theory constrains search but
  never creates supported evidence. / 照片事实与片夹画布事实由不同 owner 保存；120 的
  54/56 mm 是离散选项，不生成 55 mm 平均值。理论居中公式只约束搜索，不能生成
  supported 证据；没有 selected pair 绑定时，frame solver 不选择默认 54/56。
- Single-strip observation is now pair-first: each cross-section forms a
  physically allowed top/bottom point pair before joint tracking. Equivalent
  confidence tracks are merged deterministically; candidates retain at least
  three sections, while supported pairs require five robust inliers per edge,
  80% inliers, three supported local windows distributed across at least two of
  three bins, role-specific photo-side structure on top/bottom inner sides,
  compatible 95% slope intervals, and full physical-band containment. Holder
  coincidence is neutral, scan extrema cannot self-prove, and a strong outer
  holder transition without photo-side structure remains unavailable.
  / 单条片夹先在每个截面形成物理允许的上下点对，再共同连接与确定性合并；pair 的局部
  支持、稳健拟合、斜率和 95% 物理约束分别验证。holder 重合保持 neutral，扫描外沿不能
  自证。
- Removed the entire observed-leverage concept, including configuration,
  calculation, report, comparison, and tests; no coverage ratio, photo-height
  multiple, renamed substitute, generic short-axis boundary dependency, TIFF
  resolution-evidence chain, or `FrameScaleObservation` remains. Observation
  extent survives only as raw intervals, sample distribution, and fit
  confidence. / 完整删除 observed leverage 及所有改名替代，也删除 photo-edge 对通用
  boundary measurement 的依赖、TIFF resolution 证据链和重复 frame scale；观测范围只以
  原始区间、样本分布和拟合置信带存在。
- `PhotoEdgePairEvidence` is the sole edge-identity truth. Transform,
  `SharedShortAxisPlan`, and frame-dimension validation consume it independently:
  source edge identity may be supported while angle estimation or strip-wide
  extrapolation remains unavailable. Affine correction maps the same evidence
  and never re-observes a short axis. `DecisionGate` now always consumes the
  actual canvas and transform states, even before count resolution. /
  `PhotoEdgePairEvidence` 是唯一边缘身份真相；校斜、共享短轴和照片尺寸分别消费。同一
  source pair 可以已成立而角度或整幅外推仍 unavailable；仿射后只映射不复测，
  `DecisionGate` 始终消费真实 canvas/transform state。
- `135-dual` remains `not_applicable` to fixed-canvas calibration. It resolves a
  source divider and observes each lane from image evidence; only two unique
  pairs with compatible angle intervals can produce one global correction. /
  `135-dual` 不虚构统一物理画布，先解 source divider，再由两条 lane 的图像证据进入同一
  pair 与消费模型。
- The current-only report revision is `scan_canvas_photo_edge_evidence`. It
  records canvas matching, effective px/mm, theoretical bands, retained
  candidates plus typed summaries, source/mapped pair evidence, affine mapping,
  shared-axis outcomes, and frame-size binding. Raw local section turns,
  legacy deskew fields, resolution judgments, and duplicate scale fields are not
  serialized. Debug Analysis now shows source physical evidence, mapped/shared
  geometry, and long-axis evidence in three read-only panels. / 当前 report
  revision 为 `scan_canvas_photo_edge_evidence`；不序列化局部 section 转折、旧 deskew、
  DPI 判断或重复尺度字段。Debug 三联图只读显示 source、mapped/shared 和长轴证据。
- Manual review remains paused. Existing candidate confirmations and rejections
  are read-only regression seeds; runtime reads no whitelist, writes no new
  human label, and never describes a machine-supported pair as human-confirmed.
  / 人工审阅继续暂停；现有确认与否定只作只读回归种子，runtime 不读白名单、不写新标签，
  也不把机器 supported 描述成人工确认。
- Validation covers 832 contract/unit tests and all 14 format/mode
  configurations. A fresh default-flow run produced 112 valid current-schema
  reports and 112 readable Debug Analysis images: 69 `135_standard`, 8
  `135_narrow`, 3 `120_standard`, and 32 `120_wide`; all 112 remain REVIEW.
  All nine user-confirmed edge pairs are retained in one physically compatible
  hypothesis, while no supported hypothesis overlaps the 41 scan-extrema or
  S054/S061 empty-region rejection coordinates. Two independent S010 runs
  compare with zero current-schema differences. These checks consume existing
  labels only and create no new human confirmation. / 验证覆盖 832 项合同/单元测试与
  14 组 format/mode 配置；全新默认流程生成 112 份有效 current-schema report 和
  112 张可读 Debug Analysis，profile 计数为 69/8/3/32，全部保持 REVIEW。九组已有
  人工确认的上下边缘均保留在同一物理兼容 hypothesis 中，任何 supported hypothesis
  均不与 41 组扫描外沿及 S054/S061 空白区否定坐标重合；S010 两次独立运行的
  current-schema 差异为零。这些检查只消费既有标签，不产生新人工确认。
- Rollback must restore the complete physical catalog, detection model,
  workspace, report schema, contracts, and documentation as one unit. Mixing
  TIFF-DPI scale, generic short-axis paths, optional deskew, or an older report
  model into this flow is unsupported. / 回滚必须整体恢复物理目录、检测模型、workspace、
  report schema、合同与文档；不得混入 TIFF-DPI 尺度、通用短轴路径、可关闭 deskew 或旧
  report 模型。

### 2026-07-22 — 已被物理画布模型取代的共享短轴阶段 / Superseded Shared-Axis Stage

- Deskew is now the mandatory first stage of detection. Detection measures two
  real source-photo inner edges once, creates the sole `SharedShortAxisPlan`,
  derives the transform from those same edges, and maps that plan into the
  `DetectionWorkspace`; downstream frame solving never searches for another
  short axis. `image` owns only the generic pixel transform, `geometry` owns
  `AffineCoordinateTransform`, and runtime owns only orchestration and I/O. /
  Deskew 现已收归 detection 的强制第一阶段：只在原图测量一次真实照片双内缘，建立唯一
  `SharedShortAxisPlan`，由同一证据决定 transform，并将同一计划映射进
  `DetectionWorkspace`；后续 frame solver 不再搜索短轴。`image` 只拥有通用像素变换，
  `geometry` 拥有 `AffineCoordinateTransform`，runtime 只编排与执行 I/O。
- The only supported transform outcomes are `identity_within_tolerance` and
  `deskew_applied`. Missing, single, holder, scan-extrema, low-support,
  high-residual, slope-conflicting, and out-of-range evidence blocks automatic
  PASS through `DecisionGate`. Dual-lane correction requires one source divider,
  two resolved photo-edge pairs, and one consistent global angle. / 只有
  `identity_within_tolerance` 与 `deskew_applied` 支持 transform；缺边、单边、holder、扫描
  外沿、覆盖不足、残差过高、斜率冲突或超角度都由 `DecisionGate` 阻止自动 PASS。Dual lane
  必须先有唯一 source divider、两组真实双边缘和一致的全局角度。
- Photo-edge qualification now requires a scale-adaptive tonal span and a
  per-cross-section gap from holder transitions. Scores select only among
  overlapping observations of one physical edge pair; they cannot choose between
  distinct pair hypotheses. This specifically prevents scan-footprint extrema and
  weak holder-adjacent transitions from becoming resolved crop geometry. / 照片
  边缘资格现要求相对灰度动态范围足够的强度跨度，并在每个共同截面与 holder transition
  保持尺度化间隔；评分只能在同一物理边缘对的重叠观测中选代表，不能替互斥边缘假设裁决，
  从而阻止扫描外沿和 holder 邻近弱 transition 成为 resolved 裁切几何。
- A strip-wide shared crop is auto-safe only when both photo edges share support
  across the complete long-axis crop domain. Partial edge support remains visible
  as REVIEW evidence but is not linearly extrapolated into crop geometry. This
  closes the content-cut risk found by affine comparison of the previously
  60%–67%-supported S015, S023, and S099 candidates. / 只有上下照片边缘共同覆盖完整长轴
  裁切域时，整条共享短轴才可自动安全；局部覆盖仍作为 REVIEW 证据显示，但不得线性外推为
  裁切几何。该合同关闭了仿射人工基线审计在原 60%–67% 覆盖的 S015、S023、S099 上发现的
  内容切入风险。
- Removed `--deskew`, `--deskew-fallback`, `--deskew-min-angle`, and
  `--deskew-max-angle` from CLI, interactive/runtime configuration, cache
  identity, reports, and comparison tools. The current-only report revision is
  `detection_owned_shared_short_axis`, with source observations, the single
  transform outcome/map, physically named edge-drift measurements, and mapped
  plans; old `measurement_outcome`, `span_px`, and `span_threshold_px` fields
  have no shim. /
  CLI、交互/runtime 配置、cache identity、报告和比较工具已删除上述四个 deskew 参数；当前
  report revision 为 `detection_owned_shared_short_axis`，记录物理命名的边缘投影漂移；旧
  `measurement_outcome`、`span_px` 与 `span_threshold_px` 字段不提供兼容层。
- The local 112-scenario review baseline records 41
  `scan_footprint_extrema_not_photo_edges` and 2 `empty_region_offset`
  rejections, withdraws the old S054/S109/S111 assistant support, and resets all
  new candidates to pending. Historical 4 user-confirmed and 13
  assistant-reviewed records remain audit history only; `manual_baseline.jsonl`
  remains the sole manual crop authority. / 本地 112 场景基线记录 41 条扫描外沿否定与 S054、
  S061 两条空白区偏移否定，撤回 S054/S109/S111 的旧 assistant 支持，并将新模型 112 条候选
  全部重置为 pending；旧 4 条 user-confirmed 与 13 条 assistant-reviewed 仅作历史审计，
  `manual_baseline.jsonl` 仍是唯一人工裁切权威。
- Validation covers 820 contract/unit tests and all 14 format/mode
  configurations. A fresh default-flow run produced 112 valid current-schema
  reports and 112 Debug Analysis images: all 112 remain non-exportable REVIEW,
  with transform outcomes 103 `photo_edges_unavailable`, 8
  `insufficient_common_support`, and 1 `edge_fit_high_residual`. Affine comparison
  against `manual_baseline.jsonl` found zero resolved content-cut risks. All 112
  new short-axis review candidates remain pending, and two consecutive read-only
  architecture audits passed the same frozen ownership/residue checklist. /
  验证覆盖 820 项合同/单元测试与全部 14 组 format/mode 配置。全新默认流程生成 112 份有效
  current-schema report 与 112 张 Debug Analysis：112 组全部保持不可导出的 REVIEW；transform
  outcome 为 103 个 `photo_edges_unavailable`、8 个 `insufficient_common_support` 与 1 个
  `edge_fit_high_residual`。与 `manual_baseline.jsonl` 的仿射对照未发现任何已解析内容切入
  风险；112 个新短轴审阅候选全部保持 pending，同一冻结所有权/残留清单的两轮连续只读
  架构审计均通过。
- Rollback must restore the complete pre-change source, CLI, and report schema as
  one unit. Mixing old optional deskew or scan/holder-derived spans with the new
  detection workspace is unsupported because it restores evidence already
  rejected by physical review. / 回滚只能整体恢复变更前源码、CLI 与 report schema；不得把旧的
  可关闭 deskew 或 scan/holder 短轴混入新 workspace，因为那会恢复已被人工物理审阅否定的证据。

### 2026-07-21 — Real-sample label reset 与 baseline 清理 / Real-Sample Label Reset And Baseline Cleanup

- The local real-sample baseline now contains 112 TIFFs: 88 `pass` samples are
  `pass_required`, and all 24 `unknown` samples are `pass_preferred`; there are
  no `review_required` samples. `135/full/unknown_X5_00038` is now
  `unknown_X5_00011`, `135/partial/review_X5_00002` is now
  `unknown_X5_00009`, and the `67/partial` sample set was removed. / 当前本地真实
  样片基线为 112 张：88 张 `pass` 为 `pass_required`，24 张 `unknown` 全部为
  `pass_preferred`，不再有 `review_required`；`135/full/unknown_X5_00038` 已改名为
  `unknown_X5_00011`，`135/partial/review_X5_00002` 已改名为 `unknown_X5_00009`，
  `67/partial` 样片集已删除。
- `pass_preferred` may omit a manual geometry reference when an `unknown` sample
  is allowed to remain REVIEW; if a reference is present, it must belong to the
  same source. A reference-free unknown must never be treated as physically
  verified merely because it auto-passes. / 当 unknown 样片允许保持 REVIEW 时，
  `pass_preferred` 可以没有人工 geometry reference；若有 reference，必须属于同一 source。
  没有 reference 的 unknown 不能仅因 auto-pass 就被视为物理上已验证。
- The obsolete `Test/test 1`, `Test/test 2`, and the generated
  `Test/135/full/x5_crop_output` were removed to prepare a new baseline. / 为重新建立
  基线，旧的 `Test/test 1`、`Test/test 2` 与生成的 `Test/135/full/x5_crop_output` 已删除。

### 2026-07-20 — Holder 与内容反证闭环 / Holder And Content Refutation Closure

- Assignment-consensus input now lets a near-complete independent separator
  sequence own a full-strip mapping only when the shared short axis is bounded
  by measured photo edges, at most one internal separator is missing, and the
  bindings cover a strict majority of internal boundaries. Binding topology is
  keyed by boundary and observation identity rather than tuple order. Holder-bounded,
  partial, and one-of-two separator cases retain every physical topology.
  Focused diagnostics promote `135/full/pass_X5_00001` and `00003` to
  reference-matched automatic PASS while `00006`, `unknown_X5_00038`,
  `half/full/pass_X5_00007`, `120-67/full/pass_X5_00002`, and holder-bounded
  `135/full/pass_X5_00010` remain non-exportable REVIEW. / Assignment-consensus
  input 现在只在 full strip 的共享短轴由实测 photo edges 双侧界定、内部 separator 最多缺一且
  bindings 覆盖严格多数内部边界时，才允许近完整独立 separator 序列拥有 mapping 权限；binding
  topology 由 boundary 与 observation identity 标识，不受 tuple 顺序影响；
  holder-bounded、partial 与二选一 separator 情形继续保留全部物理 topology。具名 diagnostics
  将 `135/full/pass_X5_00001` 与 `00003` 提升为符合人工 reference 的自动 PASS，同时 `00006`、
  `unknown_X5_00038`、`half/full/pass_X5_00007`、`120-67/full/pass_X5_00002` 与 holder-bounded
  `135/full/pass_X5_00010` 继续保持不可导出的 REVIEW。
  The full verifier passes 816 tests and
  14 format/mode configuration pairs. / 完整 verifier 通过 816 项测试与 14 组 format/mode 配置。
- Measured-frame graph search now materializes immutable ordered-option coordinates, width bounds,
  content coverage, separator identities, observation counts, and boundary uncertainty once per
  search. Graph feasibility and best-path layers index those exact facts instead of repeatedly
  translating the same typed options into NumPy arrays; no candidate, witness, Gate, decision,
  result, or budget state is cached. On isolated `78c6d450` versus the candidate, the fixed
  auto-count `half/partial/pass_X5_00001` detection changed from 35.10 s to 34.00/34.37 s, while
  cProfile calls fell from 277.60 M to 255.52 M and profiler time from 77.26 s to 73.34 s.
  All 963,127 assignment evaluations, 11 assessed candidates, cache 52/7, the current report, and
  the byte-identical Debug Analysis remain unchanged. / Measured-frame graph search 现在于每次
  search 只物化一次 ordered option 的不可变坐标、宽度边界、content coverage、separator
  identity、observation count 与 boundary uncertainty；graph feasibility 与 best-path layer
  只索引这些精确事实，不再重复把同一 typed option 翻译成 NumPy 数组，且不缓存 candidate、
  witness、Gate、decision、result 或 budget state。隔离的 `78c6d450` 基线与候选对比中，固定
  auto-count `half/partial/pass_X5_00001` detection 从 35.10 s 降至 34.00/34.37 s；cProfile
  调用从 277.60 M 降至 255.52 M，profiler 时间从 77.26 s 降至 73.34 s。963,127 次
  assignment evaluation、11 个 assessed candidate、cache 52/7、current report 与字节一致的
  Debug Analysis 均保持不变。
  The full verifier passes 813 tests and 14 format/mode configuration pairs. / 完整 verifier
  通过 813 项测试与 14 组 format/mode 配置。
- Full-workspace reliable content now refutes only a long-axis holder boundary it physically
  crosses before the sequence search scope is built. `FrameCoverageEvidence` also merges the
  exact cached workspace and holder-local content runs, so a false holder clip cannot hide an
  omitted photo from preservation evidence. Content still cannot prove a holder, count, frame
  edge, or automatic decision. / 完整 workspace 的 reliable content 现在只在实际穿过长轴
  holder boundary 时，于 sequence search scope 建立前否定该边界；`FrameCoverageEvidence`
  同时合并 exact-cache 的 workspace 与 holder-local content runs，使错误 holder clipping
  不能再把遗漏照片藏到 preservation evidence 之外。Content 仍不能证明 holder、count、
  frame edge 或自动 decision。
- A geometry-corroborated observation wider than the interval allowed by an independent common
  width and the opposite anchor is now resolved as their dimension-constrained intersection.
  Direct and measurement-corroborated boundaries remain measured facts. This closes the broad
  endpoint that previously let `120-66/partial` 00014 remain resolved-wrong. / 当
  geometry-corroborated 观测区间宽于独立 common width 与对侧 anchor 允许的区间时，最终位置
  现在改为两者的 dimension-constrained 交集；direct 与 measurement-corroborated 边界仍保持
  实测事实。该规则关闭了此前使 `120-66/partial` 00014 保持 resolved-wrong 的宽端点。
- Three frozen-HEAD contracts reproduced all three failures before the fix. Current verification
  passes 803 tests and 14 configuration pairs. A fresh 113-TIFF diagnostics run completed with
  zero runtime/schema failures; after source-pixel correction of three overly narrow manual
  intervals, authority validation reports 51 conforming samples, 62 capability gaps, zero
  evidence-contract conflicts, and zero physical violations. `unknown_X5_00038.tif` remains
  `REVIEW`, geometry unavailable, and non-exportable. / 冻结 HEAD 上的三项合同在修复前均稳定
  失败；当前 803 项测试与 14 组配置通过。全新 113 张 TIFF diagnostics 无 runtime/schema
  failure；依据原图像素修正三条过窄人工区间后，authority validator 为 51 conforming、
  62 capability gap、0 evidence-contract conflict、0 physical violation。
  `unknown_X5_00038.tif` 保持 `REVIEW`、geometry unavailable、不可导出。

### 2026-07-19 — 无环观测权限 / Acyclic Observation Authority

- Lexicographic graph ranking now carries the exact still-ambiguous row indexes from one
  criterion to the next instead of reducing the full boolean matrix twice per criterion. A
  permanent contract reproduced 38 ambiguity reductions for 19 rank criteria and now allows
  only one per criterion plus one initialization per graph transition. On the complete fixed
  `half/partial/pass_X5_00001` count-11 search, detection fell from 66.34 s to 63.02 s while
  preserving 750,766 total assignment evaluations, selection, Decision, non-exportable output,
  and a byte-identical Debug Analysis JPG. The unchanged 100,000-budget run remains typed
  budget-exhausted at 101,127 evaluations; this wave improves exact work but does not treat
  budget as proof. All 813 tests and 14 configuration pairs pass. / Graph 字典序 ranking 现在把
  每轮仍并列的 row index 精确传给下一 criterion，不再为每个 criterion 对完整布尔矩阵做两次
  reduction。永久合同在旧实现复现 19 个 rank criterion 对应 38 次 ambiguity reduction，
  当前只允许每 criterion 一次，并在每个 graph transition 初始化一次。固定
  `half/partial/pass_X5_00001` count-11 完整搜索的 detection 从 66.34 s 降至 63.02 s，
  同时保持 750,766 次总 assignment evaluation、selection、Decision、不可导出 output 与
  字节一致的 Debug Analysis JPG。默认 100,000 budget 仍以 101,127 次 evaluation 保持
  typed budget exhaustion；本波次只减少精确计算，不把 budget 当作证明。813 项测试与
  14 组配置均通过。
- Boundary-path appearance now reuses exact local-window statistics within one
  `boundary_measurements` call, keyed by the typed axis-local section, scan direction, and
  complete start/end coordinates. No count, offset, candidate, Gate, or decision is cached. A
  synthetic holder contract exposed 12 duplicate physical windows and now finds zero. On the
  same fixed `120-66/partial/pass_X5_00011` count-3 cProfile, window measurements fell from
  2,920 to 2,782 and detection from 9.00 s to 8.90 s; assignment evaluations remain 106,989,
  the report has zero diff, and Debug Analysis is byte-identical. / Boundary-path appearance
  现在只在单次 `boundary_measurements` 内复用 exact local-window statistics，typed key
  包含 axis-local section、scan direction 与完整 start/end 坐标；不缓存 count、offset、
  candidate、Gate 或 decision。合成 holder 合同从 12 个重复物理窗口降为 0。固定
  `120-66/partial/pass_X5_00011` count-3 cProfile 中，window measurement 从 2,920 降至
  2,782，detection 从 9.00 s 降至 8.90 s；assignment evaluation 仍为 106,989，
  report 0 diff，Debug Analysis 字节一致。
- Transition and independent-separator-edge witnesses now share one cached
  best-prefix/best-suffix path index per feasible graph instead of rerunning a two-state graph
  search for every physical edge. A two-edge contract failed with nine predecessor traversals
  on the frozen implementation and now needs only the two traversals of the ordinary best path.
  On fixed `120-66/partial/pass_X5_00011`, count 3 and the unchanged 100,000 budget, comparable
  cProfile detection fell from 10.52 s to 9.00 s, graph-witness cumulative time from 2.58 s to
  0.96 s, and calls from 39.00 M to 33.66 M. Assignment evaluations remain 106,989; the report
  has zero diff and Debug Analysis is byte-identical. / Transition 与 independent separator
  edge witness 现在于每张可行 graph 内共用一套缓存的 best-prefix/best-suffix path index，
  不再为每条 physical edge 重跑 two-state graph search。双 edge 合同在冻结实现上需要 9 次
  predecessor traversal，现在只保留普通 best path 的 2 次。固定
  `120-66/partial/pass_X5_00011`、count 3、10 万预算的可比 cProfile 中，detection 从
  10.52 s 降至 9.00 s，graph witness 从 2.58 s 降至 0.96 s，调用量从 39.00 M 降至
  33.66 M；assignment evaluation 仍为 106,989，report 0 diff，Debug Analysis 字节一致。
- Exact frame-sequence search now deduplicates equal physical-aspect priors, reuses resolved
  boundary and role facts, prunes prefix-unreachable backward states and interval-incompatible
  path observations, stops lexicographic ranking once each row is unique, and computes each
  independent-edge witness with one seen/unseen dynamic path. Partial mode skips full-only
  completion work, while a complete two-sided separator seed preserves canonical physical
  ordering. On the frozen count-11 `half/partial/pass_X5_00001` command with the unchanged
  100,000 budget, detection fell from 9.04 s to 5.95 s and assignment evaluations from 102,974
  to 101,127; the current report has zero diff and Debug Analysis is byte-identical. All 811
  tests and 14 configuration pairs pass; no proof, Gate, or budget authority changed. / 精确
  frame-sequence search 现在对相同 physical aspect 去重，复用 resolved boundary 与 role
  facts，剪除 prefix-unreachable backward state 和区间不兼容 path observation，每行唯一后
  停止余下字典序 ranking，并以一条 seen/unseen 动态路径计算每个 independent-edge witness。
  Partial 模式跳过 full-only completion；存在完整双边 separator seed 时继续保留 canonical
  physical order。固定 count-11、10 万预算的 `half/partial/pass_X5_00001` detection 从
  9.04 s 降至 5.95 s，assignment evaluation 从 102,974 降至 101,127；report 0 diff，
  Debug Analysis 字节一致。811 项测试与 14 组配置通过，proof、Gate 与 budget 权限均未改变。
- Graph path predecessor ranking now evaluates each layer in bounded vectorized batches while
  retaining the exact physical-validity filters and lexicographic rank authority. The former
  per-option ranking API was deleted; no candidate, state, evaluation, or execution budget was
  changed. On the frozen `half/partial/pass_X5_00001` diagnostic, detection fell from 74.71 s to
  50.27 s while preserving 971,842 assignment evaluations, 11 candidates, cache 41/6, a
  zero-diff current report, and a byte-identical Debug Analysis JPG. / Graph path predecessor
  ranking 现在以有界 vectorized batch 处理每一层，同时完整保留原有 physical-validity filter
  与 lexicographic rank authority；旧的逐 option ranking API 已删除，candidate、state、
  evaluation 与 execution budget 均未改变。冻结 `half/partial/pass_X5_00001` diagnostics
  从 74.71 s 降至 50.27 s，同时保持 971,842 次 assignment evaluation、11 个 candidate、
  cache 41/6、current report 0 diff 与 Debug Analysis JPG 字节一致。
- Forward and backward graph reachability now materialize coordinate/fallback ordering once for
  each exact index subset within a single pass; no candidate, witness, edge result, or decision is
  cached. On the frozen `half/partial/pass_X5_00001` diagnostic, detection fell from 80.71 s to
  74.71 s while preserving 971,842 assignment evaluations, 11 candidates, cache 41/6, a zero-diff
  current report, and a byte-identical Debug Analysis JPG. / 前向与反向 graph reachability
  现在于单次 pass 内为每个完全相同的 index subset 只物化一次 coordinate/fallback
  顺序；不缓存 candidate、witness、edge result 或 decision。冻结
  `half/partial/pass_X5_00001` diagnostics 从 80.71 s 降至 74.71 s，同时保持
  971,842 次 assignment evaluation、11 个 candidate、cache 41/6、current report 0 diff
  与 Debug Analysis JPG 字节一致。
- Recurring-width branches without a supported internal separator seed now retain the
  frame-width-focused order prepared by construction; separator-backed searches keep the
  canonical contributor ranking. No hypothesis is deleted and budget exhaustion remains typed.
  On the frozen `half/partial/pass_X5_00001` diagnostic, detection fell from 129.16 s to
  80.71 s with 11 candidates and cache 41/6; the still-unresolved geometry became more
  conservative and remained `REVIEW` / non-exportable. / 没有 supported internal separator
  seed 的 recurring-width 分支现在保留 construction 已准备的 frame-width-focused 顺序；有
  separator 权限的搜索继续使用 canonical contributor ranking。该变化不删除 hypothesis，
  也不掩盖 typed budget exhaustion。冻结 `half/partial/pass_X5_00001` diagnostics 从
  129.16 s 降至 80.71 s，仍为 11 个 candidate、cache 41/6；未解决几何更保守，并保持
  `REVIEW`、不可导出。
- Graph reachability now materializes each count-local fallback order once per boundary
  instead of re-sorting the same eligible options for every current node. On the frozen
  `half/partial/pass_X5_00001` diagnostic, detection fell from 199.28 s to 129.16 s while
  preserving 933,677 assignment evaluations, 11 candidates, cache 41/6, a zero-diff current
  report, and a byte-identical Debug Analysis JPG. / Graph reachability 现在每个 boundary
  只物化一次 count-local fallback 顺序，不再为每个 current node 重排同一组 eligible options。
  冻结 `half/partial/pass_X5_00001` diagnostics 从 199.28 s 降至 129.16 s，同时保持
  933,677 次 assignment evaluation、11 个 candidate、cache 41/6、current report 0 diff 与
  Debug Analysis JPG 字节一致。
- Multi-slot geometry resolution now requires every ordinary slot width to intersect the
  supported common frame width, and holder-occlusion inference cannot resolve nominal
  boundaries outside the acquired workspace canvas. The 11 reference-violating automatic
  approvals found by the complete real-sample audit now remain typed, non-exportable
  `REVIEW` instead of reporting resolved-wrong geometry. / 多 slot geometry resolution
  现在要求每个普通 slot 宽度与 supported common frame width 相交；holder-occlusion inference
  也不能把已采集 workspace canvas 之外的 nominal boundary 判为 resolved。完整真实样片审计
  找到的 11 个 reference-violating 自动通过现在均保持 typed、不可导出的 `REVIEW`，不再报告
  resolved-wrong geometry。
- 共同 frame width 现在要求实测宽度具有非空共享区间；不相交宽度不能再被宽 uncertainty
  envelope 合并并获得 dimension-sequence proof。`135/partial/review_X5_00002` 因而从错误的
  自动通过恢复为不可导出的 `REVIEW`。 / Common frame width now requires a non-empty
  shared interval across measured widths; disjoint widths can no longer be merged by a
  broad uncertainty envelope and gain dimension-sequence proof. Consequently,
  `135/partial/review_X5_00002` returned from a false automatic approval to
  non-exportable `REVIEW`.
- Candidate resolution 现在先验证 proposed gray-path boundary 的正 slot extent，再构造
  `FrameSlot`；宽度跨过 0 的 band 不能成为 separator binding/assignment。Common-width 与
  candidate-local content-continuity/spacing identity 也纳入完整物理输入与测量权限，避免不同
  观测或 authority 共用同一 ID。越过 holder 的可见 slot 会在 solver 内成为 typed
  constraints failure，不再流入最终模型触发 runtime error。 /
  Candidate resolution now verifies positive slot extent before constructing a
  `FrameSlot`, and a band whose width crosses zero cannot become a separator binding or
  assignment. Common-width and candidate-local content-continuity/spacing identities also
  include their complete physical inputs and measurement authority so distinct observations
  or authorities cannot share one ID. Visible slots outside the holder now become a typed
  solver constraint failure instead of reaching the final model as a runtime error.
- 真实样片期望现在分别记录人工 geometry reference、允许灰度观测的独立 proof 预期与自动
  decision 预期；文件名前缀只拥有 dataset intent，不能再作为 decision oracle。 /
  Real-sample expectations now record manual geometry reference, independent-proof
  expectation for allowed grayscale observations, and automatic-decision expectation
  separately; filename prefixes own dataset intent only and are no longer decision oracles.
- 新的 real-sample validator 对齐仓库相对人工记录与 runtime 绝对 source，并把 current report
  判定为 conforming、capability gap、evidence-contract conflict 或 physical violation；
  unresolved export、resolved-wrong、review-required 自动通过和 runtime/schema failure 均不能
  被标签掩盖。 / A new real-sample validator aligns repository-relative manual records with
  absolute runtime sources and classifies each current report as conforming, a capability
  gap, an evidence-contract conflict, or a physical violation; labels cannot hide unresolved
  export, resolved-wrong geometry, review-required auto approval, or runtime/schema failure.
- `MeasurementProvenance` 现在拒绝 root 同时出现在 dependencies 中；content、
  frame geometry、photo-edge role、spacing 和 dual-lane containment 的派生路径已清理同类
  自循环。 / `MeasurementProvenance` now rejects its root appearing again in
  dependencies; derived content, frame-geometry, photo-edge-role, spacing, and
  dual-lane-containment paths no longer create the same self-cycle.
- Current-report validation now rejects one `ObservationId` carrying conflicting
  provenance, so duplicated identity cannot silently merge different physical
  observations. / Current report 现在拒绝同一 `ObservationId` 对应不同
  provenance，不允许重复 identity 静默合并不同物理观测。
- Final frame-sequence identity now rejects a separator assignment whose matching
  signed spacing is not `OBSERVED`, positive, non-geometric, and traceable to the
  assigned band, or whose cross-axis continuity was measured on a different
  short-axis span. / 最终 frame-sequence identity 现在拒绝与 assigned band 不可追溯、
  不是正值 `OBSERVED`、仍由 geometry hypothesis 授权，或跨轴连续性来自其他短轴 span 的
  separator assignment。
- Holder occlusion now requires a positive hidden extent and is restricted to
  the first slot's leading side or final slot's trailing side. / Holder occlusion
  现在必须隐藏正宽度，并且只能作用于首 slot 的 leading side 或尾 slot 的 trailing side。
- Content continuity can corroborate overlap only across independently measured
  physical boundary roles; repeated-width geometry can no longer gain overlap
  output-protection authority through content. / Content continuity 只能佐证两侧
  physical role 已独立测得的 overlap；repeated-width geometry 不能再借 content 获得
  overlap 输出保护权限。
- Canonical measured-frame and graph-path selection now rank physical support,
  observation quality, and measurement uncertainty before search hints; hints
  can order work but cannot choose the retained observation identity or graph
  predecessor. / Measured-frame 规范化与 graph-path 选择现在先比较物理支持、
  观测质量和测量不确定度，再比较 search hint；hint 只能安排搜索顺序，不能决定保留哪条
  观测 identity 或 graph predecessor。
- Assignment consensus now treats measured-versus-inferred slot identity as a
  real topology disagreement even when both alternatives occupy the same
  coordinates. / 即使两个替代解坐标完全相同，assignment consensus 也会把 measured
  slot 与 sequence-inferred slot 的身份差异保留为真实 topology disagreement。
- Candidate geometry clustering now preserves sequence-inferred slot identity
  and mutually exclusive visible extents instead of merging them by nominal
  boundary coordinates alone. / Candidate geometry clustering 现在同时保留
  sequence-inferred slot 身份与互斥 visible extent，不再只按 nominal boundary 坐标合并。
- Repeated-width boundary roles are now excluded from single-frame proof,
  single-frame geometry resolution, evidence-independence support, and measured
  frame-scale observations. / Repeated-width boundary role 现在不能进入单帧 proof、
  单帧 geometry resolution、evidence-independence support 或 measured frame-scale
  observation。
- REVIEW 导出现在同时要求 resolved geometry 与 feasible `FrameBleedPlan`；
  `--export-review` 不能绕过 unresolved overlap protection。Report validation、Debug
  和实际 writer 共用同一 export eligibility，且 current report 拒绝不可导出状态下声称存在
  frame outputs。 / REVIEW export now requires both resolved geometry and a feasible
  `FrameBleedPlan`; `--export-review` cannot bypass unresolved overlap protection.
  Report validation, Debug, and the writer share one export eligibility,
  whose positive reason is `geometry_resolved_output_protected`; current reports
  reject claimed frame outputs while export is ineligible.
- Report-based analysis reuse 已删除：runtime 不再从旧 report 恢复 Candidate、Gate、Decision 或
  final geometry，`--no-reuse-analysis`、相关 config、FailureStage 与 schema 状态也同步删除。
  Current report 只保留 `analysis_identity` 供审计与 regression 定位；每次运行重新检测，只有运行内
  exact、count/offset-independent measurement 可以缓存。 / Report-based analysis reuse was
  removed: runtime no longer restores Candidate, Gate, Decision, or final geometry
  from an earlier report, and `--no-reuse-analysis` plus its config, FailureStage,
  and schema state were deleted in the same change. Current reports retain only
  `analysis_identity` for audit and regression identity; every run detects afresh,
  and only exact, count/offset-independent measurements may be cached in-run.
- 在输出目录预置旧 report 后，00007 的普通运行仍执行 fresh detection（1 个 assessed candidate、
  13,557 次 assignment evaluation），并写入新的 `analysis_identity` report。六张冻结样片的
  selection、Decision、output 物理字段保持一致，Debug JPG 字节一致。 / With an earlier report
  pre-seeded in the output directory, a normal 00007 run still performed fresh
  detection (one assessed candidate and 13,557 assignment evaluations) and wrote a
  new `analysis_identity` report. The six frozen samples preserved selection,
  Decision, and physical output fields, with byte-identical Debug JPGs.
- 初始 provenance/sequence-conservation 波次使六张冻结 `135/full` 样片的循环
  provenance 由 55 降为 0，同时保持 canonical report 零差异和 Debug Analysis 字节一致。 /
  The initial provenance and sequence-conservation waves reduced cyclic
  provenances from 55 to zero across the six frozen `135/full` samples while
  preserving canonical reports and Debug Analysis bytes.
- 随后的 repeated-width 权限清理按物理事实移除了 00007/13/18/19/31 中依赖 pattern 的
  measured frame-scale/independence 记录；00031 新增 `evidence_independence_failed`，只有其
  Debug 标题改变，几何框未变。六张样片仍全部 `REVIEW` / 不导出。 / The later
  repeated-width authority cleanup removed pattern-dependent measured
  frame-scale and independence records from 00007/13/18/19/31; 00031 gained
  `evidence_independence_failed`, with only its Debug header changing and all
  geometry boxes preserved. All six samples remain `REVIEW` / non-exportable.
- 六张冻结 `135/full` 样片的 selection、DecisionGate、FrameBleedPlan、crop envelopes 与
  final boxes 保持逐字段一致；00007 仅修正 export eligibility 和 Debug 输出权限表达：保留
  FrameCropEnvelope，但不再绘制未受保护的 final boxes，真实 `--export-review` 运行没有写出
  frame TIFF；其余五张 Debug 只改变公共图例文字，几何像素一致。 / Across the six
  frozen `135/full` samples, selection, DecisionGate, FrameBleedPlan, crop
  envelopes, and final boxes remained field-identical; 00007 changed only export
  eligibility and Debug output-authority rendering, retaining FrameCropEnvelope
  while omitting unprotected final boxes, and an actual `--export-review` run wrote
  no frame TIFF. The other five Debug images changed only the shared legend text;
  their geometry pixels remained identical.
- 完整验证通过 769 项 current-only 测试和 14 组配置；旧 reuse/restoration 专属测试与死模块已删除。 /
  Full verification passed 769 current-only tests and 14 configuration pairs;
  obsolete reuse/restoration-only tests and the unreachable module were deleted.

### 2026-07-15 — 共享短轴与 Frame Slot / Shared Short Axis And Frame Slots

- 每条片条先解析一个共享安全短轴，再由全局 solver 联合解析有序 frame slots、共同宽度、
  separator assignments、片间关系与共识。 / Each strip resolves one shared safe short axis before
  the global solver resolves ordered frame slots, common width, separator assignments, spacing,
  and consensus.
- Full 序列最多允许一个由完整已解决序列唯一推导的空白 slot；缺少内容不能证明空白，也不能
  移动实测真实边界。 / A full sequence may contain at most one blank slot uniquely inferred from a
  resolved sequence; missing content neither proves the blank nor moves measured real boundaries.
- Report、Debug、cache reuse 和 regression reference 迁移到 current-only
  `frame_slot_sequence_resolution`。 / Reports, Debug, cache reuse, and regression references moved
  to the current-only `frame_slot_sequence_resolution` schema.
- 新模型使此前的 architecture-closure candidate 失效；必须重新完成物理验证、性能对比和两轮
  冻结清单审计。 / The new model invalidated the earlier architecture-closure candidate and requires
  fresh physical validation, performance comparison, and two frozen-checklist audits.

### 2026-07-14 — 权限、证据与性能收敛 / Authority, Evidence, And Performance

- 配置只在 runtime boundary 解析；检测下层不再读取 registry、scan calibration 或隐式默认值。 /
  Configuration resolves only at the runtime boundary; lower detection layers no longer query
  registries, scan calibration, or implicit defaults.
- TIFF resolution 只保留为输入/报告 metadata；候选内比例诊断不能反向证明生成它的同一几何。 /
  TIFF resolution remains input/report metadata only; candidate-local scale diagnostics cannot prove
  the geometry that produced them.
- 搜索结果区分 resolved、物理矛盾、测量不可用与 budget exhaustion；预算状态不再伪装成可靠性。 /
  Search distinguishes resolved geometry, physical contradiction, unavailable measurement, and budget
  exhaustion; execution state no longer masquerades as reliability.
- Pareto 归约只删除真正被逐边收窄的 geometry；宽 uncertainty 不能桥接并吞掉互斥窄解。 /
  Pareto reduction removes only genuinely refined geometry; broad uncertainty cannot bridge and erase
  mutually exclusive narrow solutions.
- Exact measurement 可按 typed identity 复用；candidate、Gate、decision 和近似几何不缓存。 /
  Exact measurements may be reused by typed identity; candidates, gates, decisions, and approximate
  geometry are never cached.
- 代表性热点在保持 unresolved 语义和 current-schema 输出的前提下显著降时；性能变化不授予物理
  权限。 / Representative hotspots were reduced while preserving unresolved semantics and current-schema
  output; performance never grants physical authority.

### 2026-07-13 — 灰度物理观测与联合序列 / Grayscale Observation And Joint Sequence

- Detection 收敛为一个 canonical grayscale workspace；颜色、材料标签和穿孔不参与检测证明。 /
  Detection converged on one canonical grayscale workspace; color, material labels, and perforations
  do not participate in proof.
- Boundary paths 成为带轨迹和 uncertainty 的二维观测；separator start/end 分别约束相邻 frame
  边界。 / Boundary paths became two-dimensional tracked observations with uncertainty; separator
  start/end constrain the adjacent frame boundaries separately.
- Content 只反证遗漏或裁断，不能创建、移动或收缩几何；同一观测与覆盖计算供 solver 和最终
  evidence 使用。 / Content may reject omission or clipping but cannot create, move, or shrink geometry;
  the solver and final evidence share the same observation and coverage calculation.
- Holder identity、assignment consensus 和 overlap support 都要求真实共同空间区间；单条宽路径不能
  抹平互斥 transition。 / Holder identity, assignment consensus, and overlap support require genuine
  shared spatial intervals; one broad path cannot erase mutually exclusive transitions.

### 2026-07-12 — 物理序列与决定合同 / Physical Sequence And Decision Contracts

- Candidate assessment、geometry resolution、selection、final decision 和 output finalization 分离；
  最终状态只由最终 decision 层创建。 / Candidate assessment, geometry resolution, selection, final
  decision, and output finalization are separate; only the final decision layer creates status.
- Format 只表达物理规格，不拥有算法分支；adaptive measurement 参数、runtime configuration 与报告
  描述保持分离。 / Formats describe physical specifications rather than algorithm branches; adaptive
  measurement parameters, runtime configuration, and report descriptions remain separate.
- 未解决 geometry 不可导出；`--export-review` 只允许已有 resolved geometry 的 REVIEW 输出。 /
  Unresolved geometry is never exportable; `--export-review` applies only to REVIEW results with resolved
  geometry.
- Output bleed 成为逐 boundary 计划，不再用全局最大值扩大无关 frame。 / Output bleed became a
  per-boundary plan rather than a global maximum applied to unrelated frames.

### 2026-07-11 — 模块化源码与 current-only schema / Modular Source And Current-Only Schema

- `X5_Crop.py` 保持薄入口，V4+ 开发源码迁移到分层 `x5crop/`；发布构建仍生成单文件脚本。 /
  `X5_Crop.py` remains a thin entry while V4+ development lives in layered `x5crop/`; release builds
  still generate one standalone script.
- Report、Debug、tests、tools 和 cache reuse 使用同一 current schema，不再重建缺失决定或保留旧字段。 /
  Reports, Debug, tests, tools, and cache reuse consume one current schema and no longer reconstruct
  missing decisions or retain superseded fields.
- Repository-owned hooks enforce staged-file hygiene and full pre-push validation while preserving Git
  LFS behavior. / 仓库自有 Hook 在保留 Git LFS 行为的同时执行 staged-file hygiene 与完整 pre-push
  验证。

## 当前验证边界 / Current Validation Boundary

- `tools/verify full` 是 unit contracts、compile、configuration consistency、macOS shell syntax、diff
  hygiene 和版本检查的统一入口。 / `tools/verify full` is the single entry for unit contracts, compile,
  configuration consistency, macOS shell syntax, diff hygiene, and version checks.
- GitHub Actions、pre-commit 与 pre-push 只调用该入口或其 staged/pre-push 模式。 / GitHub Actions,
  pre-commit, and pre-push are thin adapters around that verifier.
- 绿色测试不能代替具名 TIFF 的当前报告与 Debug 复核；精确暂停状态和剩余样片见
  `PROJECT_MEMORY.md`。 / Green tests do not replace current-report and Debug review of named TIFFs;
  the precise checkpoint and remaining samples live in `PROJECT_MEMORY.md`.
- 旧的 architecture-closure、测试数量和样片统计只描述对应提交与运行产物，不自动适用于当前
  checkout。 / Previous closure labels, test counts, and sample totals apply only to their identified
  commit and run artifacts, never automatically to the current checkout.

## 版本摘要 / Version Summary

| Version / 版本 | Status / 状态 | Summary / 摘要 |
|---|---|---|
| V4.9 | Active development / 当前开发 | Typed physical frame-sequence model and current-only architecture / typed 物理 frame sequence 与 current-only 架构 |
| V4.7 | Previous development / 旧开发线 | Thin entry and modular `x5crop/` layering / 薄入口与模块化源码分层 |
| V4.6 | Historical development / 历史开发 | Policy-driven detection structure / policy 驱动检测结构 |
| V4.3–V4.5 | Historical development / 历史开发 | Full/partial, 120, half-frame, diagnostics, and candidate experiments / 模式、格式、诊断与候选实验 |
| V4.2.8 | Stable release / 稳定发布 | Partial-only count prompt; Return/`auto` enables automatic count / 仅 partial 询问张数，回车或 `auto` 自动判断 |
| V3–V4.2 | Historical / 历史 | Early workflow, format parameters, and geometry experiments / 早期流程、格式参数与几何实验 |

## 发布政策 / Release Policy

- GitHub Releases 是用户下载渠道；`main` 可以领先稳定发布。 / GitHub Releases are the user
  download channel; `main` may lead the stable release.
- `tools/release_manifest.py` 是发布包内容的唯一清单，`tools.build_release` 生成 standalone script
  和 UTF-8 zip。 / `tools/release_manifest.py` is the single package manifest; `tools.build_release`
  generates the standalone script and UTF-8 zip.
- 用户包不含模块化源码、测试、内部文档、诊断启动器、本地样片或生成输出。 / User packages exclude
  modular source, tests, internal docs, diagnostics launchers, local samples, and generated output.
