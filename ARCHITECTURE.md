# X5 Crop 架构说明 / Architecture Guide

本文件是当前源码清洁审核和后续结构变更的主导架构契约。它定义源码层级、policy
所有权、候选和决策边界、format / mode 隔离规则，以及必须通过的验证门槛。

本文件不记录版本流水、人工审核台账或用户操作说明。版本变化见 `CHANGELOG.md`；
用户手册见 `README.md`；Codex 协作规则和当前 handoff 见 `AGENTS.md`。

This file is the active architecture contract for source cleanup and future
structural changes. It defines source layers, policy ownership, candidate and
decision boundaries, format / mode isolation, and required verification gates.

It is not a changelog, audit ledger, or user manual. Version history belongs in
`CHANGELOG.md`; usage belongs in `README.md`; Codex coordination and handoff
belong in `AGENTS.md`.

## 中文说明

### 1. 架构命题

V4.9 是 evidence-governed policy reset。目标不是增加自动 PASS 数量，而是让自动裁切
只发生在 outer、separator、geometry、content 和 risk 证据能够共同解释时。

架构判断：

- 自动 PASS 不是高分结果，而是证据契约结果。
- 新增错误 PASS 不可接受；更保守的 REVIEW 可以接受，但必须可解释。
- 裁切目标是保护真实图像内容。full 和 partial 都允许多切出不含真实影像的空 frame；
  只要真实图像没有被切伤，空 frame 本身不是负面证据。
- format physical facts、runtime policy、candidate evidence 和 final decision
  必须分层表达。
- 检测能力可以通用化；默认启用必须由 format / mode policy 显式控制。
- TIFF metadata、位深、ICC、resolution 和压缩行为属于输出契约，不能被检测重构改变。

### 2. 不可破坏的边界

| 领域 | 唯一职责 |
|---|---|
| Format facts | `x5crop.formats` 定义格式身份、family、张数、aspect 和物理事实。 |
| Runtime policy | `x5crop.policies` 定义 format / mode 行为、gate、risk、diagnostics、output 和 policy detail。 |
| Foundation | `x5crop.geometry`、`x5crop.image`、`x5crop.io` 提供 box、gap、profile、deskew、pixel transform 和 TIFF I/O 等底层能力。 |
| Detection | `x5crop.detection` 生成候选、证据、候选评估、候选选择和最终 PASS / REVIEW 输入。 |
| Decision | `x5crop.detection.decision` 按 decision contract 产生最终 `PASS` / `REVIEW`。 |
| Finalization | `x5crop.detection.final` 只做 output-adjacent geometry、bleed、cap 和只读 diagnostics attachment。 |
| Output surfaces | `x5crop.export`、`x5crop.report`、`x5crop.debug` 只消费稳定结果。 |
| Tools | `tools/` 承担 standalone build、reference compare 和 safety classification；不进入 runtime package。 |

基础层规则：

- `geometry` / `image` / `io` 不得依赖 runtime、cache、workflow、detection、debug、
  report 或 policy registry。
- 基础层不得读取 `Detection.detail`、risk detail 或 PASS / REVIEW 语义。
- 基础层不得接收 `strip_mode` 字符串；上层必须先解析为普通参数对象。
- cache adapter 属于 `x5crop.cache`；纯数学和像素能力留在 foundation。

### 3. 运行所有权地图

| 层级 | 主要职责 |
|---|---|
| `X5_Crop.py` | 开发入口；Release 构建生成单文件发布版。 |
| `x5crop.entry` | CLI 和交互入口；只形成入口选项。 |
| `x5crop.runtime.config` | 将入口选项、输入、layout 和运行参数解析为 `RuntimeConfig`。 |
| `x5crop.runtime.input_probe` / `x5crop.runtime.app` | 探测 TIFF、解析 layout、打印启动摘要、调度 worker。 |
| `x5crop.runtime.workflow` | 单图流程编排：read -> preprocess -> detect -> finalization -> export/report/debug。 |
| `x5crop.formats` | format identity、physical spec、count/aspect facts 和 CLI choices 的单一入口。 |
| `x5crop.policies` | runtime policy、decision contract、format 参数覆盖、preset assembly 和 policy detail serialization。 |
| `x5crop.cache` | analysis、profile、evidence cache adapters；只复用计算结果，不产生候选或决策。 |
| `x5crop.detection` | detector mode、physical proposal、content guidance、candidate lifecycle、evidence、decision 和 finalization。 |
| `x5crop.report` / `x5crop.debug` / `x5crop.export` | 报告、Debug Analysis 和 TIFF 输出；不反向参与选择。 |

