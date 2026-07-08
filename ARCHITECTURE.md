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
| Runtime decision policy | `policies.runtime.decision` | decision 前置证据、confidence cap 和 low-confidence context review reasons。 |
| Final decision contract | `x5crop.policies.decision` | final PASS / REVIEW 门槛从 active runtime policy 派生，只保留少量不可推导 override。 |
| Foundation capability | `x5crop.geometry` / `x5crop.image` / `x5crop.io` | 只提供 box、gap、profile、deskew、pixel transform、TIFF I/O 等能力。 |
| Cache adapters | `x5crop.cache` | 只复用 analysis、profile、evidence 结果，不生成候选或决策。 |
| Detection behavior | `x5crop.detection` | 生成候选、证据、assessment、selection、decision 和 finalization。 |
| Output geometry | `x5crop.output` | output bleed 参数转换、overlap 输出风险读模型和缓存输出几何恢复。 |
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
| `detection.final` | 消费 `x5crop.output` bleed helper，执行 approved geometry adjustment 和 read-only diagnostics attachment。 |

关键审核点：

- outer 和 separator 是 physical structure；content 是 guidance + evidence。
- content 可提示 search center，可生成 content-model proposal；content candidate 的 confidence、
  diagnostics 和 internal `candidate_reasons` read model 属于 candidate assessment。
  content 不能生成 hard gap、不能直接修 physical result、不能决定 PASS / REVIEW。
- build 只生成未评分 Detection；assessment 和 decision 才消费证据。
- `candidate_build` detail 只描述物理 build geometry；base scoring 是否应用写在
  `base_candidate_scoring`，不能反写到 build detail。
- base scoring 输出使用显式 `BaseDetectionAssessment`，字段为 `confidence`、
  `candidate_reason_codes` 和 `detail`；不能用匿名 tuple 解包来传递 assessment 契约。
- content candidate assessment 输出使用显式 `ContentCandidateAssessment`，字段为
  `confidence`、`diagnostics` 和 `detail`；content diagnostics 仍是候选级解释。
- separator gate 输出使用显式 `SeparatorGateResult`，字段为 `ok` 和 `detail`；
  调用方不能用匿名 tuple 解包 gate 契约。
- separator gate 内部 profile / supplemental support checks 输出使用显式
  `SeparatorGateSupportAssessment`，字段为 `ok` 和 `reason`；内部 helper 也不能
  用匿名 ok/reason tuple 表达 gate 支持契约。
- gate check 使用统一 `GateCheck`，字段为 `code`、`stage`、`bucket`、
  `passed`、`severity`、`signal` 和 `detail`；低层 signal 不直接伪装成最终
  REVIEW reason。
- candidate gate 输出使用显式 `CandidateGateAssessment`，字段为 `passed`、
  `checks`、`blockers`、`diagnostics` 和 `confidence_caps`；`blockers` 只能从
  failed required gate checks 派生，不能维护独立 blocker 词表。
- candidate assessment 的 reason 只能作为候选 blockers / diagnostics；最终用户可见
  `review_reasons` 只由 decision contract 生成。
- `candidate_assessment.gate` 是候选资格的唯一结构化来源；候选级 failed
  gate 结果写作 `candidate_gate_failed`，不能回塞进 `candidate_reasons` 或独立
  blocker 词表。
- decision 的 `candidate_reason_inputs_before_decision` 只保留候选 blockers /
  diagnostics 作为主模型；旧 reason 归并读模型必须显式命名为
  `legacy_reduced_candidate_reasons`。
- low-confidence context reasons，例如 outer candidate disagreement 和 deskew uncertainty，
  属于 decision contract input；不能在 `final_decision` 中事后补写 `decision_summary`。
- decision gate 输出使用显式 `DecisionGateAssessment`，字段为 `passed`、
  `checks`、`final_review_reasons`、`reason_inputs` 和 `confidence_caps`；最终
  REVIEW reason 只能从这个结构产生。
