# 项目记忆

更新：2026-07-30

这是 X5 Crop 唯一跨会话检查点，只保存当前目标、已验证状态、能力边界、开放风险和精确
下一步。详细运行合同见 `ARCHITECTURE.md`，版本历史见 `CHANGELOG.md`。Git、源码、原始
TIFF、current report、Debug Analysis 与现场命令输出始终优先于本文件。

## 当前检查点

- 分支：`main`。
- Source-core 实现检查点：
  `5f8b96eac9823a6b6c93f5fa208df2e0820a2f02`。本文件由后续 docs-only 提交更新；
  恢复时以现场 `HEAD == origin/main` 为准，不在文档内硬编码自身提交 SHA。
- Tracked 工作区干净；ignored 内容只有 `Test/` 本地样片与证据。
- 当前 runtime：`X5_Crop.py` V4.9 source-core 安全基线。
- 当前用户 runtime 依赖：`numpy`、`tifffile`、`imagecodecs` 与 `Pillow`；SciPy 与
  OpenCV 不是 current runtime dependency。
- 当前稳定公开 Release：`v4.2.8`。
- Runtime schema：

  ```text
  schema_id       = detection_report
  schema_revision = source_core_grid_authority
  ```

- 当前没有获批的独立 `FrameGridEvidence` phase authority。所有需要定位 frame 的输入
  正式得到：

  ```text
  status = needs_review
  reason = frame_grid_authority_unavailable
  frame boxes = ()
  frame TIFF outputs = ()
  ```

这不是 detector 失败后的 fallback，而是 current runtime 的真实能力边界；它不再代表
项目最终成功标准。

## 不可偏移的产品宗旨

X5 Crop 的目标是在用户已经提供 format 与 count 后，自动生成**足够安全、不切掉真实照片
内容**的逐帧 TIFF。它不是照片边界测量工具，不要求唯一还原真实边界，也不追求手术刀式
贴边；合理的 outward over-retention 优于 inward content loss。

固定产品合同：

- 用户输入的 format 与 count 是 runtime authority，detector 不重新猜测这两项。
- Separator、content、outer、expected position、格式尺寸、score 与其它模型线索可以参与
  bounded proposal、assessment 和 selection。Report/Debug 必须区分 observed 与
  inferred，但模型推断本身不是送审理由。
- `approved_auto` 表示最终保护后的输出满足有界安全合同；不表示 Grid phase、separator
  或照片边被唯一证明。
- `needs_review` 只表示存在 protection 无法吸收的具体输出风险，例如整格/ordinal
  歧义、count 无法成立、已知内容仍会被切掉、候选会混入错误相邻照片，或 geometry
  在应用固定 protection 前就越出 source/lane authority。
- Partial 可以推断真实照片位于哪些 slots；blank 保留 slot；contact/overlap 可以让相邻
  输出框重叠并重复保留共享像素。只有 slot ownership 或安全包络无法有界时才送审。
- 多个精确 geometry 不唯一但输出等价时允许自动批准。回归验收关注 count、顺序、slot
  ownership、真实内容 containment、允许的向外多保留与 TIFF 保真，不要求复刻历史 box。
- `CandidateGate` 只检查候选与输出安全事实；只有 `DecisionGate` 创建 final status 与
  final reasons。

## 当前目标

2026-07-30 已完成 `v4.2.8`、V3 archive、`X5_Split_v17/v18` 与 source-core 切换前
V4.9 的只读历史审查，并冻结 bounded safe-crop Grid 的下一阶段设计。当前会话只更新
文档，没有修改 detector；下一个任务按 `ARCHITECTURE.md` 第 12 节实现，不要求唯一独立的
真实 Grid phase，也不按历史版本逐层恢复旧 detector。

冻结的目标数据流：

```text
source pixels + authoritative format/count
→ source-core measurements
→ bounded prior / placement / corridor observations
→ ordered DP FrameGridProposal
→ FrameSlot / interaction / SafeCropEnvelope
→ millimetre OutputProtection
→ optional VisualDeskewProposal and output geometry
→ CandidateGate safety facts
→ DecisionGate
→ inverse-affine ROI
→ TIFF
```

