# 项目记忆

更新：2026-09-03。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

优先让当前 96 个 development nominal 全部安全 `approved_auto`。Release commit 必须让 110 个
development task 的 `unsafe_approved_auto = 0`；中间开发允许黄金集暴露危险 auto，但必须逐项保存样片、
错误边界与根因，并明确不能发布或正式交付。Challenge 不预设终态：安全 auto 是能力发现，安全 review
同样合格。不得改样片角色、隐藏 runner、放宽黄金合同或用更大 bleed 换覆盖。

V5 是 v4.2.8 已有效检测能力在 current-only 物理与安全架构中的重建和增强，不是另一个从零设计的
裁切器。删除旧机制前必须先确认它为何在真实像素上有效，把有效部分迁入唯一 observation、anchor、
local correction、risk feature、veto、protection 或 selection owner；不保留旧源码结构、兼容层、平行
runtime、无条件 fallback 或无法解释的 post-selection mutation。

发布验收分为两层：

- 检测能力：development nominal 全部安全自动通过，全部角色危险自动批准为 0；未来建立 sealed cohort
  后，其 nominal 适用同一标准。
- 工程能力：正式 24-source mean `<= 5s`，并通过 TIFF/metadata、安装、Apple Silicon macOS、Intel
  macOS、Windows x64、打包与 Hook/CI 验证。3 秒 mean 仍是非阻断优化目标。

当前没有 sealed cohort，黄金也未覆盖 `xpan`、`120-645`、`135-dual`。这些事实不阻断首版发布，但必须
披露为“尚无未见/真实样片覆盖”，不能宣称已经验证，也不能据此建立 format 禁用、白名单或宽松规则。

## 当前检查点

- Runtime 已严格分开完整 pre-Gate proposal、candidate eligibility 与 `approved_auto | needs_review`。
  `TemplatePlacementProposal` / `TemplateSourceProposal` 是 proposal 的唯一 owner；资格不足不再删除已经形成的
  方案，正式 TIFF 仍只来自 approved output。Development gold 分别比较 proposal、candidate 与正式 auto；
  `--gate report` 保留危险 auto 诊断，`--gate release` 与 `tools/verify accuracy` 才执行发布检测门槛。
- 有 absolute anchor 且已形成全部 role 坐标的 direct 或 calibrated-Grid phase 不再因权限不足被当作
  “无几何”。`PhaseRetainedProposalBasis` 同时表达 pre-local counterevidence 与 residual counterevidence；
  后者在全部 bounded fit 都超过直接残差合同时保留一份诊断 proposal 和一个离散 runner。原 typed failure、
  unresolved 状态与 winner 权限保持不变。Cross 可用时可组合完整 source proposal，Cross 不可用时只显示
  轴级事实；两种情况都不取得 candidate 或 auto 权限。
- 普通 Cross competition 没有取得 authority 时，`CrossRetainedProposalBasis` 仍可保留 Review-only 几何。
  多个合法 direct pair 先由物理最外侧 TOP 锚定，再按校准 H、方向相容性和稳定 identity 保留 proposal 与
  runner；两侧保持 native coordinate。没有 pair 时，才从 role-authorized 最外侧单边或覆盖至少三个独立
  高度区域的有界 direct-role hypothesis 结合校准 H 补 opposite。原 `UNRESOLVED`、typed failure、runner
  与工作量上限不变；任何路径都不增加 candidate、rank、查询、score 或正式输出权限。
  `CrossLineProjectionBasis` 让 resolved/eligible fit 继续使用完整物理方向包络，而 retained unresolved best
  只用自身统计拟合方向形成可比较的 Review proposal；完整物理区间仍留在 evidence/report，不能借此取得
  candidate 或 auto 权限。`CrossHeightProjectionBasis` 同样让 resolved/eligible 与 retained direct pair
  使用完整 H interval；retained single-side best 只用 canonical H 画具体 Review proposal，完整 H 风险仍
  独立保留并阻断 eligibility。
