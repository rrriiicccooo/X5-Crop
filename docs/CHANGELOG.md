# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前目标与风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只有一条 current-only runtime；历史 mode、schema、fallback 与平行 detector 只保存在 Git history。

V5 的定位明确为：以 v4.2.8 已在真实样片中证明有效的 Grid、separator、outer/cross、deskew、候选无关
复用与 TIFF 输出经验为能力基础，在 current-only 的 typed evidence、uncertainty、Gate、Debug 和黄金验收
下重建其物理权限。旧机制不能因名称或来源被直接整体删除；必须先把有效事实迁入 observation、anchor、
local correction、risk feature、veto、protection 或 selection 的唯一 owner，再删除旧式自证、任意评分、
重试 mutation 与兼容路径。

发布验收现在明确分为两层：检测能力要求当前 development nominal 全部安全 `approved_auto` 且全部角色
`unsafe_approved_auto = 0`，challenge 的安全 auto 或安全 review 都合格；工程能力另行要求正式性能、
TIFF/metadata、安装、三目标平台、打包与 Hook/CI。当前没有 sealed cohort，以及黄金未覆盖 `xpan`、
`120-645`、`135-dual`，都只作为未见/真实样片覆盖事实披露，不阻断首版发布，也不改变统一 Runtime 合同。

Proposal、eligibility 与产品决定现已成为三层独立事实。`TemplatePlacementProposal` /
`TemplateSourceProposal` 保存一份完整 pre-Gate proposal 或 typed unavailable；资格层只能决定它能否成为
selected candidate，`DecisionGate` 仍独占 `approved_auto | needs_review`，正式 TIFF 仍只来自前者。
Normal report 与 Debug 可显示 Review proposal，但它不会冒充 approved sampling geometry。Report revision
更新为 `x5crop_v5_template_report_50`，不保留旧 schema 或旧 projection helper。

Development gold 现在分别比较 proposal、candidate 和 approved output；`--gate report` 即使发现危险 auto
也完整写出样片、错误边界与 root failure 并成功结束，`--gate release` 才要求 nominal 全部安全 auto 且
全部角色危险 auto 为 0。完整 110-task diagnostic 无分析错误：85 个 proposal 已生成、25 个尚不可用；
proposal 为 25 safe / 60 unsafe / 25 unavailable，candidate 为 19 safe / 20 unsafe / 71 unavailable。
其中 6 个安全 proposal 与 40 个不安全 proposal 被 eligibility 层保留为 Review；Runtime stage 分布为
16 approved auto、23 eligible candidate Review、46 proposal-generated/eligibility-withheld、25 proposal
unavailable。当前仍是 16 个安全 auto、94 个 Review、危险 auto 0，release detection gate 未达标；
绑定提交 `ad04f95f` 的 development-detail mean 为 4.172 秒，只作开发归因。该分层没有新增 TIFF query、
detector、candidate、score、fallback 或正式输出。

完整验收同时发现并消除了 enclosing-support aperture-center calibration 的 provenance 漂移：canonical W
扩大后，S109 的 cross 从唯一解变为多解，合格 calibration source 因而从 21 变为 20，但旧登记只比较
cohort SHA 与数量。当前 v2 calibration 绑定精确 observation-set SHA，runtime authority 与 Report 同时携带
该 digest；release gold analysis 会阻断 cohort、eligibility、成员、观测值或登记数值任一漂移，development
report 仍只负责如实暴露；detector/comparator source manifest 不等于 HEAD 时也不能形成 release receipt。
`tools/verify accuracy` 现在薄调用同一 release analysis owner。Report revision
更新为 `x5crop_v5_template_report_51`，不保留 v1 calibration 或旧 schema 兼容路径；数值区间仍为
`[-0.009H, +0.007H]`，没有改变 crop geometry。

局部反证不再抹掉此前已经完整定位的 phase proposal。`PhaseRetainedProposalBasis` 明确区分 direct lattice
与 calibrated nominal Grid 的 pre-local proposal；后续 `fixed_template_mismatch` 等 typed failure、unresolved
状态和 winner 缺失全部保留，因此 retained phase 只能参与 pre-Gate proposal，不能取得 candidate 或 auto
权限。若 cross 仍不可用，只显示轴级事实，不伪造完整 source proposal。Normal report、development detail
与 Debug 均显示该 provenance，Report revision 更新为 `x5crop_v5_template_report_52`。

完整 110-task development diagnostic 无分析错误：proposal 从 85 增至 90，unavailable 从 25 降至 20；
proposal 为 26 safe / 64 unsafe / 20 unavailable，candidate 仍为 19 safe / 20 unsafe / 71 unavailable。
S070、S085、S096、S099、S101 新增完整 proposal，其中只有 S085 安全，其余四张暴露明确黄金越线或预算
错误；五张全部保持 candidate unavailable 与 Review。Runtime stage 仍为 16 approved auto、23 eligible
candidate Review，变化仅为 51 proposal-generated/eligibility-withheld 与 20 proposal unavailable；危险 auto
仍为 0，但这只是当前开发结果，不是发布通过。Development-detail mean 为 4.003 秒，只作开发归因；本机制
不新增 TIFF query、detector、candidate search、score 或正式输出。

单侧短轴不再把“source W / ratio 尚未闭合”等同于“H 不存在”。`SourceScanGeometry.height_state` 已经拥有由
format 设计 H、黄金校准 mixed guard 与 source 扫描尺度形成的有界 H；唯一 source-spanning 或完整
selected-domain direct anchor 可以用它推导 opposite。若 source W 与 format ratio 已闭合，仍优先使用更窄的
ratio H；ratio 形成反证时只保留 calibrated-H proposal 并阻断 eligibility。`CrossHeightInferenceBasis`、
inferred binding、Normal report 与 Debug 统一显示 `aperture_aspect_ratio | calibrated_format_height`，旧式
“ratio unavailable 就删除完整方案”的权限缺口不再存在。Report revision 更新为
`x5crop_v5_template_report_53`；该能力不新增 TIFF query、detector、score、候选空间或正式输出路径。

完整 110-task development report 无分析错误：proposal 从 90 增至 100，unavailable 从 20 降至 10；
proposal 为 26 safe / 74 unsafe / 10 unavailable，candidate 为 19 safe / 21 unsafe / 70 unavailable。
S001、S004、S011、S018、S019、S020、S037、S056、S066、S097 新增完整 proposal；S011、S020、S037、
S097 仍存在黄金向内越线，其余六张只超过逐侧 5% 外扩预算。S066 新增不安全 Review candidate；十张都保持
`needs_review`，没有获得正式输出。Runtime stage 为 16 approved auto、24 eligible candidate Review、
60 proposal-generated/eligibility-withheld、10 proposal unavailable；本次危险 auto 为 0，但 report gate 即使
出现危险 auto 也会完整列出而不会伪造通过。Release detection gate 仍未达标。绑定 detector manifest
`6c4414d8418613686c90736510befefc2130ee939a0e28112ff7ba108d22d4d1` 的 development-detail mean 为
4.035 秒，只作开发归因，不替代正式性能 Gate。

Cross competition 不再把“局部 direct top/bottom 尚不足以取得短轴 authority”等同于“短轴没有任何可比较
几何”。普通 Cross fit 为空时，唯一 `template_cross.py` owner 可从 role-authorized、方向有界的最外侧
registered direct TOP/BOTTOM 与当前校准 H 保留至多两个 fixed-H proposal，并以
`CrossRetainedProposalBasis.CALIBRATED_HEIGHT_FROM_OUTERMOST_REGISTERED_ROLE` 明确 provenance。原
`CrossFailureKind`、`UNRESOLVED`、runner 和工作量上限全部保留；固定 H 明确冲突、严格外侧反证、无角色
权限、无方向或 producer bound 仍不生成这条 proposal。它不增加 rank、candidate、score、TIFF query 或
正式输出权限，Normal report 与 Debug 同时显示 retained basis 和原失败。Report revision 更新为
`x5crop_v5_template_report_54`，不保留旧 schema 兼容路径。