实现必须保持固定结构上限、observed/inferred provenance、source-coordinate geometry、
typed uncertainty 与单向生命周期权限。Score 与 expected position 只能排序/约束搜索；
不得恢复旧 schema、兼容层、fallback/retry 或按样片写死的 whitelist。

## 当前运行与状态语义

唯一运行流：

```text
TIFF source pixels
→ base gray / statistics，各一次
→ ScanCanvasEvidence
→ independent long/short scale intervals
→ SourceStripValidationDomain
→ immutable positive-content components
→ FrameGridEvidence(NO_INDEPENDENT_PHASE_AUTHORITY)
→ CandidateGate
→ DecisionGate
→ review copy / current report / Debug Analysis
```

已经成立：

- 设计 aperture 保持离散 format components，不取 hull。
- Long/short scale 分轴传播，TIFF DPI 不参与检测。
- Validation domain 只来自唯一 scan canvas/lane 与 source extent。
- Positive content 由独立 intensity/texture fields、strict 4-connectivity 和 immutable
  RLE 产生；它是确定性 measurement，无 Grid 权限。
- 当前无组合搜索，因此没有 `PhysicalAuditBudget`。

当前未运行：

- Separator 与 photo edge：没有 active detector 或 runtime type。
- Frame Grid：固定 `NO_INDEPENDENT_PHASE_AUTHORITY`。
- Photo containment：`NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`。
- Visual Deskew：`NOT_APPLICABLE_CORE_UNAVAILABLE`。
- Blank/contact/overlap：没有 current measurement owner，不进入 current schema。
- Millimetre protection：只报告 authority；没有 frame geometry 时 `applied=false`。
- ROI/TIFF exporter：独立 foundation 保留，但 current runtime 没有合法 boxes。

系统只有两个 Gate：

1. `CandidateGate` 检查 source-core facts，不创建 final status/reason。
2. `DecisionGate` 是 final status 与 typed reason 的唯一 owner。

术语：

- `unavailable`：evidence owner 缺少足够权威事实，不是负质量分数。
- `needs_review`：DecisionGate 把阻断 evidence 映射成用户可见 final status。
- `unsolvable`：不是 current runtime/schema 术语，不得作为 alias 加入。
- `contradicted`：只表示完整物理约束明确否定，不能代替 incomplete。

正常 source core 完整但 Grid 缺 authority 时只产生
`frame_grid_authority_unavailable`。若 scan canvas/content 自身不可用，追加各自 typed
reason；被 Grid 阻断的下游只标记 `NOT_APPLICABLE`。

## 已验证检查点

### Current-only tree

- Source-core 原子替换：`0a4a93fcab94cf620cec0bc30b27eeb6f898a48f`。
- 极致收口：`4a5ac722d2a0c489a7da4bd84fbb6adadd3d5254`。
- Runtime 依赖闭合：`5f8b96eac9823a6b6c93f5fa208df2e0820a2f02`；strict
  4-connectivity 改由 NumPy RLE 与确定性 union-find 实现，active runtime 不再依赖
  SciPy。
- Active tree 已原子删除旧 PhotoEdge/separator/sequence/transform/rotated-gray/pixel-bleed
  链及 reader、alias、shim、adapter、feature flag 和双实现。
- 不可达的 auto-approval/Debug PASS、空 export wrapper、重复 content fields 与过期 ignore
  例外也已删除。
- 两轮相同 checklist 均为零残留：无 legacy token、空 source 目录、无 owner module 或
  文档断链。

### Contracts、样片与性能

- Pre-push full：29/29 tests、compileall、14/14 format/mode、shell syntax、diff hygiene
  和 version check 全部通过。
- Named audit：S027、S035、S051、S055、S062、S091、S094、S109、S098 共 9/9 正常
  `needs_review`，0 frame output。S098 只作 `irregular_geometry_stress`。
- 111 张 invariant：111 completed、0 failure、0 frame output。
- NumPy RLE/union-find 在 600 组独立 oracle mask 与 111 张 current 样片上保持 strict
  4-connectivity/content geometry 一致。
