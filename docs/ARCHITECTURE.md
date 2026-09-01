# X5 Crop V5 架构

本文是 V5 已确认产品合同、运行流、数值合同和源码 owner 的唯一说明。版本变化见
[CHANGELOG.md](CHANGELOG.md)。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 1. 产品定义与输入 authority

X5 Crop 是已知胶片模板的自动对准器，不是通用照片边界检测器。

```text
用户 format + 用户确认 count
→ format 设计先验与 source-level W/H 模板
→ 从整条片带到局部边界的有界对准
→ 合法 placement 竞争
→ 唯一获准的 selected placement，或拒绝自动选择
→ selected-only source-space 安全 polygon
→ CandidateGate / DecisionGate
→ 可选 lightweight deskew
→ 整张 source 自动输出或人工检查
```

- Format 始终由用户提供，像素、文件名和片夹容量都不能改写。
- Count 包含中间空白曝光格；不做 blank suppression。
- 省略 count 表示用户确认匹配片夹的默认完整格数。
- 明确 count 表示用户确认实际 slot 数，必须满足 `1 <= count <= holder_full_count`。
- 同一 source SHA 可以建立多个显式 count 的独立 evaluation task；它们复用同一物理边界标注，但
  分别验证对应 slot 解释和输出。Source SHA 只固定 format 与像素身份，不固定 count。
- 同源 count 变体按共享物理 `boundary_pair` 映射真实 Frame。不同 count 可以合法改变 ambiguity 和
  `approved_auto` / `needs_review` 终态，但增加或省略空白、残缺 slot 不得把已有真实 Frame 重定相到
  危险位置。任一自动批准的变体都必须独立满足同一黄金安全合同；Review candidate 的跨 count 分歧只
  作 development diagnostic，不等同危险输出。
- Runtime 不保存 full/partial mode。是否铺满是 placement 选定后的物理事实，不是搜索权限。
- `135-dual` 默认 12 格、每 lane 6 格。其它明确 count 产生
  `unsupported_dual_count` 并进入 review，不猜 lane 分配，不运行自动 placement。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。

唯一 count 数据流是：

```text
SlotCountRequest
→ matched holder
→ ResolvedSlotCount
→ ResolvedOutputSlots
```

## 2. Format、片夹与尺度

尺寸按照片长轴 × 短轴记录：

| format | 设计 W × H | `G_format` 局部搜索先验 | 默认完整格数 |
|---|---:|---:|---:|
| `135` | 36 × 24 mm | 2 mm | 6 |
| `135-dual` | 每 lane 36 × 24 mm | 2 mm | 12，6/lane |
| `half` | 18 × 24 mm | 1 mm | 12 |
| `xpan` | 65 × 24 mm | 2 mm | 3 |
| `120-645` | 42 × 56 mm | 无 | 4 |
| `120-66` | 56 × 56 mm | 无 | 3 |
| `120-67` | 70 × 56 mm | 无 | 普通片夹 3，短片夹 2 |

片夹画布提供大致 px/mm、有效区域和 format/count 相容性，不提供照片组长轴中心。Frame 兼容范围由
`ApertureCompatibilitySpec` 以同一混合物理模型计算，不为 format 或样片保存独立 tolerance：

```text
guard_W = max(0.95 mm, 2.4% × nominal_W)
guard_H = max(0.70 mm, 1.8% × nominal_H)
W compatibility = nominal_W ± guard_W
H compatibility = nominal_H ± guard_H
holder extent = 物理名义范围 ±3.5%
```

W 与 H 使用不同参数，但所有 format 共用公式与 owner。当前数值使用 105 个合格 source、494 个完整
Frame 校准：只接受 `slot_kind=image` 且 START、END、共享 top/bottom 全为 `directly_visible` 的记录，
自然排除 `source_truncated`、`human_width_estimate`、残缺曝光与空 slot；先对每个 source 取中位尺寸，
再按名义轴长分组计算相对名义值的绝对偏差 q95，以最小总 guard 拟合混合式，最后分别向外量化到
0.05 mm 与 0.001 ratio。全部合格 source 都参与统计，超出 q95 guard 的 source 进入 review 诊断，不变成
format 或样片例外。该 development 校准尚未经过 sealed 数据验证，因此不能宣称未见来源泛化；缺少
sealed cohort 本身不阻断首版发布。

设计 W/H 是跨相机的有界搜索先验，不是每台相机共享的绝对片门尺寸。唯一 placement 闭合后，同一
source 的直接 START/END 可以收紧共同 W，唯一直接 aperture top/bottom pair 可以收紧共同 H。Direct
W/H observation 分别保留自己的 identity；直接可见边界的 native coordinate 始终优先，catalog 或
比例推断都不能把它拉回名义尺寸。相机 aperture 差异与该轴扫描比例差异在像素域可能不可区分，本项目
只保存能够安全证明的 source-level extent 与相关推断。

`G_format` 只决定首次理论搜索位置，不能单独建立 phase、pitch 或 placement。X5 长图不依赖齿孔。

### 2.1 画幅比例 authority

Format 的 `actual_W / actual_H` 是强物理先验，但不是零不确定性的常量。当前
`ApertureAspectRatioAuthority` 使用各 format 的合格 source-level 中位比例与设计比例形成
`R_raw` 包络，再把第 2 节两轴混合 guard 传播成该 format 自己的 `R_guarded`：

```text
W_px = actual_W × scale_W
H_px = actual_H × scale_H
R = actual_W / actual_H
gW = guard_W / nominal_W
gH = guard_H / nominal_H
R_min = R_raw_min × (1 - gW) / (1 + gH)
R_max = R_raw_max × (1 + gW) / (1 - gH)
H_px ∈ W_px × (scale_H / scale_W) / R_guarded
```

`135`、`half`、`120-66` 与 `120-67` 已注册 development calibration；没有合格黄金 observation 的
`xpan`、`120-645` 保持 unavailable，`135-dual` 复用同一 135 Frame 物理定义。不同 format 得到不同
数值，但只能通过上述同一公式复算。旧的固定 `0.01`、统一 `1%` 外扩和按名义比例零误差换算都不存在。

| 证据状态 | 结果 |
|---|---|
| direct top/bottom 唯一闭合 H | 保留 native coordinate；direct H 优先 |
| 至少两张完整直接 Frame 闭合 source W、共享 scale identity 与 `R_guarded` 均完整 | 产生一份相关 H interval；不冒充 direct H，不增加 constraint rank |
| ratio calibration、direct source W 或共享 scale identity 不可用 | `aperture_aspect_ratio_authority_unavailable` |
| ratio 推断与 format H compatibility 不相交 | `aperture_aspect_ratio_physical_prior_conflict` |
| 已支持的 ratio 推断与唯一 direct H 不相交 | `aperture_aspect_ratio_direct_conflict` |
| 推断 uncertainty、residual 与 bleed 耗尽逐侧 5% 预算 | `aperture_aspect_ratio_budget_exhausted` |

Direct H 存在时优先承担 cross；ratio authority 的 unavailable、physical-prior conflict 或 budget failure
不会覆盖 direct H。只有一份本来受支持的 ratio interval 与 direct H 真正冲突时才阻断。该 authority
只能消费既有 source W 与共享 scan-scale identity，不读取新 TIFF、不选择 phase/ordinal、不创造双侧都
不可见的 Frame。Report 与 Debug 显示 calibration identity、`R_raw/R_guarded`、`gW/gH`、W provenance、
推导与有效 H interval、预算、是否被 cross 消费、相关性和 typed failure。

Separator 不复用 aperture compatibility。`G_format` 是理论搜索中心；实际 separator gap 由 material
两侧直接 START/END 与 local advance 拥有。黄金 gap 的局部与跨 source 变化远大于 aperture 轴尺寸，
用名义 gap 周围的对称混合 guard 会同时过窄又接近零下界；后续如需扩大召回，应单独校准非对称的
候选无关搜索 coverage，不改变已观察 gap。Holder extent 目前只有独立的片夹设计范围 ±3.5%；同一批
holder-normalized 黄金尺寸不能反过来独立校准它，除非以后取得外部 holder metrology。`1.1H` enclosing
support、lattice residual、`max(0.15 mm, 0.7%W)` bleed 与逐侧 5% 输出上限分别拥有输出包络、统计残差、
产品 bleed 和最终风险预算，不能合并成 aperture tolerance。

## 3. 几何词汇与权限

“outer”不能再表示多个不同对象：

- `CoarseStripSupport`：片带大致位置、搜索 corridor 和局部测量所需的粗方向。它可以来自片夹边、
  胶片材料边、照片边或其它长距离稳定结构，但不能直接决定 crop 或输出 deskew。
- `OuterBoundaryObservation` / `PhotoBoundaryAnchor`：role-free 像素观察与模板绑定后，才可能
  获得 first、last、top 或 bottom 的照片边界权限。
- `CanonicalPlacement`：format、count、phase、pitch、cross 和直接 separator 已证明的有界 local
  advances 共同决定的 source-axis 固定矩形集合。
- `PhotoGroupOuter`：从已选 placement 的 first start 与 last end 推导的长轴范围；不反向参与选位。
- `OutputFootprint`：联合不确定性、直线残差和产品 bleed 后，在 source 坐标中已经确认安全的区域。

这些词汇只映射到一套 current type：`CoarseStripSupport` 保存 role-free aggregate observation，
`OuterBoundaryObservation` 使用 `BoundaryEdgeObservation`，模板绑定后的 `PhotoBoundaryAnchor` 保存在
sequence/cross provenance，`CanonicalPlacement` 使用 `FormatPlacement`。不再建立同义 wrapper。

项目无需把非照片外侧支撑继续分类为 holder edge 或 film edge；两者都只能提供 coarse support，
或在满足完整 enclosing 合同时成为输出边界。同一 raw observation 可以承担多个职责，但 identity
只有一个，不能重复计为独立证据。

Sequence 的坐标身份与证据相关性是两种不同事实。`observation_id` 是 edge-family registration 后唯一
能够表示同一物理坐标的 identity；`evidence_group_id` 只表示多条 edge 共享同一 material/transition
证据，需要在 phase、pitch、W 与 constraint rank 中去重。一个 separator 的左右两侧拥有不同
`observation_id`，但可以共享同一 `evidence_group_id`。相关组不能把两个坐标合并成连续 placement、
生成中间位置或隐藏 runner；缺少相同 `observation_id` 时必须保持离散竞争。Production 不保留旧的
`independent_support_id` 同义字段。

| 两个 role binding | 坐标关系 | 证据关系 | placement 行为 |
|---|---|---|---|
| 相同 `observation_id` | 同一 canonical coordinate | 必然相关 | 可以合并同一连续 placement |
| 不同 `observation_id`、相同 `evidence_group_id` | 两个物理坐标 | 相关，只计一组独立 evidence | 保留离散竞争，不得合并 |
| 不同 `observation_id`、不同 `evidence_group_id` | 两个物理坐标 | 独立 | 保留离散竞争并分别计证据 |

Edge-family registration 是 `observation_id` 的 owner；`template_phase_candidates.py` 只把已登记的
separator material/component 映射成 `evidence_group_id`，并由 `SequenceRoleBinding` 同时保存两种身份。
`template_phase.py` 只读取 coordinate identity 判断连续 placement；phase、pitch、W 与 lattice rank
只读取 evidence group 去重。无法满足第一行时，Gate 通过现有 `discrete_phase_ambiguous` 保持 review，
不增加 proximity、residual 或 score 旁路。

## 4. Source-axis placement 与可选 deskew

检测中的 placement 没有角度自由度。每个 lane 独立拥有 phase、pitch、cross offset 和有界 local
advances；全部 aperture frame 的 start/end 与 top/bottom 都沿 source axes。双 lane 只共享相容的
W/H 与 px/mm，不共享检测角度或输出旋转权限。

`SharedStripDirection` 只保留在 cross evidence 内，用来证明局部 fragment 的方向完整、两侧平行或
enclosing support 的同一物理状态；它不是 `FormatPlacement` 属性，不能旋转 frame、改变 phase、
选择 winner、进入 Gate 或拥有 deskew。Role-authorized aperture binding 只能在自己直接采样的 trace
范围内，把短轴 offset 投影到某个 frame center；超出该范围不得外推。投影只移动 fixed-H 的
top/bottom 位置，边界仍与 source axis 平行。

局部 aperture slope、弯曲和逐 trace departure 只扩大 selected placement 的输出保护。只有直接
`ENCLOSING_SUPPORT_PAIR` 因自身就是最终 top/bottom，才在同一联合状态中保留自己的边界 slope。
Sequence 从不提供角度。超过预算就 review，不建立逐帧角度、自由四边形或曲线 detector。

