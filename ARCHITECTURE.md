# X5 Crop 架构说明 / Architecture Guide

本文件是源码审核视角地图。它说明从不同角度审查代码时，项目应呈现什么结构、哪些层级
拥有事实和决策、哪些差异只是审查线索。用户说明见 `README.md`；版本记录见
`CHANGELOG.md`；Codex 协作和 handoff 见 `AGENTS.md`。

This file is a source-audit perspective map. It describes what the project should
look like from each review angle, which layers own facts and decisions, and which
diffs are audit evidence rather than blockers. Usage lives in `README.md`;
version history lives in `CHANGELOG.md`; Codex coordination and handoff live in
`AGENTS.md`.

## 中文说明

### 1. 文档视角

根目录文档是一组不重叠的工作表面：

| 文档 | 内容 |
|---|---|
| `快速启动_Quick_Start.md` | Release 用户的最短安装、摆放、启动和输出说明。 |
| `README.md` | 完整用户手册：下载、依赖、启动器、format、partial、Debug Analysis、输出、命令行和卸载。 |
| `ARCHITECTURE.md` | 源码审核视角、层级边界、policy 所有权、format / mode 组合和验证边界。 |
| `CHANGELOG.md` | 版本级变化、验证记录、发布策略和回滚线索。 |
| `AGENTS.md` | Codex 规则、当前 handoff、同步要求和仓库级约束。 |

`README.md` 不放文档分工或内部架构说明。`ARCHITECTURE.md` 不放版本流水和长 handoff。
仓库不维护 `docs/` 镜像。

### 2. 入口和运行视角

项目运行时应呈现为一条明确的数据流：

```text
X5_Crop.py / launchers
  -> entry options
  -> runtime config and input probe
  -> workflow
  -> detection
  -> decision
  -> finalization
  -> export / report / debug
```

| 层级 | 审核时应看到的职责 |
|---|---|
| `X5_Crop.py` | 开发入口；Release 构建生成 standalone 单文件。 |
| `x5crop.entry` | CLI 和交互入口，只生成入口选项。 |
| `x5crop.runtime.config` | 将入口选项、输入、layout 和 policy 绑定成 `RuntimeConfig`。 |
| `x5crop.runtime.input_probe` / `runtime.app` | 探测 TIFF、解析 layout、打印启动摘要、调度 worker。 |
| `x5crop.runtime.workflow` | 单图编排 read -> preprocess -> detect -> decision -> finalization -> export/report/debug。 |
| launchers | 只负责找到 Python、进入交互流程或 diagnostics 流程。 |

入口不拥有检测策略；workflow 不承载 format-specific 实现。

### 3. Source Ownership 视角

每类知识只有一个长期 owner：

| 领域 | Owner | 项目形态 |
|---|---|---|
| Format facts | `x5crop.formats` | format identity、family、count、aspect 和物理事实集中定义。 |
| Runtime policy | `x5crop.policies.runtime` / `policies.assembly` | format / mode 行为由 policy profile 和 assembly 显式生成。 |
| Runtime decision policy | `policies.runtime.decision` | decision 前置证据、confidence cap 和 tail review reasons。 |
| Final decision contract | `x5crop.policies.decision` | final PASS / REVIEW 门槛从 active runtime policy 派生，只保留少量不可推导 override。 |
| Foundation capability | `x5crop.geometry` / `x5crop.image` / `x5crop.io` | 只提供 box、gap、profile、deskew、pixel transform、TIFF I/O 等能力。 |
| Cache adapters | `x5crop.cache` | 只复用 analysis、profile、evidence 结果，不生成候选或决策。 |
| Detection behavior | `x5crop.detection` | 生成候选、证据、assessment、selection、decision 和 finalization。 |
| Output surfaces | `x5crop.export` / `x5crop.report` / `x5crop.debug` | 消费稳定结果，不反向参与候选选择。 |
| Developer tools | `tools/` | standalone build、reference compare、classification 和 unit tests；不进入 runtime package。 |

基础层审核规则：

- `geometry` / `image` / `io` 不反向依赖 runtime、workflow、detection、debug、report 或
  policy registry。
- 基础层不读取 `Detection.detail`、risk detail 或 PASS / REVIEW 语义。
- 基础层不接收 `strip_mode` 字符串；上层先解析为普通参数对象。
- cache key 只包含实际影响计算的输入和参数，不用 format 名称替代参数所有权。