- 固定 24 张 detector-only、`--jobs 2`：

  ```text
  cold       单独记录
  median     2.216 秒/张（三次 measured runs）
  ```

  受限环境中 process worker 不可用，实际降级为两个 thread workers；且没有 frame TIFF
  写出，因此只是 `diagnostic_only`。它证明安全基线保有 `<5.0 秒/张`的未来余量，不是
  正式输出性能认证。
- 正式性能仍要求 bounded Grid proposal 与 safe crop envelope 恢复输出后，用固定
  24 张、`--jobs 2`、真实 TIFF 写出和复读，三次中位数 `<=5.0 秒/张`。当前状态必须是
  `not_certified`。
- 人工证据链重新验证：111 条 source manifest、9 条 fit proposal、9 条 user-confirmed
  baseline；outer-noise、overlapping-divider 与 declared-frame-count contracts 均通过。

## 本地证据与历史边界

本地有 111 张未修改 source TIFF：47 张 135/full、14 张 135/partial、32 张
120-66/partial、3 张 120-67/full、10 张 half/full、5 张 half/partial。九张黄金样片的
source/marked/JPG/proposal/baseline hashes 完整保留；八张属于 nominal calibration，
S098 属于 stress。

Baseline 只能在 detector/output receipt 冻结后用于 comparator，不参与检测、Grid、
deskew 或输出选择。

重启前原型证据：

```text
Test/local_audit_evidence/2026-07-29-source-core-cutover/
```

该 ignored 目录含 SHA manifest、cutover patch、原型脚本、决定性输出与 validation
receipt，不得随 cache 清理。它只否定特定表示或 measurement 合同：

- exact top × bottom photo-edge 未在八张 nominal 上形成唯一 pair；
- leading × trailing 笛卡尔积覆盖不完整且超预算；
- 原子暗带、width conservation、section connectivity、dense row-band、
  fragment/K-message、full-axis sparse 与 full-height origin proposal 都没有形成普遍、
  唯一、有限工作量的 separator identity；
- release outer/holder continuity 只能提供 proposal 或向外 containment 线索；
- confirmed-line signal matrix 否定的是
  `base_gray_u8 + current local-noise/integration` 的普遍可用性，不证明原始高位深 TIFF
  没有物理信号。

### 2026-07-30 历史机制回收审查

审查范围：

- `v4.2.8:x5crop/geometry.py`、`detection/pipeline.py`、`deskew.py` 与历史
  `CHANGELOG.md`；
- V3.0–V3.9 archive，包含已回滚的 semantic hard-gap、local-grid 与 overlap 实验；
- `X5_Split_v17/v18` 的 edge、Grid、outer、same-frame-size、deskew 与 TIFF 路径；
- `663c45a1` 的 V4.9 frame-sequence、separator assignment、boundary role、uncertainty、
  Gate、affine 与 cache 合同。

以下 CamelCase 是新计划的 owner 名称，不是 current runtime 已有能力。回收的是物理思路与
生命周期边界，不是旧函数、参数、schema、status 或 fallback branch。

#### 重写进入新方案

1. **Expected-position local corridors**：保留 `expected position` 的搜索权限。每个
   `count - 1` boundary corridor 保留少量普通 band、wide band、edge-pair 与一个
   model-only position，直到有序 assignment；不得像旧 `find_gap()` 一样先按最近位置只留
   一个观测。
2. **Separator band 与 edge-pair**：新的 `SeparatorBandObservation` 保存两侧 transition
   interval、band interval、center、width、cross-axis support、appearance 与 source
   provenance。Edge-pair 的价值是同时给出 `Photo end`、`Grid divider`、`Photo start`
   的候选约束；center 不能吞掉两侧边缘，也不能直接成为 final cut。
3. **Learned one-sided edge**：复用 V17 “先从多个 edge-pair 学习 gutter width，再解释
   单边 photo↔blank transition”的思路。新的 `OneSidedBoundaryObservation` 只提供某一侧
   的 containment bound；它适合 blank、leader、片头片尾与接触边界，但不能单独确认
   separator identity、ordinal 或 final status。
