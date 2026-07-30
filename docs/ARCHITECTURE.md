# X5 Crop V4.9 当前架构

本文只描述当前运行流、数值合同、权限与源码分层。版本历史见
[CHANGELOG.md](CHANGELOG.md)，用户操作见中英文用户手册，跨会话检查点只属于
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## 1. 产品与安全合同

X5 Crop 在用户提供 format 后生成保守裁切，目标是不内切真实照片内容，而不是唯一恢复
真实物理边界或复制历史 boxes。

- Format 始终是 runtime authority。
- Full 使用格式默认 slots；partial 的 explicit count 是 authority。
- Partial auto 输出唯一匹配片夹对该 format 的全部有效 slots。它不推断或声明真实照片
  张数。
- `approved_auto` 只表示 protection 后的输出满足有界安全合同。
- 输出允许向外多保留、相邻框重叠、保留 blank slot 或带入相邻照片像素。
- `needs_review` 只用于具体且无法吸收的 ordinal、primary ownership、containment、
  source/lane authority、omission coverage 或 output geometry 风险。
- Separator 缺失、blank、inferred Grid、等价 geometry、未 deskew 和 protection 饱和
  都不能单独制造 review。
- I/O 失败是独立 terminal failure，不能转成 review。

当前系统是 current-only 原子实现。Runtime、tests、tools、report 与 Debug 只消费
`bounded_safe_crop_capacity_grid`；没有 feature flag、双 schema、兼容 reader、fallback、
alias 或 shim。

## 2. 单向运行流

