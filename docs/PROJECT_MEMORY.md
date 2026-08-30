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
support、直接坐标权限和真实 TIFF 外缘的显式 source saturation。Contact/overlap 以后仍只扩展同一
adjacency/placement 模型。

## 当前检查点

- `6a121ab1` 删除两条局部 start/end 仅凭彼此间距与 W prior 互相授予 native coordinate 权限的循环。
  已观察坐标只接受 source-wide edge、跨高度联合或同一 separator pair；独立闭合 W 只推导真正缺失的
  opposite。S088 因弱局部线失去自授权而在 placement 前安全 review。
- `b54ac17f` 把输出保护拆为 mandatory、完整 requested 与实际 required 三层 polygon。真实 TIFF 外缘
  显式限定不存在的源像素，并区分 optional bleed 与 joint protection saturation；内部 dual-lane 边界
  两种情况都继续阻断。5% 预算使用未限定 requested 层，Debug 与 report 保留完整请求、kind 和越界距离。
  S083、S084、S085、S092 因此安全 auto；S088 仍无 placement。
- `b7ab6d40` 修正 enclosing support 的 direct-use 预算：top/bottom 各自完整 expansion 继续受逐侧
  5% 限制，support span 继续受 `1.1H` 限制；联合项只计算同一可行状态中额外的直线 alignment
  padding，不再重复收费 support 位置 uncertainty 或相加互斥极值。S094 因此安全 auto；S017 的真实
  超预算候选仍被 Gate 阻断。
- `ca6d2d23` 增加一次性 `partial_height_separator_pair` 权限：两个高度区域的 normal separator 只有在
  一侧已具完整直接权限时，才向同一 adjacency 的另一侧传递 native coordinate；传递不能级联，最终还
  必须由两侧直接 `aperture_pair` 闭合短轴。S029、S081 因此安全 auto；S012、S015、S091、S098、S099
  保守停在 typed `direct_role_aperture_domain_unavailable`。
- 完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础
  nominal 13/66、较难 nominal 1/30、challenge 0/14；基础 nominal candidate 为 52 个不可用、13 个安全、
  1 个不安全，较难 nominal 为 29 个不可用、1 个安全。安全 auto 为 S022、S025、S029、S063、S064、
  S067、S081、S083、S084、S085、S087、S092、S094、S095；全部 challenge 均安全 review。
- 黄金 receipt 的 detector、comparator 与 cohort 均精确匹配 `ca6d2d23`；detector manifest 为
  `8d1e26ab8d5978c6b38cf0f400ebbd0bf68de59c3e0b833384657b6f2e15713f`，comparator manifest 为
  `199d6ee95247f11ffa3cab159b9458d0e3a642d7bf9b7fe619a83223a1e66457`。24-source 正式性能 mean 为
  2.795 秒，p95 为 4.591 秒，最慢 S109 为 4.824 秒；5 秒 Gate 通过且 3 秒 non-blocking 目标达到。
  Receipt 只证明该 commit、记录的依赖和 M2 Max 主机。

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

- 基础 nominal 仍有 53/66 review，较难 nominal 有 29/30 review。当前完整集有 23 个
  `direct_role_binding_authority_unavailable`、5 个 `direct_role_aperture_domain_unavailable`、29 个
  `discrete_phase_ambiguous`、17 个 `non_equivalent_fits`、14 个 placement-level
  `phase_template_mismatch`、6 个 `global_lattice_authority_unavailable` 与 6 个
  `aperture_aspect_ratio_budget_exhausted`。竞争必须由新的直接观察 identity、权限或相关安全状态闭合；
  不得恢复 W 自授权、缩窄 guard、精确 W→H 或改 challenge 分类。
- 当前唯一不安全 candidate 是 S017，并继续由 `direct_use_budget_exceeded` 阻断；其余 95 个 task 没有
  selected candidate，不能把“没有输出”误当成精度问题。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 拆解剩余 23 个 `direct_role_binding_authority_unavailable`，区分未成对短 edge、outer role 与真正的
   observation 缺失。新增能力必须来自同一 registered 像素的通用 source-wide、跨高度或 separator
   physical identity，不能让两个弱局部边界重新凭 W 互相授权。
2. 随后按独立未知量拆解 `discrete_phase_ambiguous` 与 `non_equivalent_fits`，完善候选无关 separator
   coverage、局部片距和弱边缘权限；contact/overlap 仍在 nominal 机制稳定后作为同一 adjacency 模型扩展。
