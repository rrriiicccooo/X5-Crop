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
  native boundary 并形成 local advance，反证淘汰非法状态。Grid 不是 fallback，也不能自授自动批准。
- `AdjacencyRelation` 已完整表达 `SeparatorRelation | ContactRelation | OverlapRelation`。Overlap 只接受
  已登记、独立且角色相反的反序 END/START edge pair；完整 adjacency coverage、无 separator 竞争且严格
  负 signed gap 后，才以 `delta = W - pitch + signed_gap` 进入同一 O(count) prefix。Contact/Overlap 两侧
  不参加 source W 独立支撑。
- 已证明 Contact/Overlap 只保护前一 Frame END 与后一 Frame START，额外保护与基础 bleed、uncertainty、
  residual 共用原有每侧 5% 预算。只有 relation 对应的 Frame 可以重叠，cross evidence 在重叠中点分区；
  输出 polygon 不被修改。Report revision 为 `x5crop_v5_template_report_36`。
- Calibrated Grid 重拟合曾暴露 relation 的 canonical signed gap 仍绑定旧 seed 中心的问题。现已由最终联合
  连续状态统一实现 relation，并用 `topology_binding_unavailable` 阻止必要 direct binding 被投影丢失；
  S008、S051、S054 均恢复为正常完成且安全 review，没有用异常捕获掩盖根因。
- 真实 overlap 样片 S009、S056 当前均为安全 review。S009 没有形成合法 proposal；S056 只有未选中的
  诊断 proposal，真实 Frame 4/5 尚未闭合 relation，因此本阶段没有 challenge 自动通过能力发现。

完整 development gold 已完成 110/110，分析错误 0，`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
17/66、较难 nominal 2/30、challenge 0/14；candidate 为 87 个不可用、20 个安全、3 个不安全，3 个不安全
candidate 全部保持 review。与 Contact 检查点相比，自动批准集合和 candidate 安全分类不变。

Overlap 的 24-source 正式性能已通过 mean `<= 5s` Gate；3 秒 non-blocking challenge 尚未达到。Receipt
只对其中记录的 clean commit、依赖与机器有效；development diagnostic 的 4.43 秒均值不属于性能 Gate。

## 证据边界与开放风险

- 106-source/110-task development gold 用于发现机制、调试和 incident regression，不估计未来生产错误率。
  独立 calibration/sealed 仍是未来概率选择与未见来源声明的前提，但不再是当前首版发布前置条件。
- 当前 96 个 nominal 仍有 77 个 review。主要 phase root failure 为
  `nominal_grid_complete_frame_unobserved` 22、`discrete_phase_ambiguous` 12、
  `direct_role_binding_authority_unavailable` 11、`fixed_template_mismatch` 10；另有
  `nominal_grid_phase_anchor_unavailable` 3、`adjacency_continuity_unresolved` 2 与其它独立 typed failure。
- 完全不可见 Frame 不能靠继续加强 edge detector 全部解决。未取得独立 calibration/OOD/abstention 权限
  前，不能让 Grid 或 source W 创造像素事实。概率 scorer 当前不进入 Runtime。
- 宽缓 outer/cross 边界目前主要是诊断 evidence；内容是否连续穿过理论间隔的 continuity 仍不完整；
  source truncation 与片夹遮挡也缺少统一 clipped-boundary geometry。这三类能力可能同时影响 nominal 的
  phase、长轴和短轴 authority，但必须分别按小机制闭环实现。

## 精确下一步

1. 完成 Overlap 检查点的 clean-commit 性能 receipt、正常 Hook/推送与 GitHub Verify。
2. 以完整黄金 typed root failure 重新排序 nominal 工作；优先让唯一、跨高度一致的宽缓 outer/cross
   material edge 取得正式 phase/outer/cross authority，不用 score 选择多解。
3. 再补完整 adjacency continuity，以及 source boundary clipping、部分可见线段和片夹遮挡的通用几何；
   continuity 只能否定普通 separator 或加强反证，不能单独证明 contact/overlap 或移动裁切框。
4. 随真实使用逐步补充 calibration、sealed 和缺失 format 样片。出现危险自动裁切时保存原 TIFF、format、
   count 与 SHA，人工建立权威 baseline，加入 incident regression，并只用通用机制永久修复。
