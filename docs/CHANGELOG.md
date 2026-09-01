# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前目标与风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只有一条 current-only runtime；历史 mode、schema、fallback 与平行 detector 只保存在 Git history。

V5 的定位明确为：以 v4.2.8 已在真实样片中证明有效的 Grid、separator、outer/cross、deskew、候选无关
复用与 TIFF 输出经验为能力基础，在 current-only 的 typed evidence、uncertainty、Gate、Debug 和黄金验收
下重建其物理权限。旧机制不能因名称或来源被直接整体删除；必须先把有效事实迁入 observation、anchor、
local correction、risk feature、veto、protection 或 selection 的唯一 owner，再删除旧式自证、任意评分、
重试 mutation 与兼容路径。

发布验收现在明确分为两层：检测能力要求当前 development nominal 全部安全 `approved_auto` 且全部角色
`unsafe_approved_auto = 0`，challenge 的安全 auto 或安全 review 都合格；工程能力另行要求正式性能、
TIFF/metadata、安装、三目标平台、打包与 Hook/CI。当前没有 sealed cohort，以及黄金未覆盖 `xpan`、
`120-645`、`135-dual`，都只作为未见/真实样片覆盖事实披露，不阻断首版发布，也不改变统一 Runtime 合同。

### 产品行为

- 用户提供 format，并确认匹配片夹的默认 count 或显式 count；count 包含中间空白曝光格。Runtime 不猜
  format、照片数或 blank，也没有 full/partial mode。`135-dual` 只有 12=6+6 可自动处理。
- Detector 改为有界 fixed-template-first：从整条片带建立 coarse support，再在 format/count 编译出的
  outer、separator 与 top/bottom 邻域一次测量。Format 设计 W/H、source-level aperture 与 typed evidence
  决定 phase、pitch、cross 和 ordinal；每个唯一绑定的直接 separator 可以约束自己的 local advance，
  全部变化仍只作一次 O(count) 传播。像素强度、片夹中心或样片规则不能替代 authority。
- Separator material 在同一个 registered measurement owner 内完整支持 `dark | light` polarity。相邻
  反向 edge 必须在同一高度区域同时满足 oriented tone contrast 与 core texture 合同；局部两区域 support
  不能冒充 source-wide role authority，完整三区域反证产生 typed `separator_material_conflict`。超出 normal
  gap 上界的 material 仍保留为事实，但不能创造 phase、ordinal 或直接角色权限。
- 已登记 sequence baseline 现在同时产生两类三区域 aggregate：局部 weak gradient/tone/texture 可以
  `aggregate_union` 加强唯一 short direct edge；宽缓 material 使用 `0.25/0.50 mm` 双尺度 tone、texture、
  uniformity、polarity 与 background-side 一致性。宽缓单边只能匹配或保留为 standalone，不增加
  direct-role 权限；只有完整 END/material/START pair 才能进入 placement 并约束 local advance。
  `aggregate_edge_support.py` 统一拥有解析、去重与 pair 投影；跨尺度、跨高度、角色或多解冲突保持 typed
  unavailable/contradiction。任一 edge 已属于 supported canonical separator 时，宽缓 pair 不能用另一侧
  重新解释该 edge；同一物理 pair 也不重复计票。该能力不扩大 query、halo、
  TIFF 读取，不建立 enhanced detector、第二 geometry 或 score。
- Coarse short-axis observation 现在把 5 条 sharp trace 与 9 条 broad material trace 合并为一个
  registered union 并只读取一次。Sharp 或 broad 都可建立 role-free enclosing pair；broad 必须具有正确
  outward background、共同 polarity、三区域 source-spanning 支持、相容方向和 `H < span <= 1.1H`。
  两者等价时保留 sharp native coordinate，broad 只作相关 validation；不等价时产生 typed contradiction，
  不按分数选解。单侧、源边界不可观察、支持不足或 span 不相容都不授予权限；长轴 broad standalone edge
  仍只作 observation。Resolution basis/failure 进入 Development report、gold analysis 与 Debug。
