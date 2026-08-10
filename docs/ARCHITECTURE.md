# X5 Crop V5 架构

本文是 V5 已确认产品与实现合同的唯一 owner。源码尚未对齐的项目只记录在
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)，并在完成验证前阻断发布。版本变化见
[CHANGELOG.md](CHANGELOG.md)。

## 1. 产品合同

X5 Crop 处理用户已经知道 format 与片条数量的 Hasselblad / Imacon X5 片夹扫描 TIFF。

- format 是硬 authority，程序不从像素或文件名猜 format。
- `full_count` 是当前 format 与匹配片夹合同定义的完整曝光格数。
- full 表示实际 slot 数等于 `full_count`；它不表示片条铺满片夹或贴近画布两端。
- partial 必须由用户明确输入 `1 <= count < full_count`；count 包括中间空白曝光格。若 count 等于
  `full_count`，必须使用 full。
- 例如 120-66 的完整三格片条始终使用 full，即使片条位于片夹中间；只有一格或两格才使用
  partial。
- 片夹容量只校验 count 上限，不生成 count。交互入口对无效 count 重新询问，非交互入口失败。
- 空白曝光仍占 slot 并参与几何求解；V5 不删除、不合并也不抑制空白 slot。
- 任一 slot 不能安全输出时，整个 source 为 `needs_review`，不做 slot salvage。

核心裁切原则是：

> Format 决定照片矩形的形状与尺寸；检测依据物理证据放置这个矩形，再只纳入避免切掉可见内容
> 所必需的最小安全范围。5%/3% 只验证最终结果，不参与生成候选或填充边缘。

## 2. 坐标、格式与尺度

### 2.1 片条坐标

每个 lane 使用同一套片条坐标：

- `start/end` 沿照片排列的长轴；
- `top/bottom` 沿片条短轴；
- 水平与垂直扫描只是坐标轴互换，不能进入两套 detector。

### 2.2 格式目录

尺寸按“长轴 × 短轴”记录，单位为 mm：

| format | 照片尺寸 | `G_format` |
|---|---:|---:|
| `135` | 36 × 24 | 2.0 mm |
| `135-dual` | 每 lane 36 × 24 | 2.0 mm |
| `half` | 18 × 24 | 1.0 mm |
| `xpan` | 65 × 24 | 2.0 mm |
| `120-645` | 42 × 56 | 未定义 |
| `120-66` | 56 × 56 | 未定义 |
| `120-67` | 70 × 56 | 未定义 |

135 的 2 mm 来自 38 mm 名义 frame pitch 减去 36 mm 照片宽度；half 的 1 mm 来自 19 mm
名义 pitch 减去 18 mm 照片宽度；XPan 采用已确认的 2 mm。它们只提供第一次搜索的中心，不能
证明当前 source 的真实间隙。

120 族只使用 56 mm 短边，不保留 54 mm component。其正常间隙受相机或后背影响，联网名义值
和项目样片都不能成为 format 级 authority，因此 `G_format` 保持未定义，而不是零。

X5 扫描长图通常没有可用齿孔。任何 format 都不得使用齿孔估计尺度、相位、位置或 Gate 结论。

### 2.3 名义像素尺寸

片夹与扫描画布从一开始提供宽松尺度：

```text
nominal_px_per_mm = 片夹扫描范围像素尺寸 / 片夹对应物理尺寸
W_nominal_px      = nominal_px_per_mm × format 长轴尺寸
H_nominal_px      = nominal_px_per_mm × format 短轴尺寸
```

片夹实物和扫描设置会有小偏差，因此它们是窄范围先验，不是精密校准尺。对本项目而言，相机片门
尺寸偏差与扫描比例偏差不可区分，也无需区分；可直接观测的是 source 共享的像素尺寸。

同一 source 的所有照片共享 `W`、`H` 与扫描尺度，不允许逐张尺寸。设计兼容范围固定为：

```text
W：format 名义宽度的 ±1.25%
H：format 名义高度的 ±0.40%
片夹物理 extent：±3.5%
```