依赖方向应从入口、runtime 和 workflow 流向 policy、detection 和 foundation。任何反向依赖、
隐式 global state 或 format-name if/else 都需要被重新审查。

### 4. Detection 子层

`workflow` 只负责调度；检测语义必须留在 `x5crop.detection` 内部。

| 子层 | 职责边界 |
|---|---|
| `detection.pipeline` | 候选计划、候选池、扩展和 selection 的 orchestration。 |
| `detection.modes` | dual-lane、review-only 等 mode detector。 |
| `detection.physical` | holder physical structure：outer proposal / correction、separator proposal / model。 |
| `detection.guidance` | content-derived guidance：outer hints、separator hints、review-only content-model candidate。 |
| `detection.evidence` | separator、content、geometry、outer alignment、risk 和只读 diagnostics evidence。 |
| `detection.candidate.plan` | count、offset、candidate source 和 execution budget。 |
| `detection.candidate.proposal` | safety、review-only 等非物理候选入口。 |
| `detection.candidate.build` | outer -> separator gaps -> frames -> unscored `Detection`。 |
| `detection.candidate.assessment` | base scoring、pure support scores、gate support、candidate-level review reasons 和 auto gate。 |
| `detection.candidate.selection` | 多候选竞争和 selected candidate。 |
| `detection.candidate.extension` | corrected outer、content-guided separator 等 reassessed candidates。 |
| `detection.decision` | final evidence summary、risk summary、PASS / REVIEW 和 reason normalization。 |
| `detection.final` | output bleed、approved geometry adjustment 和 read-only diagnostics attachment。 |

关键规则：

- outer 和 separator 是 physical holder structure；content 是 guidance + evidence。
- content 可以提示 search center 或生成 review-only content-model candidate；不能生成 hard gap，
  不能修 physical result，不能直接 PASS / REVIEW。
- content scoring 使用 containment 语义：真实图像 frame 必须被完整包含；安全 overcut
  和空 frame 只写入 detail，不应单独拉低评分或阻断 PASS。
- raw outer area 只是候选阶段的 diagnostic；是否 overcut 有害必须由 final
  outer-content alignment、content containment 和 separator / geometry 共同解释。
- content quality score 只表示影像证据强弱，不是 content hard gate。最终 hard gate
  关注真实内容是否完整包含，以及是否存在 aspect / boundary harm risk。
  partial-holder 和 evidence-dependency validation 也只能把 content score 写成
  quality detail，不能把低 quality score 当作独立失败原因。
- global image contrast 只表示输入图像质量，不是裁切物理事实；它可以写入
  image-quality detail，但不能作为 base confidence weight 或独立 review reason。
- candidate build 不评分、不最终裁决；assessment 和 decision 才能消费证据形成 gate 结果。
- `assessment.scoring` 只计算 support scores；base confidence / reasons 属于
  `assessment.base_scoring`，gate supplemental support 属于 `assessment.gate_support`。
- 宽度稳定性评分以照片影像区域尺寸为准：有可靠 separator edge 时使用
  `photo_width_cv`；`frame_box_width_cv` 只是 fallback / output geometry detail；
  `separator_width_cv` 只是 separator evidence detail，宽窄不一不会被直接当成照片尺寸不稳。
  support score、gate-support、risk credit、`photo_width_unstable` 和 final
  photo-width gate 都只能消费 `photo_edges` 来源。
  对应 scoring / gate policy 字段使用 `photo_width_*` 命名；普通 `width_cv`
  只保留为报告兼容字段或 gap / separator 几何自身的测量名。
- corrected candidate 必须重新 build、重新 assessment，再回到候选池统一 selection。

### 5. Policy 和决策模型

`DetectionPolicy` 是 runtime 能力和参数的组合面。它连接 detector、count、outer、
separator、content、scoring、selection、candidate extension、diagnostics、report 和
output。

`DetectionDecisionContract` 是最终 PASS / REVIEW 的 public decision policy contract。
它必须从 active `DetectionPolicy` 派生；`policies/decision/overrides.py` 只保存无法从
runtime policy 直接推导的最终证据门槛。

`x5crop.policies` 所有权：