完整 110-task development report 无分析错误：proposal 从 100 增至 105，unavailable 从 10 降至 5；
proposal 为 26 safe / 79 unsafe / 5 unavailable，candidate 保持 19 safe / 21 unsafe / 70 unavailable。
S033、S068、S069、S082、S108 新增完整 proposal，黄金均判定为不安全：S033/S068/S069 的主要短轴
问题表现为 `cross_high` 逐侧预算超限，S108 还有 `cross_low` 预算超限，S082 与 S108 另暴露长轴向内
越线；五张全部保持 candidate unavailable 与
`needs_review`。Runtime stage 为 16 approved auto、24 eligible candidate Review、65 proposal-generated /
eligibility-withheld、5 proposal unavailable；本次观测仍为 0 个危险 auto，但这是开发诊断事实，不是中间
改动必须归零的前置条件。Release detection gate 尚未达标。Development-detail mean 为 3.958 秒，只作开发
归因，不替代正式性能 Gate。

长轴 solver 现在也区分“全部完整 fit 都有 residual 反证”和“没有任何完整几何”。只要 bounded competition
已由 direct absolute anchor 形成全部 role 坐标，即使所有 fit 都超过 direct residual compatibility，
`template_phase.py` 仍保留一份诊断 proposal 和一个离散 runner，并分别记录
`direct_lattice_with_residual_counterevidence | calibrated_nominal_grid_with_residual_counterevidence`。
原 `fixed_template_mismatch`、`UNRESOLVED` 和 eligibility 阻断不变；该路径不新增 TIFF query、候选、score、
rank 或正式输出。Normal report 与 Debug 的统一路径为 `retained_phase_proposal`，Report revision 更新为
`x5crop_v5_template_report_55`，不保留旧 schema 或旧路径别名。

完整 110-task development report 无分析错误：proposal 从 105 增至 106，unavailable 从 5 降至 4；
proposal 为 26 safe / 80 unsafe / 4 unavailable，candidate 保持 19 safe / 21 unsafe / 70 unavailable。
S102 新增的完整 proposal 被黄金判为不安全，主要暴露短轴向内越线、后半段长轴错位和多处逐侧预算超限；
它仍是 candidate unavailable 与 `needs_review`。S106 已保留长轴 fit，但短轴仍无完整几何，因此 source
proposal 继续 unavailable。Runtime stage 为 16 approved auto、24 eligible candidate Review、66
proposal-generated / eligibility-withheld、4 proposal unavailable；本次观测仍为 0 个危险 auto，release
detection gate 尚未达标。Development-detail mean 为 3.938 秒，只作开发归因，不替代正式性能 Gate。

Cross proposal 进一步区分“角色权限不足”和“没有稳定物理线”。当没有 role-authorized TOP/BOTTOM，但某条
registered direct role hypothesis 覆盖至少三个独立高度区域并具有有界方向时，`template_cross.py` 可用
校准 H 保留 Review-only fixed-H geometry，并记录
`calibrated_height_from_registered_role_hypothesis`；原
`direct_role_authority_unavailable`、`UNRESOLVED`、runner、candidate 阻断和工作量上限均不改变。一至两个
区域、无方向、固定 H 冲突、严格外侧反证或 producer bound 仍不保留。Report revision 更新为
`x5crop_v5_template_report_56`，不新增 query、detector、rank、score 或正式输出路径。

黄金比较同时修正了 Orientation 坐标职责：人工线与 polygon 继续只保存原 TIFF 坐标，唯一 comparator
现在用冻结 `raw_to_canonical` affine 恰好转换一次后再与 canonical Runtime footprint 比较；截断 Frame 的
非四边形 polygon 按真实人工 boundary line 半平面逐侧验收，不再按顶点序号猜边。Development gold record
更新为 v15、summary 更新为 v17。完整 110-task report 无分析错误：proposal 为 26 safe / 81 unsafe / 3
unavailable，candidate 保持 19 safe / 21 unsafe / 70 unavailable；S106 从无完整 source geometry 变为
不安全 Review proposal，Frame 1–8 只暴露真实 `cross_low` 向内越线，Frame 9–12 无逐侧违例。Runtime
仍为 16 approved auto、24 eligible candidate Review、67 proposal-generated / eligibility-withheld、3
proposal unavailable；本次观测危险 auto 为 0，release detection gate 尚未达标。Development-detail mean
为 3.947 秒，只作开发归因，不替代正式性能 Gate。

显式 count 小于 lane 片夹容量时，role-free long material hull 不再被误当成“该照片组必定位于 hull 内”的
权限。`coarse_strip_support.py` 现在保留 direct hull 与 observation identity 作为诊断事实，同时以
`holder_slot_subset_conservative` 为完整 lane 登记 phase 搜索；它不居中、不选择 slot subset，也不新增
query、candidate、rank、score 或正式输出权限。Full-capacity sequence 仍使用原 pixel-localized interval，
没有 direct hull 时仍使用 `holder_conservative`。Normal report、development detail、Debug 与 validator
共享该 typed authority，Report revision 更新为 `x5crop_v5_template_report_57`。

完整 110-task development report 无分析错误：proposal 从 107 增至 109，变为 27 safe / 82 unsafe / 1
unavailable；S112 新增安全 Review proposal，S107 新增不安全 Review proposal，唯一生成缺口只剩 S002 的
`producer_bound_exceeded`。Candidate 保持 19 safe / 21 unsafe / 70 unavailable，Runtime 保持 16 safe
approved auto、24 eligible candidate Review；proposal-generated / eligibility-withheld 增至 69。当前观测
危险 auto 为 0，但这只是诊断事实而非开发提交的前置门槛；release detection gate 仍未达标。
Development-detail mean 为 3.938 秒，只作开发归因，不替代正式性能 Gate。

Cross 原始 run 的工作量现在按物理角色独立计账。TOP 与 BOTTOM 各自拥有编译的 512 条 producer 上限；
总数只用于 receipt，不再拿两侧合计误触单侧上限。任一侧真正超界仍产生 typed
`registration_bound_exceeded`，不截断、不按分数丢弃，也不增加 TIFF query。Canonical fitted observation
与 compatible-pair 上限保持独立。Report 与 Debug 显示 TOP/BOTTOM 实际计数和每角色上限，Report revision
更新为 `x5crop_v5_template_report_58`，不保留合并配额字段或旧 schema 兼容路径。

完整 110-task development report 无分析错误：proposal 从 109 增至 110，变为 27 safe / 83 unsafe；
S002 的 TOP 393、BOTTOM 185 分别未超过 512，因而不再假性终止，并暴露完整不安全 Review proposal。
其 Frame 4–6 `cross_high` 向内越过黄金线，Frame 1 的 `cross_high` 与 `sequence_end` 超过逐侧 5% 外扩预算；
真实下游根因为 `discrete_phase_ambiguous`、`non_equivalent_fits` 和 `phase_placement_ambiguous`。
Candidate 仍为 19 safe / 21 unsafe / 70 unavailable；Runtime 为 16 approved auto、24 eligible candidate
Review、70 proposal-generated / eligibility-withheld，正式输出行为未改变。当前观测危险 auto 为 0，但仍
只是开发事实；release detection gate 未达标。干净提交上的 development-detail mean 为 3.956 秒，只作
开发归因，不替代正式性能 Gate。

