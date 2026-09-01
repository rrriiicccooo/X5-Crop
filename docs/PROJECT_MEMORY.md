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
- 当前 Report revision 为 `x5crop_v5_template_report_39`；Debug/报告显式保存 calibration identity、anchor、
  inferred adjacency、完全未观察 Frame、联合参数依据、measured relation、projection outcome、typed
  failure 与工作量。Debug 进一步列出精确 anchor role、逐 adjacency local delta、direct correction、
  coverage/counterevidence 与最终联合 envelope。完整路径最多 6 次 fit pass，不增加 TIFF query、第二
  detector 或旧 schema 兼容层。

完整 development gold 已完成 110/110，分析错误 0，`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
13/66、较难 nominal 2/30、challenge 0/14；95 个 task 安全 review。Candidate 为 81 个不可用、17 个安全、
12 个不安全；全部不安全 candidate 均保持 review，14 个 challenge 的安全 Review 均合格。相较上一检查点，
Grid 让 9 个原本不可用的 task 形成可审计候选，但它们的最坏包络均未通过黄金/预算，因此自动覆盖保持
15，不以放宽 Gate 换数量。完整黄金 diagnostic mean 为 4.058 秒，只作开发归因，不冒充正式性能 receipt。

对 96 个 nominal 的同源 v4.2.8/V5 对照中，发布版 80 个 auto 里有 70 个黄金危险自动裁切；发布版仅
11 个 geometry 安全。发布版安全而 V5 Review 的 9 个 task 已按 typed root 分到 aspect/cross、
fixed-template、direct-role、Grid conflict、continuity、phase ambiguity 与 output budget，不以旧终判恢复
通过。当前提交的正式 performance 必须在最终干净 commit 上重新绑定，不能用 development diagnostic
mean 或旧 commit receipt 替代。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 是未来概率选择与未见来源声明的前提，但不再是首版发布前置条件。
- 当前 96 个 nominal 仍有 81 个 review。主要 phase root failure 为
  `direct_role_binding_authority_unavailable` 17、`discrete_phase_ambiguous` 15、
  `fixed_template_mismatch` 10、`calibrated_nominal_grid_conflict` 5、
  `nominal_grid_phase_anchor_unavailable` 3、`direct_phase_anchor_unavailable` 2、
  `frame_width_inference_unavailable` 2 与 `adjacency_continuity_unresolved` 1；另有 41 个 nominal 已通过
  phase，其中只有 15 个最终安全 auto。
- 完全不可见 Frame 已可由校准 Grid 生成，但这不是像素事实，也不直接授权 auto。当前新增的 9 个候选均
  因真实黄金偏差或最坏预算保持 Review，说明后续应改善 anchor、local correction 与直接 evidence，而非
  收窄传播不确定性。概率 scorer 当前不进入 Runtime。
- 内容是否连续穿过理论间隔的 continuity 仍不完整；source truncation 与片夹遮挡也缺少统一
  clipped-boundary geometry。宽缓单根长轴 material 仍可能是构图线，不能单独创造 phase。

## 精确下一步

1. 先逐一审计“v4 geometry 安全但 V5 Review”的 9 个 task，以及本阶段新增的 9 个不安全 Grid candidate
   与 5 个 nominal calibration conflict；区分发布版的有效 observation/anchor/local correction、当前
   counterevidence 和预算阻断，再选择一个 canonical owner 形成下一小机制，不恢复旧终判或放宽预算。
2. 再处理数量最多的 `direct_role_binding_authority_unavailable`，随后才按真实 root 分布推进离散 ambiguity、
   fixed mismatch、adjacency continuity 与 clipped-boundary geometry；每次只闭合一个通用机制。
3. 随真实使用逐步补充 calibration、sealed 和缺失 format 样片。出现危险自动裁切时保存原 TIFF、format、
   count 与 SHA，人工建立权威 baseline，加入 incident regression，并只用通用机制永久修复。
