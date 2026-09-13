# 项目记忆

更新：2026-09-13。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与执行顺序

- 产品目标是完整、留边不过分、能够直接使用的照片：包含人工确认区域和倾斜四角，真实源外内容除外；
  每侧实际照片 W/H 的 5% 是质量上限，正常输出保持小幅留边。内部误差预算只是风险代理，
  必须同时检查误拒合格方案与漏判不合格方案；不能直接取消、放宽阈值或扩大 bleed。
- 目标是让当前 96 个 development nominal 全部正确 `approved_auto`，全部角色 `unsafe_approved_auto = 0`；
  challenge 尽量安全自动通过，安全 Review 不掩盖能力缺口。发布前全部要求绑定同一 release commit。
  中间开发可暴露危险 auto，但必须保存具体边界与根因并明确不可发布；release commit 才是硬性归零验收。
- 保持 current-only、唯一 canonical owner、无旧兼容、无样片特例；不放宽 format/count authority、
  人工黄金、真实反证或逐侧预算，不通过事后修框、合并互斥候选或扩大 bleed 获得批准。
- 正式 24-source 完整用户路径平均耗时 `<= 5s`，持续争取 `<= 3s`；工程、黄金、正式性能、
  TIFF/metadata、安装、三目标平台、打包和 Hook/CI 分别验证。
- 执行顺序为 Cross 优先，再集中处理剩余长轴问题。Cross 同时负责照片上下边界的解释、短轴位置和
  高度，明确区分照片边与外框支撑。冻结无关长轴算法调整，使用当前 W 和各格长轴范围；只处理妨碍
  Cross 正确性验证的必要依赖，不要求两轴完全解耦。
- 每轮分别报告短轴质量改善、整组合格方案任务数、可靠自动交付数、错误自动交付数，并保留端到端与
  性能验证。当前先修复没有合格短轴方案的 28 个任务，再处理已有合格方案的可靠选择与误阻断。
  整组仍有 64 个任务无合格方案，另有 27 个已有合格方案但 Review。多个解释或多个合格方案不应永久
  阻断输出，有充分可用性依据即可选择，不要求唯一真实边界；精确合同见架构第 9、14 节。
  补齐外框、扩大保护、增加 Review 或 Cross 变为 resolved，本身均不算产品质量进展。
- Source-W、有界候选集合、typed features 与首轮离线开发排序已验证。首轮排序没有改善选择，
  不具备接入 Runtime 的依据；继续核查风险代理的物理职责与不安全候选生成根因。
  不要求全部 nominal 先通过才开发评分；排序不是概率，概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末共同 W 审计。当前只登记，不打断现有工作，
  不提前增加自由度、隐藏 observation 或回退已有正确改动。

## 当前源码与已验证事实

当前 Runtime 为 `52f3c005891e0a5e8ee082f694c6cb29cfbb543c`，已正常提交并推送 main。
完整原子归属搜索、整批拟合预检和可重放工作账本已接入同一 registration owner，新增解释仅为有条件提案。
前一接受 Runtime 为 `80f60d02219cf9df2970f7b1e7f6f643dc92cfb3`。Canonical 完整组作为不可拆分输入，
新解释只保留完整 raw 并集；原有 Cross best/runner/H 与自动权限独立决定。每条 lane 至多追加一份
有条件提案，全部物化、预算与特征计入实际工作量；不扩大像素查询、phase 搜索或原 Cross 总上限。
完整合同见架构第 8、9、14 节。Report revision 80；Gold record/summary v21/v24，无旧 schema 兼容。

本轮 74 项搜索、registration、报告、runtime 与 Debug 专项测试通过；110-task 正式 production flow
与全部 current report 校验完成。S013/S031/S032 正式 Debug Analysis、report 校验及单张有界预览检查通过。
本轮正常 pre-push 工程验证通过，共 935 项测试、2 项按既定条件跳过；干净提交性能见下一节。
[当前 Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34764480215) 的 12 个环境组合全部通过。
工程 CI 不替代最终三目标实机发布 receipt；前一接受 Runtime 的 12 组合全部通过。

冻结环境为 `/private/tmp/x5crop-frozen-20260910`，SciPy 1.18.0、tifffile 2026.8.16；依赖检查已通过，
系统共享包未修改。后续先核对该环境仍存在，并在 PATH 前置其 bin；共享 Python 版本已漂移。

