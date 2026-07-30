# X5 Crop V4.9 当前架构

本文只描述当前运行流、数值合同、权限与源码分层。版本历史见
[CHANGELOG.md](CHANGELOG.md)，用户操作见中英文用户手册，跨会话检查点只属于
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## 1. 产品与安全合同

X5 Crop 在用户提供 format 后生成保守裁切，目标是不内切真实照片内容，而不是唯一恢复
真实物理边界或复制历史 boxes。

- Format 始终是 runtime authority。
- Full count 固定；partial 同时支持 explicit 与 bounded auto count。
- `approved_auto` 只表示 protection 后的输出满足有界安全合同。
- 输出允许向外多保留、相邻框重叠、保留 blank slot 或带入相邻照片像素。
- `needs_review` 只用于具体且无法吸收的 count、ordinal、primary ownership、
  containment、source/lane authority 或 output geometry 风险。
- Separator 缺失、blank、inferred Grid、等价 geometry、未 deskew 和 protection 饱和
  都不能单独制造 review。
- I/O 失败是独立 terminal failure，不能转成 review。

当前系统是 current-only 原子实现。Runtime、tests、tools、report 与 Debug 只消费
`bounded_safe_crop_grid`；没有 feature flag、双 schema、兼容 reader 或备用 detector。

### 1.1 已批准的下一原子切换（尚未实现）

用户已确认：partial `auto` 可以输出额外空白 TIFF，完全空片也可以输出全部空白 slot；
安全优先级是“不漏掉真实照片”，不是识别唯一真实 count。当前
`main@7478ca09` 仍运行 `1..default_count` 的跨 count dominance，因此本文后续章节在
切换完成前仍如实描述 current runtime，不能把以下目标宣称为已上线行为。

下一次原子切换的唯一目标合同是：

- `fixed_full` 继续使用 format 默认 count；`explicit` 继续严格服从用户 count。
- Partial `auto` 在唯一匹配 scan-canvas 后，使用该片夹对当前 format 的有效最大容量作为
  唯一 `output_slot_count`。同一 format 进入较短片夹时，以 typed
  `ScanCanvasFormatFit.maximum_frame_count` 为准，不盲用 format 默认值。
- `output_slot_count` 只表示输出 holder slots，不表示真实照片张数。前导、尾随或中间
  blank 均保留；真实照片可以位于容量 Grid 中任意物理允许的位置。
- Auto 不再搜索多个 count，也不再建立跨 count
  `FrameCountDominanceAssessment`、全局 count competition 或
  `automatic_count_unresolved`。同一容量 count 内的 placement、corridor、ordered DP、
  component/seed selection、slot ownership、safe envelope 与 protection 继续保留。
- `CandidateGate` 与 `DecisionGate` 的权限不变。容量语义不能绕过 Grid、ownership、
  containment、source/lane authority、protection 或 transform 的具体阻断事实。
- Current schema 原子改用 `output_slot_count` 表达检测与输出身份；被替代的
  `selected_count`、跨 count work/dominance 字段、reason、tests 与 reader 同批删除，
  不保留 alias、shim 或双 schema。

切换后的验收合同是：

- fixed/explicit 的输出 slot 数必须精确等于权威 count。
- auto 的输出 slot 数必须精确等于唯一匹配片夹的有效容量。
- 黄金 partial auto 使用 source-coordinate、保持顺序的一对一包含匹配：每个用户确认
  polygon 必须完整落入某个输出 footprint；确认照片 ordinal 不要求等于 holder slot
  ordinal，额外输出允许为空白。
- 51 条 partial filename count 只作 validation-only lower bound，永不进入 detector。
  Approved auto 不得少于该 annotation；精确 count 命中率降为非目标诊断。
- 正式性能继续按输入张数认证，但必须重新记录实际 frame TIFF 数、额外 slot 分布与
  write/read-back 成本。搜索减少不能替代真实 I/O 性能复测。

## 2. 单向运行流

```text
RuntimeOptions
  -> FrameCountRequest
  -> DetectionConfigurationBundle
  -> TIFF profile + source pixels
  -> base gray + exact MeasurementCache
  -> ScanCanvasEvidence
  -> canonical lane domains
  -> SourceContentObservation
  -> LongAxisSeparatorMeasurementField
  -> separator bands / edge-pairs / learned one-sided observations
  -> bounded placement + local corridors + ordered DP
  -> FrameGridProposal + per-count dominance
  -> FrameSlot + SafeCropEnvelope
  -> fixed millimetre protection
  -> CandidateGate
  -> DecisionGate
  -> FinalDetection
  -> one inverse-affine source sample per ROI
  -> TIFF write + read-back validation
  -> report / Debug / run manifest
```

