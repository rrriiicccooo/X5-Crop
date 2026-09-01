# 项目记忆

更新：2026-09-01。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

优先让当前 96 个 development nominal 全部安全 `approved_auto`，同时让 110 个 development task 的
`unsafe_approved_auto` 始终为 0。Challenge 不预设终态：安全 auto 是能力发现，安全 review 同样合格。
不得改样片角色、隐藏 runner、放宽黄金合同或用更大 bleed 换覆盖。

发布验收分为两层：

- 检测能力：development nominal 全部安全自动通过，全部角色危险自动批准为 0；未来建立 sealed cohort
  后，其 nominal 适用同一标准。
- 工程能力：正式 24-source mean `<= 5s`，并通过 TIFF/metadata、安装、Apple Silicon macOS、Intel
  macOS、Windows x64、打包与 Hook/CI 验证。3 秒 mean 仍是非阻断优化目标。

当前没有 sealed cohort，黄金也未覆盖 `xpan`、`120-645`、`135-dual`。这些事实不阻断首版发布，但必须
披露为“尚无未见/真实样片覆盖”，不能宣称已经验证，也不能据此建立 format 禁用、白名单或宽松规则。

## 当前检查点

- Grid 是唯一 placement 主生成模型；format 提供有界 `W/H/pitch`，直接观察确定 absolute phase、保留
  native boundary 并形成 local relation，反证淘汰非法状态。Grid 不是 fallback，也不能自授自动批准。
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
- 当前 Report revision 为 `x5crop_v5_template_report_38`；Debug/报告显式保存 measured relation、direct
  separator refit、authority ceiling、projection outcome、typed failure 与工作量。完整路径最多 6 次 fit
  pass，不增加 TIFF query、第二 detector 或旧 schema 兼容层。

完整 development gold 已完成 110/110，分析错误 0，`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
13/66、较难 nominal 2/30、challenge 0/14；95 个 task 安全 review。Candidate 为 90 个不可用、17 个安全、
3 个不安全，3 个不安全 candidate 全部保持 review；14 个 challenge 均为安全 review。相较上一检查点减少的
4 个 nominal 自动批准来自新揭示的 phase/direct-role authority 缺口，没有用样片特例、改分类或放宽 Gate
恢复。完整黄金 diagnostic mean 为 3.853 秒，只作开发归因，不冒充正式性能 receipt。

当前机制检查点的 24-source 正式性能已通过 mean `<= 5s` Gate，3 秒 non-blocking challenge 尚未达到；
最终 receipt 必须继续绑定包含本结论的干净提交。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 是未来概率选择与未见来源声明的前提，但不再是首版发布前置条件。
- 当前 96 个 nominal 仍有 81 个 review。主要 phase root failure 为
  `nominal_grid_complete_frame_unobserved` 21、`fixed_template_mismatch` 18、
  `discrete_phase_ambiguous` 16、`direct_role_binding_authority_unavailable` 12；另有
  `adjacency_continuity_unresolved` 3、`nominal_grid_phase_anchor_unavailable` 3、
  `direct_phase_anchor_unavailable` 2、`frame_width_inference_unavailable` 2 与
  `separator_material_conflict` 1。
- 完全不可见 Frame 不能靠加强 edge detector 全部解决。未取得独立 calibration/OOD/abstention 权限前，
  不能让 Grid 或 source W 创造像素事实；概率 scorer 当前不进入 Runtime。
- 内容是否连续穿过理论间隔的 continuity 仍不完整；source truncation 与片夹遮挡也缺少统一
  clipped-boundary geometry。宽缓单根长轴 material 仍可能是构图线，不能单独创造 phase。

## 精确下一步

1. 先完善 adjacency material continuity：它可以否定普通 separator、加强 normal/contact/overlap 反证，
   但不能单独移动边界或证明 topology。完整黄金仍以危险自动批准为 0 为硬前提。
2. 再补 source boundary clipping、部分可见线段和片夹遮挡的通用几何；TIFF 截断只能限制可观察线段，
   片夹边不能冒充完整 aperture。
3. 随后继续处理 nominal 的弱边缘、局部片距变化与完全不可见 Frame；缺少独立风险权限时不得用 Grid
   或 score 强行自动批准。
4. 随真实使用逐步补充 calibration、sealed 和缺失 format 样片。出现危险自动裁切时保存原 TIFF、format、
   count 与 SHA，人工建立权威 baseline，加入 incident regression，并只用通用机制永久修复。
