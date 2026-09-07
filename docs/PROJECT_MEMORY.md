# 项目记忆

更新：2026-09-07。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与执行顺序

- 当前 96 个 development nominal 全部正确 `approved_auto`，全部角色 `unsafe_approved_auto = 0`；
  challenge 尽量安全自动通过，证据不足时安全 Review 不掩盖能力缺口。中间开发可暴露危险 auto，但必须
  保存具体边界与根因，并明确不可发布；release commit 才是硬性归零验收。
- 保持 current-only、唯一 canonical owner、无旧兼容、无样片特例，不放宽 format/count authority、
  人工黄金、真实反证或逐侧预算，不通过事后修框、合并候选外包框或扩大 bleed 获得批准。
- 正式 24-source 完整用户路径平均耗时 `<= 5s`，持续争取 `<= 3s`；工程、黄金、正式性能、
  TIFF/metadata、安装、三目标平台、打包和 Hook/CI 分别验证，全部发布证据绑定同一 release commit。
- Source-W、有界候选集合、typed features 与首轮离线开发排序已验证。首轮排序没有改善选择，
  不具备接入 Runtime 的依据；下一步核查风险代理的物理职责与不安全候选生成根因。
  不要求全部 nominal 先通过才开发评分；排序不是概率，正式概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末“共同 W 与逐 Frame 真实变化审计”。该任务当前只登记，
  不打断现有工作，不提前增加自由度或回退已有正确改动。

## 当前几何与验证检查点

当前源码为 `89e74346`，端部材料与条件几何修正为 `3601023d`，均已推送 `main`。
最新正常 Hook 完成 805 项工程测试、2 项按既定条件跳过；远端
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34129207993)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。

- 端部窄材料带保留内侧边界假设，但不再否定外侧 edge 的独立角色权限；窄带可能位于 aperture 内。
  真实 separator material 与反序 pair 的反证仍保留，没有扩大 W、bleed 或预算。
- 纯离散歧义的 primary/runner 分别消费自身 supported direct-role/rank-3 约束；runner 重新核验自身
  ledger，并去除不匹配 source W 的输入。条件几何不授予选择权限；其它 typed conflict 不能借此收紧。
- Enclosing aperture-center 校准从当前唯一 selected pair 重算：S005、S007 退出，S012 进入，18→17 个
  source。登记的 observation-set 指纹已刷新，方法、资格与 `[-0.009H, +0.007H]` 数值均不变。
- 每条 lane 的已有 best 与单个 runner 经同一 projection/output owner 各物化一次；正式输出复用
  primary。没有扩大搜索、增加像素查询或改变 selection/Gate。投影与实际逐 slot 输出评估次数均有界。
- Report revision 为 `x5crop_v5_template_report_69`；gold record / summary 为 v20 / v23。每份候选保留
  identity、实际 footprint、typed unavailable 原因与独立方向性黄金标签；多个候选可同时安全。
  集合以 task 为单位，无法生成不算负例；真实歧义与 coverage/预算阻断分别统计。
- 每份 proposal 复用同一 owner 的逐 slot 数值预算，正式 candidate 不重算；28 项物理特征冻结单位、
  source fields、missingness 与 provenance，不读取黄金、sample ID、文件名或 cohort，不增加几何自由度。
- 专项反例覆盖一次投影/预算、工作量与特征篡改、缺失不记 0、锚点去重、同 SHA 同折、source 等权、
  训练集内 transform、多正例、未知不算负例、稳定同分、模型正规方程、预测与聚合不可篡改。

最新完整 receipt 为 `/private/tmp/x5crop-outer-material-full-20260907b`，绑定干净提交
`89e74346`；detector/comparator 均匹配 HEAD，全部物理校准登记通过，110/110 完成、分析错误 0：

| 层级 | 结果 |
|---|---|
| 完整 proposal | 110；36 safe / 74 unsafe |
| Candidate | 20 safe / 13 unsafe / 77 unavailable |
| 最终决定 | 16 safe auto / 0 unsafe auto / 94 Review |
| Nominal | 16 safe auto / 80 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 189 份；39 safe / 150 unsafe |
| 每任务至少一份安全 | 37；其中 nominal 33 / challenge 4 |
| 单份 / 多份安全 | 35 / 2 个任务 |
| 全部保留候选不安全 | 73 个任务；其中 nominal 63 |
| 安全候选且有明确 placement 歧义 | 7 个任务 |

