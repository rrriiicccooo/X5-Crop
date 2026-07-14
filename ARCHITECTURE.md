# X5 Crop 架构说明 / Architecture Guide

本文件只描述当前 V4.9 的运行流程、物理模型和源码分层。用户操作见
`README.md`，版本历史见 `CHANGELOG.md`，协作与封口规则见 `AGENTS.md`。

## 1. 运行流程 / Runtime Flow

```text
entry
  -> runtime bootstrap + DetectionConfigurationBundle
  -> TIFF read + layout normalization + preprocess
  -> PreparedWorkspace + DetectionContext + MeasurementCache
  -> gray boundary paths + separator bands + content observations
  -> count hypotheses + frame-dimension priors
  -> solve_photo_sequence -> PhotoSequenceSolution candidates
  -> physical evidence + CandidateGate
  -> GeometryResolution + deterministic selection
  -> FrameBleedPlan
  -> DecisionGateAssessment
  -> finalization -> FinalDetection
  -> TIFF export / current-schema report / three-panel debug
```

### 1.1 权限边界 / Authority Boundaries

| Stage | Canonical responsibility |
|---|---|
| Entry | 只解析 CLI 与 interactive 输入。 |
| Runtime | 一次性解析 configuration，编排 worker、cache reuse 和写出副作用。 |
| Preprocess | 读取 TIFF，统一 layout，生成唯一灰度 workspace，测量 deskew 和 metadata。 |
| Observation | 生成 count-independent 灰度 path、separator band、content 与图像统计。 |
| Physical solver | 联合求解逐张 `PhotoAperture`、间距、count 与物理守恒。 |
| Evidence | 描述支持、矛盾、不可用或不适用；不决定最终状态。 |
| CandidateGate | 判断一个候选是否有独立物理证明且没有明确物理矛盾。 |
| GeometryResolution | 唯一 early-stop 输入；确认 count、placement、边界与替代解已经解决。 |
| Selection | 按物理目标确定性排序，并聚合区间等价解。 |
| FrameBleedPlan | 合并用户 bleed 与逐 boundary 的叠片保护。 |
| DecisionGate | 唯一创建最终 status 和 `final_review_reasons`。 |
| Finalization | 只应用输出计划和 canvas/lane clamp；不重新检测。 |
| Report / Debug | 只读 typed results；不补算事实或参与裁决。 |

`CandidateGate` 与 `DecisionGate` 是唯一两个 Gate。CandidateGate PASS 不代表几何已经
resolved，也不能触发 early-stop。只有 `GeometryResolution.supported` 可以结束候选扩展，只有
DecisionGate 可以创建 `approved_auto` 或 `needs_review`。

### 1.2 Runtime Configuration

Runtime 从 `FormatPhysicalSpec + strip_mode` 创建唯一 `DetectionConfiguration`。Format spec
只保存真实 frame mm、derived aspect、允许 count、physical layout 与 occupancy trait。Format
名字只用于 lookup，不拥有算法分支或 format-specific threshold。

Lower layers 只接收显式 physical spec、configuration group 或普通参数对象。它们不查询 registry，
不根据 mode 字符串发明默认参数。`DetectionContext` 保存检测请求、已解析 configuration、
metadata calibration observation 和 exact measurement cache；TIFF `ImageProfile` 停留在 I/O、
runtime 与 export 数据流。

## 2. Photo Aperture 物理模型

### 2.1 唯一裁切真相

`PhotoAperture` 表示源图中一张真实照片的可见开口，是检测层唯一理想裁切几何：

- 外部可见片基不属于照片开口。
- 内部 separator 不属于任何一张照片开口。
- 片夹直接压住画面时，holder-to-image contact 就是该侧可见照片边界。
- 被片夹遮住而不可见的画面不可恢复，不算脚本 undercrop。
- 灰度无法可靠区分照片与片基时，该边保持 unresolved。

每张照片由 leading、trailing、top、bottom 四个
`PhotoApertureBoundaryResolution` 组成。每条边保存位置区间、evidence state、typed source 与
measurement provenance。`PhotoSequenceSolution.photo_sequence_envelope` 派生全部开口的外包络
`Box`，不拥有检测权限。