权限只沿这条链路向下游移动。Report 和 Debug 只能读取已经完成的事实，不能重测、重选或
重判。DecisionGate 后不得改变 selected count、transform 或 boxes。

## 3. 输入与配置

### 3.1 `FrameCountRequest`

`x5crop/configuration/model.py` 是 count request 的唯一 owner：

| 用户入口 | Typed mode | Candidate set |
|---|---|---|
| Full 省略 count | `fixed_full` | `(default_count,)` |
| Full 显式默认 count | `fixed_full` | `(default_count,)` |
| Partial 整数 | `explicit` | `(requested_count,)` |
| Partial 省略、回车或 `auto` | `auto` | `1..default_count` |

Full 的其它显式 count 被拒绝。`135-dual` 不支持 partial。没有独立
`--auto-count`；lower layer 不接收裸 `None`。

`StripHandlingSpec` 只拥有 `default_count` 与 `partial_mode_supported`。Partial 范围由
两者确定，不存在第二份 count 表。

### 3.2 Scan-canvas 容量

`ScanCanvasPhysicalSpec.format_fits` 是 format 适用关系与最大张数的唯一 owner：

- Explicit/fixed 先按 requested count 排除容量不足的 profile，再唯一匹配 canvas。
- Auto 先按 format 唯一匹配 canvas，再用该 profile 容量收窄 count candidates。
- Count 不缩短 validation domain，不选择最近 profile。

`ScanCanvasEvidence` 独占 long/short axis-scale intervals。`SourceLaneEvidence` 可以只读
携带这些 intervals，但不是 scale authority。TIFF resolution 不参与检测。

### 3.3 运行并发

普通入口默认 `STANDARD_JOB_DEFAULT = 2`，只在用户显式传入更高 `--jobs` 时使用
`STANDARD_JOB_LIMIT = 3`。诊断模式单独保留 `DIAGNOSTICS_JOB_LIMIT = 4`。Runtime
boundary 在建立 `RunConfig` 时执行上限归约；lower layer 只读取归约后的正整数，不根据
硬件、文件名或 detection 结果自适应改变并发。

并发单位是相互独立的输入 TIFF。三 worker 是内存充足机器处理至少三张输入时的 opt-in
吞吐选项，不是新的默认值或性能通过条件。正式性能认证继续固定 `--jobs 2`。

## 4. 物理与 measurement owner

| Concept | 唯一 owner | 禁止事项 |
|---|---|---|
| 照片设计尺寸 | `FrameDesignApertureMm` | 片夹或 runtime 不复制 |
| 片夹尺寸、适用 format、容量 | `ScanCanvasPhysicalSpec` | count 不发明尺寸 |
| px/mm scale | `ScanCanvasEvidence` | lane/source-core 不重新计算 |
| lane/domain/positive content | `source_core.py` | 不创建 separator 或 Grid |
| separator field/band/edge-pair/one-sided | `detection/evidence/separator.py` | 不依赖 positive-content components |
| prior | `configuration/grid.py` | 不冒充 observation |
| Grid/slot/envelope selection | `detection/grid/` | 不创建 final status |
| protection | `detection/protection.py` | 不修改未保护 proposal |
| transform assessment | `detection/output_geometry.py` | 不在 DecisionGate 后改变 |
| final status/reasons | `DecisionGate` | CandidateGate 不保存 final reason |

### 4.1 Positive content

Source content 使用独立 intensity 与 texture field、严格 4-connectivity 和不可变 RLE：

```text
intensity = abs(I - five_point_local_mean(I)) / 255
texture   = (abs(dx) + abs(dy)) / 510
positive  = intensity_supported AND texture_supported
```

它只提供 source-coordinate containment/placement facts。Positive activity 不是照片边、
separator 或 Grid 观测；无法可靠识别 primary content 时，对应 containment 可以保持
`UNAVAILABLE`，而不是制造 review。

### 4.2 Separator evidence

每个 lane 只从 base-gray 建立一次 vectorized long-axis adjacent-difference field。字段和
line observations 都携带 `MeasurementIdentity.SEPARATOR_FIELD` provenance，且不读取
content components。

