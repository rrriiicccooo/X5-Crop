# 项目记忆

更新：2026-09-08。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与执行顺序

- 当前 96 个 development nominal 全部正确 `approved_auto`，全部角色 `unsafe_approved_auto = 0`；
  challenge 尽量安全自动通过，安全 Review 不掩盖能力缺口。发布前全部要求绑定同一 release commit。
  中间开发可暴露危险 auto，但必须保存具体边界与根因并明确不可发布；release commit 才是硬性归零验收。
- 保持 current-only、唯一 canonical owner、无旧兼容、无样片特例；不放宽 format/count authority、
  人工黄金、真实反证或逐侧预算，不通过事后修框、合并互斥候选或扩大 bleed 获得批准。
- 正式 24-source 完整用户路径平均耗时 `<= 5s`，持续争取 `<= 3s`；工程、黄金、正式性能、
  TIFF/metadata、安装、三目标平台、打包和 Hook/CI 分别验证。
- Source-W、有界候选集合、typed features 与首轮离线开发排序已验证。首轮排序没有改善选择，
  不具备接入 Runtime 的依据；继续核查风险代理的物理职责与不安全候选生成根因。
  不要求全部 nominal 先通过才开发评分；排序不是概率，概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末共同 W 审计。当前只登记，不打断现有工作，
  不提前增加自由度、隐藏 observation 或回退已有正确改动。

## 当前源码与已验证事实

Runtime 最近改动提交为 `ecf6a9a9e3e7a730d7ad0213dfe09d9bfefc60bb`，已正常推送 `main`。
该提交正常 pre-push Hook 的 827 项工程测试通过、2 项按既定条件跳过；
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34145570146)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。
本轮仅修正黄金比较器与对应文档，未改变 Runtime、Gate 或人工 reference；62 项黄金专项测试通过。

- 源截断后的实际确认 polygon 是包含检查对象。人工线确定物理轴与权限，受保护输出边的半平面
  检查全部确认顶点，且每个受保护侧都必须实际参与。完整自包含与逐侧诊断一致；
  亚像素内切、缺失受保护侧的斜凸多边形和 `visible_content_limit` 反例均保持失败。
- Material pair 保留 endpoint 原有像素角色候选；两种解释不增加独立票数或 rank，各自核验直接权限。
  S106 旧的第 2 格约 87 px 纵向内切已消除，仍有独立 Cross 内切待解决。
- 纯离散歧义的 primary/runner 分别补全局部边界、投影晚期弱线并保留硬反证；不共享 selected W、
  不重新排序、不扩大 6-pass 上界。每个新增调用均记录实际工作量。
- Cross 分别编译两份候选的 N 格支撑区间，同一横向边界须逐组满足原有覆盖条件，不合计为 2N 票。
  S081 的直接 TOP/BOTTOM 闭环恢复，两份候选均安全；S015 新增安全 primary，但数值预算仍失败。
- Report revision 为 `x5crop_v5_template_report_70`，gold record / summary 为 v20 / v23。
  Cross authority 保留逐候选实际区间与覆盖序号；校验与 Runtime 共用纯 canonical-support owner。
  成对删组、清空全部组或篡改 runner 区间均被拒绝；不复制检测或几何规则。
- 原有 `direct_lattice_conflict` 投影失败可通过严格报告校验；集合允许只有 runner 能物化，
  不伪造 primary、不把无法生成计为负例。两项均有失败后修复的回归测试。
- Enclosing aperture-center calibration v5 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  仍为 18 个 source，但 S006/S013 退出、S026/S043 加入，其余 16 项观测不变；
  当前区间为 `[-0.008H, +0.010H]`，精确 observation-set SHA 为
  `9507b115ed4f440eb2d79f05b92f8e1fae42223e70fd7f6204e8aad22c945b61`。
  成员变化不是单纯 hash 更新；它不改变 pair 选择、采样 geometry 或既有 5% 阈值。

## 完整黄金与性能证据

最新完整开发 receipt：
`/private/tmp/x5crop-source-clipped-comparator-full-20260908a`。
110/110 完成、分析错误 0、全部物理校准登记一致：

| 层级 | 结果 |
|---|---|
| Primary proposal | 36 safe / 73 unsafe / 1 unavailable |
| Candidate | 21 safe / 13 unsafe / 76 unavailable |
| 最终决定 | 17 safe auto / 0 unsafe auto / 93 Review |
| Nominal | 17 safe auto / 79 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 185 份；40 safe / 145 unsafe |
| 每任务至少一份安全 | 38；36 个单份安全、2 个多份安全 |
| 全部保留候选不安全 | 72 个任务 |
| 安全候选且有明确 placement 歧义 | 8 个任务 |

与 `/private/tmp/x5crop-cross-domain-calibrated-full-20260908a` 相比，全部 185 份 footprint、
黄金标签、数值预算和决定完全一致。逐侧诊断修正五处：S048 runner 第 1 格移除 Cross LOW 误报；
S052 primary 第 1 格补报 Cross LOW；S081 两份候选第 2 格和 S098 primary 第 10 格移除 END 误报。
S081 两份候选均安全但仍为真实双解 Review；不能因黄金判安全就跳过 Runtime 选择能力缺口。
S079 的旧安全候选仍保留为 runner，新 primary 不安全；没有隐藏这项选择退步。

