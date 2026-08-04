# X5 Crop V4.9 当前架构

本文只描述当前运行流、数值合同和源码 owner。版本变化见
[CHANGELOG.md](CHANGELOG.md)，当前实施检查点见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## 1. 产品合同

用户提供 format。Full 使用格式固定张数；partial explicit 严格使用用户 count；partial
auto 使用唯一匹配片夹对该 format 的容量。Runtime 不猜 format、真实照片张数或 filename
count。

检测采用固定格式模板放置模型。令 `P` 为所有满足正式像素证据、格式尺寸、source-wide
geometry、count/order、局部卷片关系、共同方向和 source/lane authority，且未被机械合同排除
的完整摆放：

```text
approved_auto 当且仅当：
  P 非空且每个 output slot 均有完整摆放
  direction、source geometry、ordinal、lane 与 transform 成立
  SafeCropEnvelope 包含 P 的全部 full safety footprints
  ActualOutput 位于每个 retained physical placement 的合法输出窗口内
```

逐边合法窗口固定为：

```text
start/end  每边 = frame_width_mm  × 5%
top/bottom 每边 = frame_height_mm × 3%
```

四边分别为闭区间硬上限：刚好达到上限通过，任意正超量失败。Canonical 只负责代表性
geometry、deskew、minimum guard 与报告排序，无权删除会改变安全 union 的摆放。

## 2. 唯一运行流

```text
format / count / ScanCanvas / lane authority
→ one TIFF decode and registered measurements
→ sequence profile + provisional cross profile
→ complete template proposals and phase groups
→ template-bound top/bottom evidence
→ SharedStripDirection
→ exact materialization
→ SourceFrameGeometry + NominalPitch + LocalAdvanceRelation
→ retained complete FormatPlacements
→ canonical representative
→ SafeCropEnvelope + direct-use assessment
→ CandidateGate → DecisionGate → Finalization
→ lane-safe inverse-affine Writer
→ report / Debug Analysis
```

权限只沿这条路径前进。不存在旧 sequence DP、short-candidate 笛卡尔积、best-score
placement、blank geometry、旧 schema reader、feature flag 或并行 producer。

## 3. Format、片夹与 source geometry

### 3.1 唯一物理 owner

`FormatSpec` 同时拥有：

- `frame_width_mm` / `frame_height_mm`；
- aperture component；
- nominal gap 与允许的 local gap interval；
- full count、partial 范围；
- 适用 ScanCanvas profile 与容量。

格式尺寸 tolerance 只有一个全局 owner：

```text
frame width separation tolerance  = 1.25%
frame height separation tolerance = 0.40%
```

Tolerance 只判断观测边是否能属于同一设计模板，并在缺边推导时进入 full interval。它不是
search allowance、padding 或 direct-use budget。

### 3.2 联合 SourceFrameGeometry

每个 source 只有两个旋转等价 axis states：width 与 height。每个 state 联合保存 scale
`s` 和 normalized extent `q`：

```text
factor_min × s ≤ q ≤ factor_max × s
observed_extent_min / design_mm ≤ q ≤ observed_extent_max / design_mm
```

Scale 与真实尺寸 factor 始终相关，不能拆成可自由组合的独立区间。完整内部 opposite-edge
pair 可以收紧 source-wide state；第一张 start 或最后一张 end 的片夹遮挡只改变可见位置
约束，不改变真实照片尺寸。所有 frame 和双 lane 共享同一 source state，不存在逐帧或逐
lane scale。

120 的 54/56 mm component 分别保留。即使它们产生相同采样输出，也必须保留各自的物理
budget 约束。

### 3.3 NominalPitch 与局部卷片

理论节距直接消费联合 width state：

```text
frame_width_px(q) = frame_width_mm × q
pitch_px(q,s)     = frame_width_mm × q + nominal_gap_mm × s
```

相邻关系为：

```text
start[i+1] = start[i] + NominalPitch + confirmed_delta[i]
```

默认 `delta=0`。非零 delta 只能由一组相互一致的边缘事实证明；它只在该 adjacency 应用
一次，使后续相位整体平移，后续间隔恢复 NominalPitch。观测 gap 必须先与 format 拥有的
local gap interval 在同一 joint width scale 下求交；无交集的摆放违反硬物理合同。未确认的
宽 interval 不得逐格累积。

## 4. 测量与 template-first producer

### 4.1 一次测量

每个 TIFF 只建立一份 `source_gray`。所有 query 在执行前登记；未完整执行的 measurement
不能被消费。Search corridor、Grid、outer 与 expected position只决定 query band 和顺序，
不能创建首个照片位置或缩短 placement truth。

每个 lane 构建一份：

```text
sequence_profile  # start/end/separator
cross_profile     # top/bottom
```

