# X5 Crop V4.9 当前架构

本文是当前运行流、数值合同和源码分层的唯一 owner。历史与版本级变化见
[CHANGELOG.md](CHANGELOG.md)。

## 1. 产品边界

V4.9 在用户提供 format 后，从原 TIFF 重建每张照片的 source-coordinate 四边，形成安全
输出：

- full 使用格式固定张数；
- partial explicit 严格使用用户 count；
- partial auto 使用唯一匹配片夹对该 format 的容量，并保留 blank slots；
- 目标是零真实内容 inward loss，同时使额外面积可由边界不确定度、插值 allowance 和固定
  protection 重算；
- 非空照片的保护后输出还必须在 direct-use budget 内，使用户无需人工二次裁切；
- 人工成本优先级为：零 inward loss > 避免过宽非空输出 > 减少可直接删除的 blank TIFF；
- 无法由 protection 吸收的 placement、ordinal、ownership、containment、lane authority
  或 transform 风险进入 `needs_review`。

系统不猜 format，不从文件名读取 runtime count，也不要求复刻 V4.2.8 的裁切框。

## 2. 单向权限流

```text
runtime format/count
→ source TIFF decode/base gray
→ ScanCanvas/lane/scale authority
→ registered search proposals
→ complete pixel measurement
→ physical constraint propagation
→ complete FrameGeometryState
→ lane-local ordered DP
→ CandidateGate
→ DecisionGate
→ source geometry + output transform
→ inverse-affine ROI sampling
→ TIFF write/readback
→ report/debug
```

三类输入不得混淆：

| 类别 | 可以做什么 | 不可以做什么 |
|---|---|---|
| Pixel observation | 产生 transition、line、support、residual、angle 与 measurement uncertainty | 消费 expected position 作为边界 |
| Physical constraint | 用 format、count、scale、aperture tolerance、lane 与邻接筛选或推断 | 冒充 observed edge |
| Search proposal | 由 Grid、outer、corridor 决定查询域与顺序 | 进入 measurement uncertainty 或最终边界 |

`CandidateGate` 只记录候选事实；只有 `DecisionGate` 创建 final status 和 final reasons。

## 3. Format、count 与片夹 authority

`FramePhysicalSpec` 独占设计 aperture；`FrameApertureToleranceMm` 固定为长短轴各
`0.5 mm`。对 ScanCanvas 提供的轴向 scale interval：

```text
W_px = [(long_mm - 0.5) × long_scale_min,
        (long_mm + 0.5) × long_scale_max]

H_px = [(short_mm - 0.5) × short_scale_min,
        (short_mm + 0.5) × short_scale_max]
```

`dimension_search_allowance_mm=1.0` 只扩大查询域，不进入 inference uncertainty。
120 的 `54/56 mm` aperture label 是 lane 级选择，不允许逐帧混用。

`ResolvedOutputSlots` 是输出数量的唯一 owner：

- `fixed_full` 与 `explicit` 给出权威 N，不跨 count 搜索；
- `auto` 从唯一 `ScanCanvasFormatFit` 得到 lane capacity；
- `135-dual` 使用 `(6, 6)`，全局顺序为 lane 0 后 lane 1；
- auto capacity 不表示真实照片数。

## 4. Source workspace 与 content

`DetectionWorkspace` 只建立一份 canonical `source_gray`。`ScanCanvasEvidence` 决定 profile、
lane、long/short px/mm interval 与容量；TIFF resolution 只属于 I/O metadata。

`SourceContentObservation` 只帮助 ownership、containment 和候选选择，不创建照片边。为
避免整幅多通道 float field，content 对完整 source domain 做确定性分块测量：每块最多
`1,048,576` pixels，只长期保留 full-coverage boolean support 与最终 source-coordinate
components/row runs。阈值 sampling 与未分块算法使用相同的全局 flattened indices，不降低
空间分辨率。Report 记录 source pixels、streaming blocks、run/component 数量、canonical
row-run digest、component derivation、耗时和峰值临时内存；不展开全量 raw
component/run records。

## 5. 照片边界 measurement

### 5.1 Canonical 类型

`x5crop/detection/photo_geometry/` 独占：

- `PhotoBoundaryMeasurementField`：canonical source gray 与精确局部测量能力；
- `PhotoBoundaryMeasurementQuery`：source band/corridor、方向与 lattice；
- `PhotoBoundaryMeasurementSet`：完整 transitions 与 coverage receipt；
- `PhotoBoundaryMeasurementSpec`：唯一测量参数；
- `PhotoEdgeSearchCorridor`、`SequenceAnchorDiscoveryDomain`：search proposal；
- `FrameSequenceGeometryConstraintSet`、`FrameGeometryState`、
  `FrameSequenceGeometrySolution`：物理约束与完整状态；