```text
RuntimeOptions
  -> FrameCountRequest
  -> DetectionConfigurationBundle
  -> TIFF profile + source pixels
  -> base gray + exact MeasurementCache
  -> ScanCanvasEvidence
  -> ResolvedOutputSlots
  -> canonical lane domains
  -> SourceContentObservation
  -> LongAxisSeparatorMeasurementField
  -> separator bands / edge-pairs / learned one-sided observations
  -> one slot-count bounded placement + local corridors + ordered DP
  -> output-equivalence classes + omission proof
  -> FrameGridProposal
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
重判。DecisionGate 后不得改变 profile、slots、transform 或 boxes。

## 3. 输入、容量与 identity

### 3.1 `FrameCountRequest`

`x5crop/configuration/model.py` 是 count request 的唯一 owner：

| 用户入口 | Typed mode | `authoritative_count` |
|---|---|---:|
| Full 省略 count | `fixed_full` | format 默认值 |
| Full 显式默认 count | `fixed_full` | format 默认值 |
| Partial 整数 | `explicit` | 用户整数 |
| Partial 省略、回车或 `auto` | `auto` | `None` |

Full 的其它显式 count 被拒绝。`135-dual` 不支持 partial。没有独立
`--auto-count`；lower layer 只接收 typed request。

`StripHandlingSpec` 只拥有 `default_count` 与 `partial_mode_supported`。Partial explicit
范围为 `1..default_count`。

### 3.2 `ScanCanvasEvidence` 与 `ResolvedOutputSlots`

`ScanCanvasPhysicalSpec.format_fits` 是 format 适用关系与最大容量的唯一 owner：

- Fixed/explicit 先按权威 count 排除容量不足的 profile，再唯一匹配 canvas。
- Auto 先按 format 与实际画布唯一匹配 profile，再读取该 fit 的
  `maximum_frame_count`。
- 不选择最近 profile，也不建立第二份容量表。

`ScanCanvasEvidence` 独占匹配状态、selected profile 和 long/short axis-scale intervals。
`SourceLaneEvidence` 可以只读携带 scale intervals，但不是 scale authority。TIFF
resolution 不参与检测。

解析结果只有：

```python
ResolvedOutputSlots(
    lane_output_slot_counts=(...),  # canonical lane 顺序
)
```

`output_slot_count` 只由 lane counts 求和。Candidate 与 `FinalDetection` 引用同一个
resolution；report 现场派生并校验总数，不保存另一份权威整数。

`135-dual` 固定 lane counts `(6, 6)`。输出顺序为 `lane:0/1..6`，再
`lane:1/1..6`；每个输出同时保存 global output ordinal、lane ID 与 lane-local ordinal。

### 3.3 Configuration identity

`DetectionConfiguration.detector_kind` 固定为：

```text
bounded_safe_crop_capacity_grid
```

Configuration identity 只保存输入 policy：

- full：`format_default`
- partial explicit：`user_explicit` 与权威整数
- partial auto：`scan_canvas_capacity`

Resolved profile、lane counts 与 slot identities 只进入 analysis/output identity。

### 3.4 运行并发

普通入口默认 `STANDARD_JOB_DEFAULT = 2`，用户可显式使用
`STANDARD_JOB_LIMIT = 3`。诊断模式单独保留 `DIAGNOSTICS_JOB_LIMIT = 4`。Runtime
boundary 在建立 `RunConfig` 时归约；lower layer 不根据硬件、文件名或检测结果改变并发。

三 worker 是内存充足机器处理至少三张输入时的 opt-in 吞吐选项。正式性能认证固定使用
`--jobs 2`。

## 4. 物理与 measurement owner

| Concept | 唯一 owner | 禁止事项 |
|---|---|---|
| 照片设计尺寸 | `FrameDesignApertureMm` | 片夹或 runtime 不复制 |
| 片夹尺寸、适用 format、容量 | `ScanCanvasPhysicalSpec` | Grid 不发明容量 |
| profile、px/mm scale | `ScanCanvasEvidence` | lane/source-core 不重新计算 |
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

Tracked calibration receipt 使用
`x5crop_grid_calibration_receipt_v2`，固定记录：

- source SHA 集合；
- algorithm/config revision；
- format、mode、aperture component、orientation、slot count；
- partial placement 与 interaction class；
- candidate/work distribution；
- single resolved slot count、equivalence-only union 与 omission-proof 合同；
- canonical `calibration_receipt_id`。

当前 identity：

```text
GRID_ALGORITHM_REVISION   = bounded_ordered_capacity_grid_v5
GRID_CONFIGURATION_REVISION = safe_crop_prior_v1
CALIBRATION_RECEIPT_ID    = sha256:f6edbfd78d1711b361113abc952b37884bf594dd367ba22cd64f316e42f94738
```

八张 nominal 样片只校准 prior 中心与典型搜索区间；S098 只作 stress；其余真实记录只提供
measurement/coverage 分布。Confirmed `Photo start/end` 不进入 runtime
separator/photo-edge observation，也不能证明 Grid。Receipt provenance 保留
`user_confirmed_geometry`。

Runtime 只读取 tracked typed prior 与 receipt ID，不读取 `Test/`、baseline 或现场
calibration 输出。XPan 与 120-645 使用明确 `physical_rule` prior 和 synthetic contracts，
不借用最近格式。

`FrameGridSearchPrior` 是 search authority，只保存 pitch、gutter、full margins、
uncertainty、equality interval 与 provenance。经验范围不能升级为“未见过即失败”的硬
边界。

## 6. 单容量 Bounded Grid

### 6.1 Placement、corridors 与 ordered DP

每个 lane 只搜索 `ResolvedOutputSlots` 指定的一个 slot count。Placement seeds 来自
full-leading、full-trailing、centered model 或 positive-content placement；它们只表达
有限 hypothesis，不是 separator observation。

应用上限前，精确 descriptors 先按 equality/equivalence 归约。固定上限为：

```text
P_MAX = 6  # 每个 lane/component 的 placement seeds
O_MAX = 2  # 每个 internal corridor 的 observed classes
K_MAX = 3  # 每个 corridor/DP frontier 的总 classes，含 model-only
```

Count 1 没有 internal corridor，对应 interaction 固定为 `NOT_APPLICABLE`。

DP transition 要求位置严格递增、shared interval 小于一个 pitch，并能形成正面积半开
slot。对 count 12，每个 lane/component 最多 198 states、558 transitions。Report
保存逐 lane/component 工作量，并乘实际 lane/component 数汇总。

### 6.2 Output-equivalence selection

Score、residual 与 tie-break 只决定构建顺序和诊断展示，不能选择最终赢家。只有同时满足
以下条件的 proposals 才属于同一 output-equivalence class：

- lane、slot count、canonical ordinal 与 known-content assignment 一致；
- 浮点差先按冻结 equality interval 归约；
- slot phase 差不形成整 pitch ordinal 偏移；
- 按 ordinal outward union 后仍单调、合法且位于 source/lane authority。

同一 class 合并 seed、corridor path 与 aperture-component members，并按 ordinal outward
union。全 blank 仍执行相同 geometry、authority 与 union 检查。

只有最终恰好一个 class 且 omission coverage 成立时才产生 selected proposal。若存在两个
或更多非等价 classes，whole-pitch/ordinal 分歧阻断 `slot_ordinal_assignment`，
known-content/primary owner 分歧阻断 `slot_ownership`；不得由 scalar 排序选出赢家。

### 6.3 Hard rejection

Hard rejection 只允许来自：

1. slot count 与 request 或 scan-canvas 容量冲突；
2. 非单调、非正面积或其它非法 geometry；
3. fixed protection 前的 geometry 越出 source/lane authority；
4. 已知 primary content 无法有界完成 ordinal assignment 或 containment。

缺少 separator、blank、model-only、较低 score、较大的有界 outward retention 与
protection 饱和都不是 hard rejection。

### 6.4 Omission proof

`GridOmissionSummary` 对 placement-seed、observed-corridor 和 DP-frontier scope 保存：

- 确定性 `scope_id`；
- lane/component、适用的 `seed_id` 与 corridor ordinal；
- discovered、retained、omitted 数；
- 每个 omitted alternative 的稳定 ID；
- absorbing equivalence-class ID；无法吸收时为 `None`；
- absorbed 与 unresolved outcome 数。

IDs 只由 canonical identities、assignment signature 与排序后的 member IDs 构造，不受
score 或遍历顺序影响。只有每个 omitted alternative 都已证明属于 retained class，并已
进入 outward union，截断才不阻断。

任一 omitted alternative 非等价、无法分类，或预算耗尽导致证明未完成时：

- `grid_search_coverage = CONTRADICTED`
- 不产生 selected proposal 或自动输出

`omitted_outcome_risk` 只能从 summaries 派生。`search_incomplete` 只作诊断，不是默认
风险结论，也不是可靠性证据。

## 7. Slot、interaction 与 envelope

每个 proposal 产生恰好 resolved count 个有序 lane-local `FrameSlot`。Blank 不删除 slot；
appearance unavailable 不改变容量。

每个 internal corridor 保存：

- `separated`
- `contact`
- `overlap`
- count 1 或端点处的 `not_applicable`

浮点位置先经过 equality interval 归约。Observed/model interval 形成 bounded shared
interval，完整并入相邻两侧安全包络，因此相邻输出允许重叠。

`SafeCropEnvelope` 是 fixed protection 之前的 outward geometry：

- 首尾 endpoint 独立；
- 同一 equivalence class 的 alternatives 按 ordinal outward union；
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
output_slot_count
slot_ordinal_assignment
slot_ownership
known_content_containment
source_lane_geometry
output_protection
output_transform
```

