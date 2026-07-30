# X5 Crop 架构说明

本文件是 V4.9 当前运行流、数值合同、源码分层与已冻结下一阶段设计的唯一架构说明。
用户操作见 `docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`，版本行为见
`CHANGELOG.md`。

## 产品目标与成功合同

X5 Crop 的产品目标是在用户已经提供 format 后，生成足够安全的逐帧 TIFF：`full` 使用
格式固定张数；`partial` 既允许用户显式提供 count，也允许 bounded `auto count`。系统
优先保证不切掉真实照片内容，允许在保护范围内向外多保留像素。目标不是唯一重建照片的
真实物理边界，也不要求手术刀式贴边。

未来自动输出必须遵守：

- format 始终是 runtime authority；显式 count 是 authority，`auto count` 则只在格式与
  已匹配片夹容量限定的有限整数集合内选择；
- observed separator/content/outer 与模型 inferred Grid 必须分开记录，但都可以参与有限
  proposal、assessment 与 selection；
- 精确边界或 Grid phase 没有唯一真值，不自动等于 `needs_review`；多个候选若具有相同
  slot ownership，且差异可被同一个保守输出包络与 protection 吸收，仍可
  `approved_auto`；
- blank 保留设计 slot；partial 可以推断 slot placement；contact/overlap 可以让相邻输出
  框重叠并重复保留共享像素；
- `approved_auto` 只声明最终输出满足有界安全合同，不声明每条边界被证明，也不声明输出
  只含本 slot 的像素；固定 protection 可以跨过 nominal divider 并带入相邻照片像素；
- `needs_review` 只用于会改变 count/ordinal/slot ownership、无法满足显式 count、auto
  count 仍有非支配竞争结果、仍可能切掉已知内容、主照片归属无法有界或未保护 geometry
  越出 source/lane authority 的具体风险；
- `CandidateGate` 只保存安全事实，只有 `DecisionGate` 创建 final status 与 final
  reasons。

回归验收以 count、顺序、slot ownership、内容 containment、允许的 outward
over-retention 与 TIFF 保真为准；auto 模式还要检查 selected count，不要求复刻历史 box
或逼近人工边界。下述 current source-core 尚未实现该自动输出合同；当前全量 review 是
能力检查点，不是产品最终目标。

## 1. 当前能力边界

V4.9 当前开发树是一个物理诚实的 source-core 安全基线。系统尚无获批的独立
`FrameGridEvidence` phase authority，因此所有需要定位 frame 的输入都保持
`needs_review`，不写出 frame TIFF。

这是 current runtime 的正式能力边界，但“独立且唯一的 Grid phase 证明”不再是未来
`approved_auto` 的产品前提：

- separator、photo edge、outer、positive content 与设计宽度都不能自行补出 Grid phase；
- containment 因没有 frame assignment 而为
  `NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`；
- Visual deskew 因核心 geometry 不成立而为
  `NOT_APPLICABLE_CORE_UNAVAILABLE`；
- inverse-affine ROI exporter 作为独立 foundation 保留，但 runtime 不调用它导出 frame；
- 当前没有组合搜索，因此没有 `PhysicalAuditBudget`。

## 2. 唯一运行流

```text
TIFF source pixels
  -> base_gray_u8，一次
  -> ImageMeasurementStatistics，一次
  -> ScanCanvasEvidence
  -> CanvasAxisScaleIntervals
  -> SourceStripValidationDomain
  -> SourceContentObservation
  -> FrameGridEvidence(NO_INDEPENDENT_PHASE_AUTHORITY)
  -> CandidateGate
  -> DecisionGate
  -> FinalDetection(needs_review, no boxes)
  -> review copy / current report / Debug Analysis
```

权限单向流动。Report 与 Debug 只读既有 evidence，不重新测量、选择或裁决。
`CandidateGate` 只检查候选事实；`DecisionGate` 是 final status 与 final reason 的唯一
owner。

## 3. 物理 authority

### 3.1 设计照片 aperture

`FrameDesignApertureMm` 保存用户批准的离散设计值：

| 格式 | long × short |
|---|---|
| 135 / 135-dual | `36 × 24 mm` |
| half | `18 × 24 mm` |
| XPan | `65 × 24 mm` |
| 120-645 | `42 × 54`、`42 × 56 mm` |
| 120-66 | `54 × 54`、`56 × 56 mm` |
| 120-67 | `70 × 54`、`70 × 56 mm` |

不同 component 不取 hull，也不混用 width/height。当前这些事实只进入配置、报告与未来
Grid 合同；单独使用设计 aperture 不能确定位置，但可以约束有限模型 proposal。

### 3.2 Scan canvas 与分轴 scale

照片格式与 scan canvas 是不同 owner。当前 catalog：

| Profile | long × short | Format fit 与最大张数 |
|---|---:|---|
| `135_standard` | `232 × 32.22 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_narrow` | `232 × 25.4 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_dual` | `232 × 63.44 mm` | 135-dual ≤ 12 |
| `120_standard` | `226 × 60 mm` | 120-645 ≤ 4；120-66 ≤ 3；120-67 ≤ 3 |
| `120_wide_224_5` | `224.5 × 63.44 mm` | 120-645 ≤ 4；120-66 ≤ 3；120-67 ≤ 3 |
| `120_wide_223` | `223 × 63.44 mm` | 120-645 ≤ 4；120-66 ≤ 3；120-67 ≤ 3 |
| `120_wide_188_5` | `188.5 × 63.44 mm` | 120-645 ≤ 4；120-66 ≤ 3；120-67 ≤ 2 |

`ScanCanvasFormatFit` 是片夹与 format 的物理适用关系，并保存该组合的
`maximum_frame_count`。它不属于 `FormatSpec`，因为同一 format 可进入不同长度的片夹，
同一片夹也可容纳不同 format。旧 `120_66_three_frame` 名称已删除；188.5 mm profile
不能被命名为 66 专用。

Runtime 先用 authoritative format 与 resolved count（full 默认张数或显式 partial count）
排除装不下的 profile，再按 source 像素长短比寻找唯一匹配。唯一匹配的
`ScanCanvasPhysicalSpec` 产生：

```text
s_long  = observed_long_axis_px  / canvas_long_axis_mm
s_short = observed_short_axis_px / canvas_short_axis_mm
```

当前没有额外 measurement uncertainty 时，两者分别是 point interval。一个轴的数值
不得扩宽另一个轴。TIFF resolution/DPI 只作为 I/O metadata 保留，不参与检测。

无匹配或多个 profile 同时成立时，scan-canvas authority 不可用。系统不得选择最近
profile。Count 过滤只排除物理容量不足的片夹；不得从 count 推导较短的 source domain。
`resolved_frame_count` 属于 typed runtime configuration，并进入 configuration identity；
不得让不同 count 的 profile 集合共享同一配置身份。

### 3.3 Validation domain

`SourceStripValidationDomain` 只来自唯一 scan canvas/lane 与 source extent：

```text
work_box = 完整 scan canvas 或完整 lane 的半开 cell-edge Box
```