`PhotoSequenceSolution` 的 provenance 由其实际 aperture assignments、separator assignments、
dimension prior 与 holder boundaries 自动派生，root 固定为 `FRAME_GEOMETRY`；调用者不能声明或
改写几何身份。每条 measured aperture edge 和 separator edge 都必须精确对应一个原始 observation
assignment，不能只靠 source 标签伪造实测几何。

`HolderBoundaryObservation` 只描述 canvas 邻接片夹范围，用于约束搜索。它不能直接定义照片
边界。`ContainmentFallback` 只给 REVIEW 与 Debug 提供安全范围，永远不是 resolved geometry。

### 2.2 灰度 Observation

Detection 只消费二维灰度 workspace。原 TIFF 通道、ICC 和色彩 metadata 由 I/O 与 export
保存，不形成 RGB、holder color 或片孔检测旁路。

每个 cross-section 保留最强的一组 adaptive change points，再按坐标邻近、跨 section 连续性与
二维路径拟合聚合成 `GrayBoundaryPathObservation`。每个 local sample 保存自己的 orthogonal
区间和位置不确定度；solver 在逐张照片长轴范围内解析 top/bottom path，而不是把全图 path
压成一个固定短轴坐标。灰度中位数、MAD、纹理、梯度、连续性和 intensity tail 只描述像素
外观，不能证明区域是片夹、片基、照片或 separator。局部 strongest-change 选择属于 adaptive
measurement；只有 path 数量或 solver search 的显式上限耗尽才产生 execution-budget unavailable。
Raw samples 的精确线性拟合由 `BoundaryPathFit` 表达；同一次 solve 对每条 observation 只构造一次，
随后按候选的长轴区间查询。它不是候选几何、物理证明或跨运行 cache。

Raw path 的物理解释只发生在 candidate-specific assignment：

- 可与 canvas 邻接形成 holder boundary constraint。
- 可分配为某张照片某一侧的 measured aperture edge。
- 可保留为未分配 observation diagnostic。

不同 observation channel 的 raw paths 完整保留在 report 中。几何等价 paths 在 solver 入口只形成
一个 hypothesis；已与内部 separator band 相交且中点位于 band 内的 path 由该 band 的双边解释
唯一消费，不再同时进入 generic aperture-pair 搜索。Band 边缘与独立 measured aperture edges 若
产生不同几何，冲突仍保留到 assignment consensus，不能用去重静默消失。

### 2.3 Separator 双边模型

`SeparatorBandObservation` 是 count-independent 像素 band，只保存 `start/end`、灰度外观、
tonal measurement 与 provenance；中点由两端派生，不是第三事实源。
跨短轴测量只存在于 candidate-specific `SeparatorBandCrossAxisSupport`，因为它必须对应当前照片
开口的短轴范围。

一个正间距 separator 有两条照片边界：

```text
band.start -> previous photo trailing edge
band.end   -> next photo leading edge
```

Candidate-specific `SeparatorBandAssignment` 必须同时满足：

- boundary position constraint；
- physical separator width constraint：band 必须窄于相邻照片的最小可行长轴宽度；若一个空白区
  已足以容纳一张完整照片，它只能保持 raw observation 或 dimension-dependent hypothesis，不能被
  命名为单个 hard separator；
- 跨短轴连续性；
- 单调 aperture order；
- measurement provenance 独立性。

宽度可变化，照片开口尺寸一致性才是主要物理约束。过宽的欠曝 tonal run 可以保留为 raw
observation，但不能成为 hard separator。Dimension-only edge 只是一条 provisional hypothesis，
不能增加 hard separator 数量或单独证明 count。

相邻照片的 signed `InterPhotoSpacing`：正值表示 separator，零表示 contact，负值表示 overlap；
`InterPhotoSpacingKind` 是该状态的唯一 typed identity，runtime/evidence/output 不比较裸字符串。
只有独立 observation 或独立约束共同佐证的 overlap 才能触发输出保护；geometry equation
推导的负值不能证明自身，也不能自动增加 bleed。

### 2.4 Global Photo Sequence Solving

`solve_photo_sequence` 对每个允许 count 和 frame-size option 联合求解一个或多个
`PhotoSequenceSolution`，每个结果包含全部
`PhotoAperture`，不先确定一个 outer
再补 separator：