不建立 `W_effective_px`、`H_effective_px` 或逐张尺寸；`W` 与 `H` 就是当前 source 共享的可行
窄范围。一组兼容的完整 opposite-edge pair 可以验证并收紧该范围，多组兼容测量取共同交集；
直接测量互相冲突时保持 unresolved，不能平均，也不能分别赋给不同照片。双 lane 共享扫描尺度；
每个 lane 分别拥有方向、中心线、相位、`G_source`、局部异常和可见范围。

## 3. 片条几何

每个 lane 只有一个共同主方向和一条连续中心线。胶片卷曲、片夹压力与扫描形变可以造成小而连续
的偏离，但照片不能逐张横向跳动、独立旋转或变成自由四边形。物理照片仍是共享尺寸的矩形：

- `top/bottom` 属于共同长边方向族；
- `start/end` 接近该方向的法线；
- 对边近似平行，两方向近似正交；
- 缺边只能由共享尺寸、中心线、顺序和相邻关系推导，不能让四角迎合画面内容。

Deskew 使用 lane 的共同方向，只要求输出在视觉上平直，不追逐每张照片的内部线条。

Full 与 partial 片条都可以从画布长轴的任意位置开始；模式、source 或片夹边缘都不能证明第一张
或最后一张照片的位置。Expected position 只决定先搜索哪里，不能创建照片位置。Grid phase 与
可见照片边缘必须分开。

## 4. 正常间隙与局部异常

间隙分成三个不同 authority：

```text
G_format  format 级搜索先验
G_source  当前 lane 的正常间隙中心
g[i]      slot i 与 i+1 的实际局部间隙
```

无异常证据时默认 `g[i] = G_source`；轻微机械波动留在测量兼容区间内，不为每一格建立独立
delta。相邻关系为：

```text
start[i+1] = start[i] + W + G_source + delta[i]
```

已证明的局部异常只在该 adjacency 改变一次相位；后续照片整体平移，后续间隙恢复正常，除非
另有异常证据。固定 pitch 一路复制和每个 slot 完全自由移动都不符合物理关系。

间隙 authority 固定为：

```text
完成角色绑定的直接局部边缘或 separator
> 当前 lane 已建立的 G_source
> G_format 搜索先验
```

直接观察必须先通过方向、W/H、ordinal、短轴连续性和内容否决检查；孤立的照片内部线不能仅凭
强度推翻正常模板。可靠直接证据与 `G_source` 冲突时，该处成为异常证据；多组同等级直接证据
互相冲突时保持 unresolved，不能平均。

### 4.1 建立 `G_source`

一段 pitch 只能提出 `G_source`，不能证明它是正常间隙。最低成立条件是三条按 ordinal 排列的
同类边形成两段相互兼容的独立 pitch：

```text
P1 = edge[2] - edge[1]
P2 = edge[3] - edge[2]
G_source = P_source - W
```

- 0 段：只有 `G_format` 搜索先验；
- 1 段：`G_source proposal`；
- 2 段一致：最低限度建立 `G_source`；
- 3 段以上：使用全部兼容证据共同收紧；
- 证据不兼容：保持 unresolved，不平均，也不选择更接近名义值的一段。

“兼容”由各段 pitch 的测量可行区间是否存在共同交集决定，不另设随意百分比。120 partial 若
只有一段 pitch，`G_source` 始终 unresolved；不得从其它样片建立先验。

### 4.2 缺失 separator

当 `G_source` 已建立且正常链没有被否决时，缺失 separator 使用正常间隙模板补全。模板位置可以
用于继续搜索、放置与默认裁切，但必须标记为 inferred，不能报告成直接观测。

只有以下证据能够打开异常解释：

- 直接几何证明接触或叠片；
- 直接观测到真实大间隙；
- 可靠内容否决预计的正常 separator；
- 两侧锚点的总间隙与正常总量不相容；
- `G_source` 未建立，正常分配没有 authority。