Cross 多解现在也保留一份物理顺序明确的 Review proposal。`template_cross.py` 在多个 fixed-H-compatible
registered direct pair 都没有最终 authority 时，先用物理最外侧 admissible TOP 锚定低侧，再按校准 H
偏差、方向相容性与稳定 observation identity 保留 proposal 和 runner；两侧仍使用 native coordinate。
更内侧的短局部线继续作为反证，不能仅凭偶然平行移动整条片带。原 `non_equivalent_fits`、`UNRESOLVED`、
candidate 阻断和 runner 都不改变；该路径只作有界候选选择，不新增 TIFF query、detector、rank、score 或
正式输出权限。`CrossRetainedProposalBasis.OUTERMOST_ADMISSIBLE_REGISTERED_ROLE_PAIR` 是唯一 provenance，
Report revision 更新为 `x5crop_v5_template_report_59`，不保留旧枚举或 schema 兼容路径。

14 个真实同机制 task 未出现 safe→unsafe proposal 回归；S002 不再从短轴向内越过黄金基线，剩余错误迁移
为 Frame 1 的 `cross_high` 与 `sequence_end` 外扩超出逐侧 5% 预算，S032 也减少一侧短轴向内错误。完整
110-task development gold 无分析错误，分布仍为 27 safe / 83 unsafe proposal、19 safe / 21 unsafe / 70
unavailable candidate，以及 16 safe auto / 94 Review；当前观测危险 auto 为 0，但这不是开发提交门槛，
release detection gate 仍未达标。Development-detail mean 为 3.961 秒，只作开发归因，不替代正式性能
Gate。

`SourceFrameWidthAuthority` 不再把“离散竞争仍有 runner”误写成“W 不知道”。唯一 canonical owner 现在用
`resolved_placement | retained_ambiguous_proposal` 明确 W 所属 scope；后者只收紧保留的 best proposal 并补其
已有缺失 opposite，原 `AMBIGUOUS`、typed failure 与 runner 不变，也不取得 candidate/auto 权限。额外
native pair/单边 local rebind 仍只允许 resolved placement；W 不能回写 rank、选择 runner 或覆盖 direct
native coordinate。Report revision 更新为 `x5crop_v5_template_report_60`，development gold record/summary
更新为 v16/v18；旧字段、旧 failure 和旧 schema 不保留兼容层。

完整 110-task development gold 无分析错误，全部 proposal 仍已生成。14 个 ambiguous proposal 建立
placement-bound W，其中 S029、S078 从 unsafe proposal 变为 safe，没有 safe→unsafe 回归；proposal 分布变为
29 safe / 81 unsafe，candidate 仍为 19 safe / 21 unsafe / 70 unavailable，决定仍为 16 safe auto / 94
Review。S002 的 Frame 1 END measurement expansion 从 243.794 px 降至 31.088 px，长轴预算根因闭合；只剩
Frame 6 `cross_high` 外扩 107.332 px 略超 106.483 px。S019 则把 W→H 真实反证迁移为
`aperture_aspect_ratio_conflict`。当前观测危险 auto 为 0，但仍只是开发事实；release detection gate 未达标。
Development-detail mean 为 3.954 秒，只作开发归因。本机制不新增 TIFF query、detector、candidate、score、
fallback 或样片规则。

Cross 的 retained Review proposal 不再把一条局部线的完整物理方向区间当作具体 proposal 的唯一画法。
`CrossLineProjectionBasis` 现在强制隔离两条路径：resolved/eligible Cross 继续用
`complete_physical_direction` 承担完整最坏包络；只有携带 `CrossRetainedProposalBasis` 的 unresolved best
才能用 `retained_review_statistical_fit` 形成一份可供黄金比较的具体几何。原完整物理区间、typed failure、
runner、candidate 与正式输出权限均不改变，placement identity、Normal report 与 Debug 显式记录 projection
basis。Report revision 更新为 `x5crop_v5_template_report_61`，不保留旧 schema 兼容路径。

完整 110-task development gold 无分析错误，全部 proposal 继续生成；只有 S002 从 unsafe proposal 变为
safe，Frame 6 `cross_high` 外扩由 107.332 px 降至 53.215 px，进入 106.483 px 黄金预算。Proposal 分布为
30 safe / 80 unsafe；candidate 仍为 19 safe / 21 unsafe / 70 unavailable，决定仍为 16 safe auto / 94
Review，runner 与 typed root failure 分布均未改变，危险 auto 为 0。S051 反例仍是 unsafe candidate 与
`needs_review`，证明 Review projection 没有泄漏到 eligibility。Development-detail mean 为 3.971 秒，只作
开发归因；本机制不新增 TIFF query、detector、candidate、rank、score、fallback 或样片规则。

Retained Cross 的 H 现在也由 `CrossHeightProjectionBasis` 显式分层：resolved/eligible fit 与 retained
direct pair 使用 `complete_physical_interval`；只有单侧角色结合校准 H 的 unresolved Review best 使用
`retained_review_canonical_height` 画具体默认 proposal。完整 H interval、typed failure、runner 和 eligibility
仍独立保留，canonical H 不取得物理权限，也不能进入正式输出。Report revision 更新为
`x5crop_v5_template_report_62`，旧 schema 不保留兼容路径。

完整 110-task development gold 无分析错误且全部生成 proposal。7 个 task 的 53 个 Cross side 采用新的
Review 画法：S069 从 unsafe proposal 变为 safe；S112 从 safe 变为 unsafe，明确暴露 canonical H 在
`cross_low` 向黄金内侧 15.047 px，而不再用完整 H 风险包络掩盖默认模型误差；S033、S068、S106、S107、
S108 仍为 unsafe proposal。总分布保持 30 safe / 80 unsafe，candidate、决定、runner 与 typed root 均不变：
19 safe / 21 unsafe / 70 unavailable candidate，16 safe auto / 94 Review，当前观测危险 auto 为 0。
Development-detail mean 为 3.954 秒，只作开发归因。本机制不新增 TIFF query、detector、candidate、rank、
score、fallback、Gate 权限或样片规则。

Separator connected component 现在由 `template_separator_support.py` 唯一解析。共享任一 physical edge 的
全部合格 band 始终属于同一个相关 evidence group；只有唯一、无拓扑分叉的 source-wide pair 能原子授予
`END → material → START`。多个 source-wide pair 产生 `alternative_pair_interpretations`，唯一 pair 的
endpoint 若又参与另一 pair 且角色相反则产生 `endpoint_role_conflict`；partial-height alternative 继续保留
为相关 provenance 和既有的一次权限传递，但不能覆盖 source-wide pair 或增加 rank。孤立 endpoint 的单条
方向 hint 不再错误推翻完整 material pair。Report revision 更新为 `x5crop_v5_template_report_63`，Debug
显示 component 的 supported/unavailable/contradicted 数量，不保留旧 grouping helper 或 schema 兼容路径。

S082 的第二张 START 因而从错误的 edge 115 回到真实 edge 111，消除了该长轴向内越过黄金线的根因；它仍因
独立的短轴 `physical_group_unavailable` 保持 Review。S043、S075 保持 Review，S081、S091 保持安全 auto。
完整 110-task development gold 无分析错误且全部生成 proposal：30 safe / 80 unsafe proposal、19 safe /
21 unsafe / 70 unavailable candidate、16 safe auto / 94 Review，当前观测危险 auto 为 0。S019、S026、
S051、S070 只迁移到更具体的下游 typed root，产品终态不变。Development-detail mean 为 4.074 秒，只作
开发归因，不替代正式性能 Gate；本机制不新增 TIFF query、detector、candidate、score 或样片规则。

已经 resolved 的 `GlobalLatticeAuthority` 不再只停留在诊断层。唯一
`template_feasible_geometry.py` owner 现在把同一 direct-role/absolute-phase 约束加入既有低维联合可行集合，
再投影未观察角色；因此不会把 phase、W、pitch 与 local delta 各自不相关的边际端点拼成一个实际不可能
同时发生的最坏状态。Direct native coordinate、canonical placement、runner、eligibility 与 Gate 均未被
改写。Phase competition 尚 unresolved 或 rank 0–2 时仍使用完整 `model_intervals` proposal，不会因把冲突
约束强行求交而丢失方案。`JointPlacementEnvelope`、Normal report 与 Debug 显式保存
`sequence_constraint_basis` 和实际 constraint identity；Report revision 更新为
`x5crop_v5_template_report_64`。

