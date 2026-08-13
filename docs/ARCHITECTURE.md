# X5 Crop V5 架构

本文是 V5 已确认产品合同、物理模型、运行流、数值合同与源码 owner 的唯一说明。版本级变化见
[CHANGELOG.md](CHANGELOG.md)。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 1. 产品与输入 authority

X5 Crop 处理用户已经知道 format、片条模式及必要 count 的 Hasselblad / Imacon X5 片夹扫描。

- format 是硬事实，程序不从像素或文件名猜 format。
- count 包括中间空白曝光格；空白格不能删除、合并或改变 ordinal。
- full 表示用户确认片条采用匹配片夹的完整铺满布局；count 自动使用 `full_count`。
- partial 表示片条没有铺满片夹，必须明确输入 `1 <= count <= full_count`。即使 count 相同，
  partial 的 phase 仍可位于片夹长轴任意位置。
- `135-dual` 只允许 full，总计 12 格，每 lane 6 格，表示两条 lane 都是用户确认的完整铺满布局。
  一个 total partial count 无法表达两条片条的分配，因此不提供该模式。
- 片夹匹配先于 matched-holder count 校验。非交互调用发现非法 count 时，在整批 detector 启动前
  以退出码 `2` 停止；交互入口列出全部冲突并返回 mode/count 步骤。
- Holder identity 或 `full_count` 无法唯一确定时保持 `needs_review`，不猜片夹或 count。
- 任一 slot 不安全时，整个 source `needs_review`，不做 slot salvage。V5 不做 blank suppression。

唯一 count 数据流是：

```text
SlotCountRequest
→ MatchedHolder/full_count
→ ResolvedSlotCount
→ ResolvedOutputSlots
```

`ResolvedSlotCount` 同时保存用户给出的 `HolderLayoutAuthority`。片夹匹配只提供 profile 与
`full_count`，不能替用户判断是否铺满。

核心裁切原则是：format 先给出固定照片矩形；检测依据物理证据放置矩形，再只纳入该胜出位置
自身的测量不确定区间。5%/3% 只验证最终结果，不参与搜索、选位或 padding。

## 2. Format、片夹与尺度

尺寸按片条长轴 × 短轴记录：

| format | 固定照片尺寸 | `G_format` 搜索先验 | `full_count` |
|---|---:|---:|---:|
| `135` | 36 × 24 mm | 2 mm | 6 |
| `135-dual` | 每 lane 36 × 24 mm | 2 mm | 12，6/lane |
| `half` | 18 × 24 mm | 1 mm | 12 |
| `xpan` | 65 × 24 mm | 2 mm | 3 |
| `120-645` | 42 × 56 mm | 无 | 4 |
| `120-66` | 56 × 56 mm | 无 | 3 |
| `120-67` | 70 × 56 mm | 无 | 通常 3，短片夹 2 |

120 族只保留 56 mm 短边，不保留 54 mm component。135、half、XPan 的 gap 数值只确定首次
搜索中心，不能证明当前 source 的正常间隙。120 间隙受相机或后背型号影响，不建立联网值或
项目样片先验。

片夹画布只提供宽松尺度：

```text
nominal_px_per_mm = 匹配片夹扫描范围像素尺寸 / 片夹物理尺寸
W_nominal_px      = nominal_px_per_mm × format 长轴尺寸
H_nominal_px      = nominal_px_per_mm × format 短轴尺寸
```

相机片门尺寸偏差与扫描比例偏差对本项目等价，不尝试区分。数值合同为：

```text
W 兼容范围：format 名义宽度 ±1.25%
H 兼容范围：format 名义高度 ±0.40%
片夹 extent：物理名义范围 ±3.5%
```

X5 长图基本没有可用齿孔；源码、测试与 Gate 都不得依赖齿孔。

## 3. 共享物理几何

### 3.1 `SourceScanGeometry`

同一 source 共享：

- px/mm 扫描比例与 W/H 可行窄范围；
- source 主方向族；
- affine 坐标基准。

不建立 `W_effective_px`、`H_effective_px` 或逐张尺寸。完整 opposite-edge span 只能验证和收紧
共享范围；多组兼容 span 取交集，冲突保持 unresolved，不能平均或分配给不同照片。

