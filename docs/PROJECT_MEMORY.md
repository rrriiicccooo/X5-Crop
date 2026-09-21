# 项目记忆

更新：2026-09-21。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
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
  TIFF/metadata、安装、三目标平台、打包和 Hook/CI 分别验证。正式性能合格在发布验收时确认，
  开发提交默认不运行 `tools/verify performance`，不再逐次生成性能 receipt。
- 当前先解决并验收 H 的共享上下边，再评估将同一几何思路推广到 W。H 在既有上下窄走廊内研究
  “从外向内贴近画面”：TOP 向下、BOTTOM 向上，同时约束位置、倾斜、有界 H、配对和空间覆盖，
  不要求逐像素移动。充分结合现有放置模型和联合搜索，不强制检测与模型严格串行；模型指导搜索，
  原始像素约束边界，整体几何检查相容性。模型预测及符合预测不能被重复登记为接触证据。
- 接触必须有多处可信实测支撑；灰尘、片夹边、内部强线和单个突出点不能独自成为停止依据。
  证据不足与多个合法解释保留不确定性。验证有效后在当前唯一机制内替换相应职责，删除被替代路径，
  不叠加第二检测器、旧兼容或样片例外。W 阶段须额外闭合逐张左右边归属和间隔、接触、重叠关系。
  H 验收前冻结无关 W 算法调整；现有 W、长轴范围和放置约束仍可参与 H 联合求解。
- 每轮分别报告短轴质量改善、整组合格方案任务数、可靠自动交付数、错误自动交付数，并保留端到端
  验证。当前短轴诊断仍有 23 个任务无合格方案，再处理已有合格方案的可靠选择与误阻断；
  S100 的诊断归因限制见下文。整组仍有 61 个任务无合格方案，另有 30 个已有合格方案但 Review。
  多个解释或多个合格方案不应永久阻断输出，有充分可用性依据即可选择，不要求唯一真实边界；
  精确合同见架构第 9、14 节。
  补齐外框、扩大保护、增加 Review 或 Cross 变为 resolved，本身均不算产品质量进展。
- Source-W、有界候选集合、typed features 与首轮离线开发排序已验证。首轮排序没有改善选择，
  不具备接入 Runtime 的依据；继续核查风险代理的物理职责与不安全候选生成根因。
  不要求全部 nominal 先通过才开发评分；排序不是概率，概率自动权限另需独立校准与准入证据。
- 此前确认的全部能力完成后，才启动文末共同 W 审计。当前只登记，不打断现有工作，
  不提前增加自由度、隐藏 observation 或回退已有正确改动。

## 当前源码与已验证事实

当前已验证提交为 `ceaf2f11371ae3382d1f8b2481c08c1cb8daeb94`，已正常推送 main。
前一接受提交为 `e077e3ac`，依赖合同仍为 `51f7b6fc` 的现场新版。
Cross 保留完整位置/斜率联合域与统计、raw 保护；两轴闭合后保留每状态左右总保护，按实际长轴端点
单次重投影上下边。外框支撑也已按各 sequence 状态的实际范围重算域外方向差，完整积顶点继续覆盖
连续位置/斜率组合及同状态风险。全部已准入端点保持共享，精确合同与证明见架构第 10 节。
没有增加迭代、状态、查询或选择权限。
完整原子归属及条件提案权限保持；没有增加 query、拟合尝试、Gate 权限或 bleed。
Report revision 85；Gold record/summary v21/v24，无旧 schema 兼容。

本轮保留两侧各自完整的已接受 raw，共同 trace 仍独立负责配对权限；原有 straight residual 按完整
本侧测量重算。248 项几何/报告专项与 20 项校准专项通过，独立只读复核无剩余发现。
110-task 正式 production flow、current report 与校准校验完成。S025/S081 正式 Debug Analysis 和
report 85 校验通过，均保持 Review、无正式 TIFF；它们分别验证中心观测变化和完整 raw 的保护传播。
正常 pre-push 共 945 项测试通过、2 项按既定条件跳过；干净提交性能见下一节。
[当前 Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34939465229) 的 12 个环境组合全部通过。
工程 CI 不替代最终三目标实机发布 receipt。