它不得由 holder、photo edge、separator、content、Grid 或 deskew 缩窄。水平和垂直布局只
交换 work axes，不重采样 source measurement。`full` 与 `partial` 使用同一个短轴 domain；
partial count 仍只描述完整设计 slot。

`135-dual` 先以完整 `232 × 63.44 mm` canvas 建立两轴 scale，再使用确定的中心分区让每个
lane 独立建立 domain；不得把两个 lane 分别误认成 `135_standard` 或 `135_narrow`。
当前 dual-lane 因 Grid 尚未实现仍保持 review。

## 4. Immutable positive content

Canonical 灰度为：

```text
I = base_gray_u8.astype(float32)
```

图像边缘在 five-point mean 中复制当前像素：

```text
intensity_content
= abs(I - (I + north + south + west + east) / 5) / 255

dx[:, 0] = 0
dy[0, :] = 0
texture_content = (abs(dx) + abs(dy)) / 510
```

Intensity 与 texture 分别使用同一套 current adaptive threshold 与 spatial-support 参数：

```text
positive_content
= intensity_supported AND texture_supported
```

严格 4-connectivity 产生 immutable `SourceContentComponent`。组件的 row runs 以只读
`int32` RLE 表保存，组件只引用连续 span；report/Debug 只输出有界摘要。每个组件保存：

- 完整半开 footprint；
- positive cell 数；两个 channel 的总体 measurement 统计由 observation owner 保存；
- row-run offset/count；
- censored 状态；
- source measurement provenance。

接触 lane authority、需要 clamp 或 measurement 不完整的组件标记 censored。Content
measurement 是确定性线性工作，记录 domain pixels、active cells、raw/retained
components、runs、wall time 与临时内存上界。它无权创建 Grid、frame、containment 或
deskew。

## 5. Grid、Gate 与 finalization

Current-only Grid 固定为：

```text
FrameGridOutcome.NO_INDEPENDENT_PHASE_AUTHORITY
authority = None
frame_slots = ()
```

不存在休眠 detector、feature flag、baseline runtime 入口或 manual phase 注入。

`NO_INDEPENDENT_PHASE_AUTHORITY` 只描述当前树为何没有 boxes，不定义未来批准门槛。后续
方案可以在用户 format/count 约束内结合 observed evidence、expected position 与格式模型
建立 bounded Grid hypotheses，并把输出等价的多个 hypotheses 合并为保守安全包络；无需
先证明唯一真实 phase。

`CandidateGate` 依次检查：

1. `scan_canvas_authority`
2. `source_content_measurement`
3. `frame_grid_authority`

Candidate checks 不保存 final reason。`DecisionGate` 把阻断事实映射为唯一 typed reason。
正常 source-core 完整时固定为：

```text
status = needs_review
reason = frame_grid_authority_unavailable
```

若 scan canvas 或 content measurement 自身不可用，追加各自独立 reason。由 Grid 阻断的
containment、protection 与 deskew 只标记 `NOT_APPLICABLE`，不重复制造 reason。

`FinalDetection` 不含 final boxes，`frame_export_eligible` 永远为 false。Unavailable 不得
进入 frame finalization。

未来恢复自动输出时，`CandidateGate` 应检查 format/count、box 数量与顺序、
source/lane bounds、已知内容 inward loss、slot ownership 和 uncertainty 是否已被
protection 吸收。精确边界为 inferred、separator 不完整、blank slot 或多个输出等价
hypotheses 都不是独立否决项。`DecisionGate` 仍是 `approved_auto` / `needs_review` 与
typed reasons 的唯一 owner。

## 6. 毫米 output protection authority

Pixel bleed 接口与模型已删除。唯一 owner 是格式级毫米设计表：

本计划中口语所称的 “bleed 保护”由 `shared_interaction` 的有界重复保留加固定毫米
`OutputProtection` 共同实现；它不是恢复旧 `--bleed` 参数、pixel bleed model 或动态
50 px 规则。

| 格式 | long | short |
|---|---:|---:|
| half | `0.15 mm` | `0.25 mm` |
| 135 / 135-dual | `0.25 mm` | `0.25 mm` |
| 120-645 | `0.30 mm` | `0.25 mm` |
| 120-66 | `0.40 mm` | `0.25 mm` |
| XPan | `0.45 mm` | `0.25 mm` |
| 120-67 | `0.50 mm` | `0.25 mm` |

当前没有 frame geometry，所以 authority 只进入 report，`applied=false`。当前代码不能
用它创建输出。未来 protection 是 output-safety assessment 的组成部分：它可以吸收
bounded Grid/edge uncertainty 和 contact/overlap 风险，但不能把无界或整格错位的
placement 变成安全输出。

下一阶段冻结的换算与应用合同如下：

- 表中 long/short 数值均是**每一侧**的固定保护量，不是两侧总量；
- 使用唯一 scan-canvas authority 的两个独立 scale interval，禁止使用 TIFF DPI：

  ```text
  long_pad_px  = ceil(long_axis_mm  * s_long.upper)
  short_pad_px = ceil(short_axis_mm * s_short.upper)
  ```

- 先在 physical work axes 中合并 `SafeCropEnvelope`、输出等价 proposal 与
  contact/overlap shared interval，再向四侧应用固定 protection；
- protection 不以 nominal slot boundary 为 clamp：扩张带入相邻照片像素是获批的保守
  retention，不改变 primary slot ownership，也不独立触发 review；
- 保护后的半开 box 通过 affine outward mapping 转成 source ROI。不得先取最近整数、不得
  inward round，也不得完整旋转 RGB 后重新检测；
- 不恢复动态 50 px、overlap multiplier、旧 pixel bleed 或用户 override；
- 未保护的 `SafeCropEnvelope` 必须完整位于 source/lane authority。只有固定 protection
  超出 authority 时，才允许在 source/lane 边界饱和，并必须报告
  `source_saturated` / `lane_saturated`；纯 protection 饱和不自动送审；
- 每个最终 box 必须分别报告 `primary`、`shared_interaction`、`fixed_protection` 与
  `authority_saturation` retention provenance；不得用饱和或 clamp 掩盖原始 envelope
  越界、已知内容丢失、错误 lane 或整格 ownership 错位。

## 7. Report、Debug 与 comparator

Runtime schema 唯一为：

```text
schema_id       = detection_report
schema_revision = source_core_grid_authority
```

Report 保存 source identity、配置、lane/domain、分轴 scale、content 聚合统计与有界组件
样例、Grid/containment/deskew outcome、两级 Gate、finalization 原因以及
`core_facts_sha256`。Measurement wall time 不进入 core hash。

不存在旧 schema reader、alias、shim、adapter 或忽略字段。Debug Analysis 只显示完整
domain、positive-content 有界摘要与 typed decision。

外部人工 baseline comparator 唯一为：

```text
x5crop_golden_baseline_directional_comparison_v3
```

Comparator 只在 detector/output receipt 冻结后读取 baseline。当前结果固定为
`production_geometry_unavailable`，不输出 `resolved-safe`。

## 8. ROI 与 TIFF foundation

以下 foundation 独立保留：

- `AffineCoordinateTransform.inverse_matrix`
- non-clamping `map_half_open_box_outward`
- `sample_affine_roi`
- `write_crops`