- Selected placement 现在由 `AdjacencyContinuityObservation` 为每个 adjacency 建立唯一 typed ledger。
  唯一正序 separator band 始终保存 direct gap；gap 异常或需要约束未观察 suffix role 时形成 measured
  `SeparatorRelation`，保存两侧 native observation 与直接 signed-gap interval。共享 W/pitch 改变时只重算
  相关 `delta = signed_gap - (pitch - W)` 和 derived `normal|wide|narrow`，不能把真实 gap 拉回默认值。
  完整 corridor 但无反证只保留 unobserved nominal Grid，
  不能冒充直接 separator；material unavailable、band/角色冲突、跨零 gap、未登记反序 edge pair 与 coverage
  不完整分别保留独立状态。
  普通 adjacency 的歧义和拓扑反证通过专用 Gate reason 安全 review。该映射只复用已登记事实，不新增
  TIFF 读取、低梯度 detector 或 winner-specific query。
- `AdjacencyRelation` 现在显式区分 `SeparatorRelation`、`ContactRelation` 与 `OverlapRelation`。Candidate-independent
  `ContactEdgeObservation` 只接受具有独立坐标权限、未被正 separator material 拥有且没有另一条重叠
  authoritative identity 的物理边；phase solver 把同一 edge 原子绑定为前一 Frame END 与后一 Frame
  START，并以 `delta = W - pitch` 进入原有 O(count) prefix。走廊不完整、多个 physical identity 或多种
  ordinal 映射保持 typed review；反序边不能冒充 Contact。
  Candidate-independent `OverlapEdgePairObservation` 只登记空间相邻、角色相反、physical identity 独立且
  具有直接坐标权限的反序 END/START，不读取新像素或携带 ordinal。Phase solver 在有限合法 adjacency 中
  绑定同一 pair；完整 coverage、无 separator 竞争且严格负 signed gap 才形成 `OverlapRelation`，并以
  `delta = W - pitch + signed_gap` 进入同一 prefix。Contact/Overlap 相邻 Frame 不参加 source W 独立支撑。
- 已证明 Contact/Overlap 的输出只在前一 Frame END 与后一 Frame START 增加一份同状态 sequence base bleed 作为
  `topology_protection`，并继续消耗原有每侧 5% 总预算；其它边不变，预算或 containment 不成立时 review。
  Overlap 只允许 relation 对应的两个物理 Frame polygon 重叠；其它重叠仍为 `fixed_template_mismatch`。短轴
  evidence 在 overlap 中点分区，避免共享区域重复计票，输出 polygon 不被修改。
  Report/Debug 分开保存 relation identity、基础 bleed、topology protection、uncertainty 与 residual。
- Direct separator refit 只能让同一 adjacency 的 native endpoint 调整局部关系；原 phase anchor 保持原
  权限，新追加 endpoint 只能作为 `LOCAL_REFINEMENT`。重拟合前的全局 phase binding 与 Contact/Overlap
  必要角色冻结为 `phase_anchor_authority_ceiling`；新增
  separator endpoint 不能创造 phase authority、constraint rank 或无关 role binding。Projection 以
  `direct_separator_refit/direct_separator_gap` 保存依据，并核对 immutable relation evidence identity；越过
  ceiling 或改变 template/ordinal/evidence/role mapping 时 typed review。完整路径仍为 O(count)、不新增
  TIFF query，fit pass 上界为 6。
- 校准 Grid 现在正式作为唯一 placement 的 primary generative model。Format/count 提供黄金集校准且带
  完整区间的 W/H/pitch 与 normal adjacency；至少一个获得坐标权限的 absolute anchor 将它放入 TIFF。
  Direct rank 3 仍是更强的完全直接闭合路径，但不再是 Grid 的唯一使用权限。某张 Frame 即使 START/END
  都未直接观察，只要校准 prior、anchor、逐 adjacency 完整 coverage 和无 typed 反证全部成立，仍可由
  同一 Grid 生成；`unobserved_frame_ordinals` 只作 provenance，不再是硬失败。全部 W/pitch/scale/local
  关系以联合可行状态传播到 output，最终仍由 source containment、content veto 和每侧 5% 最坏包络决定
  auto/review。无 anchor、coverage 不完整、直接反证、校准包络冲突或预算超限分别保留自己的 typed
  failure；没有 fallback、第二 Grid、样片特例或零不确定性 nominal 值。