- Sequence full reference position 同时包含原 residual/localization 保护与同一 raw physical family
  的完整位置投影；`PhysicalLineRegion` 保留位置/斜率联合顶点，原角度上限、角色资格与 rank 不变。
  最小不对称反例、退化点/线段、大坐标相切与 288 次独立 LP 投影对照通过。
  输出继续保留同一线族；aperture 按实际 native 可达范围裁切，并解析闭合两轴角点保护。
  原始端点准入按整帧所有状态共享，有限轮次不新增 query/候选/通用 solver；mandatory/requested 分开。
  删除旧 fixed-span aperture 分支，线族准备提升到 frame 级，requested 保护复用；98 次逐帧结果
  对照完全一致，67 项专项测试通过。本轮 enclosing 已接入相同原始端点准入与有界角点闭合，
  同时保留 `(top,bottom,slope)` 全部三维顶点，避免投影位置后丢失可达斜率。
  四个独立输出反例的原始端点漏包均归零；requested-only 端点不污染 mandatory。
  Cross、registration、联合输出等 191 项专项通过，extent 修正后的 106 项 Cross 测试通过。
  当前完整工程 Hook 与正式性能均已通过；全部 nominal 自动通过仍未达成。
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
- registered observation → phase binding → frame line 的完整物理来源与唯一有符号 W 位移被独立校验。
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
- Enclosing aperture-center calibration v12 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  当前 selected support 集合为 22 source / 22 task；原始 hull 仍为 `[-0.007785885H, +0.009195549H]`。
  区间仍为 `[-0.008H, +0.010H]`，没有为更高通过率缩窄区间；精确 observation-set SHA 为
  `754fc1d473c694eea389ccaf673de678c547f8c2b007f27ebd5fad66c391798d`。
  来自冻结环境完整黄金派生；非冻结环境的5个中点相差最多约7.6e-9px，但原始hull与校准区间不变。
  精确身份按冻结环境重新登记，未放松核对；登记后全量复验通过。登记不改变 pair 选择、采样 geometry 或 5% 阈值。

## 完整黄金与性能证据

最新完整开发结果：`Test/gold_analysis/whole_atom_membership_full_20260913`，冻结依赖下
110/110 完成，分析错误 0，全部 current report 与物理校准通过。它是 development 验证，不是 release receipt。

| 层级 | 结果 |
|---|---|
| Primary proposal | 39 safe / 70 unsafe / 1 unavailable |
| Candidate | 27 safe / 13 unsafe / 70 unavailable |
| 最终决定 | 19 safe auto / 0 unsafe auto / 91 Review |
| Nominal（96 任务） | 41 生成合格方案 / 19 安全自动交付 / 77 Review |
| Challenge（14 任务） | 5 生成合格方案 / 0 自动交付 / 14 Review |
| 短轴合格方案 | 82 个任务：nominal 73 / challenge 9 |
| 无合格短轴方案 | 28 个任务：nominal 23 / challenge 5 |
| 保留候选集合 | 220 份；57 safe / 163 unsafe |
| 每任务至少一份安全 | 46 |
| 无合格方案 | 64 个任务：nominal 55 / challenge 9 |
| 已有合格方案仍 Review | 27 个任务：nominal 22 / challenge 5 |

与接受基线 `Test/gold_analysis/constrained_family_full_20260913` 按 source SHA、format/count 和角色
对齐：短轴合格 80→82，整组合格 45→46，安全 auto 19→19，错误 auto 0→0。原有 189 份 canonical
placement 的实际 `required_source_footprint` 多边形逐项完全相同；全部最终决定相同。
S031 新条件方案短轴 6/6 合格、长轴仍不安全；S032 新条件方案整组安全。S016/S018/S019/S064
只有部分短轴改善，均仍不合格。S101 原 runner 12/12 合格短轴保持。其它任务的质量指标无退步；
具体对照保存在该目录 `baseline_quality_comparison.json`，可重算脚本为 `compare_current.py`。
S051 primary 仍不可用，保留的 runner 可评价但不安全；不晋升 runner 或伪造 primary。