| 子包 | 职责 |
|---|---|
| `policies.formats` | format-specific physical tolerance、content profile tolerance 和 search budget overrides。不得声明 scoring、gate、risk、detector、diagnostics 或 runtime preset。 |
| `policies.parameters` | 数值参数对象、format parameter registry 和 override ownership validator。 |
| `policies.runtime` | runtime `DetectionPolicy` 及其子 policy dataclass。 |
| `policies.decision` | final decision contract 和少量 final evidence overrides。 |
| `policies.assembly` | 从 format id、物理 facts、受限参数覆盖和 profile defaults 组装 runtime policy。 |
| `policies.reporting` | policy detail serialization；只负责报告可见性。 |
| `policies.registry` / `consistency` / `ids` | public lookup、consistency smoke 和 schema / policy id。 |

影响最终 PASS / REVIEW 的参数必须进入 report 的 decision policy detail。影响 runtime
检测路径但不直接决定 PASS / REVIEW 的参数必须进入 runtime policy detail。

### 6. 决策权

自动 PASS 至少需要：

- 候选来源符合当前 format / mode policy。
- separator、geometry、content 和 outer evidence 共同支持候选。
- gate profile、partial-holder requirements 和 mode-specific checks 通过。
- risk 层没有将候选拉回 REVIEW。
- final decision contract 允许该候选自动通过。

保守规则：

- score 只能辅助 gate，不能替代 gate。
- score 应把物理事实变成数值偏好：照片影像区域尺寸一致、separator 可解释、真实内容完整
  包含应加分；separator 宽度不均和安全空 frame 不应被误读成照片尺寸不稳或内容损伤。
- base confidence 只能由 separator/gap support 和 photo-width stability 组成。
  raw outer area 与全局 contrast 都只用于诊断或后续 final contract，不参与 base confidence。
- support score、gate-support、risk credit 和 width-instability risk 只能把
  `photo_edges` 来源的宽度 CV 当成照片尺寸证据；`frame_boxes` fallback
  只能作为弱 geometry detail。
- `photo_width_unstable` 和 final photo-width gate 只能消费 `photo_edges`
  来源；`frame_boxes` fallback 不能产生照片宽度不稳 hard reason。
- risk 只能拉回 REVIEW 或限制输出，不能救回 PASS。
- weak grid、equal、content-only、safety、review-only、untrusted partial-edge 或 evidence
  dependency cycle 不能获得自动 PASS 权限。
- separator-derived outer 若依赖 observed width-profile gaps，自动 PASS 必须再由
  standard hard gap、content ok 和 geometry ok 独立确认。

### 7. 必须隔离的行为

- 135 full 的完整片条假设不能推广给其它 format。
- 135-dual full 使用 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half/full` 开启。
- `width_aware` 是唯一 active separator gap profile；observed width 是中性实测宽度证据，
  不是 broad-only profile。
- 120-66 的 broad-width、square-frame、separator-derived outer 和 strict-holder 风险模型
  只能由 120-66 相关 policy 默认启用，不能默认推广给其它 format。
- 120-66 partial 的额外安全检查属于 holder-edge disambiguation：separator width
  evidence 可以作为消歧证据，但 active gate / reason 不应把“宽 separator”当成唯一物理身份。
- outer correction 是通用 corrected-candidate capability；format 只能调物理参数和 gate，
  不能拥有独立 correction algorithm switch。
- partial-holder policy 可以表达更多 holder safety requirement；默认严格行为不得被推广给
  half / xpan / 645。

### 8. 数据和报告契约

- `CliOptions` 是文件探测前的用户选项。
- `RuntimeConfig` 是绑定输入、layout 和 policy 后的运行配置。
- `Detection` 是检测阶段的稳定候选结果。
- `ProcessResult` 是 report、debug 和 export 的稳定输入。
- report row 顶层必须包含 `version`、`policy_id` 和 `report_schema`。
- V4.9 使用 `v4_9_policy_schema_1`，包含 evidence、risk、decision policy 和 selected
  candidate detail。
- V4.5.4 / V4.7 reports 是 historical reference，不再是 mandatory 0-diff oracle。
  新增 wrong PASS 不可接受；保守 REVIEW、schema diff 和 reason diff 必须解释。

### 9. 清洁编辑规则

- 一个概念只能有一个长期 owner；兼容 adapter 必须窄、短、可删除。
- 新命名必须语义化，不使用 format 号、版本号或历史实现名表达当前职责。
- 版本号只应出现在 version constants、release history、artifact 名、archive path 和
  machine schema value 中。
- `pipeline.py`、`workflow.py`、`common.py` 和 public re-export 只能保留必要 orchestration
  或兼容面；新实现应进入职责明确的子模块。
- `ARCHITECTURE.md` 只保留当前架构契约；历史迁移细节写入 `CHANGELOG.md`，当前交接写入
  `AGENTS.md`。

### 10. 验证门槛

文档-only 变更至少运行：

```bash
git diff --check
```

源码或 policy 变更至少运行：

```bash
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