- final review reasons 只能由 decision contract 一次性 set；decision layer 不保留
  add/append-style final reason helper。
- policy / report 可见的 gate stage 名必须使用 `candidate_gate` 和
  `decision_gate` 这类职责名，不能把 finalization 写成裁决 gate。
- candidate / mode 候选阶段读取或更新候选级原因必须经过
  `detection.candidate.reasons`，并写入 `Detection.detail["candidate_reasons"]`；
  candidate / mode 子层不能把候选原因写进 `Detection.review_reasons`。
  candidate reason reader 不 fallback 到 `Detection.review_reasons`；`Detection.review_reasons`
  只用于 decision 之后的最终用户可见原因。
- `content_only_evidence` 只表示 candidate source 主要依赖 content；content containment /
  content harm 失败使用 `content_evidence_insufficient`，不能复用 content-only reason。
- decision `risk_summary.candidate_source_detail` 同时记录 `candidate_assessment.source`
  和顶层 `candidate_source`；content-only risk 读取候选评估来源，safety / review-only
  risk 读取对应候选来源，不能再混成一个模糊 source。
- decision `evidence_summary.content` 中，`content_score_role` 表示 content containment
  support；`content_quality_score_role` 只表示 quality diagnostic，不是 hard gate。
- `overlap_risk` 和 `lucky_pass_risk` 是不同 final risk reason：前者来自 overlap /
  output-bleed 物理诊断，后者来自证据组合可能侥幸通过的 decision risk。两者不能互相借名。
- candidate selection 只能记录 `selection_risk_inputs`、selection override 和 competition
  detail；它不能提前追加 final-looking review reason，也不能提前执行 decision cap。
- content mismatch selector 属于 candidate selection；它只能读取 candidate-level
  diagnostics / blockers 并选择更可信的候选，不能命名为 review policy 或生成最终
  review reason。
- content-model proposal 的 contract 使用 `content_guidance_assessment_required` 这类
  guidance / assessment 语义；不能把 content proposal 命名成 review-only 裁决。
- content candidate assessment 里的 content-run / grid-fallback / aspect observations
  叫 diagnostics；它们可以进入 internal `candidate_reasons` read model，但不能用
  `content_candidate_*_reasons` 这类 final-looking 命名。
- dual-lane lane content / outer-alignment checks 属于 `candidate.assessment`；`candidate.plan`
  只选择 lane candidate 并调用 assessment helper；lane candidate 限分写入
  `candidate_confidence_caps`。
- safety candidate 的 auto-pass blocker、candidate cap 和 auto-gate 改写属于
  `candidate.assessment`；`candidate.plan` 只生成 safety candidate 并调用 assessment helper。
  最终 REVIEW 原因由 decision risk summary 根据 safety candidate source 生成。
- candidate table / selected candidate 的候选级原因字段使用 `candidate_reasons`、
  `candidate_blockers` 和 `candidate_diagnostics`；最终原因字段使用 `final_review_reasons`。
- candidate plan / execution budget 的可靠性细节也使用 `candidate_reasons` 和
  `candidate_reasons_ok`；不把候选级阻断条件写成 final-looking `review_reasons`。
- special mode detail 使用 `mode_diagnostics` 和 `candidate_reasons` 记录模式级诊断；
  不在 mode detail 中输出 final-looking `review_reasons` 字段。
  review-only mode 也不在构造出的 `Detection.review_reasons` 写最终 reason；
  它只写 candidate / mode diagnostics，最终 REVIEW 原因由 decision contract 生成。
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
- finalization 不生成候选、不评分、不决定 PASS / REVIEW；它只消费 decision 结果并调用
  `x5crop.output` 做输出相邻调整。
- `x5crop.output` 是 output-adjacent read/apply helper；它可以读取已存在的 risk /
  decision detail 来计算 output bleed，但不能生成新的 PASS / REVIEW 输入。