`Box` 是半开 cell-edge 区间。Identity transform 精确切片。非 identity ROI 只反演既有
matrix，以一个 bilinear sampler 从原始 RGB/gray 直接采样；production 不创建完整 rotated
RGB 或第二份 rotated gray。越出 source/output authority 直接报错，不 clamp。

Foundation contracts 验证：

- ROI 与 test-owned full rotation 后切片逐像素 `array_equal`；
- dtype、axes、channels、ICC、resolution、metadata 与 NONE/LZW compression 保真；
- 每个 ROI 只采样原始像素一次。

当前 runtime 没有合法 frame boxes，因此不会调用 exporter。

## 9. 配置、缓存与源码分层

Runtime boundary 解析 `DetectionConfiguration`。Lower layer 接收显式 typed input，不查询
registry、不发明默认值。

`DetectionWorkspace` 只保存：

```text
source_gray
measurement statistics/cache
SourceCoreEvidence
```

Cache 只拥有 base gray、image statistics 与 layout-normalized work gray。它不保存
candidate、Gate、decision、final reason 或 report。

主要 owner：

| 路径 | 职责 |
|---|---|
| `x5crop/formats/` | aperture 与 scan-canvas 物理事实 |
| `x5crop/image/` | 灰度、统计、activation 与 affine sampling |
| `x5crop/detection/source_core.py` | domain、positive content、Grid unavailable 与 downstream outcome |
| `x5crop/detection/candidate/` | CandidateGate |
| `x5crop/detection/decision/` | DecisionGate 与 final reasons |
| `x5crop/report/` | current-only report |
| `x5crop/debug/` | source-core 可视化 |
| `x5crop/export/` | 独立 TIFF/ROI foundation |
| `tools/regression/` | current report comparator、baseline comparator 与性能 runner |

`X5_Crop.py` 保持 13 行模块入口。Standalone 仅由 release builder 从 modular tree 生成，不
维护第二份实现。

## 10. 验证与性能边界

`tools/verify` 是唯一机械验证入口。Pre-commit 只做 staged hygiene；pre-push 是唯一 full
validation。

当前 detector-only 诊断：

```text
固定 24 张
--jobs 2
cold 一次
三次新输出目录
median(detector wall / 24) < 5.0 秒/张
```

它只证明安全基线仍有未来生产余量，不是正式输出性能 PASS。

真实 TIFF 认证只有未来 bounded Grid proposal 与 safe crop envelope 恢复 frame export
后才可执行：

```text
24 张真实 TIFF 写出并复读
median(total wall / 24) <= 5.0 秒/张
```

当前真实输出认证必须报告 `not_certified`。崩溃、遗漏、写出或复读失败单独失败。

Named audit 覆盖 S027、S035、S051、S055、S062、S091、S094、S109 与 S098；预期全部
`needs_review`、无 frame output。111 张发布前审计只验证 source-core invariant。

## 11. Current-only 删除边界

Active tree 不保留：

- exact `PhotoEdge*`；
- ridge graph、fragment、scheduler、frame sequence solver；
- separator/profile/score/rank/Top-K；
- holder-sequence、transform evidence、rotated gray、shared short axis；
- pixel bleed CLI/model/report 字段；
- legacy reader、alias、shim、adapter、feature flag 或双实现。

历史术语只允许存在于 `CHANGELOG.md` 与 ignored 本地证据包。旧实现只能从 Git history/tag
恢复，不能与 current runtime 混用。

## 12. 已冻结的下一阶段设计（尚未实现）

本节是下一任务的实现合同，不是 current capability 声明。第 1–11 节描述的
`source_core_grid_authority` runtime 在原子切换前保持不变；不得以 feature flag、fallback、
兼容 reader 或新旧双路径提前开放自动输出。

### 12.1 输入 authority、count mode 与有效 count

Runtime boundary 唯一解析 authoritative format、mode 与 typed `FrameCountRequest`：

| 输入 | count 合同 |
|---|---|
| `full` | `fixed_full`：format 的 `default_count`；显式 count 若存在必须与其相同 |
| `partial + explicit` | 用户显式 count 是 authority，范围为 `1..default_count`，包含格式最大 count |
| `partial + auto` | `count_candidates = 1..default_count`，再由唯一匹配片夹的容量排除装不下的 count |
| `135-dual/full` | source 总数 12；两个 authoritative lane 各自为 6 |

用户入口语义同时冻结：CLI 的 partial 模式不传 `--count` 即为 `auto`，传
`--count N` 即为 `explicit`；交互入口的回车或 `auto` 同样表示 `auto`，整数表示
`explicit`。Full 不传 count 时建立 `fixed_full`，若显式传入 count，只接受
`default_count` 并仍规范化为 `fixed_full`。不增加第二个 auto-count 开关，也不让 lower
layer 从裸 `None` 猜 mode；runtime boundary 必须把 `strip_mode + requested_count` 一次解析
成明确的 `FrameCountRequest`。

所有支持 partial 的单 lane format 都允许显式或自动选择到 format 最大 count；不再用
`complete_strip_can_be_underfilled` 区分哪些格式可以在 partial mode 使用最大值。片夹
`ScanCanvasFormatFit.maximum_frame_count` 仍是更窄的物理上界，例如 188.5 mm 片夹上的
120-67 最多为 2。

原子切换时 `StripHandlingSpec` 只保留 `default_count` 与
`partial_mode_supported`；partial 的完整 count range 由 `1..default_count` 推导。同批
删除 `allowed_partial_counts`、`complete_strip_can_be_underfilled` 及其分支，不保留 alias
或兼容 reader。`135-dual` 当前只支持 full；其它 canonical single-lane format 支持
partial。

Explicit 模式先用 requested count 排除容量不足的 scan-canvas profile。Auto 模式先用
format 与 source aspect 在全部适用 profile 中建立唯一 scan-canvas authority，再把该
profile 的容量应用到 count candidate set；不得用 filename、`pass/unknown` 标签或检测
score 帮助匹配片夹。`FrameCountRequest` 与 candidate range 进入 configuration identity；
auto 选出的 count 进入 analysis/output identity、report 与最终文件序号。

每个 `FrameGridProposal` 都携带自己的 `frame_count`，该 proposal 内的 ordinal 始终是
lane-local `1..frame_count`；系统不猜 roll-global frame number。Auto count 可以使用
separator、edge-pair、endpoint、content containment、format pitch 与 model-only Grid
作有界推断，不要求 observed separator 或照片边证明。没有内容观测不能把尾部 slot 判成
不存在：blank 仍保留完整 slot。

不同 count 的 proposal 永远不属于 output-equivalent。硬物理约束、ordinal-compatible
observation、endpoint/containment 与 bounded prior 可以使一个 count proposal 支配其它
count；score 只负责稳定排序。若仍有多个改变输出张数或 primary ownership 的非支配 count，
`frame_count` 事实阻断 auto approval。Count 为 1 时没有 internal boundary corridor，但仍
要选择有界 placement、建立一个 slot 并执行完整 envelope、protection 与 Gate 流程。

`FrameDesignApertureMm` 的离散 components 原样进入搜索。135、half、XPan 只有一个
component；120-645、120-66、120-67 的两个 component 分别运行，不取 hull，不交叉拼接
long/short 尺寸。