Profiles 复用相同 pixel measurements，不增加 decode、第二次全图扫描或 image-sized evidence
field。Cross profile 保留固定分段的逐 trace runs；未知方向时不会先把整条 lane 平均成一条
线。

`SideTransitionRegion` 不拥有 slope。它保存 reciprocal-nearest tracking 得到的 transition
IDs、proposal interval、support、continuity、residual 与方向性 evidence；start/end 最终严格
正交于共同 top/bottom 方向。

### 4.2 PlacementAnchor

首个模板锚点必须同时满足：

- region 非 ambiguous；
- transition IDs 独立；
- trace count/fraction、continuity 与 missing-step 合同；
- gradient 和 tone/texture 合同；
- role interval 与模板相交；
- source/lane/order 无硬矛盾。

Grid、holder edge 或 expected position不能单独成为锚点。该 authority 是经后续真实样片验证
的检测假设，不声称对完全漏检的边缘作数学证明。

### 4.3 Phase groups

每个 profile run 对可能模板 role 投票：

```text
phase interval = observed run interval - template role relative position
```

单次 endpoint sweep 形成少量完整 template groups。Runs 按 coordinate 排序；每个 group/role
通过 `bisect` 查询一次，每个 phase vote 最多匹配一次。不存在 top-K 或通用 path DP。

一个 group 获得排除孤立错误相位的权限，除共同 component、source geometry、pitch、ordinal
与 authority 一致外，还必须满足：

```text
两个独立 observed roles 的模板坐标间距 ≥ 一个 frame width 下界
或
一个通过联合尺寸合同的完整 start/end opposite-edge pair
```

相邻 separator 两侧只能证明 local advance，不能单独取得全局 phase 排除权。唯一完整组可
排除只有一个独立 role、无 opposite pair、无 confirmed delta 的孤立冲突；2-vs-2 等同强度
冲突全部保留。

### 4.4 Provisional cross 与 direction

共同方向未知时，每个 cross transition 投影到 lane reference：

```text
raw coordinate interval
± |trace-reference| × tan(maximum_search_angle)
± numeric uncertainty
```

该 interval 只生成 proposal，不能用 0.40% tolerance 提前删除摆放或进入安全输出。
Template 绑定 transitions 后，每个 top/bottom role最多拟合一条 raw line；同组 angle intervals
精确相交形成 `SharedStripDirection`，然后才重新投影已有 observations、收紧 source height
state 并 materialize。不得生成第二批 placements。

每个 lane 只需一个合格的 top 或 bottom 像素锚点即可建立完整 height placement；缺失的
opposite edge 只能由同一个联合 source-height state 推导。只有同时观测到合格的 top/bottom
pair 时，才允许用其 separation 收紧 source-wide 真实高度。

Sampling-equivalent direction classes可以合并，但必须保存完整 angle safety hull。存在多个
非等价 transform class 时，`shared_strip_direction=nonunique`，下游 geometry 和 budget
unavailable，正式输出为零。

### 4.5 EnhancedEvidence

Basic 已闭合时 enhanced work 必须为零。Enhanced 只由已登记的 typed structural gap触发，
复用相同 decode、measurement cache、role band 与 coordinate index；每个 query ID 最多执行
一次。它只能确认、反驳或收紧已有完整模板，不能创建 basic 不存在的新 phase、direction、
geometry authority 或更宽 query coverage。

## 5. Retention 与 canonical

Placement 只能因以下原因删除：

- 违反 format、联合 geometry、count、ordinal、lane 或 source authority；
- 被严格 group-support 合同证明为孤立错误相位；
- 删除前后 safety footprint union、全部 legal-window intersection 与 sampling identity 完全
  不变的结构冗余。

Support、residual、tone、background preference 与 expected position只用于 canonical 排序，
不能缩小 retained set。增加有效竞争时，安全包络只能扩大或不变。

Canonical 从 retained placements 中选择一个实际可行的代表状态。固定 direction 和 joint
geometry 下，scalar weighted-Huber 只选择代表 translation；结果不在可行 interval 时使用
interval midpoint，禁止 clamp。

## 6. SafeCropEnvelope 与 budget

每个 output slot 只有一个 geometry owner：`SafeCropEnvelope`。它保存：

```text
placement_source_footprint
required_source_footprint
constrained_source_footprint
saturation_facts
mapped_output_box
```

构建顺序：

```text
outermost(
  union(retained full safety footprints),
  canonical minimum-guard footprint
)
+ exactly one 1 source-px visible interpolation guard
→ source/lane authority intersection
→ direct transform of continuous vertices
→ integer half-open mapped box
```