4. **Anchor-derived model Grid**：复用 pair/RANSAC-like hypotheses、weighted refit、
   inlier/residual 与强观测冲突记录；把它改写为有序 DP 的 `FrameGridProposal`。两个以上
   ordinal-compatible anchors 可拟合 pitch/phase；一个 anchor 只在有限 ordinal 与
   placement seeds 中展开；零 anchor 仍可形成 model-only proposal。缺失 separator 可以由
   Grid 补位，观测与推断必须分开记录。
5. **Floating 与 separator-first placement**：复用 120-66 的“照片不一定铺满或居中”和
   “先由 separator 反推 Grid/outer”经验。`GridPlacementSeed` 只能来自有界集合：scan
   canvas/lane、格式物理 component、content/outer 左右与中心、observed separator
   assignment，以及 partial 的有限 phase/endpoint hypotheses。它们是同级 proposal source，
   不建立 `fallback/retry/always` 分支。
6. **Format geometry 与 frame fit**：复用格式 aspect、separator total、robust common frame
   width、`pitch - learned gutter` 和左右 edge weighted median。它们进入
   `FrameEnvelopeProposal` 与 residual assessment，不作为 width oracle。最终
   `SafeCropEnvelope` 对输出等价 hypotheses 作向外包络，再应用毫米 protection；首尾 slot
   可向已选 strip containment endpoint pin，但不得越过 source/lane 或吸入错误邻片。
7. **Nearby 与 semantic measurements**：复用 narrow nearby search，以及 gap content、左右
   content、continuity、background、activity、width、geometry conflict 等 measurement。
   它们可以重排局部观测、保留 competing proposal 或形成 uncertainty；不得恢复 V3.5
   “semantic validator 直接降级 hard gap”，也不得静默移动一个 strong observation。
8. **Blank/contact/overlap**：复用 overlap-like / continuous-content 测量，但改写为
   `BoundaryInteractionObservation`。Blank 保留完整 slot；contact/overlap 使相邻
   `SafeCropEnvelope` 向同一区域扩张并允许重复像素。旧“overlap 直接 REVIEW”规则不恢复；
   只有保护后仍会切内容、混入错误邻片或 ownership 无界时，CandidateGate 才记录阻断事实。
9. **Short-axis 与 Visual Deskew**：复用上下边缘 pair、两侧 line agreement、residual、
   base/enhanced angle proposal 与 source-coordinate uncertainty。它只在 Grid/envelope
   选择后产生 `VisualDeskewProposal`，不能证明 Grid，也不是自动批准前提；最终仍只做一次
   inverse-affine ROI，不恢复完整 RGB 旋转再裁切。
10. **V4.9 生命周期骨架**：复用 ordered `FrameSlot`、boundary-role provenance、separator
    assignment、raw alternatives、output-equivalence consensus、internal/external safety
    envelope、typed search-incomplete 与 per-stage work statistics。实现改为当前所需的有界
    corridor + ordered DP，不恢复 ridge graph、fragment、dense sequence graph 或全组合
    solver。
11. **测量复用与可审计性**：继续 base gray/statistics 各一次、vectorized measurement、
    source-coordinate exact cache、count/offset-independent cache key、候选上限、固定工作
    顺序、observed/inferred/blank/interaction provenance、accepted/rejected/conflict detail、
    current-schema comparator 与 Debug overlay。Report/Debug 不重测、不选择、不裁决。

#### 只回收事实，不回收旧动作

- `hard_trust`、nearby conflict、`lucky_pass_risk`、content/separator candidate label 与旧
  confidence score 只能成为 observation/proposal/selection 或 CandidateGate facts，不能
  直接创建 PASS/REVIEW、confidence cap 或 final reason。
- V3.4.2 local-grid 只能作为 competing local-drift proposal 或 Debug 建议；在 named
  evidence 证明普遍安全前，不得直接改写 selected Grid。
- V3.5 semantic hard-gap 的局部 measurements 可以复用；其 broad hard-gap demotion 已有
  回归失败，不得恢复。
- V4.2.x 的历史 PASS 数、box parity、stable-grid / wide-gap gate 与 content-only 禁止规则
  只说明机制曾有参考价值，不是 current acceptance contract。