### 12.2 目标生命周期

```text
source pixels + authoritative format/mode + FrameCountRequest
  -> source-core measurements，一次
  -> FrameGridSearchPrior
  -> finite GridPlacementSeed
  -> separator / one-sided / content / interaction observations
  -> count - 1 local corridors and BoundaryCandidate
  -> ordered one-dimensional DP
  -> FrameGridProposal selection and output-equivalence merge
  -> ordered FrameSlot and SafeCropEnvelope
  -> contact/overlap union and millimetre OutputProtection
  -> optional VisualDeskewProposal and final output-geometry assessment
  -> CandidateGate safety facts
  -> DecisionGate
  -> finalization
  -> one inverse-affine ROI sample per output
  -> TIFF write and read-back receipt
```

所有 detection geometry 保持 source-coordinate 或 layout-normalized work-coordinate
半开区间，并携带明确 transform。Visual Deskew 只影响最终采样 transform：没有有界角度时
使用 typed `IDENTITY_NO_DESKEW`，不因“未 deskew”送审；它不能改变 Grid、slot、envelope
或 protection。DecisionGate 后不再改变 box。

Report 与 Debug 只能消费已完成的 measurement、proposal、selection、Gate 与 output
receipt，不重测、不选择、不裁决。

### 12.3 Canonical owners

下一阶段只建立以下 canonical concepts；类型名同时冻结其唯一职责：

| Concept | 唯一职责 |
|---|---|
| `FrameCountRequest` | 保存 `fixed_full/explicit/auto`、requested count 或有限 candidate range；不拥有 selection/status |
| `FrameGridSearchPrior` | 保存按 format/mode/component 校准的 pitch、gutter、phase corridor 与 endpoint interval；只约束搜索 |
| `GridPlacementSeed` | 一个有限 origin/span hypothesis 及 provenance；不属于 observation |
| `SeparatorBandObservation` | 保存 band 两侧 transition、band interval、center、width、cross-axis support、appearance 与 source provenance |
| `OneSidedBoundaryObservation` | 保存单侧 photo↔background transition 与方向，只提供单侧 containment bound |
| `BoundaryCandidate` | 把 observation 或 model-only interval 绑定到一个 local corridor；不拥有 final cut |
| `FrameGridProposal` | 保存 frame count、ordered boundaries、pitch/phase interval、slot assignment、observed/inferred provenance、residual 与 work receipt |
| `FrameCountDominanceAssessment` | 保存两个 surviving proposal 的逐维、归一化跨 count 比较与 `dominates/incomparable` 结果；不拥有 Gate/status |
| `FrameSlot` | 保存 lane-local ordinal、design component、左右 boundary role 与 occupancy/interaction facts |
| `BoundaryInteractionObservation` | 保存 separated、contact/overlap 或 appearance-unresolved，以及有界 shared interval |
| `FrameEnvelopeProposal` | 一个 Grid proposal 下的逐帧 primary outward containment |
| `SafeCropEnvelope` | 合并输出等价 proposal 与 bounded shared interaction 后的安全包络，尚未应用固定 protection |
| `ProtectedFrameEnvelope` | 应用毫米 protection、可选 affine outward mapping 与 authority 饱和后的最终候选 box；允许含邻片像素 |
| `GridSearchWorkStatistics` | 保存固定结构工作量、截断与 exact-cache 命中；不能作为可靠性证据 |

`FrameCountRequest` 与 `FrameGridSearchPrior` 属于显式 runtime configuration；
observation 属于 evidence layer；Grid/slot/envelope 属于 detection；protection 属于
output geometry；Gate、finalization、report、debug 与 exporter 继续各守现有生命周期
边界。Lower layer 只接收 typed input，不查询 format registry 或补默认值。

原子切换后的 tracked owner 路径也冻结：

| 路径 | 下一阶段职责 |
|---|---|
| `x5crop/configuration/model.py` | `FrameCountRequest`、count mode/range、configuration 与 analysis identity 边界 |
| `x5crop/formats/protection.py` | 格式级毫米 protection authority 表 |
| `x5crop/configuration/grid.py` | `FrameGridSearchPrior` 与结构上限 |
| `x5crop/detection/evidence/separator.py` | 唯一 separator/edge/one-sided measurement 与 observations |
| `x5crop/detection/grid.py` | placement、corridor candidates、ordered DP 与 proposal selection |
| `x5crop/detection/envelope.py` | slots、interactions、output-equivalence 与 safe envelopes |
| `x5crop/output/protection.py` | 毫米换算、fixed expansion、authority saturation 与 protected envelopes |
| `x5crop/detection/deskew.py` | 可选 Visual Deskew proposal 与 output-transform assessment |
| 现有 `candidate/`、`decision/`、`final/` | 两级 Gate、唯一 final decision 与 finalization |

`source_core.py` 在切换后只保留 lane/domain/content source facts；当前 Grid unavailable、
containment/protection/deskew placeholders 必须同批删除，不得迁移成 parallel owner。
`detection/pipeline.py` 只编排上述单向 owner。

### 12.4 Prior、placement 与 partial

`FrameGridSearchPrior` 的数值表必须按 format、full/partial、离散 aperture component
分别保存：

```text
pitch_interval_mm
gutter_interval_mm
phase_corridor_ratio
endpoint_slack_mm
calibration_receipt_id
```

这些 interval 是 search authority，不是照片或 separator 的物理观测。初始值可以由现有
真实 TIFF 的只读 source-coordinate calibration，或明确记录的物理规则推导产生，并冻结在
typed configuration；不得直接复制旧 tuning。每份 calibration receipt 必须同时列出
format、mode、component、orientation、count、partial placement 与 interaction class 的
实际覆盖，区分 empirical calibration、holdout 与 synthetic/physical-rule validation。

现有样片只校准搜索中心、排序、典型 corridor 与 measurement 分布；样片 min/max 不得直接
成为“未见过即失败”的硬 admissibility bound。硬物理边界仍由
`FramePhysicalSpec`、`ScanCanvasPhysicalSpec`、source/lane authority 与 output protection
合同提供。S098 保持 `irregular_geometry_stress`，不进入 nominal tolerance estimation，
但这项角色不改变它必须自动批准的验收期望。没有真实样片的 format/component 不发明“最近
格式”值；通用模型只能使用显式审阅过的 physical-rule prior 与 synthetic contracts。
Coverage gap 只限制验证或发布声明，不能成为 CandidateGate 事实、format denylist 或
单张输入的 `needs_review` reason。

每个 lane/component 先生成下列同级 seed source，不设 fallback/retry 顺序：

- lane/source 的 leading-aligned、trailing-aligned 与 centered span；
- content/outer containment 的 leading、trailing 与 centered span；
- observed separator 的有限 ordinal assignment；
- partial 的 observed endpoint/containment assignment。

Seed 使用当前 count candidate 的完整 span。Partial 不再使用
`0 / 0.25 / 0.5 / 0.75 / 1` 固定 offsets，也不假定真实照片贴左、贴右或居中；首尾 endpoint
各自独立成为 hypothesis。两个 seed 只有在 source cell-edge outward quantization 后的
全部 endpoint 与 `count - 1` corridor interval 完全相同时才去重。