完整 110-task development gold report 无分析错误且全部生成 proposal：33 safe / 77 unsafe proposal、
21 safe / 19 unsafe / 70 unavailable candidate，18 auto / 92 Review。其中 17 个 auto 安全；S035 Frame 6
是唯一已知错误 auto，`cross_low` 相对人工基线外扩 120.752 px，超过 106.682 px 上限。直接 Cross TOP
role 位于约 y=339–343，而该 Frame 的黄金 aperture top 位于约 y=368–373；当前通用根因是 Cross TOP
角色绑定到了真实 aperture 外侧的错误材料边，Runtime 自身没有形成 counterevidence。相对上一检查点，
S028、S033 proposal 和 S038 candidate 变为安全，S038 安全 auto；S035 则从 unsafe Review 暴露为 unsafe
auto。该提交因此明确是 **DEVELOPMENT ONLY / NOT RELEASE READY**，不可用于正式发布或交付；
`--gate report` 只完成诊断，`--gate release` 仍失败。Development summary 更新为 v19，并以
`result_disposition=development_only_not_release_ready` 和终端警告防止把 report 的成功退出误称为验证
通过。Development-detail mean 为 3.968 秒，只作开发归因；本机制不新增 TIFF query、detector、candidate、
score、fallback 或样片规则。

### 产品行为

- 用户提供 format，并确认匹配片夹的默认 count 或显式 count；count 包含中间空白曝光格。Runtime 不猜
  format、照片数或 blank，也没有 full/partial mode。`135-dual` 只有 12=6+6 可自动处理。
- Detector 改为有界 fixed-template-first：从整条片带建立 coarse support，再在 format/count 编译出的
  outer、separator 与 top/bottom 邻域一次测量。Format 设计 W/H、source-level aperture 与 typed evidence
  决定 phase、pitch、cross 和 ordinal；每个唯一绑定的直接 separator 可以约束自己的 local advance，
  全部变化仍只作一次 O(count) 传播。像素强度、片夹中心或样片规则不能替代 authority。
- Separator material 在同一个 registered measurement owner 内完整支持 `dark | light` polarity。相邻
  反向 edge 必须在同一高度区域同时满足 oriented tone contrast 与 core texture 合同；局部两区域 support
  不能冒充 source-wide role authority，完整三区域反证产生 typed `separator_material_conflict`。超出 normal
  gap 上界的 material 仍保留为事实，但不能创造 phase、ordinal 或直接角色权限。
- 已登记 sequence baseline 现在同时产生两类三区域 aggregate：局部 weak gradient/tone/texture 可以
  `aggregate_union` 加强唯一 short direct edge；宽缓 material 使用 `0.25/0.50 mm` 双尺度 tone、texture、
  uniformity、polarity 与 background-side 一致性。宽缓单边只能匹配或保留为 standalone，不增加
  direct-role 权限；只有完整 END/material/START pair 才能进入 placement 并约束 local advance。
  `aggregate_edge_support.py` 统一拥有解析、去重与 pair 投影；跨尺度、跨高度、角色或多解冲突保持 typed
  unavailable/contradiction。任一 edge 已属于 supported canonical separator 时，宽缓 pair 不能用另一侧
  重新解释该 edge；同一物理 pair 也不重复计票。该能力不扩大 query、halo、
  TIFF 读取，不建立 enhanced detector、第二 geometry 或 score。
- Coarse short-axis observation 现在把 5 条 sharp trace 与 9 条 broad material trace 合并为一个
  registered union 并只读取一次。Sharp 或 broad 都可建立 role-free enclosing pair；broad 必须具有正确
  outward background、共同 polarity、三区域 source-spanning 支持、相容方向和 `H < span <= 1.1H`。
  两者等价时保留 sharp native coordinate，broad 只作相关 validation；不等价时产生 typed contradiction，
  不按分数选解。单侧、源边界不可观察、支持不足或 span 不相容都不授予权限；长轴 broad standalone edge
  仍只作 observation。Resolution basis/failure 进入 Development report、gold analysis 与 Debug。
- Selected placement 现在由 `AdjacencyContinuityObservation` 为每个 adjacency 建立唯一 typed ledger。
  唯一正序 separator band 始终保存 direct gap；gap 异常或需要约束未观察 suffix role 时形成 measured
  `SeparatorRelation`，保存两侧 native observation 与直接 signed-gap interval。共享 W/pitch 改变时只重算
  相关 `delta = signed_gap - (pitch - W)` 和 derived `normal|wide|narrow`，不能把真实 gap 拉回默认值。
  完整 corridor 但无反证只保留 unobserved nominal Grid，
  不能冒充直接 separator；material unavailable、band/角色冲突、跨零 gap、未登记反序 edge pair 与 coverage
  不完整分别保留独立状态。
  普通 adjacency 的歧义和拓扑反证通过专用 Gate reason 安全 review。该映射只复用已登记事实，不新增
  TIFF 读取、低梯度 detector 或 winner-specific query。
- `AdjacencyRelation` 现在显式区分 `SeparatorRelation`、`ContactRelation` 与 `OverlapRelation`。Candidate-independent
  `ContactEdgeObservation` 只接受具有独立坐标权限、未被正 separator material 拥有且没有另一条重叠
  authoritative identity 的物理边；phase solver 把同一 edge 原子绑定为前一 Frame END 与后一 Frame
  START，并以 `delta = W - pitch` 进入原有 O(count) prefix。走廊不完整、多个 physical identity 或多种
  ordinal 映射保持 typed review；反序边不能冒充 Contact。
  Candidate-independent `OverlapEdgePairObservation` 只登记空间相邻、角色相反、physical identity 独立且
  具有直接坐标权限的反序 END/START，不读取新像素或携带 ordinal。Phase solver 在有限合法 adjacency 中
  绑定同一 pair；完整 coverage、无 separator 竞争且严格负 signed gap 才形成 `OverlapRelation`，并以
  `delta = W - pitch + signed_gap` 进入同一 prefix。Contact/Overlap 相邻 Frame 不参加 source W 独立支撑。
- 已证明 Contact/Overlap 的输出只在前一 Frame END 与后一 Frame START 增加一份同状态 sequence base bleed 作为
  `topology_protection`，并继续消耗原有每侧 5% 总预算；其它边不变，预算或 containment 不成立时 review。
  Overlap 只允许 relation 对应的两个物理 Frame polygon 重叠；其它重叠仍为 `fixed_template_mismatch`。短轴
  evidence 在 overlap 中点分区，避免共享区域重复计票，输出 polygon 不被修改。
  Report/Debug 分开保存 relation identity、基础 bleed、topology protection、uncertainty 与 residual。
- Direct separator refit 只能让同一 adjacency 的 native endpoint 调整局部关系；原 phase anchor 保持原
  权限，新追加 endpoint 只能作为 `LOCAL_REFINEMENT`。重拟合前的全局 phase binding 与 Contact/Overlap
  必要角色冻结为 `phase_anchor_authority_ceiling`；新增
  separator endpoint 不能创造 phase authority、constraint rank 或无关 role binding。Projection 以
  `direct_separator_refit/direct_separator_gap` 保存依据，并核对 immutable relation evidence identity；越过
  ceiling 或改变 template/ordinal/evidence/role mapping 时 typed review。完整路径仍为 O(count)、不新增
  TIFF query，fit pass 上界为 6。