不能仅因数学上可能就构造“接触 + 大间隙”等组合。正常链已被否决而异常具体位置仍无法区分时，
`separator chain` 才保持 unresolved。

### 4.3 接触、叠片与大间隙

```text
g[i] = start[i+1] - end[i]
```

- `g[i]` 的可行区间完全大于零：存在 separator；
- `g[i]` 的可行区间包含零：接触候选或接触附近的不确定关系；
- `g[i]` 的可行区间完全小于零：叠片，最小物理界为 `-W`；
- 很大的 `g[i]`：大间隙。

这些情况都不改变 count、ordinal 或单向顺序。大间隙不能自动增加 slot，叠片不能合并 slot。
叠片时两张照片各自保持完整 `W`，重叠 source pixels 合法地同时出现在两张输出中；重叠量不消耗
5% budget。单条接触线可以同时承担 `end[i]` 与 `start[i+1]`，但底层仍是一份观察；它不能单独
证明接触，还需与共享 W、两侧锚点或整体跨度相容。

局部异常没有统一的允许间隙常数；相机故障、老化和装片状态可以造成接触、叠片或很大空隙，
是否成立只由实际证据决定。若已观察到相邻异常两侧的锚点，可直接约束：

```text
g[i] = end[i+1] - start[i] - 2W
```

叠片仍保持 `start[i] < start[i+1] < end[i] < end[i+1]` 的单向关系。

## 5. 边界证据语义

每条预期边界只有三种状态：

- `support`：像素变化与边界角色、方向、位置和物理链相容；
- `contradiction`：可靠证据证明候选边界或矩形不能成立；
- `unobservable`：空白、遮挡、截断、叠片或内容使边界不可观察。

没有检测到边缘不等于反对边界；强烈的画面线、灰尘、片夹或胶片边也不自动成为照片边界。
一个 slot 即使四边都不完整可见，仍由 count、共享尺寸和物理序列保留。

内容占用层与边缘外观层必须分开。内容观察先在 source 坐标中独立建立，不能随候选位置改变：

- separator 的黑度、低纹理和连贯性可以成为 band 的正向观察质量；
- 内容层只提供负向否决，永远不提供正票；
- 没有内容不能证明边界，也不能证明 slot 是空片；
- 内容必须可靠、连续并且跨过候选本应保留的边界，才能否决候选。

## 6. `top/bottom` 与中心线

`H_nominal_px` 从 format 与片夹画布开始就是共享窄范围。Detector 只在该范围决定的两个短轴
走廊中寻找局部连续边缘段，不先要求完整 `top/bottom` 才建立高度。

```text
观察到 top    → 用共享 H 预测 bottom 与中心线
观察到 bottom → 用共享 H 预测 top 与中心线
同时观察两边  → 验证并收紧共享 H
```

实际看到的边缘是 observed evidence；由共享 H 推出的另一边只是 template inference。两者必须
在 report 中分开，推导边不能反过来冒充第二份观察。

项目不需要区分照片边缘、胶片边缘或片夹可见开口。只要某条边界外没有可恢复的照片内容，它们
对裁切等价：

- 长距离连续存在，更像片夹、胶片或可见内容外边界；
- 在多个纵向区域重复落入同一走廊，更像照片真实边缘；
- 只在一张照片局部出现，更像照片内部横线，只能成为局部候选。

局部连续段是最小观察单位。两个物理分离的纵向区域是建立 source/lane 边缘族的最低重复证据；
一条贯穿长图的连续线可以按前、中、后等空间分离区域提供有限支持，不能按像素无限计票。

`top` 与 `bottom` 分别聚合，再通过共享 H、共同方向和连续中心线配对。一处可靠、连续的跨线
内容就足以否决候选，不要求整条线多数反对；没有跨线内容仍然只是不反对。最终选择能放置共享
H 的 format 矩形、未被外侧内容否决的最小完整安全 pair；不得把多个候选取 union，也不在选择
后重复添加 guard。片夹遮挡或 source 边界以外的内容不可恢复，不要求 padding。