### 3.2 `LaneGeometry`

每个 lane 独立拥有：

- 连续中心线；
- 围绕 source 主方向族的小角度偏差；
- sequence phase；
- `LaneGapModel`；
- 局部异常与可见 authority。

双 lane 共享尺度和大致方向族，但不共享中心线、phase、gap 或异常，也不强迫数学上完全平行。
所有照片都是同一 W/H 的矩形：不允许逐张尺寸、逐张旋转或四角自由迎合内容；允许卷曲、片夹
压力与扫描形变造成小而连续的中心线和边缘偏离。Start/end 与 top/bottom 属于近似正交的共同
方向族。水平与垂直扫描只交换规范坐标轴，不能形成两套 detector。Deskew 使用 lane 共同方向，
只需视觉上平直，不追逐照片内部线条。

## 4. Authority 与证据语义

每个物理边界只有三种状态：

- `support`：直接像素观察与候选角色相容；
- `contradiction`：可靠事实否决候选；
- `unobservable`：遮挡、截断、空白、叠片或内容使边界不可观察。

没有检测到边缘不等于边缘不存在；强烈内容线、灰尘、片夹线也不自动成为照片边界。Expected
position 只限定首次搜索走廊和顺序，不能创建 phase 或边界。Partial 可位于画布长轴任意位置；
full 只有在完整正常布局事实成立时才取得条件式居中权限。第一张或最后一张被遮挡时，物理框
可以延伸到 authority 外；项目只保护 TIFF 中可恢复的部分。

Source/lane authority 来自 raster、片夹布局和 lane 几何，不能从“没有内容”推导。

## 5. 唯一 observation 层

Registered measurement 一次生成候选无关、数量有界的观察。

### 5.1 `BoundaryEdgeObservation`

记录单条局部边缘的 source 坐标区间、方向与不确定区间、空间支持区域、极性及原始 observation
ID。单 edge 在完整链绑定前没有 start/end、ordinal 或 contact authority。

### 5.2 `SeparatorBandObservation`

只有方向、空间支持和极性相容的相邻 edge 才能组成 band：

```text
band[i] = [L[i], R[i]]
L[i]    = end[i]
R[i]    = start[i+1]
g[i]    = R[i] - L[i]
```

Band 保留左右边、gap 区间、黑度、纹理与跨短轴连续性。一条 band 是一份直接像素观察；左右边
不能算两票，但绑定后可同时约束两个 slot。

### 5.3 Top/bottom edge family

只在共享 H 决定的窄走廊中寻找局部连续段。Top 与 bottom 分别聚合，再用共享 H、方向和连续
中心线配对。两个空间分离的长轴区域是最低重复证据；一条长连续线最多按有限的前、中、后区域
提供支持。Count=1 也可在同一照片的不同长轴区域取得重复支持。只在单张照片局部出现的横线
不能改变 source/lane 级边缘族。

项目无需区分照片边缘、胶片边缘和片夹可见边缘；只要候选外没有可恢复照片内容，它们对裁切
等价。已知 top 可由共享 H 推导 bottom，反之亦然；推导边必须标记 `inferred`，不能冒充第二份
直接观察。最终选择能够放置固定 H、未被内容否决的最小安全 pair。

### 5.4 `ContentOccupancyObservation`

内容层保存真正的二维占用单元或连通区域，不把某个长轴位置的内容扩展成贯穿 lane 的 bbox。
内容只作负向否决：可靠连续内容被候选裁断，或可靠内容穿过预计的正常正 separator core，才可
否决候选。

以下情况保持中性：没有检测到内容、黑片或低纹理、start/end 外侧的邻片内容、接触或叠片中的
跨边内容、片夹遮挡外不存在像素。黑色区域不能证明大间隙；连续黑区仍须按 count、W 和物理链
保留所有空白 slot。

角落局部擦边同样中性。Top/bottom 的否决内容必须离开 start/end 角落并在照片长轴内部跨过完整
边界不确定区间；start/end 亦须在照片短轴内部成立。二维结构还必须在边界内外各保持一个内容
测量单元的连续深度。项目保护具有可靠二维延续的有效内容，不把角点、边缘锯齿、尘点或极小
局部擦边升级成 veto。