冻结结构上限：

```text
P_MAX = 6  # 每个 lane/component 的非重复 placement seeds
```

最多两个 seed 可来自 separator-first anchor assignment。生成顺序固定为
observed-anchor、content/outer、lane/source，只用于确定工作顺序，不表达可信度。若去重后
仍有超过 6 个非支配 seed，不静默按 score 丢弃；记录 typed `search_incomplete`，并只在被
省略 seed 可能改变 count/ordinal/primary ownership，或使 content containment/source
authority 无法由 bounded union 表达时形成 Gate 阻断事实。仅改变可被 shared/fixed
protection 吸收的 final box 不阻断。

Separator-first 在尚无 expected position 时也不得做 band 全配对。设 canonical raw band
数为 `R`、internal ordinal difference 为 `d in 1..count-1`：按 source position 排序后，对
每个 band 与 `d` 用 pitch interval 二分查找最多两个 compatible successor，工作量上界为
`O(R * count * log R)`，而不是 `O(R^2)`；随后只形成上述最多两个 separator-first seeds。
`R`、查询次数、compatible pairs 与截断必须进入 work statistics。

### 12.5 Separator、edge-pair 与 corridor candidates

每个 lane 只建立一次 vectorized long-axis measurement field；ordinary、wide 与 edge-pair
是同一 observation owner 的 appearance/method，不是三条 runtime branch：

- edge-pair 同时保留 leading transition、background-like band 与 trailing transition，
  分别可约束 `Photo end`、`Grid divider`、`Photo start`；
- wide band 只是较宽的同类 interval，不触发 retry；
- expected position 只确定 local corridor、搜索顺序与 normalized residual，不能把最近
  signal 变成可信 separator；
- nearby、semantic、continuity、background、activity 与 local-drift measurement 只能参与
  dominance、residual 或 competing proposal，不能静默改写 strong observation；
- content/outer 只能提供 placement/containment，不能冒充 separator/photo edge。

Learned gutter 只在同一 lane/component 至少有两个 ordinal-compatible edge-pair 时成立。
其 interval 是这些 pair width intervals 的 outward hull，并保留每个 source observation；
存在相互矛盾的 pair 时建立 competing proposal，不删除“离群值”来制造一致。一个
`OneSidedBoundaryObservation` 只有在该 learned interval 能把另一侧限制在当前 corridor
内时，才可产生一个 observed-plus-inferred candidate；它仍不能单独确认 separator identity
或 ordinal。条件不成立时只进入 Debug。

对每个 placement 的每个 internal corridor：

```text
O_MAX = 2  # 全部 appearance 合计的非支配 image-observed candidates
M_MAX = 1  # 由当前 seed/prior 产生的 model-only candidate
K_MAX = 3  # corridor 总上限
```

同一物理 band、相同 source interval 与相同 boundary roles 的 candidates 先合并
provenance。超过 `O_MAX` 的非等价、非支配观测不由最高分代替完整事实；记录
`search_incomplete`；只有上述 output-relevant 条件成立时才让
`grid_search_coverage` 进入 `CONTRADICTED`。每个 corridor 始终保留一个 model-only
interval，因此看不见齿孔、separator 缺失、空片或 count 为 1 都不是流程失败。

### 12.6 Anchor 数量与 ordered DP

Anchor 只指已绑定 local corridor 的 `SeparatorBandObservation` 或合格 one-sided
candidate：

- `2+` 个 ordinal-compatible anchors：在 prior interval 内拟合 pitch/phase，保留
  inlier、residual 与冲突；不得越过 strong conflicting observation；
- `1` 个 anchor：只在其 `1..count-1` 有限 ordinal assignment 与现有 placement seeds 中
  展开；
- `0` 个 anchor：每个 seed 只沿 model-only corridor 完成一个 Grid proposal。

DP 状态只包含“当前 corridor + 当前 candidate”。Transition 只允许：

- source 位置严格递增；
- pitch/phase 位于当前 component 的 prior interval；
- boundary roles、lane、ordinal 与 count 一致；
- primary content assignment 与 local ordinal 一致；shared/protection retention 不作为
  transition 冲突；
- endpoint 与 internal boundaries 能形成正面积半开 slot。

对一个 `C = proposal.frame_count`、`B = C - 1`，每个 lane/component 的结构上界为：

```text
DP states       <= P_MAX * B * K_MAX
DP transitions  <= P_MAX * (
                     min(B, 1) * K_MAX
                     + max(B - 1, 0) * K_MAX^2
                   )
```

最大 count 12 时分别不超过 198 states 与 558 transitions。Count 为 1 时两者为 0。总工作量
再乘明确的 lane 数与离散 component 数；禁止全轴 band 笛卡尔积、wall-clock early best、
预算耗尽后把当前最高分当成可靠结果。

Auto count 复用同一个 measurement field，只对有限 count set 分别建立 placement/corridor/
DP，不建立跨 count 的笛卡尔积。若 candidate set 是完整 `1..C_MAX`，每个 lane/component
的总上限为：

```text
auto states      <= sum(C=1..C_MAX, P_MAX * (C - 1) * K_MAX)
auto transitions <= sum(C=1..C_MAX, per-count transition bound)
```

`C_MAX = 12` 时合计不超过 1188 states 与 3168 transitions。Report 必须分别记录每个 count
的 seeds、states、transitions、hard rejection、dominance 与 retained proposal，不能把
auto count 的额外工作隐藏在单一总数中。

每个 lane 最多保留：

```text
G_MAX = 3  # 非支配 FrameGridProposal
```

Hard rejection 只允许来自可执行的物理不可能或安全冲突：

1. count 不在 `FrameCountRequest` candidate set，或超过已选 scan-canvas 容量；
2. placement/slot 非单调、面积非正，或 pitch、phase、endpoint 越出对应的 hard physical
   interval；
3. 应用 fixed protection 前的 primary/safe geometry 越出 source/lane authority；
4. 已知 primary content 无法在当前 count 下完成有界 ordinal assignment 与 containment，
   或只能通过 whole-pitch ownership 错位才能容纳。

这里的 hard physical interval 只能来自 `FramePhysicalSpec`、`ScanCanvasPhysicalSpec` 与
明确的单位/容量规则；经验样片的 min/max、典型 prior corridor 或纯 ranking tolerance
不得升级为 hard rejection。超出典型值但仍在物理 admissibility 内时，只能进入 residual
与 dominance assessment。

缺少 separator、没有 observed support、model-only、blank、较低 score、较大的但仍有界
outward retention，以及 fixed protection 的 authority saturation 都不是 hard rejection。

Explicit/fixed 模式只比较 requested count。Auto 模式先合并各 count 的 surviving
proposals，`G_MAX` 是合并后的全局上限而不是“每个 count 各保留 3 个”；不同 count 不能
合并为 output-equivalent。每对跨 count proposal 必须产生
`FrameCountDominanceAssessment`，并逐维记录：

- endpoint/placement compatibility；
- `ordinal-compatible observed support / applicable internal corridors`；
- 以对应 physical interval 归一化的 pitch/phase residual；
- `unexplained strong observations / lane strong observations`；
- primary content assignment、containment 与 authority 是否保持有界。