- Grid 是唯一 placement 主生成模型；format 提供黄金集校准且有界的 `W/H/pitch`，至少一个 absolute
  anchor 将它放入 TIFF。Direct rank 3 是更强的完全直接闭合路径，不是唯一许可；逐 adjacency coverage
  完整且无反证时，Grid 可以生成两侧都未直接观察的 Frame。直接 observation 保留 native coordinate
  并形成 local relation；完整相关包络仍由 containment、content veto 与每侧 5% 预算决定 auto/review。
- 显式 count 小于 lane 片夹容量时，role-free long material hull 不能确定照片组占用哪一个连续 slot 子集。
  `coarse_strip_support.py` 因此以 `holder_slot_subset_conservative` 保留完整 lane 搜索权限，同时保存 direct
  hull 与 observation identity 供诊断；它不居中、不选择 subset、不创建 phase/rank，也不增加 query。
  Full-capacity sequence 仍使用 pixel-localized hull。S107/S112 已由此从无 proposal 变为完整 Review
  proposal，后续 eligibility 与正式决定未改变。
- `SourceFrameWidthAuthority` 是 source W 的唯一 owner，并用 `placement_scope` 区分
  `resolved_placement | retained_ambiguous_proposal`。Ambiguous scope 只收紧保留的 best proposal、补其已有
  缺失 opposite，原 phase failure 与 runner 不变，也不取得 candidate/auto 权限；额外 native pair/单边
  local rebind 仍只允许 resolved placement。`independent_complete_frames` 消费至少两张完整直接 Frame，
  `direct_lattice_closure` 消费全部 retained direct-role coordinate 已达到 rank 3 的系统，并对同一系统投影
  相关 W；
  两组同时可用时，`reconciled_direct_constraints` 只发布二者交集。交集为空产生
  `physical_width_conflict`，不得挑选有利的一组；reconciliation 保留全部 Frame/constraint/observation
  provenance，但不回写 Frame-width observation、不增加 rank、不参与离散选择。Direct-rank 不能任取
  三行：恰好三条约束时精确投影；过定系统以全部 direct coordinate 的 direct-only fit 传播每条 native
  interval 与实际 residual。`GlobalLatticeAuthority` 只拥有约束矩阵与 rank，canonical W 只由
  `SourceFrameWidthAuthority` 发布。比例层显式消费同一
  authority，W→H 仍为 rank 0 相关推断。若建立 W 时投影退出的 local line 仍构成反证，缺失角色保持
  `direct_lattice_counterevidence` review，不能删除反证后自证。
- `SourceFrameWidthTopologyAssessment` 独立回答“已获权限的 correlated-W inference 是否在全部 W 状态下
  保持既有普通 adjacency”。它只检查最终确实由 W 拥有的角色；跨零或全负 signed-gap interval 分别保存
  `normal_adjacency_unresolved | normal_adjacency_contradicted`，并映射为
  `adjacency_topology_unresolved`。W inference 未获权限时显示 `NOT USED`，不抢占
  `complete_frame_unobserved` 或 counterevidence；direct Separator/Contact/Overlap 继续由各自关系 owner
  优先。该检查不挑有利 W、不新增查询、候选、rank 或 score，工作量为 `O(count)`。
- 唯一直接 END → separator material → START 始终保存 direct gap；gap 异常或需要约束未观察 suffix role
  时形成 measured `SeparatorRelation`。它保存直接 signed-gap interval 与两侧 observation identity；共享 W/pitch 变化时按
  `delta = signed_gap - (pitch - W)` 重算相关 local advance，不能把 native endpoint 拉回默认 Grid。
  只有完整测量、无反证但没有直接 separator 的 adjacency 才使用 unobserved nominal `local_delta = 0`。
- Direct separator refit 保留原 phase anchor；新追加 endpoint 只能作为 `LOCAL_REFINEMENT`。重拟合前的
  全局 phase binding 与 Contact/Overlap 必要角色组成 `phase_anchor_authority_ceiling`；新增 endpoint 不能创造 phase authority、
  constraint rank 或无关 role binding。越过 ceiling 或改变 template、ordinal、relation evidence、role
  mapping 时 typed review。