## 7. `start/end` 与 separator chain

`W_nominal_px` 同样从 format 与片夹画布开始就是共享窄范围，不再建立 `W_effective_px`。主要
检测对象不是孤立线，而是相邻照片之间的 separator band：

```text
band[i] = [L[i], R[i]]
L[i] = end[i]
R[i] = start[i+1]
g[i] = R[i] - L[i]
```

完整 separator 是一段跨短轴连贯、黑暗、低纹理并与共同方向相容的材料区域，必须保留左右两边
及宽度。它是一份像素观察，在完成 chain role binding 前不拥有 ordinal。相邻两条 separator
还能直接验证中间照片的共享宽度：

```text
L[i+1] - R[i] = W
```

Edge pair、局部 remeasurement 与 Grid 都只能完善同一 band/chain，不建立平行 detector。
`Grid` 是若干 separator 共同支持 count、W、ordinal、phase 与局部 gap 序列的结构组织，不是
画布对齐的固定 pitch，也不拥有最终真相。

Band 只有通过 W、count、顺序和整条 chain 才绑定 ordinal：

- count=2 时，一个完整且角色唯一的 separator 足以放置两张 format 框；
- count=3 时，两条有效 separator 足以形成完整 grid；
- 一般情况下，全部 `count-1` 条按序 separator 唯一绑定 chain；
- 一条直接外边缘加已建立的 W 与 `G_source` 可以锚定整条正常 chain；只有 `G_format` 或
  `G_source` unresolved 时通常不够。

首张 start 或末张 end 可见时，用该边与共享 W 放置照片；被片夹遮挡或超出扫描范围时，物理框
可以延伸到 source 外，但输出只保护 source/lane 中可恢复的像素。

连续黑区可能同时包含 separator、空白曝光格和下一条 separator。无论像素上多么相似，都必须
按用户 count 保留全部 `W` 宽 slot，不能把整片黑区合并为一个大间隙。

对 start/end，候选外有内容可能只是邻片，不能据此否决。只有属于当前 slot 的可靠内容连续穿过
候选边界，或内容穿过预计的正 separator core，才能否决正常解释。在接触或叠片中，跨边内容
是中性或预期现象，不能单独产生边界坐标。

Start/end 与 top/bottom 使用同一个最小安全原则：先放置共享 W 的 format 框，再选择未切入当前
slot 可靠内容的最小边界区间。落选位置不能取 union，模板推导边也不能报告为直接检测。

## 8. 有界检测与完整链投票

Producer 必须 template-first 且工作量有界：一次 TIFF decode，registered 的多分段一维 profile，
在 format 预计走廊内产生少量完整链。保留历史版本中有效的能力：

- 多分段一维 separator/cross profile；
- 黑暗、低纹理的 separator material；
- opposite-polarity edge pair；
- 以共享 W 和局部 gap 重述的 Grid consensus；
- registered 的有界局部 remeasurement；
- basic 优先，仅对已登记的结构缺口执行 enhanced；
- observed 与 inferred 严格分开。

不得恢复 separator center 直接裁切、固定 pitch 全链复制、Grid override、confidence 总分 authority、
固定 bleed、format 特例阈值、content bbox 放置、canvas 平均 gap、通用 DP、top-K、候选笛卡尔积、
逐帧尺寸或无界全图 evidence。

Producer 的结构上界保持线性或有限乘积：

```text
phase_vote_count
  ≤ profile_run_count × ordered_role_count × component_count

template_role_lookup_count
  ≤ template_group_count × ordered_role_count

template_role_match_count
  ≤ phase_vote_count

local_relation_evaluation_count
  ≤ complete_chain_count × (slot_count - 1)
```

每个 registered transition 只作固定次数投影或匹配。单输入临时内存上限保持：

```text
10 × source_pixels + 32 MiB
```

候选首先通过硬物理过滤：format/count、共享 W/H、方向、ordinal、source/lane authority、内容
否决和异常依据。之后比较的是完整 chain，不允许每个 slot 各自选择最高分。