如果 checkout 展开了 `tools/`，同时编译 `tools/regression/*.py`。

检测行为变更使用 reference classifier：

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

关键 reference sets：

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

### 1. Architecture Thesis

V4.9 is an evidence-governed policy reset. Its goal is not to increase automatic
PASS count, but to export crops automatically only when outer, separator,
geometry, content, and risk evidence jointly explain the result.

Architectural stance:

- Automatic PASS is a contract result, not a high-score result.
- New wrong PASS is unacceptable; more conservative REVIEW is acceptable when explained.
- The crop target is real image preservation. Both full and partial strips may
  overcut extra empty frames; if real image content is not harmed, an empty frame
  is not negative evidence by itself.
- Format physical facts, runtime policy, candidate evidence, and final decision
  must stay separate.
- Capabilities may be generalized; default enablement must remain explicit in
  format / mode policy.
- TIFF metadata, bit depth, ICC, resolution, and compression behavior are output
  contracts and must not change during detection refactors.

### 2. Non-Breakable Boundaries

| Area | Sole responsibility |
|---|---|
| Format facts | `x5crop.formats` defines format identity, family, counts, aspect, and physical facts. |
| Runtime policy | `x5crop.policies` defines format / mode behavior, gates, risks, diagnostics, output, and policy detail. |
| Foundation | `x5crop.geometry`, `x5crop.image`, and `x5crop.io` provide boxes, gaps, profiles, deskew, pixel transforms, and TIFF I/O. |
| Detection | `x5crop.detection` creates candidates, evidence, candidate assessment, selection, and final decision inputs. |
| Decision | `x5crop.detection.decision` produces final `PASS` / `REVIEW` from the decision contract. |
| Finalization | `x5crop.detection.final` handles output-adjacent geometry, bleed, caps, and read-only diagnostics attachment. |
| Output surfaces | `x5crop.export`, `x5crop.report`, and `x5crop.debug` consume stable results only. |
| Tools | `tools/` handles standalone build, reference comparison, and safety classification outside the runtime package. |

Foundation rules:

- `geometry` / `image` / `io` must not depend on runtime, cache, workflow,
  detection, debug, report, or the policy registry.
- Foundation layers must not read `Detection.detail`, risk detail, or PASS /
  REVIEW semantics.
- Foundation layers must not accept `strip_mode` strings; upper layers must pass
  ordinary parameter objects.
- Cache adapters belong in `x5crop.cache`; pure math and pixel capability stay in
  foundation layers.

### 3. Runtime Ownership Map

| Layer | Responsibility |
|---|---|
| `X5_Crop.py` | Development entry; Release builds produce the standalone script. |
| `x5crop.entry` | CLI and interactive entry; produces entry options only. |
| `x5crop.runtime.config` | Resolves entry options, input, layout, and runtime settings into `RuntimeConfig`. |
| `x5crop.runtime.input_probe` / `x5crop.runtime.app` | Probes TIFF input, resolves layout, prints startup summary, and dispatches workers. |
| `x5crop.runtime.workflow` | Orchestrates one image: read -> preprocess -> detect -> finalization -> export/report/debug. |
| `x5crop.formats` | Single entry for format identity, physical specs, count/aspect facts, and CLI choices. |
| `x5crop.policies` | Runtime policy, decision contract, format overrides, preset assembly, and policy detail serialization. |
| `x5crop.cache` | Analysis, profile, and evidence cache adapters; they reuse results but do not create candidates or decisions. |
| `x5crop.detection` | Detector modes, physical proposals, content guidance, candidate lifecycle, evidence, decision, and finalization. |
| `x5crop.report` / `x5crop.debug` / `x5crop.export` | Reports, Debug Analysis, and TIFF output; they do not feed back into selection. |

