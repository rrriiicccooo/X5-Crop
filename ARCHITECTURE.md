# X5 Crop 架构说明 / Architecture Guide

本文件是开发者架构地图，范围限定为源码分层、policy 行为边界、format / mode
隔离规则和验证要求。使用说明见 `README.md`，版本摘要见 `CHANGELOG.md`，
Codex 协作规则见 `AGENTS.md`。

This file is the developer architecture map. It covers source layers, policy
ownership, format / mode isolation, and verification requirements. For usage,
read `README.md`; for version history, read `CHANGELOG.md`; for Codex rules,
read `AGENTS.md`.

## 中文说明

### 架构目标

V4.9 是 evidence-governed policy reset。目标不是提高自动通过数量，而是让自动裁切
只发生在 outer、separator、geometry、content 和 risk 证据能够共同解释时。

架构原则：

- 入口精简，运行配置明确。
- workflow 只承担单图和批处理编排。
- format physical facts 与 policy decision rules 分离。
- detection 生成证据、候选和最终 PASS / REVIEW。
- geometry / image / io 提供底层能力，不拥有候选或决策语义。
- report / debug / export 只消费稳定结果，不反向参与候选选择。
- developer tools 位于 `tools/`，不进入 runtime package。

### 分层边界

| 层级 | 主要职责 |
|---|---|
| `X5_Crop.py` | 开发入口；Release 构建生成单文件发布版。 |
| `x5crop.cli` / `cli_options` / `runtime_config` | CLI 解析、入口参数契约、运行配置契约。 |
| `x5crop.interactive` / launchers | 交互式菜单；平台启动器只负责找到 Python 并进入交互模式。 |
| `x5crop.input_probe` / `x5crop.app` | 输入 TIFF 探测、layout 解析、启动摘要、worker 调度。 |
| `x5crop.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug 编排。 |
| `x5crop.formats` | format identity、physical spec、count/aspect facts 和 CLI choices 的唯一入口。 |
| `x5crop.policies` | runtime policy、decision contract、format / mode presets、参数解析和 policy detail 序列化。 |
| `x5crop.geometry` / `image` / `io` | box、gap、separator profile、deskew、pixel transform、TIFF I/O 等底层能力。 |
| `x5crop.detection` | outer proposals、evidence、candidate lifecycle、candidate assessment、finalization 和 PASS / REVIEW。 |
| `analysis_reuse` / `export` / `result_builder` / `report_schema` / `report_outputs` / `debug` | 缓存复用、TIFF 输出、结果组装、报告 schema、报告写入和 Debug Analysis。 |
| `tools` | standalone build、reference compare、safety classification 等开发工具。 |

依赖方向应从入口和工作流流向基础层；基础层不得反向依赖 workflow、detection、
debug、report 或 policy registry。

### 命名和 API 规则

- `*Options`: 文件探测前的入口参数，例如 `CliOptions`。
- `*Config`: 已解析运行配置，例如 `RuntimeConfig`。
- `*Spec`: 物理事实或格式规格，例如 `FormatSpec`。
- `*Parameters`: 数值参数和低层执行参数。
- `*Policy`: format / mode 行为、gate、decision 或 output 规则。
- `*Assessment`: candidate 阶段评估结果；不得表达最终裁切决定。
- `*Decision*`: 最终 PASS / REVIEW 语义。
- `*Result`: 已完成流程的返回对象。

当前 module、class、function、policy id 和架构标签应使用语义命名。版本号只应出现在
`VERSION` / `APP_VERSION`、release history、artifact 名、historical archive path
和 machine schema value 中。

### Policy 和决策模型

`DetectionDecisionContract` 是 public decision policy contract，包含：

- `ModePolicy`: full / partial count、outer、stop condition、edge trust。
- `EvidencePolicy`: outer / separator / geometry / content 的最低组合证据。
- `RiskPolicy`: overlap、outer-content mismatch、candidate competition、partial edge uncertainty 等 REVIEW 风险。
- `CandidatePolicy`: content-only、fallback、weak-grid、equal-gap 候选的默认保守行为。
- `DecisionPolicy`: PASS / REVIEW reason id 和 confidence cap。
- `OutputPolicy`: TIFF metadata/export 行为和输出 bleed。
- `DecisionDiagnosticsPolicy`: decision/report 中记录的 diagnostics 和 overlay 说明。

runtime `DetectionPolicy` 仍用于 evidence generation wiring。它连接 detector、count、
outer、separator、content、scoring、candidate run、selection、finalization、
diagnostics、report 和 output 等 runtime 能力。`DetectionDecisionContract` 必须通过
active `DetectionPolicy` 派生；`decision_overrides.py` 只保存不能从 runtime policy
直接推导的 final evidence threshold。影响最终 PASS / REVIEW 的参数必须进入 report
schema 的 decision policy detail。

### Detection / Gate / Risk 人工审核索引

本索引用于按检测逻辑族群人工审核，不按源码目录或运行顺序切分。`主要位置` 路径默认
相对 `x5crop/`。审核目标是确认每个逻辑只在合适的 format / mode 被 policy 启用，
生成的 evidence、gate、risk 和 decision detail 可解释，并且不会绕过最终 PASS /
REVIEW contract。

| 逻辑族群 | 子逻辑 | 主要位置 | 人工审核重点 |
|---|---|---|---|
| Pre-detection | layout / coordinate mapping | `geometry/layout.py`, `geometry/boxes.py` | horizontal / vertical 的 work-space 与 original-space 映射是否一致；不得让坐标转换改变裁切语义。 |
| Pre-detection | deskew angle selection | `image/deskew.py`, `image/deskew_parameters.py` | deskew 只能改变输入姿态和质量 detail；不应直接决定 PASS / REVIEW。 |
| Pre-detection | analysis / evidence gray | `image/evidence.py` | separator/content evidence gray 只能作为证据图和检测输入；不得隐藏真实灰度上下文。 |
| Policy activation | format physical facts | `formats.py` | count、aspect、family、physical risk 是否是事实层，不含 gate threshold。 |
| Policy activation | format / mode policy presets | `policies/format_*.py` | format-specific 逻辑是否只在本 format/mode 显式启用。 |
| Policy activation | runtime policy assembly | `policies/factory*.py`, `runtime_*.py` | preset、parameters、runtime policy 是否一一映射；默认字段不得让报告误以为逻辑已 active。 |
| Policy activation | final decision contract | `policies/decision_contract.py`, `policies/decision_overrides.py` | runtime `DetectionPolicy` 与 final `DetectionDecisionContract` 的证据门槛不能语义漂移。 |
| Mode-specific detector | dual-lane detector | `detection/modes/dual_lane.py`, `detection/modes/dual_lane_context.py`, `detection/modes/dual_lane_split.py`, `detection/modes/dual_lane_detect.py`, `detection/modes/dual_lane_merge.py` | `135-dual/full` 是否独立于普通 135 strip；入口是否只调度，policy/spec context、lane split / lane detect / lane merge 是否可解释。 |
| Mode-specific detector | review-only mode | `detection/modes/review_only.py`, `candidate/fallback.py` | review-only 或 hard fallback 必须保持 review-only，不得因为 confidence 偶然过线而 PASS。 |
| Outer proposal | base outer | `geometry/outer_boxes.py`, `detection/outer/proposal/base.py` | 基础 holder / content bbox 是否只提出 outer proposal，不承担评分或通过。 |
| Outer proposal | partial content-position outer | `detection/outer/proposal/partial_content.py`, `detection/outer/proposal/partial_edge.py` | 标准 partial 若内容不铺满片夹，统一建模为 edge-anchored 或 floating 两种位置；proposal plan 先尝试 edge，edge 候选达到 trust 门槛时跳过 floating；两者只提出 outer，必须继续经过 separator/content/geometry gate，`135-dual/partial` 仍由 review-only mode 接管。 |
| Outer proposal | separator-derived outer | `detection/outer/proposal/separator.py`, `detection/evidence/separator_bands.py` | local、full-width 和 wide separator variants 是否共享同一 outer proposal 引擎；spacing / width / frame-error 约束是否由 policy 控制。 |
| Outer proposal | proposal plan | `detection/outer/proposal/plan.py` | candidate 层只能通过 proposal plan 获取和合并 outer candidates；不得直接依赖 base/common/separator 内部 helper 或 variant 常量。 |
| Outer correction | geometry consistency correction | `detection/outer/correction/geometry.py` | short-axis 与 long-axis geometry consistency 是否保持各自 policy 触发条件；outer correction 只提出 corrected box，不直接 PASS / REVIEW。 |
| Outer correction | content containment correction | `detection/evidence/outer_alignment.py`, `detection/outer/correction/content_containment.py` | 内容边缘证据是否只用于提出更小的 corrected outer；修正后的候选必须由 candidate contract 重新 build detection 并重新 assessment。 |
| Corrected candidate | corrected outer reassessment | `detection/candidate/corrected_outer.py` | corrected outer 重新 build detection、重算 evidence 并重新 candidate assessment；candidate 层只负责“怎么重新算”，不决定 correction 何时发生。 |
| Final workflow | outer correction workflow contract | `detection/final/outer_correction.py` | correction 顺序固定为 geometry consistency 再 content containment；workflow 层强制 corrected outer 必须回到 candidate reassessment，不能无证据地覆盖已选候选，不能绕过最终 decision / gate。 |
| Gap / separator | separator profile | `geometry/separator_profile.py` | profile 生成是否稳定，edge refine profile 是否只作为 gap evidence。 |
| Gap / separator | separator cache | `geometry/separator_cache.py`, `detection/evidence/evidence_cache_keys.py`, `detection/cache_keys.py` | cache key 是否包含 format / layout / policy 参数，避免复用错误证据。 |
| Gap / separator | normal gap search | `geometry/gap_search.py` | gap width、guard、peak、geometry constraint 是否符合当前 format/mode。 |
| Gap / separator | hard-gap trust | `geometry/gap_trust.py` | hard gap 可信度是否能区分真实片间空隙、frame border、content edge。 |
| Gap / separator | edge-pair refine | `geometry/edge_pairs.py` | edge-pair 替换或确认 hard gap 时，score / shift 约束是否足够严格。 |
| Gap / separator | robust grid | `geometry/robust_grid.py` | grid 只能补模型证据；weak grid 不得单独获得 auto PASS。 |
| Gap / separator | nearby separator correction | `geometry/nearby_separator.py` | 附近更强 separator 替换后是否保留 confidence cap 和 diagnostics。 |
| Gap / separator | enhanced separator | `geometry/enhanced_separator.py` | enhanced analysis 何时触发、合并多少 gap、是否导致过度补证据。 |
| Gap / separator | wide gap retry | `detection/candidate/run.py`, `detection/candidate/source_policy.py` | 放宽 gap width 后的候选是否被标记、cap，并重新过 gate。 |
| Gap / separator | wide-separator gaps | `detection/evidence/separator.py` | 120-66 宽 separator gaps 是否只在 wide separator variant 中启用，不污染普通窄 separator。 |
| Gap diagnostics | gap diagnostics | `detection/evidence/gap_diagnostics.py` | diagnostic-only evidence 是否只解释 risk，不直接参与 candidate selection。 |
| Content | content evidence | `detection/evidence/content_evidence.py` | `ok / weak / low_content / aspect_conflict` 是否符合照片内容和 aspect。 |
| Content | content profile runs | `detection/evidence/content_profile.py` | content run 推测 frame 时是否处理缺失、断裂、局部曝光。 |
| Content | content mask outer | `detection/evidence/content_profile.py`, `image/evidence.py` | content bbox 只能生成线索，不能绕过 separator gate。 |
| Content | content candidate | `candidate/content_candidate.py` | content-only candidate 必须 review-only，除非未来显式改变 final contract。 |
| Content | content support score | `candidate/scoring.py` | content score 权重和 gate multiplier 是否不压倒 separator / geometry。 |
| Content | content mismatch review | `candidate/selection.py` | content 与 separator 候选冲突时是否倾向 review，而不是选择看似更高分的错误候选。 |
| Candidate | count / offset plan | `candidate/counts.py` | full / partial 的 count、offset、默认 count inclusion 是否符合片夹物理目标。 |
| Candidate | candidate source orchestration | `candidate/run.py`, `candidate/sources.py` | separator、wide retry、fallback、content candidate 的运行顺序和 skip 条件是否可解释。 |
| Candidate | build detection for outer | `candidate/build.py` | outer -> gaps -> frame boxes -> confidence 的中间 detail 是否完整可审。 |
| Candidate | frame fit | `geometry/frame_fit.py` | frame boxes 是否以 gaps 为核心，edge / geometry fit 只能保守微调。 |
| Candidate scoring | base confidence | `candidate/scoring.py` | gap、width、outer、contrast 权重是否不会让弱证据误过线。 |
| Candidate scoring | geometry support score | `candidate/scoring.py` | width_cv、outer area、aspect、count 是否与实际裁切稳定性一致。 |
| Candidate scoring | separator support score | `candidate/scoring.py` | hard/grid/equal 的信用是否符合 hard > model 的原则。 |
| Candidate scoring | joint score | `candidate/candidate_assessment.py` | geometry/content/separator 合分是否只辅助 gate，不替代 gate。 |
| Candidate scoring | hard full confidence floor | `candidate/scoring.py` | full 默认张数且 hard gaps 完整时抬 confidence 是否只用于可信完整片条。 |
| Gate | separator gate | `candidate/gates.py` | gate profile 是否与 format/mode policy 一致。 |
| Gate | `min_hard_with_equal_cap` | `candidate/gates.py` | 135 类策略允许少量 model/equal 时，hard gap 下限是否足够。 |
| Gate | `all_internal_gaps_hard` | `candidate/gates.py` | 120 / xpan 等 strict policy 是否要求内部 gap 足够硬。 |
| Gate | `geometry_support` | `candidate/gates.py`, `candidate/scoring.py` | half/full 的 stable grid / wide geometry 支持是否不借用到其它 format。 |
| Gate | leading grid failure | `candidate/gates.py` | 前段 grid 弱、hard gap 偏后时是否阻止 lucky pass。 |
| Gate | partial safe extra frames | `candidate/partial_holder.py` | partial 多扫 holder 时是否需要 wide-like gaps、low leading content、stable frame content。 |
| Gate | auto gate | `candidate/candidate_assessment.py` | `auto_gate=True` 是否同时满足 separator/content/geometry/mode-specific 证据且无 hard review reason。 |
| Retry / rescue | equal-first before wide retry | `candidate/source_policy.py`, `candidate/run.py` | wide retry 前的保守 equal-first 是否只在 policy 允许时使用。 |
| Retry / rescue | fallback outer proposal | `candidate/run.py`, `candidate/sources.py` | fallback 只能救回可复核候选，不应绕开 hard evidence。 |
| Retry / rescue | wide-separator retry | `candidate/wide_separator_retry.py` | 120-66 full/partial 的触发条件是否足够窄。 |
| Retry / rescue | full wide-separator selection | `candidate/wide_separator_selection.py` | full 模式 wide-separator 候选竞争是否需要明确帮助条件。 |
| Retry / rescue | partial stop | `candidate/run.py` | partial safe auto 后提前停止是否不会跳过更安全的 review 证据。 |
| Risk | overlap bleed risk | `detection/evidence/risk.py`, `gap_diagnostics.py` | gap 附近叠片/连续内容风险是否进入 REVIEW 或 output bleed。 |
| Risk | lucky pass risk | `detection/evidence/risk.py` | model/equal/grid 支撑的假 PASS 是否被拉回 REVIEW。 |
| Risk | outer-content mismatch | `detection/evidence/outer_alignment.py`, `detection/final/pass_review.py` | outer 与内容 bbox 不一致时是否压 confidence / 加 review reason。 |
| Risk | candidate competition close | `candidate/selection.py`, `final/pass_review.py` | 第一、第二候选接近时是否 review，partial safe 情况的豁免是否合理。 |
| Risk | content-only / fallback risk | `candidate/candidate_assessment.py`, `final/pass_review.py` | content-only、fallback、review-only 是否保持 conservative review-only。 |
| Risk | partial edge uncertain | `candidate/partial_holder.py`, `final/pass_review.py` | partial 边缘不可信时是否必须 REVIEW。 |
| Finalization | final outer correction | `detection/final/finalize.py`, `detection/final/outer_correction.py` | selected detection 后的 corrected outer 是否重新保留 evidence/risk detail，并且是否一定经过 candidate reassessment。 |
| Finalization | edge bleed protection | `detection/final/geometry.py` | 输出前 edge bleed 保护是否只做安全几何调整，不改变 decision 证据。 |
| Finalization | approved geometry adjustment | `detection/final/geometry.py` | PASS 前几何微调是否仅在已通过候选上执行。 |
| Finalization | final caps | `detection/final/finalize.py` | content low/aspect conflict、lucky pass、outer mismatch 的 confidence cap 是否一致。 |
| Finalization | final PASS / REVIEW | `detection/final/pass_review.py` | 最终裁决是否唯一落在 decision contract；review reason normalization 是否稳定。 |
| Audit visibility | read-only diagnostics | `detection/evidence/read_only.py` | 只写解释性 diagnostics，不改变 confidence、candidate 或 status。 |
| Audit visibility | report sections | `report_schema.py`, `report_sections.py` | candidate table、gate records、selected candidate 是否足以人工复盘。 |
| Audit visibility | debug panels | `debug/*`, `policies/runtime_diagnostics.py` | 三联图默认保持可读；更丰富证据进入 report/detail 而非挤满首屏。 |
| Audit visibility | policy reporting | `policies/reporting.py` | report 中应区分 active policy、默认值、format/mode role 和 diagnostics detail。 |

建议人工审核顺序：先看 `wide_separator`、`wide retry / enhanced separator`、`lucky pass risk`，
再依次看 outer、gap/content、candidate scoring、gate、final decision。任何行为修改都应
同步检查 report/debug 是否能解释变化。

### 必须隔离的行为

- 135 full 的完整片条假设不能推广给其它 format。
- 135-dual full 使用 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half/full` 开启。
- 120-66 wide-separator、square-frame、wide-like separator 和 strict-holder checks
  只适用于 120-66 full / partial。
- 120-67 可以有自己的 short-axis / wide-separator retry，但不能继承 120-66 wide-separator。
- weak grid、equal、content-only、fallback 或不可信 partial-edge 证据不能获得自动 PASS 权限。

### 数据和报告契约

- `CliOptions` 是文件探测前的用户选项；`RuntimeConfig` 是绑定输入和 layout 后的运行配置。
- `OuterCandidate.strategy` 是 candidate kind 契约；runtime 不应靠 name prefix 推断行为。
- `Detection` 和 `ProcessResult` 是 report、debug 和 export 的稳定输入。
- report row 顶层包含 `version` 和 `policy_id`。
- V4.9 使用 `v4_9_policy_schema_1`，包含 evidence、risk、decision policy 和 selected candidate detail。
- V4.5.4 / V4.7 reports 是 historical reference，不再是必须 0 diff 的 oracle。
  新增错误 PASS 不可接受；保守 REVIEW 和 schema/reason diff 必须解释。

### 验证要求

结构或 policy 改动后至少运行：

```bash
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

如果 checkout 展开了 `tools/`，同时编译 `tools/regression/*.py`。Release build 工具
改动还应运行 `tools/build_standalone.py`，并对生成的单文件执行 `--version` smoke。

检测行为改动使用 reference classifier：

```bash
python3 -m tools.regression.reference_classify --candidate-root <root>
```

核心字段：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

常用 reference sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

验收重点是 0 `unacceptable_wrong_pass` 和 0 无解释的 `risky_regression`。

## English Guide

### Architecture Goal

V4.9 is an evidence-governed policy reset. Its goal is not to increase automatic
PASS count, but to export crops automatically only when outer, separator,
geometry, content, and risk evidence jointly explain the decision.

Principles:

- Keep entry points thin and runtime configuration explicit.
- Keep workflow as orchestration only.
- Separate format physical facts from policy decision rules.
- Let detection own evidence, candidates, and final PASS / REVIEW.
- Keep geometry / image / io as lower-level capabilities without candidate or decision semantics.
- Let report / debug / export consume stable results only.
- Keep developer tools under `tools/`, outside the runtime package.

### Layer Boundaries

| Layer | Responsibility |
|---|---|
| `X5_Crop.py` | Development entry; Release builds produce the standalone script. |
| `x5crop.cli` / `cli_options` / `runtime_config` | CLI parsing, entry option contract, runtime configuration contract. |
| `x5crop.interactive` / launchers | Interactive menu; platform launchers only locate Python and enter interactive mode. |
| `x5crop.input_probe` / `x5crop.app` | TIFF input probing, layout resolution, startup summary, worker dispatch. |
| `x5crop.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug orchestration. |
| `x5crop.formats` | Single source of truth for format identity, physical specs, counts/aspects, and CLI choices. |
| `x5crop.policies` | Runtime policy, decision contract, format/mode presets, parameter resolution, policy detail serialization. |
| `x5crop.geometry` / `image` / `io` | Boxes, gaps, separator profiles, deskew, pixel transforms, TIFF I/O, and other lower-level capabilities. |
| `x5crop.detection` | Outer proposals, evidence, candidate lifecycle, candidate assessment, finalization, PASS / REVIEW. |
| `analysis_reuse` / `export` / `result_builder` / `report_schema` / `report_outputs` / `debug` | Cache reuse, TIFF output, result assembly, report schema, report writing, Debug Analysis. |
| `tools` | Standalone build, reference compare, safety classification, and other developer tools. |

Dependencies should flow from entry/workflow toward foundation layers. Foundation
layers must not depend back on workflow, detection, debug, report, or the policy
registry.

### Naming And API Rules

- `*Options`: entry options before file probing.
- `*Config`: resolved runtime configuration.
- `*Spec`: physical facts or format specifications.
- `*Parameters`: numeric or low-level execution parameters.
- `*Policy`: format / mode behavior, gates, decisions, or output rules.
- `*Assessment`: candidate-stage evaluation.
- `*Decision*`: final PASS / REVIEW semantics.
- `*Result`: completed process return objects.

Current module, class, function, policy id, and architecture names should be
semantic. Version tags belong only in version constants, release history,
artifact names, archive paths, and machine schema values.

### Policy And Decision Model

`DetectionDecisionContract` is the public decision policy contract:

- `ModePolicy`: full / partial count, outer, stop condition, edge trust.
- `EvidencePolicy`: minimum combined outer / separator / geometry / content evidence.
- `RiskPolicy`: review risks such as overlap, outer-content mismatch, competition, partial-edge uncertainty.
- `CandidatePolicy`: conservative defaults for content-only, fallback, weak-grid, and equal-gap candidates.
- `DecisionPolicy`: PASS / REVIEW reason ids and confidence caps.
- `OutputPolicy`: TIFF metadata/export behavior and output bleed.
- `DecisionDiagnosticsPolicy`: diagnostics and overlay details recorded in decision/report.

Runtime `DetectionPolicy` remains the evidence-generation wiring surface.
`DetectionDecisionContract` must be derived from the active `DetectionPolicy`;
`decision_overrides.py` only stores final evidence thresholds that cannot be
directly inferred from runtime policy. Any parameter that affects final PASS /
REVIEW must be present in report schema decision policy detail.

### Detection / Gate / Risk Review Index

Use this index for manual review by detector logic family rather than by source
directory or execution order. Paths in `Main location` are relative to `x5crop/`
unless stated otherwise. The goal is to verify that each behavior is enabled only
by the intended format/mode policy, produces explainable evidence, gates, risks,
and decision detail, and cannot bypass the final PASS / REVIEW contract.

| Logic family | Sub-logic | Main location | Review focus |
|---|---|---|---|
| Pre-detection | layout / coordinate mapping | `geometry/layout.py`, `geometry/boxes.py` | Horizontal / vertical work-space mapping must not change crop semantics. |
| Pre-detection | deskew and evidence gray | `image/deskew.py`, `image/evidence.py` | Preprocessing may shape evidence but must not decide PASS / REVIEW. |
| Policy activation | format facts and policy presets | `formats.py`, `policies/format_*.py` | Physical facts, thresholds, and format/mode activations must stay separate and explicit. |
| Policy activation | runtime and decision contracts | `policies/runtime_*.py`, `policies/decision_contract.py` | `DetectionPolicy` and `DetectionDecisionContract` must not drift semantically. |
| Mode-specific detector | dual-lane and review-only paths | `detection/modes/dual_lane.py`, `detection/modes/dual_lane_*.py`, `detection/modes/review_only.py`, `candidate/fallback.py` | Dedicated detectors and review-only paths must stay isolated, context-driven, and conservative. |
| Outer proposal | base, partial content-position, separator-derived outer | `detection/outer/proposal/*`, `geometry/outer_boxes.py`, `detection/evidence/separator_bands.py` | Outer proposals only propose boxes; standard partial mode tries edge-anchored content before floating content and skips floating when edge candidates are trusted. Local, full-width, and wide separator variants share one separator-derived proposal engine behind the proposal plan. |
| Outer correction | geometry consistency and content containment correction | `detection/outer/correction/geometry.py`, `detection/outer/correction/content_containment.py`, `detection/evidence/outer_alignment.py` | Outer correction only proposes corrected boxes and reasons. It does not rebuild candidates and does not own PASS / REVIEW. |
| Corrected candidate | corrected outer reassessment | `detection/candidate/corrected_outer.py` | Candidate contract rebuilds detection, recomputes evidence, and reapplies candidate assessment for any corrected outer. |
| Final workflow | outer correction workflow contract | `detection/final/outer_correction.py` | Final workflow decides when correction must be attempted and sends every corrected outer back through candidate reassessment before final decision/gate. |
| Gap / separator | profile, cache, normal gap search, hard trust, edge pair, robust grid | `geometry/separator_*`, `geometry/gap_search.py`, `geometry/gap_trust.py`, `geometry/edge_pairs.py`, `geometry/robust_grid.py` | Hard evidence must stay stronger than model/equal/grid evidence, and cache keys must include policy-relevant context. |
| Gap / separator | nearby correction, enhanced separator, wide retry, wide-separator gaps | `geometry/nearby_separator.py`, `geometry/enhanced_separator.py`, `detection/candidate/run.py`, `detection/evidence/separator.py` | Rescue evidence must be marked, capped when needed, and gated again. |
| Content | content evidence, profile runs, mask outer, content candidate | `detection/evidence/content_*`, `candidate/content_candidate.py` | Content can validate or challenge candidates but must not auto-pass alone. |
| Candidate | count/offset, source orchestration, build, frame fit | `detection/candidate/counts.py`, `detection/candidate/run.py`, `detection/candidate/sources.py`, `detection/candidate/build.py`, `geometry/frame_fit.py` | Candidate lifecycle must keep all intermediate evidence in `Detection.detail`. |
| Scoring | base confidence, geometry/content/separator scores, joint score, hard-full floor | `detection/candidate/scoring.py`, `detection/candidate/candidate_assessment.py` | Scores support gates; they do not replace separator/content/geometry requirements. |
| Gate | separator gate profiles and geometry support | `detection/candidate/gates.py`, `detection/candidate/scoring.py` | `min_hard_with_equal_cap`, `all_internal_gaps_hard`, and `geometry_support` must match format/mode policy. |
| Gate | partial safe extra frames and auto gate | `detection/candidate/partial_holder.py`, `detection/candidate/candidate_assessment.py` | Partial edge safety requires explicit wide-like/content/frame evidence and no hard review reason. |
| Retry / rescue | equal-first, fallback outer, wide-separator retry, full wide-separator selection, partial stop | `detection/candidate/source_policy.py`, `detection/candidate/run.py`, `detection/candidate/wide_separator_*.py` | Retry paths must be narrow, explainable, and unable to bypass hard evidence. |
| Risk | overlap bleed, lucky pass, outer-content mismatch, close competition | `detection/evidence/risk.py`, `detection/evidence/gap_diagnostics.py`, `detection/evidence/outer_alignment.py`, `detection/candidate/selection.py`, `detection/final/pass_review.py` | Risk logic should pull suspicious PASS candidates back to REVIEW or safer output bleed. |
| Risk | content-only, fallback, review-only, partial-edge uncertainty | `detection/candidate/candidate_assessment.py`, `detection/candidate/fallback.py`, `detection/final/pass_review.py` | Conservative REVIEW-only paths must stay review-only unless the decision contract changes. |
| Finalization | final outer correction, edge bleed protection, approved geometry adjustment, caps | `detection/final/finalize.py`, `detection/final/geometry.py` | Output-adjacent geometry changes must preserve evidence/risk detail and safety caps. |
| Final decision | PASS / REVIEW, reason normalization, decision detail | `detection/final/pass_review.py` | Final status must be decided only by the decision contract. |
| Audit visibility | read-only diagnostics, report sections, debug panels, policy reporting | `detection/evidence/read_only.py`, `report_schema.py`, `report_sections.py`, `debug/*`, `policies/reporting.py` | Reports and Debug Analysis explain behavior without feeding back into candidate selection. |

Recommended manual review order: start with `wide_separator`, `wide retry / enhanced
separator`, and `lucky pass risk`; then review outer, gap/content, candidate
scoring, gates, and final decision. Any behavior change must also prove that
report/debug output explains the change.

### Behavior That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for
  `half/full`.
- 120-66 wide-separator, square-frame, wide-like separator, and strict-holder checks
  stay limited to 120-66 full / partial.
- 120-67 may have its own retry behavior, but must not inherit 120-66 wide-separator behavior.
- Weak grid, equal, content-only, fallback, or untrusted partial-edge evidence
  must not gain automatic PASS authority.

### Data And Report Contracts

- `CliOptions` records user options before file probing; `RuntimeConfig` records
  resolved input/layout runtime configuration.
- `OuterCandidate.strategy` is the candidate-kind contract.
- `Detection` and `ProcessResult` are stable report/debug/export inputs.
- Report rows include top-level `version` and `policy_id`.
- V4.9 uses `v4_9_policy_schema_1` with evidence, risk, decision policy, and selected candidate detail.
- V4.5.4 / V4.7 reports are historical references, not mandatory 0-diff oracles.
  New wrong PASS is unacceptable; conservative REVIEW and schema/reason diffs
  require explanation.

### Verification

After structure or policy changes, run:

```bash
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

If `tools/` is expanded, also compile `tools/regression/*.py`. For detector
behavior changes, classify reference reports with:

```bash
python3 -m tools.regression.reference_classify --candidate-root <root>
```

The acceptance target is 0 `unacceptable_wrong_pass` and 0 unexplained
`risky_regression`.