- 校准 Grid 现在正式作为唯一 placement 的 primary generative model。Format/count 提供黄金集校准且带
  完整区间的 W/H/pitch 与 normal adjacency；至少一个获得坐标权限的 absolute anchor 将它放入 TIFF。
  Direct rank 3 仍是更强的完全直接闭合路径，但不再是 Grid 的唯一使用权限。某张 Frame 即使 START/END
  都未直接观察，只要校准 prior、anchor、逐 adjacency 完整 coverage 和无 typed 反证全部成立，仍可由
  同一 Grid 生成；`unobserved_frame_ordinals` 只作 provenance，不再是硬失败。全部 W/pitch/scale/local
  关系以联合可行状态传播到 output，最终仍由 source containment、content veto 和每侧 5% 最坏包络决定
  auto/review。无 anchor、coverage 不完整、直接反证、校准包络冲突或预算超限分别保留自己的 typed
  failure；没有 fallback、第二 Grid、样片特例或零不确定性 nominal 值。
- Selected lattice 在 local relation 或 source-W 阶段追加 late binding 后，会由同一
  `PhaseCandidateAuthorityProjection` 再执行一次有界权限投影。无坐标权限的弱线只有在完整位置区间与
  对应 lattice role 的完整包络相交时才能降为 validation provenance；校准 Grid 与 direct-rank 路径分别以
  `calibrated_nominal_grid_conflict`、`direct_lattice_conflict` 保留不相交反证。Direct-rank selected fit
  先让独立 source W 尝试闭合 opposite，权限仍不足时才投影晚期弱线；仍有权限的
  `LOCAL_REFINEMENT` 保留 native binding，不能因不增加 global rank 而丢失。Report/Debug 保存 selected
  projection、投影 role、lattice basis、Grid solve 与 typed conflict；不新增 TIFF query、候选、detector
  或 fallback。
- `SourceFrameWidthAuthority` 成为 source W 的唯一消费 owner，并显式区分
  `independent_complete_frames | direct_lattice_closure | reconciled_direct_constraints`。前两组硬约束在同一
  selected placement 中同时可用时只发布区间交集，交集为空产生 `physical_width_conflict`，不得按通过结果
  挑选一组；第三种 basis 完整保留 Frame ordinal、rank-3 constraint 和 observation provenance，但不把
  同一 direct system 再登记为新 rank。比例层显式消费同一 typed authority，W→H 仍为 rank 0 相关推断。
  Report revision 更新为 `x5crop_v5_template_report_48`，不保留旧 schema 兼容路径。完整 110-task 黄金分析
  错误为 0，16 个安全 auto、94 个 Review、`unsafe_approved_auto = 0`；22 个 task 使用 reconciliation，
  `adjacency_topology_unresolved` 从 8 降到 6。Candidate 从 72 unavailable / 19 safe / 19 unsafe 迁移为
  70 / 20 / 20：S109 新增安全 Review candidate，S045 的不安全 candidate 仍被 5%/budget Gate 阻断。
  绑定检测提交 `03242641` 的完整黄金 receipt 中，development-detail mean 为 4.010 秒；同一提交的
  24-source 正式性能工具 mean 为 3.642 秒，通过 5 秒 Gate，3 秒目标仍为非阻断 challenge。该开发检查点
  不替代未来 release commit 的重新验证；本机制不新增 TIFF query、detector、candidate search、score、
  fallback 或样片规则。
- Direct-rank W 不再从 retained coordinate 中任取一个 deterministic 三行子集。`GlobalLatticeAuthority`
  只证明 `(phase,W,pitch)` 是否满秩并保存全部约束；唯一 canonical `SourceFrameWidthAuthority` 使用全部
  retained direct-role coordinate 做 direct-only 投影。恰好三条约束时保持精确解；过定系统把每条 native
  interval 与其实际 fit residual 通过同一线性 estimator 传播，既不要求真实 source 的 Frame width 零波动，
  也不让 calibrated prior、自选子集或完整 Frame basis 替直接系统消除反证。全部 constraint/observation
  provenance 进入 Report/Debug；物理区间冲突继续 typed Review。Report revision 更新为
  `x5crop_v5_template_report_49`，旧 basis helper 与旧 schema 同批删除。完整 110-task development gold
  无分析错误，16 个安全 auto、94 个安全 Review、`unsafe_approved_auto = 0`；candidate 为
  71 unavailable / 19 safe / 20 unsafe。S108 的旧 topology root 被解除并迁移到下游 aperture/budget；
  S109 先前依赖任意三行收窄 W 的安全 Review candidate 被撤回，完整 W 使 relation 5 的 signed-gap
  interval 跨零，因此准确保留 `adjacency_topology_unresolved`。Source W 仍为 51 supported /
  55 unavailable / 4 contradicted。相同检测源码的 clean-checkpoint 24-source 正式 performance mean 为
  3.536 秒，通过 5 秒 Gate；3 秒仍为非阻断目标。不新增 TIFF query、detector、candidate、score 或样片规则。
- Report revision 更新为 `x5crop_v5_template_report_44`，不保留旧 schema 兼容路径。Report/Debug 与
  development gold 分别显示 global lattice、source W、frame inference 的 state、basis 与 typed failure。
  当前 110 个 development task 的完整机制验收无分析错误：16 个安全 auto、94 个安全 review、
  `unsafe_approved_auto = 0`；14 个 challenge 均安全 review。50 个 task 闭合 source W，其中 39 个来自完整
  Frame、11 个来自 direct lattice；4 个物理 W 冲突继续 review。
- Direct-rank selected fit 的晚期 `LOCAL_REFINEMENT` 不再因投影 owner 只接受 calibrated Grid 而被笼统
  阻断。独立 source W 先获得闭合机会；仍无坐标权限时，原 candidate 在同一 template、ordinal、relation
  identity 和完整硬区间内重新投影。退出弱线继续作为 counterevidence，topology 必需 binding 不得退出，
  `direct_lattice_conflict` 单独表达与 direct-rank 包络不相交。Canonical W 闭合后，S076/S090 明确迁移为
  `physical_width_conflict`；S077 的 W 已由 `direct_lattice_closure` 支持，但被投影退出的 registered local
  line 形成 `direct_lattice_counterevidence`，不能删除反证后再用该 W 推断角色。Auto 仍为 16、candidate
  仍为 71 unavailable / 21 safe / 18 unsafe，危险自动批准保持 0。Selected late projection 为 20/26，
  selected Grid solve 为 16；不新增像素读取、detector、candidate、fallback 或 score。
- Enclosing support 的 shared slope 现在只由 `JointFrameState` 传播一次。逐 Frame residual 改为比较实测
  trace 与同一状态直线，超出实测域时只增加 observed direction 相对该状态 slope 的差值；不再把已经进入
  footprint 的绝对斜率重复计入 local protection。最小斜线反例、100 项相关合同测试与完整 110-task 黄金
  验证通过；auto/candidate 分布不变，危险自动批准仍为 0，说明真实超预算继续 Review，而重复预算已移除。
- Separator pair 的权限改为有序 `END → material → START`，不再把同一两条 edge 的正反序解释合并。
  Selected-only refinement 若较晚补出精确反序绑定，会以 typed `direct_role_contradiction` 淘汰当前
  candidate；只允许同一 bounded competition 中已完成权限评估的 runner 晋升，精确非法 role/edge 不得
  再绑定。仍获授权的 local refinement 保持离散 identity。该机制最多评估两个 selected fit，不新增查询、
  detector、候选或 score。
- `ENCLOSING_SUPPORT_PAIR` 现在显式计算未知 aperture 中心的最坏风险。Support 只证明 fixed `H` 位于两条
  边之间，不能证明居中；每个联合可行状态分别把 requested footprint 与该状态内最不利的 top/bottom
  aperture 位置比较，结果由 `EnclosingSupportApertureRisk` 进入原有逐侧 5% 预算。它不修改输出 polygon，
  也不混合互斥状态。该检查阻止了 S012 的危险自动批准，并让 S059 在中心权限不足时安全 Review；S091、
  S095 仍安全 auto。
- Report revision 更新为 `x5crop_v5_template_report_45`。完整 development gold 为 110/110、分析错误 0、
  `unsafe_approved_auto = 0`；15 个安全 auto、95 个安全 Review。Candidate 为 70 unavailable / 21 safe /
  19 unsafe；S026 的反序 candidate 被精确淘汰后，真实 root 迁移为缺少显式 OverlapRelation 的
  `fixed_template_mismatch`。Development diagnostic mean 为 3.974 秒，不冒充正式 performance receipt。
