# 项目记忆

更新：2026-09-01。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
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
- Selected Grid 在 local relation/source-W 阶段追加 late binding 后，由同一 projection owner 重新核对。
  无坐标权限弱线只有在完整区间与对应 Grid role 包络相交时才降为 validation provenance；不相交产生
  `calibrated_nominal_grid_conflict`。仍有权限的 local native binding 在 direct-rank 重拟合后继续拥有其
  role，不能因不增加 global rank 而消失。
- Partial-height separator role 只有在 `DirectRoleApertureDomainAuthority` 证明全部登记 trace span 位于
  同一个两侧 direct aperture，或两侧 enclosing support 经 fixed H 闭合出的 aperture 内时，才保留 native
  coordinate。单侧/无唯一域为 unavailable，域坍缩或 trace 越域为 conflict；该证明不新增像素读取、候选
  或 rank，content veto 与 5% 预算继续独立生效。
- 当前 Report revision 为 `x5crop_v5_template_report_41`；Debug/报告显式保存 calibration identity、anchor、
  inferred adjacency、完全未观察 Frame、联合参数依据、measured relation、projection outcome、typed
  failure、partial-height aperture domain 与工作量。Debug 列出精确 anchor role、逐 adjacency local delta、
  direct correction、coverage/counterevidence 与最终联合 envelope。完整路径最多 6 次 fit pass，不增加
  TIFF query、第二 detector 或旧 schema 兼容层。

完整 development gold 已完成 110/110，分析错误 0，`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
14/66、较难 nominal 2/30、challenge 0/14；94 个 task 安全 review。Candidate 为 71 个不可用、21 个安全、
18 个不安全；全部不安全 candidate 均保持 review，14 个 challenge 的安全 Review 均合格。Late-binding
projection 共执行 14 次、投影 17 个无权限 binding、完成 13 次有界 Grid solve。Partial-height aperture
domain 影响 7 个旧权限阻断：S091 新增安全 auto；S030/S045 得到安全 candidate 但仍因预算 Review；
S008/S028 的 candidate 不安全并被预算阻断；S010/S049 被 content veto 阻断。完整黄金 diagnostic mean 为
4.110 秒，只作开发归因。24-source 正式完整用户路径 mean 约 4 秒，5 秒 Gate 通过，3 秒非阻断目标
尚未达到；正式数值只由绑定当前干净 commit 的 performance receipt 证明。

对 96 个 nominal 的同源 v4.2.8/V5 对照中，发布版 80 个 auto 里有 70 个黄金危险自动裁切；发布版仅
11 个 geometry 安全。当前 V5 已让其中 S022、S025 安全 auto；其余 9 个仍按真实 typed root 安全 Review：
S004/S033 为 aspect budget，S007 为 fixed-template，S010 为 content veto，S011 为 Grid conflict，S026 为
continuity，S028/S038 为 output budget，S032 为 phase ambiguity。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 是未来概率选择与未见来源声明的前提，但不再是首版发布前置条件。
- 当前 96 个 nominal 仍有 80 个 review。主要 phase root failure 为
  `discrete_phase_ambiguous` 13、`fixed_template_mismatch` 13、
  `direct_role_binding_authority_unavailable` 7、`calibrated_nominal_grid_conflict` 5、
  `nominal_grid_phase_anchor_unavailable` 3、`direct_phase_anchor_unavailable` 2、
   `frame_width_inference_unavailable` 2、`adjacency_continuity_unresolved` 1、
   `separator_material_conflict` 1 与 `adjacency_observation_coverage_incomplete` 1；另有 48 个 nominal 已通过
   phase，其中只有 16 个最终安全 auto。
- 完全不可见 Frame 已可由校准 Grid 生成，但这不是像素事实，也不直接授权 auto。候选仍须通过完整
  containment、content veto 与最坏预算；后续应改善 anchor、local correction 与直接 evidence，而非收窄
  传播不确定性。概率 scorer 当前不进入 Runtime。
- 内容是否连续穿过理论间隔的 continuity 仍不完整；source truncation 与片夹遮挡也缺少统一
  clipped-boundary geometry。宽缓单根长轴 material 仍可能是构图线，不能单独创造 phase。

## 精确下一步

1. 继续逐一审计“v4 geometry 安全但 V5 Review”的 9 个 task。Partial-height aperture-domain 权限已经
   闭合，下一机制只从 aspect budget、fixed-template、content veto、Grid conflict、continuity、phase
   ambiguity 或 output budget 中选择一个 canonical root；不恢复旧终判。
2. 按当前真实 root 分布推进离散 ambiguity、fixed mismatch、剩余 direct-role、adjacency continuity 与
   clipped-boundary geometry；每次只闭合一个通用机制，不恢复旧终判或放宽预算。
3. 随真实使用逐步补充 calibration、sealed 和缺失 format 样片。出现危险自动裁切时保存原 TIFF、format、
   count 与 SHA，人工建立权威 baseline，加入 incident regression，并只用通用机制永久修复。