### 4. Physical Model 视角

项目处理的是片夹、照片 footprint、separator 和真实影像内容之间的关系：

- outer 是片夹白边到照片 footprint 的边界；footprint 内侧可以是黑边，也可以直接是真实图像。
- 黑边只是 side evidence，不是 outer 的定义。
- separator 是照片之间的物理间隔；`detected` / `edge-pair` 是 hard gap，`grid` /
  `equal` / `content` 是 model gap。
- `width_aware` 是唯一 active separator gap profile。observed width 是中性实测宽度证据，
  可以比理论均匀宽度更窄、相近或更宽。
- 照片影像区域尺寸一致是强结构事实；separator 宽度可变只是 observed detail。
- `detection.physical.photo_size` 是共享 photo-size consistency 模型；separator proposal、
  separator-derived outer 和 candidate assessment 不应各自发明宽度语义。
- full 和 partial 都允许安全多切空 frame；只要真实图像没有被切伤，空 frame 本身不是负面证据。
- TIFF metadata、位深、通道、ICC、resolution 和无损压缩行为属于输出质量边界，不随检测重构改变。

不要把 observed / broad separator width 当成新的 detector family，也不要把 frame-box
宽度或 separator 宽度误读成照片尺寸不稳。

### 5. Detection Lifecycle 视角

detection 是一张协同证据图：

```text
candidate plan
  -> physical proposals
  -> content guidance
  -> candidate build
  -> candidate assessment
  -> candidate extension
  -> candidate selection
  -> final decision
  -> finalization
```

| 子层 | 内容 |
|---|---|
| `detection.pipeline` | orchestration：候选计划、候选池、扩展和 selection。 |
| `detection.modes` | dual-lane、review-only 等 mode routing；dual-lane 只负责拆 lane 和合并 lane 结果。 |
| `detection.physical` | outer proposal / correction、separator proposal / model、photo-size model。 |
| `detection.guidance` | content outer hints、content separator hints 和 content-model proposal raw metrics。 |
| `detection.evidence` | separator、content、geometry、outer alignment、risk 和只读 diagnostics evidence；不读取 assessment。 |
| `detection.candidate.plan` | count、offset、candidate source、execution budget 和 dual-lane lane candidate lifecycle。 |
| `detection.candidate.build` | outer -> separator gaps -> frames -> unscored `Detection`。 |
| `detection.candidate.assessment` | base scoring、support scores、gate support、candidate blockers / diagnostics 和 auto gate。 |
| `detection.candidate.extension` | corrected outer、content-guided separator 等 reassessed candidates。 |
| `detection.candidate.selection` | 多候选竞争和 selected candidate。 |
| `detection.decision` | final evidence、confidence caps、risk summary、final review reasons 和 PASS / REVIEW。 |
| `detection.final` | output bleed、approved geometry adjustment 和 read-only diagnostics attachment。 |

关键审核点：

- outer 和 separator 是 physical structure；content 是 guidance + evidence。
- content 可提示 search center，可生成 content-model proposal；content candidate 的 confidence /
  review reasons 属于 candidate assessment。content 不能生成 hard gap、不能直接修 physical result、
  不能决定 PASS / REVIEW。
- build 只生成未评分 Detection；assessment 和 decision 才消费证据。
- candidate assessment 的 reason 只能作为候选 blockers / diagnostics；最终用户可见
  `review_reasons` 只由 decision contract 生成。
- candidate selection 只能记录 `selection_risk_inputs`、selection override 和 competition
  detail；它不能提前追加 final-looking review reason，也不能提前执行 decision cap。
- dual-lane lane content / outer-alignment checks 属于 `candidate.assessment`；`candidate.plan`
  只选择 lane candidate 并调用 assessment helper；lane candidate 限分写入
  `candidate_confidence_caps`。
- safety candidate 的 review-only contract、candidate cap 和 auto-gate 改写属于
  `candidate.assessment`；`candidate.plan` 只生成 safety candidate 并调用 assessment helper。
- candidate table / selected candidate 的候选级原因字段使用 `candidate_reasons`、
  `candidate_blockers` 和 `candidate_diagnostics`；最终原因字段使用 `final_review_reasons`。
- candidate plan / execution budget 的可靠性细节也使用 `candidate_reasons` 和
  `candidate_reasons_ok`；不把候选级阻断条件写成 final-looking `review_reasons`。
