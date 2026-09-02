# 项目记忆

更新：2026-09-02。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

优先让当前 96 个 development nominal 全部安全 `approved_auto`，同时让 110 个 development task 的
`unsafe_approved_auto` 始终为 0。Challenge 不预设终态：安全 auto 是能力发现，安全 review 同样合格。
不得改样片角色、隐藏 runner、放宽黄金合同或用更大 bleed 换覆盖。

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

- Grid 是唯一 placement 主生成模型；format 提供黄金集校准且有界的 `W/H/pitch`，至少一个 absolute
  anchor 将它放入 TIFF。Direct rank 3 是更强的完全直接闭合路径，不是唯一许可；逐 adjacency coverage
  完整且无反证时，Grid 可以生成两侧都未直接观察的 Frame。直接 observation 保留 native coordinate
  并形成 local relation；完整相关包络仍由 containment、content veto 与每侧 5% 预算决定 auto/review。
- `SourceFrameWidthAuthority` 是 source W 的唯一 owner：`independent_complete_frames` 消费至少两张完整
  直接 Frame，`direct_lattice_closure` 消费保留的 rank-3 direct-role constraint 并对同一系统投影相关 W；
  两组同时可用时，`reconciled_direct_constraints` 只发布二者交集。交集为空产生
  `physical_width_conflict`，不得挑选有利的一组；reconciliation 保留全部 Frame/constraint/observation
  provenance，但不回写 Frame-width observation、不增加 rank、不参与离散选择。比例层显式消费同一
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
  `EnclosingSupportApertureAuthority` 用 21 个黄金 source 的直接 top/bottom 校准剩余中心偏移；同源中位数、
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
- 当前 Report revision 为 `x5crop_v5_template_report_48`；Debug/报告显式保存 calibration identity、anchor、
  inferred adjacency、完全未观察 Frame、联合参数依据、measured relation、projection outcome、typed
  failure、source-W/frame-inference basis、W topology facts、partial-height aperture domain 与工作量。Debug
  列出精确 anchor role、逐 adjacency local delta、direct correction、coverage/counterevidence、candidate
  elimination、enclosing-support center authority/有效偏移区间与最终联合 envelope。完整路径最多 6 次
  fit pass，不增加 TIFF query、第二 detector 或旧 schema 兼容层。

完整 development gold 已完成 110/110，分析错误 0，`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
14/66、较难 nominal 2/30、challenge 0/14；94 个 task 安全 review。Candidate 为 70 个不可用、20 个安全、
20 个不安全；全部不安全 candidate 均保持 review，14 个 challenge 的安全 Review 均合格。Source W 为
51 supported / 55 unavailable / 4 contradicted；其中 18 个由完整 Frame、11 个由 direct lattice、22 个由
两组 direct constraint reconciliation 闭合。Frame-width inference 为 24 supported / 41 unavailable /
45 not applicable；6 个使用完整 Frame basis、18 个使用 reconciliation。唯一
`direct_lattice_counterevidence` 是 S077。S076/S090 明确为 `physical_width_conflict`。Late-binding projection
共执行 19 次、投影 24 个无权限 binding、完成 15 次有界 Grid solve。
绑定检测提交 `03242641` 的完整黄金 development-detail mean 为 4.010 秒，只作开发归因；同一提交的
24-source 正式性能工具 mean 为 3.642 秒，通过 5 秒 Gate，3 秒目标仍为非阻断 challenge。当前安全但
Review 的 nominal candidate 为
S030/S058/S109；S045 的 candidate 不安全并继续被 5%/budget Gate 阻断。S012 的 candidate 会越过黄金
cross-low 预算，同样保持安全 Review。该开发检查点不替代未来 release commit 的正式性能复验。

对 96 个 nominal 的同源 v4.2.8/V5 对照中，发布版 80 个 auto 里有 70 个黄金危险自动裁切；发布版仅
11 个 geometry 安全。当前 V5 已让其中 S022、S025 安全 auto；其余 9 个仍按真实 typed root 安全 Review：
S004/S033 为 aspect budget，S007/S010/S026 为 adjacency topology，S011 为 Grid conflict，S028/S038 为
output budget，S032 为 phase ambiguity。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 是未来概率选择与未见来源声明的前提，但不再是首版发布前置条件。
- 当前 96 个 nominal 仍有 80 个 review。主要 phase root failure 为
  `discrete_phase_ambiguous` 13、`fixed_template_mismatch` 10、`adjacency_topology_unresolved` 6、
  `calibrated_nominal_grid_conflict` 5、`source_frame_width_conflict` 4、
  `nominal_grid_phase_anchor_unavailable` 3、`direct_phase_anchor_unavailable` 2、
  `direct_role_binding_authority_unavailable` 2、`frame_width_inference_unavailable` 1、
  `separator_material_conflict` 1 与
  `adjacency_observation_coverage_incomplete` 1；另有 48 个 nominal 已通过 phase，其中只有 16 个最终安全
  auto。S012、S030 与 S058 说明 phase 通过不等于输出风险已闭合。
- 完全不可见 Frame 已可由校准 Grid 生成，但这不是像素事实，也不直接授权 auto。候选仍须通过完整
  containment、content veto 与最坏预算；后续应改善 anchor、local correction 与直接 evidence，而非收窄
  传播不确定性。概率 scorer 当前不进入 Runtime。
- 内容是否连续穿过理论间隔的 continuity 仍不完整；source truncation 与片夹遮挡也缺少统一
  clipped-boundary geometry。宽缓单根长轴 material 仍可能是构图线，不能单独创造 phase。
- 21 个 selected unique enclosing-support source 的 aperture-center calibration 已闭合并可由黄金分析复算。
  S030/S058 仍因真实逐侧 residual/完整预算 Review，S012 的 candidate 仍会切入黄金边界；后续应提高
  shared top/bottom 的观察与拟合精度，不能扩大 center calibration、删除 residual 或用 bleed 掩盖缺口。

## 精确下一步

1. 对 S007/S010/S026/S040/S108/S110 这 6 个 `adjacency_topology_unresolved` 做下一轮单机制归因：区分
   native role 绑定错误、缺少直接 local relation、真实 Contact/Overlap 与 source-W interval 本身尚未
   闭合。S026 的 boundary-edge:28 当前绑定为
   F2 END，却也位于下一 Frame 的 separator side；应先修唯一 role/relation owner，不能收窄 W、挑有利
   状态或把未知 overlap 伪装成 `OverlapRelation`。
2. 对 4 个 `source_frame_width_conflict` 只按 source physical W 与 direct lattice 的真实冲突继续诊断；不得
   扩大 W prior 或回退旧“两张 Frame 才算 W”的权限。S077 的 registered counterevidence 也必须保留。
3. 随后按真实 root 继续离散 ambiguity、剩余 direct-role 与 clipped-boundary geometry；
   每次只闭合一个通用机制，不恢复旧终判或放宽预算。随真实使用逐步补充 calibration、sealed 和缺失
   format 样片。出现危险自动裁切时保存原 TIFF、format、
   count 与 SHA，人工建立权威 baseline，加入 incident regression，并只用通用机制永久修复。