Count 1 没有 internal corridor，该维度是结构性 `NOT_APPLICABLE`，不得伪装成零分或满分。
任一 pair 中结构性 `NOT_APPLICABLE` 的维度从该次支配比较排除，不能使任何一方自动更好；
lane strong observation 总数为 0 时对应比例同样排除。
其它 count 没看到 separator 时 observed-support 覆盖为 0，但这本身不 hard reject；
model-only proposal 仍可凭 endpoint、normalized residual、containment 与 authority 支配
其它 model-only count。所有比例和 residual 必须按 applicable corridor、同一 lane
measurement 与 physical interval 归一化，不能因 count 较大、divider 较多而天然占优。

Proposal A 只有在所有适用的 output-relevant 维度都不差于 B，且至少一维严格更好时，才
支配 B；每一维先按冻结的 equality interval 归约为
`better/equivalent/worse/not_applicable`，不能用浮点微差制造严格更好。否则两者是
`incomparable`。Safe envelope 的像素大小只在其保持有界后参与同 count
稳定排序，不进入跨 count 支配，避免把“更贴边”重新变成审批要求。Scalar score、
provenance id 与稳定 tie-break 都只能排列已经得到的结果，不能删除跨 count 的
`incomparable` proposal。仍有改变输出张数或 primary ownership 的非支配 count 时，
`frame_count` 必须阻断；超过 3 个非等价、非支配 proposal 时另记 `search_incomplete`，
并使用同一 output-relevant 规则判断遗漏是否影响输出。Dual lane 分别选择，不建立 lane
proposal 的笛卡尔积。

### 12.7 Slot、blank、contact/overlap 与安全包络

每个 proposal 必须产生恰好 `proposal.frame_count` 个有序 `FrameSlot`。Slot appearance
只允许：

```text
content_observed
no_content_observed
appearance_unresolved
```

Appearance 不改变 count。`no_content_observed` 只表示当前 measurement 没有观察到内容，
不证明物理 blank；该 slot 仍输出完整设计 frame。没有 content observation、照片内容很淡
或 inferred Grid 都不自动送审。Measurement 完整但 component 数为 0 时，
`source_content_measurement` 仍是 `SUPPORTED`，不是 `UNAVAILABLE`。

逐帧 envelope 使用以下 outward 规则：

- observed separator band `[a, b)`：左帧的可能 photo end 不晚于 `a`，右帧的可能 photo
  start 不早于 `b`；各自向照片方向保留完整 observation uncertainty；
- model-only divider interval `[lo, hi)`：左帧右界取 `hi`，右帧左界取 `lo`，允许两框重叠；
- contact/overlap：把 observation 的 bounded shared interval 完整并入两侧 frame；
- one-sided edge：只约束已观测的一侧，另一侧仍由 learned gutter/prior interval 向外包络；
- first/last slot：可 pin 到被选 placement 的 containment endpoint，不自动扩张到完整
  source；已知 primary content 必须被包含，且不得发生 whole-pitch ownership 错位；
- common frame width、`pitch - gutter`、edge weighted median 与 format aspect 只产生
  `FrameEnvelopeProposal` 或 residual，不能覆盖直接 observation。

短轴没有同一 lane 内的 frame-to-frame ordinal ownership。默认
`SafeCropEnvelope.short_interval` 使用完整 authoritative lane short interval；可选
short-axis content/edge observation 只有在其 outward uncertainty、format aperture 与全部
已知 content 都被包含时才可向内收窄。没有短轴照片边、保留 holder/film border 或使用完整
lane short interval 都不是独立送审理由。

两个 `FrameGridProposal` 只有同时满足以下条件才是 output-equivalent：

1. lane、count 与 local ordinal 相同；design component 相同，或 component 差异在
   protected output 中完全消失且不改变 primary ownership；
2. 已知 primary content component 到 slot 或 shared slot set 的 ownership 相同；
3. appearance state 可以不同；interaction intervals 必须能作 bounded outward union，不
   要求一方证明 blank；
4. 未保护的逐帧 outward union 不进入另一 primary slot，除非该区域被明确标记为
   `shared_interaction`，并且 union 不越过 source/lane authority；
5. 应用固定 protection 后每个 ordinal 仍指向同一个 primary slot；最终 boxes 可以互相
   重叠，也可以包含相邻照片像素，不要求 pixel-pure 或互斥。

输出等价 proposal 按 ordinal 对 `FrameEnvelopeProposal` 作 outward union，形成唯一
`SafeCropEnvelope`。Geometry 不唯一本身不送审。若 whole-pitch/endpoint alternative 改变
primary 照片归属，且无法由一个保持 ordinal 的 bounded union 表达，则保持 competing
proposal，交给 CandidateGate 记录具体 ownership 风险。仅由 `shared_interaction` 或
`fixed_protection` 带入邻片像素不破坏 output-equivalence。

### 12.8 Gate 与 final reasons

`CandidateGate` 只建立以下完整、有序安全事实，不保存 final reason：

1. `scan_canvas_authority`
2. `source_content_measurement`
3. `grid_search_coverage`
4. `frame_count`
5. `slot_ordinal_assignment`
6. `slot_ownership`
7. `known_content_containment`
8. `source_lane_geometry`
9. `output_protection`
10. `output_transform`

`DecisionGate` 是唯一 status/reason owner。下一 schema 的 review reason 词汇冻结为：

| Candidate fact | Requirement | 阻断时的 final reason |
|---|---|---|
| `scan_canvas_authority` | `SUPPORTED_REQUIRED` | `scan_canvas_authority_unavailable` |
| `source_content_measurement` | `SUPPORTED_REQUIRED` | `source_content_measurement_unavailable` |
| `grid_search_coverage` | `NOT_CONTRADICTED` | `grid_search_incomplete_affecting_output` |
| `frame_count` | `SUPPORTED_REQUIRED` | explicit/fixed: `requested_count_unfulfilled`; auto: `automatic_count_unresolved` |
| `slot_ordinal_assignment` | `NOT_CONTRADICTED` | `slot_ordinal_ambiguous` |
| `slot_ownership` | `NOT_CONTRADICTED` | `slot_ownership_unbounded` |
| `known_content_containment` | `NOT_CONTRADICTED` | `known_content_not_contained` |
| `source_lane_geometry` | `SUPPORTED_REQUIRED` | `frame_geometry_outside_authority` |
| `output_protection` | `SUPPORTED_REQUIRED` | `output_protection_unavailable` |
| `output_transform` | `SUPPORTED_REQUIRED` | `output_transform_unavailable` |

`approved_auto` 的充分条件是 selected count 下所有 `ProtectedFrameEnvelope` 数量/顺序
正确，且上述事实均不阻断。Auto count 不要求 separator/photo edge 的唯一物理证明；一个
由 bounded prior、endpoint 与 model proposal 支配其它 count 的选择可以
`SUPPORTED`。下列事实不得单独产生 review reason：separator 缺失、齿孔不可见、
model-only 或 one-sided inference、blank、contact/overlap、未 deskew、多个输出等价
geometry、固定 protection 的 source/lane 饱和、较低 score、较大的安全 over-retention，
或 final box 中出现相邻照片像素。