Full uncertainty 与 minimum guard只取较外侧者，绝不相加。Authority 不得裁掉 retained
placement 或 canonical；只允许裁掉 guard 并记录 saturation。Footprint 不先变成 source AABB，
避免 deskew 时二次膨胀。

Minimum guard：

| Format | start/end 每边 | top/bottom 每边 |
|---|---:|---:|
| half | 0.15 mm | 0.25 mm |
| 135 / 135-dual | 0.25 mm | 0.25 mm |
| 120-645 | 0.30 mm | 0.25 mm |
| 120-66 | 0.40 mm | 0.25 mm |
| XPan | 0.45 mm | 0.25 mm |
| 120-67 | 0.50 mm | 0.25 mm |

Budget 不从 full interval 或 output 反推。每个 retained physical interpretation 都以设计尺寸
和自己的 joint geometry计算逐边 expansion；实际输出必须位于全部 MaximumLegalWindows 的
intersection。Pixels 转毫米使用可行 scale minimum，不能低估外扩。

## 7. Gate、Finalization 与 Writer

唯一 ordered Gate checks：

```text
scan_canvas_authority
output_slot_count
format_placement
shared_strip_direction
source_frame_geometry
slot_ordinal_assignment
source_lane_authority
placement_set_containment
direct_use_budget
output_transform
```

全部要求 `SUPPORTED`。`CandidateGate` 只冻结 typed facts；`DecisionGate` 导入同一个 check
tuple，并将 typed gap 与 count mode机械映射为 final reason。不存在字符串扫描、第三个 Gate
或 competition reason 推断。

`needs_review` 时 Finalization 不暴露正式 boxes，Writer 不写照片 TIFF。Approved Writer
消费 mapped box、transform 与 lane sampling authority；bilinear 四个 taps逐个检查 authority，
越出 lane 的 tap 使用 photometric background，不能 clip 后采入另一 lane。每个正式 TIFF 只
从原 TIFF 执行一次 inverse-affine sampling。

## 8. Report、Debug 与 schema

Current-only schema：

```text
report      = source_coordinate_format_placement_v2
S062 profile = x5crop_fixed_sample_profile_v5
```

Report 保存 raw observations、profiles、phase groups、direction classes、joint source geometry、
local advances、retained placements、canonical、safe envelope、budget、两级 Gate、transform 与
最终 I/O facts。它是审计产物，不是 detection cache。

Debug Analysis 只读取 runtime/report facts，保持四层布局：source authority、pixel evidence、
canonical placement、protected output。它不重新计算 detection、geometry 或 budget。

## 9. 工作量与性能

Producer 的结构上界：

```text
phase_vote_count
  ≤ profile_run_count × ordered_role_count × component_count

template_role_lookup_count
  ≤ template_group_count × ordered_role_count

template_role_match_count
  ≤ phase_vote_count

local_relation_evaluation_count
  ≤ template_group_count × (slot_count - 1)
```

内存为一维 profiles、有限 runs/votes/groups 与 geometry，禁止新 image-sized field、row index、
Hough slope family、通用 DP 或新依赖。单输入临时内存上限保持：

```text
10 × source_pixels + 32 MiB
```

正式性能固定 24 sources、168 tasks、`--jobs 2`、24 decodes 与相同 I/O。V4.9 必须满足
`≤5.0 秒/输入`，并在配对 MAD noise 之外快于冻结 v4.2.8；新 noise 不能扩大允许回退。

## 10. 源码 owner

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | format 尺寸、tolerance、gap、count 与 ScanCanvas fit |
| `x5crop/detection/source_core.py` | source/lane authority |
| `photo_geometry/measurement.py` | transitions、SideTransitionRegion 与 raw boundary fit |
| `photo_geometry/template_profiles.py` | profiles、roles、phase votes 与 indexed grouping |
| `photo_geometry/source_geometry.py` | joint axis geometry、SourceFrameGeometry 与 NominalPitch |
| `photo_geometry/template_model.py` | template proposal、local advance、placement 与 work facts |
| `photo_geometry/template_first.py` | producer orchestration 与 exact materialization |
| `photo_geometry/output.py` | SafeCropEnvelope、sampling identity 与 direct-use assessment |
| `x5crop/geometry/convex.py` | 唯一 convex footprint primitives |
| `x5crop/detection/candidate/` | CandidateGate facts |
| `x5crop/detection/decision/` | final status 与 reason mapping |
| `x5crop/detection/final/` | approved geometry exposure |
| `x5crop/export/` | lane-safe TIFF sampling、write 与 readback |
| `x5crop/report/` | current report read model 与 validation |
| `x5crop/debug/` | current facts 的只读可视化 |
| `tools/verify` | 唯一 tracked verifier 入口 |
| `tools/release/` | standalone 与 ZIP manifest |