- `detection.final` 接收 workflow 已选定的 runtime policy；它不能自行查 policy registry
  或重新解释 format / mode。
- report / debug / export 是 output read-model；它们只能消费 `ProcessResult` 或
  `decision_summary.status`，不能根据 confidence / review reason 自行推导最终状态。
  裸 Detection 若还没有 decision summary，报告和 Debug Analysis 必须显示 `unknown` /
  `UNKNOWN`。
- report schema 必须显式输出 `evidence`、`gates`、`evidence_summary` 和
  `risk_summary`；构造出的审核 section 不能只停留在内部临时字典里。
- report schema 的 risk / deskew 可见细节属于 `diagnostics` section，不挂在
  `finalization` 名下；finalization 这个词只保留给输出相邻几何和 bleed 调整。
- `Detection.detail` 的稳定读取 helper 属于 `detection.detail`，根包不承载 report/debug read-model。
- report、debug、export 和 finalization 的输出面读取最终 reason 时必须通过
  `final_review_reasons_from_detail()`，优先使用 `decision_summary.final_review_reasons`，
  裸 Detection 才 fallback 到 `Detection.review_reasons`。
- active detail 使用 `primary`、`extension`、`supplemental`、`nearby_separator_refinement`
  等职责命名，不用 `late` / `auxiliary` 表达含糊流程阶段。
- candidate / report 可见的 gap 搜索详情只使用 `gap_search_profile`；
  `separator_width_profile` 只保留给底层几何宽度计算语义，不作为 runtime detail 别名。

### 6. Scoring / Gate 视角

分数是证据排序和 gate 支持，不是最终裁决本身：

- `assessment.scoring` 只计算 support scores 和 joint score。
- `assessment.base_scoring` 负责 base confidence 和候选级 `candidate_reason_codes`。
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
- `candidate_assessment.gate`、`candidate_assessment.blockers` 和
  `candidate_assessment.diagnostics` 是 report/debug 的候选级解释，不是最终裁决。
- `candidate_gate_failed` 是 gate 结果，不是候选物理证据；它只能出现在 gate /
  confidence-cap detail 或 decision reason input，不能作为 candidate reason 存储。
- `legacy_reduced_candidate_reasons` 只是旧候选原因的 internal/read-model reducer；
  不能作为 candidate assessment 或 final review reason 的主要业务字段。
- candidate gate 的 blockers 从 `GateCheck` 派生；通用 `utils` 不承载
  candidate-specific blocker list，也不用 hard review reason 命名。
- candidate 级可见字段必须写 `candidate_gate_*`；不能用 `auto_pass_*` 表达候选资格，
  因为最终 PASS 只属于 decision contract。
- read-only diagnostics 用 `effects` 结构声明 output / confidence / decision 副作用；
  不在低层 detail 中使用 `changes_final_decision` 这类 final-looking 字段。
- read-only diagnostics 的风险观察使用 evidence 命名，例如 `single_anchor_evidence_risk`；
  不能用 `pass` 表达最终裁决风险，最终 PASS / REVIEW 只属于 decision contract。
- candidate-plan policy 中阻断 candidate auto gate 的字段必须叫 blocker，不叫 review
  reason；final review reason 只属于 decision contract。
- candidate-plan detail 中 gap search family 只用 `gap_search_profiles` 表达；旧
  `gap_profiles` 别名不再作为 runtime/report 可见字段出现。
- content-only、safety 和 review-only candidate 是否进入最终 REVIEW 由 source-derived
  `risk_summary` 和 decision contract applier 表达；decision policy 不保留未被裁决消费的
  review-only 布尔开关。
- decision contract 只承载 format/mode、evidence、risk 和 PASS / REVIEW decision
  参数；output bleed、debug panels 和 report sections 留在 runtime output /
  diagnostics / report policy，不挂在 decision contract 下。
- `selection_risk_inputs` 是候选竞争阶段的风险证据，不是最终裁决；只有 decision 可以把它
  映射为 `candidate_competition_close`。