- Selected Grid 在 local relation 或 source-W 阶段追加 late binding 后，会由同一
  `PhaseCandidateAuthorityProjection` 再执行一次有界权限投影。无坐标权限的弱线只有在完整位置区间与
  对应 Grid role 的完整包络相交时才能降为 validation provenance；不相交产生
  `calibrated_nominal_grid_conflict`。仍有权限的 `LOCAL_REFINEMENT` 在 direct-rank 重拟合后保留 native
  binding，不能因不增加 global rank 而丢失。Report/Debug 保存 selected projection、投影 role、Grid solve
  与 typed conflict；不新增 TIFF query、候选、detector 或 fallback。
- Report revision 更新为 `x5crop_v5_template_report_40`，不保留旧 schema 兼容路径。当前 110 个
  development task 的完整机制验收无分析错误：15 个安全 auto、95 个安全 review、
  `unsafe_approved_auto = 0`；14 个 challenge 均安全 review。Review candidate 的黄金偏差只作机制诊断，
  不再把未输出候选误写成 challenge 终态失败；approved output 仍必须完整通过黄金几何。本阶段解除
  12 个 `direct_role_binding_authority_unavailable`：S084、S092 新增安全 auto；S079、S094 因此前遗漏的
  authorized native binding 重新参与而暴露 typed conflict，安全回到 review，故 nominal 自动覆盖净值
  保持 15，不以丢弃反证或放宽 Gate 换数量。
- 对 96 个 nominal 的同源机制对照显示：v4.2.8 有 80 个 auto，但其中 70 个是黄金危险自动裁切；只有
  11 个 v4 geometry 安全。v4 安全而 V5 Review 的 9 个 task 是下一步能力迁移样本，当前分别落在
  aspect/cross、fixed-template、direct-role、Grid conflict、continuity、phase ambiguity 与 output budget
  等 typed root；不能据此恢复旧终判。当前 V5 有 17 个安全 candidate，其中没有“双方 geometry 都安全但
  仅因 Grid direct-rank 权限而 Review”的遗留项，说明本阶段已把默认生成权限与后续安全阻断分开。
- 直接观察到的 start/end 在最终 placement 中保留 native coordinate 与完整 interval；Grid 只补齐缺失
  角色。同一连续 placement 的互补 endpoint evidence 合并为联合可行状态，不伪造 runner。唯一 placement
  中至少两张完整直接 Frame 可闭合 source W；当每个缺失 Frame 仍有一侧直接边缘时，同一份相关 W 可补
  多条 opposite。若某个双侧未绑定 Frame 的完整物理 W 走廊内已经存在多组 registered native edge，
  独立 source W 还可在固定 placement 上追加一次有界 lookup；只有它唯一留下一个各自具有直接坐标权限的
  pair 时才绑定。双侧未绑定 Frame 若只有一侧存在唯一 intrinsic edge、另一侧完整 corridor 无候选，也可
  保留该 native coordinate 并由同一相关 W 推导 opposite；该路径可作用于 calibrated Grid selected fit，
  但 Grid/format W 自身不能授权。没有合格 pair/单侧 edge、多组解释或任一 opposite 候选继续 typed
  review。缺失 separator 只有在 direct rank-3，或校准 Grid 已有 absolute anchor 时，才能继续检查对应
  adjacency 的完整不确定性走廊；走廊被已执行窗口逐 trace 覆盖且没有局部反证，才按
  `local_delta = 0` 补齐。不再用 edge 数、连续缺失数或全局 query-complete 布尔值代替证明。候选无关
  sequence 窗口按左右 holder 端分别投影完整且相关的 `W/pitch` 状态，覆盖
  传播走廊但不重复相加互斥极值；理论 core 合并后按中点把 coarse support 的每个整数像素中心恰好分给
  一个窗口，measurement halo 可重叠而 transition ownership 无重叠、无缺口。覆盖以真实可测的离散坐标
  判断，不再把相邻像素中心之间的亚像素距离误报为缺口；扩大 ownership 不增加 TIFF 读取或 query。
  direct rank-3 推断路径还要求首尾输出 Frame 各至少绑定一条直接长轴角色；校准 Grid 路径则由 absolute
  anchor 和完整联合包络承担外侧位置，不从片夹中心创造 phase。任一已选直接
  START/END 只有获得 source-wide edge、跨高度联合或同一 separator pair 的直接坐标权限后，才能进入
  最终 placement；两条局部 edge 不能仅因间距与 catalog/source W 相容就互相授权。独立 source W 只推导
  真正缺失的 opposite，不覆盖已经授权的 native coordinate。无权 `LOCAL_REFINEMENT` 只有在同 Frame
  opposite 已授权、W 完全来自至少两张其它双边授权 Frame、且 W 走廊中只有该 observation 相容时，才让位
  于完整相关 W；弱线仅保留为 validation provenance，不能收窄 W、增加 rank 或改变 phase。其它局部孤立
  edge 保留为观察并产生 typed review，不能反向参与 lattice 自证。两高度 normal separator 只有在一侧已具完整直接权限时，才可向
  同一 adjacency 的另一侧传递一次 `partial_height_separator_pair` 权限；传递不能级联，且最终必须使用
  两侧直接的 `aperture_pair` 短轴域。Enclosing support 或单侧推断 aperture 产生 typed
  `direct_role_aperture_domain_unavailable`，不能把两个不完整机制叠加成批准。