- `FramePhotoGeometry`：非空照片的唯一 source geometry；
- `GridInferredBlankOutputGeometry`：capacity blank 的独立输出 geometry；
- `SafeCropEnvelope`：照片 geometry 的唯一未保护/保护输出派生。

### 5.2 冻结参数

```text
lattice spacing       clamp(expected_support/12, 2.0 mm, 4.0 mm)
local window          0.25 mm
transition gap        0.05 mm
transition width max  1.0 mm
gradient_z minimum    3.0
tone/texture z        max(tone_z, texture_z) >= 3.0
search angle max      4°
family connection     tan(4°) × lattice_step + 0.10 mm
missing lattice       at most one step
line fit              weighted Huber IRLS, exactly four rounds
Huber threshold       max(0.05 mm, 2.5 × MAD)
inlier threshold      max(0.10 mm, 3 × MAD)
angle uncertainty     2 × endpoint coordinate uncertainty / support span
minimum support       max(4 traces, 60% queried traces)
continuous support    at least 50% of coarse span
geometry equivalence  normal difference <= max(0.05 mm, 1 source pixel)
                      and intersecting angle intervals
```

Measurement 按最多 `1,048,576` source-pixel work units streaming。所有 query 在执行前登记；
任一 query 未完整完成时为 `UNAVAILABLE`，部分 transitions 不得被消费。

## 6. Top/bottom

`PhotoEdgeSearchCorridor` 由 ScanCanvas scale、`H_px`、名义中心、`1.0 mm` center offset、
`1.0 mm` search deviation 与 `4°` 倾角建立。完整 halo 为：

```text
ceil((0.25 + 1.0 + 0.05) mm × short_scale_max) + 1 source pixel
```

每个 lane 的 top/bottom 原始测量只执行一次。每帧只消费 format/count/anchor domain
预先声明的粗 long-axis support span，禁止先用已选中的 `S_i/E_i` 定义查询。

Top/bottom 成对验证：

- 高度落入 `H_px`；
- angle intervals 相容；
- support/coverage 完整；
- known content 位于两边之间；
- 不是 scanner/holder border pair。

一侧 observed 时可用 observed rotation、typed height interval 与 scale 推断另一侧；
inferred edge 不能反向支持 rotation、scale 或 observed edge。两侧均不可见时不创建照片边。
Rotation slope 可跨帧共享，intercept、support、residual 和 uncertainty 始终逐帧拥有。

## 7. Long-axis sequence 与锚点

每个 internal corridor 只测量一次，同时服务 `E_i` 和 `S_(i+1)`，并显式区分
`edge_pair`、`one_sided`、`contact`、`overlap`。

```text
E_i - S_i             ∈ W_px
S_(i+1) - E_i         ∈ observed adjacency 或 typed gutter interval
```

系统不要求先找到第一张。`SequenceAnchorDiscoveryDomain` 对权威 N/容量计算：

```text
T_min = N × W_px.min + Σ typed_gutter_min
τ_min = lane_start
τ_max = lane_end - T_min
AnchorDomain(q) = [τ_min, τ_max] + relative_interval(q)
```

查询域另加 `0.5 × lane_short_extent × tan(4°)` 与完整 halo。平移区间被切成 core 无缝的
half-open tiles；名义宽度是 `6.0 mm × long_scale`。Grid/outer 只改变 tile 执行顺序，
不能缩小覆盖，也不能根据早期 score 跳过或追加 query。

任意 observed start、end、internal adjacency 或 trailing edge都可以锚定 translation，并
向前或向后传播。无绝对 observed anchor 时：

- `PhotoSequenceTranslationAssessment=unresolved`；
- 不创建 `FramePhotoGeometry`；
- 不使用 expected Grid、outer bbox 或 placement union 假装照片位置已识别。

`PhotoSequenceExtentProposal` 只保存 Grid/content/outer 给出的查询顺序或 domain proposal。
只有在 proposal 内重新执行完整二维 transition 和 line fitting，才能升级为 observed edge。

## 8. 完整状态、限额与 DP

固定流水线：

```text
raw measurement
→ local line family
→ physical dedup
→ local dominance
→ interval propagation
→ indexed compatibility join
→ complete FrameGeometryState dedup/dominance
→ lane-local ordered DP
```

`FrameGeometryState` 已经组合 `S/E`、top/bottom、source polygon、rotation class、
sequence aperture label、ownership、interaction 与逐边 provenance/uncertainty。