- overlap / lucky-pass 这类 final risk evidence 必须在 decision 阶段生成；finalization
  只能消费已有 risk detail 做 output bleed，不能在 PASS / REVIEW 之后补充裁决输入。
- `decision_reason_inputs`、`decision_generated_review_reasons` 和 `final_review_reasons` 是最终
  PASS / REVIEW 的解释入口；low-confidence context reason 也必须进入这些 final summary 字段。
- decision 子层读取或更新最终原因必须经过 `detection.decision.reasons`；`review_reasons`
  字段在 decision 后才是用户可见 final reason，不允许绕过 helper 直接追加。
- `approved_auto` 必须同时满足 confidence 达到阈值且 `final_review_reasons` 为空；
  workflow / finalization 不能只根据 confidence 推导最终状态。

字段命名必须反映物理语义。`width_cv` 只能作为 generic diagnostic 或 separator / gap
几何测量；照片宽度证据使用 `photo_width_*`。

### 7. Policy 视角

format fact、runtime capability 和 final decision 必须分开：

| 子包 | 内容 |
|---|---|
| `policies.formats` | format-specific physical tolerance、content profile tolerance 和 search budget overrides。 |
| `policies.parameters` | 数值参数对象、format parameter registry 和 override ownership validation。 |
| `policies.runtime` | runtime `DetectionPolicy` 和子 policy dataclass，包括 candidate / risk / decision / finalization / output / diagnostics / report。 |
| `policies.assembly` | 从 format facts、受限 overrides 和 profile defaults 组装 active runtime policy。 |
| `policies.decision` | final PASS / REVIEW decision contract 和少量 final evidence overrides。 |
| `policies.reporting` | policy detail serialization；只负责报告可见性。 |
| `policies.registry` / `consistency` / `ids` | lookup、consistency smoke、policy id 和 schema id。 |

format 文件不能声明 scoring、gate、risk、detector、diagnostics 或 runtime preset。影响
final PASS / REVIEW 的参数必须进入 decision policy detail；影响 runtime 检测路径但不直接
决定 PASS / REVIEW 的参数必须进入 runtime policy detail。`finalization` policy 只保留最终
输出前的 approved geometry adjustment / attachment 开关；runtime output policy 拥有 output
bleed 的执行开关、detection bleed、output bleed 和 edge-bleed protection。runtime risk
policy 只保留生成 final risk evidence 的参数；diagnostics policy 与 report policy 单独装配，
confidence cap 和 review reason 不属于 finalization。
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
Build creates unscored detections. `candidate_build` detail describes only the
physical build geometry; base scoring state belongs to `base_candidate_scoring`.
Assessment and decision consume evidence.
Corrected candidates must be rebuilt, reassessed, and returned to the shared
candidate pool before selection.