- Source W 闭合与其下游 topology 权限现在明确分层。只有 correlated-W inference 已实际取得的角色才进入
  `SourceFrameWidthTopologyAssessment`；它以完整 W interval 和相邻 native boundary interval 检查普通
  signed gap，不挑选有利 W，也不把未知 overlap 伪装成 `OverlapRelation`。跨零与全负 interval 分别保存
  `normal_adjacency_unresolved | normal_adjacency_contradicted`，统一映射为
  `adjacency_topology_unresolved`；未获权限的 W inference 显示为 `NOT USED`，不覆盖
  `complete_frame_unobserved` 或 counterevidence。Report revision 更新为
  `x5crop_v5_template_report_46`，Debug/Development report 显式保存逐 relation facts。完整 110-task 黄金
  receipt 无分析错误且 `unsafe_approved_auto = 0`；auto 仍为 15，candidate 为 72 unavailable / 19 safe /
  19 unsafe。S007/S026/S040/S110 从迟到的 `fixed_template_mismatch` 前移为准确的 topology root；S045/S109
  先前的 candidate 对黄金虽安全，但完整 W 状态未闭合，因此保守 Review。Development diagnostic mean 为
  3.894 秒；不新增 TIFF query、detector、candidate、score 或样片规则。
- Selected unique enclosing support 现在由唯一 `EnclosingSupportApertureAuthority` 收窄剩余 aperture 中心
  偏移。Calibration 使用 19 个黄金 top/bottom 均直接可见的 source，以同源中位数、source hull 和
  `0.001H` 向外量化得到 `[-0.009H, +0.007H]`；它是 rank 0 相关推断，不选择 geometry、不把 support
  冒充 direct aperture，也不修改 output polygon。Calibration 不可用时保留完整物理中心包络；与直接
  support 无交集时产生 typed `enclosing_support_aperture_center_conflict`。Report revision 更新为
  `x5crop_v5_template_report_47`。完整 110-task 黄金无分析错误且 `unsafe_approved_auto = 0`；S059 从安全
  Review 转为安全 auto，合计 16 auto / 94 Review，nominal 为 16 / 80，14 个 challenge 仍全部安全 Review。
  Candidate 分布仍为 72 unavailable / 19 safe / 19 unsafe；S030/S058 的真实预算缺口和 S012 的危险
  candidate 均未被掩盖。Development diagnostic mean 为 3.899 秒，不冒充正式 performance receipt；不新增
  TIFF query、detector、candidate、score 或样片规则。
- 对 96 个 nominal 的同源机制对照显示：v4.2.8 有 80 个 auto，但其中 70 个是黄金危险自动裁切；只有
  11 个 v4 geometry 安全。v4 安全而 V5 Review 的 9 个 task 是下一步能力迁移样本，当前分别落在
  aspect/cross、fixed-template/topology、content veto、Grid conflict、phase ambiguity 与 output budget
  等 typed root；不能据此恢复旧终判。当前 V5 有 20 个安全 nominal candidate，其中没有“双方 geometry 都安全但
  仅因 Grid direct-rank 权限而 Review”的遗留项，说明本阶段已把默认生成权限与后续安全阻断分开。
- 直接观察到的 start/end 在最终 placement 中保留 native coordinate 与完整 interval；Grid 只补齐缺失
  角色。同一连续 placement 的互补 endpoint evidence 合并为联合可行状态，不伪造 runner。唯一 placement
  中的 source W 可由至少两张完整直接 Frame，或保留的独立 rank-3 direct-role 系统闭合；当每个缺失 Frame
  仍有一侧直接边缘且没有同系统 counterevidence 时，同一相关 W 可补多条 opposite。若某个双侧未绑定
  Frame 的完整物理 W 走廊内已经存在多组 registered native edge，
  独立 source W 还可在固定 placement 上追加一次有界 lookup；只有它唯一留下一个各自具有直接坐标权限的
  pair 时才绑定。双侧未绑定 Frame 若只有一侧存在唯一 intrinsic edge、另一侧完整 corridor 无候选，也可
  保留该 native coordinate 并由同一相关 W 推导 opposite；该路径可作用于 calibrated Grid selected fit，
  但 Grid/format W 自身不能授权。没有合格 pair/单侧 edge、多组解释或任一 opposite 候选继续 typed
  review。缺失 separator 只有在 direct rank-3，或校准 Grid 已有 absolute anchor 时，才能继续检查对应
  adjacency 的完整不确定性走廊；走廊被已执行窗口逐 trace 覆盖且没有局部反证，才按
  `local_delta = 0` 补齐。不再用 edge 数、连续缺失数或全局 query-complete 布尔值代替证明。候选无关
  sequence 窗口按左右 holder 端分别投影完整且相关的 `W/pitch` 状态，覆盖
  传播走廊但不重复相加互斥极值；理论 core 合并后按中点把 coarse support 的每个整数像素中心恰好分给
  一个窗口，measurement halo 可重叠而 transition ownership 无重叠、无缺口。覆盖以真实可测的离散坐标
  判断，不再把相邻像素中心之间的亚像素距离误报为缺口；扩大 ownership 不增加 TIFF 读取或 query。
  direct rank-3 推断路径还要求首尾输出 Frame 各至少绑定一条直接长轴角色；校准 Grid 路径则由 absolute
  anchor 和完整联合包络承担外侧位置，不从片夹中心创造 phase。任一已选直接
  START/END 只有获得 source-wide edge、跨高度联合或同一 separator pair 的直接坐标权限后，才能进入
  最终 placement；两条局部 edge 不能仅因间距与 catalog/source W 相容就互相授权。独立 source W 只推导
  真正缺失的 opposite，不覆盖已经授权的 native coordinate。无权 `LOCAL_REFINEMENT` 只有在同 Frame
  opposite 已授权、W 不依赖该线、且 W 走廊中只有该 observation 相容时，才让位于完整相关 W；弱线仅
  保留为 validation provenance，不能收窄 W、增加 rank 或改变 phase。其它局部孤立
  edge 保留为观察并产生 typed review，不能反向参与 lattice 自证。两高度 normal separator 只有在一侧已具完整直接权限时，才可向
  同一 adjacency 的另一侧传递一次 `partial_height_separator_pair` 权限；传递不能级联。最终新增唯一
  `DirectRoleApertureDomainAuthority`：两侧 direct aperture，或两侧 enclosing support 经校准 fixed H
  闭合的 aperture，都必须在完整位置/方向不确定性下包含该 edge 的全部登记 trace span，才能保留 native
  coordinate。单侧域产生 `direct_role_aperture_domain_unavailable`；域坍缩或 trace 越域产生
  `direct_role_aperture_domain_conflict`。该 owner 不读取像素、不增加候选或 rank，后续 content veto 与
  5% 预算仍优先。
- 该 aperture-domain 迁移解除 S008、S010、S028、S030、S045、S049、S091 的旧笼统权限阻断。S091 在
  全部后续检查通过后成为新增安全 auto；S030/S045 只有安全候选但仍因预算 Review；S008/S028 的候选
  不安全并被预算阻断；S010/S049 被 content veto 阻断。候选从 76 unavailable / 18 safe / 16 unsafe
  迁移为 71 / 21 / 18，没有恢复发布版终判或放宽 Gate。