输出 deskew 是与模板无关的 role-free 旁路 observation。只有 `DecisionGate` 已批准输出时，
finalization 才在整条片带的 6–24 个有界稀疏位置读取最外侧暗边；review 不执行这项扫描。两侧分别
稳健拟合，只有 slope、residual 和角度范围相容时才产生角度。它不识别 holder、film 或 photo edge，
不可用或矛盾时返回 typed skip reason 和 `None`，绝不伪造 `0°`。`--deskew auto` 是默认值；
`--deskew off` 不执行这项旁路观测并记录 `user_disabled`。两种模式都不能改变 placement、Gate 或
final status。

Observation 继承 v4.2.8 的数值合同，但保留 V5 的双侧必需与 typed skip：暗像素 `<245`，outer row/
column 支撑至少 1%，outer 长轴至少 100 px；沿长轴约每 350 px 取样，总数限制为 6–24。每条 trace
至少包含 `max(10 px, 5% × short_extent)` 个暗像素；每侧至少 4 点。MAD inlier 容差为
`max(2 px, 3 × MAD)`，最终中位 residual 不超过 `max(3 px, 0.003 × short_extent)`，双侧 slope 差
不超过 `0.006`，可报告观测角绝对值不超过 `2°`。`2°` 只是 measurement plausibility，不授予输出
旋转权限。

## 5. 从整体到局部的模板编译

V5 吸收 v4.2.8 的有效行为，不复制其代码、未经校准且直接决定终态的任意加权分数、把未校准 Grid
当作答案的 fallback，或 content equal-split：

```text
format/count/holder 编译固定模板、coarse intents 与工作上界
→ 两个 role-free 全片 aggregate query 建立 CoarseStripSupport
→ coarse support 与固定 lattice 生成有限理论窗口
→ 全部精测窗口一次登记、一次读取
→ region/band-first observation 与局部边界拟合
→ residual pattern
→ placement closure
```

`TemplateMeasurementPlan` 在观察结果产生前冻结：

- `TemplateSpec` 与物理单位；
- sequence、separator、top、bottom 和 content query intents；
- phase、role、cross、placement、像素与内存上界。

Coarse pass 对每个 lane 只执行一个长轴和一个短轴 aggregate query，输出保守 interval 和 receipt；
aggregate interval 本身没有角色、ordinal、placement 或输出 deskew authority。短轴 query 的各条
已注册 trace 若能直接闭合为双侧 track，可以在满足第 8.2 节全部条件时建立 enclosing support；
这份 authority 来自逐 trace 直接观察，不来自 aggregate interval。Long-axis precision 从左右 holder 端
分别投影 format/count 编译的完整且相关的 `W/pitch` 状态，合并为候选无关 role search core；没有
direct coarse observation 时才使用一个保守全长窗口。所有计划内的精测窗口随后一次登记、一次读取；
某个 selected placement 是否真正被覆盖，必须在测量后按第 7 节逐 adjacency 证明，不能从“查询已全部
执行”反推。不能为某个 candidate 重读 TIFF、扩张全图搜索或 winner-specific requery。

同一 trace lattice 只建立一次全局 normalization baseline，再由理论窗口切出局部测量。Baseline
不产生 transition 或 placement evidence；其像素和临时内存仍完整计入 receipt，不能伪装成免费工作。

正常片条在 outer、phase/pitch、separator topology、闭环、content 和输出预算均唯一且相容时停止。
Registered measurement 始终 candidate-independent；每个已唯一绑定的直接 separator 可以在同一次
O(count) 传播中约束自己的 adjacency advance，但不能触发额外像素读取、fit pass、winner-specific
query 或无界 hypothesis。

## 6. Observation 与独立证据

Registered measurement 一次生成 role-free、候选无关、数量有界的观察。

### 6.1 `BoundaryEdgeObservation`

保存局部转变的位置区间、方向区间、极性、内外背景关系、空间支持和唯一 observation ID。Raw edge
不知道自己属于哪一格或哪个角色；模板只能在位置与职责相容后绑定它。

同一份 registered 灰度窄带一次产生 gradient、tone、texture、polarity 与纵向一致性等 typed
measurement。它们共同描述同一个 observation，可以互相加强、否定或形成 missing/conflict；不能把增强图、
另一套阈值或另一次读取包装成平行 detector，再按最高分挑赢家。

### 6.2 `SeparatorBandObservation`

`SeparatorMaterialPolarity = dark | light`。同一个 candidate-independent registered measurement
owner 只配对每条 trace 中相邻的反向 edge：`- / +` 描述暗 material，`+ / -` 描述亮 material；不得跳过
中间 transition 拼出更有利的 pair。Band 保留 polarity、material 宽度、位置区间、两侧 edge identity，
以及三个固定高度区域各自的 oriented tone contrast、core texture 和 typed state。一个 separator 的两条
edge、band、多条 trace 和全部梯度像素仍是一份物理证据，不能变成多票或第二 detector。

每个高度区域只有在 oriented material contrast 的完整下界同时高于 uint8 量化步长与该区域 core
texture 上界时才为 `supported`；否则明确为 `tone_unresolved` 或 `material_non_uniform`。不同区域不能各自
贡献 tone、texture 或 polarity 后拼成一份支持：

| 已观察区域与 material 状态 | `SeparatorBandObservation` | 权限 |
|---|---|---|
| 至少 2 个独立区域一致支持同一 polarity | `support` | 只形成局部 material support |
| 3 个区域全部支持 | `support` | 可建立 source-wide END→START pair authority |
| 3 个区域均已观察，但支持少于 2 个 | `contradiction` | 不授予正向权限；同角色 edge 竞争产生 `separator_material_conflict` |
| 少于 2 个区域支持且没有完整三区域反证 | 无 band | `unavailable`，不得推断缺失证据 |
| material gap 超出当前 normal gap 上界 | 保留原始 material fact | 不得创造 normal phase、ordinal 或直接角色权限 |

局部 band 只能连接两条已经由各自像素观察取得相容角色的 edge，不能覆盖或创造角色；存在多个局部解释
时不按强度或距离挑选。正常范围内的 band 可以提供 phase anchor；只有它的两侧 edge 已共同绑定到同一个
明确 adjacency 时，实测宽度才能约束该处 local advance。亮、暗两种 polarity 使用完全相同的权限和
失败合同；极性本身不参与 winner 评分。

### 6.3 跨高度 aggregate 与宽缓 material boundary

同一个已登记 `SEQUENCE_BASELINE` 只生成一次全长灰度测量，`SEQUENCE_ANCHOR_WINDOW` 只切出已经登记的
坐标与 transition ownership。它固定分成三个高度区域，并产生两种互不冒充的 typed aggregate：

- `CROSS_HEIGHT_AGGREGATE` 在原有局部 signed gradient、tone 与 texture 上联合弱信号；
- `BROAD_MATERIAL_AGGREGATE` 同时使用 `0.25 mm` 与 `0.50 mm` 两个物理尺度的 signed tone、两侧
  texture 与 material uniformity。两个尺度必须保持相同 polarity，同一侧必须在两个尺度上都是更均匀的
  background，完整 tone contrast 下界还必须高于该侧 texture 上界与 uint8 量化步长。

每个 broad 高度区域内部要求多数 trace 支持同一 polarity 与 background side；三个高度区域还必须在
位置区间、方向区间、polarity 和 background side 上一致。宽缓通道不伪造 gradient，不降低局部 edge
阈值，也不扩大既有 query、transition ownership、local measurement halo 或 TIFF 读取。它只复用已经
完整登记的全长 baseline；新增数组和计算完整进入 work/RSS receipt。

两类 aggregate 都不知道 role、ordinal 或 placement。`aggregate_edge_support.py` 是 edge resolution 与
separator pair 投影的唯一 owner：

| aggregate 与既有 edge/material 的关系 | typed resolution | 权限 |
|---|---|---|
| cross-height 唯一匹配一条空间支持不足的 direct edge | `bound_direct_edge` | 保留 direct native coordinate，以 `aggregate_union` 补足三区域支持，只计一份相关证据 |
| broad 唯一匹配一条既有 edge | `matched_existing_edge` | 保留既有 edge 原 basis；单根宽缓边不增加坐标或 direct-role 权限 |
| 没有匹配既有 edge | `standalone_edge` | 只进入 evidence、report 与 Debug；没有完整 pair 时不进入 phase、outer 或 placement |
| 两条已解析 aggregate edge 依次具备 END/START 角色，且其间 material 由三个高度区域共同支持 | `standalone/matched edge + aggregate separator band` | 作为一份 `separator_pair` 投影到 placement；实测 gap 可以约束该 adjacency 的 local advance |
| 匹配的既有 edge 已覆盖三个高度区域，或已由另一 aggregate 支持 | `redundant_existing_edge` | 保留既有 edge，不重复计票，也不能让未成 pair 的 aggregate edge 进入 placement |
| aggregate pair 的任一 resolved edge 已属于一组 supported direct/较早 aggregate separator | 保留原 separator 为 canonical | 新 pair 只作诊断，不能用另一侧重新解释同一物理 edge 或改变既有 placement |
| 同一 aggregate 匹配多个既有 edge | `multiple_compatible_existing_edges` | typed contradiction，不授予 aggregate 权限 |
| 多个可绑定 aggregate 竞争同一既有 edge | `multiple_aggregates_for_one_existing_edge` | typed contradiction，不授予 aggregate 权限 |
| edge/material 少于三个支持区域、跨尺度或跨高度状态冲突、角色不相容、coverage 不完整 | 无合格 aggregate pair | `unavailable`，保持原 evidence 与安全终态 |

单条 aggregate edge 不能创造相位候选。只有完整 separator pair 才能把 standalone 坐标带入唯一 placement
模型；同一物理 pair 已有 direct band 时 direct 事实保持 canonical，aggregate band 不再投票。缺失
direction 不是反证，但两份明确且不相交的 direction interval 必须保留为不同解释。Development report 与
Debug 分别显示 local aggregate、broad material、resolution、pair、typed failure 和工作量；Debug 不重新
测量或求解。

### 6.4 Cross observation

Top/bottom observation 的局部线段先保持独立。方向相同、坐标接近、残差较小或 trace 较多都不足以
证明多个 fragment 属于同一物理 side track；必须有 source-spanning 连续性，或明确的空间连接和
独立长轴支持。

### 6.5 Content observation

内容层保存二维占用单元或连通区域，只作 negative veto。它不能移动边界、选择 winner、创造
placement、平分照片或把内容 bbox 当 crop。角落擦边、锯齿、尘点、黑片和低纹理保持中性；只有
可靠二维内容连续跨过完整输出边界时才否决。

## 7. Sequence phase、pitch 与偏差

Sequence 在方向规范化长轴上使用固定 lattice：

```text
role = phase
     + slot_index × source_pitch
     + local_prefix[slot]
     + (W if END else 0)
```

这条 Grid 是唯一 placement 的主生成模型，不是 detector 失败后的 fallback。零偏差状态由 format 的有界
`W/H/pitch` 先验、`local_delta = 0` 和 normal adjacency 组成；像素观察随后收紧 source W/H、确定
absolute phase、保留直接 START/END 的 native coordinate，或给某个 adjacency 增加一次 local advance。
Grid 始终可以生成一个待检验的默认 placement，但它不能仅凭自己取得 `approved_auto` 权限。

- 连续小误差保存在一个 placement 的区间中。
- 不同 ordinal mapping 或相隔明显的 phase 是离散 placements，保留 winner/runner，绝不平均。
- Holder 长轴中心不参与 phase。省略 count 也不提供居中权限。
- Format/count 可以定义尺子的刻度和 ordinal，但不能知道尺子应放在 TIFF 的哪一个像素；absolute phase
  必须来自直接 outer、START/END 或其它独立 anchor。
- 已绑定的直接角色在最终 placement 中保留自己的 native canonical coordinate、完整 observation interval
  与 observation identity；固定 Grid 只组织 ordinal 并补齐未观察角色，不能覆盖直接位置。
- 全局未知量固定为 `(phase, W, source_pitch)`。每条已绑定直接 START/END 形成一行带 observation
  provenance 的线性约束；外部直接 phase、共同 W 或 pitch authority 也只能各形成自己拥有的一行。
  `GlobalLatticeAuthority` 保存全部约束与矩阵秩，只有 joint rank 为 3 才表示三个未知量独立闭合。
  Raw edge 数、同一位置的重复支持和连续缺失 adjacency 数都不是闭合证明。
- Rank 3 直接坐标系统由 `template_phase_candidates.py` 在同一个连续 placement 内联合拟合
  `(phase, W, source_pitch)`。无约束最小二乘若落在已编译的 phase、W、pitch 与
  `pitch-W` 全部区间内，记录 `direct_least_squares`；若只越过这些硬区间，求解器在同一可行集合内取得
  最近的 `bounded_direct_least_squares`，不能把 W/pitch 整体退回 catalog 中心后继续沿用不相容的
  phase。同一离散 placement 经候选无关 source pitch 或 local advance 重拟合时，报告保留该连续
  lineage 中约束最强的一次参数依据；只有 template 身份、ordinal offset、phase 区间及共享
  observation-role 映射一致才允许继承，runner 之间不能串用。区间不会扩张，直接 role 的 native
  coordinate 也不会被拟合值覆盖。Source W 只能在离散与 local competition 已唯一结束后收紧 selected
  fit 的连续 W，不属于候选重拟合，不能改变 lineage、ordinal、winner 或 runner。受约束后仍存在另一离散
  ordinal/edge 解释时保留 runner 并产生 `discrete_phase_ambiguous`；连续最小二乘不能充当 best-score。