- special mode detail 使用 `mode_diagnostics` 和 `candidate_reasons` 记录模式级诊断；
  不在 mode detail 中输出 final-looking `review_reasons` 字段。
- close competition 的阈值只有一个来源：runtime candidate selection policy。decision
  contract 读取同一个阈值生成最终 `candidate_competition_close` reason 和 cap。
- guidance 和 candidate plan detail 只能写 `candidate_contract` / `evidence_contract` 这类
  源头契约；`decision_contract` 名称只属于 `policies.decision` 和 `detection.decision`。
- runtime 调用 decision 时直接 import owning module；`detection.decision.__init__` 只做 package marker。
- format 的 `known_physical_risks` 是 report/debug 可见描述；policy assembly 必须用
  family、count、aspect 等物理谓词推导参数，不能把 risk 字符串当能力开关。
- corrected candidate 必须重新 build、重新 assessment，再回到候选池统一 selection。
- physical correction 不读取 candidate assessment；是否尝试 correction 属于 candidate extension。
- physical 层不保留 `plan.py`；计划、execution budget 和候选 source 组合属于
  `detection.candidate.plan`。
- evidence 层只生成和汇总证据；从 `candidate_assessment` 读取 gate detail 属于 decision
  或 report/read-model。
- finalization 不生成候选、不评分、不决定 PASS / REVIEW；它只消费 decision 结果并做输出相邻调整。
- `Detection.detail` 的稳定读取 helper 属于 `detection.detail`，根包不承载 report/debug read-model。
- active detail 使用 `primary`、`extension`、`supplemental`、`nearby_separator_refinement`
  等职责命名，不用 `late` / `auxiliary` 表达含糊流程阶段。

### 6. Scoring / Gate 视角

分数是证据排序和 gate 支持，不是最终裁决本身：

- `assessment.scoring` 只计算 support scores 和 joint score。
- `assessment.base_scoring` 负责 base confidence 和 base review reasons。
- `assessment.gate_support` 负责 hard-full calibration 和 separator geometry support。
- base confidence 只由 separator / gap support 和 `photo_width_cv` 组成。
- raw outer area、global contrast、frame-box width 和 separator-width variation 是 diagnostics
  或 final decision 输入，不是 base confidence 输入。
- content support score 表示真实内容 containment support；content quality score 只表示影像证据强弱。
- 当 detail 明确给出 `content_containment_ok` / `content_harm_risk` 时，support score 只能消费
  containment 字段；旧 `support` summary 只是报告 detail。
- partial mode 本身不是低置信度原因。只有单张 partial 或 35mm 两张 partial 这类天然无法解释
  holder structure 的情况继续标记 `partial_too_ambiguous`。
- `photo_width_unstable` 和 final photo-width gate 只能消费 `photo_edges` 来源的
  `photo_width_cv`；`frame_boxes` measurement 不能生成照片宽度 hard reason。
- risk 只能拉回 REVIEW 或限制输出，不能救回 PASS。
- confidence cap 必须记录 owner、reason、cap value 和前后 confidence；candidate cap 和
  decision cap 分别归 assessment / decision。
- `candidate_assessment.blockers`、`candidate_assessment.diagnostics` 和
  `candidate_assessment.auto_gate_inputs` 是 report/debug 的候选级解释，不是最终裁决。
- `selection_risk_inputs` 是候选竞争阶段的风险证据，不是最终裁决；只有 decision 可以把它
  映射为 `candidate_competition_close`。
- `decision_reason_inputs`、`final_review_reasons_added` 和 `final_review_reasons` 是最终
  PASS / REVIEW 的解释入口；decision tail reason 也必须进入这些 final summary 字段。

字段命名必须反映物理语义。`width_cv` 只能作为 generic diagnostic 或 separator / gap
几何测量；照片宽度证据使用 `photo_width_*`。

### 7. Policy 视角

format fact、runtime capability 和 final decision 必须分开：

| 子包 | 内容 |
|---|---|
| `policies.formats` | format-specific physical tolerance、content profile tolerance 和 search budget overrides。 |
| `policies.parameters` | 数值参数对象、format parameter registry 和 override ownership validation。 |
| `policies.runtime` | runtime `DetectionPolicy` 和子 policy dataclass。 |
| `policies.assembly` | 从 format facts、受限 overrides 和 profile defaults 组装 active runtime policy。 |
| `policies.decision` | final PASS / REVIEW decision contract 和少量 final evidence overrides。 |
| `policies.reporting` | policy detail serialization；只负责报告可见性。 |
| `policies.registry` / `consistency` / `ids` | lookup、consistency smoke、policy id 和 schema id。 |