- Source W 不再由 provisional/base phase 预先校准后重编译 template，也不再形成第二次 pitch/phase 搜索。
  离散与 local competition 先在没有 source W evidence 的同一候选空间中结束；只有唯一 selected candidate、
  pre-W joint rank 至少为 2、必要 adjacency coverage 完整且没有直接反证时，至少两张独立
  完整 Frame 才建立 typed `SourceFrameWidthAuthority`。它只收紧 selected fit 的连续 W，并在最终阶段
  重新评估 rank、direct-role/outer authority 与相关 opposite inference；不能删除离散 runner、改变
  ordinal/winner、重编译 template 或回写先前候选选择。普通 local refinement 使用完整 format W，不能让
  fitted Grid W 过滤自己的反证；只有 typed independent source W 能排除与同 Frame opposite role 物理不相容
  的 material alternative。未支持与矛盾状态均进入 report/Debug，不建立旧 API、fallback 或并行 runtime。
- Rank 3 直接坐标现在在 phase、W、pitch 与 `pitch-W` 的联合硬区间内执行有界最小二乘。无约束解轻微
  越界时不再把 W/pitch 整体退回 catalog 中心却保留原 phase；报告以
  `direct_least_squares | bounded_direct_least_squares | template_interval_center` 记录连续参数依据。
  该求解不扩张物理区间、不覆盖 direct native coordinate，也不选择离散 runner；受约束后暴露出的另一
  合法解释仍安全进入 review。
- 每个 bounded phase candidate 现在会在离散竞争前对称执行 direct-role authority projection。
  `contradicted` 直接终止；`unavailable` binding 只有在删除后每张 Frame 仍保留一侧直接坐标、相关
  evidence-group 去重后的 `(phase,W,pitch)` rank 仍为 3、且同一 template/ordinal/local topology 可以
  有界重拟合时才投影出去。全部 eligible candidate 重新 canonicalize 并竞争，真实双解仍保持
  `discrete_phase_ambiguous`；弱线只保留为 provenance，不能拥有 phase、收窄 W 或隐藏 runner。
  完全未观察 Frame 或 direct rank 0–2 会离开纯 direct projection，并只在第 7.2 节的校准 Grid 合同完整
  成立时继续；material contradiction 与 refit/identity failure 仍是 typed terminal outcome。该机制复用
  registered evidence，不增加 TIFF 读取或第二 detector。
- `135`、`half`、`120-66`、`120-67` 使用同一 source-level 方法校准 nominal pitch interval，并与 W、
  source scale 保持相关；`xpan`、`120-645`、`135-dual` 没有合格真实 calibration 时明确 unavailable，
  不跨 format 外推。Calibration identity、anchor、coverage、未观察 Frame、work receipt 和 root failure
  全部进入 report/Debug。
- Format W/H compatibility 由一个 current-only 混合物理合同统一计算：
  `guard_W=max(0.95 mm, 2.4%W)`、`guard_H=max(0.70 mm, 1.8%H)`。参数来自 105 个合格黄金 source、
  494 个完整且全部直接可见 Frame 的 source-level 中位尺寸、分轴长 q95 与向外量化；不再保存 `half`
  或其它 format 的 tolerance 特例。Direct complete Frames 以完整 uncertainty 收紧 source W，唯一直接
  aperture pair 收紧 source H，native boundary 始终优先。
- `ApertureAspectRatioAuthority` 已启用：各 format 的 source-level raw W/H 包络由两轴混合 guard 传播成
  format-specific guarded ratio，再从至少两张完整直接 Frame 闭合的 W 推导一份 rank 0 相关 H。
  Calibration/共同 scale/W authority 不足、physical prior 冲突、direct H 冲突与 5% 预算耗尽均有 typed
  failure；direct H 存在时优先承担 cross。没有合格黄金数据的 format 保守 review，不作精确名义比例换算。
