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

- 检测检查点 `d062703b` 让 registration 成为 same-role Cross family identity 的唯一 owner：只有一次
  refit 精确保留完整 transition union 才合并 fragment，旧 selection-time containment/dominance 权限已经
  删除。Direct top/bottom 还可在两侧各自拥有独立区域、domain union 覆盖全部 selected Frame、方向与
  fixed H 相容时，以 `complementary_domains` 形成闭环；它不伪造 shared trace。
- 同一检查点加入通用外侧反证：若某个完整 pair 的同一 opposite 还能与严格更外侧的直接局部 role
  闭合，内侧 pair 产生 `outward_role_counterevidence`；若外侧 pair 也完整，则保留两者竞争。Source-wide
  单侧不得把没有覆盖全部 selected domain 的局部 opposite 外推。S018、S062 因此安全 review，S064
  取得安全 auto；没有样片特例或 score。
- 完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础
  nominal 8/66、较难 nominal 1/30、challenge 0/14；基础 nominal candidate 为 47 个不可用、15 个安全、
  4 个不安全，较难 nominal 为 26 个不可用、3 个安全、1 个不安全，所有不安全 candidate 均保持 review。
  安全 auto 为 S022、S025、S063、S064、S067、S081、S087、S095、S103；全部 challenge 均安全 review。
- 黄金 receipt 的 detector、comparator 与 cohort 均精确匹配 `d062703b`；detector manifest 为
  `81a6c33c07fdad76b1d3e34fac76ab27f5dbe712a1f41942b4d940bed503d848`。24-source 正式性能 mean 为
  2.711 秒，最慢 S109 为 4.740 秒，5 秒 Gate 通过且 3 秒 non-blocking 目标达到；receipt 位于
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

- 基础 nominal 仍有 58/66 review，较难 nominal 有 29/30 review。当前完整集有 29 个
  `discrete_phase_ambiguous`、17 个 `non_equivalent_fits`、11 个
  `direct_role_binding_authority_unavailable` 和 7 个 `aperture_aspect_ratio_budget_exhausted`。较宽真实先验
  暴露的竞争必须由观察 identity、权限或安全预算闭合；不得靠缩窄 guard、恢复精确 W→H 或改 challenge
  分类取回数字。
- 仍有 9 个几何安全但最终 review 的 candidate：S015、S083、S084、S085、S091、S092、S093、S094、
  S099；另有 S012、S013、S017、S088、S098 五个不安全 candidate 被正确阻断。前者是后续权限机制的
  正例，后者必须作为同机制的安全反例，不能把 candidate 安全混同于可自动批准。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 先闭合 source-lane/output-footprint 权限：以 S083、S084、S085、S092、S094 等安全 candidate 为正例，
   以 S088 的危险 candidate 及真实 source truncation 为反例，区分输入确实不足、已有 enclosing authority
   未传播和 bleed 无法容纳；source containment 保持硬合同，不能静默裁小。
2. 再审计 `direct_use_budget_exceeded`：S015、S091、S099 是安全正例，S012、S013、S017、S098 是安全
   反例。只允许修正同一 placement 的相关 uncertainty、residual 与逐侧预算 owner，不扩大 5% 产品上限，
   也不把不能同时发生的误差分别相加。
3. 随后按独立未知量而非样片数量拆解 `discrete_phase_ambiguous` 与 `non_equivalent_fits`，依次完善
   candidate-independent separator coverage、局部片距和弱边缘权限；contact/overlap 仍在 nominal 机制
   稳定后作为同一 adjacency 模型的 challenge 扩展。
