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
- 执行顺序：保留可评价的完整 proposal，优先修复不安全方案的通用几何根因，再处理安全方案的错误
  权限阻断与可用性选择。目标是最终裁切直接可用，不要求逐线复原唯一真实边界；精确合同见架构第 9、14 节。
- Source-W、有界候选集合、typed features 与首轮离线开发排序已验证。首轮排序没有改善选择，
  不具备接入 Runtime 的依据；继续核查风险代理的物理职责与不安全候选生成根因。
  不要求全部 nominal 先通过才开发评分；排序不是概率，概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末共同 W 审计。当前只登记，不打断现有工作，
  不提前增加自由度、隐藏 observation 或回退已有正确改动。

## 当前源码与已验证事实

当前 Runtime 与验证基座为 `36d18f8dbb968710e5eedf7772421952174232c6`，已正常推送 `main`。
正常 pre-push Hook 的 887 项工程测试通过、2 项按既定条件跳过；
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34191642141)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。

- Sequence full reference position 同时包含原 residual/localization 保护与同一 raw physical family
  的完整位置投影；`PhysicalLineRegion` 保留位置/斜率联合顶点，原角度上限、角色资格与 rank 不变。
  最小不对称反例、退化点/线段、大坐标相切与 288 次独立 LP 投影对照通过。
  目前只闭合 measurement 层，不能声称完整联合角点已经传播到最终输出。
- 晚期弱线投影消费完整 registered 身份账本，seed 搜索仍用原 `support_fraction >= 0.35` 子集。
  S110 的获权稀疏局部边不再被误报 unknown edge，正式 CLI 与 revision 75 校验通过；
  真实弱线反证仍保留，最终为 `direct_lattice_conflict` Review。

- 单侧直接边推导 opposite 时，输出直线证据和 full position 同时传播完整有符号 W interval，
  避免 W 不确定性抵消真实角点方向 departure。没有新增像素查询、候选、权限或 bleed；
  最小反例覆盖缺失 START/END、正负斜率与三种原始 full 余量，旧代码 8 个子用例失败，现均通过。
- 已按原共享域合同闭合的直接 Cross pair，不因某侧新增 source-spanning 连续性而降为单侧 H 推导。
  候选选择、外侧反证和最终授权复用同一 pair proof，删除重复判定；局部互补 closure 不能在选择时
  被排除，却又冒充完整方案免除反证。多个合法 pair 仍保持竞争，不按支持数或外侧顺序强选。
  新增测试覆盖两侧翻转、2/4 个共享域、1/2 个局部重合 trace、合法竞争与完整连续 pair；
  旧提交在 4 个测试中的 9 个子用例失败，新提交通过。未修改阈值、搜索上界或 Gate。
- S089/S091 从 enclosing support 改为直接 aperture pair，仍为安全 auto，不计新增覆盖。
  S038 仍有两个合法 aperture pair，最终使用唯一 enclosing support，但逐侧预算仍阻断 auto。
- Top/bottom 共用预登记的完整 lane 短轴 `CROSS_BASELINE`，替代各查询小窗口独立 median/MAD。
  Sequence 仍使用原完整长轴基线；没有新增物理 intent、测量阈值、solver pass、Gate 或 reference 权限。
  两组窗口保留原 ownership 与源边 kernel 可观测性；基线不产生任何 transition 或 placement evidence。
- 根因正反例：S106 同尺度合成 trace 的内侧 raw tone/texture 不变时，远处阶跃能把旧局部
  tone z 从约 100.857 降到 1.100，使真实内侧 material 消失。共同基线恢复该信号，旋转轴和窗口变化
  保持同一内侧测量；未把合成对照冒充原 TIFF 人工测量。
- 两轴基线顺序消费并释放数组；工作量计入全部 trace 同时保留的底层存储与处理缓冲，
  slice view 不重复计底层数组。该 detector 缓冲预算不冒充进程 RSS，像素与内存上限均未放宽。
- 单区域片段仍保留在完整 family 账本，完整并集达到原两区域要求才可获权；全局 solver 只消费获权线。
  不按 selected Frame 覆盖数抬高独立证据，不选择性合并较有利子集，也不删除新增测量。
- Report revision 为 `x5crop_v5_template_report_75`，gold record / summary 为 v20 / v23。
  `registered_normalization_revision` 绑定计划与报告。Runtime 与开发校验共用基线登记合同；
  缺失基线、虚构基线边界、lane 范围漂移、漏计像素或整组内存，即使重算总账也不能通过。
  原有 raw／角色／solver 回链、逐候选 Cross 支撑区间与 source extent 校验继续保留。
