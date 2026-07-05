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
- detection 生成证据、候选和候选选择；decision 子层裁定最终 PASS / REVIEW。
- geometry / image / io 提供底层能力，不拥有候选或决策语义。
- report / debug / export 只消费稳定结果，不反向参与候选选择。
- developer tools 位于 `tools/`，不进入 runtime package。

### 分层边界

| 层级 | 主要职责 |
|---|---|
| `X5_Crop.py` | 开发入口；Release 构建生成单文件发布版。 |
| `x5crop.entry` / `x5crop.runtime.config` | CLI 解析、入口参数契约、运行配置契约。 |
| `x5crop.entry.interactive` / launchers | 交互式菜单；平台启动器只负责找到 Python 并进入交互模式。 |
| `x5crop.runtime.input_probe` / `x5crop.runtime.app` | 输入 TIFF 探测、layout 解析、启动摘要、worker 调度。 |
| `x5crop.runtime.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug 编排。 |
| `x5crop.formats` | format identity、physical spec、count/aspect facts 和 CLI choices 的唯一入口。 |
| `x5crop.policies` | runtime policy、decision contract、format / mode presets、参数解析和 policy detail 序列化。 |
| `x5crop.cache` / `geometry` / `image` / `io` | analysis cache、box、gap、separator profile、deskew、pixel transform、TIFF I/O 等底层能力。 |
| `x5crop.detection` | detection pipeline、mode detector、candidate lifecycle / proposals、evidence、decision 和 finalization。 |
| `x5crop.runtime.analysis_reuse` / `x5crop.export` / `x5crop.report` / `x5crop.debug` | 历史结果复用、TIFF 输出、结果组装、报告 schema、报告写入和 Debug Analysis。 |
| `tools` | standalone build、reference compare、safety classification 等开发工具。 |

依赖方向应从入口和工作流流向基础层；基础层不得反向依赖 workflow、detection、
debug、report 或 policy registry。

### Detection 子层和运行流程

`workflow` 只编排 read -> preprocess -> detect -> finalize -> export/report/debug。
`x5crop.detection` 内部固定按下列职责分层：

| 子层 | 主要职责 |
|---|---|
| `detection.pipeline` | 构建候选计划、收集候选、触发候选扩展、统一 selection。 |
| `detection.modes` | dual-lane、review-only 等 mode-specific detector。 |
| `detection.candidate.plan` | count、offset、candidate source、execution budget。 |
| `detection.candidate.proposal` | outer、separator、content、safety、corrected outer 等 candidate proposal family；只提出候选输入或候选 evidence。 |
| `detection.candidate.build` | 将 proposal 变成 Detection：outer -> separator gap lifecycle -> frames。 |
| `detection.candidate.assessment` | scoring、gate、candidate-level review reasons 和 auto_gate。 |
| `detection.candidate.selection` | 多候选竞争并选择 best candidate。 |
| `detection.candidate.extension` | 将需要复评的 corrected proposal 追加回候选池；不直接 PASS / REVIEW。 |
| `detection.evidence` | separator、content、geometry、outer alignment、risk 等 evidence detail。 |
| `detection.decision` | final evidence summary、risk summary、PASS / REVIEW 和 reason normalization。 |
| `detection.final` | output bleed、approved geometry adjustment、read-only diagnostics attachment。 |

运行语义是：

```text
workflow
  read / preprocess / detect / finalize / export

detection pipeline
  build candidate plan
  build proposal set
  build detections from proposals
  assess candidates
  extend candidates when primary evidence is weak or conflict evidence appears
  select candidate

decision
  evidence summary
  review risk
  PASS / REVIEW

finalization
  output bleed
  approved geometry adjustment
  report/debug attachment