format 文件不能声明 scoring、gate、risk、detector、diagnostics 或 runtime preset。影响
final PASS / REVIEW 的参数必须进入 decision policy detail；影响 runtime 检测路径但不直接
决定 PASS / REVIEW 的参数必须进入 runtime policy detail。`finalization` policy 只保留输出相邻
几何、bleed 和 diagnostics attachment；confidence cap 和 review reason 不属于 finalization。
format policy module 的唯一构建入口是 `build_policy(strip_mode)`；`full_policy()` /
`partial_policy()` 这类 mode-specific convenience helper 不再保留。

### 8. Format / Mode 组合视角

format / mode 不再被审核为互相隔离的行为围栏。当前代码更接近一组可组合的能力：
format 提供物理事实和参数范围，mode 提供执行姿态，policy assembly 决定能力如何启用，
evidence / decision 决定结果如何解释。

审核时应区分：

| 问题 | 应归属的层 |
|---|---|
| 这是什么片夹或画幅？ | `x5crop.formats` 的 physical facts。 |
| 这个能力是否可用？ | runtime policy capability。 |
| 这个 format / mode 默认怎样启用能力？ | policy assembly / preset。 |
| 这个能力如何计算证据？ | detection / geometry / image 的对应 owner。 |
| 这个证据如何影响结果？ | assessment、decision、risk 和 report detail。 |

当前审核口径：

- format 名称不是算法边界。看到 format 名称时，先判断它是物理事实、参数 override、
  preset 选择、report label，还是历史命名残留。
- 能力可以跨 format / mode 共享；关键是 owner、输入参数、启用条件和报告 detail 是否清楚。
- 旧的 “某能力只能属于某 format” 表述不再作为架构规则。它只能作为历史迁移线索。
- format-specific 数值应表达物理尺寸、容忍度、search budget 或证据解释，不应隐藏独立算法分支。
- mode-specific detector 应表达执行姿态，例如 standard、dual-lane、review-only，而不是把
  format 物理事实复制成第二套行为体系。
- 当一个能力从单一 format 推广为共享 capability，文档应记录新的 owner 和 policy
  enablement，而不是保留旧的 format 隔离语言。

### 9. Report / Debug 视角

report 和 debug 必须让人复盘为什么得到当前结果：

- `Detection` 是检测阶段的稳定候选结果。
- `ProcessResult` 是 report、debug 和 export 的稳定输入。
- report row 顶层包含 `version`、`policy_id` 和 `report_schema`。
- V4.9 report schema 包含 evidence、risk、decision policy 和 selected candidate detail。
- Debug Analysis 默认保持三联图；更细 evidence / gate / risk 信息进入 report detail。
- output surface 只解释和输出结果，不参与候选选择。

报告字段要说明 evidence 从哪里来、被谁消费、为什么通过或进入复核；不要把报告字段变成
新的运行逻辑。

### 10. Diff / Verification 视角

历史 reference 是审查材料，不是裁判。当前项目阶段允许任何历史 reference diff；
diff 本身不阻断验收，也不要求归类为错误。

应保留的做法：

- 用 reference reports 定位变化。
- 记录 material diff 的原因、涉及视角和后续检查点。
- 区分 source cleanup、policy 变化、report schema 变化、metadata 变化和输出行为变化。
- 对检测行为变更运行 reference classifier 或 raw compare，以便知道变化在哪里。

不再使用的做法：

- 不要求 V4.5.4 / V4.7 0 diff。
- 不把 `status`、`confidence`、`review_reasons`、`outer_box`、`frame_boxes`、`gaps` 等字段
  单独设为历史一致性保护字段。
- 不把旧分类标签作为历史 reference diff 的阻断条件。
- 不用旧 baseline 决定当前 architecture 是否正确。

文档-only 变更至少运行：

```bash
git diff --check
```

源码或 policy 变更至少运行：