- Separator 仍以 catalog gap 为搜索中心，实际宽度由直接 material edges 与 local advance 拥有；holder
  extent 保留独立的外部 ±3.5% 设计先验。二者都没有为了复用 aperture guard 而改变物理含义。
- Cross 注册超过编译上界时不再抛出 runtime error；完整实际计数进入 typed `producer_bound_exceeded`
  receipt，并由 Gate 安全 review，不截断观察或提高魔法上限。
- Output protection 现在分别保存 mandatory、完整 requested 与实际 required source footprint。真实 TIFF
  外缘只限定不存在的源像素，并按 `source_boundary_optional_bleed | source_boundary_joint_protection`
  显式记录；内部 dual-lane 边界仍按 `lane_boundary_*` 阻断，不能借裁小获得批准。5% 预算继续使用未裁小
  requested footprint，Debug 以虚线保留完整请求，不静默丢失保护事实。
- Enclosing support 的 direct-use 预算不再把 top/bottom 的位置不确定性重复计入联合 alignment padding，
  也不再相加不同可行状态的边缘极值。逐侧完整 expansion、`1.1H` support span 与同一状态额外直线
  alignment padding 仍分别受原有上限约束；报告和 Debug 显式保存该同一状态最大值，未放宽 5% 产品预算。
- Cross registration 现在是同角色边界 family identity 的唯一 owner。只有一次 robust refit 精确保留完整
  transition union 时，多个局部 fragment 才合并为一个 canonical observation；refit 丢失任一 transition
  时全部成员原样保留，并报告 typed `complete_transition_union_refit_rejected`。Selection 中旧的
  broader/local dominance 已删除；不再按 trace containment、邻近、support 或 residual 消除 runner。
- 当前选择仍只使用 typed hard facts；没有启用 score。架构允许未来在硬合法候选之间加入经独立数据
  校准、带高阈值与 abstention 的概率选择，但未经校准的 score 不得拥有最终决定权，runner
  必须继续报告。
- Cross 不再用片夹短轴中心选择最终边界；它只帮助编译有界测量 corridor。直接 top/bottom pair 现在显式
  区分 `shared_traces` 与 `complementary_domains`：后者只在两侧都是 role-authorized direct evidence、
  各自有至少两个独立区域、两侧 trace 并集完整覆盖全部 selected Frame domain，且 fixed H 与方向相容时
  成立；共享 trace 数仍如实为 0。缺 domain、template-local/inferred opposite、方向冲突或多个完整 pair
  均保留 typed failure 与 review。若完整 pair 的同一 opposite 还能与严格更外侧的直接局部 role 闭合，
  内侧 pair 产生 typed `outward_role_counterevidence`；更外侧 pair 若也拥有完整 authority，则两者继续作为
  非等价 placement review。Source-spanning 单侧也不再把未覆盖全部 selected domain 的局部 opposite 外推
  为整条片带边界。Cross winner basis、pair support mode、family resolution、source 长轴投影
  与 enclosing-support 的逐侧/联合 padding 预算进入 typed report 和 Debug。已经由 fixed H 与 `1.1H`
  合同预闭合的唯一 enclosing-support pair 直接拥有两侧输出权限，不再错误依赖或消费只用于缺失
  aperture side 的 W/H 比例推导。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。Contact 与 overlap 始终属于
  challenge，但 challenge 不预设终态：标准 detector/Gate 可产生安全自动批准，证据不足时安全 review
  同样合格。Contact 与 Overlap 均进入同一 adjacency/placement；受影响边界的 topology protection 消耗
  既有 5% 总预算，不建立第二套 detector 或独立特殊 bleed 预算。
- Placement 保持 source-axis；局部直线 slope 只扩大安全包络。Deskew 是批准后的可选整理，不参与
  placement、Gate 或黄金准确性；证据不足或超限时保持原始倾斜。
- 安全层只处理唯一 selected placement 的联合可行状态。Aperture 每侧共用 5% 外扩预算；直接 enclosing
  support 使用总高度不超过 `1.1H` 的独立合同。真实 TIFF 外缘按显式 saturation 限定实际可用像素；
  内部 lane authority 越界仍 review，不静默裁小。