- local observed non-dominated geometry class 超过 2 个：截断前 unresolved；
- 完整组合后 observed non-dominated state 超过 2 个：截断前 unresolved；
- 两个 protection 后仍不等价、且互不支配的完整 sequence states 也必须保留为明确竞争，
  不能在 report 中保留竞争状态却自动批准；
- DP 的 `K≤3` 指最多两个完整 observed states 加一个 model-only/blank state；
- partial auto 固定容量 slots，不枚举 `2^N` occupancy；
- lane chain 为 `O(N × K²)`。

Receipt 保存 raw transitions、line families、physical geometries、join 前后数量、dedup 后
数量、sequence phase classes、DP states/transitions、pixel queries、measurement reuse 与
peak temporary memory。

## 9. 照片、blank 与 translation assessment

`PhotoSequenceTranslationAssessment` 描述实际照片位置：

```text
observed_anchor
sequence_inferred
unresolved
not_applicable_no_photo_geometry
```

`GridSlotTranslationAssessment` 描述容量 Grid：

```text
observed_grid_anchor
scan_canvas_profile_bounded
model_bounded_output_equivalent
unresolved
```

没有照片锚点时不创建照片 geometry。若没有 assigned known content，且所有 Grid placements
对每个 ordinal 产生相同的 protected、clipped、half-open source footprint，允许生成
`GridInferredBlankOutputGeometry`；否则按 ordinal、ownership 或 containment 风险进入
Gate。Blank provenance 固定为 `grid_inferred_blank`，不冒充 observed photo。

## 10. 安全包络与 Deskew

照片输出从 `FramePhotoGeometry` 单向派生：

1. measurement uncertainty 或 inference uncertainty；
2. `1 source pixel` bilinear interpolation allowance；
3. format 固定毫米 protection；
4. source/lane clipping。

Writer 只接受 `SafeCropEnvelope | GridInferredBlankOutputGeometry`。

### 10.1 非空输出可用性合同

“可重算”只能证明额外面积有来源，不能证明输出仍可直接使用。对每个非空照片，运行流还需在
source coordinates 中按边计算 measurement/inference uncertainty、插值 allowance 与固定
protection 带来的外扩，并与用户确认的 direct-use budget 比较。

- 预算内：可继续参与 `approved_auto` 安全证明；
- 超出预算：是无法由 protection 吸收的具体输出可用性风险，必须经 CandidateGate 进入
  `needs_review`，且不得写出正式 TIFF；
- `GridInferredBlankOutputGeometry` 不参与该预算，因为 blank 可被用户低成本删除；
- 预算必须按边、以物理单位或显式 scale 映射表达，不能用总面积 clamp、历史 V4.2.8 box
  或候选 union 替代。

当前代码只完成了额外面积的来源重算、固定 protection 和 source/lane clipping；
`output_protection` 还只检查 resolved geometry 是否完整，尚未实现独立的非空 direct-use budget
硬门槛。该项是 V4.9 发布前的已知未闭合合同，不得用现有黄金零 inward loss 成绩代替。

Rotation 只使用 selected observed top/bottom photo lines；这些沿照片长轴的观测拥有
shared strip deskew authority。Start/end 仍是 observed polygon boundary，但个别 aperture
切口可以不完全正交，不能建立或放宽 shared rotation。所有参与 rotation class 的 observed
angle intervals 精确交集是唯一可行域：

- 交集包含零：`identity`；
- 非零交集存在且绝对值不超过 `2°`：`observed_rotation`；
- 无共同交集：transform `UNAVAILABLE`。

Blank-only 输出可使用 authority 为 `grid_blank_no_photo_geometry` 的 identity；它不能用于
照片输出。

旋转固定 source center，使用整数像素中心：

```text
Wout = ceil(rotated_max_x - rotated_min_x + 2 × guard)
Hout = ceil(rotated_max_y - rotated_min_y + 2 × guard)
source center → ((Wout - 1)/2, (Hout - 1)/2)
```

Source half-open boxes 始终 outward rounding，并检查完整 bilinear footprint。最终对每个
ROI 从原 TIFF 做一次 inverse-affine sampling，不生成整张旋转 RGB 中间图。

## 11. Gate 与输出

CandidateGate 的 current checks：

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

底层 query 缺失先保持 `UNAVAILABLE`。只有它可能改变安全输出时，才映射到具体 Gate；
`grid_search_coverage` 只表示 Grid placement proposal 覆盖不完整。Inferred、blank、
separator 缺失、query 失败或多个 output-equivalent candidates 本身不是 final reason。