- aperture order 与所有边界必须严格单调；
- 每张照片必须有正面积；
- interior photo dimensions 服从同一物理尺寸 option；
- holder occlusion 只允许作用于首张 leading 与末张 trailing；
- separator start/end 分别绑定相邻 aperture edge；
- count-independent content runs 只作为反证过滤明显漏掉已测可见内容的 solver alternatives；
  它们不能生成、移动或收缩任何 aperture edge。若所有 alternatives 都与 content 冲突，solver
  保留这些几何并由后续 evidence 明确报告 contradiction，而不是用 content 伪造新边界；
- aperture 总宽不是物理质量指标；在可见内容已经覆盖后，更宽的几何不能仅凭多包含片基或片夹
  余量支配另一组边界，实质不同的 alternatives 必须继续进入 geometry consensus；
- 首尾 aperture endpoint 的物理可行性与搜索顺序分离。符合完整照片宽度的 endpoint 与由同侧
  holder boundary 佐证的 clipped endpoint 都必须进入全局求解；dimension residual 只能决定探索
  次序，不能在 geometry consensus 前选出唯一 outer；
- assignment consensus 要求每张照片的每条 aperture edge 在全部非支配解之间存在同一个共同
  interval。仅由一条宽 uncertainty 分别接触两组互斥边界，不构成 geometry agreement；
- Pareto 支配只允许更优目标且逐边 interval 是另一解的细化。未经佐证的 overlap 可以在兼容
  geometry 内参与目标排序，但不能淘汰另一组 geometry；归约只比较仍存活的 frontier alternatives；
- cross-axis hypothesis 的搜索顺序不奖励更高的 aperture。可信 calibration 存在时使用照片短轴
  尺寸残差；否则只使用 count/aspect 可行性、测量质量、uncertainty 与稳定坐标顺序。被预算截断
  的 alternatives 仍使 geometry unavailable；
- raw boundary paths 只有在共享轨迹上的位置 uncertainty 完全相同时才是 geometry-equivalent。
  区间相交只表示 alternatives 可能一致，必须留给全局 consensus；一条宽 path 不能删除两条互斥
  的窄 aperture observations；
- holder boundary 只有在全部最高支持 edge-adjacent paths 存在共同 position interval 时才成立；
  宽 uncertainty 分别接触两条互斥 transition 时保持 unavailable，不能任选一条授予 clipping 权限；
- content coverage 必须与逐张 aperture 一致；spacing 与相邻 aperture edge 的
  守恒关系由 `PhotoSequenceSolution` 构造不变量保证，不再包装成独立 evidence 或 Gate；
- supporting measurement 可以被 geometry 消费；只有 measurement 反向依赖 `FRAME_GEOMETRY`
  才构成循环证明；
- search budget exhaustion 只产生 unresolved。

`FrameDimensionPrior` 由 mm/aspect/calibration 约束搜索，不是 measurement evidence。只有独立
photo edge measurement 可以形成 `FrameDimensionEvidence`。TIFF X/Y resolution 只是 metadata
observation，必须与独立物理观测一致才可成为 supported calibration；缺失或冲突 calibration
不会阻断 normalized detection。

Partial auto count 从允许的较大 count 向较小 count 求解。XPAN 与 120-66 可由 physical trait
包含 nominal count，以表达完整胶片未铺满片夹；该 trait 只改变 count availability 与 occupancy
解释，不绕过 aperture、coverage 或 preservation。

## 3. Evidence、Assessment 与 Decision

### 3.1 Candidate Evidence

Standard candidate 的 canonical evidence 包括：

- `PhotoApertureCoverageEvidence`：逐张 aperture 并集是否覆盖可见内容；content profile 的平滑半窗
  只形成位置不确定度，不能让未分配给任何照片的内容藏在 sequence 外包络内。
- external aperture preservation：首张 leading、末张 trailing，以及逐照片 top/bottom 的外边界安全。
- inter-photo boundary preservation：每条内部边界是否由 separator、contact 或 overlap 解释。
- separator sequence 与 photo dimensions；spacing conservation 是 geometry invariant，不是独立证明。
- holder boundary、holder occupancy、partial edge safety 与 physical scale。
- measurement independence。