```bash
python3 -m unittest discover -s tools/tests
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

同时编译 `tools/regression/*.py`。

## English Guide

### 1. Documentation Perspective

Root documentation has non-overlapping roles:

| Document | Content |
|---|---|
| `快速启动_Quick_Start.md` | Short Release-user install, placement, launch, and output guide. |
| `README.md` | Complete user manual: download, dependencies, launchers, formats, partial mode, Debug Analysis, output, CLI, uninstall. |
| `ARCHITECTURE.md` | Source-audit perspectives, layer boundaries, policy ownership, format / mode composition, and verification boundaries. |
| `CHANGELOG.md` | Version-level changes, validation records, release policy, and rollback context. |
| `AGENTS.md` | Codex rules, current handoff, sync requirements, and repository constraints. |

`README.md` should not contain document-role maps or internal architecture notes.
`ARCHITECTURE.md` should not contain version logs or long handoffs. The repository
does not keep a `docs/` mirror.

### 2. Entry And Runtime Perspective

Runtime should read as one explicit flow:

```text
X5_Crop.py / launchers
  -> entry options
  -> runtime config and input probe
  -> workflow
  -> detection
  -> decision
  -> finalization
  -> export / report / debug
```

Entry code does not own detection policy. Workflow orchestrates work and should
not become the home for format-specific implementation.

### 3. Source Ownership Perspective

Each kind of knowledge has one long-term owner: `formats` owns physical facts,
`policies` owns runtime and decision policy, foundation layers own pure
capability, `cache` owns reuse adapters, `detection` owns candidates and
decisions, and output surfaces consume stable results only.

Foundation layers must not depend back on runtime, workflow, detection, debug,
report, or the policy registry; must not read `Detection.detail`; and must not
receive `strip_mode` strings.

### 4. Physical Model Perspective

The physical model is the relationship among holder, photo footprint, separator,
and real image content:

- Outer is the holder-to-photo-footprint boundary; black rim is side evidence,
  not the definition of outer.
- Separator is the physical space between photos. `detected` / `edge-pair` are
  hard gaps; `grid` / `equal` / `content` are model gaps.
- `width_aware` is the only active separator gap profile. Observed width is
  neutral measured evidence and may be narrower than, similar to, or wider than
  theoretical even spacing.
- Consistent photo image-region size is strong structure; separator width
  variation is observed detail.
- Safe empty frames are acceptable when real image content is not harmed.
- TIFF quality attributes are output boundaries and must not change during
  detection refactors.

### 5. Detection Lifecycle Perspective

Detection is a cooperative evidence graph:

```text
candidate plan
  -> physical proposals
  -> content guidance
  -> candidate build
  -> candidate assessment
  -> candidate extension
  -> candidate selection
  -> final decision
  -> finalization
```

Outer and separator are physical structure; content is guidance plus evidence.
Build creates unscored detections. Assessment and decision consume evidence.
Corrected candidates must be rebuilt, reassessed, and returned to the shared
candidate pool before selection.

`detection.modes` routes special modes only. For dual-lane full strips, modes
split and merge lanes, while lane candidate build / assessment / selection lives
in `detection.candidate.plan`. `detection.evidence` produces and summarizes
evidence only; reading `candidate_assessment` is a decision or report read-model
concern. Candidate assessment reasons are candidate blockers / diagnostics only;
final user-visible `review_reasons` are generated by the decision contract.
Candidate selection records `selection_risk_inputs`, selection override, and
competition detail only; it must not append final-looking review reasons or apply
decision caps. Dual-lane lane content / outer-alignment checks belong to
`candidate.assessment`; `candidate.plan` selects lane candidates and calls the
assessment helper. Lane-candidate caps are recorded in
`candidate_confidence_caps`. Safety-candidate review-only contract, candidate
cap, and auto-gate rewrite also belong to `candidate.assessment`; `candidate.plan`
only builds the safety candidate and calls the assessment helper. Candidate table
/ selected-candidate detail uses
`candidate_reasons`, `candidate_blockers`, and `candidate_diagnostics` for
candidate-level explanations. Candidate plan / execution-budget detail also uses
`candidate_reasons` and `candidate_reasons_ok`, not final-looking
`review_reasons`. Special-mode detail uses `mode_diagnostics` and
`candidate_reasons`. Final reasons use `final_review_reasons`.
Close-competition uses one threshold source: the runtime candidate selection
policy, which the decision contract consumes to produce the final
`candidate_competition_close` reason and cap.
Guidance and candidate-plan detail may use `candidate_contract` or
`evidence_contract`; `decision_contract` naming belongs only to decision policy
and decision execution. Runtime callers import decision owning modules directly;
`detection.decision.__init__` remains a package marker only.
Format `known_physical_risks` are report/debug descriptors only; policy assembly
derives parameters from physical predicates such as family, count, and aspect,
not from risk strings.
Physical packages do not keep `plan.py`; planning, execution budget, and source
composition belong to `detection.candidate.plan`.
`detection.decision` owns final evidence, confidence caps, risk summary, final
review reasons, and PASS / REVIEW. `detection.final` consumes that result
for output bleed, approved geometry adjustment, and read-only diagnostics only.
Stable `Detection.detail` readers live in `detection.detail`, not the root
package.

### 6. Scoring / Gate Perspective

Scores rank and support evidence; they are not the final decision. Base
confidence uses separator / gap support and `photo_width_cv`. Raw outer area,
global contrast, frame-box width, and separator-width variation remain diagnostic
or final-decision inputs. Content support means containment; content quality
means evidence strength. Photo-width hard reasons may consume only
`photo_edges`-sourced `photo_width_cv`. Candidate blockers, diagnostics,
auto-gate inputs, and candidate confidence caps are assessment detail; decision
reason inputs, final-review reason fields, and decision confidence caps are
final decision detail.

### 7. Policy Perspective

Format facts, runtime capability, runtime decision policy, and final decision
contract remain separate.
Format files may provide physical tolerance, content profile tolerance, and
search-budget overrides only. Runtime path parameters must appear in runtime
policy detail; final PASS / REVIEW parameters must appear in decision policy
detail. Finalization policy is output-adjacent only. The only policy-construction
entry in a format module is `build_policy(strip_mode)`; mode-specific convenience
helpers such as `full_policy()` / `partial_policy()` are not kept.

### 8. Format / Mode Composition Perspective

Format / mode review is no longer a list of isolated behavior fences. The current
code is closer to composable capability: format supplies physical facts and
parameter ranges, mode supplies execution posture, policy assembly decides how
capabilities are enabled, and evidence / decision layers explain the result.

Review should separate:

| Question | Owning layer |
|---|---|
| What holder or frame family is this? | Physical facts in `x5crop.formats`. |
| Is this capability available? | Runtime policy capability. |
| How does this format / mode enable the capability by default? | Policy assembly / preset. |
| How is the evidence computed? | The relevant detection / geometry / image owner. |
| How does the evidence affect the result? | Assessment, decision, risk, and report detail. |

Current review stance:

- Format names are not algorithm boundaries. When a format name appears, first
  decide whether it is a physical fact, parameter override, preset choice,
  report label, or historical naming residue.
- Capabilities may be shared across formats and modes when owner, inputs,
  enablement, and report detail are explicit.
- Old statements that a capability can belong only to one format are historical
  migration clues, not architecture rules.
- Format-specific numbers should express physical size, tolerance, search budget,
  or evidence interpretation. They should not hide independent algorithm branches.
- Mode-specific detectors describe execution posture, such as standard,
  dual-lane, or review-only; they should not duplicate format physical facts as a
  second behavior system.
- When a capability moves from one format to a shared capability, documentation
  should record the new owner and policy enablement instead of preserving old
  isolation wording.

### 9. Report / Debug Perspective

Reports and Debug Analysis explain behavior without feeding back into candidate
selection. Report rows include `version`, `policy_id`, and `report_schema`; V4.9
detail exposes evidence, risk, decision policy, and selected candidate state.
Debug Analysis stays readable, while richer evidence belongs in report detail.

### 10. Diff / Verification Perspective

Historical references are review material, not judges. In the current project
phase, any historical reference diff can be accepted. A diff locates a change; it
does not block acceptance and does not need to be classified as an error.

Keep using reference reports to locate material changes and explain which audit
perspective they touch. Do not require V4.5.4 / V4.7 zero-diff parity, do not
protect core fields solely for historical parity, and do not use old baselines
to decide whether the current architecture is correct.

For documentation-only changes, run:

```bash
git diff --check
```

For source or policy changes, run:

```bash
python3 -m unittest discover -s tools/tests
python3 -m compileall -q X5_Crop.py x5crop
python3 -m x5crop.policies.consistency
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

Also compile `tools/regression/*.py`.
