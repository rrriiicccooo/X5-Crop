# X5 Crop 架构说明

本文件是 V4.9 当前运行流、数值合同与源码分层的唯一架构说明。用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`，版本行为见 `CHANGELOG.md`。

## 1. 当前能力边界

V4.9 当前开发树是一个物理诚实的 source-core 安全基线。系统尚无获批的独立
`FrameGridEvidence` phase authority，因此所有需要定位 frame 的输入都保持
`needs_review`，不写出 frame TIFF。

这不是临时 fallback。它是 current runtime 的正式能力边界：

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
Grid 合同；不能在没有 phase authority 时定位 frame。

### 3.2 Scan canvas 与分轴 scale

照片格式与 scan canvas 是不同 owner。唯一匹配的 `ScanCanvasPhysicalSpec` 产生：

```text
s_long  = observed_long_axis_px  / canvas_long_axis_mm
s_short = observed_short_axis_px / canvas_short_axis_mm
```

当前没有额外 measurement uncertainty 时，两者分别是 point interval。一个轴的数值
不得扩宽另一个轴。TIFF resolution/DPI 只作为 I/O metadata 保留，不参与检测。

无匹配或多个 profile 同时成立时，scan-canvas authority 不可用。系统不得选择最近
profile。

### 3.3 Validation domain

`SourceStripValidationDomain` 只来自唯一 scan canvas/lane 与 source extent：

```text
work_box = 完整 scan canvas 或完整 lane 的半开 cell-edge Box
```

它不得由 holder、photo edge、separator、content、Grid 或 deskew 缩窄。水平和垂直布局只
交换 work axes，不重采样 source measurement。`full` 与 `partial` 使用同一个短轴 domain；
partial count 仍只描述完整设计 slot。

`135-dual` 使用确定的中心分区，每个 lane 独立建立 domain。当前 dual-lane 仍保持 review。

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

## 6. 毫米 output protection authority

Pixel bleed 接口与模型已删除。唯一 owner 是格式级毫米设计表：

| 格式 | long | short |
|---|---:|---:|
| half | `0.15 mm` | `0.25 mm` |
| 135 / 135-dual | `0.25 mm` | `0.25 mm` |
| 120-645 | `0.30 mm` | `0.25 mm` |
| 120-66 | `0.40 mm` | `0.25 mm` |
| XPan | `0.45 mm` | `0.25 mm` |
| 120-67 | `0.50 mm` | `0.25 mm` |

当前没有 frame geometry，所以 authority 只进入 report，`applied=false`。它不能补救
Grid、选择候选或创建输出。

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

真实 TIFF 认证只有未来独立 Grid authority 恢复 frame export 后才可执行：

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