Production phase competition 在离散比较前，对每个去重后的 bounded candidate 对称执行
`DirectRoleBindingAuthority` 和 `PhaseCandidateAuthorityProjection`。`contradicted` 表示直接物理反证，
始终终止该解释；`unavailable` 只表示某个被绑定像素线没有 native-coordinate 权限，因此先把这些 binding
投影出去，再判断剩余直接坐标能否独立承担同一个离散解释。投影只允许使用原 candidate 已经绑定且获得
权限的坐标，按原 template、ordinal、local topology 和完整硬区间精确重拟合；不能新增 observation、
改变离散 identity、生成新 Frame 或读取像素。

投影后的 candidate 重新按 coordinate identity canonicalize，再与全部其它 eligible candidate 对称竞争。
同一连续 placement 的互补直接证据仍可合并，非等价 projected/unchanged placement 仍保留 runner。
原弱线只保存在 projection provenance；它不能继续拥有 phase、收窄 W、提高 constraint rank 或消失于
Debug。若所有解释都终止，最佳原 candidate 只作为诊断几何保留，并以 projection outcome 说明首个缺口，
不得退回 residual、support 或 Grid 强选。

| bounded candidate 事实 | projection outcome | 离散竞争结果 |
|---|---|---|
| 全部直接 binding 均获授权 | `unchanged` | 原 candidate 进入竞争 |
| 仅有 `unavailable` binding；投影后每张 Frame 至少保留一侧直接坐标，且相关 evidence-group 去重后的 `(phase,W,pitch)` rank 为 3 | `projected` | 只以保留坐标重拟合同一离散 identity，再进入竞争 |
| 投影会使某张 Frame 的 START/END 都没有直接坐标 | `complete_frame_unobserved` | 当前 direct-evidence 路径终止；不让该弱线创造整张 Frame |
| 保留坐标 rank 为 0–2 | `retained_rank_insufficient` | 终止；不能让已删除的弱线或 Grid 反向补 rank |
| 存在 separator material 或同角色直接反证 | `direct_role_contradiction` | 终止且反证保留；不得作为噪声删除 |
| 有界重拟合不存在，或会改变 template/ordinal/local topology/role mapping | `refit_unavailable | discrete_identity_changed` | 终止并报告 typed failure |
| 两个非等价 eligible candidate 均成立 | `unchanged | projected` 各自保留 | 继续硬物理比较；不能明确分离时 `discrete_phase_ambiguous` |

Constraint rank 只由 `template_lattice_authority.py` 计算。相同 `evidence_group_id` 的多个坐标只贡献一行；
若同组绑定多个 role，按最低 role index 选择该组的 canonical rank row，其余 native coordinates 仍完整保留，
不能因 rank 去重而合并坐标或隐藏 runner。整个 projection 只消费已登记 evidence，候选数、角色数与重拟合
次数均受原 template 上界约束，不增加 TIFF 读取或第二 detector。

| 直接约束状态 | 连续参数结果 | 离散选择结果 |
|---|---|---|
| rank < 3 | `template_interval_center` 只维持候选搜索；不能建立全局 authority | 后续由 `global_lattice_authority_unavailable` 阻断缺失角色推断 |
| rank = 3，最小二乘位于全部硬区间内 | `direct_least_squares` | 继续按既有物理支持比较 placement |
| rank = 3，无约束解越界但联合可行集非空 | `bounded_direct_least_squares` | 继续保留所有合法 runner |
| 受约束后两个离散 fit 均合法且不能等价合并 | 两者各保留自己的参数与证据 | `discrete_phase_ambiguous`，不得强选 |
- Source pitch 必须由至少两个不同直接 separator 位置或独立同角色 advance 支持。一个 separator
  只能证明自己所在 adjacency。
- 两个 separator 可以收紧 pitch，但不能用同一对事实自证 absolute phase。短片条中的两点投影
  只是一项 phase hypothesis；只有该区间内的完整合法 fit 还绑定了不属于这两个 separator 的独立
  direct support，才可晋升为 phase authority。长片条中的两点还可能跨过一个或多个已测 local advance，
  只能缩小 pitch 搜索。至少三个独立 material 位置形成周期闭环后，separator lattice 才能自行收紧
  absolute phase；不同解释仍保留为离散 placement。
- 未标 ordinal 的 separator lattice 只枚举 `直接 band 对 × 有限 ordinal distance`，并在循环前
  检查编译上界；超界直接产生 `producer_bound_exceeded`，不截断候选。
- 同一 template、integer offset 与 local topology 下，若两个 fit 只分别携带互补的 START/END
  observation，所有 phase、pitch 与 role interval 都相交，且同一 role 没有绑定不同物理 support，
  它们是一个连续 placement 的联合证据，不是 runner。合并只取联合可行区间与 observation 并集；
  ordinal、support identity 或 local relation 不同仍是离散竞争。
- 离散 placement 与 local topology 必须先在没有 source W evidence 的候选空间中唯一闭合。普通 local
  refinement 必须使用 format 编译的完整物理 W interval，不能用正在受检验的 fitted Grid W 过滤自己的
  反证；source-wide 与跨高度联合 edge 优先尝试唯一闭合，不能唯一时仍保留全部注册观察参与冲突判断。
  随后对 selected candidate 评估直接角色权限、pre-W lattice rank 与逐 adjacency coverage；pre-W joint
  rank 至少为 2、所有必要 coverage 完整且没有直接反证时，至少两张具有独立直接双边的完整 Frame 才可
  建立一份 `SourceFrameWidthAuthority`。该 source-level 尺寸事实不要求首尾 Frame 已经取得直接角色，
  因为它本身不创建输出；两端 Frame authority 仍在最终 Grid inference/Gate 阶段检查。W 收紧 selected
  fit 的连续 W，并在最终阶段重新评估 rank 3、opposite inference 与 Gate。W 不得重编译 template、重新
  搜索 phase、删除 runner、改变 ordinal 或把自己写回离散候选选择证据。所有物理相容的完整 Frame 都以
  完整 uncertainty 进入一个保守 hull；非相邻 Frame 同样有效，不挑 dominant subset、不取中位 winner，
  也不覆盖任何已经取得坐标权限的直接边界。若每个仍缺角色的 Frame 都至少有一侧直接边缘，同一份相关
  W 可以推导多条 opposite；这些推导不是多份独立证据。一个仅由两高度局部 support 形成、没有直接坐标
  权限的 `LOCAL_REFINEMENT` 不是应当保留的 native coordinate：当同 Frame 的 opposite 已独立授权、W
  完全来自至少两张其它双边授权 Frame、W 走廊中只有该 observation 与角色相容时，该局部绑定让位于
  `opposite + correlated W`。局部 observation 只保留为 validation provenance，不能收窄 W 或增加 rank。
  若某张 Frame 原本双侧都未绑定，但完整 format W 走廊内已有多组 registered native edge，而独立 source W
  能唯一留下其中一组，则允许在固定 placement 上追加一次有界 local lookup 并绑定该原生 pair。它不读取
  新像素、不生成坐标、不改变 phase/pitch/ordinal，也不能在多解时强选。若双侧未绑定 Frame 只有一侧存在
  唯一 intrinsic-authorized native edge，且另一侧完整 registered corridor 没有任何候选，同一份独立
  source W 也可以先保留该 native coordinate，再以完整相关 W 推导 opposite；另一侧存在任何观察、同侧
  intrinsic 多解或 source W 不可用时均不得使用。该合同同样适用于 calibrated Grid 生成的 selected fit，
  但 format/Grid W 自身没有这项权限。最终直接角色权限、outer authority、adjacency coverage、
  counterevidence 与 5% 预算仍须重新完整评估。

| source W 与缺失角色状态 | 结果 |
|---|---|
| 离散 placement 仍有 runner、pre-W rank < 2、必要 adjacency coverage 不完整或存在直接反证 | `SourceFrameWidthAuthority` 保存对应 typed failure；source geometry 与候选均不改变 |
| 唯一 placement、pre-W rank = 2、必要 coverage 完整、无反证，且至少两张独立完整 Frame | 建立 selected-only source W；它可以补最后一个 rank，但不能参与先前的离散候选选择 |
| pre-W rank = 3 且其它条件完整 | source W 只收紧 selected continuous W 并提供相关推断，不增加新的离散选择权限 |
| 没有缺失角色 | 不需要 W 推断，全部直接 native coordinate 保持不变 |
| 至少两张完整直接 Frame 闭合共同 W，且每个缺失 Frame 仍有一侧直接边缘 | `supported`；同一相关 W 补齐全部 opposite |
| 至少两张其它完整直接 Frame 闭合共同 W；某个双侧未绑定 Frame 在该 W 内只有一组 registered、intrinsic-authorized native edge pair | 固定 placement 上绑定该 pair；随后重新计算直接权限、outer、coverage 与 Gate |
| 至少两张其它完整直接 Frame 闭合共同 W；某个双侧未绑定 Frame 只有一侧唯一 intrinsic edge，另一侧 registered corridor 为空 | 保留该 native edge，以同一相关 W 推导 opposite；calibrated Grid 不能把自己的 W 冒充这份 authority |
| 双侧未绑定 Frame 没有上述唯一 pair 或唯一单侧 edge，或仍有多组合法解释 | 保持 `complete_frame_unobserved`；source W 不创造坐标也不强选 |
| 无权 `LOCAL_REFINEMENT`，opposite 已授权，W 来自至少两张其它双边授权 Frame，且 W 走廊中只有该线相容 | 该角色成为 `validation_only`；完整相关 W 推导坐标，记录 role index 与 validation observation ID |
| 弱线参与 W、opposite 未授权、W 走廊多解，或该线承担 `PHASE_ANCHOR` | 不让位；原 `direct_role_binding_authority_unavailable` 保持 |
| 任一 Frame 的 START/END 都未观察，且上述 source-W native-pair rebind 未唯一成立 | `complete_frame_unobserved` → `frame_width_inference_unavailable` |
| 缺失 opposite，但不足两张完整直接 Frame 建立共同 W | `common_width_authority_unavailable` → `frame_width_inference_unavailable` |

Source H 的直接 authority 仍只来自 selected、唯一且直接的 aperture top/bottom pair；enclosing support
或单侧 fixed-H 推断不能冒充 direct H。Source W 只能经第 2.1 节校准比例区间产生一份相关 H 推断；它
不增加独立 rank，且 direct H 始终优先。

被模板选中的 edge 仍须取得 `DirectRoleBindingAuthority`，才能让自己的 native coordinate 进入最终
placement；“观察到了”本身不等于“有权决定裁切”。权限只来自以下独立物理闭环：

| edge 空间支持与关系 | 角色坐标权限 |
|---|---|
| 同一 edge 直接覆盖三个独立高度区域 | `source_wide_edge`，允许 |
| 一条局部 direct edge 唯一绑定三区域局部弱信号 aggregate | `aggregate_union`，允许；两者仍是一份相关证据；宽缓 material aggregate 单边不取得该权限 |
| 同一三区域联合 separator 的 material 与两侧 END/START edge 都覆盖三个独立高度区域 | `separator_pair`，两侧均允许；缺一项则只保留诊断事实 |
| 同一 source-wide separator 的两侧 edge 原子绑定到一个 adjacency | `separator_pair`，两侧均允许 |
| normal separator 在两个独立高度区域成立，且两侧原子绑定到同一 adjacency，其中一侧已由上述任一完整闭环授权 | 只向另一侧传递一次 `partial_height_separator_pair`；该 placement 还必须具有唯一、两侧直接的 `aperture_pair` 短轴域 |
| 两高度 separator 的两侧都只有局部 edge | 不能互相授权；`direct_role_binding_authority_unavailable` |
| 两条局部 edge 的间距只与 catalog 或 source W 相容 | 只能证明尺寸未冲突，不能让两条无 intrinsic/pair 权限的线互相授予 native coordinate |
| source W 在固定 placement 中唯一选择一组各自具有 intrinsic 权限的 registered pair | source W 只消除本地多解；两条 native coordinate 的权限仍来自各自 source-wide/aggregate basis |
| 双侧未绑定 Frame 只有一侧唯一 intrinsic edge，另一侧完整 corridor 无候选，且 source W 已独立闭合 | 该 edge 保留自己的 native coordinate；opposite 只来自相关 W，不冒充 direct observation |
| 无权局部 refinement 满足上方独立 W 让位合同 | 弱线不取得 native coordinate；由已授权 opposite 与完整相关 W 推导该角色 |
| 只覆盖局部高度，且没有上述任一直接闭环 | `direct_role_binding_authority_unavailable` |