Content evidence 只由局部 gradient、texture 与 contrast 共识生成，不把全局明暗位置当成内容。
它只提供遗漏内容反证与 preservation measurement，不能定义精确 aperture edge、制造 frame
count，或无条件扩张物理几何。同一份 count-independent content observation 由 measurement cache
保存一次，并同时供 solver 反证与最终 aperture coverage evidence 使用，避免两套覆盖事实漂移。
External crossing 测量排除相邻 aperture boundary 的 uncertainty
区域和 evidence kernel footprint，避免垂直边角或卷积邻域伪造跨界内容。单个 content/noise pixel
不得改写 aperture；独立 measured edge 与 content measurement 冲突时保留 conflict，不静默删除
measured geometry。Internal crossing 必须同时具有左右 aperture edge 上重合的短轴 content tracks，
以及一条贯穿该 boundary interval 的 count-independent 长轴 content run；两个互不相交的边缘纹理
不能佐证 overlap 或反证内部切线。

### 3.2 CandidateGate 与 GeometryResolution

CandidateGate 消费 canonical evidence，并检查：

- content preservation；
- measured photo geometry；
- evidence independence；
- 至少一条完整 boundary proof path。

它不读取 scalar confidence，也不拥有 final reason。Candidate blockers 只能从 failed Gate checks
派生。Standard 与 dual-lane physical candidate 拥有 CandidateGate；review-only candidate 使用独立
assessment 且没有 CandidateGate。DecisionGate 从这一 lifecycle fact 派生 automatic-processing
eligibility，physical geometry 不保存或推导 decision 权限布尔值。

`GeometryResolution` 单独回答 count、placement、每张照片边界、content compatibility、assignment
consensus、替代几何和 execution budget 是否已解决。Unresolved geometry 可以进入 provisional
selection 与 Debug，但不能形成 finalization plan，也不能在 `--export-review` 下导出 frame TIFF。

### 3.3 Selection 与 DecisionGate

Selection 只按 typed facts 确定性排序：优先保护可见内容，减少明确物理矛盾，优先 resolved
independent proof；partial auto 在其它事实相同后优先较大 count；最后比较物理 residual 与稳定
source order。`EvidenceQuality` 只统计叶子 physical evidence；`content_preservation` 与
`partial_edge_safety` 等 Gate/proof projection 不会再次计数。Geometry consensus 由对应 aperture/cut
uncertainty intervals 是否相交决定，不使用固定百分比 clustering tolerance。

DecisionGate 只消费 selected CandidateGate、GeometryResolution、selection consensus、
FrameBleedPlan 和 transform geometry。它不重新测量 evidence，不生成候选，也不以低 confidence
制造 REVIEW。

## 4. Output、Report 与 Debug

### 4.1 FrameCropEnvelope 与 Bleed

`FrameCropEnvelope` 由每张 `PhotoAperture` 四边 uncertainty interval 的保守外侧产生。它可以因
measurement uncertainty 多包少量空白，但不能冒充理想照片开口。

Final output 的次序固定为：

```text
PhotoAperture -> FrameCropEnvelope -> FrameBleedPlan -> final box
```

用户 bleed 是唯一主动增加普通 margin 的设置。Measured/corroborated overlap 只扩张相关
boundary 两侧；无关 frame 不受全局最大值影响。可用范围由 holder canvas 或所属 lane 的
`frame_output_bounds` 决定。Output planning 直接携带 canonical `InterPhotoSpacing` 与 typed
measurement provenance，不复制支持布尔值或压扁身份字符串。Bleed 不修改 aperture、
CandidateGate、GeometryResolution 或 status。

### 4.2 Current Report Schema

```text
schema_id: detection_report
schema_revision: photo_aperture_sequence_resolution
```

Canonical sections：

- `input`: TIFF profile、workspace extent、resolution metadata 与 transform geometry。
- `configuration`: current `DetectionConfiguration` read model。
- `selection`: candidates、provisional geometry、evidence、CandidateGate、GeometryResolution 与 clusters。
- `decision`: status、DecisionGate 与 `final_review_reasons`。
- `output`: FrameBleedPlan、optional finalization plan、optional final geometry 与实际写出结果。