按用户要求，本机依赖升级后以现场新版为准，同步 `tools/install/dependencies.toml` 并验证，
不为旧合同或旧 receipt 降级共享库。2026-09-18 实际加载 Python 3.14.7、NumPy 2.5.3、SciPy 1.18.1、
OpenCV 5.0.0、tifffile 2026.9.15、imagecodecs 2026.8.16、Pillow 12.3.0；合同已同步，依赖检查及
18 项安装/TIFF/平台 I/O 专项通过。此前全量 receipt 不能冒充这组新版依赖的重新验收。
旧 `/private/tmp/x5crop-frozen-20260910` 已不构成独立冻结环境，本轮实际加载的是上述新版；
其目录名不能证明旧版本仍在使用。后续核对实际 import 版本与来源，入口使用 `/opt/homebrew/bin/python3`。

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
- Enclosing aperture-center calibration v13 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  当前 selected support 集合为 22 source / 22 task；原始 hull 仍为 `[-0.007785885H, +0.009195549H]`。
  区间仍为 `[-0.008H, +0.010H]`，没有为更高通过率缩窄区间；精确 observation-set SHA 为
  `7023a062693324829960e55560dd2f58bf19fde10aba9cfb909a280592c09eac`。
  唯一观测变化是 S025 支撑中点 1997.381016499→1997.028552802 px；黄金中心、H、资格和成员不变。
  原未同步登记的完整运行保留在 `cross_complete_side_full_20260915`，不作为最终接受结果；
  同步指纹后重新完成全量，决定、预算状态与逐帧质量不变，校准身份全部通过。
  登记不改变 pair 选择、采样 geometry 或 5% 阈值；历史环境标签不能代替当前 import 核验。

## 完整黄金与性能证据

最新完整开发结果：`Test/gold_analysis/cross_complete_side_full_20260915b`，当前新版依赖下
110/110 完成，分析错误 0，全部 current report 与物理校准通过。它是 development 验证，不是 release receipt。

| 层级 | 结果 |
|---|---|
| Primary proposal | 41 safe / 68 unsafe / 1 unavailable |
| Candidate | 28 safe / 12 unsafe / 70 unavailable |
| 最终决定 | 19 safe auto / 0 unsafe auto / 91 Review |
| Nominal（96 任务） | 44 生成合格方案 / 19 安全自动交付 / 77 Review |
| Challenge（14 任务） | 5 生成合格方案 / 0 自动交付 / 14 Review |
| 短轴诊断合格方案 | 87 个任务：nominal 78 / challenge 9；S100 归因限制见下文 |
| 无合格短轴方案 | 23 个任务：nominal 18 / challenge 5 |
| 保留候选集合 | 220 份；60 safe / 160 unsafe |
| 每任务至少一份安全 | 49 |
| 无合格方案 | 61 个任务：nominal 52 / challenge 9 |
| 已有合格方案仍 Review | 30 个任务：nominal 25 / challenge 5 |

