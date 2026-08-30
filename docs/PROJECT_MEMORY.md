# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三层提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的目标是全部安全
`approved_auto`。不得改样片角色、放宽黄金合同、隐藏 runner，或牺牲正式 mean `<= 5s` 来提高覆盖；
3 秒 mean 是持续优化目标。

每次只闭合一个通用物理机制，并同时交付合同与真值表、canonical owner、typed evidence/failure、
Debug、正反例、少量真实样片、完整黄金验收和性能。已闭合全局 lattice authority、逐 adjacency
coverage、候选无关查询走廊、polarity-complete separator、跨高度弱边缘，以及 source-level W/H direct
aperture。Contact/overlap 以后仍只扩展同一 adjacency/placement 模型。

## 当前检查点

- `f8760091` 已推送：format W/H 改为分格式、可非对称的跨相机先验；`half` W 下界为名义值的 96.5%。
  唯一 placement 中至少两张完整直接 Frame 可闭合 source W，并以一份相关 W 推断多个单侧 opposite；
  双侧都不可见的 Frame 明确失败。Direct top/bottom pair 独立收紧 source H，旧的零不确定性 W→H 精确
  换算已删除。Report revision 为 `x5crop_v5_template_report_18`。
- Pre-push Hook 为 549 项通过、2 项按设计跳过。完整 development gold 精确绑定该 commit，110/110
  完成、分析错误 0、`unsafe_approved_auto = 0`；安全 auto 为基础 nominal 10/66、较难 nominal 0/30、
  challenge 0/14。Candidate 为 86 个不可用、18 个安全、6 个不安全，全部不安全 candidate 保持 review。
  Detector source manifest 为 `715e3ee958355eb9d5b76ea983680d07c755c4ad5f88b6a1692030ad493a2b41`。
- S003 因 source W 的相关多角色推断从 review 安全进入 auto；S087 因旧精确 W→H 换算被删除而由
  `content_veto` 安全回到 review。两者一进一退，基础 nominal 总覆盖仍为 10/66。
- 同 commit 的 24-source 正式性能 mean 为 3.437 秒，5 秒 Gate 通过；3 秒不阻断目标未达到。权威 receipt
  位于 `build/v5-performance/performance_receipt.json`，只证明其记录的 commit、依赖和 M2 Max 主机。

## 黄金物理事实

- 黄金红线是尽量贴近该 source 真实有效成像边界的验收基线，基本可作为 source aperture 尺寸观测；
  它能校准分布与 source-level authority，但不是跨相机绝对固定常量。
- 106 个唯一 source 的直接 W/H 均落入当前 runtime pixel prior：`135` 289/289、`120-66` 88/88、
  `120-67` 9/9、`half` 108/108。该结论包含 holder scale uncertainty，不等于 catalog mm 是精确真值。
- H 的跨 source / 同源 variation ratio 在四个已覆盖 format 中为 2.71–8.71。W 在 `135`、`120-66`、
  `half` 为 1.16、2.34、5.13；`120-67` 只有 3 个 source 且 ratio 为 0.05，不能据此泛化。
- 直接 Frame aspect ratio 低于现有 catalog interval 的数量为：`135` 76/289、`120-66` 2/88、
  `120-67` 7/9、`half` 49/108。Format ratio 是有效强先验，但必须用区间而非精确常量。
- 同源 separator gap 的相对 RMS 为 0.15–0.38，pitch 为 0.010–0.018。Gap 的局部变化远大于 pitch，
  继续支持“source pitch + direct local advance”，不支持一个 source-common 固定 gap。

## 开放风险

- 基础 nominal 仍有 56/66 review：主要 phase root 为 14 个离散 phase、7 个直接角色权限不足、4 个
  separator material conflict、4 个 W 推断权限不足；cross 另有 6 个非等价 fit、6 个空间支持不足和
  5 个 direct H 冲突。不能用 Grid 自证、弱线单独授权或隐藏 runner 消除。
- `ApertureAspectRatioAuthority` 尚未实现。S087 的迁移说明旧精确等式不安全，但 W/H 仍受 format 比例
  约束；当前保守 review 不能被误写成“两轴永久独立”。
- 当前黄金只覆盖 `135` 57、`120-66` 32、`120-67` 3、`half` 14 个 unique source；尚无 `xpan`、
  `120-645`、`135-dual`，也没有 sealed acceptance。Development gold 不证明未见扫描泛化或发布就绪。
- 当前开发集不能事后兼任概率 calibration 或 sealed acceptance。未来 scorer 仍需预先冻结的新数据、
  OOD、abstention 和独立风险阈值。

## 精确下一步

1. 以 `ApertureAspectRatioAuthority` 作为下一个小机制闭环。用全部 development gold 的 source-level
   W/H 比例分布建立 format-specific `R_interval`；由 source W、两轴 scale authority 与该区间推导相关
   H interval。它不能冒充 direct H、增加 constraint rank、选择 phase/ordinal 或创造双侧不可见 Frame。
2. 同批交付 canonical type/owner、`authority_unavailable`、`direct_conflict`、`budget_exhausted` typed
   failure、Report/Debug、合成正反例，并用 S087 等少量真实样片验证。比例不闭合、多解、与 direct H
   冲突或耗尽 5% 预算时保持 review。
3. 再运行完整黄金集与正式性能；达到阶段标准后形成独立检查点。随后继续基础 nominal 的离散 phase
   竞争机制，不提前进入 contact/overlap。