在每个 design component 的 gutter interval 内：

- 每条 line 通过有序二分区间查询 compatible successor；
- 每条 line 最多保留 2 个 successor；
- transition pair 形成 typed `SeparatorBandObservation`；
- band 保存 leading/trailing transition、band/width/center interval、support 与
  appearance；
- 至少两个 retained bands 才能形成 outward hull 的 learned gutter；
- one-sided observation 必须携带该 learned gutter，另一侧才可在 local corridor 内推断；
- report 记录 raw lines、query、compatible pairs、retained bands 与截断量。

任何 separator observation 仍需绑定 local corridor 与 ordinal 才能参与 proposal。它不
单独证明 Grid。

## 5. Calibration 与 prior

Tracked `CalibrationReceipt` 固定记录：

- source SHA 集合；
- algorithm/config revision；
- format、mode、aperture component、orientation、count；
- partial placement 与 interaction class；
- candidate/work distribution；
- canonical `calibration_receipt_id`。

八张 nominal 样片只校准 prior 中心与典型搜索区间；S098 只作 stress；其余 102 条只提供
measurement/coverage 分布。Confirmed `Photo start/end` 不进入 runtime separator/photo-edge
observation，也不能证明 Grid。Receipt provenance 始终保留
`user_confirmed_geometry`。

Runtime 只读取 tracked typed prior 与 receipt ID，不读取 `Test/`、baseline 或现场
calibration 输出。XPan 与 120-645 使用明确 `physical_rule` prior 和 synthetic contracts，
不借用最近格式。

`FrameGridSearchPrior` 是 search authority，只保存 pitch、gutter、full margins、
uncertainty、equality interval 与 provenance。经验范围不能升级为“未见过即失败”的硬
边界。

## 6. Bounded Grid

### 6.1 Placement 与 corridors

每个 count/lane/component 建立 observed start/end 与 leading、trailing、centered model
seeds。Seed 只表达有限 placement hypothesis，不是 observation。按 equality interval 去重
后固定：

```text
P_MAX = 6
```

每个 internal corridor 最多：

```text
O_MAX = 2  # image-observed candidates
K_MAX = 3  # O_MAX + one model-only candidate
```

Count 1 没有 internal corridor，interaction 与对应 dominance dimension 都是结构性
`NOT_APPLICABLE`。

### 6.2 Ordered DP 与真实工作量

DP state 只包含当前 corridor 与 candidate。Transition 要求位置严格递增并能形成正面积
半开 slot。每个 seed 每层只保留 `K_MAX` states；统计记录实际保留 state 与实际尝试
transition，不以事后 clamp 伪装上限。

对 count `C`、internal corridor `B = C - 1`，每个 lane/component：

```text
states <= P_MAX * B * K_MAX

transitions <= P_MAX * (
  min(B, 1) * K_MAX
  + max(B - 1, 0) * K_MAX^2
)
```

因此：

| Scope | States | Transitions |
|---|---:|---:|
| count 12，每个 lane/component | 198 | 558 |
| auto 1..12，每个 lane/component | 1188 | 3168 |

Report 同时保存逐 count/lane/component 明细，并按实际 lane/component 数汇总。Dual lane
分别搜索，不建立 lane proposal 笛卡尔积。

### 6.3 Hard rejection

Hard rejection 只允许来自：

1. count 与 request 或 scan-canvas 容量冲突；
2. 非单调、非正面积或其它非法 geometry；
3. fixed protection 前的 geometry 越出 source/lane authority；
4. 已知 primary content 无法有界完成 ordinal assignment 或 containment。

缺少 separator、blank、model-only、较低 score、较大的有界 outward retention 与
protection 饱和都不是 hard rejection。

### 6.4 Dominance、截断与 selection

每对跨 count proposal 生成 typed `FrameCountDominanceAssessment`。当前逐维记录：

- endpoint support；
- two-sided slot balance 与其 observed slot 次序；
- observed boundary balance；
- internal-corridor observed support；
- content assignment 与 authority。

`two-sided slot balance = observed two-sided slots - other slots`，先按 balance、再按
observed slot 数形成 typed 次序；`observed boundary balance = observed boundaries -
model-only boundaries`。这两个余额避免直接比较天然随 count 增长的原始数量，也允许
前导或尾随 blank 作为安全 slot 保留。