与接受基线 `Test/gold_analysis/cross_side_observed_full_20260915b` 按 source SHA、format/count
和角色对齐：短轴诊断 86→87、整组合格 48→49、安全 auto 19、错误 auto 0。唯一整组标签变化是
S013 primary unsafe→safe，末格下边外扩 115.126596947→98.609929065 px，上限 108.425843952 px。
两份方案短轴均为 6/6；runner 原有首格 START、第三格 END 外扩仍在，主方案预算仍失败，最终 Review。
220 份保留方案无增删，1,167 帧中 38 个 required 范围改变，58 项 canonical/feasible 字段与
70 项 START/END 保护记录变化；没有新增 inward/outward failure side 或安全标签退化。
12 项新 polygon 超出旧 polygon，仅为 S081 两份方案的前两格、各三种范围；长轴扩大最多
0.001150282 px，旧覆盖仍包含在新范围内。TOP 独有 trace 11875 的 raw `[198.5,219.5]`
将 K 从 0.361330541 提高到 1.519225278 px，内部支撑状态使两格 raw departure 增加
0.046783626 px，经原有两轴闭合准确得到上述扩大；S081 原有第二格 END 内切与 Review 不变。
该控制状态解释来自当前正式报告的共同账本反事实，不能冒充旧 production 报告。
对照及可重算脚本为 `baseline_quality_comparison.json`、`compare_current.py`；校准身份核对为
`calibration_identity_verification.json`。本轮完整 raw 会改变内部状态，不声称 polygon 一律收缩。
S019 条件方案的六格四边及数值预算保持合格，尚未可靠选定，仍为 Review。S031/S032、S101 已有收益保持。
S100 的 12/12 短轴诊断沿用前轮归因：F6/F8/F9 的倾斜角点消失使部分内切半平面不再归到 Cross，
实际覆盖没有增加，仍有长轴内切且整组不安全；不能称为找回照片内容。
S051 primary 仍不可用，保留的 runner 可评价但不安全；不晋升 runner 或伪造 primary。

短轴统计读取同一最终 footprint 的逐帧 cross_low/cross_high 内切与外扩诊断，并核对全部已确认
`boundary_pair` 身份，包括局部照片。S007/S049/S050 各有一格 `not_applicable` 空白曝光：输出 count
仍为 6，几何比较为 5 格；不能把空白格当遗漏，也不能漏掉已有 reference 的局部照片。
短轴合格不能替代整组四边合格，数值预算不能替代黄金质量。
S005 有条件提案虽然黄金安全，数值预算仍失败；生成进展尚未解除其自动准入缺口。