Dependencies should flow from entry, runtime, and workflow toward policy,
detection, and foundation layers. Reverse dependencies, implicit global state,
or format-name conditionals require review.

### 4. Detection Sublayers

`workflow` schedules the work; detection semantics must remain inside
`x5crop.detection`.

| Sublayer | Boundary |
|---|---|
| `detection.pipeline` | Candidate plan, candidate pool, extension, and selection orchestration. |
| `detection.modes` | Mode detectors such as dual-lane and review-only. |
| `detection.physical` | Holder physical structure: outer proposal / correction and separator proposal / model. |
| `detection.guidance` | Content-derived guidance: outer hints, separator hints, review-only content-model candidates. |
| `detection.evidence` | Separator, content, geometry, outer alignment, risk, and read-only diagnostics evidence. |
| `detection.candidate.plan` | Count, offset, candidate source, and execution budget. |
| `detection.candidate.proposal` | Non-physical candidate entries such as safety and review-only. |
| `detection.candidate.build` | outer -> separator gaps -> frames -> unscored `Detection`. |
| `detection.candidate.assessment` | Base scoring, pure support scores, gate support, candidate-level review reasons, and auto gate. |
| `detection.candidate.selection` | Candidate competition and selected candidate. |
| `detection.candidate.extension` | Reassessed candidates such as corrected outer and content-guided separator. |
| `detection.decision` | Final evidence summary, risk summary, PASS / REVIEW, and reason normalization. |
| `detection.final` | Output bleed, approved geometry adjustment, and read-only diagnostics attachment. |

Rules:

- Outer and separator are physical holder structure; content is guidance + evidence.
- Content may guide search centers or create review-only content-model candidates,
  but it must not create hard gaps, mutate physical results, or decide PASS /
  REVIEW.
- Content scoring uses containment semantics: content-bearing frames must be
  intact; safe overcut and empty frames are reported as detail and should not
  independently reduce score or block PASS.
- Raw outer area is candidate-stage diagnostic only. Whether overcut is harmful
  must be explained by final outer-content alignment, content containment, and
  separator / geometry evidence together.
- Content quality score measures evidence strength only; it is not the content
  hard gate. Final hard gates care about intact real content and aspect /
  boundary harm risk. Partial-holder checks and evidence-dependency validation
  may report content quality detail, but low quality score is not an independent
  failure reason.
- Global image contrast expresses input image quality, not crop geometry. It may
  be reported as image-quality detail, but it must not be a base confidence
  weight or independent review reason.
- Candidate build does not score or decide; assessment and decision consume evidence.
- `assessment.scoring` calculates support scores only. Base confidence / reasons
  belong to `assessment.base_scoring`; supplemental gate support belongs to
  `assessment.gate_support`.
- Width-stability scoring means photo image-region stability: when reliable
  separator edges are available, assessment uses `photo_width_cv`;
  `frame_box_width_cv` is only a fallback / output-geometry detail, and
  `separator_width_cv` is separator evidence detail rather than a direct penalty.
  Support scores, gate support, risk credit, `photo_width_unstable`, and final
  photo-width gates may consume only `photo_edges` evidence.
  Related scoring / gate policy fields use `photo_width_*` names; plain
  `width_cv` remains only as report compatibility or gap / separator geometry
  measurement wording.
- Corrected candidates must be rebuilt, reassessed, and returned to the shared
  candidate pool before selection.

### 5. Policy And Decision Model

`DetectionPolicy` is the runtime capability and parameter surface. It wires
detector, count, outer, separator, content, scoring, selection, candidate
extension, diagnostics, report, and output.

`DetectionDecisionContract` is the public final PASS / REVIEW contract. It must
be derived from the active `DetectionPolicy`; `policies/decision/overrides.py`
stores only final evidence thresholds that cannot be inferred directly from
runtime policy.

`x5crop.policies` ownership:

| Subpackage | Responsibility |
|---|---|
| `policies.formats` | Format-specific physical tolerance, content profile tolerance, and search-budget overrides. They must not declare scoring, gates, risks, detectors, diagnostics, or runtime presets. |
| `policies.parameters` | Numeric parameter objects, format parameter registry, and override ownership validation. |
| `policies.runtime` | Runtime `DetectionPolicy` and child policy dataclasses. |
| `policies.decision` | Final decision contract and narrow final evidence overrides. |
| `policies.assembly` | Builds runtime policy from format id, physical facts, constrained overrides, and profile defaults. |
| `policies.reporting` | Policy detail serialization for report visibility only. |
| `policies.registry` / `consistency` / `ids` | Public lookup, consistency smoke, schema id, and policy id. |