Gate 在 fixed protection 之前判断 primary ordinal/ownership，在 protection 之后只判断
box 数量、source/lane/transform 有效性与保护是否按合同应用；它不对 final pixel purity
评分。只有 whole-pitch/primary assignment 仍存在具体 competing risk 时，才由
`slot_ordinal_assignment` 或 `slot_ownership` 阻断。

因上游阻断而无法执行的下游 check 必须标记 typed `NOT_APPLICABLE`；DecisionGate 只输出
根因 reason，不为同一 scan-canvas、Grid 或 geometry 问题重复制造 protection/transform
reason。

### 12.9 Report、Debug 与 cache

原子 runtime 切换时，唯一 report revision 改为：

```text
schema_id       = detection_report
schema_revision = bounded_safe_crop_grid
```

同批删除 `source_core_grid_authority` reader/branch，不提供 alias。新 report 至少保存
count request mode、requested/candidate/selected count、逐 count work、hard rejection 与
pairwise dominance assessment、
prior/calibration identity、seed、corridor candidates、observed/inferred roles、DP work、
retained/rejected/conflicting proposals、output-equivalence、slots、interactions、raw/safe/
protected envelopes、primary/shared/fixed-protection retention provenance、protection
pixels/saturation、optional transform、两级 Gate、final decision 与 TIFF receipt。Debug
overlay 使用同一 source geometry。

Cache 仍只保存 exact、count/offset-independent measurements；不得缓存 seed、candidate、
proposal、Gate、decision、final reason 或 output box。`GridSearchWorkStatistics` 至少记录
domain pixels、raw/canonical bands、retained/truncated candidates、seed 数、DP
states/transitions、proposal 数、exact-cache hit、各阶段 wall time 与临时内存上界。

### 12.10 实现与验证顺序

下一任务按以下阶段执行；1–4 是同一原子变更内的工作顺序，不是可发布的中间 commits。
期间新增的逻辑必须被 contracts 或 read-only calibration tool 实际消费，不留下 dormant
detector；只有阶段 5 的完整 tree 才改变 runtime 行为：

1. **Contracts**：新增上述 types、构造不变量、结构上限与 synthetic oracle；覆盖
   `fixed_full/explicit/auto`、partial 最大 count、跨 count dominance 与 auto-count 总工作
   上限。旧 `FrameGridEvidence`/source-core downstream placeholders 在切换前不扩展成
   双语义。
2. **Read-only calibration**：用现有真实样片为已覆盖的 format/mode/component 生成 prior
   与 separator measurement audit。九张 confirmed baseline 是唯一 accuracy geometry
   oracle；其中八张 nominal 可参与校准，S098 只作 irregular-geometry stress、不进入
   nominal tolerance estimation，但仍必须 `approved_auto`。其余 102 张只能用于
   measurement distribution、coverage observation 与非阻断诊断，不能成为 accuracy
   completion gate 或冒充真实 holdout。无真实覆盖的 cell 使用明确 physical-rule prior 与
   synthetic contracts。冻结数值、receipt 与 candidate/work distributions 后才进入
   runtime configuration。
3. **最小纵切**：实现 seed、一个 canonical separator/edge-pair measurement、
   model-only candidate、ordered DP、跨 count selection、slot、safe envelope、毫米
   protection 与 identity output geometry；先通过 135/full 与 120-66/partial 的
   explicit/auto named audit，不开放 runtime export。
4. **安全交互**：加入 partial endpoints、blank、contact/overlap、output-equivalence 与
   one-sided learned gutter；wide/nearby/local-drift/advanced frame fit/deskew 只有 named
   gap 证明需要时才逐项加入同一 owner。
5. **原子切换**：一次替换 runtime flow、CandidateGate、DecisionGate、finalization、
   report revision、Debug 与 comparator，删除所有被替代的 placeholder/type/test；没有
   feature flag、fallback、旧 schema reader 或格式白名单；同一变更更新中英文公共文档。
6. **校准与发布验证**：只按跨样片物理类别调参，不为单 TIFF 放宽；更新 standalone
   builder、release metadata 与版本记录。

必须先有能失败的 contracts，至少覆盖 count 1、partial 显式/自动 count、format 最大
count、片夹容量收窄、auto count 唯一/支配/非支配竞争、逐 count 与总工作上限、anchor
`0/1/2+`、seed/candidate/proposal 上限、search-incomplete、horizontal/vertical、dual
lane、两个 120 components、partial 任意位置、blank、contact/overlap、等价与不等价
union、每侧 protection、authority 饱和、protection 带入相邻照片仍批准、whole-pitch
primary ownership 错位送审、outward affine、两级 Gate 与 forbidden legacy tokens。

任何 threshold tuning 前必须先校验已经 materialize 的 validation-only cohort identity；
原子 runtime 切换后再由同一 cohort 执行 accuracy completion：

```text
schema = x5crop_safe_crop_acceptance_cohort_v1
expectation = must_approve_safe | auto_or_review
evaluation_role = calibration | holdout | stress
```

当前唯一 tracked owner 是
`tools/regression/cohorts/safe_crop_acceptance.jsonl`。每条记录绑定 source SHA、
format/mode、expected count、需要运行的 count modes、expectation authority、
evaluation role 与 confirmed baseline geometry oracle。当前 cohort **只包含九张已经由
用户确认 geometry 的黄金样片**：

| sample | format/mode | count | count modes | expectation | role |
|---|---|---:|---|---|---|
| S027 | 135/full | 6 | fixed_full | must_approve_safe | calibration |
| S035 | 135/full | 6 | fixed_full | must_approve_safe | calibration |
| S051 | 135/partial | 3 | explicit + auto | must_approve_safe | calibration |
| S055 | 135/partial | 4 | explicit + auto | auto_or_review | calibration |
| S062 | 120-66/partial | 3 | explicit + auto | must_approve_safe | calibration |
| S091 | 120-66/partial | 3 | explicit + auto | must_approve_safe | calibration |
| S094 | 120-67/full | 3 | fixed_full | must_approve_safe | calibration |
| S098 | half/full | 12 | fixed_full | must_approve_safe | stress |
| S109 | half/partial | 7 | explicit + auto | must_approve_safe | calibration |

因此当前 accuracy completion gate 是八条 `must_approve_safe` 加一条
`auto_or_review`，不是此前 draft 中按 111 个文件名形成的 88/23 gate。S098 是
`must_approve_safe + stress`，stress 不是 review 豁免。`must_approve_safe` 只接受
DecisionGate 的 `approved_auto`；`auto_or_review` 优先自动批准，只有实际 Gate 阻断事实
成立时 review 才可接受。Partial 黄金样片在 explicit 与 auto 两种 count mode 下都运行；
auto 必须选择 cohort 的 expected count，才能形成自动输出。

原子实现必须同时建立唯一 runner：

```text
owner          = tools/regression/safe_crop_acceptance.py
result_schema  = x5crop_safe_crop_acceptance_result_v1
summary_schema = x5crop_safe_crop_acceptance_summary_v1
result_file    = safe_crop_acceptance_results.jsonl
summary_file   = safe_crop_acceptance_summary.json
```