- 旧 post-approval geometry polish 的“向外发现遗漏内容”可以前移为
  `SafeCropEnvelope` 之前的 measurement；不得在 DecisionGate 之后再改变 boxes。

#### 明确不恢复

- 自动猜 format/count、partial count candidates、五个固定 partial offsets 或按样片写死的
  offset/threshold；
- 无 corridor 的全轴 band 笛卡尔积、dense ridge/fragment/sequence graph，以及用预算耗尽
  选择当前最好答案；
- `equal/grid/content` fallback 身份、ordinary/wide/enhanced retry branch、feature flag、
  compatibility shim、旧 cache/report/schema 与旧 reason；
- 把 outer/content bbox、expected position、最近候选、最高 score、共同 width 或重复
  geometry 宣称为 observed photo edge/separator；
- strong hard gap 对 Grid 的绝对 authority、local-grid active mutation、semantic hard-gap
  broad demotion、overlap/lucky-risk 直接 review gate；
- pixel bleed、post-Decision geometry mutation、完整旋转图后再次检测/裁切，以及 historical
  status/confidence/whitelist/baseline selection。

## 2026-07-30 设计冻结检查点

详细数值与生命周期合同唯一见 `ARCHITECTURE.md` 第 12 节。下一个任务不得重新把这些项目
降级为开放架构问题：

- Full 使用 format `default_count`；partial 必须由用户显式提供 allowed count；135-dual
  两个 lane 各自 6。Ordinal 始终是本次输出的 lane-local `1..count`。
- `FrameGridSearchPrior` 只保存按 format/mode/component 校准的 pitch、gutter、phase
  corridor 与 endpoint interval，不是 observation 或 Decision authority。
- 每个 lane/component 最多 6 个非重复 placement seeds；每个 internal corridor 最多 2 个
  image-observed candidates 加 1 个 model-only candidate；每个 lane 最多 3 个非支配
  `FrameGridProposal`。
- 对 count 12，每个 lane/component 的 ordered DP 上限为 198 states、558 transitions。
  超限只产生 typed `search_incomplete`；只有被省略 alternative 可能改变 ownership 或安全
  box 时才阻断。
- Separator-first 不做 raw band 全配对；按 band、有限 ordinal difference 与 pitch interval
  作有界查询，再最多保留两个 seed。
- Anchor `2+ / 1 / 0` 分别走有限 pitch/phase fit、有限 ordinal assignment、model-only
  proposal；没有 separator、齿孔不可见或 model inference 本身不送审。
- Partial 不使用五个固定 offsets；leading/trailing endpoint 独立竞争。Blank 保留 slot；
  contact/overlap 的 bounded shared interval 同时并入相邻输出。
- Output-equivalent 要求 count/order/content ownership/interaction 一致，且 union 不进入
  已知错误邻片或越出 authority；等价 geometry outward union 后仍可自动批准。
- 毫米 protection 表值均是每侧值，按独立 scan-canvas scale upper endpoint 向上取整；先
  合并 safe envelope/shared interval，再应用 protection。只有固定 protection 可在
  source/lane authority 饱和，原始 envelope 不得 clamp。
- 短轴默认保留完整 authoritative lane；只有能同时包含 format aperture、observation
  uncertainty 与全部已知 content 时才向内收窄。看不见短轴照片边不送审。
- `CandidateGate` 只保存十一项有序安全事实；只有 `DecisionGate` 映射
  `approved_auto` / `needs_review` 与冻结的 typed reasons。Blank、inferred、
  equivalent geometry、未 deskew、protection 饱和或较低 score 都不是独立 review reason。
- 原子切换时 report revision 变为 `bounded_safe_crop_grid`；同批删除
  `source_core_grid_authority` runtime reader/branch，不保留 alias 或双路径。
- 初始 prior/threshold 数值是下一任务的只读 calibration data 或明确的同 film-family
  physical-rule data，不是待重新设计的权限问题。八张 nominal 用于校准，S098 只作
  stress；没有真实 fixture 的 XPan/120-645 不宣称准确性覆盖。

## 文档与工作区