当前结果的 detector 指纹为
`4665140f4cc76bc4c8151355323a80ad56a874179c48bd48c373679ca611f609`；
comparator 指纹为 `d38bab1f757aa6b5995507d2b0a5b2bfdb02962e4fce1293fffead7d6b9cdac6`；
cohort 为 `c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。
该全量运行从未提交源码开始，不能伪造为同一 release commit receipt。提交后已确认 detector、comparator
与 cohort 指纹逐项完全一致；复核为 `post_commit_identity_verification.json`，原 receipt 未改写。
依赖版本与来源由本轮正式性能 receipt 记录；
此前现场版本观察保留在上一轮目录，不伪造冻结环境声明。

干净 `ceaf2f11`、当前新版依赖下 `tools/verify performance` 完成：24-source 完整用户路径均值
**4.064568 秒**，5 秒 Gate 通过，3 秒挑战未达成。p95 为 7.290106 秒，最慢 S091 为 7.503203 秒；
未插桩 peak RSS 最大 1,226,850,304 bytes。
当前 receipt 为 `build/v5-performance/performance_receipt.json`，并保存在本轮黄金目录
`performance_receipt_ceaf2f11.json`。它仅证明该提交、当前机器与本次决定分布。
前一接受提交在相同依赖下均值为 4.068112 秒；单次差异不能证明稳定提速，不用剖面时间替代正式计时。
正常 pre-push 的 945 项工程检查通过、2 项跳过；CI `34939465229` 的 12 组合全部成功，
结构化结果保存在本轮黄金目录 `ci_verification.json`。

## 开放风险与精确下一步

`ceaf2f11` 的正常 Hook、正式全量黄金、干净提交性能与 12 组合 CI 已完成。它仍是最后接受的
Runtime 检查点；当前工作树有未接受的 broad 逐线原型及配套文档，不将其当作已合格版本。
开发提交不重复正式性能。以下新证据不能替代上文接受检查点或发布验收。

- 当前原型已删除区域均值的伪代表点，保留真实 broad trace/峰身份、完整物理区间与原网格多数。
  Runtime、report 87 和最终 edge provenance 校验同步；cross-height 弱梯度聚合保持独立。
  已删除 coarse 重复的 support-trace 字段与恒等 broad view，无旧类型或兼容别名。
- `Test/gold_analysis/broad_association_full_20260915` 已完成 110 项、0 分析错误，16 安全 auto、
  0 危险 auto、94 Review。2026-09-18 重新读取并核对 summary 聚合，改动前 detector/comparator/cohort
  身份与该 receipt 一致；同目录 `baseline_quality_comparison.json` 核对全部 source SHA、format/count、
  cohort role 与物理 frame 身份。相对接受检查点，整组合格方案 49→46（nominal 44→42，challenge 5→4），
  短轴合格 87→86（nominal 78→77，challenge 9→9）。S030/S044/S058 丢失整组合格方案；
  S058/S110 丢失短轴合格，S109 新增短轴合格。S012/S042/S086 已恢复整组合格。
  Primary 为 38 safe / 71 unsafe / 1 unavailable；候选为 20 safe / 13 unsafe / 77 unavailable；
  222 份保留方案为 57 safe / 165 unsafe。尚不满足 nominal 全部自动正确通过，原型未接受。
- 关联对每份 query 的实际峰只运行一次，保留完整多数且物理相容的极大 raw 集合；超界清空 paths，
  保留原始测量并阻止 selected placement。最终 edge 允许完整关联路径的子集或经过物理核验的完整
  source-region 并集。原始 material-band 身份加入映射后 ID，避免不同带映射同一边界对产生重复登记。
  2026-09-18 新版依赖下 114 项测量、关联、provenance 与 Runtime 专项通过；没有放宽 Gate 或把局部测量改为 reference。
- 新增的三项 auto 回退 S069/S078/S082 均为 `producer_bound_exceeded`，其合格方案仍保留。
  2026-09-18 三份正式 CLI/report 87 复现保存在 `Test/gold_analysis/association_bounds_20260918`。
  受阻 query 的 P 分别为 18/18/19；S069 独立穷举确认三个极大解释，长度 10/11/10。
  完成第一条后仍有非包含尾部峰，使保守未来 raw 集合阻止子集剪枝；不能只选最长解释或提高额度。
  新增的 18 峰数值反例仅验证完整结果须等于三个解释、超界不能泄露部分路径，尚未证明预算内完成。
  Cursor 收紧及插入支配实验均未在原额度内解决三例，未留在 Runtime；下一步需要改进极大解释搜索，
  而非继续叠加未取得收益的剪枝。
- S086 原始 footprint 投影失败后仍被选择，触发 `selected placement must reuse the primary proposal`。
  已在 source selection 前沿原 typed failure 撤下 unavailable primary，保留候选和原始投影原因。
  不放宽模型校验、不晋升 runner；故障注入覆盖该完整选择链。
- S086/S097/S109/S110 的原始投影问题均为截面角点占满顶点额度。新的 slope polygon join 只删除
  两侧均位于仿射边内部的组合，保留完整三维可行域；40 截面角点/24 极点反例有精确凸组合证书，
  真实 40 极点仍拒绝。原 64 次工作与 32 顶点上限不变。完整输出与同状态风险对照、退化测试及
  现有分别凸性合同通过独立只读复核；相关 114 项专项通过，新增完整输出对照另行通过。
  `Test/gold_analysis/broad_trace_vertices_20260915` 的四张正式 CLI、report 校验及同源官方黄金函数完成：
  S086 恢复 safe auto；另三张均恢复 proposal，但仍 unsafe Review。S109 短轴 7/7，S110 4/5；
  S097 primary/runner 分别 3/12、8/12。修复后的整体覆盖以本节新全量结果为准。
- S030/S042/S044 的旧源码隔离复跑报告位于 `broad_trace_old_measurements_20260915`，新报告位于
  `broad_trace_regressions_20260915`；旧 primary footprint 均与接受检查点完全相等。S030 真实 END 链
  8 点的区域计数为 `[4,2,2]/[4,3,4]`，末区不足多数，separator 消失，F1 END 改为宽模型推断。
  保存的同次 registered 数组与 `S030-measurement/signal_summary.json` 显示，在 2905–2940 px，
  trace 1848 最大 contrast z 2.85，低于原 3.0；2002 最大仅 1.333333。旧末区 3/4 是 polarity/background
  状态支持，不能替代真实峰。观测运行没有新增 pixel query，三层保护 polygon 与此前原型逐项一致；
  顶点压缩使 state count 80→48，risk 仅有约 1e-13 浮点差，不能声称完整报告相同。
- S042 的对应 START 实际存在完整相容分支，reciprocal-nearest 在 trace 2826 从 14539.5 选择
  14548.5，而另一条 14511 分支随后取得 3083:14519、3340:14503.5，导致主链失去末区多数。
  主链前六点接后三点时区域数 `[3,2,4]`，水平线 p=14511 位于全部九点原 physical intervals 内。
  这证明关联遗漏，不证明唯一边界；两个含不同 trace2826 峰的链不能直接 union。新关联已保留两条
  非包含合法解释，正式 CLI、report 87 与全量黄金确认 primary safe；材料带冲突仍保持 Review。
- S058 的 TOP 分成前段外边与后段内边，均不满足完整多数；转用 aperture 后 BOTTOM39 的两点方向
  外推导致过宽。现有合法 Cross `26+54` 被枚举序与两个保留槽排除，尚无该组合正式 footprint，
  不能称为安全替代。S012 初轮曾因新增完整 broad 与 sharp 非等价冲突丢失合格方案，新全量已恢复。
  S044 是角色变化与 Grid 冲突；S030/S042/S044 不是简单的 raw 保护扩大。

Broad 区域测量坐标修正的原始反例证据位于
`Test/gold_analysis/broad_region_geometry_20260915/reproduce.py` 与
`measurement_counterexamples.json`，绑定 `67dec91e` 和三个测量/拟合 owner 的 SHA：

- 三条 trace 为 0/1000/2000，真实阶跃边界 397.5/399.5/401.5 px，斜率 0.002，角度约 0.11459°。
  外侧 230、内侧均值 70/210/210、纹理 ±4，使用原双尺度窗口与 scale 10。区域 tone 均值返回
  代表 trace 1000 的 physical `[394.5,398.5]`，排除真实 399.5 达 1 px；镜像也复现。
  中间 trace 自身的 broad physical `[396.5,400.5]` 包含真实边界。反例不依赖超角度、源外窗口或降阈值。
- 九条 trace 的完整平行双侧片带也能通过原 coarse broad pair 编译。其 reference trace 4000 处真实
  TOP 为 205.5，但 compiled full position 为 `[200.5,204.5]`；因此问题进入了获准的支撑几何。
  同一输入按原 outward material 条件保留全部实际逐 trace 峰，原 pair 数值求解得到 TOP
  `[202.5,206.5]`、BOTTOM `[804.5,809.5]`，均包含真实位置。此项仅验证几何修正方向，未验证
  production 的多峰归属、最终输出或 Gate，不算新增黄金覆盖或错误 auto。
- 平坦中间 trace 没有边界或局部峰时，另外两条线仍可生成标记该中间 trace 的区域观测。这只证明
  contributing/多数计数不是代表点测量，不将不存在的中间真边界用于准确性比较。
- 旧类型把区域身份、全部 contributing traces 与代表点坐标混在一起；coarse 使用全部 contributing
  traces 证明连续性，tracking 固定遍历三个代表点，报告校验也将该点区间重建为物理线域。
  不能只替换拟合数组，或按位置区间相交把 sharp 与 broad 合并成同一物理边界。
- 引入提交 `a864fa4c` 与当前正例证明的是双尺度 broad 对宽缓边的检测：单条 trace 本身已有两个
  broad 峰，没有证明“全部单条无峰、区域均值恢复峰”。后者的现有测试属于另一条 cross-height
  弱梯度聚合路径，不能混为一谈，也不在本次修正范围内。
- S024/S058 已各运行一次正式 CLI 只读观察，均 exit 0、report 85 校验通过；source SHA、Runtime
  文件 SHA、原 accepted 几何与 Review 结论一致。证据为
  `/private/tmp/x5crop_broad_source_audit_s064_20260915/summary.json` 及同目录逐峰账本。
  S024 两侧各区域有 2/3/2 条唯一相交同材料峰；S058 在 trace 7695 的 TOP 有 237/276 两峰，
  trace 17685 的 BOTTOM 有 2490/2494/2506.5 三峰。这里的相交仅为关联线索，不能按最近峰强选。
  九条原采样线共检出 293/91 个 broad 峰；改用逐线测量必须约束实际关联工作，不能沿用三点工作账。

当前 H 机制评估与反例：

- 现有 `template_cross_model.cross_role_authorized_by_measurement` 只要求至少两个独立区域和外侧纹理
  较低的支持比例严格过半；它不是完整的画面接触证明。现有 Cross 已联合 H、方向、共享或互补域与
  纵向覆盖；`template_feasible_geometry.py` 保留输出联合状态。这些 owner 是整合基础，不新增平行求解器。
- `Test/gold_analysis/h_contact_assessment_20260921/assess_current.py` 通过正式 measurement、tracking、
  registration 复现原始像素反例：画面从 49.5 px 开始、含平坦边带，70 px 的内部纹理线反而取得角色
  权限，真实外边没有取得；上下翻转同样成立。真实边直接连接纹理的两个对照正常取得权限。
  这是构造图像的机制反例，不是实际样片 reference 或新算法验收。
- 同一反例脚本复现模型最近点选择：100 和 101.6 px 两条原始线分别与同一 anchor、H=[79,81]
  及方向/空间覆盖相容；同时出现时缺边精修只保留 100 px。后续联合机制不能只因预测距离较近就
  丢掉另一合法解释。`template_registration.py` 的最近峰精修和 `template_cross.py` 的单参考位置
  外侧比较须与新的完整位置/倾斜接触约束统一评估，不能在它们之后再叠同职责终选器。
- 正式 CLI 基线位于 `Test/debug_analysis/h_contact_baseline_20260918/{S016,S038,S064}`，revision 87
  报告及现场源 SHA 已重新核验；独立黄金比较的最佳保留方案短轴合格分别为 1/6、6/6、2/3，均 Review。
  S016 主/次方案有 BOTTOM 内切；S064 主/次方案外扩失败，条件方案仍有末格 BOTTOM 内切；S038 保持
  完整短轴对照。数据汇总在上述反例目录的 `assessment.json`，不是新版接触机制的效果或全量验收。

精确下一步：在同一 H 联合状态中定义可重放的接触事实与反证，保留其原 query/transition 身份，
模型只收缩候选可行域，不产生新像素支持。先覆盖平坦画面边带、内部强线、片夹、灰尘/局部突出、
倾斜边相交和不等距多解，再以真实样片与全部 nominal/challenge 对照上下边误差、内切、外扩和已接受
结果回归；达到 H 验收后才推进 W。H 可行性、整组方案质量、自动交付和发布资格分别报告。
暂缓与 H 无直接依赖的 broad 关联搜索优化；S069/S078/S082 超界及 S030/S044/S058/S110 等原型回退
仍未解决，不视为接受。此前冲突删除实验在密集查询退化且数值证明有漏洞，没有合入；其它原始观测
剪枝实验也没有形成生产修复。校准等机制稳定后再按原资格与全体 hull 重算，不为当前结果收窄区间。

新增测量或完整拟合不能挤掉已有合格
短轴备选。完整分组的数值补充只保留为有条件提案，保持原 canonical 两阶段与排序相关编号。
完整原子归属、实际跨度重投影、逐侧 observed 来源及完整 raw 均已接入。S013 末格已合格；其原
TOP trace 135 曾在两侧取共同 trace 时丢失，旧可行直线能在该处落到 214.342105 px，违反
原始 `[246.5,247.5]` 区间；完整约束现已保留。下一步核查剩余测量/解释缺口，不继续重复该修复。
S017 两侧原本同三条 raw，所有保留方案的质量、预算状态和 required polygon 与上一轮完全相同。
首格 TOP 黄金外扩 138.713866 px、超限 30.786728 px；控制 footprint 的状态附加保护为
`raw 0 + 域外方向 40.037151 + 长轴扩展方向 0.357287 + pixel 1 = 41.394438 px`。
另一个状态控制 aperture 风险：`slack 80.191980 + center 20.881215 + protection 46.728571
= 147.801765 px`。两种极值不可混加；center 区间只评估风险，不推动 footprint。
旧观察报告 `/private/tmp/x5crop-coarse-fit-S017-20260915/x5_crop_report.jsonl` 与
`/private/tmp/x5crop-coarse-fit-S017-20260915.fit-witness.json` 保留数值来源；TOP trace 10125 的 residual/localization 加 connection allowance
形成 observed 方向宽度。首格本地 support/aperture 关系仍缺直接证据，不能把未知中心或方向当作零。
S012 整组已黄金安全，但 F5 TOP/F6 BOTTOM 的 Runtime 风险仍为 1.367598/1.226402 mm，超过 1.2 mm。
当前正式报告为 `Test/debug_analysis/cross_side_observed_20260915/S012/x5_crop_report.jsonl`。
两项都有同状态合法 support 顶点：F5 TOP 的 114.706903421 px 由支撑半余量 59.778145539、
校准中心上端 20.881214501、1 px、raw departure 28.322258772 与方向差 4.725284608 组成；
F6 BOTTOM 的 102.864115506 px 由 59.955502996、16.704971601、1 px、零 raw 与方向差
25.203640909 组成。不能按黄金合格取消完整校准区间或删去已准入 raw。
原始测量探针为 `/private/tmp/x5crop-coarse-fit-S012-20260915.fit-witness.json`，运行正式 CLI，
photo_geometry、candidate_gate、decision、output 与未插桩报告完全一致。F5 控制 raw 位于 trace 15255，
physical `[219.5,247.5]`，localization `[242.5,243.5]`；应追踪物理宽区间来源，不把窄定位等同于窄支撑。
F6 下边自身 observed 上界 0.249387293° 来自 measured full；physical 上界已达 0.245711388°，
不能仅删除连接容差推断足以解决。继续核对完整原始测量与真实 material/aperture 身份。
S018/S064 继续处理 family/角色解释，明确局部反证的有效位置范围与 pair 闭合范围是否一致；
先保存原始 trace 与方向证据，不凭 lane reference 的
标量次序、外侧位置或黄金结果转移跨域权限。已有条件方案的可靠选择继续单独验证，不因某份黄金
安全或预算通过直接晋升自动权限。保持完整 canonical 原子及全部原测量，不按拟合或黄金结果挑子集。
S031、S100 剩余长轴问题不算本轮新增 Cross 能力。
S018 完整 TOP :14 / BOTTOM :67 pair 仍受合法局部外侧反证约束，当前保留单侧 H 推导；
条件 TOP 的完整 raw 直线可行域为空，不能删除 residual 保护以缩小输出。
S064 条件方案第 3 格 cross_high 内切由约 20.762868 增至 21.187766 px，仍不安全；
选中完整 family 的端点已纳入保护，缩减多余外扩没有修复错误 family 的几何解释。
外侧 BOTTOM :99 与 TOP :13 只有第 1 格共享支撑，尚无跨域完整 pair 权限；根因在 family/角色解释，
不能强选该局部边或把竞争 family 的 raw 并入已选输出冒充解决。
只读复核确认 `:13+:99` 的局部闭合发生在 F1，而 `:99` 相对 `:32` 的严格外侧分离出现在 F2/F3；
现有反证索引只保存 lane reference 4949 处的标量区间，尚未表达该跨域交叉关系。缺少局部闭合权限
可跨域传播的证据，不能直接增加 F3 veto；这不是 pair 枚举遗漏。
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
S012 首格旧超限已由逐侧 observed 来源修正消除；此前仅相容的 TOP :21 两条宽区间仍不收紧任何
共同直线状态，且有22种其它归属。不能以它延长coarse实测域并取消保护。
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
5. 作为独立小机制闭环完成全部黄金与相应工程验证；正式性能在发布验收时验证。
   当前仅登记，不调整物理模型或验收标准。