### 8.1 证据等级

投票不是任意加权总分。比较顺序固定为：

1. 直接物理证据；
2. 完整 chain 与正常物理关系；
3. separator 外观质量；
4. expected position、片夹布局等弱先验。

低等级证据不能靠数量推翻高等级证据；只有同等级才比较独立单位。弱先验只能在 sampling 等价
或近乎相同的位置间选择代表中心，不能解决两个不同 format 框的同等级竞争。

### 8.2 独立证据单位

- 一个完整 separator band 是一份观察，左右边不重复计票；
- 两个空间分离的 separator 是两个单位；
- separator 之间符合 W 是结构兼容性，不是新增像素票；
- complete opposite-edge pair 是一份强结构证据，不伪装成两个空间独立单位；
- 一条长 top/bottom 线可按空间分离区域提供有限支持，更多区域只增强稳定性；
- 一条外边缘是一份观察；模板推导出的所有位置没有直接票；
- 同一原始边的多个拟合、阈值版本或派生角色只能计一次；
- 已建立的 `G_source` 是 source 模型支持，不能对每个补全 separator 重复计票；
- 内容只否决，不提供正票；接触线承担两个角色仍只有一份观察。

count=2 的一条完整 role-bound separator，或一个直接外边缘加可靠 `G_source`，都可能以一份观察
唯一建立完整 chain；不得机械规定所有 source 必须“两票”。

### 8.3 明显胜出

候选 A 只有在以下条件同时成立时才明显胜出：

- A 与竞争者都先经过硬物理过滤；
- A 在更高证据等级占优，或在同等级拥有更多独立物理单位；
- 竞争者没有 A 无法解释的同等级直接证据；
- A 的胜出不只来自黑度、expected position 或微小总分差；
- A 能形成完整 chain 和安全输出；其中异常均有证据。

多个合法候选不自动进入 review；符合上述规则的高概率胜出者可以自动批准。若两个非嵌套位置
同等级且无法区分，则 `placement unresolved`，不能平均、任选或扩大为巨型 union。

## 9. FormatPlacement 与 `SafeCropEnvelope`

Detector 先依据 format 的共享 W/H、lane 方向和中心线生成固定尺寸 `R_format`，再以胜出 chain
放置每个 slot。正常间隙、接触、叠片或大间隙只改变框的位置，不改变框的尺寸。

所谓“选择更小的安全 top/bottom 或 start/end”，比较的是同一固定 format 框的安全放置与可见
包络，不是缩小 W/H。只有 source/lane 可见 authority 的真实截断可以让输出少于物理框；被遮挡
或未扫描的部分不属于可恢复内容。

```text
SafeCropEnvelope
  = 胜出 FormatPlacement
  + 该 placement 自身的边界测量不确定区间
  ∩ source/lane 可见 authority
```

边界不确定区间直接向外消费一次：`start/top` 取最小值，`end/bottom` 取最大值。它已经是保护，
不得再增加固定或最小 guard。连续坐标到整数像素的向外取整属于坐标正确性，不是 padding。

内容证据可以否决位置，不能拖动或自由放大 format 框去包围 content bbox。落选候选不得进入
`SafeCropEnvelope`。若存在多个安全边界描述，选择能够完整保护胜出位置且按包含关系最小的矩形，
不能从不同候选拼接四边，也不能按面积拍脑袋选择。

若接触与极小叠片等解释只形成同一个 placement 可行区间，并得到相同或近乎相同的 sampling，
它们属于胜出位置自身的测量不确定性；只有产生不同 format 框位置时，才是结构性竞争候选。

片夹、lane 或 source 遮挡外没有可恢复内容；与可见 authority 求交不算内切，也不补黑边。

### 9.1 Direct-use budget

Budget 以已放置的 format 框为基准，四边分别为闭区间上限：

```text
start 外扩  ≤ 5% W
end 外扩    ≤ 5% W
top 外扩    ≤ 3% H
bottom 外扩 ≤ 3% H
```

