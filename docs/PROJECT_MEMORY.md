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

当前源码为 `b2cb1470`，已推送 `main`；其中 `2047b026` 修复重拟合后的 phase residual 相容性，
后续提交只更新 enclosing calibration 登记。
最新正常 Hook 完成 809 项工程测试、2 项按既定条件跳过；远端
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34136044537)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。

- 端部窄材料带保留内侧边界假设，但不再否定外侧 edge 的独立角色权限；窄带可能位于 aperture 内。
  真实 separator material 与反序 pair 的反证仍保留，没有扩大 W、bleed 或预算。
- 窄 separator 的原子补边不再额外要求实测 gap 达到 nominal 下界；既有 material、W、ordinal 与
  competing-pair 条件不变。候选投影按本次实测 relations 重算 rank；pitch 从方程中消去后，使用已有
  calibrated Grid 或报告不可用，不沿用旧 nominal rank，不新增欠定拟合器或逐 Frame 自由度。
- 两项最小回归均先红后绿；反例保留 competing/partial-height pair、W 冲突、缺 calibration 的阻断。
  Grid 路径原样保留 native binding、完整区间、use 与 ordinal，不添加 phase authority。
- 直接与校准 Grid 重拟合共用当前 phase-anchor 的 native/model 残差判定，不继承旧模型的相容性，
  local refinement 不进入全局均值。原有 `max(2px, 0.015W)` 阈值、总 residual 特征与预算不变。
  正反例先红后绿，覆盖旧失败→新相容、旧成功→新不相容，以及 local binding 不改变锚点均值。
- 纯离散歧义的 primary/runner 分别消费自身 supported direct-role/rank-3 约束；runner 重新核验自身
  ledger，并去除不匹配 source W 的输入。条件几何不授予选择权限；其它 typed conflict 不能借此收紧。
- Enclosing aperture-center 校准从当前唯一 selected pair 重算：S094 新满足既有资格，17→18 个 source；
  原 17 项观测完全不变。登记指纹为 `1f228750b9ff92a81bdd724b456bb8791079dcf346ad73e561840d89cb89f5be`，
  方法、资格与 `[-0.009H, +0.007H]` 数值均不变。
- 每条 lane 的已有 best 与单个 runner 经同一 projection/output owner 各物化一次；正式输出复用
  primary。没有扩大搜索、增加像素查询或改变 selection/Gate。投影与实际逐 slot 输出评估次数均有界。
- Report revision 为 `x5crop_v5_template_report_69`；gold record / summary 为 v20 / v23。每份候选保留
  identity、实际 footprint、typed unavailable 原因与独立方向性黄金标签；多个候选可同时安全。
  集合以 task 为单位，无法生成不算负例；真实歧义与 coverage/预算阻断分别统计。
- 每份 proposal 复用同一 owner 的逐 slot 数值预算，正式 candidate 不重算；28 项物理特征冻结单位、
  source fields、missingness 与 provenance，不读取黄金、sample ID、文件名或 cohort，不增加几何自由度。
- 专项反例覆盖一次投影/预算、工作量与特征篡改、缺失不记 0、锚点去重、同 SHA 同折、source 等权、
  训练集内 transform、多正例、未知不算负例、稳定同分、模型正规方程、预测与聚合不可篡改。

最新完整开发 receipt 为 `/private/tmp/x5crop-grid-residual-full-20260907b`，绑定干净 `b2cb1470`。
Detector manifest 为 `cf900d0ea295f4853f1ef3a1f776078c215497a21f1605529c58bc9eb408e426`，
detector/comparator 均与 HEAD 匹配，comparator/cohort 未变。
全部物理校准登记通过，110/110 完成、分析错误 0：

| 层级 | 结果 |
|---|---|
| 完整 proposal | 110；36 safe / 74 unsafe |
| Candidate | 22 safe / 13 unsafe / 75 unavailable |
| 最终决定 | 18 safe auto / 0 unsafe auto / 92 Review |
| Nominal | 18 safe auto / 78 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 186 份；40 safe / 146 unsafe |
| 每任务至少一份安全 | 37；其中 nominal 33 / challenge 4 |
| 单份 / 多份安全 | 34 / 3 个任务 |
| 全部保留候选不安全 | 73 个任务；其中 nominal 63 |
| 安全候选且有明确 placement 歧义 | 6 个任务 |

与上一轮 `/private/tmp/x5crop-measured-rank-full-20260907a` 比较，110 项主 proposal 的黄金 verdict
均不变。S094 的安全 proposal 从模板不相容 Review 变为安全 auto；其它最终决定未变。
S018 不再继承旧模型的 `fixed_template_mismatch`，但仍因 aspect-ratio budget 失败而 Review。
S012/S019 native 端边修复、S083 安全 auto 以及此前 S017/S109 端边修复均保留。
主 proposal 逐 Frame/side 内切数 156→151，外扩超限数 255→250；这不是逐项全面改善：
S111 第 3–8 格 END 的 6 处内切消除，S106 第 2 格 END 新增内切（-87.105609 px）；
S026 新增第 3/5 格 START、第 6 格 END 外扩超限，旧第 3 格 END 超限消除。
S111 另消除 7 处 START 外扩超限。所有退步样片仍 Review，不隐藏其候选风险。
标定登记前的 `/private/tmp/x5crop-grid-residual-full-20260907a` 与最终复算的全部 110 条 record
仅 duration 不同：所有候选输出范围、预算、黄金结论和决定完全一致。

逐候选数值预算对照：40 份黄金安全中 32 passed / 8 failed；146 份不安全中 25 passed / 121 failed。
它不能单独代替真实黄金安全，也不能据此整体关闭现有风险条件。

