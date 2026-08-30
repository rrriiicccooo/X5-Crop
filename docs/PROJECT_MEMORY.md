# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三阶段提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的目标是全部安全
`approved_auto`。不得改样片角色、放宽黄金合同、隐藏 runner 或牺牲正式 mean `<= 5s` 来提高覆盖。

每个阶段只闭合一个通用物理机制，并同时交付合同与真值表、canonical owner、typed evidence/failure、
Debug、正反例、少量真实样片和完整黄金验收。当前第 1 阶段已闭合全局 lattice authority 与逐 adjacency
coverage；下一阶段只完善 candidate-independent 查询走廊。

## 已验证事实

- 黄金集为 106 个唯一 source SHA、110 个显式 count task：96 个 nominal、14 个 challenge；优化分层为
  66 / 30 / 14。全部 task 已人工确认，同源 count 变体共享物理边界但独立验证。
- 当前 detector source manifest `73915a17b1fd21b6` 的黄金分析为 110/110 完成、分析错误 0、危险自动
  批准 0。安全 `approved_auto` 为 11 个：基础 nominal 10/66、较难 nominal 1/30；14 个 challenge 均
  安全 review。Candidate 为 79 个不可用、23 个安全、8 个不安全；Review candidate 只作机制诊断。
- 缺失 separator 只有在直接约束矩阵以 rank 3 独立闭合 `(phase, W, pitch)`、该 adjacency 的完整传播
  走廊被预登记 query 逐 trace 覆盖、且没有直接反证时，才能按 `local_delta = 0` 使用 Grid。运行时不再
  使用 raw edge 数、连续缺失数或全局 query-complete 布尔值代替证明。
- 当前 typed phase root failure 为 `adjacency_observation_coverage_incomplete` 23 个、
  `global_lattice_authority_unavailable` 9 个；旧 `phase_support_discontinuity` 已删除。S004 因走廊不完整、
  S081 因 rank 2 从旧安全 auto 转为安全 review；这是被新基础设施揭示的证明缺口，不是通过率回归掩盖。
  S089 不再被连续缺失数阻断，但仍由其它独立合同保持 review。
- 真实机制检查覆盖 S001/S013 的 rank 3 + 完整 coverage、S046 的 coverage incomplete、S081 的 rank 2；
  wide/narrow local advance 与 contact/overlap/conflict 的安全反例由同一 residual owner 验证，没有样片特例。
- 24-source clean-commit 正式性能仍通过 5 秒 mean Gate，并达到不阻断的 3 秒 mean 目标。精确数值与
  commit identity 以 `build/v5-performance/performance_receipt.json` 为准；黄金 diagnostic 时间不充当
  性能证据。
- 当前黄金仍只有 `135` 57、`120-66` 32、`120-67` 3、`half` 14 个 unique source；尚无 `xpan`、
  `120-645`、`135-dual`。全部都是可查看的 development gold，不证明未见扫描泛化或 release readiness。

## 开放风险

- 96 个 nominal 中仍有 85 个 review。23 个 adjacency coverage failure 应通过扩大或重排既有
  candidate-independent ownership 走廊解决，不能改为 winner-specific requery，也不能放宽 Gate。
- 9 个 global lattice authority failure 代表独立未知量尚未闭合；增加同位置 edge 数没有意义，必须补充
  真正独立的 phase、W 或 pitch 观察。
- 当前开发集不能事后兼任概率校准或 sealed acceptance。未来 scorer 仍需预先冻结的新 calibration 与
  sealed source、OOD、abstention 和独立风险阈值；当前不创建占位评分器。

## 精确下一步

1. 以 23 个 coverage failure 为机制集合，核对每个 `required_interval` 与现有 query ownership 的差集，
   只完善候选无关 `SEQUENCE_ANCHOR_WINDOW`，不增加 TIFF 重读或 selected-placement 查询。
2. 用 rank 3 + complete/incomplete 的最小正反例和 S004、S046 等少量真实样片确认 coverage 提升；保持
   global authority、direct counterevidence、uncertainty 与 Gate 不变。
3. 完整黄金继续要求 `unsafe_approved_auto = 0`，再比较 nominal 覆盖、challenge 能力、typed root
   migration 与性能。第 2 阶段闭合后单独提交推送，之后才进入弱边缘/片距变化与 challenge 拓扑。
