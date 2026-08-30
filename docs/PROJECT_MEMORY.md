# 项目记忆

更新：2026-08-31。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三层提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的目标是全部安全
`approved_auto`。不得改样片角色、放宽黄金合同、缩窄真实物理先验、隐藏 runner，或牺牲正式
mean `<= 5s` 来提高覆盖；3 秒 mean 是持续优化目标。

每次只闭合一个通用物理机制，并同时交付合同与真值表、canonical owner、typed evidence/failure、
Debug、正反例、少量真实样片、完整黄金验收和性能。已闭合全局 lattice authority、逐 adjacency
coverage、候选无关查询走廊、polarity-complete separator、跨高度弱边缘、source-level W/H direct
aperture、有界的 W/H compatibility 与 aspect-ratio authority，以及不依赖比例推导的 fixed-H enclosing
support。Contact/overlap 以后仍只扩展同一 adjacency/placement 模型。

## 当前检查点

- 检测检查点 `728450da` 修正唯一 `ENCLOSING_SUPPORT_PAIR` 的权限：它只由 source fixed H、canonical H、
  两条直接支撑和 `1.1H` 上限闭合，不再错误依赖或消费只服务缺失 aperture side 的比例推导。
  S083、S092 因此取得安全 enclosing candidate，但仍由真实的 source-footprint 越界阻断；S001、S024、
  S002 与 S012 等反例继续 review。
- 同 commit 的完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto
  为基础 nominal 6/66、较难 nominal 0/30、challenge 0/14；基础 nominal candidate 为 47 个不可用、
  13 个安全、6 个不安全，所有不安全 candidate 均保持 review。安全 auto 为 S022、S025、S063、S081、
  S095、S103；全部 challenge 均安全 review。
- 黄金 receipt 的 detector、comparator 与 cohort 均精确匹配 `728450da`；detector manifest 为
  `9b0d6a6dba78286219ade8c718b79993f5838bf84a193e15788e632ddff5d5da`。24-source 正式性能 mean 为
  2.944 秒，5 秒 Gate 通过，3 秒 non-blocking 目标达到；receipt 位于
  `build/v5-performance/performance_receipt.json`，只证明该 commit、依赖和 M2 Max 主机。

## 当前物理证据

- W/H guard 使用 105 个合格 source、494 个完整 Frame 校准。只接受 `slot_kind=image` 且 START、END、
  共享 top/bottom 全为 `directly_visible` 的 Frame；按 source 取中位尺寸、按名义轴长计算绝对偏差 q95，
  再拟合一个混合式并向外量化。运行时公式与完整黄金重算一致。S095 的 W，以及 S021、S086、
  S098 的 H 位于 q95 guard 外；它们是 review 证据，不是 format 例外。
- `135`、`half`、`120-66`、`120-67` 已注册 raw aspect calibration；`xpan`、`120-645` 没有合格黄金
  observation，保持 unavailable。`120-67` 只有 3 个 source，不能据此宣称已泛化。
- Catalog separator gap 只适合作搜索中心。黄金实际 gap 的变化大且非对称，不能复用 aperture mixed
  guard；实际宽度仍由直接 material edges 与 local advance 拥有。以后扩大召回应单独校准候选无关的
  非对称搜索 coverage。
- Holder extent 仍是外部设计先验 ±3.5%。同一批 holder-normalized 黄金尺寸不能独立校准 holder 自身；
  `1.1H` enclosing support、lattice residual、mixed bleed 与逐侧 5% 输出上限继续由各自物理含义拥有。

## 开放风险

- 基础 nominal 仍有 60/66 review。当前完整集有 29 个 `discrete_phase_ambiguous`、16 个
  `non-equivalent cross fits remain`、15 个 direct fixed-H mismatch 与 4 个 aspect-ratio budget
  exhaustion。较宽真实先验暴露的竞争必须由观察 identity、权限或安全预算闭合；不得靠缩窄 guard、
  恢复精确 W→H 或改 challenge 分类取回数字。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 先让 registration 成为 same-role cross family identity 的唯一 owner：只有一次重拟合精确保留完整
   transition union 时才形成 canonical track，并删除 selection 后的平行 broader/local 权限；不能按邻近、
   residual、方向相似或 score 合并。S013 的两个完整离散 bottom 闭环是必须保留的反例。
2. 再闭合 complementary-domain direct pair：top/bottom 各自直接、方向与 fixed H 相容、各有独立区域，
   且两侧 domain union 完整覆盖 template 时可以形成唯一闭环；共享 trace 仍记为 0。S064 是当前正例，
   缺 domain、支持不足或存在多个完整闭环时继续 review。
3. 独立审计 S083、S092、S091 等安全 candidate 的 source-footprint 越界；source containment 仍是硬合同，
   先区分真实输入不足、基础 bleed 不可满足与 authority 过窄，不能以静默裁小换取 auto。之后再处理离散
   phase、候选无关 separator coverage、局部片距与 contact/overlap challenge。