- 真实源域为 `[-0.5,width-0.5] × [-0.5,height-0.5]`，只在真实 TIFF 外缘求交，
  不普遍外扩内部边；requested 仍负责完整预算。黄金比较实际确认 polygon，严格检查角点包含；
  不能利用采样 AABB、源侧 cell 余量或预览图豁免内切。
- 源边、query 或 broad observable 域截断的峰尾仍不能取得精确定位。完整峰和内部已测弱尾保持原职责，
  未观测背景不能补造；此前平台分区实验未合入，详见开放风险。
- 纯离散歧义的 primary/runner 分别补全局部边界、投影弱线和约束自身联合包络，
  不共享 selected W、不重新排序、不扩大 6-pass 上界；原有 unavailable 与硬反证继续保留。
- Enclosing aperture-center calibration v9 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  S008 的 phase 转为 unresolved 后，不再满足 selected unique pair 资格，source 从 18 变为 17；
  没有新增来源，其余 17 份观测逐项不变。原始 hull 仍为 `[-0.007785885H, +0.009195549H]`。
  区间仍为 `[-0.008H, +0.010H]`，没有为更高通过率缩窄区间；精确 observation-set SHA 为
  `fc48b85367e5bb47a476bffc06833bf55070c2a18224253a9f731a5ad5f8251c`。
  最终全量重新派生与登记一致；登记不改变 pair 选择、采样 geometry 或 5% 阈值。

## 完整黄金与性能证据

最新完整开发 receipt：
`/private/tmp/x5crop-physical-line-position-final-full-gold-20260908h`。
110/110 完成、分析错误 0、全部物理校准登记一致：

| 层级 | 结果 |
|---|---|
| Primary proposal | 40 safe / 69 unsafe / 1 unavailable |
| Candidate | 28 safe / 8 unsafe / 74 unavailable |
| 最终决定 | 20 safe auto / 0 unsafe auto / 90 Review |
| Nominal | 20 safe auto / 76 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 188 份；46 safe / 142 unsafe |
| 每任务至少一份安全 | 43；40 个单份安全、3 个多份安全 |
| 全部保留候选不安全 | 67 个任务 |
| 安全候选且有明确 placement 歧义 | 10 个任务 |

Primary 实际生成 109/110；S051 的 primary 因 `phase_template_mismatch` 不可用，但仍保留一份
generated runner，黄金为 unsafe（第 1 格外扩超限）。因此全部 110 个任务仍有可评价的保留方案，
不能把 primary unavailable 说成整张无方案，也不能沿用早先 110/110 primary generated 的结论。

与上一版 `/private/tmp/x5crop-correlated-line-width-full-gold-20260908c` 相比，S002/S024 的 primary
由 unsafe 变为 safe；S065 从 safe auto 变为 phase ambiguous Review，尚无新增 auto。
S008 转为 `adjacency_topology_unresolved`，S018 转为 `discrete_phase_ambiguous`；
S110 保留真实 `direct_lattice_conflict`，不再发生 CLI 错误。
安全歧义任务为 S002/S005/S015/S024/S029/S034/S035/S048/S065/S067。

46 份安全候选中 31 项预算 passed / 15 failed；142 份不安全候选中 27 passed / 115 failed。
数值预算不能单独代替黄金安全，也不能据此整体关闭风险检查。

黄金运行开始于提交前，header 记录基座 `ffdbda76` 与当时的工作树身份，
不是干净 release receipt。已核对以下运行源指纹与提交 `36d18f8d` 一致：

- detector：`f8b573b74cb23416a8c176ea64c2ada70183f2291b46e549dc27d808780a5253`
- comparator：`27668cff96dba524c4000232d213ad7c5020694225fe21d7840ca8f996d3af40`
- cohort：`c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`

干净 `36d18f8d` 的正式 `tools/verify performance` receipt：
`build/v5-performance/performance_receipt.json`。24-source 完整用户路径均值 **3.639154 秒**，
5 秒 Gate 通过，3 秒挑战未达成；p95 为 6.306241 秒，最慢 S091 为 6.664384 秒。
未插桩进程峰值 RSS 最大 1,223,360,512 bytes；决定为 3 auto / 21 Review。
此结果只证明该提交、当前机器、冻结依赖和本次决定分布；没有相对上一版 3.606401 秒的性能提升声明。
新黄金 development-detail mean 为 4.339720 秒，不替代正式性能。

## 开放风险与精确下一步