短 edge 仍保留为 observation；失败只撤销它的坐标决定权，不删除像素事实。全局 rank 计算必须排除无权
角色，不能先让短线闭合 lattice，再由该 lattice、catalog W 或同一 Frame 的另一条短线反向证明短线。
两高度 separator 的权限传递只执行一遍，`partial_height_separator_pair` 不能继续为相邻关系播种，也不能
把同一关系计成另一份独立 rank。它只允许 phase/lattice 保留该 native coordinate；最终 selection 若使用
`enclosing_support_pair` 或由单侧推断的 aperture，则产生
`direct_role_aperture_domain_unavailable`。这样不能把不完整的长轴空间支持与近似短轴支撑叠加成自动批准。
独立闭合的 source W 只覆盖真正有权限的 native coordinate；上表的 validation-only 局部线不是 competing
placement，也不能反向收窄 W。若同角色 separator-material alternative 与 opposite role 形成的全部可能 W
都和这份独立 source W 不相交，它不再是合法 runner；正在拟合的 Grid W、catalog 中心或未授权局部线都
不能做同样过滤。其它局部观察与相关 W 不唯一相容时保持 unresolved。每个 bounded phase
candidate 与最终 selected fit 的直接坐标权限都由 `template_direct_role_authority.py` 唯一拥有；让位与
source W 校准/相关推断由 `template_frame_width.py` 拥有，固定 placement 上的本地 rebind 由
`template_phase.py` 调度、`template_phase_candidates.py` 执行，
短轴联合条件由 `template_selection.py` 检查；三者都不读取新像素，也不按强度选择 winner。

在完全由 direct evidence 闭合的路径中，未观察 separator 的正常 adjacency 只有同时满足以下条件时，
才可使用 `local_delta = 0` 并由已确定 Grid 补齐 START/END：

1. 全部已选直接角色的 `DirectRoleBindingAuthority` 为 `supported`；
2. `GlobalLatticeAuthority` 已用独立直接证据达到 rank 3；Grid 没有参与创造 phase 或 ordinal mapping；
3. 该 adjacency 的 END/START 完整传播区间形成 `required_interval`，每条预登记 sequence trace 上都由
   已完整执行的 `SEQUENCE_ANCHOR_WINDOW` ownership interval 覆盖全部整数像素中心；
4. 同一 adjacency 没有直接 wide/narrow gap、contact、overlap、角色冲突或其它 typed 反证；
5. 一旦使用正常 Grid 推断，首张与末张输出 Frame 各至少有一条直接绑定的长轴角色。内部 adjacency
   coverage 不能证明 source 外侧的一整张 Frame 存在，Grid 不得从片夹或 holder fill 凭空创造它。

| 直接角色权限 | 全局 rank | adjacency coverage | 外侧 Frame 直接角色 | 直接局部反证 | 结果 |
|---|---:|---|---|---|---|
| supported | 3 | complete | 首尾各至少一条 | 无 | 允许既定 Grid 使用 `local_delta = 0` |
| unavailable | 任意 | 任意 | 任意 | 任意 | `direct_role_binding_authority_unavailable` |
| supported | 0–2 | complete | 任意 | 无 | `global_lattice_authority_unavailable` |
| supported | 3 | incomplete | 任意 | 无 | `adjacency_observation_coverage_incomplete` |
| supported | 3 | complete | 首或尾整张无绑定 | 无 | `outer_frame_observation_authority_unavailable` |
| supported | 3 | complete | 任意 | 有 | 直接 wide/narrow、唯一 Contact/Overlap relation 优先；冲突保持 unresolved |

`AdjacencyObservationCoverage` 逐关系保存 `relation_ordinal`、`required_interval`、参与覆盖的 query ID、
逐 trace 的离散 ownership 并集与 coordinate count，以及 `complete | incomplete`。相邻 interval 只要
覆盖相邻整数像素中心即为无缺口；任何一个可测像素中心无人拥有仍为 incomplete。全长 normalization
baseline 不产生 transition，因此不能单独充当 separator coverage；它只让全部预登记窗口复用同一批像素。
覆盖只映射既有 candidate-independent 查询，不增加 TIFF 读取；测量全局完成但某个合法走廊未覆盖时产生
`adjacency_observation_coverage_incomplete`，全局矩阵不足时产生
`global_lattice_authority_unavailable`。`OuterFrameObservationAuthority` 分别保存首尾 Frame 已绑定的直接
observation；只有两侧都非空才支持带推断的正常 Grid，否则产生
`outer_frame_observation_authority_unavailable`。这些证明都保留完整传播不确定性，并先于输出预算进入
review。

`SequenceAnchorDiscoveryDomain` 是候选无关查询走廊的唯一 owner。存在 coarse direct long support 时，
它从 format/count 编译的完整 `W/pitch` 区间分别按左端锚定向右、右端锚定向左投影每个 START/END，
再加唯一的 role refinement radius、裁到 coarse support 并合并重叠 core。合并后的理论 core 是窗口种子；
相邻种子之间在中点分界，把 coarse support 内每个可测整数像素中心恰好分配给一个窗口。Measurement halo
可以重叠，transition ownership 不得重叠或留洞。右端公式直接保留同一 `W/pitch` 状态的相关性，不能先
制造 origin 区间再重复叠加 pitch 极值。没有 direct long support 时使用一个保守全 support 窗口。全部
窗口在 placement 前登记，并从同一条全长 baseline trace 切片；该分区不新增 TIFF 读取或 query，不读取
winner，也不授予 phase、ordinal 或 placement 权限。

模板放置后，`template_alignment_diagnostic` 只读比较 theoretical role 与 bound observation，并报告
直接角色权限、全局 constraint rank、逐 adjacency coverage、外侧 Frame observation authority、
`normal`、`measured_advances` 或 `unresolved`；它不搜索、不选择、不改变 placement。

当前每个 adjacency 由唯一 `AdjacencyRelation` sum type 表达；production 已启用
`SeparatorRelation`、`ContactRelation` 与 `OverlapRelation`：

- 直接、ordinal 唯一的 END → material → START 可产生 wide/narrow advance；
- 该差值从下一格开始累加一次，后续仍共享同一个 source pitch；
- 多处实测变化可以同时存在，但关系总数固定为 `count - 1`，整次传播为 O(count)；
- `ContactRelation` 只能由同一条具有独立坐标权限的 physical edge 唯一绑定前一 Frame 的 END 与后一
  Frame 的 START；它保存共享 edge identity，并以 `delta = W - pitch` 进入同一次 prefix 传播；
- `OverlapRelation` 只能由两条独立、角色相反且顺序反转的 authoritative edge 唯一绑定；它保存严格为负
  的 signed-gap interval，并以 `delta = W - pitch + signed_gap` 进入同一次 prefix 传播；
- 任一 adjacency 的 band、角色、physical edge 或 ordinal 存在多个解释时，整条 placement 保持
  `adjacency_relation_unresolved`；不能由相邻宽度、bleed 或模板先验猜测；
- 未登记的反序边、跨零 gap、coverage 不完整或 separator material 竞争不能取得 Overlap 权限。

黄金物理诊断表明 source pitch 通常稳定，而实际 separator 宽度可在同一 source 内变化；因此 pitch 是
共同 lattice authority，separator 宽度只拥有其已直接证明的局部 advance，不能反向改写全局 W 或 pitch。

Contact 与 overlap 始终属于 challenge。Challenge 是运行前的评测角色，不是终态：标准 detector 与
Gate 能唯一证明安全时可以 `approved_auto`，证据不足时 `needs_review` 同样合格。Contact 与 Overlap
都只在同一模型中由完整证据闭合，不以普通 Grid、基础 bleed 或强制批准替代证明。

### 7.1 Adjacency continuity、Contact 与 Overlap

`photo_geometry/template_adjacency_topology.py` 是逐 adjacency material fact 的唯一 owner。像素 query、
trace 与 coordinate coverage 在 placement 前候选无关地登记和执行；`AdjacencyContinuityObservation`
只在 selected candidate 上把这些既有事实按 ordinal 映射一次，因此它是 candidate-bound ledger，而不是
新的 detector、winner-specific requery 或第二次 TIFF 读取。每个 adjacency 恰有一个 observation：

| 已登记事实 | Continuity 结果与权限 |
|---|---|
| 唯一 END → separator material → START，方向正确且正 gap | `separator_material`；可以授权一份实测 local advance |
| 同一 authoritative physical edge 唯一绑定 END 与下一张 START，走廊完整且没有 separator 竞争 | `contact`；授权一份 `ContactRelation`，signed gap 精确为 0 |
| 两条已登记、独立且角色相反的 authoritative edge 满足 `START(next) < END(current)`，走廊完整且没有 separator 竞争 | `overlap`；授权一份 `OverlapRelation` 和严格为负的 signed-gap interval |
| 合法走廊完整覆盖，且没有直接反证 | `no_counterevidence_observed`；允许既有 Grid 保持 `local_delta=0`，但不冒充直接 separator |
| 已登记 material 在不同高度区域不能一致闭合 | `separator_material_unresolved`；本 owner 不否定已经有权限的有序直接边，但不能授予 material/local-advance 权限 |
| 多个或互相冲突的 band、band 角色冲突，或 signed-gap interval 跨过 0 | `adjacency_continuity_unresolved`；Gate 阻断普通 adjacency |
| 两条反序直接角色没有对应的 candidate-independent overlap observation | `overlap_observation_unavailable`；不能由 selected geometry 临时创造 topology |
| 合法走廊未被完整登记和执行 | `coverage_incomplete`；继续由逐 adjacency coverage 合同阻断推断 |

材料不可用与材料反证不可混淆：前者只表示这份 material observation 没有 authority；后者表示当前普通
separator 解释与直接坐标冲突。`template_residual.py` 只接受 `separator_material` 产生 local advance；
`no_counterevidence_observed` 只维持正常 Grid，不能调整 native boundary。Ledger、依据、覆盖 query、直接
角色、signed-gap interval 与 typed failure 全部进入 report/Debug；当前 report 不保留旧 schema 兼容路径。

`photo_geometry/template_contact.py` 是 candidate-independent 共享边观察的唯一 owner。它只读取已经登记的
long-axis edge ledger，不读取像素：edge 必须具有 source-wide 或 aggregate-union 坐标权限、允许
START/END 角色，且不属于任何正 separator band。同一位置若还有另一条独立 authoritative edge identity，
即使该 edge 已被 separator material 拥有，也会取消共享边的唯一性；多种 adjacency 映射同时合法时产生
`adjacency_topology_ambiguous`。被选中的 Contact 仍须通过逐 adjacency coverage、direct-role、source
containment 与完整输出预算；完整测量 receipt 不能代替该 adjacency 的走廊覆盖。

`photo_geometry/template_overlap.py` 是 candidate-independent 反序边对的唯一 owner。它同样不读取像素：
只在既有 edge ledger 中连接空间相邻、角色相反、各自具有 source-wide 或 aggregate-union 坐标权限、
不属于正 separator material 且 physical identity 互不重叠的 END/START。提议不携带 ordinal；phase solver
只把同一对 edge 投影到有限合法 adjacency，selected continuity 再核对完整走廊、原 signed-gap interval 与
material 冲突。两条边来自同一 identity 时属于 Contact；内容连续或 selected geometry 自身不能创造
Overlap observation。

宽缓/低梯度 material 已在同一 registered baseline owner 内以多尺度 tone、uniformity、texture 与跨高度
一致性形成 typed observation。Contact/Overlap 只复用这些既有事实，不用 tone、texture 或 content
continuity 单独证明 topology，也不建立 enhanced-image 平行 detector。

异常 topology 继续使用第 7 节唯一 placement 模型，不建立“发布版式 detector”或第二套 Grid。当前
sum type 为：

```text
AdjacencyRelation
├── SeparatorRelation(normal | wide | narrow)
├── ContactRelation
└── OverlapRelation
```

三种关系都保存一个有界 `delta_interval`，并继续由同一次 O(count) `local_prefix` 传播：

```text
signed_gap = next.START - current.END
delta = signed_gap - nominal_gap
```

正的 `signed_gap` 属于 separator，零表示 contact，负值表示 overlap。`SeparatorRelation` 保存正 gap 与
material identity；`ContactRelation` 保存 END/START 共用的唯一 physical edge identity；
`OverlapRelation` 保存两条独立、角色相反且顺序反转的 edge 与 overlap interval。同一 contact 共用线
只能计作一份 rank support。

Contact 必须由同一 physical edge 唯一绑定 END 与下一张 START；Overlap 必须由两条独立角色 edge
及 `START(next) < END(current)` 的有界 interval 证明。内容连续只能否定普通 separator，不能单独证明
contact 或 overlap；存在多组合法解释时保持 `adjacency_topology_ambiguous`。只有唯一
`OverlapRelation` 与 realized overlap interval 相容时该处 Frame domain 重叠才合法；其它 adjacency 的
意外重叠仍产生 `fixed_template_mismatch`。物理 output polygon 保留重叠；仅 short-axis evidence 的支持域
在 overlap 中点分区，防止同一 trace 被当成两份独立 Frame 支撑。