它不是搜索走廊、默认 padding 或候选生成条件，四边不能相互借用额度。刚好达到上限通过，任意
正超量失败。

## 10. Gate 与终态

Detection 产生候选，投票选择胜出 chain；Gate 不重新选位置。

`CandidateGate` 只记录 typed facts，分别检查：

### 选择是否可信

- 是否存在明显胜出的完整 chain；
- 胜出是否来自独立物理证据；
- 是否存在无法解释的同等级竞争证据；
- 是否只靠弱先验或微小分差胜出；
- 接触、叠片、大间隙或局部相位跳变是否有证据。

### 输出是否安全

- 每个 ordinal 是否有完整 format placement；
- `SafeCropEnvelope` 是否只保护胜出 placement；
- 是否存在可靠内容内切；
- source/lane 可见 authority 是否成立；
- 每边是否通过 5%/3%；
- deskew、坐标变换和 sampling 是否安全成立。

缺少某条直接边本身不是 review 理由。一个可靠锚点、已建立的 `G_source`、完整正常 chain、没有
同等级竞争者且输出安全时，可以自动批准。`G_source unresolved` 也只在缺失位置依赖它时阻断。

`DecisionGate` 独占 final status 与 reasons：

- `approved_auto`：选择可信且全部输出安全；
- `needs_review`：没有合法位置、没有明显胜出者、可靠内容冲突、异常位置 unresolved、超过
  5%/3%、source/lane authority 不成立或 transform 不成立。

`runtime_error` 是运行终态，不属于 `DecisionGate`。任一 slot 不安全时整个 source
`needs_review`，普通运行不写该 source 的正式照片。

## 11. Report、Debug Analysis 与复用

Current report 必须让用户看出：

- 胜出 chain 与每个 slot 的 format placement；
- 独立观察 ledger 与证据等级；
- observed、template inferred 和 unresolved 的区别；
- 竞争 chain 有什么证据、为何被淘汰或为何阻断批准；
- `SafeCropEnvelope`、逐边 5%/3% 和 Gate reasons。

不能只报告总分。Debug Analysis 只读取 runtime/report facts，展示 detected/selected
TOP/BOTTOM、detected/selected START/END、胜出 chain、最终 safety/output 和 source-atomic
decision；它不得重算检测、几何或 budget。显示层只做 source-to-display mapping，以固定
`1653 px` 宽度和 source aspect 自适应高度展示完整片条，不改变 source-coordinate detection、
crop、budget 或 deskew。

`--debug-analysis` 执行同一 detection、投票、Gate 与 Finalization，但只写诊断和报告类文件，
不写正式 TIFF 或 review copy。后续普通运行只在 current schema、完整性、版本、source runtime
identity、TIFF profile、完整配置和 resolved layout 全部一致时复用 Finalization；否则重新检测。
正式 TIFF 始终从原图 sampling 并复读验证。

## 12. TIFF、运行与输出事务

正式输入限于单页 unsigned 16-bit、RGB 三通道、contiguous planar TIFF；压缩只接受 `NONE`、
`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD`。Orientation 1–8 在 decode boundary 转为
canonical coordinates。域外输入为 `runtime_error`，不静默转换；正式输出写 `Orientation=1`。

`tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与
sampling，Pillow 只在显式 Debug Analysis 时延迟导入。输出关闭后复读 pixels、结构、ICC、
resolution、受支持 metadata、压缩与 Orientation。

X5 Crop 是唯一并发 owner。生产默认 `--jobs 1`、上限 3；数值库内部线程固定为 1。Producer
只保留一维 profiles、有限 observations/chains、typed geometry 与分块 sampling buffer，不增加
通用 DP、top-K、多份全分辨率梯度或完整 sampling coordinate field。

正式照片平铺在 target 根部。新结果在同父目录 staging 完整生成并复读后，通过 lock、journal
和 rename 原子发布；只有 owner marker、current manifest 与 inventory 全部匹配的旧 target 才能
替换。状态歧义保留 target/new/old/journal，绝不猜测删除。未验证文件系统必须明确接受
best-effort，且不能绕过路径、链接、锁、同文件系统、磁盘空间或 rename 硬失败。

普通运行退出码为：`0` 完整发布且无 runtime error，`1` 已发布但含 runtime error 或全部输入
失败而未发布，`2` 输入或 preflight 失败，`3` 事务、发布或恢复失败。全部 source 都是
`runtime_error` 时不发布空结果，旧 target 保持不动。

## 13. 验证与发布边界

`tools/verify` 是唯一验证入口：

```text
staged | full | accuracy | diagnostic | performance |
platform | platform-check | platform-package | pre-push
```

- 九张用户确认黄金各运行一项，共九项：full 使用固定 count，partial 使用 cohort 中明确确认的
  count。七项 nominal 必须安全自动批准，两项 challenge 允许安全 review；不再运行 auto 副本。
- Accuracy、diagnostic、performance 与 platform cohort 的 partial 记录都必须携带明确 count；
  工具不得从片夹容量、文件名或像素推导。Full/partial 标签必须按 `count == full_count` 或
  `count < full_count` 生成，不能继承目录名或历史标签。
- 111-source diagnostic 只验证 crash、hang、工作量、schema、authority、内存和 TIFF 工程合同，
  不产生 accuracy verdict。
- 24-source performance 使用完整用户路径，正式 mean 上限为 5 秒；profiling 在 Gate 外。
- Debug Analysis 必须显示真实 report facts，不能成为装饰性 mock-up。
- 不增加样片规则、whitelist、format denylist 或按当前输出自动晋升黄金。
- 投票的精确全局 margin 只能用用户确认黄金统一验证，不能按 format 或单个样片调参。
- `full` 通过不等于 accuracy、performance 或平台已经通过。
- 只有 accuracy、performance、依赖、TIFF、文件系统和目标平台实机 receipt 全部绑定同一
  release commit，才可创建 RC、tag、GitHub Release 或公开 ZIP。

## 14. 源码 owner

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | format 物理尺寸、W/H tolerance 与 gap 先验 |
| `x5crop/configuration/` | matching-holder `full_count`、partial count、片夹容量、ScanCanvas 与 runtime configuration |
| `x5crop/io/` | TIFF domain、Orientation、metadata 与 readback |
| `x5crop/detection/source_core.py` | source/lane 可见 authority |
| `x5crop/detection/photo_geometry/measurement.py` | registered transitions、separator material、boundary intervals 与 candidate-independent content veto observations |
| `x5crop/detection/photo_geometry/template_profiles.py` | 一维 profiles、separator bands、roles 与 bounded grouping |
| `x5crop/detection/photo_geometry/source_geometry.py` | 共享 W/H、方向、中心线与 `G_source` |
| `x5crop/detection/photo_geometry/template_model.py` | format template、local gap、完整 chain 与 vote ledger |
| `x5crop/detection/photo_geometry/template_first.py` | bounded producer 与 chain selection orchestration |
| `x5crop/detection/photo_geometry/output.py` | selected placement、`SafeCropEnvelope` 与 direct-use assessment |
| `x5crop/geometry/convex.py` | 唯一 convex footprint primitives |
| `x5crop/detection/candidate/` | `CandidateGate` typed facts |
| `x5crop/detection/decision/` | final status 与 reason mapping |
| `x5crop/detection/final/` | approved geometry exposure |
| `x5crop/export/` | lane-safe sampling、TIFF write 与 readback |
| `x5crop/report/` | current report schema、read model 与复用 validation |
| `x5crop/runtime/` | invocation、terminal、report reuse、budget 与 manifest |
| `x5crop/output/` | portable name、safe tree、filesystem、lock、journal 与 publication |
| `x5crop/debug/` | current facts 的只读可视化 |
| `tools/verify` | 唯一 tracked verifier 入口 |
| `tools/regression/` | SHA-bound accuracy、diagnostic 与 performance |
| `tools/release/` | standalone 与发布 manifest |