- 二维 content 只对最终 post-residual、post-bleed polygon 作 negative veto；它不能移动边界、选择
  runner 或创造 phase。

### 输出与报告

- Finalization 对 source 与安全 polygon 使用同一 affine transform，再取精确半开 AABB；不在旋转后继续
  裁固定 W×H。AABB 的 no-data 角落不是检测失败。
- Debug Analysis 只可视化同次检测事实：理论模板、观察、winner/runner、最终 footprint、预算和首个
  阻断原因；报告同时保存全局未知量 constraint rank、逐 adjacency query/trace/coordinate coverage 与
  直接角色/外侧 Frame observation authority，以及 dark/light material、逐区域状态和冲突。Debug 不重新
  求解，也不把 review candidate 伪装为正式输出。当前 schema 显式区分直接角色的 coordinate
  `observation_id` 与相关
  `evidence_group_id`，同时报告 phase candidate 的输入权限、projection outcome、保留 rank、投影 binding、
  calibrated nominal prior/evidence/selected authority、phase anchor、推断 adjacency、未观察 Frame、
  nominal solve/local-prefix 工作量、连续 lattice 参数依据、三层 source footprint、typed
  saturation、同一状态 cross
  alignment padding、selected-only source W authority、source W/H、相关
  Frame-width inference 及 validation-only role/observation provenance、aspect calibration、raw/guarded
  ratio、两轴 guard、推导 H、逐 adjacency continuity ledger、Contact edge/relation 与 topology
  protection、Cross typed root
  failure、pair support mode、family resolution 与预算；不保留旧 schema 兼容路径。
- 正式 TIFF 保真 16-bit RGB、ICC、resolution、支持的 metadata 与无损压缩，并写
  `Orientation=1`。完整 source 先写 staging，再原子发布到尚不存在的目录。
- Report、Gate 与 final geometry 各有唯一 owner；`CandidateGate` 只记录事实，`DecisionGate` 创建终态。

### 黄金校准

- 本地标注器使用一个 source-SHA-bound 校准池；不区分 v1/v2。同源多 count 共用一套物理边界，各自
  保留 task mapping，不建立重复页签或重复确认。
- Source record 以两条共享边、一个 `boundary_pool`、typed `slots` 和派生 `adjacencies` 表达几何。
  `blank_exposure` 保留 count/ordinal 但没有人工边界；`source_truncated` 保存物理外推线与 TIFF 内交集。
- 红线导入、机器 proposal、有界预览与原 TIFF 窄带精修都不授予黄金权限。逐线
  `review_basis`、Frame 状态、原生像素审核与明确确认完成后，source 才成为不可变
  `user_confirmed`。
- 黄金验收统一为最内侧可接受无 bleed 裁切：candidate 与正式 footprint 不得向确认 polygon 内侧
  越界；有预算权限的每侧最多向外 5%。`visible_content_limit` 只阻断向内越界，
  `human_width_estimate` 两向均不阻断，其它边仍独立生效。
- 人工红线尽量贴近该 source 的真实有效成像边界，基本可作为 source aperture 的尺寸观测。黄金分析
  按 source SHA 分开统计同源与跨 source 的 W/H、separator 和 pitch；这些事实可校准物理分布与
  source-level authority，但不能被压成适用于所有相机的单一固定常量。偏离 catalog 时先检查相机个体
  差异、扫描比例和 uncertainty，不自动归咎于标注。
- Nominal/challenge 在 detector 运行前由人工证据和固定模板合同逐 task 派生，并随确认基线冻结；
  accuracy 会重新推导核对，不能手填改类。Nominal 以安全自动批准为能力目标；challenge 的安全 auto 与
  安全 review 都有效，前者单独记录为能力发现。
- 两侧各空余至少一个固定 W、又缺少双端直接 outer 的内部 partial sequence 属于 challenge；该角色只从
  确认前几何推导，不由当前 detector 的结果或 post-selection holder fill 决定。
- Accuracy 只接受当前确认 task。没有完整的当前 development cohort 时明确报告
  `calibration is incomplete`，不回退历史基线。空 slot 不参与几何比较，但 runtime 对应输出与 ordinal
  必须保留。