`output_slot_count` 状态固定为：

- scan canvas 尚未解析：`NOT_APPLICABLE`，只由 `scan_canvas_authority` 阻断；
- resolution 已建立且每个 lane 精确形成所需 slots：`SUPPORTED`；
- 容量已解析但任一 lane 无法精确形成 slots：`CONTRADICTED`。

CandidateGate 不保存 final reason。

### 8.2 DecisionGate

DecisionGate 是 final status 与 reason 的唯一 owner：

- 全部 requirements 满足：`approved_auto`
- 存在 blocking fact：`needs_review`

`output_slot_count` 阻断按输入模式生成：

- fixed/explicit：`requested_count_unfulfilled`
- auto：`capacity_output_slot_count_unfulfilled`

其它 reason 与 Gate code 一一绑定。Approved 必须满足：

```text
slots == safe envelopes == protected envelopes == final boxes
      == output TIFFs == derived output_slot_count
```

Review 的 output TIFF 数固定为零。Finalization 只冻结已有 profile、slots、transform、
protected envelopes 与 source boxes。

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

Cache value 只保存不可变 work gray 与 exact image statistics。Slot count、offset、seed、
candidate、proposal、Gate、decision、reason 和 output box 都不得进入 cache。

Current schemas：

```text
detection report       = bounded_safe_crop_capacity_grid
run manifest           = x5crop_run_manifest_v2
fixed sample profile   = x5crop_fixed_sample_profile_v2
production performance = x5crop_production_performance_v4
```