现有 source W authority 已允许每个至少拥有一条直接 START/END 的 Frame 用同一相关 W 推导另一侧；
多张 Frame 的推导共享一份相关状态，不能当成多条独立证据。Contact/Overlap 两侧 Frame 不参加 source W
的独立完整 Frame 支撑，避免 topology edge 反向自证 W。W 不得凭空生成两侧都未观察到的 Frame、决定
topology、覆盖 direct native coordinate，或把 contact 共用线重复计票。无权 `LOCAL_REFINEMENT` 仍按第 6 节的
validation-only 合同让位。

剩余能力继续按独立小机制形成检查点：完全未观察 Frame 的校准 Grid 风险权限和带拒绝选项的概率选择
仍只保留设计边界，须等独立 calibration 与 sealed representative 数据具备后再进入 runtime。每项都必须
完整交付 type、owner、Gate、Debug、正反例、真实样片、性能和黄金安全验收；尚未闭合的能力不授予自动
批准权限，也不建立占位 runtime。

### 7.2 Calibrated nominal Grid authority

`CalibratedNominalGridAuthority` 是 direct rank-3 之外已经启用的显式闭合路径。默认 Grid 始终是同一个
primary generative model；这项 authority 只决定它何时足以进入自动批准，不建立第二套 placement：

```text
format-specific calibrated W/H/pitch intervals
+ 至少一个获得坐标权限的 direct absolute phase anchor
+ 每个使用 local_delta=0 的 adjacency 完整覆盖其合法不确定性走廊
+ 没有 wide/narrow/contact/overlap/conflict 等直接反证
+ 当前 hard-fact 层中，每张 Frame 至少有一侧直接角色
+ selected OutputFootprint 完整通过既有 source containment 与 5% 预算
→ calibrated nominal Grid 可以获得 selected-output authority
```

Format/count 提供一把有界尺子，但不能知道它应放在 TIFF 的哪个像素；absolute phase 始终来自直接
START/END 或其它获得权限的 anchor。Pitch、W 与 source scale 保留为同一相关状态，pitch uncertainty 按
离 anchor 的 slot 距离传播，不能按每格独立选择有利值。直接 START/END 保留 native coordinate 并收紧
默认模型；直接 separator 的实际宽度继续只产生一次 local advance，不能被 nominal gap 拉回。

逐 adjacency coverage 必须覆盖当前 placement 的完整合法走廊；“所有 query 都执行完成”或“没有检测到
edge”不是 normal adjacency 的充分证明。直接角色反证优先于 Grid，coverage incomplete 次之。Grid 可以
生成 START/END 都未绑定的完整 Frame 供 candidate diagnostic 使用，但 S040、S056 证明多个相邻局部偏差
可能在全局 anchor 间互相抵消；在未来校准概率层或更强 topology/continuity 证据闭合前，该候选以
`complete_frame_unobserved` evidence 和 `nominal_grid_complete_frame_unobserved` Gate failure 进入 review，
不能由 Grid 自己授权。这是当前自动批准合同，不删除候选，也不把“无法硬证明”误写成像素事实不存在。

Nominal pitch 使用冻结 development gold 的 source-level calibration：只接受 nominal source 中一个
separator 两侧均为 `directly_visible` 的完整 adjacency，每个 source 至少两次测量，先取 source 中位值，
再取跨 source hull 并向外量化到 0.05 mm。当前注册值为：

| format | pitch interval | source / measurement |
|---|---:|---:|
| `135` | 37.65–38.20 mm | 44 / 198 |
| `half` | 18.70–19.05 mm | 11 / 98 |
| `120-66` | 60.05–62.55 mm | 26 / 52 |
| `120-67` | 73.40–74.45 mm | 3 / 6 |

`xpan`、`120-645` 和 `135-dual` 当前没有独立合格 pitch calibration，因此该 authority 为 unavailable；
不能从其它 format 外推或建立 format 特例。

`formats/__init__.py` 唯一拥有 calibration identity 与毫米区间；
`template_nominal_grid_authority.py` 唯一编译 prior、求解相关 envelope 并建立 evidence/selected authority；
`template_phase_candidates.py` 只让同一 candidate 使用该 envelope，`template_phase.py` 负责 selected-only
权限与 typed failure，`template_feasible_geometry.py` 把相关状态传播到输出包络。Report 与 Debug 显示
calibration identity、参数依据、anchor、推断 adjacency、逐关系 coverage、完整未观察 Frame、工作量与
failure。该路径保持 `O(count)`，不增加 TIFF query、样片特例、format denylist、fallback、第二 Grid 或
未经校准的 score。

## 8. Cross、outer 与固定 H

Cross 寻找能够确定短轴 offset、fixed H 和局部连续性的直接证据。片夹短轴尺度与画布只编译有界
top/bottom 测量 corridor；片夹短轴中心不参与最终 aperture/support 选择、边界位置、fixed-H 推导或
输出 deskew。

### 8.1 `APERTURE_PAIR`

Photo aperture 的候选必须有正确 top/bottom 角色、外侧背景、有限位置、局部共同方向和固定 H 闭环。
允许：

- 直接 top + bottom；
- source-wide 单侧 direct anchor + 固定 H 推导 opposite；
- 一个 role-authorized direct binding 在 selected frame domains（数量至少为 3）中逐一有
  direct trace 时，即使 aggregate independent support 只有 2 个区域，也可以作为固定 H 的
  单侧 anchor；这只适用于同一个 binding 的 template-wide domain coverage，不降低普通局部
  two-region edge 的要求；
- 同侧多个相距较远且物理相连的 fragments。

Cross registration 是同角色边界 family identity 的唯一 owner。Transition tracking 可以先产生多个局部
fragment；registration 先把投影坐标与完整方向区间相容的同角色 observation 组成有界 component，再对
该 component 的完整 transition 并集只重拟合一次：

| registration 事实 | 结果 |
|---|---|
| 一次 robust refit 精确保留完整 transition union | 合并为一个 canonical observation，`state=supported` |
| refit 丢弃任一 transition 或无法成线 | 全部原 observation 原样保留，`complete_transition_union_refit_rejected` |
| 只有一个 observation | 不建立多余 family record |

Raster trace 不连续不等于物理边界不同；完整并集重拟合能够成立时，跨 domain fragment 仍可属于同一条线。
反过来，坐标邻近、方向相似、support 更多或 residual 更小都不能选择性合并其中一部分。Selection 不再
拥有 broader/local containment 或 dominance 逻辑，只消费 registration 的 canonical identity。每个最多
256 个 registered run 的集合只做有界 compatibility 与每个多成员 component 一次重拟合，不新增 TIFF
读取或 selected-placement query。Family state、成员/transition/final identity 与 typed failure 写入
development report 和 Debug。

直接 top/bottom pair 有两种互斥的 typed support mode：

| 直接观察 | `pair_support_mode` | pair authority |
|---|---|---|
| 两侧共享足够的 direct trace | `shared_traces` | 按共享 trace 的独立区域与 selected-domain 合同判断 |
| 共享 trace 不足，但两侧都为 role-authorized `direct`、各有至少 2 个独立区域、两侧 trace 并集覆盖每个 selected domain，并且 fixed H 与方向相容 | `complementary_domains` | 并集拥有 template-wide pair support；共享 trace 仍如实记录为 0 |
| domain 并集不完整、任一侧只是 template-local/inferred、支持不足或方向冲突 | 无 | typed failure，保持 review |
| 存在多个非等价完整 pair | 各自保留 | `non_equivalent_fits`，保持 winner/runner 与 review |
| 一个完整 pair 的某侧，与同一个 opposite 还能形成严格更外侧、但未取得全局 pair authority 的直接局部闭环 | 不授予该完整 pair 最终权限 | `outward_role_counterevidence`，保持 review |

`shared_traces` 仍须共享 direct trace 覆盖至少 3 个 selected frame domain，或其中一侧覆盖全部 selected
domain 且共享 trace 仍覆盖至少 2 个 domain。`complementary_domains` 不能借一条 template-wide side 把只在
一个局部 domain 出现的 opposite 外推成全局闭环；每侧的独立区域和完整 union 都必须由已登记 direct
trace 证明。若更外侧 pair 也拥有完整全局 authority，则两者都是离散 placement，继续以
`non_equivalent_fits` review；不能借“更外侧更安全”消除合法 runner。严格外侧反证只比较不相交的 full
interval，并按共享 opposite identity 建立，不使用距离、support 或 residual score。两种 mode 使用同一
fixed-H placement、相同 4096 pair 上界和同一 Gate，不建立第二套 detector；反证索引只作 O(pair count)
的有界归约。

一条短局部线不能外推整条片带。两个不同合法 side tracks 是两个 placements；不按梯度、support
数量或 residual 的未经校准标量硬选。已有 direct top+bottom 闭环时，不再执行“缺失 opposite”的局部精修；
同一批 raw transitions 的重复拟合不能成为第二个 placement。

Direct top+bottom 的局部方向只验证两侧能否属于同一 fixed-H aperture，并计算逐 trace outward
departure；它不会产生 placement angle。任何 binding 的短轴 offset 投影都必须落在该 binding 的
直接 trace span 内，未覆盖的 frame 不沿 fit direction 外推。`ENCLOSING_SUPPORT_PAIR` 可以保留
自己直接观测的 same-state slope，但这仍不是 placement 或 deskew authority。

Domain-complete 单侧 anchor 仍必须有完整方向、明确 role authority，并由同一个 direct binding
在每个 selected frame domain 中分别命中 direct trace；selected domain 少于 3 个、缺少一个
domain、把两个不连通 fragments 合计覆盖、role 未授权或方向不完整时，不能拼接或推导 placement，
继续 review。Holder short-axis center 只在 measurement compiler 中生成有界 corridor；观察登记完成后，
它不再是 compatibility、selection 或边界 authority。Opposite 只由 fixed H 推导，局部 departure 继续
进入 selected placement 的 output budget。

Source-spanning 单侧 direct anchor 与局部 opposite 即使偶然 fixed-H 相容，也不能把局部坐标或方向外推到
整条 template。只有 opposite 自己覆盖全部 selected domain 时才保留两侧 native height；否则由该
source-spanning side 与有界 H 推导 opposite。多个局部 closure 不能替代这条权限，也不能扩大整条片带的
共同方向。

### 8.2 `ENCLOSING_SUPPORT_PAIR`

当 aperture 未唯一成立时，可以使用一对直接外侧支撑作为完整输出 top/bottom，但必须同时满足：

- 两侧共享直接 trace 和相容的局部方向；
- 两侧均 source-spanning，或覆盖 3 个独立支持区域和 `min(3, count)` 个长轴 frame domain；
- 直接 span 完整包含 canonical fixed H；
- `H < support_span <= 1.1H`；
- 完整位于 lane/source authority；
- 只有一个合法 pair。

两侧 `boundary_use` 必须一致，禁止 aperture/support 混用。两侧直接闭环且唯一的 aperture 优先；
若 aperture 只有单侧 direct anchor、另一侧依赖固定 H 推导，或者仍有多个离散 aperture 解，则
唯一且直接证明的 enclosing pair 可以成为更强的输出 authority。Enclosing pair 不声称自己是
照片 aperture，只证明它完整包住可接受的照片区域。

Enclosing pair 以 source 已闭合的 `fixed_height_px` 与 canonical H 检查包含关系；它的两条直接支撑
本身拥有输出权限，不读取、消费或阻断于 `ApertureAspectRatioAuthority`。比例 authority 只在 aperture
缺少一侧、需要由 W 推导 H 时生效，不能重复接管已经预闭合的 enclosing support。

这里的 `support_span` 只由这对直接 observation 的 `observed_span.maximum` 拥有。输出 footprint
是同一 placement 多个联合可行状态的并集，不能把不同状态的 top 与 bottom 组合成新的高度，因而
不能用其包围盒反向计算 enclosing budget。

## 9. Compose、竞争、闭环与 holder fill

`compose_format_placement` 一次把 `TemplateSpec + SequenceFit + CrossFit` 编译为全部 source-axis
固定 frame。之后检查：

- W/H、pitch、cross offset 与 format/source authority 相容；
- ordinal 单调、frame 不交叉；
- first/last、separator、top/bottom 和总跨度闭环；
- 双 lane 的共享尺度与 slot identity 相容。

直接绑定的 sequence start/end 把自己的 native coordinate、full interval 与稳定直线拟合交给最终
placement；Grid coordinate 只保留为模型诊断。Placement 仍保持 source-axis，不沿拟合直线旋转 frame；
安全层只计算该直线在当前 frame 短轴 support 上超过 full interval 的向外部分，已覆盖的 residual 不重复
相加。只有一侧直接可见时，固定 W 推导 opposite，并平移同一条直线证据；两侧都直接可见时各自保留
独立 observation，不把远处 model residual 复制到本 Frame。