下一机制优先接续 raw physical 联合位置/方向到角点保护链；S065 的候选完成不对称同步保留为待修根因。
以下 S038/S064 的只读诊断已完成，尚无可合入修复。
这些诊断未修改生产代码；完整黄金与正式性能仍使用上节 receipt，不能把单样片诊断当作新全量验收。

1. 共同基线前后的 S038/S064/S067 已分别通过正式完整 flow 生成报告并校验，不能为恢复旧 auto
   回退共同基线、强选旧线或放宽 Gate。当前已区分的支撑、角色、选对与预算问题：

   - S038：新增 source-spanning TOP 仍与两条 BOTTOM 满足原共享域合同。权限不一致已修复，
     但两个合法 pair 仍竞争；不能仅凭支持数保留旧 pair。Primary/candidate 安全，唯一 enclosing
     support 的最大逐侧外扩约 1.512 mm 超过 1.2 mm；正式报告为
     `/private/tmp/x5crop-S038-spanning-pair-final-report-20260908a/x5_crop_report.jsonl`，仍仅预算阻断。
     两组配对的只读完整 footprint 对照已完成：BOTTOM line 27 的方案第 5/6 格外扩超限，line 31
     的方案黄金安全；对照见 `/private/tmp/x5crop-S038-all-pair-assay-20260908b.log`，不是 Runtime 选边。
     局部 BOTTOM 的外侧背景支撑也覆盖两个原查询区域，不能用“只有一区域”删除它。
     内容格点虽跨过其 canonical 线，计入完整位置和方向区间后仍不足以否定整组可能边界；
     现有 content veto 只检查最终 post-bleed 输出，不拥有 native boundary identity 筛选权限。
     下一步需独立物理证据或经验证的可用性选择，不能按黄金答案、单条中心线或支持数删竞争者。
   - S064：原互补配对没有共同 trace；新 BOTTOM 增强后与 TOP 共享 11 个 trace，但全部位于
     第一个 selected domain，切换为 `shared_traces` 后不能获得完整投影权限。单侧 H 推导使
     三格 cross_low 外扩超限，primary unsafe。最小反例已复现同一 pair 增加 trace 后投影权限先下降、
     再恢复；这证明分支合同不一致，未证明原互补授权更可靠。下一步先定义可保持的物理支撑合同，
     同时检查新增证据、真实反证与候选竞争；不能直接合并两个 mode、增加回退或按旧 auto 反调条件。
     现有 `test_two_shared_domains_cannot_export_complementary_tails` 只断言权限政策，没有输出 polygon、
     真实边界或最终 Gate，不能把它当作独立几何反例。旧互补授权过宽与新共享条件过严均待物理证明。
   - S067：两条 TOP 原已存在，新 BOTTOM 的完整覆盖让第二个 TOP/BOTTOM 配对满足原
     “两共享域且一侧全覆盖”条件。两条 TOP 的全体 union refit 未成立，不能因同属 family
     就合并 identity；primary safe、runner 第 1 格 sequence_start unsafe，仍为
     `non_equivalent_fits`。当前 20 个安全 auto 均不依赖互补支撑分支，该分支仍影响 S067 的竞争；
     收紧分支也可能删除竞争者并改变最终决定，不能把“收紧”本身当作安全证明。
     下一步核对真实 side-track 连通性、方向变化与物理 identity。
2. S002 的 START full reference 位置已从 `[167.833295,197.588524]` 修为
   `[154.575926,203.802469]`，与十条 raw physical interval 的独立 LP 一致；本轮 primary 黄金安全，
   phase 与 Cross 歧义仍保留。正式报告为
   `/private/tmp/x5crop-S002-physical-line-position-20260908e/x5_crop_report.jsonl`。
   第 1 格 END 仍由 START 与共同 W 推导；前两区域有宽缓材料峰，第三区域没有获权峰，
   不能降低区域门槛补造 END。原只读证据见 `/private/tmp/x5crop-S002-broad-region-assay-20260908b.log`。
   下一步是 measurement 到输出的联合角点：raw region 尚未进入 `SequenceRoleLineEvidence`，
   当前 fixed-span 方向 padding 不闭合两轴相互推动。例如
   `x=3000+0.05(y-1000)`、`y=2000+0.05(x-1500)` 的真实角点为
   `(3053.884712,2077.694236)`，固定 span 分别投影只有 `(3050,2075)`。
   优先验证有界二维线族顶点交点的保守保护包络；分母 `1-m*n` 必须在完整参数乘积上同号。
   raw region 只能按实际 native/单侧 W/无直接边分支的合法可达范围裁剪，不能用 Grid 范围删除
   native 状态；外包络不能冒充 same-state W/H、rank 或 enclosing 风险证据。
   方向、residual、pixel-center、bleed 与 topology 位移须各计一次，域外 residual 仍需独立闭合。
   不新增通用搜索器或未经证明的 LP 工作量，也不提前开展逐 Frame W 审计。
   S065 的独立只读探针另确认两候选都能由各自第 1/2 格量到 W
   `[2422.313133,2475.879781]`，并从同一 registered separator 分别推导 wide adjacency 1。
   当前 best 已完成、runner 未完成，且 best W 窄化后的 source geometry/ratio-H/Cross 被共享；
   证据在 `/private/tmp/x5crop-S065-runner-authority-readonly-20260908g`。
   后续应收敛唯一候选完成 owner，各自消费原共享扫描基座与自己的 W/adjacency/条件 Cross，
   删除 detector 临时重算 runner 权限；保留原候选顺序、竞争与真实 6-pass 工作量。
   两个 W 数值相同不等于 authority 可互换，单边完成失败不得删除候选后批准另一边。