不保留 basic/enhanced 平行 detector。唯一 measurement owner 可对已登记缺口执行一次有界局部
refinement，但结果仍进入同一 observation ledger。

## 6. `LaneGapModel`

三个量严格分开：

```text
G_format  format 级搜索先验
G_source  当前 lane 的正常间隙可行区间
g[i]      当前 adjacency 的实际局部间隙
```

完成 ordinal 绑定后，用同类边的相邻 pitch 建立 `G_source`：

- 0 段：只有 `G_format` 搜索先验；
- 1 段：proposal；
- 至少 2 段相容：supported；
- 更多段：使用全部相容证据共同收紧；
- 冲突：unresolved，不平均，也不选择更接近联网值的一段。

120 partial 只有一段 pitch 时始终 unresolved，不借用其它样片、lane 或相机型号。正常间隙是
可行中心区间，包含测量误差与很小的机械波动；不为每段正常 gap 建立自由 delta。

正常是 full 与 partial 的共同默认关系，但默认正常不等于已知 `G_source` 的具体数值。一段直接
正间隙可记录为 `observed_normal`，能够放置该 adjacency，却不能补全其它缺失间隙或升级为
`G_source supported`。`G_format` 始终只负责 registered search，不拥有 placement。

## 7. Sequence chain 与异常

默认正常关系为：

```text
start[i+1] = start[i] + W + G_source
```

没有异常证据时只建立正常 chain，不构造纯数学可能的接触、叠片或大间隙替代链。缺失 separator
仅在 `G_source supported` 且正常链未被否决时由模板补全；模板位置标记 `inferred`。若全部 slot
已由直接边缘完整锚定，即使 `G_source unresolved`，完整 chain 仍可成立；若缺失位置依赖未建立
的 `G_source`，保持 unresolved。

Full 额外声明铺满布局。没有异常证据、正常链的理论总跨度可容纳于片夹可见长轴时，完整链以片夹
长轴中点为大致中心并按正常 pitch 均匀排布；曝光矩形总跨度不必等于整个扫描画布，片夹首尾可以
保留物理余量。若所有 adjacency 都被直接观察，chain 即使尚不能建立共同 `G_source` 也可使用其
直接正间隙验证居中；任何缺失 adjacency 仍要求 supported `G_source`。接触、叠片或大间隙的直接
证据会关闭这项均匀居中模板权限，不能被 full 覆盖。Partial 永远不消费该布局权限。

特殊锚定关系：

- count=2 时，一个完成角色绑定的 separator 足以放置两个固定 frame；
- count=3 时，两条完成绑定的 separator 可形成完整 chain；
- 一条直接外边缘加 supported `G_source` 可以传播正常 chain；
- 只有 `G_format` 时，一条外边缘通常不足；
- 首尾外边缘不可见时只能由 chain 推导并与 authority 求交。

异常满足：

```text
g[i] = start[i+1] - end[i]
g[i] >= -W
start[i+1] >= start[i]
```

`g[i] > 0` 为正间隙，约等于 0 为接触，小于 0 为叠片，很大正值为大间隙。接触、叠片、大间隙
和相位跳变必须来自完成角色绑定的直接几何，或正常链被可靠内容、总跨度或两侧锚点否决。正常
链已被否决而异常位置不确定时，直接记录 `local_advance_unresolved`，不枚举组合。

已证明异常只改变对应 adjacency，后续 phase 整体移动一次，其余 gap 恢复正常，除非另有直接
异常证据。异常不改变 count、ordinal 或 W/H，也不合并 slot。叠片时两个完整 format 框可以共享
source pixels，重叠 pixels 同时写入两张输出且不消耗 direct-use budget。

## 8. 有界联合求解

Cross 与 sequence 分别产生有限 proposal，但任何一轴都不能提前选赢家：

```text
registered observations
→ 按原始 transition、位置/方向区间与连续支持去重物理 edge family
→ separator band 的固定 W 有向邻接路径 + cross proposals
→ 共享尺度、方向、中心线与 authority compatibility index
→ CompleteFormatChain
```

