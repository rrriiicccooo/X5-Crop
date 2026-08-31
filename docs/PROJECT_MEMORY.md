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

- `0075cc75` 把 `DirectRoleBindingAuthority` 前移到 bounded phase candidate 的离散竞争之前。全部
  candidate 对称使用同一预索引 evidence ledger；无权或 material-contradicted runner 保留在 report 与
  Debug，但不能阻断有权 candidate。若没有有权 candidate，返回 best 自身的 typed failure；两个均有权
  的真实竞争继续 `discrete_phase_ambiguous`。S059 因此安全 auto，S027、S075、S088 仍保守 review。
- 完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础
  nominal 15/66、较难 nominal 2/30、challenge 0/14；基础 nominal candidate 为 49 个不可用、15 个安全、
  2 个不安全。S017、S051 的不安全 candidate 均被 direct-use budget 阻断；全部 challenge 安全 review。
  安全 auto 共 17 个：S003、S022、S025、S029、S059、S063、S064、S067、S081、S083、S084、S085、
  S087、S089、S092、S094、S095。
- 黄金 receipt 精确匹配 `0075cc75`；detector manifest 为
  `9dca9de929648b177d1a236f86353fd7e22be0479be1a1ca39d6e0d3b62610c4`，comparator manifest 为
  `ad5e68cb34b121b29a53b5fc5485a9d32cb11a7ae2c14d27c921c8d1ff59ced4`，cohort SHA-256 为
  `c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。黄金 summary SHA-256 为
  `6b57552b598b276f45b02f70ee4f68349f3d0bba1fa793b1c8ff999ed8127b69`。
- 同 commit 的 24-source 正式性能 mean 为 3.384 秒，p95 为 5.716 秒，最慢 S109 为 6.124 秒；5 秒
  mean Gate 通过，3 秒 non-blocking 目标未达到。性能 receipt SHA-256 为
  `370dfa0960999e0553e586e55e3f82a00141ebe3bf39e368cc59dae37243bc7e`；receipt 只证明记录的依赖与
  M2 Max 主机。

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

- 基础 nominal 仍有 51/66 review，较难 nominal 有 28/30 review。当前完整集的 phase 根因包括 28 个
  `direct_role_binding_authority_unavailable`、12 个 `frame_width_inference_unavailable`、8 个
  `global_lattice_authority_unavailable`、7 个 `discrete_phase_ambiguous`、5 个
  `separator_material_conflict` 与 5 个 `fixed_template_mismatch`。竞争必须由新的直接 observation identity、
  权限或相关安全状态闭合；不得恢复 W 自授权、缩窄 guard、精确 W→H 或改 challenge 分类。
- S017、S051 是仅有的两个不安全 candidate，并继续由 `direct_use_budget_exceeded` 阻断；其余 91 个
  review task 没有 selected candidate，不能把“没有输出”误当成精度问题。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 只读拆分剩余 7 个 `discrete_phase_ambiguous`：S027、S034、S050、S052、S061、S075、S088。S027、
   S075、S088 已知两侧 candidate 均有权限；不得用 residual 或未经校准 score 强选。重点确认 S034/S052
   是否来自 separator 两侧的 physical identity 未闭合，challenge S050/S061 只作能力观察。
2. 对基础 nominal 的 16 个 `direct_role_binding_authority_unavailable` 按缺失 basis 分组，选择覆盖最大的
   一个候选无关 observation identity 小机制。新增权限只能来自同一 registered 像素的 source-wide、跨高度
   或 separator physical identity，不能让两个弱局部边界重新凭 W 互相授权。