### 9.1 当前选择合同

当前 production 只使用 typed hard facts 和证据职责，不使用加权总分、confidence 补偿、top-K、
投票或样片/format 特判。同一 template identity、integer offset、local topology 与独立物理 support
下，相交的 role interval 与互补 observation bindings 可以联合成一个连续 placement；同一 role 的不同
物理 support、不同坐标、ordinal、local topology、boundary use 或 required source footprint 是离散竞争。
硬物理事实不能唯一闭合时进入 review。

这是一项当前实现边界，不是对校准概率选择的永久禁令。未经校准的 score 不得拥有最终决定权；
合法 runner 也不因“仍然合法”而被定义为永久阻断项。

### 9.2 校准概率选择层的准入合同（当前未启用）

检测能力与数据条件成熟后，可以在硬物理合同之后加入带拒绝选项的概率选择：

```text
registered evidence
→ 固定模板生成有界候选
→ 硬物理合法性、source containment、输出预算与 content veto
→ 对剩余合法候选估计校准后的可接受概率
→ winner / runner + 绝对概率 + margin + evidence coverage + OOD
→ selected placement，或 abstain / needs_review
```

概率层不能创建、移动或修补 geometry，不能重新读取像素，不能让被硬合同淘汰的候选复活，也不能
使用 sample ID、文件名、nominal/challenge 角色或黄金答案作为 runtime feature。这里的训练标签是
“该候选最终 footprint 是否满足统一的方向性黄金安全合同”；多个候选可以同时可接受，因此候选概率
不要求总和为 1。危险裁切的代价远高于 review，自动批准必须同时满足预先冻结的高绝对概率阈值、
winner/runner margin、证据覆盖和 OOD 组成的冻结联合准入规则；绝对概率与 margin 不能再被
任意加权成一个 confidence。合法 runner 本身不是硬阻断，但必须进入联合规则和 report；未被校准数据
覆盖的低 margin 区域必须 abstain，而不是普通 `argmax`。

准入前必须冻结以下 versioned schema 与 artifact：

| 合同 | 必需内容 |
|---|---|
| score schema | `feature_schema_id`、`model_id`、`calibration_id`、`decision_rule_id`、candidate/placement identity、带单位与 missingness 的 typed features、evidence provenance、校准概率 |
| selection assessment | winner/runner identity 与概率、margin、absolute-threshold、coverage、OOD、abstention 和 hard-legality receipt；runner 始终保留在 report |
| calibration manifest | source-SHA 分区、同 SHA count 绑定、候选生成 commit、label contract、拟合方法、样本量、阈值、可靠性曲线、自动区危险率的单侧上界与适用 format/profile/topology |
| work receipt | 合法候选数、feature 数、feature evaluation、OOD evaluation、临时内存和编译上界 |

现有 106 个已查看 source 可用于 feature/model development、训练与反例发现，不能事后伪装成独立
calibration 或 sealed 证据。启用前必须补充在查看 scorer 输出前按 source SHA 冻结的新
calibration source；同 SHA 的全部 count 变体同分区。Calibration 只拟合概率、联合准入规则与风险上界，
sealed acceptance 不参与拟合、调参或 feature 选择。Sealed 在不暴露逐样片结果的情况下只检查
全部角色 `unsafe_approved_auto = 0`、sealed nominal 全部安全自动通过、校准可靠性和 OOD/abstention
合同。Model、feature、decision rule 或物理候选生成任一变化都会使旧 calibration 与 sealed receipt 失效。

OOD 至少覆盖未校准的 format/holder profile/count/topology、必要 feature 缺失、measurement saturation、
超出校准支持范围的连续 feature 与未知候选结构；任一命中直接 abstain。具体阈值只有在预先声明风险
预算、校准样本量与可靠性检验后才能冻结，不能从 development 或 sealed 的单张结果反调。

失败以 typed facts 表达：`probability_selector_unavailable`、`probability_contract_mismatch`、
`probability_out_of_distribution`、`probability_evidence_coverage_insufficient`、
`probability_below_auto_threshold` 或 `probability_margin_insufficient`。它们由 `CandidateGate` 汇总，
`DecisionGate` 仍独占最终状态；不得退化成“低 confidence”这一条不可解释文案。

评分工作量必须是 `O(K × F)`：`K` 为编译时有界的合法 placement 数，`F` 为冻结 feature 数。不得为
评分层新增 pixel query、候选笛卡尔积、beam/DP、winner-specific requery 或第二 detector；正式
24-source mean 仍须 `<= 5s`，`<= 3s` 继续作为优化目标。当前没有 calibration pool、sealed cohort
与准入 receipt，因此本节不授予任何 runtime score 权限。

### 9.3 Holder fill

`PhotoGroupOuter` 只在 selection 后生成。`HolderFillAssessment` 逐侧计算 outer 与 lane authority
之间的空余，并仅用 W 判断：

```text
任一侧空余 >= W  → NOT_FILLED
两侧空余都 < W   → FILLED
区间跨过 W       → UNRESOLVED
```

不加邻接 gap，不重新搜索，不提供 phase。该事实只约束 `135-dual` 的两条完整 lane。

## 10. 联合输出保护、bleed 与预算

当前 runtime 的完整安全计算严格晚于唯一获准的 selected placement。若第 9.2 节未来获准启用，
每个有界合法候选必须先用同一 source containment、预算与已注册 content observation 形成只读 eligibility
receipt；这不产生正式 OutputFootprint，也不允许 candidate-dependent 像素读取。概率选择后仍只有 selected
placement 能进入下列完整联合几何与输出流：

```text
selected placement
→ PlacementFeasibleSet
→ JointPlacementEnvelope
→ mandatory / requested source footprints
→ explicit source-boundary saturation
→ OutputFootprint
→ authority + direct-use assessment
```

`PlacementFeasibleSet` 保留同一 observation bindings、ordinal topology、boundary use 和 placement
identity 下仍合法的 W、未观察 Grid role、local delta 与 cross 联合状态；直接 sequence role 从自己的
native interval 投影，不能被全局 Grid 拉回。直接 enclosing pair 额外保留自己的 same-state slope。
每个 frame 的边界极值从这个低维联合集合求出，再加入未被 full interval 覆盖的 line outward
departure；不把同一 residual 重复相加，不吸收 runner-up，也不重新读取像素。

产品 bleed：

```text
sequence：max(0.15 mm, 0.7% W)
cross：0.25 mm
```

`APERTURE_PAIR` 四边的完整 expansion（联合不确定性 + 直线 residual + bleed）各自不得超过对应
format 尺寸的 5%。四边不能借额度；刚好达到上限通过。

已证明的 Contact/Overlap 只在参与该关系的两侧增加显式 `topology_protection`：前一 Frame 的 END 朝后一格、
后一 Frame 的 START 朝前一格，其它边仍使用基础 bleed。当前 protection 等于一份同状态的 sequence
base bleed；它不是新的预算，也不能选择或证明 topology。每侧完整
可用保护上限仍为：

```text
max(0, 5% W - joint uncertainty - line residual - base sequence bleed)
```

因此 Contact/Overlap 可以产生彼此重叠的两个安全 OutputFootprint，但每侧完整 expansion 仍不得超过 5% W。
source containment、content veto 或剩余预算不能闭合时进入 review；不确定 topology 也不能先按普通
切分再靠扩大 bleed 自动批准。Debug 与 report 分别保存基础 bleed、topology protection、relation ID、
uncertainty 与 residual。

`ENCLOSING_SUPPORT_PAIR` 的 top/bottom 使用直接 support 边，不再添加 cross bleed。其预算由三个不重叠的
合同共同组成：直接 support span 不超过 `1.1H`；top/bottom 各自的完整 expansion 不超过 `5%H`；同一
可行状态中，为覆盖两条 support 直线局部 departure 与 pixel-center span 而额外加入的 alignment padding
之和不超过 `5%H`。Support 的位置不确定性已经进入逐侧完整 expansion，不能再次算入 alignment padding；
也不能把两个不同可行状态的 top/bottom 极值相加。Start/end 使用正常 sequence bleed 和各自 5% 预算。

| enclosing support 状态 | 结果 |
|---|---|
| span `<= 1.1H`，四边逐侧预算成立，同一状态 alignment padding `<= 5%H` | `supported` |
| 任一边完整 expansion 超过自己的 5% | `direct_use_budget_exceeded` |
| support span 超过 `1.1H` | `direct_use_budget_exceeded` |
| 每侧各自成立，但同一状态 alignment padding 合计超过 `5%H` | `direct_use_budget_exceeded` |
| 只有不同状态的 top/bottom 极值相加才超过 5% | 不据此阻断 |

`OutputFootprint` 同时保存三层 source-space polygon，以及
`maximum_same_state_cross_alignment_padding_px`：`mandatory_source_footprint` 含联合测量不确定性、
直线 residual 与完整 pixel-center span；`requested_source_footprint` 再加入完整产品 bleed；
`required_source_footprint` 是最终实际采样范围。完整 5% 预算始终按 requested 层评估，不能因源边界而
收窄或掩盖超预算。

真实 TIFF 外缘是可用源像素的绝对极限。Requested 越过该外缘时，required 明确等于其与 TIFF
pixel-center extent 的交集；typed saturation fact 区分只触及 optional bleed 的
`source_boundary_optional_bleed` 与联合保护也触及边界的 `source_boundary_joint_protection`。两者都保留
完整 requested/mandatory polygon、越界距离和 Debug 虚线，不伪造 TIFF 外内容，也不因不存在的源像素
要求 review。双 lane 的内部边界不是 source boundary：`lane_boundary_optional_bleed` 与
`lane_boundary_joint_protection` 都不得裁小后批准，继续由 Gate 阻断。交集退化、其它 authority 冲突或
预算失败仍进入 review；任何 saturation 都不得静默发生。

Content protection 查询的也是同一个最终 `OutputFootprint`，即联合不确定性、局部 residual、完整
pixel-center span 和 bleed 全部加入后的精确 convex polygon。真实画面位于 nominal frame 之外、但仍
在最终 bleed 内，不构成 veto；只有可靠内容越过最终 post-bleed crop 边界才否决。Content 不能回头
移动边界、选择 runner 或创造 phase。

Decision 后 finalization 才执行并评估 lightweight deskew。`needs_review` 不扫描，记录
`output_not_eligible`；approved observation 不可用时使用 identity 且不降级。`auto` 只在观测角绝对值
至少 `0.03°`、长轴端点位移至少 `clamp(0.0005 × long_extent, 3 px, 12 px)`，并且观测角不超过
`0.35°`、端点位移不超过 `120 px` 时应用。低于下限记录 `rotation_not_needed`；高于小整理上限记录
`rotation_exceeds_cleanup_limit`。跳过 deskew 不改变 `approved_auto`。有效旋转对横向 layout 使用观测
角的反号、纵向 layout 使用同号构造 expanded rotation。每个已经确认安全的 polygon 与 source 使用
同一 affine transform，正式轴对齐 box 由旋转后 polygon 的精确半开 AABB 得到，不能先把 polygon
扩成 source AABB，也不能继续裁固定 W×H。

旋转后 AABB 的角落可以位于安全 polygon 之外；这些表示性角落允许写黑色 no-data，不是检测缺口，
不得回流 `CandidateGate`。Sampling 仍必须保证 polygon 内的已确认区域完整、输出 extent 有界、
16-bit/ICC/resolution/metadata 保真。

## 11. Gate、report 与 Debug Analysis

`CandidateGate` 只汇总 typed facts：输入 authority、measurement completeness、producer bounds、
adjacency relation、获准的 selected placement、content、holder fill、source-space 联合 footprint 和 budget；
未来概率层若启用，还包括其 versioned selection assessment 与 abstention facts。Phase、
cross continuity/direction 与 ordinal 的真实失败作为 placement 的 typed root failure 传递，不在已有
complete/selected placement 后重复建立同义 Gate fact。它不读取 deskew observation，不选择 geometry，
也不创建最终文案。

`DecisionGate` 独占 `approved_auto`、`needs_review` 和 final reasons。常见根因包括：

- `no_legal_placement`
- `placement_unresolved`
- `separator_material_conflict`
- `content_protection_conflict`
- `adjacency_relation_unresolved`
- `producer_bound_exceeded`
- `aperture_aspect_ratio_authority_unavailable`
- `aperture_aspect_ratio_physical_prior_conflict`
- `aperture_aspect_ratio_direct_conflict`
- `aperture_aspect_ratio_budget_exhausted`
- `direct_use_budget_exceeded`
- `source_lane_authority_unavailable`