- `AdjacencyRelation` 统一表达 Separator、Contact 与 Overlap，并只作一次 O(count) prefix。已证明的异常
  topology 只保护前一 Frame END 与后一 Frame START，基础 bleed、uncertainty、residual 与 topology
  protection 共用原有每侧 5% 预算；输出 polygon 不被事后修补。
- Coarse short-axis sharp/broad material 共用一次 registered measurement。唯一、跨高度一致且满足固定 H
  的 enclosing pair 可以取得权限；多解或不相容保持 typed review，不按 score 选解。
- Enclosing support 的 shared slope 只由 `JointFrameState` 传播一次；local residual 比较实测 trace 与同一
  状态直线，域外只传播 observed direction 相对该 slope 的差。绝对斜率不能在联合 footprint 与 residual
  中重复计数；现有 `BoundaryProtectionFact`、预算 Gate 与 Debug 是唯一 owner 和可见表达。
- Separator pair 的 canonical identity 是有序 `END → material → START`。Selected-only refinement 若较晚
  补出精确反序绑定，当前 candidate 以 typed contradiction 淘汰；只有已保留且权限合格的 runner 可晋升，
  非法 role/edge 不得重新绑定。仍获权限的 local refinement 保持原离散 identity。该过程最多评估两个
  selected fit，不增加查询、候选或 score。
- Enclosing support 本身只证明 aperture 位于两条 support 之间。Selected unique pair 之后，唯一
  `EnclosingSupportApertureAuthority` 用 20 个黄金 source 的直接 top/bottom 校准剩余中心偏移；同源中位数、
  source hull 与 `0.001H` 向外量化得到 `[-0.009H, +0.007H]`。它是 rank 0 相关推断，不选择 geometry、
  不把 support 变成 direct aperture，也不修改 output polygon。Calibration 不可用时继续评估完整物理
  中心区间；与直接 containment 无交集时 typed Review。`EnclosingSupportApertureRisk` 仍按同一联合状态
  消费原有 5% 预算。
- Selected lattice 在 local relation/source-W 阶段追加 late binding 后，由同一 projection owner 重新核对。
  校准 Grid 与 direct-rank 使用同一 bounded projection；无坐标权限弱线只有在完整区间与对应 role 包络
  相交时才降为 validation provenance，不相交分别产生 `calibrated_nominal_grid_conflict` 或
  `direct_lattice_conflict`。Direct-rank 路径先让独立 source W 尝试闭合 opposite，再投影仍无权限的晚期
  弱线；Contact/Overlap 必需 binding 不得退出。仍有权限的 local native binding 继续拥有自己的 role。
- Partial-height separator role 只有在 `DirectRoleApertureDomainAuthority` 证明全部登记 trace span 位于
  同一个两侧 direct aperture，或两侧 enclosing support 经 fixed H 闭合出的 aperture 内时，才保留 native
  coordinate。单侧/无唯一域为 unavailable，域坍缩或 trace 越域为 conflict；该证明不新增像素读取、候选
  或 rank，content veto 与 5% 预算继续独立生效。
- 单侧短轴 H 现在有两种明确且互斥的 inference basis。Source W 与 format ratio 已闭合时使用
  `aperture_aspect_ratio`；否则，唯一 source-spanning 或完整 selected-domain direct anchor 使用
  `SourceScanGeometry.height_state` 已拥有的有界 `calibrated_format_height`。Ratio 反证只允许保留 proposal，
  不允许成为 candidate；弱 anchor、多解或方向不足仍保持 typed unresolved，其中方向有界且角色已登记的
  弱 anchor 可以保留明确标注的 Review proposal。两条 H 路径都不增加 direct rank、不覆盖两侧 native
  boundary，并继续受完整不确定性、containment 与每侧 5% 预算约束。
- Cross registered-run 上限按物理角色独立拥有：TOP 与 BOTTOM 各自最多 512 条，一侧不能占用另一侧
  配额；任一侧超界仍 typed Review。Report/Debug 同时显示两侧实际计数和每角色上限，canonical fitted
  observation 与 pair 上限保持独立。S002 的 TOP 393 / BOTTOM 185 因而不再被两侧合计 578 假性终止。