3. S106 当前正式报告为
   `/private/tmp/x5crop-S106-cross-baseline-final-report-20260908a/x5_crop_report.jsonl`。
   raw 26／local 21／solver 5，拟合 28；内侧 BOTTOM 的 line 20 恢复 11 点、trace 5134–6927、
   两区域且外侧背景偏好 1.0。另一条 source-wide BOTTOM 仍为 83 点、背景偏好 0.433735，
   不能丢弃大量 texture ties 后声称角色已闭合。当前仍 `direct_role_authority_unavailable`。
   TOP query `[0,172.624857]`、113 traces、window=21/gap=5，可测下界 26 px；
   人工真实 TOP 约 -31.23 至 18.01 px，当前 kernel 并未观察到。不得降低 kernel 或把完成 query
   当作缺边反证；源边角点与后半段仍有真实包含缺口，S106 仍是 nominal。
4. S103 当前正式报告为
   `/private/tmp/x5crop-S103-cross-baseline-report-20260908a/x5_crop_report.jsonl`。
   raw 73／local 69／solver 4，拟合 75，仍纵向支撑不包围完整 template，primary/runner 均不安全。
   对上一版 family 关联的只读审计：去掉同 trace 不同 transition 的连接，或拒绝相同物理区间
   加原 0.10 mm 后不存在共同直线的两成员连接，均未拆开原 TOP/BOTTOM 各 11 成员组件。
   因此未合入这些无效规则；下一步需证明成员身份与可关联域，不能选择性 sub-hull 恢复旧有利答案。
5. 先澄清平顶峰分区的定位与物理区间职责，再改分区。200 px trace、背景 20、
   `values[50:60]=220`、scale=81.514422、query=`[0,199]` 的梯度平台中心为 50 px，
   现分区 canonical 为 48.5 px；实际阶跃分界 49.5 px 仍在 localization `[45.5,51.5]` 内。
   反极性 run 分区实验使 S086 获不安全 auto、S003/S095 失去安全 auto，未合入。
   对照目录为 `/private/tmp/x5crop-localization-S086-baseline-20260908a` 与
   `/private/tmp/x5crop-localization-S086-partition-20260908a`；如继续，核对 5 条 coarse sharp trace
   （130、3784、7177、10570、14141）的原／新峰区间、`_unique_nearest` 与物理直线可行性。
6. S069 本轮已安全 auto；其旧 transition 1330 的 exact-union 无解证书仍是反例线索，
   不再将旧失败视为当前状态。证据为 `/private/tmp/x5crop-family-S069-20260908.jsonl`。
   S051 的 primary 生成缺口及 unsafe runner 仍需回链 `phase_template_mismatch` 与保留方案的外扩，
   不能为补齐 primary 数量晋升 runner 或删除失败身份。生成层优先处理上节 67 个全部保留方案不安全的任务。
   首轮离线 ridge 排序 `/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`
   仍绑定旧 `38178c4a`，折外由 36 safe 降到 34，未接入 Runtime，不是当前集合重训结果。
   可用性选择仍在当前 nominal 计划内，不以全部 nominal 自动通过为开发前置条件；后续在当前源码绑定
   的有界集合上审计风险特征与多正例选择，正式概率权限另需独立 calibration、OOD 与拒绝验收。
7. 当前仍为 `development_only_not_release_ready`。没有 sealed cohort，黄金未覆盖
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
