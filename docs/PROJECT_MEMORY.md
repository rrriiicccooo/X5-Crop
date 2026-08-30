# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三层提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的目标是全部安全
`approved_auto`。不得改样片角色、放宽黄金合同、隐藏 runner 或牺牲正式 mean `<= 5s` 来提高覆盖。

每次只闭合一个通用物理机制，并同时交付合同与真值表、canonical owner、typed evidence/failure、
Debug、正反例、少量真实样片和完整黄金验收。全局 lattice authority、逐 adjacency coverage 与完整
候选无关查询走廊已经闭合；下一机制只扩展 polarity-complete separator material observation。

## 已验证事实

- 黄金集为 106 个唯一 source SHA、110 个显式 count task：96 个 nominal、14 个 challenge；优化分层为
  66 / 30 / 14。全部 task 已人工确认，同源 count 变体共享物理边界但独立验证。
- 当前 detector source manifest `a3d3fc81c3e727ce` 的黄金分析为 110/110 完成、分析错误 0、危险自动
  批准 0。安全 `approved_auto` 为 12 个：基础 nominal 11/66、较难 nominal 1/30；14 个 challenge 均
  安全 review。Candidate 为 80 个不可用、22 个安全、8 个不安全；Review candidate 只作机制诊断。
- `SequenceAnchorDiscoveryDomain` 从左右 holder 端分别投影完整且相关的 `W/pitch` 状态，合并并预登记
  全部候选无关 role corridor；不增加 TIFF 读取，不读取 winner。原 23 个
  `adjacency_observation_coverage_incomplete` 已归零，S004 恢复为安全 auto。
- 扩大的观察域同时揭示了原先被窄窗口隐藏的安全缺口。直接 START/END 只有获得 source-wide edge、
  同一 separator pair 或独立 fixed-W Frame pair 的坐标权限后才能进入 placement；当前 22 个
  `direct_role_binding_authority_unavailable` 保持 review。S034 的局部孤立 edge 不再造成危险自动批准。
- 当前其它 typed phase root failure 为 `global_lattice_authority_unavailable` 2 个、
  `outer_frame_observation_authority_unavailable` 3 个、`discrete_phase_ambiguous` 32 个、
  `fixed_template_mismatch` 5 个和 `local_advance_ambiguous` 3 个。失败迁移来自通用证据合同，没有样片
  特例、format denylist、winner-specific requery 或第二 detector。
- 24-source clean-commit 正式性能继续以 5 秒 mean 为阻断 Gate，并检查 3 秒不阻断目标；精确数值、
  commit 与机器 identity 只以 `build/v5-performance/performance_receipt.json` 为准。黄金 diagnostic 时间
  不充当性能证据。
- 当前黄金仍只有 `135` 57、`120-66` 32、`120-67` 3、`half` 14 个 unique source；尚无 `xpan`、
  `120-645`、`135-dual`。全部都是可查看的 development gold，不证明未见扫描泛化或 release readiness。

## 开放风险

- 96 个 nominal 中仍有 84 个 review。22 个直接角色权限缺口说明机器看见了局部 edge，却没有足够的
  material 或 fixed-W 关系让它决定裁切；不能通过恢复弱线单独授权来消除失败。
- 当前 separator material authority 仍只接受暗谷。亮 separator、欠曝或阴影中的弱边缘，以及宽缓
  outer/cross material transition 仍缺少通用 observation；它们必须依次闭环，不能合并成平行 detector。
- 当前开发集不能事后兼任概率 calibration 或 sealed acceptance。未来 scorer 仍需预先冻结的新数据、
  OOD、abstention 和独立风险阈值；当前不创建占位评分器。

## 精确下一步

1. 在现有 registered measurement owner 内增加 typed `SeparatorMaterialPolarity = dark | light`；两种
   polarity 都必须由两侧直接 edge、至少三个独立高度区域和一致 material 状态共同证明，冲突保持
   unresolved。
2. 固定该机制的真值表、唯一 owner、typed failure、Debug、最小亮 band 正例与照片内部亮带安全反例；
   只用少量相关真实样片验证后再运行完整黄金集和性能 Gate。
3. 该检查点闭合并推送后，才分别进入弱边缘跨高度联合观察、宽缓 outer/cross material observation；
   不恢复 enhanced detector、fallback 或未经校准且拥有最终决定权的 score。