40 份安全候选中 32 项预算 passed / 8 failed；145 份不安全候选中 24 passed / 121 failed。
这说明数值预算不能单独代替黄金安全，也不能据此整体关闭风险检查。

该黄金 receipt 生成于提交前，header 记录基座 `2f588c84`；detector 与 HEAD 匹配，comparator 为本轮
工作树状态，不是干净 release receipt。已核对运行时的源文件指纹与当前工作树一致：

- detector：`c95c0112da545c0f568f0635abe8676711d7e1a7b3f4ebf4fb921eb236f830ca`
- comparator：`096711cbe5bfff1996419c2f646318db1951fce9c34d393952fe55d9e4d9430c`
- cohort：`c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`

干净 `ecf6a9a9` 的正式 `tools/verify performance` receipt：
`build/v5-performance/performance_receipt.json`。24-source 完整用户路径均值 **3.763253 秒**，
5 秒 Gate 通过，3 秒挑战未达成；p95 为 6.540389 秒，最慢 S038 为 6.792203 秒。
未插桩进程峰值 RSS 最大 1,209,221,120 bytes。
此结果只证明该提交、当前机器、冻结依赖和本次决定分布，不外推其它平台或未来 release commit。
本轮仅改 comparator，不重复正式性能测试。新黄金分析 development-detail mean 为 3.985933 秒，
不代替正式性能结果。

## 开放风险与精确下一步

1. 优先核查 S106 源边附近的实际可观测范围。当前 Cross 没有 TOP fitted binding，只有未获
   role authority 的 BOTTOM `format-role-bound-line:1`；TOP 是其 calibrated-H Review 推导。
   正式旧 report 位于 `/private/tmp/x5crop-S106-phase-20260908/x5_crop_report.jsonl`；
   Cross canonical 与本轮 footprint 一致，但旧 phase 状态不能冒充当前结果。
   最新几何见本轮完整 gold records，原 profile 为 `/private/tmp/x5crop-S106-phase-20260908.jsonl`。
   TOP query 注册 `[0,172.624857]`，113 条 traces；9 个 raw runs 的 transition 均存在，
   但每个只有 1 个独立空间区域，低于拟合要求的 2 个，family merge 因而没有 TOP observation 可合并。
   `registered_transition_measurement.measure_trace` 的 window=21、gap=5，使本例可测下界为 26 px。
   `coverage.complete` 不等于 y<26 已有边界存在或不存在的证据，也不据此判定该字段有 bug。
   第 8–12 格 required TOP 为 10.762、12.762、26.762、24.762、27.415 px，仍有图内缺口。
   同 scale 的低层阶跃反例中，真实分界在 24.5 px 时，peak physical interval 为 `[25.5,50.5]`；
   查询端截断可能让定位区间漏掉真实分界，尚未证明它会获得完整 Runtime direct authority。
   先闭合 source/query 端截断 peak 的测量权限，不先放宽窗口或拼接碎片。
2. S106 前 7 格 required TOP=0，而冻结 polygon TOP=-0.5。人工原始 E1 经 tag 8 正确映射到
   `(0.033445,-31.449926) → (18266.966555,18.011230)`；不是 Orientation 错误。
   标注器按像素单元域 `[-0.5,extent-0.5]` 裁剪，Runtime 按像素中心域 `[0,extent-1]` 裁剪。
   约 0.4–0.52 px 是这半像素差与各 Frame 斜轴、长轴余量共同投影的结果，不是逐格垂直内切距离。
   本轮已修复另一个独立的未裁剪半平面误报，但没有改变该域差异或黄金坐标；当前仍失败。
   下一步须统一可用源域与真实采样语义的证明，不能移动人工线或增加容差来豁免。
3. 继续核查 S069 transition 1330 的上游身份。其完整 union 曾因 28 条中的 1 条超出 0.10 mm 而被
   exact-union 正确拒绝，三条区间已有共同直线无解证书：
   `/private/tmp/x5crop-family-S069-20260908.jsonl`。不以黄金斜率强行合并或放宽容差。
4. 继续处理尚无安全候选的生成根因和已有安全候选的选择缺口。首轮离线 ridge 排序
   `/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`
   仍绑定旧 `38178c4a` 数据，不是当前集合重训结果；旧折外选择由 36 safe 降到 34，
   S041/S069 退步，因此未接入 Runtime。S028/S041/S069 的既有 content 检查没有 veto fact，
   不再假设重复增加该 receipt 能解决选择问题。
5. 当前仍为 `development_only_not_release_ready`。没有 sealed cohort，黄金未覆盖
   `xpan`、`120-645`、`135-dual`；不冒充未来生产错误率或建立格式禁用规则。
   最终同一 release commit 的全部黄金、性能、工程、TIFF/安装、平台与打包验收仍待完成。
   只有此前能力完成后，才执行下面的延后审计。

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
