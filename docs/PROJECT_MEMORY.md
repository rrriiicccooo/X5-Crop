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
- 先闭合当前 source-W 测量/消费检查点；随后按架构第 9.2 节开展已有有界候选的黄金可用性集合分析、
  typed features、开发排序与风险代理评估。不要求全部 nominal 先通过才开发评分；排序不是概率，
  开发标签不反写 Runtime Gate，正式概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末“共同 W 与逐 Frame 真实变化审计”。该任务当前只登记，
  不打断现有工作，不提前增加自由度或回退已有正确改动。

## 当前 source-W 检查点

当前 tracked 基线为 `98d25e64`；本轮修改尚在验证，不能作为 release receipt。

- 合格局部完整 Frame 测量不再依赖远处 coverage、全局 phase/rank 或 proposal 已获资格。全部直接
  rank-3 约束仍参与同一 W 投影；两组合法测量只取交集，测量与 placement 消费分别保留。
- Retained ambiguous/unresolved proposal 可以消费 W，但原失败、runner 与 candidate/auto 权限不变。
  完整未观察 Frame 继续归 Grid；它不阻止其它单边 Frame 的相关 W 推导。
- 原联合 canonical W 仍可行时保留它；必须改变时同步更新派生 gap、local delta 与角色区间，native
  binding 不变。弱局部角色成为 validation-only 时，旧 model/full hull 同时退出联合约束，且只重建
  该角色的 Grid 边际，不改其它已投影区间。
- 数值预算评估、CandidateGate 预算阻断与黄金安全结果分开报告；空评估不是通过。Report revision
  为 `x5crop_v5_template_report_67`，gold record / summary 为 v18 / v21，无旧 schema 兼容。
- 67 项 source-W、联合几何与 gold-analysis 专项测试通过。最小弱边界反例先失败后修正：
  退出角色恢复为完整 Grid 区间，远处完全未观察 Frame 的联合范围不再被无权旧线压成单点。

最新已完成的完整 receipt 是弱角色区间修正后的
`/private/tmp/x5crop-source-w-full-20260907i`，110/110 完成、分析错误 0：

| 层级 | 结果 |
|---|---|
| 完整 proposal | 110；36 safe / 74 unsafe |
| Candidate | 21 safe / 14 unsafe / 75 unavailable |
| 最终决定 | 16 safe auto / 0 unsafe auto / 94 Review |
| Nominal | 16 safe auto / 80 Review |
| Challenge | 14 Review，尚无安全 auto |
| Source W | 83 supported / 24 unavailable / 3 contradicted |
| 单边 W 推导 | 55 supported / 18 unavailable / 37 not applicable |

与同源干净基线 `/private/tmp/x5crop-source-w-baseline-20260904` 相比，S041、S050、S098 的 proposal
从 unsafe 变为 safe，无 safe→unsafe proposal 回归；S047 的 unsafe candidate 被 W 反证撤回，最终决定未变。
该 receipt 的 development-detail mean 为 4.374 秒，仅作开发归因，不是正式性能资格。

## 验证边界与开放风险

- 当前仍为 `development_only_not_release_ready`；80 个 nominal Review 与 74 个不安全 proposal 表明
  检测目标未完成。黄金安全不自动证明当前阻断多余，Review 也不允许隐藏不安全候选。
- 弱角色区间修正未改变完整黄金的几何安全、phase failure 或终态分布；最小反例验证了真实区间缺陷。
- Enclosing-support aperture-center 校准登记已按完整结果更新为 18 个合格 source/task 和精确 digest
  `2aee837e8bc5b552cd1d3ac22690ba718ef3a0e00b13fcfbff743d97005c63ab`。干净基线复算已是 19，source-W
  变化再使 S047 失去资格；推导区间仍为 `[-0.009H,+0.007H]`，没有改变数值范围。上述 receipt 早于
  此登记更新；已用唯一 calibration owner 对完整 records 复算通过，但尚需当前身份的端到端复验。
- 当前 development gold 已用于机制发现，不估计未来生产错误率。当前没有 sealed cohort，且黄金未覆盖
  `xpan`、`120-645`、`135-dual`；如实披露，不冒充已验证或据此建立格式禁用规则。
  独立概率权限的 calibration/sealed 前提与首版确定性能力验收分开。
- Source truncation、片夹遮挡、部分 Cross 覆盖与连续内容反证仍有能力缺口。不能用更窄 uncertainty、
  更宽校准、丢弃 residual 或删除真实反证来换覆盖。
- 可用性排序开发尚未实现。标签必须独立评价每份最终 footprint，允许同 source 多个正例；
  先区分“至少一份可用”“多份可用”“可用但被歧义拒绝”“全部不可用”，再判断生成或选择的改进空间。
  Margin 不是永久 veto，近似框也不能相互合并或假定等价。

## 精确下一步

1. 在干净提交上取得包含新 calibration identity 的完整黄金复验，核对几何和终态保持、分析错误为零，
   以及全部物理校准登记一致。
2. 验收本轮 source-W、预算报告及相关文档，按正常 Hook 提交并推送 `main`；只作开发检查点，
   不创建发布物，不用 development duration 替代正式性能。
3. 进入架构第 9.2 节的候选集合可用性分析。复用 `template_selection.py` 的有界竞争、
   `gold_geometry.py` 的标签 owner 与 `gold_analysis.py` 的集合统计；不建立第二 detector 或黄金池，
   不为评分增加像素查询、候选笛卡尔积或无界搜索。
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