- Source W 不再由 provisional/base phase 预先校准后重编译 template，也不再形成第二次 pitch/phase 搜索。
  离散与 local competition 先在没有 source W evidence 的同一候选空间中结束；只有唯一 selected candidate、
  pre-W joint rank 至少为 2、必要 adjacency coverage 完整且没有直接反证时，至少两张独立完整 Frame 或
  保留的 rank-3 direct-role basis 才建立 typed `SourceFrameWidthAuthority`。它只收紧 selected fit 的连续 W，并在最终阶段
  重新评估 rank、direct-role/outer authority 与相关 opposite inference；不能删除离散 runner、改变
  ordinal/winner、重编译 template 或回写先前候选选择。普通 local refinement 使用完整 format W，不能让
  fitted Grid W 过滤自己的反证；source W 的 authority identity 固定绑定 phase-anchor 与 W-support role，
  direct-lattice basis 的三份 observation 不能再次登记成 Frame-width rank。未支持、物理矛盾与自证风险均
  进入 report/Debug，不建立旧 API、fallback 或并行 runtime。
- Rank 3 直接坐标现在在 phase、W、pitch 与 `pitch-W` 的联合硬区间内执行有界最小二乘。无约束解轻微
  越界时不再把 W/pitch 整体退回 catalog 中心却保留原 phase；报告以
  `direct_least_squares | bounded_direct_least_squares | template_interval_center` 记录连续参数依据。
  该求解不扩张物理区间、不覆盖 direct native coordinate，也不选择离散 runner；受约束后暴露出的另一
  合法解释仍安全进入 review。
- 每个 bounded phase candidate 现在会在离散竞争前对称执行 direct-role authority projection。
  `contradicted` 直接终止；`unavailable` binding 只有在删除后每张 Frame 仍保留一侧直接坐标、相关
  evidence-group 去重后的 `(phase,W,pitch)` rank 仍为 3、且同一 template/ordinal/local topology 可以
  有界重拟合时才投影出去。全部 eligible candidate 重新 canonicalize 并竞争，真实双解仍保持
  `discrete_phase_ambiguous`；弱线只保留为 provenance，不能拥有 phase、收窄 W 或隐藏 runner。
  完全未观察 Frame 或 direct rank 0–2 会离开纯 direct projection，并只在第 7.2 节的校准 Grid 合同完整
  成立时继续；material contradiction 与 refit/identity failure 仍是 typed terminal outcome。该机制复用
  registered evidence，不增加 TIFF 读取或第二 detector。
- `135`、`half`、`120-66`、`120-67` 使用同一 source-level 方法校准 nominal pitch interval，并与 W、
  source scale 保持相关；`xpan`、`120-645`、`135-dual` 没有合格真实 calibration 时明确 unavailable，
  不跨 format 外推。Calibration identity、anchor、coverage、未观察 Frame、work receipt 和 root failure
  全部进入 report/Debug。
- Format W/H compatibility 由一个 current-only 混合物理合同统一计算：
  `guard_W=max(0.95 mm, 2.4%W)`、`guard_H=max(0.70 mm, 1.8%H)`。参数来自 105 个合格黄金 source、
  494 个完整且全部直接可见 Frame 的 source-level 中位尺寸、分轴长 q95 与向外量化；不再保存 `half`
  或其它 format 的 tolerance 特例。Direct complete Frames 以完整 uncertainty 收紧 source W，唯一直接
  aperture pair 收紧 source H，native boundary 始终优先。
- `ApertureAspectRatioAuthority` 已启用：各 format 的 source-level raw W/H 包络由两轴混合 guard 传播成
  format-specific guarded ratio，再从 canonical `SourceFrameWidthAuthority` 的任一合法 basis 推导一份
  rank 0 相关 H；比例层不按 observation 数量另建 W 权限。
  Calibration/共同 scale/W authority 不足、physical prior 冲突、direct H 冲突与 5% 预算耗尽均有 typed
  failure；direct H 存在时优先承担 cross。没有合格黄金数据的 format 保守 review，不作精确名义比例换算。
- Separator 仍以 catalog gap 为搜索中心，实际宽度由直接 material edges 与 local advance 拥有；holder
  extent 保留独立的外部 ±3.5% 设计先验。二者都没有为了复用 aperture guard 而改变物理含义。
- Cross 注册超过编译上界时不再抛出 runtime error；完整实际计数进入 typed `producer_bound_exceeded`
  receipt，并由 Gate 安全 review，不截断观察或提高魔法上限。
- Output protection 现在分别保存 mandatory、完整 requested 与实际 required source footprint。真实 TIFF
  外缘只限定不存在的源像素，并按 `source_boundary_optional_bleed | source_boundary_joint_protection`
  显式记录；内部 dual-lane 边界仍按 `lane_boundary_*` 阻断，不能借裁小获得批准。5% 预算继续使用未裁小
  requested footprint，Debug 以虚线保留完整请求，不静默丢失保护事实。
- Enclosing support 的 direct-use 预算不再把 top/bottom 的位置不确定性重复计入联合 alignment padding，
  也不再相加不同可行状态的边缘极值。逐侧完整 expansion、`1.1H` support span 与同一状态额外直线
  alignment padding 仍分别受原有上限约束；报告和 Debug 显式保存该同一状态最大值，未放宽 5% 产品预算。
- Cross registration 现在是同角色边界 family identity 的唯一 owner。只有一次 robust refit 精确保留完整
  transition union 时，多个局部 fragment 才合并为一个 canonical observation；refit 丢失任一 transition
  时全部成员原样保留，并报告 typed `complete_transition_union_refit_rejected`。Selection 中旧的
  broader/local dominance 已删除；不再按 trace containment、邻近、support 或 residual 消除 runner。
- 当前选择仍只使用 typed hard facts；没有启用 score。架构允许未来在硬合法候选之间加入经独立数据
  校准、带高阈值与 abstention 的概率选择，但未经校准的 score 不得拥有最终决定权，runner
  必须继续报告。
- Cross 不再用片夹短轴中心选择最终边界；它只帮助编译有界测量 corridor。直接 top/bottom pair 现在显式
  区分 `shared_traces` 与 `complementary_domains`：后者只在两侧都是 role-authorized direct evidence、
  各自有至少两个独立区域、两侧 trace 并集完整覆盖全部 selected Frame domain，且 fixed H 与方向相容时
  成立；共享 trace 数仍如实为 0。缺 domain、template-local/inferred opposite、方向冲突或多个完整 pair
  均保留 typed failure 与 review。若完整 pair 的同一 opposite 还能与严格更外侧的直接局部 role 闭合，
  内侧 pair 产生 typed `outward_role_counterevidence`；更外侧 pair 若也拥有完整 authority，则两者继续作为
  非等价 placement review。Source-spanning 单侧也不再把未覆盖全部 selected domain 的局部 opposite 外推
  为整条片带边界。Cross winner basis、pair support mode、family resolution、source 长轴投影
  与 enclosing-support 的逐侧/联合 padding 预算进入 typed report 和 Debug。已经由 fixed H 与 `1.1H`
  合同预闭合的唯一 enclosing-support pair 直接拥有两侧输出权限，不再错误依赖或消费只用于缺失
  aperture side 的 W/H 比例推导。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。Contact 与 overlap 始终属于
  challenge，但 challenge 不预设终态：标准 detector/Gate 可产生安全自动批准，证据不足时安全 review
  同样合格。Contact 与 Overlap 均进入同一 adjacency/placement；受影响边界的 topology protection 消耗
  既有 5% 总预算，不建立第二套 detector 或独立特殊 bleed 预算。
- Placement 保持 source-axis；局部直线 slope 只扩大安全包络。Deskew 是批准后的可选整理，不参与
  placement、Gate 或黄金准确性；证据不足或超限时保持原始倾斜。
- 安全层只处理唯一 selected placement 的联合可行状态。Aperture 每侧共用 5% 外扩预算；直接 enclosing
  support 使用总高度不超过 `1.1H` 的独立合同。真实 TIFF 外缘按显式 saturation 限定实际可用像素；
  内部 lane authority 越界仍 review，不静默裁小。
- 二维 content 只对最终 post-residual、post-bleed polygon 作 negative veto；它不能移动边界、选择
  runner 或创造 phase。

### 输出与报告