`approved_auto` 是产品风险决定，不是“运行时已经知道真实黄金边界”的数学证明。Runtime 只能根据校准
先验、registered evidence、硬物理合同、剩余不确定性与 OOD 判断风险是否低到可直接使用；真实内容边界
只在开发验收中可知。首版检测目标因此是当前 development nominal 全部安全 `approved_auto`，全部角色
持续保持 `unsafe_approved_auto = 0`；未来建立 sealed cohort 后适用相同安全标准。不能用无限外扩换取
一个不存在的绝对保证。未来出现一次真实危险自动裁切时，必须保存原 TIFF、format、count 与 source
SHA，由人工建立 reference 后永久进入 development incident regression，再用通用机制修复；不能只修
当前图片、建立样片规则或把它改成 challenge。Calibration、sealed 与新格式样片随真实使用持续补充，
不作为单次 incident 修复的前置条件。

普通 report 只保存输入、holder/count authority、最终选择、OutputFootprint、预算、根因、输出文件
和必要 TIFF 事实。Saturation 只记录越界 `authority_side`；每项预算只按 output `geometry_id` 关联，
不保留不可达的多 placement 或 named-gap 容器。Report 只保存最终 `deskew_assessment`：是否应用、
观测角、实际旋转或 typed skip reason，不重复保存旁路 observation。
Holder/count/output-slot identity 只在 `photo_geometry` 保存一次；finalization 复用每个
`OutputFootprint` 内的 sampling authority 和 `deskew_assessment` 内的唯一 source transform，不再建立
逐 slot 同义 tuple。`needs_review` 不暴露 approved sampling geometry 或 final boxes。每个阻止事实
同时给出最小缺失事实、恢复类别和建议操作。完整 observations、alignment residual、winner/runner、
direct/inferred ledger、content veto 和工作量只属于显式 Debug Analysis 或 verifier。外部 report
validator 位于 `tools/regression/`，不进入用户 standalone。

Debug Analysis 只读取同一次 runtime facts，不重算几何、不改变决定、不写正式 TIFF。它必须展示：

- theoretical template、role-free observations 与跨高度联合观察的 typed resolution；
- dark/light separator material、逐区域状态、直接角色权限与 material conflict；
- 每个直接角色的 coordinate `observation_id`、`evidence_group_id` 与 separator side provenance；
- 每个 bounded phase candidate 的输入权限、projection outcome、保留 rank、退出几何的 binding、重拟合结果与
  terminal failure；
- `partial_height_separator_pair` 角色数、direct aperture domain 条件与对应 typed Gate；
- selected-only source W authority 的 selected signature、支持 Frame、W interval、typed failure，及相关
  推导角色、validation-only 局部角色与 observation provenance；
- 每个 bound role 的 residual 和 normal/measured-advances/unresolved pattern；
- direct 与 inferred 边界；
- best、runner 及真正不同之处；
- `APERTURE_PAIR` 或 `ENCLOSING_SUPPORT_PAIR`；
- aspect calibration identity、`R_raw/R_guarded`、`gW/gH`、W 与推导 H interval、cross 消费状态、
  输出预算和 typed failure；
- selected-only OutputFootprint，以分帧颜色半透明填充最终 required polygon，不另画白色虚线框，
  并显示四边 bleed/联合 expansion/预算；
- `DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed `DESKEW SKIPPED`；
- 第一个 blocking Gate gap，或全部事实已支持。

## 12. 工作量、性能与 TIFF

每次 development receipt 保存实际计数和编译上界：

```text
registered queries / pixels
separator lattice hypotheses
phase hypotheses / lookups / bindings / fit passes
phase candidate authority evaluations / terminal outcomes / role checks
phase candidate projection evaluations / successes / dropped bindings
local adjacency evaluations
cross runs / fits
placement / boundary / content evaluations
probability candidates / features / OOD evaluations（仅在第 9.2 节获准启用后）
domain pixels / peak temporary bytes
```

任何上界不足都显式产生 `producer_bound_exceeded`，不得 silent first-N。像素工作上限为
`128 × source_pixels`，峰值临时内存上限为 `10 × source_pixels + 32 MiB`。不得恢复通用 DP、
beam、未校准的第二套 Grid/phase vote 搜索、候选笛卡尔积、完整链 materialization/cache、逐帧尺寸、
candidate-dependent query 或 content-driven placement；概率层也只能消费已经生成且硬合法的有界候选。

性能合同是 24-source 完整用户路径平均不超过 5 秒；同一均值不超过 3 秒是明确记录但不阻断
提交、发布或平台 receipt 的 challenge。正式计时子进程同时由外部观察未插桩 peak RSS；该值与
带 cProfile 的阶段归因 RSS 分开记录。`runtime_peak_temporary_bytes` 只描述 detector 自报的有界
临时测量缓冲，不代表进程 RSS。Profiler 将完整路径拆成：

```text
unattributed runtime → TIFF decode → workspace gray → coarse support
→ registered measurement → template alignment/decision → output deskew
→ sampling → TIFF encode/write → readback → publish
```

Detector 只消费 8-bit gray、稀疏 aggregate profile 与有界局部窗口；正式输出仍从已验证的原始
16-bit RGB 通过每-frame 反向 affine ROI 采样，不先旋转整张大图。普通 product path 在 deskew 和
workspace-owned report facts 冻结后、TIFF sampling 前释放 registered gray；development CLI 同样先
冻结完整 facts 再释放，只有 Debug Analysis 为画图保留。是否继续拆分 decode、优化 detector、
sampling 或 I/O 只由阶段证据决定。

Affine sampler 独占每格 contiguous 输出缓冲，writer 完成一格后才分配下一格，避免相邻大 crop 同时
存活；vertical deskew 使用灰度转置 view，registered interval 使用连续 slice view。Transition-line
cache 只在单个 source 内复用并在 source 结束时清空。这些优化不得改变 observation、placement、
winner/runner、provenance、footprint 或输出像素。

正式输入限于单页 unsigned 16-bit、RGB 三通道、contiguous TIFF；压缩接受 `NONE`、`LZW`、
`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD`。Orientation 1–8 在 decode boundary 规范化，输出写
`Orientation=1`。

`tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界测量，SciPy 只作数值拟合与 sampling，
Pillow 只在 Debug Analysis 时延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。

输出先写同父目录 staging，全部完成后一次 rename 到尚不存在的 target。程序不覆盖、接管、遍历或
删除旧 target。

## 13. 源码 owner

下表中的 `photo_geometry/` 指 `x5crop/detection/photo_geometry/`。

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | format 设计 W/H、统一混合 W/H compatibility、分格式 raw aspect calibration、gap 搜索中心、holder count 与输出保护常量 |
| `x5crop/configuration/`、`x5crop/runtime/` | format/count/deskew mode 输入、matched-holder resolution 与 source workflow |
| `x5crop/detection/source_core.py`、`evidence/scan_canvas.py` | source/lane 与 matched-holder authority |
| `photo_geometry/coarse_strip_support.py`、`coarse_enclosing_model.py`、`coarse_enclosing_support.py` | 两个 role-free aggregate query、粗片带 interval、source-wide 双侧 track 与 receipt |
| `photo_geometry/template_measurement_plan*.py` | pixel-free 模板、有限 query intents、停止与工作上界 |
| `photo_geometry/corridors.py` | 候选无关 top/bottom 与完整 `W/pitch` sequence 查询走廊 |
| `photo_geometry/registered_*.py`、`observations.py`、`separator_*.py` | 一次性 measurement、role-free edge 与 material band |
| `photo_geometry/cross_height_transition_measurement.py`、`broad_material_transition_measurement.py` | 同一 registered baseline 上的三区域局部弱信号与双尺度宽缓 material 测量 |
| `photo_geometry/aggregate_edge_support.py` | aggregate edge 的唯一解析、相关证据去重，以及完整三区域 separator pair 向 placement 的唯一投影权限 |
| `photo_geometry/template_contact.py` | candidate-independent `ContactEdgeObservation`：从既有 authoritative edge ledger 证明唯一共享 physical edge，不读取像素或选择 ordinal |
| `photo_geometry/template_overlap.py` | candidate-independent `OverlapEdgePairObservation`：从既有 authoritative edge ledger 登记唯一反序 END/START pair，不读取像素或选择 ordinal |
| `photo_geometry/source_geometry.py`、`joint_axis_geometry.py` | source W/H extent、scan-scale authority 与不增加 direct provenance 的相关 interval 收紧 |
| `photo_geometry/template_frame_width.py` | selected-only `SourceFrameWidthAuthority`、source W 校准、无权局部 refinement 让位与相关单侧角色推断；不得参与离散候选选择或重编译 template |
| `photo_geometry/template_aspect_ratio_model.py`、`template_aspect_ratio.py` | 校准 W/H 比例的 typed authority、相关 H 推断、direct H 对账与预算失败 |
| `photo_geometry/template_phase_model.py`、`template_phase_candidates.py`、`template_model.py` | Sequence coordinate/evidence identity、role binding、`AdjacencyRelation` sum type、Contact 同边双角色与 Overlap 独立反序双角色约束、projection outcome/type、同一离散 identity 的有界投影重拟合，以及 physical/source W 下的有界 native-edge rebind |
| `photo_geometry/template_phase.py`、`template_pitch.py`、`template_residual.py` | phase/ordinal 求解、连续 placement identity、Contact/Overlap/Separator 离散竞争、selected-only source-W rebind 调度、source pitch 与逐 adjacency delta |
| `photo_geometry/template_direct_role_authority.py` | 每个 bounded phase candidate 与最终已选 START/END 的 native-coordinate 权限证明及共享 evidence ledger |
| `photo_geometry/template_lattice_authority.py` | `(phase, W, pitch)` 直接约束矩阵与独立闭合证明 |
| `photo_geometry/template_adjacency_coverage.py` | selected adjacency 合法走廊到既有 query/trace/coordinate 的覆盖证明 |
| `photo_geometry/template_adjacency_topology.py` | selected adjacency 的 continuity ledger、Contact/Overlap 验证与 typed topology failure；不读取像素或重新选择 placement |
| `photo_geometry/template_outer_frame_authority.py` | 带 Grid 推断时首尾输出 Frame 的直接长轴角色证明 |
| `photo_geometry/template_alignment_diagnostic.py` | theoretical-vs-observed residual 的只读诊断 |
| `photo_geometry/interval_math.py`、`template_cross*.py`、`template_cross_support.py` | 共享 interval 运算、source H 校准、局部 top/bottom 方向闭合、typed producer bound 与 enclosing support |
| `photo_geometry/template_placement.py`、`template_selection.py` | source-axis frame 的一次 compose、显式 overlap 的 cross-support 去重与离散 winner/runner |
| `photo_geometry/template_holder_fill.py` | selected PhotoGroupOuter 与 W-only fill assessment |
| `photo_geometry/content_*.py` | 最终 post-bleed polygon 上的二维 negative veto |
| `photo_geometry/template_feasible_geometry.py` | selected placement 的低维联合可行集合 |
| `photo_geometry/template_output.py`、`output_model.py` | JointPlacementEnvelope、基础 bleed、Contact/Overlap 两侧 topology protection、OutputFootprint 与同一 5% budget |
| `photo_geometry/template_runtime_model.py`、`template_gate.py`、`detector.py` | current-only handoff、CandidateGate facts 与顶层编排 |
| `x5crop/detection/output_deskew.py` | approved-only 6–24 trace、role-free、candidate-independent 的可选输出角度 observation |
| `x5crop/detection/decision/`、`final/` | 最终决定、Decision 后 deskew assessment 与 approved geometry exposure |
| `x5crop/report/` | compact production report 与 development facts 的生成 |
| `x5crop/debug/` | 只读诊断 facts 与面板 |
| `x5crop/io/`、`export/`、`output/` | TIFF domain、affine sampling、metadata 与原子发布 |
| `tools/verify`、`tools/regression/` | 唯一验证入口、外部 report validator、方向性黄金验收与 accuracy/diagnostic/performance/platform 分层证据 |
| `tools/manual_annotation/` | source-SHA-bound 的本地 proposal、原 TIFF 有界精修、原图坐标人工审核与最内侧可接受裁切基准冻结；不进入 production 或 release |

人工标注器的 canonical record 按 source SHA 聚合：两条共享短轴边和一个物理 `boundary_pool` 只保存
一次；每个显式 count task 分别保存 `slots` 与只读派生的 `adjacencies`。最大 count 定义物理 Frame
集合，其它 task 只能按长轴顺序引用子集。共用 end/start line ID 为 `contact`，独立边反序为
`overlap`，空 slot 邻接为 `not_applicable`，其余为 `separator`。

只有 `blank_exposure` 使用 `reference_geometry: not_applicable`；它仍占显式 count，但没有人工
start/end 或 accuracy polygon。其它 Frame 必须有 `boundary_pair`。同一物理 Frame 在各 count task 中
必须共享 `slot_kind`。只有 `source_truncated` 可让物理 Frame 越出 TIFF；冻结 polygon 为物理 Frame 与
raster pixel-center 域的交集，源外区域不参与黄金包含或 5% 预算。若物理 polygon 没有实际越界，则
`source_truncated` 标签本身不能通过确认。Orientation 只做可逆显示，持久化始终使用原 TIFF 坐标。