Count 1 的 internal-corridor 维度为 `NOT_APPLICABLE`。Endpoint 与 raw
internal-corridor support 保留为审计事实，但不单独参与 dominance，避免单张局部
edge-pair 或未证明的 separator 数量重新变成严格审批门槛。两个观测余额及
content/authority 只有全部不差且至少一项更好时才能形成支配。

Geometry、ordinal、ownership 或 containment 已为 `CONTRADICTED` 的 proposal 属于允许的
hard rejection。只要存在无硬矛盾 proposal，它就不进入跨 count selection pool；若所有
proposal 都有硬矛盾，则保留它们交给 CandidateGate/DecisionGate 产生具体 typed reason，
不把风险藏成空结果。

Residual 先按 prior 的 equality interval 归约为 left/right/equal；浮点微差不能产生严格
更好。Safe-envelope 像素大小不参与跨 count dominance。Scalar score 和稳定 tie-break
只排序现有结果。

同一 count/component 的已构建 seed 也先做 typed 非支配，不能由 scalar 静默删除。若各
候选中同一 ordinal 的起点分歧经 equality interval 归约后仍小于最小相邻 slot step，或
所有候选 slot 都是 blank/unavailable，则视为 output-equivalent 并按 ordinal outward
union。否则保留选定 count 但把 `slot_ownership` 标为 `CONTRADICTED`；达到整 pitch 的
placement 竞争因此送审，而 partial 的有界前后摆放、贴近几何微差和 blank 不送审。不同
physical aperture component 采用相同的 output-equivalence/ownership 规则后再 outward
union。

每个 lane 合并全部 count 与 components 后最多保留：

```text
G_MAX = 3
```

`G_MAX` 不是每个 count 各 3 个。不同 count 的非支配竞争使 `frame_count` 阻断。局部
`search_incomplete`、结构截断或预算信息本身只作诊断；只有被省略方案可能改变 count、
ordinal、primary ownership、containment 或 authority 时，`omitted_outcome_risk` 才让
`grid_search_coverage` 进入 `CONTRADICTED`。不存在 wall-clock early-best。

## 7. Slot、interaction 与 envelope

每个 proposal 产生恰好 count 个有序 lane-local `FrameSlot`。Blank 不删除 slot；
appearance unavailable 不改变 count。

每个 internal corridor 保存：

- `separated`
- `contact`
- `overlap`
- count 1 或端点处的 `not_applicable`

浮点位置先经过 equality interval 归约。Observed/model interval 形成 bounded shared
interval，完整并入相邻两侧安全包络，因此相邻输出允许重叠。

`SafeCropEnvelope` 是 fixed protection 之前的 outward geometry：

- 首尾 endpoint 独立；
- component/output-equivalent alternatives 按 ordinal outward union；
- 短轴使用完整 authoritative lane；
- 未保护 geometry 越界直接失败，不 clamp。

固定 protection 的毫米值按 format 冻结。Long/short axis 分别使用
`ScanCanvasEvidence` 对应 scale interval 的 upper endpoint 向上取整。只有 protection
可以在 source/lane authority 饱和；饱和 side 进入 `ProtectedCropEnvelope` receipt。

## 8. Gate 与 finalization

### 8.1 CandidateGate

CandidateGate 只建立十项有序事实：

```text
scan_canvas_authority
source_content_measurement
grid_search_coverage
frame_count
slot_ordinal_assignment
slot_ownership
known_content_containment
source_lane_geometry
output_protection
output_transform
```

`source_content_measurement`、ownership、containment、geometry 与 transform 使用
`NOT_CONTRADICTED` 语义；缺失或无法证明不是自动失败。Scan canvas、frame count 与
protection 必须 `SUPPORTED`。CandidateGate 不保存 final reason。

### 8.2 DecisionGate

DecisionGate 是 final status 与 reason 的唯一 owner：

- 全部 requirements 满足：`approved_auto`
- 存在 blocking fact：`needs_review`

Count 阻断按输入模式区分 `automatic_count_unresolved` 与
`requested_count_unfulfilled`。其它 reason 与十项 Gate code 一一绑定。Finalization 只
冻结已有 selected count、transform、protected envelopes 与 source boxes。

当前 transform 为 typed identity。Advanced fit 或 deskew 只有未来出现 named gap 时才可
加入；缺少 deskew 不阻断。

## 9. TIFF output 与失败状态

普通 approved 输入对每个 ROI：