联合只访问 compatibility index 中的相容组合，不做全量笛卡尔积，也不从不同候选拼接四条边。
每条 chain 同时拥有 W/H、方向、中心线、ordinal、phase、gap、内容 assessment 与异常 authority。
拥有 `count-1` 条直接 separator 时，sequence 由按长轴排序且相邻 W-compatible 的完整有向路径
建立，不枚举任意角色组合。双 lane 在选择前先取 source 共享 W/H 交集并生成最终候选；选择后
禁止重新绑定、重新求解或重新物化证据，输出层只能给被审查的原链增加 sampling 事实。

Producer 上界由输入合同推导：

```text
phase hypotheses
  ≤ (separator bands + outer edges) × output_count

joint chain evaluations
  ≤ sequence hypotheses × 同一兼容方向/尺度类的 cross proposals

temporary memory
  ≤ 10 × source_pixels + 32 MiB
```

Producer 上限从去重后的 edge families、输出 count 与合法物理角色推导，不用固定“四条候选”
阈值。若派生上界无法完整覆盖，保存 proposed count 并产生 `producer_bound_exceeded`，不按强度
或顺序截取 first-N。重复 trace/window/fitting 只有在共享原始 transition、位置区间相交、方向
相容且空间支持连续时才合并；连通 family 若不能整体共同拟合，则全部原 observation 保留。

不得恢复通用 DP、beam、Grid、phase-vote、component chain、候选 query 削减、separator center
裁切、固定 pitch 全链复制、content bbox 放置、逐帧尺寸或无界全图 evidence。

## 9. 硬过滤、投票与明显胜出

每条完整 chain 先把 observation 分类为 direct role-bound support、inferred support、可解释的
内部/非边界观察、contradiction 或 unobservable，再执行 format/count、共享 W/H、lane 方向与
中心线、ordinal、单向顺序、authority、内容、异常与完整 slot 数硬过滤。

便宜的区间与集合检查在 frame/sampling/report 物化前完成。基本绑定后立即按 sequence、cross、
shared 三轴形成 Pareto frontier：三个轴均不弱且至少一轴明确更强才能淘汰竞争者；任一轴的票数
不能补偿另一轴缺失的 authority。所有不可比较 placement 都保留，不使用 top-K。

投票等级固定为：

1. 独立直接物理观察；
2. 完整 chain 与正常物理关系；
3. separator 材料与拟合质量；
4. expected position 等弱先验。

一个 band 只有在左右 edge 均绑定到同一 adjacency 的明确 end/start 角色、并实际约束该 chain
位置时才有一票；接触线承担两个角色仍是一票；两个空间分离的 separator 是两票；opposite-edge
pair 是一份强结构证据。W/gap/ordinal 相容、supported `G_source` 和 inferred separator 都不是
新增像素票。内容只否决。相同原始 observation 的多个拟合只能计一次。

候选 A 只有在以下条件同时成立时才明显胜出：

- A 与竞争者都通过硬过滤；
- A 在最高差异等级严格更强，或拥有更多同等级独立观察；
- 竞争者的直接观察在 A 中有明确的内部线、非边界或矛盾解释；
- 竞争者没有 A 无法解释的同等级直接证据；
- A 不只是靠黑度、expected position 或微小总分差胜出；
- A 形成完整、安全且异常有据的 chain。

不使用加权总分或 format/样片专属 margin。

Sampling-equivalent cluster 只在 source/lane authority、transform 与方向可行类、边界区间共同交集、
全部 slot 的 source/output sampling boxes、direct-use legal windows 与 budget 结果均相同时合并。
弱线索只能在真正等价 cluster 内选一个现有代表；位置或合法窗口不同就保留为不同 placement，
不能平均制造新位置。无法明显胜出的异位竞争保持 `placement_unresolved`。

## 10. 固定框、最小安全裁切与 sampling

每个 slot 先得到固定尺寸 `R_format`。正常间隙、接触、叠片或大间隙只改变位置，不改变尺寸。

```text
SafeCropEnvelope
  = selected R_format
  + selected placement 自身的测量不确定区间
  ∩ source/lane 可见 authority
```

Start/top 取同一胜出位置的最小安全值，end/bottom 取最大安全值。这个范围只计算一次，不再添加
fixed guard、minimum padding 或 bleed。落选位置不能进入 envelope；非嵌套 placement 不能取
union、平均或拼接。内容只能否决位置，不能拖动 format 框包围 content bbox。