与上一轮候选特征基线 `/private/tmp/x5crop-placement-features-full-20260907b` 比较，所有 task 的主 proposal
黄金 verdict 和最终决定未变。S005 的安全 candidate 变为歧义 unavailable，S007、S070 的 unsafe candidate
变为 unavailable，S012 从 unavailable 变为 unsafe。不能把这些资格变化冒充黄金准确率改善。

S017 首 START 与 S109 末 END 的内切消除；S005 主 proposal 保持安全，runner 仍在第 5 张 START 内切
约 33 px。S012 第 6 张 START、S019 第 4 张 END 各新增一处内切。全体主 proposal 的逐 Frame/side
内切数仍为 158，外扩超限数 262→255；整体安全 proposal 和自动覆盖没有增加。
校准登记更新前后两份完整 receipt 逐任务比较，几何、资格、失败原因和最终决定均不变。

逐候选数值预算对照：39 份黄金安全中 30 passed / 9 failed；150 份不安全中 26 passed / 124 failed。
它不能单独代替真实黄金安全，也不能据此整体关闭现有风险条件。

首轮离线排序提交为 `938d985f`，artifact 为
`/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`，仍绑定此前 `38178c4a` 的特征基线，
不是当前 189 份候选的重训结果。它覆盖 106 个 source SHA、110 个 task、185 份候选。
固定五折、训练折标准化、source 等权 ridge 的方法见
架构第 9.2 节，不根据本轮结果调参：

| 开发比较 | 首选安全 | 排序后安全 | 改善 / 退步 |
|---|---|---|---|
| Source-grouped 折外 | 36 | 34（nominal 31 / challenge 3） | 无改善；S041、S069 退步 |
| 全量拟合的样本内 | 36 | 36 | S028 改善；S041 退步 |

S041、S069 错误 runner 均向内切入人工边界，数值预算却通过；当前线性模型还给部分较少支持、
较小 residual 的错误候选更高分。S028 的安全 runner 在折外没有胜出。上述结果不支持接入选择；
分数无界、没有 calibration、没有正式 OOD、`admission_enabled=false`，不改变任何 Runtime 结果。

干净提交 `89e74346` 的正式 `tools/verify performance` receipt 为
`build/v5-performance/performance_receipt.json`：24-source mean **3.963855 秒**，5 秒 Gate 通过；
3 秒挑战未达成。p95 为 6.809904 秒，最慢 S038 为 7.088964 秒，未插桩进程峰值 RSS 最大
1,212,563,456 bytes。该计时只证明当前机器、依赖和当前决定分布。
黄金分析的 development-detail mean 为 4.220328 秒，不能替代该正式性能结果。

## 验证边界与开放风险

- 当前仍为 `development_only_not_release_ready`；80 个 nominal Review 与 74 个不安全 proposal 表明
  检测目标未完成。黄金安全不自动证明当前阻断多余，Review 也不允许隐藏不安全候选。
- Source-W 测量、placement 消费和自动资格保持分离；有效旧联合代表不移动，失去角色权限的旧区间
  退出相关约束。当前物理校准登记与完整黄金可复算一致，没有借候选收集更改物理模型。
- 当前 development gold 已用于机制发现，不估计未来生产错误率。当前没有 sealed cohort，且黄金未覆盖
  `xpan`、`120-645`、`135-dual`；如实披露，不冒充已验证或据此建立格式禁用规则。
  独立概率权限的 calibration/sealed 前提与首版确定性能力验收分开。
- Source truncation、片夹遮挡、部分 Cross 覆盖与连续内容反证仍有能力缺口。不能用更窄 uncertainty、
  更宽校准、丢弃 residual 或删除真实反证来换覆盖。