短轴统计读取同一最终 footprint 的逐帧 cross_low/cross_high 内切与外扩诊断，并核对全部已确认
`boundary_pair` 身份，包括局部照片。S007/S049/S050 各有一格 `not_applicable` 空白曝光：输出 count
仍为 6，几何比较为 5 格；不能把空白格当遗漏，也不能漏掉已有 reference 的局部照片。
短轴合格不能替代整组四边合格，数值预算不能替代黄金质量。
S005 有条件提案虽然黄金安全，数值预算仍失败；生成进展尚未解除其自动准入缺口。

当前结果的 detector 指纹为
`13a1550525d3f9cee9651583bfb80821f187c306bb18e474b2a66c9846e98bbb`；
comparator 指纹为 `ce0affae8d78c904f0a0178b76932091bf6eb37e776de6ce872d634fea2f0bb9`；
cohort 为 `c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。
该全量运行从未提交源码开始，不能伪造为同一 release commit receipt。提交后已确认 detector、comparator
与 cohort 指纹逐项完全一致；独立复核保存在 `post_commit_identity_verification.json`，原 receipt 未改写。

干净 `52f3c005`、冻结依赖下 `tools/verify performance` 完成：24-source 完整用户路径均值
**4.015434 秒**，5 秒 Gate 通过，3 秒挑战未达成。p95 为 7.210149 秒，最慢 S109 为 7.212746 秒；
未插桩 peak RSS 最大 1,224,179,712 bytes。决定为 2 auto / 22 Review。
当前 receipt 为 `build/v5-performance/performance_receipt.json`，并保存在本轮黄金目录
`performance_receipt_52f3c005.json`。它仅证明该提交、当前机器与本次决定分布。
前一接受 Runtime 均值为 3.852067 秒；本轮均值增加约 0.163 秒，不能声称提速，不用剖面时间替代正式计时。

## 开放风险与精确下一步

本轮正常 Hook、正式全量黄金、干净提交性能与 12 组合 CI 已完成；继续剩余 28 个短轴任务。
新增测量或完整拟合不能挤掉已有合格
短轴备选。完整分组的数值补充只保留为有条件提案，保持原 canonical 两阶段与排序相关编号。
完整原子归属已接入并保留 S031/S032 的生成收益。下一步先核对 S018/S019/S064 条件方案剩余
cross_low/cross_high 内切与外扩失败，区分原测量覆盖、归属、方向和输出保护贡献。保持完整 canonical
原子及全部原测量，不按拟合或黄金结果挑子集；S031 剩余长轴问题不算短轴失败。
有条件 family 不能侵入 canonical 选择；首次侵入版本曾丢失 S022/S084/S089 的安全 auto 并使 S062
首选退步，已由权限分离和独立提案位置修复。失败版 `cross_conditional_family_full_20260910`
不能作为接受基线。
S005 的 73 条完整 raw 并集已正式生成安全有条件提案，原组原样保留；身份歧义与准入仍未解除。
不能按黄金结果删除另一合法 anchor，不能因存在多份方案永久拒绝可靠选择。下一步需有界归属证据
或经验证的可用性选择，不直接放宽预算。
S006 与 S101 已有的完整短轴备选保持；它们的剩余长轴问题继续冻结，除非构成 Cross 的必要依赖。
诊断图以黄色虚线标记有条件方案。原有长摘要越过标题的问题由现有文本宽度裁剪消除；
该显示修改发生在完整黄金之后，不改变检测或比较路径。图像预览不作黄金判断。

S018 bottom :67 的 raw2835..19845 未包围头尾；左侧 :66/:73 均多重归属，完整 refit 分别丢弃
8/1 个 transition，不能选择性删除恢复；末 query20115 没有 raw transition。
S012 F1 top 外扩110.642px、上限107.399px，主要来自coarse首raw4995之前的域外方向保护；仅相容的
TOP :21 两条宽区间不收紧任何共同直线状态，且有22种其它归属。不能以它延长coarse实测域并取消保护。
S016/S033/S036 当前都从外侧TOP加固定H推BOTTOM，后者缺少直接绑定；但测量拒绝细因不同。
S016 TOP :3 上移约67.317px、固定H比黄金跨度短49.153px，导致BOTTOM native内移约116.470px。
当前phase与Cross的四个现成组合只读生成后仍全部不合格，不能靠补一个runner解决，暂不扩大两份上限。
S033 的78条BOTTOM observation均只有一个独立区域；178+160、160+170完整raw并集可分别保留，
但都无法与现有15条TOP闭合直接pair。三者共同域为空，不能挑子集作为唯一边界；只改归组不足以改善输出。
S036 的BOTTOM :75只在共享参考点外推后接近黄金；其两条原始测量在实际x处内移约57–60px，
不能视为已测正确照片边。后两格没有覆盖人工BOTTOM的raw，需补充有效测量而非放宽角色条件。
S016独立端点诊断中，x19972的BOTTOM转变与 :45 全部61条原始约束相容，x308的7个BOTTOM
转变则全部不相容，最近仍差14.672px。仅补两端不能闭合完整边界族。诊断复用同一灰度场，独立登记
公共baseline和原TOP/BOTTOM窗口，未进入生产结果；当前合同仍禁止candidate-specific requery。
S031 本轮正式报告的 51-transition 有条件 TOP 完整组只包含 45 条不同 trace，五条 trace 上存在
不同 transition；一线一 trace 的合同至少淘汰六个成员。因此先处理身份归属，不能仅靠 Huber 容差
或约束代表点声称该组完整通过。证据为 `/private/tmp/x5crop-S031-complete-family-audit-20260913.json`，
绑定同次 production report；它是归属诊断，不是 reference。

完整分组数值补充的两个 110-task 实验均已归档，均不能替代正式 Runtime 或 release receipt。
`Test/gold_analysis/complete_family_numerical_probe_20260913` 允许新增解进入 canonical，
导致 S101 新 TOP 占用原两槽之一，原 BOTTOM runner 的 12/12 合格短轴被挤出；该方案未接入。
`Test/gold_analysis/constrained_conditional_probe_20260913` 保持原 canonical，只补充有条件解：
原 189 份 canonical polygon 完全相同，短轴合格 78→80、整组安全 43→45、安全 auto 19、错误 auto 0。
S041/S050 是同一 source SHA 的两个格数任务，不能计成两个独立源；新增条件方案安全，原两方案仍不安全。
S032 最佳短轴 4/6→5/6，第 1 格左下角仍内切 `0.336718 px`，不得按该差额增加 bleed。
这条路径已整理为当前源码：原始 run/精修、canonical 验收与物理限制保持；完整数值解具有独立方法、
原始约束复查及实际工作 receipt。有限 gap 只是浮点核验，不是严格舍入认证；
原严格距离比较与现有闭集 `1e-9 px` 算术判据的区别已在架构中明确，不能宣称数值判据完全未改。
正式四任务重点验证目录为 `Test/gold_analysis/constrained_family_targeted_20260913b`，
原两方案 polygon 均完全相同；S101 保持 12/12 合格短轴。正式全量与干净提交性能结论见上一节。

归属搜索只读量级验证：S031 原 7 个完整原子、固定两区域 anchor 的 64 个子集有 4 个包含极大可行
集合；一般情形仍可能指数增长，不能无界枚举。S032 原 BOTTOM 72-raw 组含 17 个完整原子，固定
两区域 `:48` 后，以 trace 冲突/完整物理空域作单调剪枝，397 个 visited states 穷尽 65,536 个潜在组合；
74 个可行集合中有 16 个包含极大集合，完整 raw 数 24–40。主线程复算计数与全部 16 个独立 LP 可行性
一致；8-state 耗尽反例必须返回 incomplete、没有可用 maximal 前缀。该量级不证明其它组都在预算内，
也不证明这些组合可完整 refit 或裁切安全。接入前必须定义全部访问、raw 裁剪、拟合和候选保留上界；
耗尽保持未解决，不按前 N 组、成功 refit、黄金或支持数删除其它身份。

完整原子归属的 110-task 原 TIFF 实验保存在
`Test/gold_analysis/whole_atom_membership_probe_20260913`，绑定 `80f60d02`，不属于当前 Runtime
或发布证据。108 项完成结构校验与黄金比较：原 primary/runner 的实际 polygon 全部不变，短轴
整组合格 79→81，整组安全方案 44→45，安全 auto 19、错误 auto 0；这组分母排除了 S013/S059，
不能冒充成功的 110 项结果。S031 新条件方案短轴 6/6 合格、长轴仍不安全；S032 新条件方案整组安全，
二者均仍 Review。S016/S018/S019/S064 只有部分短轴改善。31 项用尽每 lane 4096 次访问后整批不添加
新方案；其余 77 项共新增 3029 次完整 union 拟合。搜索 complete 仅指有 anchor 的合格原子宇宙，
无 anchor 的 family 不在该完整性声明内。原脚本 `maximality_checks` 为潜在次数上界，不能当实际次数。

该实验暴露了现有拟合上限：S013 TOP 的 constrained 次数 91>78，S059 BOTTOM 为 88>58，
两项被原 `2R` 校验拒绝。另有 12 个结构校验成功的样片超过每角色 `3R` 稳健拟合合同；S091 TOP
为 282>213。因此报告结构通过不能证明新机制的工作量合格。108 份报告与两项失败现场的完整原子
组合均未发现同 raw union 对应不同成员集合，也未发现重复生成原 canonical 单原子 union；这些
有限样片不能排除一般反例。全部比较与计数见该目录的 `EXPERIMENT_SUMMARY.json` 和
`MEMBERSHIP_WORK_AND_PROVENANCE_AUDIT.json`，原实验 receipt 保持不变。

整批拟合前预检实验保存在 `Test/gold_analysis/whole_atom_membership_preflight_20260913`。
每角色 R 为原 registered run 数，U 为原唯一 family union 数，C 为原 constrained 次数，K 为全部
新增唯一 union 数；拟合前要求 `R+U+K <= 3R` 且 `C+K <= 2R`，任一侧超界则整 lane 不添加
新候选，不执行新增拟合。7 项正式完整 flow 实验复测无错误：S031/S032 的上述改善保留，
S013/S059/S091 拟合前整批拒绝并保持原结果，S022 保持安全 auto，S112 搜索耗尽后保持原结果；
全部 canonical polygon 不变。独立 LP 穷举 64 组合得到 16 个可行集合、9 个包含极大集合，与搜索
一致；另已核对排列不变、8 次访问耗尽不返回前缀、多 anchor 两两可行但联合为空、闭集点状交集。
这是研究验证，不是新增正式黄金或性能 receipt。

上述研究现已整理为当前生产路径：搜索状态、固定 anchor 与完整原子宇宙、全部极大归属解释、raw union
缓存和逐成员 provenance 由唯一 owner 保存，实际访问、物理域裁剪与极大性检查可由原 query 重放。
新增拟合保持原 `3R`/`2R` 上限，下游继续使用原 512 observation / 4096 pair/fit 上限。
原观察全集与后续精修按阶段和实际拟合次数对账；同时篡改冻结列表与精修标记、却没有相应拟合工作
的反例已被测试拒绝。共享访问预算恰好用尽 4096 后下一 scope 请求访问的边界也已覆盖。
几何多边形顶点只能完整覆盖无 trace 冲突的交集解释；同 trace 不同 identity 可以编码任意冲突图，
互不相交的三角冲突组已有指数多个极大集合，不能以二维参数空间声称一般搜索为多项式。
耗尽或 provenance 不能闭合时必须明确不可用，不输出搜索前缀，不以极大性授予 family 或 auto 权限。

此前 S031/S032后段TOP内切最大12.939/38.605px，已选raw本身全部被输出包住。S031的7+4完整并集在
原bend域内可行，但Huber代表点会丢4点；S032的11+4则因同trace只能保留一点而丢 :156，
该点本身未超过bend阈值。S031片段 :4 同时兼容anchor :2/:7，三者共同域为空，现行partition保持歧义。
只读对照证明：仅把完整族Huber代表点约束到原bend可行域，登记、Cross和输出均不变；不能把优化器
漏解修正单独计为产品进展。下一步仍是保留完整provenance的多族方案及归属反证，不强制唯一分配，
不改变同trace身份、raw物理域、角色准入或预算。完整原子方案的生成已完成接入，身份准入仍须独立证据。
将coarse sharp view从5条扩展到全部9条已测trace的只读检查亦未证明收益：S012 F1 TOP外扩反增到
113.608px；S013失去完整pair；S027超出当前联合投影顶点上界。未接入Runtime或放宽上界。
S097 的BOTTOM外扩120.986–162.771px主要来自完整H半区间133.840px，而非canonical H过大。
已选TOP有109条raw，但仅49条physical interval与人工边相交；BOTTOM没有获权完整族，source W
独立权限也不可用。不得收窄H区间或删除原保护来恢复通过。
S016 将材质窗口移到physical interval外侧的只读实验仍无整组短轴合格方案；相邻两阶跃反例会让
新窗口跨入另一条边，在平坦材质中制造相反texture偏好。未替换现有测量字段，后续必须先证明
邻边隔离与真实材质可观测性，不能按单张改善普遍修改。
S061 的正短轴外扩与 inward flags不矛盾：F1约2374px长轴头部缺失触发真实斜角半平面失败，
属于必要长轴依赖；同时四格BOTTOM仍外扩超限，不能计为短轴合格，也不修改比较器消除角点失败。
S021 方案仍黄金合格，但改变支撑用途后不再把外框当作 source H，内部预算阻断；留待生成问题后处理，
不能为恢复旧 auto 让外框重新冒充照片 H。S028/S093 长轴审计与 S065 候选完成不对称暂时冻结。
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
     `non_equivalent_fits`。当前 19 个安全 auto 均不依赖互补支撑分支，该分支仍影响 S067 的竞争；
     收紧分支也可能删除竞争者并改变最终决定，不能把“收紧”本身当作安全证明。
     下一步核对真实 side-track 连通性、方向变化与物理 identity。
2. S002 的 START full reference 位置已从 `[167.833295,197.588524]` 修为
   `[154.575926,203.802469]`，与十条 raw physical interval 的独立 LP 一致；本轮 primary 黄金安全，
   phase 与 Cross 歧义仍保留。正式报告为
   `/private/tmp/x5crop-S002-physical-line-position-20260908e/x5_crop_report.jsonl`。
   第 1 格 END 仍由 START 与共同 W 推导；前两区域有宽缓材料峰，第三区域没有获权峰，
   不能降低区域门槛补造 END。原只读证据见 `/private/tmp/x5crop-S002-broad-region-assay-20260908b.log`。
   Aperture 的 raw region 与两轴闭合已接入当前输出，合同见架构第 10 节，不再重复固定 span 计划。
   Enclosing 的 S059 旧版独立角点 witness 显示 END 少约 0.739 px，本轮已统一闭合原始端点与角点保护；
   旧反例为 `/private/tmp/x5crop-S059-enclosing-native-audit-20260908p/native_corner_witness.json`。
   同例新增 115.792 px 的方向保护有合法 raw/W witness，不能收窄 family 恢复 auto。
   S028 新增 37.298 px 也有合法 raw/W witness；原生裁剪为 no-op，精确同状态角点最多只节省
   1.054 px，远少于恢复黄金所需 13.722 px。证据为
   `/private/tmp/x5crop-S028-enclosing-native-audit-20260908q/native_geometry_audit.json`。
   后续区分真实测量歧义和保守包络余量；不能因为较窄旧输出碰巧黄金合格就丢弃物理反例。
   S065 的独立只读探针另确认两候选都能由各自第 1/2 格量到 W
   `[2422.313133,2475.879781]`，并从同一 registered separator 分别推导 wide adjacency 1。
   当前 best 已完成、runner 未完成，且 best W 窄化后的 source geometry/ratio-H/Cross 被共享；
   证据在 `/private/tmp/x5crop-S065-runner-authority-readonly-20260908g`。
   后续应收敛唯一候选完成 owner，各自消费原共享扫描基座与自己的 W/adjacency/条件 Cross，
   删除 detector 临时重算 runner 权限；保留原候选顺序、竞争与真实 6-pass 工作量。
   两个 W 数值相同不等于 authority 可互换，单边完成失败不得删除候选后批准另一边。
   S006 旧 aperture 输出的 canonical bottom 自身已外移约55.197px，内部只计新增保护，导致真实外扩
   120.381px 被低估；本轮同一 pair 的支撑用途与同状态 aperture-center 风险已取代该解释。
   原始端点仍完整保留，当前结果见上节；不能仅用旧风险数字推断当前漏项仍存在。
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
   不能为补齐 primary 数量晋升 runner 或删除失败身份。生成层优先处理上节 67 个无合格整组方案的任务，
   其中 Cross 优先处理 32 个无合格短轴方案的任务。
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