Authority 截断不算切内容，也不消耗 5%/3%；被片夹遮挡或未扫描部分不恢复、不 padding。连续
坐标向整数像素的外向取整属于坐标正确性，不是保护层。

Affine sampling kernel 的像素支持由 sampling 层单独验证，不扩大 envelope、不改变 placement、
不参与 budget。旋转后 output AABB 的背景角只属于矩形 raster 表示；budget 使用 source-space
物理 footprint。

Direct-use budget 逐边使用闭区间上限：

```text
start/end 每边 ≤ 5% W
top/bottom 每边 ≤ 3% H
```

刚好达到上限通过，四边不能借额度；叠片共享 pixels 不算扩张。

## 11. Gate、输出与可审计事实

`CandidateGate` 只记录 holder/count、observation completeness、source/lane geometry、complete
chain、producer coverage、独立证据与 dominance、异常 authority、内容保护、selected placement、
selected-only envelope、source/lane authority、5%/3%、deskew、transform 与 sampling typed
assessments。它不重新选择位置，也不机械要求四条边都被直接观察。

`DecisionGate` 独占 `approved_auto`、`needs_review` 与固定 final reasons：

- `no_legal_placement`；
- `placement_unresolved`；
- `content_protection_conflict`；
- `local_advance_unresolved`；
- `producer_bound_exceeded`；
- `direct_use_budget_exceeded`；
- `source_lane_authority_unavailable`；
- `transform_sampling_unavailable`。

一个可靠锚点、supported gap、完整正常 chain、无同级竞争者且输出安全时可以自动批准。任一 slot
不安全时，整个 source `needs_review`，普通运行不写该 source 的正式照片。

普通 report 只保存输入与配置、holder/count authority、最终选择、每个 slot 的安全框、逐边 budget、
Gate 根因、输出文件和必要 TIFF 事实。Observations、全部 chain、ledger、content veto、dominance 与
producer work 只在显式 Debug Analysis 或验证工具中生成。旧 report 不参与 runtime；每次运行都从
原 TIFF 重新检测，不提供跨运行复用、旧 revision reader 或迁移器。

Debug Analysis 消费同一次 runtime 的 development facts，不重算几何、不改变检测、不写正式 TIFF。
显示层坐标归一化不能改变 source-coordinate placement、crop、budget 或 deskew。

## 12. TIFF、运行与输出发布

正式输入限于单页 unsigned 16-bit、RGB 三通道、contiguous planar TIFF；压缩接受 `NONE`、
`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD`。Orientation 1–8 在 decode boundary 转为
canonical coordinates，正式输出写 `Orientation=1`。

`tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与
sampling，Pillow 只在 Debug Analysis 时延迟导入。普通写出关闭后只复开 header，检查可读性、
shape、dtype、channels、ICC、resolution、受支持 metadata、压缩与 `Orientation=1`；完整像素复读
属于 TIFF contract、named-TIFF、platform、端到端与发布验证。

生产默认 `--jobs 1`、上限 3；数值库内部线程固定为 1。一次运行先在 target 同父目录写完整 staging，
全部成功后用一次 rename 发布为新的 target。Target 已存在或处理中出现同名目录时直接报错；runtime
不覆盖、接管、遍历或删除旧目录，不建立 lock、journal、ownership inventory、虚拟磁盘预留或文件
系统侦察。实际 I/O 失败直接报告，未完成 staging 不公开。

退出码为：`0` 完整发布且无 runtime error，`1` 已发布但含 runtime error或全部输入失败而未发布，
`2` CLI/input/preflight 错误，`3` fresh-directory 发布失败。全部 source 都是 `runtime_error` 时不发布
空结果。

数值按职责分为三类：format/片夹尺寸及 1.25%/0.40%/3.5%、5%/3% 是物理或产品合同；像素中心、
Scharr kernel 归一化、MAD consistency factor 是采样/统计恒等量；窗口毫米数、z 门槛、Huber loss
scale、内容 cell 与结构张量门槛是具名测量校准。校准值只能存在于对应 spec，必须带单位和合成/
黄金边界测试，不得散落成 placement、投票或 Gate 的隐藏阈值。

## 13. 验证与发布边界

`tools/verify` 是唯一验证入口：

```text
staged | full | accuracy | diagnostic | performance |
platform | platform-check | platform-package | pre-push
```

- Accuracy、diagnostic、performance 与 platform cohort 的 partial 记录必须携带明确 count；工具
  不得从文件名、片夹容量或像素推导。
- 111-source diagnostic 只验证 crash、hang、schema、authority、工作量、内存与 TIFF 工程合同，
  不产生 accuracy verdict。
- 24-source performance 使用完整用户路径、`jobs=1`，正式 mean 上限为 5 秒；profiling 与 SHA
  在计时外。
- Pre-commit 只检查 staged hygiene；pre-push 对纯文档运行 documentation，其余范围运行 full。
  Performance 只属于发布验证，不阻塞日常提交或推送。
- 九张用户确认黄金每张只运行一项；nominal 必须安全自动批准，challenge 允许安全 review。
- 不增加样片规则、whitelist、format denylist 或验证专用 detector path。
- `full`、diagnostic 或 performance 通过都不能替代 accuracy 与真实平台证据。
- 只有全部 release receipt 绑定同一 commit，才可创建 RC、tag、Release 或公开 ZIP。

## 14. 源码 owner

下表中的 `photo_geometry/` 均指 `x5crop/detection/photo_geometry/`。

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | 固定照片尺寸、容差、gap 搜索先验与 holder full count |
| `x5crop/configuration/` | 用户 count、片夹与 runtime configuration |
| `x5crop/io/`、`x5crop/export/` | TIFF domain、Orientation、metadata、sampling 与 write/readback |
| `x5crop/detection/source_core.py` | source/lane 可见 authority |
| `x5crop/detection/evidence/` | 候选无关的 OpenCV/SciPy 二维内容测量 |
| `photo_geometry/*model.py`、`model.py` | 物理、测量、proposal、selection 与 output 的不可变类型 |
| `photo_geometry/registered_*.py`、`robust_line_fit.py` | registered 像素测量与 SciPy Huber 数值拟合 |
| `photo_geometry/*observations.py`、`transition_tracking.py` | role-free edge family、separator material 与 observation |
| `photo_geometry/source_geometry.py`、`shared_source_geometry.py` | source 共享 W/H 及双 lane 选择前交集 |
| `photo_geometry/lane_gap_model.py`、`local_advance.py` | lane 正常间隙与有证据的局部异常 |
| `photo_geometry/sequence_*.py` | fixed-W 有向 separator path、ordinal、phase 与 sequence placement |
| `photo_geometry/cross_*.py` | short-axis family、fixed-H 配对、方向与中心线约束 |
| `photo_geometry/chain_*.py`、`chains.py` | 完整链物化、authority、ledger 与不可变签名 |
| `photo_geometry/*dominance.py`、`source_*.py` | sequence/cross/shared 分轴 Pareto 与 source 选择 |
| `photo_geometry/content_*.py` | placement 相关的二维内容负向解释 |
| `photo_geometry/placement_clusters.py` | 严格 sampling-equivalent placement cluster |
| `photo_geometry/output*.py`、`selected_source_output.py` | selected-only envelope、budget、transform 与 sampling assessment |
| `photo_geometry/lane_*.py`、`detector.py` | lane 准备、bounded reconstruction 与唯一顶层编排 |
| `x5crop/detection/candidate/`、`decision/`、`final/` | typed facts、最终决定与 approved geometry exposure |
| `x5crop/report/` | compact production report、development facts 与外部 read model |
| `x5crop/runtime/`、`x5crop/output/` | invocation、source workflow、terminal outcome 与全新目录发布 |
| `x5crop/debug/` | 只读 Debug facts、分轴面板与绘图 |
| `tools/verify` | 唯一 tracked verifier 入口 |
| `tools/regression/` | SHA-bound accuracy、diagnostic、performance 与 platform 验证 |
| `tools/install/`、`tools/release/` | standalone 依赖与发布 manifest |
| `tools/tests/` | 按物理、运行、I/O 与工具职责拆分的 focused contracts |