- 完整确认集合通过唯一生成器独立核对 source、确认快照、审阅 artifact、task authority、角色和 geometry
  digest 后，才写入 tracked development cohort。Development 黄金分析把基础 nominal、较难 nominal 与
  challenge 分开，并逐边区分已观察且绑定、已观察未绑定、模板补全和竞争状态；这些诊断不进入 runtime
  或黄金权限。
- 当前已查看黄金明确归入 `development_gold`；未来 sealed acceptance 必须在查看 detector 结果前按
  source SHA 分区，同源 count 同分区，解封调试后永久退役到 development。人工 reference 仍只有一套。
- 验证分别报告危险自动批准、Review candidate 几何、nominal 自动覆盖和 challenge 能力；只有正式
  `approved_auto` 越过黄金安全合同才是用户层危险输出。
- 同源合法 count 变体按共享物理 Frame 建立 source-level diagnostic；额外空白或残缺 slot 不得把共享
  内容重定相到危险位置，但不同 count 可以合法产生不同 auto/review 终态。

### 工程与验证

- `tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与 sampling，
  Pillow 只在 Debug Analysis 延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。
- Phase residual compatibility 在物理阈值处保持包含语义，并只吸收 `1e-9 px` 的浮点舍入误差；不同
  NumPy/LAPACK 构建不得因此改变 `resolved/ambiguous`。对应阈值与独立支持回归随 full/pre-push
  验证执行。
- Full/pre-push 在工程测试前先以只读方式核对当前 Python 环境与 CI 共用的依赖合同；
  版本或模块能力漂移必须在推送前失败，不得留到 GitHub 矩阵暴露。
- Sequence coordinate identity 由 `observation_id` 唯一拥有；`evidence_group_id` 只负责相关证据去重。
  Separator 左右侧即使共享 material group 也不得被合并成同一坐标或用于隐藏离散 runner；旧的
  `independent_support_id` 字段已删除，不保留兼容别名。
- Registered gray、affine crop buffer 与 source-local cache 按阶段释放；这些优化不得改变 observation、
  placement、Gate、footprint 或输出像素。
- `tools/verify` 是 Hook、CI 与本地验证的唯一入口。Diagnostic 只证明工程合同；gold accuracy、性能与
  platform receipt 分层记录，不互相冒充。
- 正式性能 Gate 为 24-source 完整用户路径 mean 不超过 5 秒；3 秒只是不阻断的 challenge。
- Direct measured separator relation 检查点的完整 development gold 为 110/110 完成、分析错误 0、
  `unsafe_approved_auto = 0`；安全 auto 为基础 nominal 13/66、较难 nominal 2/30、challenge 0/14。
  Candidate 为 90 个不可用、17 个安全、3 个不安全；全部不安全 candidate 均保持 review，14 个 challenge
  均安全 review。相较上一检查点减少的 nominal 自动批准来自新揭示的 phase/direct-role 证明缺口，不以
  样片规则、分类变化或 Gate 放宽恢复。
- 24-source 正式性能只由绑定最终干净 commit 的 receipt 判定；5 秒 mean 仍是 blocking Gate，3 秒仍是
  non-blocking 目标。当前 direct measured separator relation 检查点已通过 5 秒 Gate，尚未达到 3 秒
  challenge；最终 receipt 必须绑定包含本结论的干净提交。当前 review 表达
  真实的 phase/cross、Grid/W、topology 与预算证明缺口，不以调窄 guard、静默隐藏 saturation、恢复精确
  W→H 或改变样片角色掩盖。
- Apple Silicon macOS、Intel macOS 与 Windows x64 必须在同一最终 commit 取得实机 receipt。Accuracy、
  性能与平台证据未全部绑定该 commit 前，不创建 RC、tag、Release 或公开 ZIP。
- 发布包由唯一 manifest 构建，不包含 modular source、tests、tools、内部文档或开发输出。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但没有
完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明“先看整条片带，再在理论位置附近找 outer 和 separator”可以快速覆盖规则片条。V5 继承并
重建理论 pitch/规则间距、material band、native gap edge、outer/cross、有限局部搜索、缺边投影、deskew、
候选无关复用与 TIFF readback。被删除的是由临时 content 区域驱动且未校准的 equal split、Grid 自证、
未经校准且直接决定终态的 confidence/best-score、selection 后 mutation、无条件固定像素 bleed 和
separator-center crop；它们曾承载的有效物理事实必须先迁入 current canonical owner。

## 回滚

恢复历史版本必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本
拼接组件。
