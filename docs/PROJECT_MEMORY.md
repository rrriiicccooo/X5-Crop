# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三层提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的目标是全部安全
`approved_auto`。不得改样片角色、放宽黄金合同、隐藏 runner 或牺牲正式 mean `<= 5s` 来提高覆盖。

每次只闭合一个通用物理机制，并同时交付合同与真值表、canonical owner、typed evidence/failure、
Debug、正反例、少量真实样片和完整黄金验收。全局 lattice authority、逐 adjacency coverage、完整
候选无关查询走廊、polarity-complete separator material 和跨高度弱边缘联合观察已经闭合。先继续完成
nominal 检测能力；Contact/Overlap 随后只扩展同一 adjacency/placement 模型，不建立第二套 detector。

## 已验证事实

- 黄金集为 106 个唯一 source SHA、110 个显式 count task：96 个 nominal、14 个 challenge；优化分层为
  66 / 30 / 14。全部 task 已人工确认，同源 count 变体共享物理边界但独立验证。
- 当前 detector source manifest `550c8672bd5eaf14` 的黄金分析为 110/110 完成、分析错误 0、危险自动
  批准 0。安全 `approved_auto` 为 10 个，全部位于基础 nominal：10/66；较难 nominal 为 0/30，14 个
  challenge 均安全 review。全部 candidate 为 85 个不可用、19 个安全、6 个不安全；其中 review candidate
  为 85 个不可用、9 个安全、6 个不安全，只作机制诊断。
- `SequenceAnchorDiscoveryDomain` 从左右 holder 端分别投影完整且相关的 `W/pitch` 状态，合并并预登记
  全部候选无关 role corridor；不增加 TIFF 读取，不读取 winner。原 23 个
  `adjacency_observation_coverage_incomplete` 已归零，S004 恢复为安全 auto。
- Separator material 由同一个 registered measurement owner 同时观察 dark/light polarity、两侧相邻
  edge、逐高度 oriented contrast 与 core texture。局部两区域 support 不冒充 source-wide authority；
  完整三区域反证和同角色竞争产生 typed `separator_material_conflict`。超出 normal gap 的 material 保留
  原始事实，但不能自创 phase、ordinal 或直接角色权限。
- 同一 registered sequence window 还把既有 trace 固定分成三个高度区域，联合 signed gradient、tone、
  texture 和 polarity。只有三区域一致且唯一绑定一条已有局部 direct edge 时，才以
  `cross_height_union` 授予同一坐标一份相关权限；standalone、重复和多解联合线只进入 report/Debug。
  该机制让 S007、S016、S017、S026、S033、S049、S074、S102 越过原直接角色根因并暴露下游事实，未
  增加自动批准或 TIFF 读取。
- 当前 typed phase root failure 为 `direct_role_binding_authority_unavailable` 16、
  `discrete_phase_ambiguous` 24、`separator_material_conflict` 7、`fixed_template_mismatch` 8、
  `outer_frame_observation_authority_unavailable` 5、`local_advance_ambiguous` 4 和
  `global_lattice_authority_unavailable` 2。S075、S089 的同角色冲突安全进入 review；S080 的照片内部亮带
  没有误伤合法边界。失败迁移来自通用证据合同，没有样片特例、format denylist、winner-specific requery
  或第二 detector。
- 24-source clean-commit 正式性能继续以 5 秒 mean 为阻断 Gate，并检查 3 秒不阻断目标；精确数值、
  commit 与机器 identity 只以 `build/v5-performance/performance_receipt.json` 为准。黄金 diagnostic 时间
  不充当性能证据。
- 当前黄金仍只有 `135` 57、`120-66` 32、`120-67` 3、`half` 14 个 unique source；尚无 `xpan`、
  `120-645`、`135-dual`。全部都是可查看的 development gold，不证明未见扫描泛化或 release readiness。

## 开放风险

- 96 个 nominal 中仍有 86 个 review。基础 nominal 主要缺口是 14 个离散 phase 竞争、10 个直接角色
  权限不足、4 个 material 冲突，以及少量 cross/outer/W 闭合；不能通过恢复弱线单独授权或放宽 Grid
  消除失败。
- Polarity-complete observation 揭示了两个原有证明缺口：S003 的直接末端使实际 Frame width 低于当前
  fixed-W 下界，S073 的直接 separator gap 超出当前 normal 上界；二者都安全回到 review。黄金物理统计
  还显示多个 format 的直接 Frame ratio 与 separator gap 系统性超出当前先验，必须区分设计尺寸、真实
  aperture 变化和 observation uncertainty 后再调整 canonical prior，不能直接扩大容差。
- 联合弱线已经能安全加强已有局部 direct edge，但纯 standalone 联合线仍没有 phase/outer 权限；只有
  新的独立物理闭环才能扩大权限。宽缓 outer/cross material transition 尚未 typed 闭合，不能用联合线
  或 enhanced detector 代替。
- 当前开发集不能事后兼任概率 calibration 或 sealed acceptance。未来 scorer 仍需预先冻结的新数据、
  OOD、abstention 和独立风险阈值；当前不创建占位评分器。

## 精确下一步

1. 单独审计并闭合 W、separator gap 与真实 aperture 的 authority。黄金分布只提出偏差，不能直接生成
   runtime 常量；任何 prior 修正都须有物理 owner、反例、Debug、全黄金安全与性能证明。
2. 再闭合宽缓 outer/cross material transition。Nominal 能力完成后，依次实现 adjacency continuity
   negative、contact、overlap；三者共用 `AdjacencyRelation`、O(count) `local_prefix` 和统一 5% 输出预算，
   不建立异常图专用 detector 或独立 bleed 预算。