机器拟合、红线导入、有界 JPG 与原 TIFF 窄带精修都只有 proposal 权限。精修不得改变证据基础、物理
identity、task mapping、Frame 语义或相邻关系；只有用户完成原生像素审核并明确确认，记录才成为不可变
`user_confirmed` 基线。确认记录冻结 task-level nominal/challenge 角色与原因，accuracy 会从冻结证据
重新推导核对；确认本身不改写 tracked cohort。完整操作见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)。

漏光、小角与正负片只形成校准分层，不产生 ignore mask、whitelist、样片阈值或 runtime 分支。若通用
二维 content 证据仍可靠越过最终 footprint，`content_veto` 让整张 source 进入 `needs_review` 才是
安全行为。

## 14. 验证边界

- `x5crop_directional_minimum_acceptable_crop_v1` 是全部当前与以后用户确认黄金共用的
  accuracy 合同。用户确认 polygon 是尽量贴近该 source 真实有效成像边界的最内侧可接受无 bleed
  基准，基本可视为该 source 的 aperture 尺寸；它仍不是实验室级绝对测量，也不限定 detector 只能产生
  一个逐像素相同的答案。
- 黄金比较是方向性的：`approved_auto` 的正式 post-bleed `required_source_footprint` 必须完整包含确认
  polygon，边、角点或亚像素位置不得向其内侧越界；任一违例都是危险自动批准并硬阻断。Development
  contract 还用同一规则检查 selected candidate，以定位 detector 机制；Review candidate 的偏差不产生
  正式输出，因此只属于 candidate 几何诊断，不能称为用户层危险批准。几何 epsilon 只吸收浮点计算
  误差。具有向外预算权限的每一侧，其总 expansion 不得超过对应确认 W/H span 的 5% 加命名的 sampling
  allowance，uncertainty、residual 与 bleed 均消耗该预算。这不是零像素误差或对称接近度要求。
- 逐线 `review_basis` 分别决定向内包含与向外 5% 预算能否产生阻断 accuracy verdict：

  | 证据基础 | 向内越线 | 向外超过 5% |
  |---|---|---|
  | `visible_content_limit` | 阻断 | 不阻断 |
  | `human_width_estimate` | 不阻断 | 不阻断 |
  | `directly_visible` | 阻断 | 阻断 |

  `directly_visible` 只表示人类从原 TIFF 的可靠像素分界确信该侧是真实内容边缘；分界可以很淡、很短，
  不必覆盖完整 H。它不建立 detector edge/trace 命中、observation identity、证据长度、强度或逐像素坐标
  相等要求。比较只检查 candidate 或正式 `required_source_footprint` 是否满足上表对应的方向性几何
  合同；检测机制不同但最终安全裁切合格时仍通过。
  `visible_content_limit` 是残缺曝光中仍可见内容的最内侧安全保护线：裁切进入该线以内会丢失可见内容，
  必须阻断；线外没有可见内容证据，因此不能用相对该线的 5% 预算阻断更大的外扩。
  `human_width_estimate` 由同一 source 中其它直接可见边界所确定的一致 Frame 宽度推算；它仍不是该侧
  的直接像素观察，线内、线外均不产生 accuracy verdict。没有足够一致的可见 Frame 宽度时保持未分类，
  不制造估计线。
  同一 Frame 的其它边仍逐侧独立生效，不能因一侧豁免整格或整张 source。以上权限只属于黄金 accuracy
  比较，不放宽 Runtime 的 source 内安全、format/count、Gate、TIFF 或正式输出合同。`origin` 只记录
  坐标来源，`review_basis` 独立记录证据基础；人工移动或冻结不能改写已经声明的证据基础。
- 几何 accuracy 只比较带 `boundary_pair` reference 的 Frame ordinal。`blank_exposure` 的
  `not_applicable` 表示没有人工内容边界，不是通配框、估计框或放行特例；它不减少 Runtime count，
  也不改变模板、源内安全和整张 source 决策合同。
- 上述黄金合同不因 `boundary_use` 改变。`enclosing_support_pair` 的总高度不超过 `1.1H` 仍是 runtime
  自动决策合同，但在黄金 accuracy 中还必须满足逐侧 5% 外扩上限，不能用总 span 隐藏单侧过度外扩。
- Nominal 的能力目标是安全自动批准；challenge 不预设终态，安全 `approved_auto` 与安全
  `needs_review` 都是合格结果，前者单独记录为能力发现。角色在运行 detector 前按 evaluation task 的
  证据充分性冻结，不读取 detector 输出，也不进入 runtime：只要人工确认的直接证据与
  format/count/template 能唯一确定合法 placement 和 source-safe footprint，即使存在残缺曝光、源截断、
  空 slot 或 `visible_content_limit`，仍可属于 nominal；这些标签本身不是 challenge 原因。
  只有必要边界权限缺失、存在多个同样合法的 placement、安全闭合无法唯一证明、未知必需 Frame、
  contact/overlap，或异常数量超出当前固定模板合同等事实使自动安全结论不可靠时，才属于 challenge。
  长轴直接证据还必须满足逐 task 的结构预算。只统计拥有 `boundary_pair` 的非空 Frame，并将
  `visible_content_limit` 与 `human_width_estimate` 计为非直接可见边界；按唯一物理 boundary identity
  计数，contact 共用线不得重复。满足任一条件即为 challenge：某个 Frame 的 start/end 均非直接可见且
  另一 Frame 还有另一条非直接可见边界；`count <= 3` 且非直接可见边界不少于 2 条；`count > 3` 且
  不少于 4 条；或 count 小于 format 最大完整格数、人工照片组在 source 长轴两侧都明确空余至少一个
  固定 W，且首张 START 与末张 END 不是两条都直接可见。最后一种事实命名为
  `two_sided_floating_partial_sequence`：它从确认前的 source extent、format W 与物理 outer 推导，不读取
  detector 输出，也不复用 selection 后的 `HolderFillAssessment`。两端 outer 都直接可见的内部短片条
  仍为 nominal。单个标签或低于预算的分散估计不自动降级，未分类线仍由必要边界权限缺失单独阻断。
  角色不能在观察失败后修改，也不能成为样片 whitelist。
  标注器按该合同逐 task 派生并展示角色，不提供人工切换；同一 source 的任一 task 为 challenge 时，
  source 队列归入 challenge，同时保留各 count task 的独立角色与原因。
  不存在 selected candidate 的 Review 记录为 candidate `not_available`，不伪造几何 verdict；cosmetic
  deskew 精度不阻断黄金，affine polygon envelope 与 TIFF 安全合同仍阻断。
- Development 验证分开报告四个维度：任何角色均须为 0 的 `unsafe_approved_auto`、不产生正式输出的
  candidate geometry conformance、nominal 自动覆盖，以及 challenge capability。决定分布、candidate
  偏差、自动覆盖与安全准确性不得合并为单一“准确率”。
- 检测能力发布底线是当前 development nominal 全部安全 `approved_auto`，全部角色
  `unsafe_approved_auto = 0`；challenge 的安全 auto 是能力发现，安全 review 同样合格，但不能替代
  nominal 覆盖。未来建立 sealed cohort 后，其 nominal 也必须全部安全自动通过。不得把失败 nominal 改成
  challenge、放宽黄金合同或隐藏 runner 来达标。
- 工程发布底线独立检查正式 24-source mean `<= 5s`、TIFF/metadata、安装、Apple Silicon macOS、Intel
  macOS、Windows x64 三目标、打包以及 Hook/CI。检测能力与工程能力不得合并成一个模糊的“发布通过”。
- 受跟踪的 `development_diagnostic` cohort 只证明不崩溃、工作量有界、报告闭合和 TIFF 工程合同，
  不证明几何正确或未见来源泛化。
- 黄金 reference 只有一个 source-SHA-bound 权威集合；人工确认只授予 reference，不自动决定 evaluation
  partition。当前 `development_gold.jsonl` 是已经查看并用于调试的开发集。集合被重置或没有当前开发
  确认时，development gold 明确报告 `calibration is incomplete`，不读取旧确认、旧 JPG 或历史 cohort
  回退。`tools.regression.gold_cohort` 是当前 development 确认汇总到 tracked cohort 的唯一生成入口：
  逐一复核 source、确认快照、审阅 artifact、task identity、format、count、角色和 geometry digest，且
  不由标注器自动触发。
- 未来新增 source 必须在查看 detector 结果前按 source SHA 固定为 development 或 sealed acceptance；
  同 SHA 的全部 count task 同分区。日常开发命令不得读取或输出 sealed 的逐样片结果，只能在里程碑生成
  aggregate receipt。显式打开 sealed source 调试后，该 source 永久转入 development，并补充新的 sealed
  source。分区共享同一 reference authority，不建立 v1/v2 或其它平行校准池。当前尚无 sealed cohort，
  因而不能作未见 X5 扫描的泛化或发布准确性声明；这一事实须在发布说明中披露，但不阻断首版发布。
- 生产中发现的危险自动裁切不是新的 validation partition。该 source 完成人工 reference 后永久加入
  `development_gold`，作为 incident regression 参与此后每次机制验证；同类修复必须是通用物理能力，
  不能读取 incident identity 或建立 whitelist。新的 sealed source 应随真实使用持续补充，但不要求每个
  production incident 在修复前同步取得一张 sealed source。
- 概率选择层还需要独立 calibration source，且必须在查看 scorer 输出前冻结；calibration 与 sealed
  不能互相替代。只有 feature/model/threshold、风险预算、OOD 合同和候选生成 commit 全部冻结后，才能
  运行 sealed aggregate acceptance。任何改动都使两类 receipt 同时失效；sealed 失败不得用于逐样片
  调参，打开 source 调试则按既有规则永久转入 development。
- `tools.regression.gold_analysis` 只在 development gold 上生成优化分层与 diagnostic；不进入
  runtime、Gate 或黄金 verdict。分层只读取冻结人工事实：结构正常、全部直接可见、`count >= 3` 且人工
  几何对最佳固定 `phase + pitch + W` lattice 的最大 role residual 不超过 `0.02W` 时进入基础 nominal
  分桶，其它 nominal 进入较难分桶，challenge 保持原角色。该 2% 只是优化顺序，不是 runtime 阈值、
  5% 安全预算或样片白名单。“机器是否看见”必须由每次运行的 observation/binding 事实重新生成，不能
  写回人工基线。分析结果绑定 HEAD、detector source manifest、comparator source manifest 与 development
  gold SHA，并分别记录两组路径是否与 HEAD 一致。`--gate zero-unsafe-auto` 只在完整 development gold 上
  阻断危险自动批准；完整 development contract 仍独立检查 candidate conformance 与 nominal 目标。
- 同一分析按 source SHA 去重验证 runtime 物理先验，并分别统计同源与跨 source 的 W/H、separator gap、
  pitch，以及 scan-canvas/profile 和 top/bottom corridor。黄金红线是人工确认、尽量贴近该 source 真实
  有效成像边界的最内侧可接受基准，基本可作为 source aperture 的真实尺寸观测；因此它可以校准物理
  分布、format prior 和 source-level extent owner。它仍不是跨相机绝对固定常量：holder-normalized mm
  只是在名义片夹尺度上的估计，明显偏离 catalog 时必须先检查真实相机个体差异、扫描比例和 measurement
  uncertainty，不能自动判为标注错误，也不能由开发集直接晋升为未见验证证据。
- 24-source performance 只证明其绑定 commit、依赖和机器上的完整路径时间与资源；5 秒均值是
  blocking Gate，3 秒均值只是 non-blocking challenge。
- Platform 聚合必须同时收到同一 commit 的 Apple Silicon macOS、Intel macOS 与 Windows x64
  三份实机 receipt。APFS/HFS+ 与 NTFS 分别本机验证；没有独立卷时 exFAT 必须保持
  `best_effort_unverified`，不得静默升级为已验证。
- 合成和变形合同覆盖 coarse support 的统一边框、翻转、横竖转置和亮度/对比度，phase 的平移、缩放
  与 fractional pitch，cosmetic deskew 的可用/跳过及横竖旋转符号，轻微直线 residual、缺边、
  多处直接 wide/narrow gap、contact/overlap 的安全 auto 与安全 review、同源 count 变体、强内部假边、填充
  状态、dual lane、联合安全预算和 source-wide 事务。
- Development gold、性能、依赖、TIFF/metadata、安装、三目标平台、打包和 Hook/CI 的 release receipt
  必须绑定同一最终 commit；否则 V5 不创建 RC、tag、Release 或公开 ZIP。若已有 sealed cohort，其
  aggregate receipt 也必须绑定同一 commit。当前黄金未覆盖 `xpan`、`120-645`、`135-dual` 不阻断发布，
  但发布说明必须明确“尚无真实样片覆盖”，Runtime 不得为此建立禁用、白名单或宽松规则。
