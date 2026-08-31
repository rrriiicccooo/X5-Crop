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
support、直接坐标权限、coordinate/evidence identity 分离和真实 TIFF 外缘的显式 source saturation。
Contact/overlap 以后仍只扩展同一 adjacency/placement 模型。

## 当前检查点

- `11e0e7a6` 将 sequence coordinate `observation_id` 与相关 `evidence_group_id` 分离。只有相同
  coordinate identity 可以合并连续 placement；共享 material group 只用于证据去重，不能隐藏不同坐标
  runner。旧字段已删除，report revision 为 `x5crop_v5_template_report_28`；类型、owner、Debug、外部
  report validator 与正反例使用同一 current-only schema。
- 完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础
  nominal 14/66、较难 nominal 2/30、challenge 0/14；基础 nominal candidate 为 50 个不可用、14 个安全、
  2 个不安全。S017、S051 的不安全 candidate 均被 direct-use budget 阻断；全部 challenge 安全 review。
  安全 auto 共 16 个：S003、S022、S025、S059、S063、S064、S067、S081、S083、S084、S085、
  S087、S089、S092、S094、S095。
- S029 的旧批准依赖把同一 material group 中 14325.97px 与 14386.36px 两个 START 当成同一坐标；后者
  相对黄金基线会向内裁切约 63.5px。当前明确保留 runner 并返回 `discrete_phase_ambiguous`。S002、S015、
  S024、S030、S047 终态仍为 review，只把 root failure 前移到同一真实 phase 歧义。
- 黄金 receipt 精确匹配 `11e0e7a6`；detector manifest 为
  `8b7d361953ba7792612dfad29a35c5f167f4b689e684ecab7f0f4dc40836b05e`，comparator manifest 为
  `3bd4218ed1b752ac5b47b9c7ea124d2d795095e8f5938590e69fef464995e969`，cohort SHA-256 为
  `c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。黄金 summary SHA-256 为
  `35d463e89cbbb0c0712ef623de5315b2028fa66ef730960ddeb79aba3e41bb1b`。
- 同 commit 的 24-source 正式性能 mean 为 2.947 秒，p95 为 5.064 秒，最慢 S109 为 5.476 秒；5 秒
  mean Gate 通过，3 秒 non-blocking 目标达到。性能 receipt SHA-256 为
  `f90d6a103990eae5c7d0760c7dca1a3b0df8fb690a009c5c7585df1f4f722546`；receipt 只证明记录的依赖与
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

- 基础 nominal 仍有 52/66 review，较难 nominal 有 28/30 review。当前完整集的 phase 根因包括 28 个
  `direct_role_binding_authority_unavailable`、13 个 `discrete_phase_ambiguous`、11 个
  `frame_width_inference_unavailable`、8 个 `global_lattice_authority_unavailable`、5 个
  `separator_material_conflict` 与 5 个 `fixed_template_mismatch`。竞争必须由新的直接 observation identity、
  权限或相关安全状态闭合；不得恢复 W 自授权、缩窄 guard、精确 W→H 或改 challenge 分类。
- S017、S051 是仅有的两个不安全 candidate，并继续由 `direct_use_budget_exceeded` 阻断；其余 92 个
  review task 没有 selected candidate，不能把“没有输出”误当成精度问题。
- `lane_preparation.py` 仍在最终直接角色权限和离散竞争闭合前校准 source W、重编译模板，再把该 W 作为
  global lattice evidence。黄金结果当前安全，但这个顺序让相关 W 可能参与选择自己的 source placement，
  是下一项必须消除的循环权限，而不是通过率工具。
- 当前黄金同时参与 development calibration 与 development 验收，只能证明该集合上的安全与可复算性；
  尚无 sealed acceptance，也没有 `xpan`、`120-645`、`135-dual` 的独立黄金覆盖。
- 当前开发集不能事后兼任概率 calibration。未来 scorer 仍需预先冻结的新数据、OOD、abstention 和独立
  风险阈值。

## 精确下一步

1. 删除 pre-selection source-W calibration/recompile 路径。Bounded candidate 必须先只凭直接角色权限和
   独立 lattice facts 完成离散竞争；唯一 placement、全局 rank、adjacency coverage、outer authority 与
   topology 闭合后，才允许 selected-only source W 校准和相关 opposite 推断。W 不得删除 runner、改变
   ordinal 或把自己写回选择证据。
2. 上述安全顺序稳定后，再为每个 bounded candidate 增加对称的 authority projection：只删除
   `unavailable` binding、绝不删除 `contradicted`，保留的直接角色必须重新独立闭合 rank 3；随后全部投影
   candidate 重新 canonicalize 并竞争。它不能生成双侧都未观察的 Frame，也不能让 validation-only 弱线
   增加 rank、收窄 W 或决定 winner。