`detection.modes` routes special modes only. For dual-lane full strips, modes
split and merge lanes, while lane candidate build / assessment / selection lives
in `detection.candidate.plan`. `detection.evidence` produces and summarizes
evidence only; reading `candidate_assessment` is a decision or report read-model
concern. Candidate assessment reasons are candidate blockers / diagnostics only;
final user-visible `review_reasons` are generated by the decision contract.
Base scoring returns an explicit `BaseDetectionAssessment` result with
`confidence`, `candidate_reason_codes`, and `detail` fields; callers must not
depend on anonymous tuple positions for the assessment contract.
Content candidate assessment returns an explicit `ContentCandidateAssessment`
result with `confidence`, `diagnostics`, and `detail` fields; content
diagnostics remain candidate-level explanations.
Separator gate assessment returns an explicit `SeparatorGateResult` with `ok`
and `detail` fields; callers must not depend on anonymous tuple positions for
the gate contract.
Internal separator-gate profile and supplemental support checks return an
explicit `SeparatorGateSupportAssessment` with `ok` and `reason` fields; helper
functions must not encode gate-support contracts as anonymous ok/reason tuples.
Gate checks use a shared `GateCheck` shape with `code`, `stage`, `bucket`,
`passed`, `severity`, `signal`, and `detail` fields; low-level signals must not
pretend to be final REVIEW reasons.
Candidate gate assessment returns an explicit `CandidateGateAssessment` with
`passed`, `checks`, `blockers`, `diagnostics`, and `confidence_caps` fields;
blockers are derived from failed required gate checks, not from an independent
blocker vocabulary.
`candidate_reason_inputs_before_decision` keeps blockers / diagnostics as the
main model; the old reason-reduction read model must be named
`legacy_reduced_candidate_reasons`.
Decision gate assessment returns an explicit `DecisionGateAssessment` with
`passed`, `checks`, `final_review_reasons`, `reason_inputs`, and
`confidence_caps` fields; final REVIEW reasons are generated only from this
structure.
Policy/report-visible gate stage names use `candidate_gate` and
`decision_gate`; finalization must not be named as a decision gate.
Candidate and mode-stage code must read or update candidate-level reasons
through `detection.candidate.reasons`; the underlying
`Detection.detail["candidate_reasons"]` field stores candidate-level reasons.
Candidate and mode sublayers must not write those candidate reasons into
`Detection.review_reasons`, and candidate reason readers do not fall back to it.
`Detection.review_reasons` is reserved for final user-visible reasons after the
decision step.
Candidate selection records `selection_risk_inputs`, selection override, and
competition detail only; it must not append final-looking review reasons or apply
decision caps. The content mismatch selector is a candidate-selection rule: it
reads candidate-level diagnostics / blockers and may choose a more credible
candidate, but it is not a review policy and does not create final review
reasons. `content_only_evidence` means the candidate source relies mainly on
content; failed content containment or content-harm checks use
`content_evidence_insufficient` instead. Decision risk summaries expose
`candidate_source_detail` with both `candidate_assessment.source` and top-level
`candidate_source`, so content-only risk and safety / review-only risk keep
separate source ownership. Decision content summaries use `content_score_role`
for content-containment support and `content_quality_score_role` for quality
diagnostics, which are not hard gates. Content-model proposal contracts use
guidance / assessment language such as
`content_guidance_assessment_required`; they are not named as review-only
decisions. Content-candidate assessment observations use diagnostic naming for
content-run, grid-fallback, and aspect details; `content_candidate_*_reasons`
is not an active naming pattern. Dual-lane lane
content / outer-alignment checks belong to
`candidate.assessment`; `candidate.plan` selects lane candidates and calls the
assessment helper. Lane-candidate caps are recorded in
`candidate_confidence_caps`. Safety-candidate auto-pass blocker, candidate cap,
and auto-gate rewrite also belong to `candidate.assessment`; `candidate.plan`
only builds the safety candidate and calls the assessment helper. Final REVIEW
reasons are generated by decision risk summary from the safety-candidate source.
Candidate table
/ selected-candidate detail uses
`candidate_reasons`, `candidate_blockers`, and `candidate_diagnostics` for
candidate-level explanations. Candidate plan / execution-budget detail also uses
`candidate_reasons` and `candidate_reasons_ok`, not final-looking
`review_reasons`. Special-mode detail uses `mode_diagnostics` and
`candidate_reasons`. Review-only mode also leaves `Detection.review_reasons`
empty at construction time; it records candidate / mode diagnostics and lets the
decision contract generate the final REVIEW reasons. Final reasons use
`final_review_reasons`.
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
review reasons, and PASS / REVIEW. `x5crop.output` owns output-bleed parameter
conversion, output-risk read models, and cached output-geometry restoration.
`detection.final` consumes the decision result and `x5crop.output` helpers for
approved geometry adjustment, output-adjacent bleed adjustment, and read-only
diagnostics only. It receives the runtime policy selected by workflow instead
of looking up policy registry itself.
`approved_auto` requires both threshold-level confidence and empty final review
reasons; workflow and finalization must not derive final status from confidence
alone.
Report, debug, and export are output read-models: they consume `ProcessResult`
or `decision_summary.status`, never infer final status from confidence or review
reasons. A bare Detection without decision summary is reported as `unknown` /
`UNKNOWN`. Report schema must expose `evidence`, `gates`, `evidence_summary`,
and `risk_summary`; constructed audit sections must not remain hidden internal
dictionaries. Report-visible risk / deskew details live under `diagnostics`, not
a `finalization` section.
Stable `Detection.detail` readers live in `detection.detail`, not the root
package. Output-facing report/debug/export/finalization code reads final reasons
through `final_review_reasons_from_detail()`, preferring
`decision_summary.final_review_reasons` and falling back to
`Detection.review_reasons` only for bare detections.
Candidate/report-visible gap-search detail uses `gap_search_profile` only;
`separator_width_profile` is reserved for low-level width-profile geometry, not
as a runtime-detail alias.

