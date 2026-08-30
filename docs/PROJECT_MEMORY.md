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
aperture，以及有界的 W/H compatibility 与 aspect-ratio authority。Contact/overlap 以后仍只扩展同一
adjacency/placement 模型。

## 当前检查点

- `2d9fbf9c` 已推送：全部 format 通过同一个 mixed guard 计算 W/H compatibility；
  `guard_W=max(0.95 mm, 2.4%W)`，`guard_H=max(0.70 mm, 1.8%H)`，没有 `half` 或样片例外。
  `ApertureAspectRatioAuthority` 用分格式 raw W/H 包络与两轴 guard 推导 rank 0 相关 H；direct H 优先，
  authority 不足、physical-prior/direct conflict 和 5% 预算耗尽均为 typed review。Report revision 为
  `x5crop_v5_template_report_19`。Cross 注册超界也改为 `producer_bound_exceeded`，不再崩溃或截断。
- 同 commit 的 pre-push Hook 为 564 项通过、2 项按设计跳过。完整 development gold 为 110/110
  完成、分析错误 0、`unsafe_approved_auto = 0`；安全 auto 为基础 nominal 4/66、较难 nominal 0/30、
  challenge 0/14。九个 candidate 安全、五个不安全、96 个不可用；五个不安全 candidate 全部保持
  review。安全 auto 为 S022、S025、S063、S081；全部 challenge 均安全 review。
- 黄金 receipt 的 detector、comparator 与 cohort 均精确匹配该 commit；detector manifest 为
  `58bd8e25c53fa4cd3072ed3bad6850afe345d0823df75ce6281e34c672979298`。24-source 正式性能 mean 为
  2.966 秒，5 秒 Gate 通过，3 秒 non-blocking 目标已达到；receipt 位于
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

- 基础 nominal 仍有 62/66 review。较宽且真实的 W/H guard 揭示了旧窄 prior 曾排除的竞争解释：完整集
  当前有 29 个 `discrete_phase_ambiguous`、42 个 non-equivalent cross fit、34 个 direct H mismatch，
  另有 10 个 aspect-ratio budget exhaustion。旧检查点的 10 个基础安全 auto 变为当前 4 个，不是危险
  放行回归；不得靠缩窄 guard、恢复精确 W→H 或改 challenge 分类取回数字。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 对旧 10 个与当前 4 个安全 auto 做机制迁移，先闭合由真实 W/H 范围暴露的离散 phase 与 cross
   竞争。优先让已有直接 START/END、separator pair 与 source-wide top/bottom 获得正确权限，不调窄
   compatibility，也不引入 score。
2. 单独建立 separator 的非对称、候选无关搜索 coverage 合同；它只提高正确位置的观察覆盖，不改变
   direct local gap，不与 aperture 或 holder tolerance 合并。
3. 基础 nominal 稳定后再处理弱边缘与局部片距变化，最后按既定顺序闭合 contact/overlap challenge。