Report、cache reuse、regression tools 与 tests 只接受该 schema。旧 schema 或字段形状直接 cache
miss；report/restoration 不补算 selection 或 decision。

### 4.3 Debug Analysis

Debug Analysis 固定三联图：原始灰度上下文、照片开口/输出几何、boundary/separator evidence。
它只读取 final typed model。内置图例由 diagnostics configuration 生成：

- white dashed: holder boundary；
- yellow: raw observation；
- red: measured aperture / separator edge；
- purple dashed: dimension-only provisional edge；
- cyan: corroborated overlap；
- green: `PhotoAperture`；
- blue dashed: `FrameCropEnvelope` / protected output。

Unresolved geometry 明确标记 `NOT EXPORTABLE`。Debug 可以用彩色线条解释灰度检测，但颜色不
回流 detection。

## 5. 源码分层 / Source Layers

| Layer | Canonical responsibility |
|---|---|
| `x5crop.entry` | CLI、interactive parsing 与用户文本输出。 |
| `x5crop.runtime` | Bootstrap、workflow、workers、reuse 与 output side effects。 |
| `x5crop.formats` | Format identity 与真实 physical spec。 |
| `x5crop.configuration` | Adaptive measurement parameters、execution budgets 与 runtime assembly。 |
| `x5crop.cache` | Exact count-independent measurement cache。 |
| `x5crop.geometry` | 纯 box、layout 与 sampling 算法。 |
| `x5crop.image` | Gray、statistics、deskew 与 pixel transforms。 |
| `x5crop.io` | TIFF read/write 与 metadata ownership。 |
| `x5crop.detection.physical` | Boundary/separator observations、photo dimensions 与 global solver。 |
| `x5crop.detection.evidence` | Typed physical measurements，不 Gate、不 decision。 |
| `x5crop.detection.candidate` | Count plan、build、assessment、execution 与 selection。 |
| `x5crop.detection.modes` | Standard、dual-lane 与 review-only composition。 |
| `x5crop.detection.decision` | 唯一 DecisionGate、status 与 final reason owner。 |
| `x5crop.detection.final` | Resolved geometry 的 finalization plan 与 FinalDetection。 |
| `x5crop.output` | FrameBleedPlan 与 output geometry。 |
| `x5crop.export` | Crop/review TIFF 写出。 |
| `x5crop.report` | Current-schema projection、validation、restoration 与 outputs。 |
| `x5crop.debug` | 三联 Debug Analysis 的只读渲染。 |
| `tools` | Contract tests、current-schema diff 与 standalone build。 |

Dependencies 只沿生命周期向前流动。Foundation 不知道 format/mode identity、configuration
registry、Gate、decision 或 report schema。Report/debug 可以读取 typed final model，但不能 import
detection computation。

## 6. 参数、Cache 与封口 / Parameters, Cache, Closure

每个运行参数与影响行为的数值常量必须且只能属于一个角色：

| Role | Allowed ownership |
|---|---|
| `physical_fact` | mm、count、layout、occupancy 等真实规格。 |
| `standard_transform` | luma、单位换算等标准变换。 |
| `adaptive_measurement` | quantile、MAD、采样、平滑与 minimum support。 |
| `numerical_safety` | epsilon 与索引 clamp；不得改变物理语义。 |
| `execution_budget` | observation、solver、deskew 与 worker 的有限计算量。 |
| `user_preference` | bleed、deskew 范围与显式运行选项。 |
| `diagnostics_only` | Debug 渲染；不得反向进入 runtime detection。 |

`MeasurementCache` 只缓存 exact、count/offset-independent measurements，typed key 包含所有影响
结果的参数与 region。Candidate、Gate、GeometryResolution、decision、final reason 和 approximate
geometry 永不缓存。Solver-local `BoundaryPathFit` 只是对同一 raw observation 的精确数值展开，
不进入 MeasurementCache，也不跨 count、图片或运行复用。

`tools/tests` 使用 AST 与 synthetic physical contracts 检查模块可达、唯一归层、单向依赖、
current schema、显式参数、零兼容与零孤儿。发现残余时先增加失败契约，再删除整类根因。冻结的
Extreme Cleanliness Contract 与双轮封口规则见 `AGENTS.md`。