- S017 的 Cross 端部方向外推仍超预算。逐端点收紧内部 polygon 不是已证明的修复：最终使用唯一
  source-wide deskew 后的矩形 AABB，仍须包住另一端极值；不能把内部轮廓缩小冒充真实裁切收益。
- 首轮可用性排序没有改善现有选择；集合只有 33 个 nominal 至少有一份安全候选，单靠选择无法完成目标。
  集合范围只含当前 best/单 runner，不能把其余 63 个 nominal 外推成所有潜在裁切均不安全。
  这 63 项的 primary 首个黄金失败为 47 项向内切入、16 项向外超预算，属于诊断分组而非已证明根因。
  Margin 不是永久 veto，近似框也不能相互合并或假定等价；数值范围支持检查不替代正式 OOD。

## 精确下一步

1. 先以 S012、S019 的新内切回归核对局部 separator 生成与候选保留：

   - S012 正确 START105 仍注册，但最终候选的投影输入已无该 role；source-W 后走廊排除它，改由 END138
     推断 START。S019 的内侧 END128 在 W 建立前已为 phase anchor，正确 END129→START130 的完整
     separator 仍注册。两者都不是 W 直接替换已绑定边。
   - `template_phase_candidates.py::_refine_local_role_bindings` 的原子 pair 要求 component supported 且
     实测 gap 与 nominal gap 双侧相交。两例实测 gap 均低于 nominal 下界；S012 另有既有 partial-height
     一次传权与原子补边资格是否一致的问题。用通用最小正反例核对是否遗漏既有合法权限，不扩大 W。
   - S019 的 adjacency ledger 只查询当前精确 pair，未消费同 corridor 的完整另一 pair；核查应否保留
     离散竞争，不直接替换已有 anchor。现 report 不含早期全部 candidate 淘汰记录，最早退出点尚未证明。

2. 从 S028、S041、S069 的已有同次事实核查 Cross 方向/位置、支持、residual 和预算的物理职责：
   区分真实硬合法性、内切内容风险与过度保守的代理，补足可核验的 hard-legality/risk assessment。
   不以临时分差阈值、样片特例、盲目调参或关闭 Gate 消除失败；新特征仍必须来自现有 typed facts，
   不增加像素查询、候选笛卡尔积或平行 detector。开发评估与独立概率校准保持分开。
3. 沿 63 个 nominal 的已有候选全部不安全分组，优先追查方向性向内切入的几何生成根因，
   用最小正反例和正式 CLI 样片检查推进已有能力；不提前启动逐 Frame W 变化审计。
4. 用明确的可用候选缺口和几何根因继续完成 nominal/challenge 能力；最终在同一 release commit 完成
   全部黄金、正式性能和工程/平台验收。只有此前能力完成后，才执行下列延后审计。

## 延后任务：共同 W 与逐 Frame 真实变化审计

启动条件：此前已确认的全部能力完成后再开展，不打断当前工作，不提前实施，不据此回退正确改动。

审计问题是区分“各 Frame 围绕 source 共同 W 有经过校准的小幅真实变化”和“全部 Frame 共享同一个
尚不精确的 W”。扩大共同 W 区间不必然等价于允许逐 Frame 变化。侧会话提供的三条线索——source W
估计容许 residual 并传播到 W、双侧/单侧/无直接边的投影方式不同、完整未观察 Frame 调用整条 sequence
联合约束而可能暴露远处冲突——均是待验证机制，不是已证明的样片根因，也不授权放宽 Gate。

1. 区分测量误差、真实 aperture/走片变化与模型误差，核对各自 canonical owner。
2. 以最小正反例和少量真实样片，验证三种投影是否遵守一致物理合同。
3. 仅在开发测试的 solver 输入隐藏指定 observation；原 TIFF、测量记录和黄金不变，检查几何跳变或
   无解是否合理。测试实验不得成为平行 production path。
4. 若确认问题，优先复用共同 W、local correction 与联合 uncertainty；只有证据证明必要时才设计
   经校准、有界的局部变化合同，不增加样片特例，不隐藏反证。
5. 作为独立小机制闭环完成全部黄金与相应性能验证；当前仅登记，不调整物理模型或验收标准。