### 6. Scoring / Gate Perspective

Scores rank and support evidence; they are not the final decision. Base
scoring owns base confidence and candidate-level `candidate_reason_codes`.
Base confidence uses separator / gap support and `photo_width_cv`. Raw outer area,
global contrast, frame-box width, and separator-width variation remain diagnostic
or final-decision inputs. Content support means containment; content quality
means evidence strength. Photo-width hard reasons may consume only
`photo_edges`-sourced `photo_width_cv`. Candidate blockers, diagnostics,
auto-gate inputs, and candidate confidence caps are assessment detail; decision
reason inputs, final-review reason fields, and decision confidence caps are
final decision detail. `legacy_reduced_candidate_reasons` is only an
internal/read-model reducer for old candidate reason names, not the primary
candidate-assessment or final-review reason field. Content-only, safety, and
review-only candidate outcomes
are expressed by source-derived `risk_summary` plus the decision contract
applier, not by unused review-only flags in decision policy.
The decision contract carries only format/mode, evidence, risk, and PASS /
REVIEW decision parameters; output bleed, debug panels, and report sections
remain in runtime output / diagnostics / report policy instead of decision
contract.
Candidate gate blockers are derived from `GateCheck` results, not stored in a
generic utility vocabulary, and must not be named as hard review reasons.
Candidate-visible fields use `candidate_gate_*`; they must not use
`auto_pass_*` for candidate eligibility because final PASS belongs only to the
decision contract.
Read-only diagnostics use an `effects` object for output / confidence /
decision side effects; low-level detail must not use final-looking fields such
as `changes_final_decision`.
Candidate-plan policy fields that contribute candidate gate signals use signal
naming, not review-reason naming; final review reasons belong only to the
decision contract.
Candidate-plan detail exposes gap search families only as `gap_search_profiles`;
the old `gap_profiles` alias is not a runtime/report field.
Final risk evidence such as overlap and lucky-pass risk is attached before the
final decision. `x5crop.output` and finalization may consume that detail for
output bleed, but must not generate PASS / REVIEW inputs after the decision
step.
Decision sublayers must read or update final reasons through
`detection.decision.reasons`; after the decision step, `review_reasons` is the
user-visible final reason field, so decision code must not append to it directly.

### 7. Policy Perspective

Format facts, runtime capability, runtime risk policy, runtime decision policy,
and final decision contract remain separate.
Format files may provide physical tolerance, content profile tolerance, and
search-budget overrides only. Runtime path parameters must appear in runtime
policy detail; final PASS / REVIEW parameters must appear in decision policy
detail. Finalization policy owns approved geometry adjustment / attachment
switches before export; runtime output policy owns the output-bleed execution
switch, detection bleed, output bleed, and edge-bleed protection. Runtime risk
policy only owns parameters for final risk evidence. Diagnostics and report
policies are assembled separately. The only policy-construction entry in a
format module is `build_policy(strip_mode)`;
mode-specific convenience helpers such as `full_policy()` / `partial_policy()`
are not kept.

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