- 当前 Report revision 为 `x5crop_v5_template_report_62`；普通报告与 Debug 显式分开 proposal、eligibility、
  selected output 和决定，并继续保存 calibration identity、anchor、inferred adjacency、完全未观察 Frame、
  联合参数依据、measured relation、projection outcome、typed failure、cross-H/source-W/frame-inference basis、全部
  retained W constraint/observation、placement scope、W topology facts、Cross line/height projection、partial-height
  aperture domain 与工作量。完整路径最多 6 次 fit pass，不增加 TIFF query、第二 detector 或旧 schema 兼容层。
- Enclosing-support aperture-center v2 calibration 使用 20 个当前仍具唯一 selected support pair、且黄金
  top/bottom 均为 `directly_visible` 的 source，并同时绑定 cohort、eligibility 与精确 observation-set SHA。
  S109 在 canonical W 扩大后成为 cross 多解，不再冒充 calibration observation；release analysis 会阻断
  source manifest 不等于 HEAD，以及成员、观测值、数量或登记数值的任何漂移。区间仍为
  `[-0.009H, +0.007H]`，crop geometry 未改变。

完整 development gold diagnostic 已完成 110/110，分析错误 0。现有主模型为全部 110 个 task 生成完整
proposal，分布为 30 safe / 80 unsafe。Retained single-side Cross 现在以 canonical H 画具体 Review proposal，
完整 H 风险继续单独保留；7 个 task 的 53 个 Cross side 受影响。S069 从 unsafe 变为 safe；S112 从 safe
变为 unsafe，暴露 canonical H 在 `cross_low` 向黄金内侧 15.047 px，而不再由完整 H 风险包络掩盖。S033、
S068、S106、S107、S108 的 proposal 仍不安全。Eligibility 层仍保留
40 个 candidate，形成 19 safe / 21 unsafe / 70 unavailable：11 个安全 proposal 与 59 个不安全 proposal
被保留为 Review。Runtime stage 为 16 approved auto、24 eligible candidate Review、70 proposal-generated /
eligibility-withheld。当前仍是 16 个安全 auto、94 个 Review、危险 auto 0，但 release detection gate 未
达标；开发 report 即使出现危险 auto 也必须完整列出，不能把中间结果称为发布通过。
本次 development-detail mean 为 3.954 秒，只作开发归因，不是正式性能 receipt；
最近一次 clean-checkpoint 24-source 正式性能 mean 为 3.536 秒，通过 5 秒 Gate，3 秒目标仍为
非阻断 challenge，该旧性能 receipt 不替代未来 release commit 的复验。

黄金 line/polygon 的原 TIFF 坐标现在由唯一 comparator owner 使用冻结的 `raw_to_canonical` affine 恰好
映射一次，再与 canonical Runtime footprint 比较；Orientation 3/8 不再混用坐标空间。源截断 Frame 的
非四边形 polygon 使用真实人工 boundary line 半平面逐侧判断，避免把 TIFF 裁切交点误认成物理边界。
Development gold record 为 v16、summary 为 v18。

Source W 为 65 supported / 41 unavailable / 4 contradicted；51 个属于 resolved placement，14 个属于
retained ambiguous proposal；其中 22 个由完整 Frame、13 个由 direct lattice、30 个由两组 direct constraint
reconciliation 闭合。Frame-width inference 为 33 supported / 41 unavailable / 36 not applicable；唯一
`direct_lattice_counterevidence` 是 S077。S029、S078 的 proposal 由 unsafe 变为 safe，没有 safe→unsafe
回归；S019 的 W→H 反证迁移为 `aperture_aspect_ratio_conflict`。Candidate、决定与 runner 分布均未改变。
Late-binding projection 共执行 18 次、投影 23 个无权限 binding、完成 15 次有界 Grid solve。