Report 保存 typed configuration policy、calibration receipt、measurement provenance、
selected profile、canonical lane counts、slot identities、equivalence classes、omission
summaries、逐 lane/component 工作量、separator query work、slots/interactions、
safe/protected envelopes、两级 Gate、finalization、TIFF receipt 与 output identity。总 slot
数只从 lane counts 派生并交叉校验。Measurement wall time 不进入
`core_facts_sha256`。

Debug preview 只显示已选 separator、Grid、protected boxes、status 与 reasons，不重新运行
detector。

## 11. 验收与性能边界

### 11.1 黄金 accuracy gate

唯一真实 accuracy gate 是九张 source-SHA-bound、用户确认 geometry 的黄金样片，展开为
14 个 fixed/explicit/auto 场景。12 个 `must_approve_safe` 必须批准；S055 两个场景只有在
具体 Gate 阻断时才允许 review。

Golden comparator 使用 source-coordinate、严格递增的一对一 containment：

- 每个 confirmed polygon 必须完整落入一个不可复用的 output footprint；
- slot identity 必须递增；
- 允许额外 blank slots；
- 多个合法匹配记录字典序最早结果；
- 同时比较 profile、canonical lane counts、global/lane-local identities 与 transform。

不比较 IoU、历史 box parity 或贴边误差。

### 11.2 111 条 blocking coverage audit

Audit 只消费 manifest 的 canonical current records，不盲扫 `Test/`。Filename annotation
只属于 validation，永不进入 runtime。完成门槛为：

- 88 条 `pass_*` 全部 `approved_auto`，包括 S098；
- 41 条 pass partial 全部批准，并精确输出匹配片夹容量；
- 23 条 `unknown_*` 只有存在具体 CandidateGate 阻断时才允许 review；
- 重复 source SHA 分组报告，record 数不冒充独立样片数。

`real_holdout = unavailable`。XPan、120-645 与其它缺少真实样片的 cell 保存
`real_sample_coverage = unavailable`；覆盖缺口只限制验证声明，不制造 runtime review。

### 11.3 正式性能

正式性能使用固定 24 张、`--jobs 2`、一个新空 root：

```text
cold/
measured-1/
measured-2/
measured-3/
```

Full 使用 `fixed_full`，partial 使用 `auto`。Runner 从冻结 cohort、实际 TIFF、
scan-canvas catalog 与 validation annotations 动态计算 profile、lane counts 和 totals，
不维护第二份容量表。四次都写出并复读全部 frame TIFF；当前 receipt 必须为每次 168 个
输出 TIFF，九个 partial 输入相对 annotation 多 25 个 slots。认证只取三次 measured
的中位数，合同为 `<= 5.0 秒/张`。

## 12. 源码职责

| 路径 | 当前职责 |
|---|---|
| `x5crop/configuration/` | count request、prior、scan-canvas 与 runtime configuration |
| `x5crop/formats/` | design aperture、strip contract、scan-canvas catalog |
| `x5crop/detection/source_core.py` | lane/domain/positive-content facts |
| `x5crop/detection/evidence/` | scan-canvas 与 separator observations |
| `x5crop/detection/grid/` | placement、corridor、DP、equivalence、omission、slot/envelope |
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