首轮离线排序提交为 `938d985f`，artifact 为
`/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`，仍绑定此前 `38178c4a` 的特征基线，
不是当前候选的重训结果。它覆盖 106 个 source SHA、110 个 task、185 份旧候选；数量相同不代表身份相同。
固定五折、训练折标准化、source 等权 ridge 的方法见
架构第 9.2 节，不根据本轮结果调参：

| 开发比较 | 首选安全 | 排序后安全 | 改善 / 退步 |
|---|---|---|---|
| Source-grouped 折外 | 36 | 34（nominal 31 / challenge 3） | 无改善；S041、S069 退步 |
| 全量拟合的样本内 | 36 | 36 | S028 改善；S041 退步 |

S041、S069 错误 runner 均向内切入人工边界，数值预算却通过；当前线性模型还给部分较少支持、
较小 residual 的错误候选更高分。S028 的安全 runner 在折外没有胜出。上述结果不支持接入选择；
分数无界、没有 calibration、没有正式 OOD、`admission_enabled=false`，不改变任何 Runtime 结果。

干净提交 `2047b026` 的正式 `tools/verify performance` receipt 为
`build/v5-performance/performance_receipt.json`：24-source mean **4.033761 秒**，5 秒 Gate 通过；
3 秒挑战未达成。p95 为 6.894610 秒，最慢 S038 为 7.203435 秒，未插桩进程峰值 RSS 最大
1,216,036,864 bytes。该计时只证明当前机器、依赖和该提交的决定分布；后续仅改标定登记，
完整复算已证明结果不变，但此 receipt 不冒充 `b2cb1470` 或未来 release commit 的性能证据。
黄金分析的 development-detail mean 为 4.235590 秒，不能替代正式性能结果。

## 验证边界与开放风险

- 当前仍为 `development_only_not_release_ready`；78 个 nominal Review 与 74 个不安全 proposal 表明
  检测目标未完成。黄金安全不自动证明当前阻断多余，Review 也不允许隐藏不安全候选。
- Source-W 测量、placement 消费和自动资格保持分离；有效旧联合代表不移动，失去角色权限的旧区间
  退出相关约束。当前物理校准登记与完整黄金可复算一致，没有借候选收集更改物理模型。
- 当前 development gold 已用于机制发现，不估计未来生产错误率。当前没有 sealed cohort，且黄金未覆盖
  `xpan`、`120-645`、`135-dual`；如实披露，不冒充已验证或据此建立格式禁用规则。
  独立概率权限的 calibration/sealed 前提与首版确定性能力验收分开。
- Source truncation、片夹遮挡、部分 Cross 覆盖与连续内容反证仍有能力缺口。不能用更窄 uncertainty、
  更宽校准、丢弃 residual 或删除真实反证来换覆盖。
- S018 的旧残差标记传递错误已修复，当前预算失败是不同问题。S088 两个 Grid LP 均真实不可行，
  必要 W 交集分别为 `[3581.771330, 3559.278756]`、`[3581.771330, 3498.973317]`，均为空。
  不能把该反证误修成成功，也不能借此提前开展逐 Frame W 自由度审计。
- S028/S041/S069 的一次正式 CLI 后，用冻结既有 content index 评估两份原有 footprint，6 项均没有
  content-veto fact；输出范围与基线完全一致。这一路现有证据不能识别上述排序错误，不新增无效路径。
- S069 bottom line 4/5 的完整 union 实际已拟合，但 28 条 transition 中有 1 条超出现有 0.10 mm
  容差而被丢弃，exact-union 正确拒绝。三条测量区间已有共同直线无解证书；应核查 transition 1330
  的上游身份，不以黄金斜率强行合并或放宽容差。证据位于 `/private/tmp/x5crop-family-S069-20260908.jsonl`。
- S017 的 Cross 端部方向外推仍超预算。逐端点收紧内部 polygon 不是已证明的修复：最终使用唯一
  source-wide deskew 后的矩形 AABB，仍须包住另一端极值；不能把内部轮廓缩小冒充真实裁切收益。
- 首轮可用性排序没有改善现有选择；集合只有 33 个 nominal 至少有一份安全候选，单靠选择无法完成目标。
  集合范围只含当前 best/单 runner，不能把其余 63 个 nominal 外推成所有潜在裁切均不安全。
  这 63 项的 primary 首个黄金失败为 45 项向内切入、18 项向外超预算，属于诊断分组而非已证明根因。
  Margin 不是永久 veto，近似框也不能相互合并或假定等价；数值范围支持检查不替代正式 OOD。

## 精确下一步

1. 优先闭环 S106 新增内切：第 2 格 START 新绑定 `boundary-edge:5`（1628.589322 px），END 仍推断，
   整格比此前前移约 100 px。同次正式 CLI 已确认重拟合后 phase resolved，使 local refinement 可达；
   `separator-band:28` 的原子补边把 edge 5 绑定到 START。当前 typed 拒绝针对 role 16 的 edge 215，
   并非识别了 edge 5 的内切。证据为 `/private/tmp/x5crop-S106-phase-20260908.jsonl`，对应 report 验证通过。
   下一步核查该材料带与角色身份的物理依据，不能只凭原始 END 资格禁止所有相反角色解释，
   也不能因仍 Review 就忽略几何退步。
   S012/S019、S018 的已修根因与 S088 已证明的不可行不重复排查。
2. 沿 S069 transition 1330 的原测量身份，以及 S041/S069 逐侧支持、外推和单侧 residual 的物理职责
   继续检查 Cross 内切根因。低 residual 与 budget passed 不证明准确；既有 content 检查已证无帮助，
   不再假设新增 runner content receipt 就能修复这些样片。新事实不得读取黄金或样片 ID，不增加像素
   查询、候选笛卡尔积或平行 detector；不以临时分差、盲目调参或关闭 Gate 消除失败。
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