```

### 人工审核进度台账

本台账用于回顾已经从哪些视角审核过项目、形成了什么成果、还剩哪些逻辑族群未深审。
它记录人工审核进度，不替代版本历史；行为或源码变化仍记录在 `CHANGELOG.md`。

状态词：

- `完成`: 结构和逻辑都已审，并已实施必要清理。
- `结构完成，逻辑待审`: 边界已清理，但算法或规则还没有逐项审核。
- `进行中`: 当前正在人工审核。
- `未开始`: 尚未进入该族群。
- `持续复核`: 每次相关逻辑改动后都要回看。

#### 视角审核台账

| 视角/族群 | 我们问的问题 | 已做工作 | 成果 | 当前状态 | 下一步接点 |
|---|---|---|---|---|---|
| 源码结构视角 | 项目分哪些层，文件是否在正确位置？ | 重组 entry、runtime、cache、report、formats、policies 和 candidate 包。 | `entry/runtime/cache/report/formats/policies/candidate` 分层。 | 完成 | 只在新增层级时复核。 |
| 运行流程视角 | TIFF 从读取到输出如何流动？ | 明确 entry、runtime、workflow、detection、decision、finalization、export/report/debug 的顺序。 | `entry -> runtime -> workflow -> detection -> decision -> finalization -> export/report/debug`。 | 完成 | 行为链路变化时更新流程图。 |
| 极致干净视角 | 是否有跨层依赖、旧文件、漏网文件或语义残留？ | 多轮检查未使用文件、层级漏网、foundation coupling 和文档一致性。 | 基础层不反向依赖 runtime、policy 或 detection。 | 持续复核 | 最终命名清理阶段统一处理旧名残留。 |
| Policy 视角 | format facts、runtime policy 和 decision contract 是否混在一起？ | 拆分 policy formats、parameters、runtime、decision、assembly、reporting。 | `formats/parameters/runtime/decision/assembly/reporting` 分离。 | 完成 | 每次新增 policy 字段时跑 consistency 并更新说明。 |
| Candidate 生命周期视角 | 候选如何生成、评估、扩展和选择？ | 去 retry 化，建立 plan、proposal、build、assessment、selection、extension。 | candidate plan、assessment、selection、extension 边界清楚。 | 完成 | 只在候选来源新增时复核 execution budget。 |
| Outer 视角 | outer 是 proposal 还是 correction，是否越权 PASS？ | 拆分 outer proposal/correction，corrected outer 回到 candidate reassessment。 | proposal/correction 分离，outer 不决定 PASS / REVIEW。 | 完成 | 后续只复核新增 proposal 是否走 plan。 |
| Wide / Dark / Retry 视角 | wide、dark、retry、fallback 是否是真正概念？ | 收敛 wide/dark 为 separator width evidence，retry 为 candidate plan，fallback 为 safety candidate。 | width evidence、candidate plan、safety candidate。 | 完成 | 最终命名清理时清除旧 detail 双写。 |
| Debug / Report 视角 | 人类如何复盘候选、gate 和 policy？ | 保留三联 Debug Analysis，report 保留 candidate/gate/policy detail。 | 三联图和 report detail 作为人工审核 surface。 | 持续复核 | 每改一个逻辑族群都检查解释力。 |
| 逻辑族群视角 | 检测逻辑本身有哪些族群，哪些已审？ | 建立 Detection / Gate / Risk 人工审核索引，Pre-detection 和 outer 已完成，Gap / Separator 已开始。 | 当前接点明确为 Gap / Separator。 | 进行中 | 从 `separator_profile` / `find_gap` 继续。 |
| Git / 验证视角 | 改动是否验证、提交和同步？ | 跑静态检查、policy consistency、standalone、样片 smoke，并提交推送。 | 最新结构已推送到 `main`。 | 完成 | 每次源码或文档改动后按范围验证。 |

#### 逻辑族群审核进度

| 视角/族群 | 我们问的问题 | 已做工作 | 成果 | 当前状态 | 下一步接点 |
|---|---|---|---|---|---|
| Pre-detection | layout、deskew、base gray、evidence gray 是否只提供输入证据？ | 完成 layout/坐标映射、deskew angle selection、base gray、evidence gray、analysis cache / reuse 深审。 | `base_gray`、work-space 输入、deskew detail 和 evidence/cache 分离；不生成候选、不评分、不 PASS / REVIEW。 | 完成 | 进入 Gap / Separator；separator cache 作为 gap evidence cache 继续审。 |
| Policy activation | format/mode 是否只通过 policy 打开行为？ | 完成 format facts、runtime policy、decision contract 分层。 | format/mode isolation 基本稳定。 | 完成 | 新增格式或 mode 时复核。 |
| Mode detector | standard、dual-lane、review-only 是否隔离？ | 审核 dual-lane 和 review-only 边界。 | review-only 成为通用保守模式。 | 完成 | 新 mode 必须声明 detector kind。 |
| Outer proposal / correction | outer 是否只提出候选或修正候选？ | 完成 proposal/correction 拆分和 corrected candidate reassessment。 | outer 不再拥有 PASS / REVIEW 权限。 | 完成 | 后续只做新增逻辑复核。 |
| Gap / Separator | separator、geometry、content gap 证据如何分类和消费？ | 已完成族群分类，并按 candidate proposal 模型建立 `detection.candidate.proposal.separator` proposal / refinement / evidence 入口；candidate build 层已抽出 separator gap lifecycle helper。 | separator 只提出或修正 gap evidence；当前 hard gap 只有 `detected / edge-pair / enhanced-detected`；outer -> gaps 与 gaps -> frames 的职责已拆开。 | 进行中 | 从 `separator_profile` / `find_gap` 开始逐项深审。 |
| Content | content evidence 是否只验证或挑战候选？ | 尚未进入深审。 | 暂无最终结论。 | 未开始 | Gap / Separator 稳定后开始。 |
| Candidate build / frame geometry | outer -> gaps -> frames 的中间 detail 是否完整？ | 结构已归入 candidate build 和 geometry。 | build 层边界清楚。 | 未开始 | Content 后审核 frame fit 与 geometry detail。 |
| Scoring | separator/content/geometry 分数是否只辅助 gate？ | 尚未进入深审。 | 暂无最终结论。 | 未开始 | build/frame geometry 后审核。 |
| Gate | separator/content/geometry/partial/auto gate 是否清楚？ | 结构已归入 assessment。 | gate 位置清楚，但规则未逐项审。 | 未开始 | Scoring 后审核。 |
| Risk | lucky pass、overlap、competition 等是否只拉回 REVIEW？ | 架构上已从 retry/rescue 中拆出。 | risk 不应救回 PASS。 | 未开始 | Gate 后审核。 |
| Decision | 最终 PASS / REVIEW 是否唯一落在 decision contract？ | 已完成结构迁移和边界清理。 | final decision 层位置清楚。 | 结构完成，逻辑待审 | Risk 后逐项审 reason 和 cap。 |
| Finalization | 输出几何处理是否不生成新候选？ | 已完成 finalization 边界清理。 | finalization 只做 output-adjacent work。 | 结构完成，逻辑待审 | Decision 后审 output bleed / geometry adjustment。 |
| Audit visibility | report/debug 是否足以解释变化？ | 建立三联 Debug Analysis 和 report detail 方向。 | 审核 surface 已存在。 | 持续复核 | 每完成一个逻辑族群都回看。 |

维护规则：

- 每完成一个逻辑族群审核，同时更新本台账和下方人工审核索引。
- 每次实施代码变更后，只在 `CHANGELOG.md` 记录行为或结构变化，不复制本台账。
- `AGENTS.md` 只在 handoff 需要时记录当前接点，不放完整台账。
- 最终命名清理单独作为最后阶段，不穿插在每个逻辑族群中执行。

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
- `CandidatePolicy`: content-only、safety、weak-grid、equal-gap 候选的默认保守行为。
- `DecisionPolicy`: PASS / REVIEW reason id 和 confidence cap。
- `OutputPolicy`: TIFF metadata/export 行为和输出 bleed。
- `DecisionDiagnosticsPolicy`: decision/report 中记录的 diagnostics 和 overlay 说明。

runtime `DetectionPolicy` 仍用于 evidence generation wiring。它连接 detector、count、
outer、separator、content、scoring、candidate plan / extension、selection、
finalization、diagnostics、report 和 output 等 runtime 能力。`DetectionDecisionContract` 必须通过
active `DetectionPolicy` 派生；`policies/decision/overrides.py` 只保存不能从 runtime policy
直接推导的 final evidence threshold。影响最终 PASS / REVIEW 的参数必须进入 report
schema 的 decision policy detail。

`x5crop.policies` 内部按职责分包：

| 子包 | 职责 |
|---|---|
| `policies.formats` | format / mode policy presets。 |
| `policies.parameters` | 数值参数对象和 format parameter registry。 |
| `policies.runtime` | runtime `DetectionPolicy` 及其子 policy dataclass。 |
| `policies.decision` | final PASS / REVIEW decision contract 和少量 override。 |
| `policies.assembly` | 从 format preset + parameters 组装 runtime policy。 |
| `policies.reporting` | policy detail serialization；只负责报告可见性。 |
| `policies.registry` / `consistency` / `ids` | public lookup、consistency smoke 和 schema / policy id。 |

### Detection / Gate / Risk 人工审核索引

本索引用于按检测逻辑族群人工审核，不按源码目录或运行顺序切分。`主要位置` 路径默认
相对 `x5crop/`。审核目标是确认每个逻辑只在合适的 format / mode 被 policy 启用，
生成的 evidence、gate、risk 和 decision detail 可解释，并且不会绕过最终 PASS /
REVIEW contract。

| 逻辑族群 | 子逻辑 | 主要位置 | 人工审核重点 |
|---|---|---|---|
| Pre-detection | layout / coordinate mapping | `geometry/layout.py`, `geometry/boxes.py` | 已审：horizontal / vertical work-space 与 original-space 映射对称；坐标转换只改变视角，不改变裁切语义。 |
| Pre-detection | deskew angle selection | `image/deskew.py`, `image/deskew_parameters.py`, `runtime/deskew.py` | 已审：deskew 只估角、旋转输入和写入质量 detail；deskew uncertainty 只能作为最终 REVIEW reason 的风险输入，不能直接 PASS。 |
| Pre-detection | base gray | `image/gray.py`, `io/tiff.py`, `runtime/deskew.py`, `runtime/analysis_reuse.py` | 已审：`make_base_gray_u8` 是唯一基础灰度入口，用于 TIFF 读取和 deskew 后重建灰度；不承担 content / separator 语义。 |
| Pre-detection | analysis / evidence gray | `image/evidence.py`, `cache/analysis.py` | 已审：content/separator evidence gray 和 analysis cache 只提供可复用证据输入；不隐藏原始 gray，不选择候选，不决定 PASS / REVIEW；不保留 color contrast 或 heavy texture 预留接口。 |
| Policy activation | format physical facts | `formats/` | count、aspect、family、physical risk 是否是事实层，不含 gate threshold。 |
| Policy activation | format / mode policy presets | `policies/formats/format_*.py` | format/mode 是否只声明物理参数、gate profile 和 detector 差异；通用 detector capability 不应变成 format 专属算法开关。 |
| Policy activation | runtime policy assembly | `policies/assembly/*`, `policies/runtime/*`, `policies/parameters/*` | preset、parameters、runtime policy 是否一一映射；默认字段不得让报告误以为逻辑已 active。 |
| Policy activation | final decision contract | `policies/decision/contract.py`, `policies/decision/overrides.py` | runtime `DetectionPolicy` 与 final `DetectionDecisionContract` 的证据门槛不能语义漂移。 |
| Mode-specific detector | dual-lane detector | `detection/modes/dual_lane.py`, `detection/modes/dual_lane_context.py`, `detection/modes/dual_lane_split.py`, `detection/modes/dual_lane_detect.py`, `detection/modes/dual_lane_merge.py` | `135-dual/full` 是否独立于普通 135 strip；入口是否只调度，policy/spec context、lane split / lane detect / lane merge 是否可解释。 |
| Mode-specific detector | review-only mode | `detection/modes/review_only.py`, `detection/candidate/proposal/safety.py` | review-only 或 hard safety 必须保持 review-only，不得因为 confidence 偶然过线而 PASS。 |
| Outer proposal | base outer | `geometry/outer_boxes.py`, `detection/candidate/proposal/outer/base.py` | 基础 holder / content bbox 是否只提出 outer proposal，不承担评分或通过。 |
| Outer proposal | partial content-position outer | `detection/candidate/proposal/outer/partial_content.py`, `detection/candidate/proposal/outer/partial_edge.py` | 标准 partial 若内容不铺满片夹，统一建模为 edge-anchored 或 floating 两种位置；proposal plan 先尝试 edge，edge 候选达到 trust 门槛时跳过 floating；两者只提出 outer，必须继续经过 separator/content/geometry gate，`135-dual/partial` 仍由 review-only mode 接管。 |
| Outer proposal | separator-derived outer | `detection/candidate/proposal/outer/separator.py`, `detection/candidate/proposal/separator/bands.py` | separator-derived outer 是否按 `outer_scope`（local / full-width）与 `gap_search_profile`（standard / broad_width）组合生成候选；broad_width 是 separator gap/search/evidence profile，不是 outer variant；标准 strip 的 full 全部 eligible，partial 只有显式 count 时 eligible extension profiles；candidate execution budget 可在可靠 primary 结果后跳过 extension 执行。 |
| Outer proposal | proposal plan | `detection/candidate/proposal/outer/plan.py` | candidate 层只能通过 proposal plan 获取和合并 outer candidates；不得直接依赖 base/common/separator 内部 helper 或 variant 常量。 |
| Outer correction | geometry consistency correction | `detection/candidate/proposal/correction/geometry.py`, `detection/candidate/proposal/correction/types.py` | long-axis / short-axis 是否由 `OuterCorrectionFamilyPolicy` 控制开启面、修正轴和 partial 显式 count 门控；outer correction 只提出 `OuterCorrectionProposal`，不直接 PASS / REVIEW。 |
| Outer correction | content containment correction | `detection/evidence/outer_alignment.py`, `detection/candidate/proposal/correction/content_containment.py`, `detection/candidate/proposal/correction/types.py` | 内容边缘证据是否只用于提出更小的 corrected outer proposal；full 和显式 count partial 可用，auto-count partial 不启用，修正后的候选必须重新 build detection 并重新 assessment。 |
| Corrected candidate | corrected outer reassessment | `detection/candidate/build/corrected_outer.py` | corrected outer 重新 build detection、重算 evidence 并重新 candidate assessment；candidate 层负责“怎么重新算”。 |
| Candidate extension | outer correction candidate extension | `detection/pipeline.py`, `detection/candidate/extension/outer_correction.py`, `detection/candidate/proposal/correction/*` | correction 顺序固定为 geometry consistency 再 content containment；candidate plan 记录 eligible / skipped / attempted family；可靠 selection 且 outer alignment ok 时可跳过 correction 计算，并写出 execution budget action / reason；pipeline 只把 reassessed corrected outer 追加回候选池，不能绕过最终 decision / gate。 |
| Gap / separator | separator profile | `geometry/separator_profile.py` | profile 生成是否稳定，edge refine profile 是否只作为 gap evidence。 |
| Gap / separator | separator cache | `geometry/separator_cache.py`, `detection/evidence/evidence_cache_keys.py`, `detection/cache_keys.py` | cache key 是否包含 format / layout / policy 参数，避免复用错误证据。 |
| Gap / separator | separator proposal | `detection/candidate/proposal/separator/proposal.py`, `geometry/gap_search.py`, `geometry/separator_width_profile.py` | normal / broad-width gap proposal 是否只提出 gap evidence；gap width、guard、peak、geometry constraint 是否符合当前 format/mode；width profile 纯数学归 `geometry/separator_width_profile.py`，参数归 `SeparatorPolicy.width_profile`，outer policy 只保留 separator-derived outer family/band 参数。 |
| Gap / separator | hard-gap trust | `geometry/gap_trust.py` | hard gap 可信度是否能区分真实片间空隙、frame border、content edge。 |
| Gap / separator | separator refinement | `detection/candidate/proposal/separator/refinement.py`, `geometry/edge_pairs.py`, `geometry/nearby_separator.py`, `geometry/enhanced_separator.py` | edge-pair / nearby / enhanced 只能修正或补充 gap evidence；不得直接 PASS；替换或确认 hard gap 时 score / shift 约束是否足够严格。 |
| Gap / separator | robust grid model gaps | `detection/candidate/proposal/separator/refinement.py`, `geometry/robust_grid.py` | grid 只能补模型证据；weak grid 不得单独获得 auto PASS。 |
| Gap / separator | gap search profile planning | `detection/gap_profiles.py`, `detection/candidate/plan/separator_width_profile.py`, `detection/candidate/plan/sources.py` | `standard` 与 `broad_width` 是否作为同一候选计划里的 gap search profiles；full 和显式 count partial 可进入统一 assessment，但 primary separator 已可靠时可以不执行 broad-width profile；auto-count partial 不让 broad-width profile 抢候选。 |
| Gap / separator | broad-width detected gaps | `detection/candidate/proposal/separator/proposal.py`, `detection/candidate/proposal/separator/evidence.py`, `geometry/separator_width_profile.py` | broad separator width gaps 是否只作为普通 hard separator evidence 加 width detail，不生成独立 gap method；profile / band / expected-gap search 使用同一套底层 helper。 |
| Gap / separator | separator gap lifecycle in candidate build | `detection/candidate/build/separator_gaps.py`, `detection/candidate/build/detection.py` | `build_detection_for_outer` 是否只消费 separator gap lifecycle 结果去生成 frames、score 和 detail；separator gap lifecycle helper 负责 origin/pitch、standard/broad-width gaps、edge-pair、grid、enhanced 和 nearby refinement，但不 PASS / REVIEW。 |
| Gap diagnostics | gap diagnostics | `detection/evidence/gap_diagnostics.py` | diagnostic-only evidence 是否只解释 risk，不直接参与 candidate selection。 |
| Content | content evidence | `detection/evidence/content_evidence.py` | `ok / weak / low_content / aspect_conflict` 是否符合照片内容和 aspect。 |
| Content | content profile runs | `detection/evidence/content_profile.py` | content run 推测 frame 时是否处理缺失、断裂、局部曝光。 |
| Content | content mask outer | `detection/evidence/content_profile.py`, `image/evidence.py` | content bbox 只能生成线索，不能绕过 separator gate。 |
| Content | content candidate | `detection/candidate/proposal/content.py` | content-only candidate 必须 review-only，除非未来显式改变 final contract。 |
| Content | content support score | `detection/candidate/assessment/scoring.py` | content score 权重和 gate multiplier 是否不压倒 separator / geometry。 |
| Content | content mismatch review | `detection/candidate/selection/choose.py` | content 与 separator 候选冲突时是否倾向 review，而不是选择看似更高分的错误候选。 |
| Candidate | count / offset plan | `detection/candidate/plan/counts.py` | full / partial 的 count、offset、默认 count inclusion 是否符合片夹物理目标。 |
| Candidate | candidate source orchestration | `detection/candidate/plan/run.py`, `detection/candidate/plan/sources.py`, `detection/candidate/plan/reliability.py`, `detection/candidate/proposal/*` | separator、gap search profiles、safety candidate 和 content candidate 是否由同一个 candidate plan 声明；primary separator 是否先 assessment，只有不可靠时才执行 extension profiles / outer scope/profile combinations；selection 是否只发生在 assessment 后。 |
| Candidate | build detection for outer | `detection/candidate/build/detection.py`, `detection/candidate/build/separator_gaps.py` | outer -> separator gap lifecycle -> frame boxes -> confidence 的中间 detail 是否完整可审；gap lifecycle 与 frame/score assembly 分开。 |
| Candidate | frame fit | `geometry/frame_fit.py` | frame boxes 是否以 gaps 为核心，edge / geometry fit 只能保守微调。 |
| Candidate scoring | base confidence | `detection/candidate/assessment/scoring.py` | gap、width、outer、contrast 权重是否不会让弱证据误过线。 |
| Candidate scoring | geometry support score | `detection/candidate/assessment/scoring.py` | width_cv、outer area、aspect、count 是否与实际裁切稳定性一致。 |
| Candidate scoring | separator support score | `detection/candidate/assessment/scoring.py` | hard/grid/equal 的信用是否符合 hard > model 的原则。 |
| Candidate scoring | joint score | `detection/candidate/assessment/candidate.py` | geometry/content/separator 合分是否只辅助 gate，不替代 gate。 |
| Candidate scoring | hard full confidence floor | `detection/candidate/assessment/scoring.py` | full 默认张数且 hard gaps 完整时抬 confidence 是否只用于可信完整片条。 |
| Gate | separator gate | `detection/candidate/assessment/gates.py` | gate profile 是否与 format/mode policy 一致。 |
| Gate | `min_hard_with_equal_cap` | `detection/candidate/assessment/gates.py` | 135 类策略允许少量 model/equal 时，hard gap 下限是否足够。 |
| Gate | `all_internal_gaps_hard` | `detection/candidate/assessment/gates.py` | 120 / xpan 等 strict policy 是否要求内部 gap 足够硬。 |
| Gate | `geometry_support` | `detection/candidate/assessment/gates.py`, `detection/candidate/assessment/scoring.py` | half/full 的 stable grid / detected geometry 支持是否不借用到其它 format。 |
| Gate | leading grid failure | `detection/candidate/assessment/gates.py` | 前段 grid 弱、hard gap 偏后时是否阻止 lucky pass。 |
| Gate | partial safe extra frames | `detection/candidate/assessment/partial_holder.py` | partial 多扫 holder 时是否需要 broad separator width evidence、low leading content、stable frame content。 |
| Gate | auto gate | `detection/candidate/assessment/candidate.py` | `auto_gate=True` 是否同时满足 separator/content/geometry/mode-specific 证据且无 hard review reason。 |
| Candidate plan | gap search profiles | `detection/gap_profiles.py`, `detection/candidate/plan/separator_width_profile.py`, `detection/candidate/plan/sources.py`, `detection/candidate/plan/reliability.py` | `standard` 和 `broad_width` 是否作为同一候选计划的 eligible profiles；execution budget 可在 reliable primary 后跳过更贵的 profile 执行，并在 detail 中写出 action / reason / stage；不得退回失败补救式 retry。 |
| Candidate plan | safety outer proposal | `detection/candidate/proposal/safety.py`, `detection/candidate/source_policy.py`, `detection/candidate/plan/sources.py` | safety candidate 只能提供 review-only 安全结果，不应绕开 hard evidence 或 auto gate。 |
| Candidate plan | broad-width profile selection | `detection/candidate/selection/separator_width_profile.py` | full 模式 broad-width profile 候选竞争是否有明确帮助条件，且必须保留统一 assessment detail。 |
| Candidate plan | partial stop | `detection/candidate/plan/run.py` | partial safe auto 后提前停止是否不会跳过必要的 review evidence。 |
| Risk | overlap bleed risk | `detection/evidence/risk.py`, `gap_diagnostics.py` | gap 附近叠片/连续内容风险是否进入 REVIEW 或 output bleed。 |
| Risk | lucky pass risk | `detection/evidence/risk.py` | model/equal/grid 支撑的假 PASS 是否被拉回 REVIEW。 |
| Risk | outer-content mismatch | `detection/evidence/outer_alignment.py`, `detection/decision/pass_review.py` | outer 与内容 bbox 不一致时是否压 confidence / 加 review reason。 |
| Risk | candidate competition close | `detection/candidate/selection/choose.py`, `detection/decision/pass_review.py` | 第一、第二候选接近时是否 review，partial safe 情况的豁免是否合理。 |
| Risk | content-only / safety risk | `detection/candidate/assessment/candidate.py`, `detection/decision/pass_review.py` | content-only、safety、review-only 是否保持 conservative review-only。 |
| Risk | partial edge uncertain | `detection/candidate/assessment/partial_holder.py`, `detection/decision/pass_review.py` | partial 边缘不可信时是否必须 REVIEW。 |
| Finalization | edge bleed protection | `detection/final/geometry.py` | 输出前 edge bleed 保护是否只做安全几何调整，不改变 decision 证据。 |
| Finalization | approved geometry adjustment | `detection/final/geometry.py` | PASS 前几何微调是否仅在已通过候选上执行。 |
| Finalization | output-adjacent caps and bleed | `detection/final/finalize.py` | content low/aspect conflict、lucky pass、outer mismatch 的 confidence cap 和 output bleed 是否不生成新候选。 |
| Decision | final PASS / REVIEW | `detection/decision/pass_review.py` | 最终裁决是否唯一落在 decision contract；review reason normalization 是否稳定。 |
| Audit visibility | read-only diagnostics | `detection/evidence/read_only.py` | 只写解释性 diagnostics，不改变 confidence、candidate 或 status。 |
| Audit visibility | report sections | `report/schema.py`, `report/sections.py` | candidate table、gate records、selected candidate 是否足以人工复盘。 |
| Audit visibility | debug panels | `debug/*`, `policies/runtime/diagnostics.py` | 三联图默认保持可读；更丰富证据进入 report/detail 而非挤满首屏。 |
| Audit visibility | policy reporting | `policies/reporting/__init__.py` | report 中应区分 active policy、默认值、format/mode role 和 diagnostics detail。 |

建议人工审核顺序：先看 broad-width gap search profile、enhanced separator、`lucky pass risk`，
再依次看 outer、gap/content、candidate scoring、gate、final decision。任何行为修改都应
同步检查 report/debug 是否能解释变化。

### 必须隔离的行为

- 135 full 的完整片条假设不能推广给其它 format。
- 135-dual full 使用 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half/full` 开启。
- broad-width gap search profile 是通用 separator 宽度证据；120-66 只拥有更宽的 width 参数、square-frame gate、broad separator width evidence 要求和 strict-holder checks。
- outer correction 是通用 corrected-candidate capability；format 只能提供 aspect、margin、shrink/expand 和 gate 参数，不能拥有独立 correction 算法开关。
- weak grid、equal、content-only、safety 或不可信 partial-edge 证据不能获得自动 PASS 权限。

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
| `x5crop.entry` / `x5crop.runtime.config` | CLI parsing, entry option contract, runtime configuration contract. |
| `x5crop.entry.interactive` / launchers | Interactive menu; platform launchers only locate Python and enter interactive mode. |
| `x5crop.runtime.input_probe` / `x5crop.runtime.app` | TIFF input probing, layout resolution, startup summary, worker dispatch. |
| `x5crop.runtime.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug orchestration. |
| `x5crop.formats` | Single source of truth for format identity, physical specs, counts/aspects, and CLI choices. |
| `x5crop.policies` | Runtime policy, decision contract, format/mode presets, parameter resolution, policy detail serialization. |
| `x5crop.cache` / `geometry` / `image` / `io` | Analysis cache, boxes, gaps, separator profiles, deskew, pixel transforms, TIFF I/O, and other lower-level capabilities. |
| `x5crop.detection` | Detection pipeline, mode detectors, candidate lifecycle / proposals, evidence, decision, and finalization. |
| `x5crop.runtime.analysis_reuse` / `x5crop.export` / `x5crop.report` / `x5crop.debug` | Historical result reuse, TIFF output, result assembly, report schema, report writing, Debug Analysis. |
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
- `CandidatePolicy`: conservative defaults for content-only, safety, weak-grid, and equal-gap candidates.
- `DecisionPolicy`: PASS / REVIEW reason ids and confidence caps.
- `OutputPolicy`: TIFF metadata/export behavior and output bleed.
- `DecisionDiagnosticsPolicy`: diagnostics and overlay details recorded in decision/report.

Runtime `DetectionPolicy` remains the evidence-generation wiring surface.
`DetectionDecisionContract` must be derived from the active `DetectionPolicy`;
`policies/decision/overrides.py` only stores final evidence thresholds that cannot be
directly inferred from runtime policy. Any parameter that affects final PASS /
REVIEW must be present in report schema decision policy detail.

`x5crop.policies` is internally split by ownership:

| Subpackage | Responsibility |
|---|---|
| `policies.formats` | Format / mode policy presets. |
| `policies.parameters` | Numeric parameter objects and format parameter registry. |
| `policies.runtime` | Runtime `DetectionPolicy` and child policy dataclasses. |
| `policies.decision` | Final PASS / REVIEW decision contract and narrow overrides. |
| `policies.assembly` | Build runtime policy from format presets and parameters. |
| `policies.reporting` | Policy detail serialization for report visibility only. |
| `policies.registry` / `consistency` / `ids` | Public lookup, consistency smoke, and schema / policy ids. |

### Detection / Gate / Risk Review Index

Use this index for manual review by detector logic family rather than by source
directory or execution order. Paths in `Main location` are relative to `x5crop/`
unless stated otherwise. The goal is to verify that each behavior is enabled only
by the intended format/mode policy, produces explainable evidence, gates, risks,
and decision detail, and cannot bypass the final PASS / REVIEW contract.

| Logic family | Sub-logic | Main location | Review focus |
|---|---|---|---|
| Pre-detection | layout / coordinate mapping | `geometry/layout.py`, `geometry/boxes.py` | Reviewed: horizontal / vertical work-space mapping is symmetric and must not change crop semantics. |
| Pre-detection | base gray, deskew, and evidence gray | `image/gray.py`, `image/deskew.py`, `image/evidence.py`, `cache/analysis.py` | Reviewed: preprocessing may shape base gray, input posture, evidence gray, and reusable cache detail, but must not choose candidates or decide PASS / REVIEW. No color-contrast or heavy-texture evidence interfaces are reserved. |
| Policy activation | format facts and policy presets | `formats/`, `policies/formats/format_*.py` | Physical facts, thresholds, and detector differences must stay separate from universal capability activation. |
| Policy activation | runtime and decision contracts | `policies/runtime/*`, `policies/decision/contract.py` | `DetectionPolicy` and `DetectionDecisionContract` must not drift semantically. |
| Mode-specific detector | dual-lane and review-only paths | `detection/modes/dual_lane.py`, `detection/modes/dual_lane_*.py`, `detection/modes/review_only.py`, `detection/candidate/proposal/safety.py` | Dedicated detectors and review-only paths must stay isolated, context-driven, and conservative. |
| Outer proposal | base, partial content-position, separator-derived outer | `detection/candidate/proposal/outer/*`, `geometry/outer_boxes.py`, `detection/candidate/proposal/separator/bands.py` | Outer proposals only propose boxes; standard partial mode tries edge-anchored content before floating content and skips floating when edge candidates are trusted. Separator-derived proposals combine outer scope (local / full-width) with gap search profile (standard / broad_width); broad_width is not an outer variant. Full makes all separator-derived scope/profile combinations eligible, while partial makes extension profiles eligible only when count is explicit. Candidate execution budget may skip extension execution after a reliable primary result. |
| Outer correction | geometry consistency and content containment correction | `detection/candidate/proposal/correction/geometry.py`, `detection/candidate/proposal/correction/content_containment.py`, `detection/candidate/proposal/correction/types.py`, `detection/evidence/outer_alignment.py` | Outer correction families declare mode, allowed axes, evidence requirements, and explicit-count partial gating. They emit `OuterCorrectionProposal` boxes only and do not own PASS / REVIEW. |
| Corrected candidate | corrected outer reassessment | `detection/candidate/build/corrected_outer.py` | Candidate contract rebuilds detection, recomputes evidence, and reapplies candidate assessment for any corrected outer. |
| Candidate extension | outer correction candidate extension | `detection/pipeline.py`, `detection/candidate/extension/outer_correction.py`, `detection/candidate/proposal/correction/*` | The pipeline appends reassessed corrected outer candidates back into the candidate pool before selection; candidate detail records eligible, skipped, attempted correction families, and execution budget action / reason. Reliable selected candidates may skip correction computation only when outer alignment is also ok. |
| Gap / separator | profile, cache, proposal, hard trust, refinement, grid model | `geometry/separator_*`, `geometry/gap_search.py`, `geometry/gap_trust.py`, `detection/candidate/proposal/separator/*` | Hard evidence must stay stronger than model/equal/grid evidence, and cache keys must include policy-relevant context. Separator proposal/refinement only creates or adjusts gap evidence; it does not PASS / REVIEW. Width profile math lives in `geometry/separator_width_profile.py`; width profile parameters live under `SeparatorPolicy.width_profile`; outer policy only owns separator-derived outer family/band parameters. |
| Gap / separator | gap search profile planning and broad-width detected gaps | `detection/gap_profiles.py`, `detection/candidate/plan/separator_width_profile.py`, `detection/candidate/plan/sources.py`, `detection/candidate/proposal/separator/proposal.py`, `detection/candidate/proposal/separator/evidence.py`, `geometry/separator_width_profile.py` | Profile evidence must be explicit, capped when needed, and assessed through the normal candidate gate; reliable primary separator candidates may skip broad-width profile execution, and auto-count partial does not let broad-width profiles compete. |
| Gap / separator | separator gap lifecycle in candidate build | `detection/candidate/build/separator_gaps.py`, `detection/candidate/build/detection.py` | `build_detection_for_outer` consumes separator gap lifecycle output for frame building, scoring, and detail writing. The lifecycle helper owns origin/pitch, standard/broad-width gaps, edge-pair, grid, enhanced, and nearby refinement, but not PASS / REVIEW. |
| Content | content evidence, profile runs, mask outer, content candidate | `detection/evidence/content_*`, `detection/candidate/proposal/content.py` | Content can validate or challenge candidates but must not auto-pass alone. |
| Candidate | count/offset, source orchestration, build, frame fit | `detection/candidate/plan/counts.py`, `detection/candidate/plan/run.py`, `detection/candidate/plan/sources.py`, `detection/candidate/proposal/*`, `detection/gap_profiles.py`, `detection/candidate/plan/reliability.py`, `detection/candidate/build/detection.py`, `detection/candidate/build/separator_gaps.py`, `geometry/frame_fit.py` | Candidate lifecycle must keep all intermediate evidence in `Detection.detail`; primary separator candidates are assessed before extension profiles / outer scope/profile combinations execute, and separator gap lifecycle stays separate from frame/score assembly. |
| Scoring | base confidence, geometry/content/separator scores, joint score, hard-full floor | `detection/candidate/assessment/scoring.py`, `detection/candidate/assessment/candidate.py` | Scores support gates; they do not replace separator/content/geometry requirements. |
| Gate | separator gate profiles and geometry support | `detection/candidate/assessment/gates.py`, `detection/candidate/assessment/scoring.py` | `min_hard_with_equal_cap`, `all_internal_gaps_hard`, and `geometry_support` must match format/mode policy. |
| Gate | partial safe extra frames and auto gate | `detection/candidate/assessment/partial_holder.py`, `detection/candidate/assessment/candidate.py` | Partial edge safety requires explicit broad separator width, content, and frame evidence and no hard review reason. |
| Candidate plan | gap search profiles, safety candidate, broad-width profile selection, partial stop | `detection/candidate/plan/run.py`, `detection/candidate/plan/sources.py`, `detection/gap_profiles.py`, `detection/candidate/plan/reliability.py`, `detection/candidate/plan/separator_width_profile.py`, `detection/candidate/selection/separator_width_profile.py` | Candidate plan profiles and families are declared together, but execution budget may stop after a reliable primary candidate and reports action / reason / stage; no source can bypass hard evidence. |
| Risk | overlap bleed, lucky pass, outer-content mismatch, close competition | `detection/evidence/risk.py`, `detection/evidence/gap_diagnostics.py`, `detection/evidence/outer_alignment.py`, `detection/candidate/selection/choose.py`, `detection/decision/pass_review.py` | Risk logic should pull suspicious PASS candidates back to REVIEW or safer output bleed. |
| Risk | content-only, safety, review-only, partial-edge uncertainty | `detection/candidate/assessment/candidate.py`, `detection/candidate/proposal/safety.py`, `detection/decision/pass_review.py` | Conservative REVIEW-only paths must stay review-only unless the decision contract changes. |
| Finalization | edge bleed protection, approved geometry adjustment, caps | `detection/final/finalize.py`, `detection/final/geometry.py` | Output-adjacent geometry changes must preserve evidence/risk detail and safety caps without generating candidates. |
| Final decision | PASS / REVIEW, reason normalization, decision detail | `detection/decision/pass_review.py` | Final status must be decided only by the decision contract. |
| Audit visibility | read-only diagnostics, report sections, debug panels, policy reporting | `detection/evidence/read_only.py`, `report/schema.py`, `report/sections.py`, `debug/*`, `policies/reporting/__init__.py` | Reports and Debug Analysis explain behavior without feeding back into candidate selection. |

Recommended manual review order: start with broad-width gap search profile,
enhanced separator, and `lucky pass risk`; then review outer, gap/content, candidate
scoring, gates, and final decision. Any behavior change must also prove that
report/debug output explains the change.

### Behavior That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for
  `half/full`.
- Separator width profile is a universal separator-width evidence capability.
  120-66 keeps only its broader width parameters, square-frame gate, broad-width
  evidence requirements, and strict-holder checks.
- Outer correction is a universal corrected-candidate capability; formats may tune
  aspect, margins, shrink/expand limits, and gates, but must not own separate
  correction algorithm switches.
- Weak grid, equal, content-only, safety, or untrusted partial-edge evidence
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