对 96 个 nominal 的同源 v4.2.8/V5 对照中，发布版 80 个 auto 里有 70 个黄金危险自动裁切；发布版仅
11 个 geometry 安全。当前 V5 已让其中 S022、S025 安全 auto；其余 9 个仍按真实 typed root 安全 Review：
S004/S033 为 aspect budget，S007/S010/S026 为 adjacency topology，S011 为 Grid conflict，S028/S038 为
output budget，S032 为 phase ambiguity。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 是未来概率选择与未见来源声明的前提，但不再是首版发布前置条件。
- 当前 110 个 task 均有完整 proposal，其中 70 个 eligibility withheld。后者包含 11 个黄金安全 proposal
  （S002/S014/S029/S048/S069/S078/S079/S083/S085/S088/S094）和 59 个不安全 proposal；
  安全并不自动证明当前阻断多余，不安全也不能因 Review 而隐藏，必须分别追到通用权限或几何根因。
- 当前 96 个 nominal 仍有 80 个 review。主要 phase root failure 为
  `discrete_phase_ambiguous` 13、`fixed_template_mismatch` 10、`adjacency_topology_unresolved` 6、
  `calibrated_nominal_grid_conflict` 5、`source_frame_width_conflict` 4、
  `nominal_grid_phase_anchor_unavailable` 3、`direct_role_binding_authority_unavailable` 2、
  `frame_width_inference_unavailable` 1、
  `separator_material_conflict` 1 与
  `adjacency_observation_coverage_incomplete` 1；另有 50 个 nominal 已通过 phase，其中只有 16 个最终安全
  auto。S012、S030 与 S058 说明 phase 通过不等于输出风险已闭合。
- 完全不可见 Frame 已可由校准 Grid 生成，但这不是像素事实，也不直接授权 auto。候选仍须通过完整
  containment、content veto 与最坏预算；后续应改善 anchor、local correction 与直接 evidence，而非收窄
  传播不确定性。概率 scorer 当前不进入 Runtime。
- 内容是否连续穿过理论间隔的 continuity 仍不完整；source truncation 与片夹遮挡也缺少统一
  clipped-boundary geometry。宽缓单根长轴 material 仍可能是构图线，不能单独创造 phase。
- 20 个 selected unique enclosing-support source 的 aperture-center calibration 已闭合并由精确 observation
  set digest 复算一致。
  S030/S058 仍因真实逐侧 residual/完整预算 Review，S012 的 candidate 仍会切入黄金边界；后续应提高
  shared top/bottom 的观察与拟合精度，不能扩大 center calibration、删除 residual 或用 bleed 掩盖缺口。

## 精确下一步

1. 全部 110 个合法黄金 task 已能生成完整 proposal。Cross direction 与 H projection 已分别从物理风险
   包络中拆出具体 Review 画法，原 failure、runner 与 eligibility 保持不变。S033/S068 的 Cross side 已进入
   预算，但 proposal 仍因长轴失败不安全；下一步与 S082 一起回到 phase/local relation。S107/S108/S112
   暴露的 single-side canonical-H 向内误差回到 Cross anchor、source truncation 与校准 H owner，不能再用
   完整 H interval 外扩伪装默认 proposal。随后继续处理此前
   calibrated-H proposal：S011/S020/S037/S097 的长轴向内越线优先回到
   phase/local relation；S001/S004/S018/S019/S056/S066 的逐侧外扩超预算回到 cross anchor、H interval 或
   residual/bleed 的真实 owner。不能为了让黄金变绿而收窄校准区间或放宽 5% 合同。
2. 在 110 个已生成 proposal 上优先修 80 个黄金不安全几何的通用 detector、anchor、local relation、cross
   或 output 根因；黄金只作离线比较，不能进入 Runtime。随后审计 11 个安全但 eligibility withheld 的方案，
   只移除真正放错层级或重复的阻断，保留真实 counterevidence。
3. Proposal 几何稳定后再收紧 eligibility 与 DecisionGate，使 96 个 nominal 全部安全 auto；开发期间任何
   危险 auto 都完整列出并继续修复，release commit 才硬性归零。每次只闭合一个通用机制，不恢复旧终判、
   放宽预算或建立兼容路径；真实 incident 经人工确认后永久进入回归集。