- `README.md`：精简中英双语入口。
- `ARCHITECTURE.md`：当前 runtime 与数值合同唯一 owner。
- `CHANGELOG.md`：版本行为、验证边界与历史。
- `docs/user-guide.*`、`docs/quick-start.*`：分离的中英文公共文档。
- `PROJECT_MEMORY.md`：唯一跨会话检查点；不得新增平行 handoff 文档。
- `Test/`：ignored 本地样片与证据。原 TIFF、manual review、baseline 和
  `local_audit_evidence` 必须保留；cache、`.DS_Store` 与 generated output 不保留。

## 开放风险

1. 当前没有 bounded Grid proposal、slot assignment 与 safe crop envelope，所以仍不能
   定位或输出 frame。
2. Prior、separator/edge-pair、one-sided edge 与 interaction thresholds 尚未基于 current
   source-coordinate named audit 校准；旧值只能作为比较材料。
3. Current positive-content 是已知内容的保守 measurement，不保证观察全部真实内容；实现
   必须依靠物理 prior、outward envelope 与 protection，而不是把 content absence 当 blank
   真值。
4. XPan 与 120-645 缺少真实 fixture，不能声明准确性覆盖。
5. Detector-only 余量不能代替真实 frame TIFF 性能合同。
6. Green tests、历史 PASS、hash 或 comparator 一致不能单独证明安全输出；Named TIFF
   必须检查真实内容 containment，但不要求精确贴合人工边界。

## 新任务的精确下一步

设计已经冻结。新任务从实现与 read-only calibration 开始，不再先重写一份平行方案，也
不把全部历史机制一次性恢复。

开始时核对：

```bash
git log -1 --oneline --decorate
git status --short
git rev-parse origin/main
rg 'REPORT_SCHEMA_REVISION' x5crop
python3 -B Test/manual_review/red_markup_converter.py verify
wc -l Test/manual_review/manifest.jsonl
wc -l Test/manual_review/user_confirmed_golden_baseline.jsonl
```

实施顺序：

1. 按架构第 12.3–12.8 节建立 types、构造不变量、Gate vocabulary 与 synthetic contracts；
   current runtime 仍保持 review-only。
2. 用八张 nominal 原 TIFF 生成 per-format/mode/component 的 read-only prior/measurement
   audit，冻结 calibration receipt、candidate/work distributions；S098 不参与调参。
3. 完成 seed、canonical separator/edge-pair、model-only corridor、ordered DP、slot、
   safe envelope、毫米 protection 与 identity output geometry 的最小纵切；先审计
   135/full 与 120-66/partial，不开放 export。
4. 加入 partial endpoints、blank、contact/overlap、output-equivalence 与 learned
   one-sided gutter。Wide/nearby/local-drift/advanced frame fit/deskew 只在 named gap
   证明需要时逐项加入。
5. 一次原子替换 runtime、两级 Gate、finalization、report/Debug/comparator 与旧
   placeholders；同批更新中英文公共文档，不建立 feature flag、fallback、compatibility 或
   格式白名单。
6. 运行九张人工证据、代表性 cohorts、111 invariant 与固定 24 张真实 TIFF 写出/复读，
   检查 `<=5.0 秒/张`正式性能合同及 TIFF 保真。

任一阶段都不得让 lower layer 创建 final status/reason，也不得在物理输出尚未检查时声明
自动裁切或正式性能完成。

新任务恢复提示：

> 继续 X5 Crop。读取 `README.md`、`AGENTS.md`、`PROJECT_MEMORY.md` 与
> `ARCHITECTURE.md`，核对 `main` 与 `origin/main` 一致、tracked 工作区干净，并确认
> `5f8b96ea` 是 source-core 实现检查点。当前 runtime 仍是 review-only，但产品宗旨是
> 在用户提供 format/count 后保守自动裁切、不切真实内容，而不是唯一证明照片边界。
> 历史机制审查与 bounded-safe-crop 设计均已冻结。直接按架构第 12 节实施
> contracts、read-only calibration 与最小纵切；保持 `P_MAX=6`、`K_MAX=3`、
> `G_MAX=3`、DecisionGate-only final decision、每侧毫米 protection 和原子 schema
> cutover。不要另建平行计划，也不要原样恢复旧 runtime/schema。