规范调用为：

```bash
python3 -m tools.regression.safe_crop_acceptance \
  --source-root . \
  --baseline Test/manual_review/user_confirmed_golden_baseline.jsonl \
  --output-root <fresh-directory>
```

Runner 默认读取 tracked cohort，先按 `sample_id + source_sha256` 校验九张 current source、
confirmed baseline、format/mode/count/expectation/role，再把 4 张 full 各展开为一个
`fixed_full` 场景、5 张 partial 各展开为 `explicit + auto`，合计恰好 14 个场景。逐场景
JSONL 至少保存输入 identity、count request/selected count、DecisionGate status/reasons、
输出 count/order、confirmed content containment、final boxes 与比较结果；summary 保存
12 个 `must_approve_safe` 场景和 2 个 S055 `auto_or_review` 场景的通过/失败明细。
`must_approve_safe` 只接受 `approved_auto`；S055 的 review 只有携带实际 DecisionGate
阻断事实才可接受，若批准则 selected count 必须为 4。任一自动批准场景都必须命中
expected count，并包含对应 confirmed content。

Containment comparator 只在 source coordinates 工作：按 ordinal 取得 final output sampling
footprint 经 inverse transform 后的 source polygon，使用冻结的 half-open pixel-boundary
语义，要求它完整包含 baseline 对应的 `confirmed_integer_boundary_polygon`。允许 footprint
更大、相邻 ordinal footprint 重叠或包含邻片像素；不比较 IoU、box parity 或贴边误差。
Output root 必须是新建空目录；全部 completion expectations 满足时 exit 0，合法运行但
completion gate 失败时 exit 1，identity/schema/path 等 preflight 失败时 exit 2。

Partial 全量 audit 不盲扫 `Test/`；唯一 validation inventory 是
`Test/manual_review/manifest.jsonl` 中的 canonical current records。对其中
`strip_mode=partial` 的 basename，filename parser 只接受
`^(pass|unknown)_X5_([1-9][0-9]*)_([0-9]+)\.(tif|tiff)$`（TIFF suffix
大小写不敏感）；标注 count 必须位于该 format 的有效范围，并与黄金 cohort/baseline 中的
count 一致。未被 manifest 引用、仅为不可变 confirmed baseline 保留的旧路径/symlink 可以
按 SHA 解析 oracle，但不属于 filename audit，不得造成错误。Manifest 内重复 `sample_id`、
重复 canonical path、缺失/畸形 filename 或越界 count 是 regression preflight error；
重复 source SHA 允许存在，但必须分组报告，不能宣称为相互独立的真实样片。上述 preflight
错误都不是 detector 结果，不得转成 `needs_review`。标准 Hook/CI 不依赖 ignored
`Test/`；runner 的纯
schema/preflight contracts 进入 `tools/verify full`，具备本地黄金 TIFF 时的 14 场景运行
才是物理 completion gate。

其余 102 张没有人工确认 geometry，不参与 accuracy 完成判定，也不叫真实 holdout。它们
仍可用于 read-only measurement calibration、coverage matrix、性能与回归观察。当前 51 张
partial 原图由用户把 count 写为 `X5_<count>_<index>.tif`；该 count 是 validation-only
用户标注。Regression driver 可以在调用 detector 前解析它，runtime detector、prior、score、
Gate 与 selection 不得读取 filename。51 张中 41 张是 `pass_*`：目标是 auto count 选中
标注 count 并 `approved_auto`，但除黄金样片中的四张 pass partial 外，其余结果只作
非阻断质量指标；10 张 `unknown_*` 同样只作观察。

当前九张全部用于 calibration 或 stress，因此没有独立真实 accuracy holdout。这个边界不
阻止本轮计划完成，但发布声明必须写明 `real_holdout = unavailable`，不得把 102 张未确认
样片或 calibration 结果包装成独立准确度。Coverage matrix 仍至少列出
format/mode/component、方向、count、partial 起止位置、blank/contact/overlap 与可见
separator 情况；未覆盖 cell 使用物理规则与独立 synthetic contracts，并保持
`real_sample_coverage = unavailable`。

XPan 与 120-645 当前没有真实 fixture，短期也不把补样片列为前置任务。它们继续使用
`FramePhysicalSpec` 的明确 components、通用 bounded search 与 synthetic contracts；
真实输入仍经过同一 CandidateGate/DecisionGate，不因格式缺样片而强制 review。发布前可
声明 contract coverage，但在获得真实样片前不得宣称 real-TIFF accuracy、回归或性能覆盖，
也不得用其它格式的最近值建立隐藏 fallback。

物理验收顺序：

1. 校验 tracked 九张 cohort 与 ignored confirmed baseline 的 source SHA、current path、
   count、expectation 和 role；filename count 只由 regression preflight 读取；
2. 九张人工 baseline 检查 count/order/ownership/confirmed content containment。八张
   nominal 可校准，S098 只作 stress、不反向估计 nominal tolerance；八张 `pass_*`
   （包括 S098）必须 `approved_auto`，S055 可自动批准或因具体 Gate 风险 review；
3. 五张 partial 黄金样片同时运行 explicit 与 auto count。四张 pass partial 的 auto count
   必须选中 confirmed count 并批准；S055 若批准也必须选择 count 4；
4. 完整运行 111 张只作非阻断 coverage/diagnostic audit，单列 51 张 filename-annotated
   partial 的 selected-count confusion matrix 与 41 张 pass partial 的 auto-approval 结果；
   不用这些结果代替九张 accuracy gate；
5. 运行 dual/vertical、所有 count、片夹容量边界、XPan、120-645 与未覆盖 interaction 的
   独立 synthetic contracts，并单列 real-sample coverage gap；
6. 固定 24 张、`--jobs 2`、cold 单列、三个新输出目录，真实 TIFF 写出并复读；正式认证
   固定使用 full=`fixed_full`、partial=`auto`，并在 performance result 的每个 group 明确
   记录 count mode，不依赖“恰好省略 `--count`”的隐式行为。Explicit partial 只可作为
   另行标记的诊断 benchmark，不进入正式 median。原子切换时
   `PERFORMANCE_RESULT_SCHEMA` 更新为 `x5crop_production_performance_v3`，group receipt
   保存 `format_id/strip_mode/layout/count_mode/input_count`，不保留 v2 reader。正式合同仍是
   `median(total wall / 24) <= 5.0 秒/张`；这只认证性能与 TIFF 保真，不把未确认 geometry
   变成 accuracy truth；
7. 人工检查九张 current report、Debug Analysis 与 final output 中 observed/inferred、
   selected count、slot ownership、envelopes、protection、Gate、final box 与原 TIFF 是否
   一致。

Green test、非黄金 `pass_*` 自动批准率、score、hash、box parity 或 comparator 一致都
不能替代以上九张物理检查；验收不要求手术刀式贴合人工边界。当前计划不要求新增黄金
样片。只有要扩大 real-TIFF accuracy 声明，或实现暴露出现有九张与 synthetic contracts
均无法代表的新物理类别时，才新增定向黄金样片；随机增加普通样片不是前置任务。