- Finalization 对 source 与安全 polygon 使用同一 affine transform，再取精确半开 AABB；不在旋转后继续
  裁固定 W×H。AABB 的 no-data 角落不是检测失败。
- Debug Analysis 只可视化同次检测事实：理论模板、观察、winner/runner、最终 footprint、预算和首个
  阻断原因；报告同时保存全局未知量 constraint rank、逐 adjacency query/trace/coordinate coverage 与
  直接角色/外侧 Frame observation authority，以及 dark/light material、逐区域状态和冲突。Debug 不重新
  求解，也不把 review candidate 伪装为正式输出。当前 schema 显式区分直接角色的 coordinate
  `observation_id` 与相关
  `evidence_group_id`，同时报告 phase candidate 的输入权限、projection outcome、保留 rank、投影 binding、
  calibrated nominal prior/evidence/selected authority、phase anchor、推断 adjacency、未观察 Frame、
  nominal solve/local-prefix 工作量、连续 lattice 参数依据、三层 source footprint、typed
  saturation、同一状态 cross
  alignment padding、selected-only source W authority、source W/H、相关
  Frame-width inference 及 validation-only role/observation provenance、aspect calibration、raw/guarded
  ratio、两轴 guard、推导 H、逐 adjacency continuity ledger、Contact edge/relation 与 topology
  protection、Cross typed root
  failure、pair support mode、family resolution 与预算；不保留旧 schema 兼容路径。
- 正式 TIFF 保真 16-bit RGB、ICC、resolution、支持的 metadata 与无损压缩，并写
  `Orientation=1`。完整 source 先写 staging，再原子发布到尚不存在的目录。
- Report、Gate 与 final geometry 各有唯一 owner；`CandidateGate` 只记录事实，`DecisionGate` 创建终态。

### 黄金校准

- 本地标注器使用一个 source-SHA-bound 校准池；不区分 v1/v2。同源多 count 共用一套物理边界，各自
  保留 task mapping，不建立重复页签或重复确认。
- Source record 以两条共享边、一个 `boundary_pool`、typed `slots` 和派生 `adjacencies` 表达几何。
  `blank_exposure` 保留 count/ordinal 但没有人工边界；`source_truncated` 保存物理外推线与 TIFF 内交集。
- 红线导入、机器 proposal、有界预览与原 TIFF 窄带精修都不授予黄金权限。逐线
  `review_basis`、Frame 状态、原生像素审核与明确确认完成后，source 才成为不可变
  `user_confirmed`。
- 黄金验收统一为最内侧可接受无 bleed 裁切：candidate 与正式 footprint 不得向确认 polygon 内侧
  越界；有预算权限的每侧最多向外 5%。`visible_content_limit` 只阻断向内越界，
  `human_width_estimate` 两向均不阻断，其它边仍独立生效。
- 人工红线尽量贴近该 source 的真实有效成像边界，基本可作为 source aperture 的尺寸观测。黄金分析
  按 source SHA 分开统计同源与跨 source 的 W/H、separator 和 pitch；这些事实可校准物理分布与
  source-level authority，但不能被压成适用于所有相机的单一固定常量。偏离 catalog 时先检查相机个体
  差异、扫描比例和 uncertainty，不自动归咎于标注。
- Nominal/challenge 在 detector 运行前由人工证据和固定模板合同逐 task 派生，并随确认基线冻结；
  accuracy 会重新推导核对，不能手填改类。Nominal 以安全自动批准为能力目标；challenge 的安全 auto 与
  安全 review 都有效，前者单独记录为能力发现。
- 两侧各空余至少一个固定 W、又缺少双端直接 outer 的内部 partial sequence 属于 challenge；该角色只从
  确认前几何推导，不由当前 detector 的结果或 post-selection holder fill 决定。
- Accuracy 只接受当前确认 task。没有完整的当前 development cohort 时明确报告
  `calibration is incomplete`，不回退历史基线。空 slot 不参与几何比较，但 runtime 对应输出与 ordinal
  必须保留。
- 完整确认集合通过唯一生成器独立核对 source、确认快照、审阅 artifact、task authority、角色和 geometry
  digest 后，才写入 tracked development cohort。Development 黄金分析把基础 nominal、较难 nominal 与
  challenge 分开，并逐边区分已观察且绑定、已观察未绑定、模板补全和竞争状态；这些诊断不进入 runtime
  或黄金权限。
- 当前已查看黄金明确归入 `development_gold`；未来 sealed acceptance 必须在查看 detector 结果前按
  source SHA 分区，同源 count 同分区，解封调试后永久退役到 development。人工 reference 仍只有一套。
- 验证分别报告危险自动批准、Review candidate 几何、nominal 自动覆盖和 challenge 能力；只有正式
  `approved_auto` 越过黄金安全合同才是用户层危险输出。
- 同源合法 count 变体按共享物理 Frame 建立 source-level diagnostic；额外空白或残缺 slot 不得把共享
  内容重定相到危险位置，但不同 count 可以合法产生不同 auto/review 终态。

### 工程与验证

- `tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与 sampling，
  Pillow 只在 Debug Analysis 延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。
- Phase residual compatibility 在物理阈值处保持包含语义，并只吸收 `1e-9 px` 的浮点舍入误差；不同
  NumPy/LAPACK 构建不得因此改变 `resolved/ambiguous`。对应阈值与独立支持回归随 full/pre-push
  验证执行。
- Full/pre-push 在工程测试前先以只读方式核对当前 Python 环境与 CI 共用的依赖合同；
  版本或模块能力漂移必须在推送前失败，不得留到 GitHub 矩阵暴露。
- Sequence coordinate identity 由 `observation_id` 唯一拥有；`evidence_group_id` 只负责相关证据去重。
  Separator 左右侧即使共享 material group 也不得被合并成同一坐标或用于隐藏离散 runner；旧的
  `independent_support_id` 字段已删除，不保留兼容别名。
- Registered gray、affine crop buffer 与 source-local cache 按阶段释放；这些优化不得改变 observation、
  placement、Gate、footprint 或输出像素。
- `tools/verify` 是 Hook、CI 与本地验证的唯一入口。Diagnostic 只证明工程合同；gold accuracy、性能与
  platform receipt 分层记录，不互相冒充。
- 正式性能 Gate 为 24-source 完整用户路径 mean 不超过 5 秒；3 秒只是不阻断的 challenge。
- 当前 partial-height aperture-domain 检查点的完整 development gold 为 110/110、分析错误 0、
  `unsafe_approved_auto = 0`；16 个 nominal 安全 auto、80 个 nominal 安全 Review，14 个 challenge 全部
  安全 Review。24-source 正式性能 mean 约 4 秒，5 秒 Gate 通过，3 秒非阻断目标尚未达到。当前 Review
  表达真实的 phase/cross、Grid/W、topology、content 与预算缺口，不以调窄 guard、隐藏 saturation、恢复
  精确 W→H 或改变样片角色掩盖。
- Apple Silicon macOS、Intel macOS 与 Windows x64 必须在同一最终 commit 取得实机 receipt。Accuracy、
  性能与平台证据未全部绑定该 commit 前，不创建 RC、tag、Release 或公开 ZIP。
- 发布包由唯一 manifest 构建，不包含 modular source、tests、tools、内部文档或开发输出。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但没有
完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明“先看整条片带，再在理论位置附近找 outer 和 separator”可以快速覆盖规则片条。V5 继承并
重建理论 pitch/规则间距、material band、native gap edge、outer/cross、有限局部搜索、缺边投影、deskew、
候选无关复用与 TIFF readback。被删除的是由临时 content 区域驱动且未校准的 equal split、Grid 自证、
未经校准且直接决定终态的 confidence/best-score、selection 后 mutation、无条件固定像素 bleed 和
separator-center crop；它们曾承载的有效物理事实必须先迁入 current canonical owner。

## 回滚

恢复历史版本必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本
拼接组件。