Parameters that affect final PASS / REVIEW must appear in report decision-policy
detail. Parameters that affect runtime detection paths must appear in runtime
policy detail.

### 6. Decision Authority

Automatic PASS requires:

- Candidate source allowed by the current format / mode policy.
- Separator, geometry, content, and outer evidence jointly support the candidate.
- Gate profile, partial-holder requirements, and mode-specific checks pass.
- Risk does not pull the candidate back to REVIEW.
- Final decision contract permits automatic export.

Conservative rules:

- Scores support gates; they do not replace gates.
- Scores should encode physical facts as numeric preference: stable photo image
  regions, explainable separators, and intact real content should score higher;
  separator width variation and safe empty frames must not be mistaken for photo
  size instability or content harm.
- Base confidence may only use separator/gap support and photo-width stability.
  Raw outer area and global contrast are diagnostics or final-contract inputs,
  not base confidence inputs.
- Support scores, gate support, risk credit, and width-instability risk may treat
  width CV as photo-size evidence only when the source is `photo_edges`;
  `frame_boxes` fallback is weak geometry detail.
- `photo_width_unstable` and final photo-width gates may consume only
  `photo_edges`; `frame_boxes` fallback cannot create a photo-width hard reason.
- Risk can pull to REVIEW or limit output, but it cannot rescue PASS.
- Weak grid, equal, content-only, safety, review-only, untrusted partial-edge, or
  evidence-dependency-cycle cases cannot gain automatic PASS authority.
- If a separator-derived outer relies on observed width-profile gaps, automatic
  PASS also requires independent standard hard-gap, content, and geometry validation.

### 7. Behaviors That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for `half/full`.
- `width_aware` is the only active separator gap profile; observed width is
  neutral measured-width evidence, not a broad-only profile.
- 120-66 broad-width, square-frame, separator-derived outer, and strict-holder
  risk modeling must be enabled by 120-66 policy only and must not become default
  behavior for other formats.
- 120-66 partial extra safety is holder-edge disambiguation: separator width
  evidence may be one disambiguating signal, but active gates / reasons should
  not treat "broad separator" as the only physical identity.
- Outer correction is a generic corrected-candidate capability; formats may tune
  physical parameters and gates, but must not own separate correction algorithm
  switches.
- Partial-holder policy may express richer holder safety requirements; strict
  defaults must not be promoted to half / xpan / 645.

### 8. Data And Report Contracts

- `CliOptions` records user options before file probing.
- `RuntimeConfig` records input, layout, and policy-bound runtime configuration.
- `Detection` is the stable detection-stage candidate result.
- `ProcessResult` is the stable input for report, debug, and export.
- Report rows must include top-level `version`, `policy_id`, and `report_schema`.
- V4.9 uses `v4_9_policy_schema_1` with evidence, risk, decision policy, and
  selected candidate detail.
- V4.5.4 / V4.7 reports are historical references, not mandatory 0-diff oracles.
  New wrong PASS is unacceptable; conservative REVIEW, schema diffs, and reason
  diffs require explanation.

### 9. Clean Editing Rules

- One concept may have only one long-term owner; compatibility adapters must be
  narrow, temporary, and easy to delete.
- New names must be semantic. Do not encode current responsibility with format
  numbers, version numbers, or historical implementation names.
- Version tags belong only in version constants, release history, artifact names,
  archive paths, and machine schema values.
- `pipeline.py`, `workflow.py`, `common.py`, and public re-exports should keep
  only necessary orchestration or compatibility surfaces; new implementation
  belongs in focused submodules.
- `ARCHITECTURE.md` keeps the current architecture contract only. Historical
  migration detail belongs in `CHANGELOG.md`; current handoff belongs in
  `AGENTS.md`.

### 10. Verification Gates

For documentation-only changes, run at least:

```bash
git diff --check
```

For source or policy changes, run at least:

```bash
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

If `tools/` is expanded, also compile `tools/regression/*.py`.

For detector behavior changes, use the reference classifier:

```bash
python3 -m tools.regression.reference_classify --candidate-root <root>
```

Core fields:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

Key reference sets:

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

Acceptance centers on 0 `unacceptable_wrong_pass` and 0 unexplained
`risky_regression`.