`approved_auto` 才允许正式 TIFF。`needs_review` 的正式 TIFF 数必须为零；Debug Analysis
中的候选标为 `NOT EXPORTABLE`，也没有 provisional product export 路径。
非空 direct-use budget 实现后应映射到现有 `output_protection` 或 `source_lane_geometry` 事实，
仍由 `DecisionGate` 独占 final status/reason；不增加第三个 Gate。

## 12. Report、Debug Analysis 与 TIFF

Current report：

```text
schema_id       = detection_report
schema_revision = source_coordinate_photo_geometry_v1
```

Report 保存 source authority、measurement coverage、search proposals、observed/inferred
provenance、完整 states、competition、translation assessments、两级 Gate、safe/protected
geometry、transform、final boxes 与 TIFF receipt。Raw transitions 与 source-content
components/row runs 只记录完整 coverage、数量、canonical row-run SHA-256 digest 与
component derivation，不在 current JSON 中逐条展开；selected observations 和完整候选
states 仍保留。Report 不是 cache。

Debug Analysis 固定展示：

1. source context；
2. raw measurement 与 line families；
3. selected source geometry / unresolved candidates；
4. protected output footprint。

Review audit sampling只允许验证工具写入忽略的
`build/v49-photo-geometry/golden-review-audit/`，不得进入产品 output、run manifest 或
`tiff_output_count`。

Approved ROI 写出后复读并检查 pixels、dtype、axes/channels、photometric、bit depth、
ICC、resolution、metadata 与 NONE/LZW 无损压缩。I/O 失败是独立 terminal failure。

## 13. 验证边界

Accuracy blocker 只有 tracked `tools/regression/cohorts/gold_accuracy.jsonl`：

- nominal：S027、S035、S051、S055、S062、S091、S094、S109；
- stress-excluded calibration：S098；
- 九张共 14 个场景。

12 个 `must_approve_safe` 场景必须批准并正式写出/复读 TIFF。S055 两个 review 场景必须
存在黄金安全 state 和 protection 后仍不等价的物理竞争 state，且正式 TIFF 数为零。
在 V4.9 发布闭合前，12 个 approved 场景的每个非空输出还必须新增按边 direct-use budget
验收；blank 输出明确豁免。预算的 metric 与数值尚待用户确认，实现者不得临场自行决定。

`diagnostic_unreviewed.jsonl` 的 111 records 不产生 accuracy verdict。它们只阻断 crash、
hang、非法 schema、未完成 query 被消费、无界 query/DP/memory、TIFF 损坏和 authority
逃逸。单输入 peak temporary memory 的冻结上界为
`10 × source_pixels + 32 MiB`；这是随输入面积线性增长的工程上界，不是固定尺寸样片
白名单。文件名 `pass/unknown` 与 filename count 不进入 runtime 或 validation
expectation。

正式性能使用固定 24 TIFF、`--jobs 2` 与 status-independent 168-task I/O workload。
V4.2.8 基线固定 tag `v4.2.8` / commit
`8d14c55d8af5c944a0b78b51df4c4c428e606f07`。硬门槛为 V4.9 median
`<=5.0 秒/输入`，且 paired total wall 在 MAD 噪声之外快于基线。

## 14. 源码 owner

| 路径 | 职责 |
|---|---|
| `x5crop/configuration/` | format-independent runtime configuration 与 typed physical inputs |
| `x5crop/formats/` | format aperture、count 和 protection |
| `x5crop/detection/evidence/scan_canvas.py` | 片夹、lane、scale、capacity observation |
| `x5crop/detection/source_core.py` | bounded content ownership measurement |
| `x5crop/detection/photo_geometry/` | 照片边界、序列、状态、DP 与 source geometry |
| `x5crop/detection/output_geometry.py` | observed transform assessment |
| `x5crop/geometry/affine.py` | affine 数值合同 |
| `x5crop/detection/candidate/` | CandidateGate facts |
| `x5crop/detection/decision/` | final status/reasons |
| `x5crop/detection/final/` | resolved geometry finalization |
| `x5crop/export/`、`x5crop/io/` | 一次 sampling、TIFF 写出与复读 |
| `x5crop/report/`、`x5crop/debug/` | current report 与 Debug Analysis |
| `tools/regression/gold_comparator.py` | tracked gold geometry comparator |
| `tools/regression/gold_accuracy.py` | 九张、14 场景 blocking gold runner |
| `tools/regression/diagnostic_cohort.py` | 111-source 非阻断诊断 runner |
| `tools/regression/performance.py` | status-independent paired performance |
| `tools/verify` | 唯一验证入口 |

旧 nearest-line Grid、separator field、固定 uncertainty、跨候选 outward union 和
identity-only detector 已删除；current tree 不保留 fallback、双 detector 或 compatibility
shim。