1. 从原 source array 做一次 inverse-affine sampling；
2. 写临时 TIFF；
3. 复读临时 TIFF；
4. 验证像素与 profile；
5. 原子替换为最终文件。

验证覆盖 dtype、axes、shape、channels、Photometric、BitsPerSample、SampleFormat、
planar configuration、ICC、resolution、resolution unit、description、datetime、software、
支持的 extra tags 与 lossless compression。`same` 保持源 NONE/LZW 等已知无损行为；
`none` 写无压缩。

任一读取、写出、复读或替换错误返回 `FailedInput` 与独立 failure stage。它不进入
DecisionGate，不修改既有 decision，也不生成成功 receipt。

`--diagnostics` 是只读 output action：仍完成相同 detection、Gate 与 final boxes，report
记录 `diagnostics_read_only`，但不写 frame TIFF 或 review copy。

## 10. Cache、report 与 Debug

`MeasurementCacheKey` 只包含：

- workspace gray identity；
- work layout；
- base-gray parameters；
- image-statistics parameters。

Cache value 只保存不可变 work gray 与 exact image statistics。Count、offset、seed、
candidate、proposal、Gate、decision、reason 和 output box 都不得进入 cache。

Current report：

```text
schema_id       = detection_report
schema_revision = bounded_safe_crop_grid
```

Report 保存 typed configuration/count identity、calibration receipt、measurement provenance、
逐 count/lane/component proposal/work、separator query work、dominance、slots、interactions、
safe/protected envelopes、两级 Gate、finalization、TIFF receipt 与 output identity。
Measurement wall time 不进入 `core_facts_sha256`。

Debug preview 只显示已选 separator、Grid、protected boxes、status 与 reasons，不重新运行
detector。

## 11. 验收与性能边界

唯一真实 accuracy gate 是九张 source-SHA-bound、用户确认 geometry 的黄金样片，展开为
14 个 fixed/explicit/auto 场景。12 个 `must_approve_safe` 必须批准；S055 两个场景只有在
具体 Gate 阻断时才允许 review。四张 pass partial 的 auto 场景必须命中 confirmed count。

Containment 只比较 inverse-transform 后的 source footprint 是否完整包含 confirmed
polygon；不比较 IoU、历史 box parity 或贴边误差。

111 条 manifest 是非阻断 coverage audit：

- 只消费 canonical current records，不盲扫 `Test/`；
- filename annotation 只作 validation；
- 重复 source SHA 分组报告；
- 51 条 partial 输出 count confusion matrix；
- 41 条 pass partial 输出质量指标；
- `real_holdout = unavailable`；
- XPan、120-645 等缺口标记 `real_sample_coverage = unavailable`。

正式性能使用固定 24 张、`--jobs 2`、一个新空 root：

```text
cold/
measured-1/
measured-2/
measured-3/
```

Full 使用 `fixed_full`，partial 使用 `auto`。输入只按 local manifest 的 canonical
`source_relative_path` 解析并复核 source SHA；同 SHA 的 baseline symlink 或其它复制
文件不参加 source discovery。四次都写出并复读全部 frame TIFF；认证只取三次 measured
的中位数，合同为 `<= 5.0 秒/张`。Performance schema 为
`x5crop_production_performance_v3`。

## 12. 源码职责

| 路径 | 当前职责 |
|---|---|
| `x5crop/configuration/` | count request、prior、scan-canvas 与 runtime configuration |
| `x5crop/formats/` | design aperture、strip contract、scan-canvas catalog |
| `x5crop/detection/source_core.py` | lane/domain/positive-content facts |
| `x5crop/detection/evidence/` | scan-canvas 与 separator observations |
| `x5crop/detection/grid/` | placement、corridor、DP、proposal、dominance、slot/envelope |
| `x5crop/detection/protection.py` | fixed millimetre protection |
| `x5crop/detection/candidate/` | CandidateGate facts |
| `x5crop/detection/decision/` | final status 与 reasons |
| `x5crop/detection/final/` | immutable finalization |
| `x5crop/export/`、`x5crop/io/` | one-sample ROI 与 TIFF write/read-back |
| `x5crop/report/`、`x5crop/debug/` | current audit surfaces |
| `tools/regression/` | comparator、黄金验收、coverage、profiling、性能 |
| `tools/verify` | tracked contracts 的唯一验证入口 |

修改 runtime flow 或 source layering 时更新本文；版本行为、验证、打包或回滚背景更新
`CHANGELOG.md`。
