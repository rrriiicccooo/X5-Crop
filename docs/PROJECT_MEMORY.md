# 项目记忆

本地 main 已整合原生 coarse/Cross、共同输出及完整细化记录，仍未达到发布标准。

更新：2026-10-02。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前验收快照

当前生产提交为 `9600156b5cd871290b460232c3c84953af67b112`，本地 main，未推送。
本轮修复 phase 同几何桶的冲突身份误删、仅补全首选造成的假唯一，以及晚到缺绑定桥接绕过竞争
检查的问题。冲突 seed 用同生成器两遍重放恢复；全部 eligible 候选采用保守补全支持上界，按必要
绑定身份、phase 和 role 区间分量归约。同 observation ID 先取 hull，保留其桥接 None 的可能性。
只有绑定身份、phase-anchor 用途、coverage 与五类合并区间已被首选包含的原候选才跳过检查。
不增加拟合、坐标组合、像素查询或原工作预算；新增索引存储计入 receipt。

同提交 `tools/verify full` 运行1112项测试（1110通过、2项Windows专属跳过），依赖、编译、cohort、shell
与版本检查通过。反例覆盖同坐标不同身份、第三组补全、720种顺序、同ID区间桥接，以及晚到桥接后
互斥身份与未吸收保护范围。它们证明 owner 缺口，不等于完整TIFF流程曾触发 unsafe auto。
工程日志及独立反例归档于 `Test/gold_analysis/local_phase_9600156b/`。

本轮相位修复后的完整用户路径在cdb99027上测得5.178709793秒，5秒Gate失败；固定四源ABBA同环境对照为
旧546代码6.07957秒、cdb代码6.07191秒，未支持phase变化造成主要变慢；对照不是24源验收。
完整CLI剖析定位逐线跟踪全列表扫描。当前提交用保守二分窗预筛已排序候选，半径与端点均向外
nextafter后，仍由原距离谓词最终判断，不建新数组或扩大连接门槛。59次真实输入重放输出和相同
身份作用域中的ID精确一致；独立236592点浮点审计零漏点，包含只扩张结果端点会失败的消去反例。
旧失败回执和ABBA证据保留在 `local_phase_cdb99027/`，不覆盖、不用局部提速冒充正式Gate。

完整110项正式gold回归为0分析异常、21 safe auto、0 unsafe auto、75 nominal Review、
14 challenge Review。源码身份与校准检查通过，发布准确性Gate失败。
结果见 `phase_9600156b_20261002_full/gold_analysis_summary.json`，
与546f99f7的逐字段及几何差异见 `local_phase_9600156b/gold_comparison.json`。
本轮跟踪优化与cdb99027的完整110条记录除耗时外逐字段一致，凭据为
`local_phase_9600156b/tracking_full_gold_equivalence.json`，没有增加或减少自动批准。
当前仍未达到全部96项nominal安全自动处理的标准；不得把安全Review写为nominal能力已完成。
中心校准按原资格与固定公式刷新为v16，S030失去唯一phase资格，来源为S043/S053/S064/S074四源；
数值区间仍为 `[-0.007H,+0.010H]`，不按最终批准挑样，不证明sealed泛化。

同提交24源完整用户路径平均 **4.90273492358秒**，5秒Gate通过；p50为4.67058508350秒，
p95为6.88408400000秒，最慢S091为8.34165641600秒。3秒非阻断挑战未达到。
回执为 `local_phase_9600156b/performance_9600156b.json`；不把旧546f99f7的4.863秒重标成本次结果。
后续纯文档提交不改变上述回执绑定的生产commit。

此前546f99f7上的六源TIFF/metadata、Orientation3/8、APFS/HFS+竞争/取消/重试、只读依赖安装检查
通过，记录在 `local_atomic_546f99f7/`，不是当前提交或完整三平台的发布证书。exFAT实测原子不替换
rename返回ENOTSUP(45)，安全停止且staging清理；不能称exFAT输出通过。公共手册说明先输出到
APFS/HFS+。Intel Mac与Windows x64设备暂缺是用户确认的发布阻碍，本机准确性缺口独立存在。
发布打包、三平台签收与最终Hook/CI仍须在准确性完成后绑定同一最终提交；不创建RC或公开包。

用户已明确M1/M2黑色是外部材料，其余是照片；M3白色是外部材料，其余是照片。原话、消息来源、
窗口与哈希保存在 `material_identity_gap_20261002/review/human_semantics_20261002.json`。
不再等待或要求重复确认这三个区域；精确过渡带仍未标注，不自动生成mask或改gold。
固定RGB种子延续法在M1/M2材料内部停止，不能把停止点授予照片内缘角色。后续先冻结的仿射延续
实验仍会漏掉无噪线性种子后的弱照片前沿，没有安全外推包络；不整合、不沿失败结果调阈值。
三窗和19组反例及可重放脚本见 `material_identity_gap_20261002/human_semantics_followup/`。
这些局部语义不授予通用RGB材料分类权限；separator灰度证据也不能直接转成跨域材料身份。

独立W研究：S040第4邻接即使采用同一W的最有利相关计算仍需比独立合法W下限小80.68px，不能靠
撤回已获权edge125、产生负gap或改成overlap消除冲突。S032/S034已保留proposal共同范围满足必要
逐侧预算，S065不满足；现有best/runner/conditional不是全部解释，不能直接开启common-W。
完整membership仍缺seed处置、去重包含、合并叶子以及后续refit到最终几何的闭合映射；长期保留各pass
全部fit还会改变共存存储。只增加诊断账本不能算输出改进，需先完成受原预算约束的闭合证明。
凭据在 `local_phase_b632c2ff/`，该目录包含c39生成集合上的必要条件研究，不是最终自动权限。

后续只读完整CLI在982f291f（运行时仍为9600156b）捕获S032/S034全部已生成phase记录。
最终相容集合分别为4/6份；小集合穷尽subset/order合并oracle分别比较12/30次，成员均不可连续合并。
这是已生成集合的oracle，不证明seed拒绝、后续补全或最终输出完整。当前硬比较下，S032前3份未分离，
S034前2份未分离；其它成员的支持/coverage排除仍需证明在后续流程成立。两源初次去重只删除完全
相同fit；S034第二次去重8→6删除两份不同的authority/projection来源，几何fit完全相同。
纯owner反例已重放：相同binding key、rank和完整初始区间，canonical pitch为110/130时，原late
refinement分别只保留a、保留a+b+c，各18次lookup；所以这些初始字段不能证明下游等价。
该反例不证明生产generator同轮产生两份，也不证明这两张TIFF被错误裁切。
证据、原始候选、报告、可重放脚本和拟议验收见 `common_w_closure_982f291f_20261002/`。

共同W例外已由父任务询问用户，尚未获得答复；相关合同和runtime扩展暂停。问题限定为全部解释已
覆盖、共同框对每个解释满足原5%和内容保护、证明不完整继续Review、计算预算不增加。
现行架构第9节禁止合并离散框，第10节只授予固定W的共同H；第12节最多2份canonical加1份
conditional以及6次fit-pass保持。S032还有独立H投影权限缺口，不能承诺共同W独自使其通过。
不同projection来源的完整账本可在现权限下修复，但尚无证据它会增加安全auto；不将其当成已证实
准确性收益，不为等待这一决定重复旧颜色、几何下界或全量测试。

S046递归存储独立实验未整合：55296种完整选择oracle得到6个极大解释；两项压缩合用仍只产生3个
中间解释便触及2000次工作预算，不能声称完整搜索。证据 `s046_recursive_storage_20261002/`。
S031/S052的共同H保护仍超过原1.2mm预算；S073/S079/S090的短角边失败不能归为独立H漏检。
以上负结果不证明其它准确性路线都无法继续；W、phase、anchor与邻接独立研究仍在授权范围。

## 当前目标与执行顺序

已从暂停的“V5发布”会话 `01a07f23-208e-7871-ab28-65270d32dc9e` 交接至
`01a0e15e-4384-7972-9455-cd3a9af52ee0`，后者持有持续目标；不唤醒前者。
最新用户要求是在当前 Apple Silicon Mac 完成全部适用发布标准后，再由用户安排 Intel Mac 和
Windows x64 实机验收；跨平台待验不阻塞本阶段开发，也不算已通过。当前只授权本地开发和验证，
已授权本地串行整合和提交；不推送、发布、部署、远程合并或建立公开包。原任务停在 `659d1847`，
本轮从干净主工作区继续。

1. 先完成 H，验收对象是最终安全、留边合格、直接可用的裁切。当前优先识别外侧大面积纯色、低纹理
   或规律纹理片夹区域，再沿其内缘保留照片。保护给定 TIFF 中已经记录的可见内容，不恢复被片夹
   遮挡且没有记录的内容；人工黄金源内 polygon、逐侧 5% 上限及倾斜角点保护仍有效。
2. 区域身份、内缘位置、方向、H 与输出预算在现有模型和联合求解中闭合。低纹理或外侧位置本身不能
   证明片夹；照片贴到源边时不能凭空建立背景种子。允许无害不确定性，不为已可用样片继续精修。
3. 继续 W 的逐张左右边归属、phase、anchor、间隔、接触、重叠与截断，再完成此前全部能力。
   最新指令已解除原先H完成前的W开发顺序限制；物理权限、黄金语义、预算和最终验收保持。
4. 最终当前 development nominal 全部正确 `approved_auto`，所有角色
   `unsafe_approved_auto = 0`；challenge 尽量安全自动通过，安全 Review 不替代 nominal 能力。
   当前 cohort 为 110 task / 106 source，其中 nominal 96、challenge 14；数量以冻结 cohort 核对。
5. 完整用户路径 24-source 平均 `<=5s`，`<=3s` 为持续挑战目标。正式性能留在发布验收；
   工程、黄金、TIFF/metadata、安装、三目标实机、打包与 Hook/CI 都绑定同一最终提交。
   达到发布标准后仍由用户确认发布，不提前创建 RC、tag、Release 或公开 ZIP。

保持 current-only、唯一职责，无旧兼容、样片特例、隐性 fallback、放宽黄金或提高预算。
新机制须改善最终输出或解决具体证明缺口；只增加峰、解释数或中间精度不是整合依据。
同源 task 按 source SHA 组织研究；黄金只用于离线研究和评价，不进入运行时选边。

## 已整合的实现与历史验证

本轮三项独立实验已串行进入本地 main：`34a13e01` 原生 coarse/Cross 证据、`2f655640` 完整共同
enclosing 输出、`cfbe9b00` 可重放的局部精修记录。原 `702c78f7` 及之前的性能修复完整保留；
当前验收以本文件开头绑定的生产提交为准，不能借用独立工作树结果宣称最终通过。
`x5-association` 的 `8b1a280a` 是对应独立实验快照；`x5-native-h` 的独立 min×max 原型未采用。

完整逐 trace broad 修正已在 `40435b3d232706dbc8e4fe1ceb02fa7cd86af0df` 整合：真实峰坐标、
完整极大关联、物理竞争保留、最终来源回链、超界 Gate 与联合外框顶点去冗余由当前唯一路径消费。
本轮关联减少重复搜索：已完成路径的包含传播、经原向外算术证明的三 raw 冲突、固定物理宽度调度，
并按现场 CPython digit 载荷计量 mask 存储。完整 raw、互不包含解释与最终闭集物理 owner 均保持。
`5P²`、`2PT+2T`、路径数量、深度、几何状态、区域分母及原自动批准标准均未提高。
`659d1847` 进一步保留粗测 broad 的完整原始支撑约束。本轮补齐粗测九条 trace 同时保留的数组计量，
与 baseline 共用底层数组去重 owner，原资源上限不变。合成输入实际保留 500274 bytes，原 receipt
仅 53194 bytes，修正后保守峰值为 550570 bytes；这不等于进程 RSS 或全路径 heap 证明。
本轮 main 已整合以下本地开发改动：`bed402b5` 补齐保留数组计量，
`7e91c1aa` 在性能 Gate 失败前保存完整测量记录，`5f9761c1` 将初始关联点对谓词内联，保持每次计费、
完整路径与原上限。后者的 81 份 oracle 结果和完整工作账本逐项等价，S101 正式报告的 measurement、
photo_geometry、candidate_gate、decision 完全相同。独立工作区相同源码的 `tools/verify full`
为 1060 tests OK、2 skipped（Windows 专属），包含依赖、编译、cohort、shell、输出事务与临时打包合同。
后续 `7a3abe82` 删除跟踪热循环的恒定调用与重复距离，84 项专项、40 次完整结果对照通过；
`0dc1dfa7` 在满秩格拟合后跳过被原解覆盖的中位重算，101 项专项、2171 次精确 fit 对照通过，
覆盖低秩、直接及有界最小二乘。`9d7d5f0b` 正式平台入口已通过 full，随后在性能 Gate 失败。
正常 pre-commit Hook 已通过；
当前未推送，未运行本次提交的远端 CI。

`9d7d5f0bf9964d16e27bc289400245219a1e1b53` 的正式 24-source 完整用户路径平均
5.6761117587 秒、p95 8.7694719170 秒，未达到 5 秒 Gate；记录保存在
`Test/gold_analysis/local_release_optimized_20261002/performance_receipt.json`，平台未生成通过证书。
之前 `7e91c1aa` 的同入口平均为 5.5830757829 秒。带插桩的 registered_measurement 平均由 1.710
降至 1.547 秒，template_alignment_decision 由 4.672 降至 4.340 秒，但这些数据不能替代正式 Gate，
本轮结果不支持宣称端到端提速。下一步性能优化仍以完整用户路径为验收。
主工作区既有 6-source TIFF/metadata、APFS 与临时 HFS+、只读 installer 检查通过，记录在
`Test/gold_analysis/local_release_20261002/`；它们不是最终同提交平台合格证。exFAT 未验证。
用户已明确暂时没有 Intel Mac 和 Windows x64；两类实机继续列为发布阻碍，本机工作继续。

最新完整生产开发诊断：

- 命令：`tools/verify diagnostic --gold-analysis --output-root Test/gold_analysis/coarse_trace_memory_20261002_full`。
- 完成 110/110，analysis error 0，21 safe auto、0 unsafe auto；nominal 21/96 自动批准，75 Review，
  challenge 14 项均 Review。与 `h_coarse_full_raw_fix_20261001_full` 的全部非耗时记录完全相同；
  `release_detection_gate_ready=false`，本机检测能力尚未达到发布门槛。
- Detector manifest：`4aef7cdb2cf2b0d5883d5c87a13fdb0dd6eceb9d1f7d42669481c1b583b241b6`。
- Comparator manifest：`b1e90275fa6dfba89449c5b4a04de8088003e4ff931df6a374be1cad0e54ce1e`。
- Cohort SHA：`c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。
- 该运行在主工作区的 `659d1847` dirty tree 执行；整合以完整 detector/comparator manifest
  与 cohort SHA 的精确一致为准。它是绑定源码字节的开发证据，不是 release receipt。
- Report revision 为 `x5crop_v5_template_report_92`。现场依赖为 Python 3.14.8、NumPy 2.5.3、
  SciPy 1.18.1、OpenCV 5.0.0、tifffile 2026.9.20、imagecodecs 2026.8.16、Pillow 12.3.0。

S078/S082 已由 producer-bound Review 恢复为 safe auto，当前 21-auto 集合与旧已接受
`registered_exterior_20260927_full` 相同。S079 已完成关联，仍因 `content_protection_conflict` Review。
当前关联超界 task 为 S046/S055/S057/S058/S059；不能把搜索完成等同于 H 或产品验收。
50 份正式 raw query 重放中，42 份原 COMPLETE 路径集合精确保持；S078/S079/S082 的新 COMPLETE
集合与独立全选择 oracle 相同。存储研究实测活动容器和实际整数载荷，未宣称 Python heap/RSS 证明。

当前 primary 的 H 逐侧诊断为 71 合格、18 外扩超限、15 内切、5 内切且外扩超限、1 未生成。
这是最终 proposal 的 H 几何分类，既不证明 runtime H 预算或全部权限，也不等于 safe auto。
S030 六帧 H 几何合格，但首帧长轴 END 外扩超限；不能把该 W 问题误算作 H。
S064 仍有 H 外扩和比例推断缺口；一份条件方案虽通过 runtime 预算，却内切，不能用它替换主方案。

## 旧版 outer 的复用证据与材料权限边界

稳定 `v4.2.8` 为 `8d14c55d8af5c944a0b78b51df4c4c428e606f07`。精确 tag outer 函数在当前
正式 TIFF/gray owner 上的全任务研究保存在
`Test/gold_analysis/h_release_outer_population_20261001/`，六份既有灰度捕获逐像素等价。
全部 110 TIFF 路径在读取前核验实际 SHA，均与 cohort 匹配，覆盖 110 task / 106 source SHA；
无 unsupported 或 untested。Raw 存在 H 半平面合格候选的任务为 91（nominal 84/96）；
加旧默认 10 px 短轴 bleed 后为 84（nominal 76/96）。这支持优先研究整行统计，不能按黄金挑候选。
研究不运行旧版完整 TIFF normalization、deskew、最终 footprint、材料判断或批准；它不证明 H 完成。

现有固定区域测量仍只是 registered gray facts，未授予片夹或输出权限；`constructed_enclosure.py`
仍未接入 detector。材料研究及反例在 `Test/gold_analysis/holder_region_20260927/` 和
[BOUNDARY_FEATURE_RESEARCH.md](BOUNDARY_FEATURE_RESEARCH.md)。低纹理、外侧位置、颜色前缀均
不足以证明片夹。S047 亮照片与白片夹连通、S106 照片贴源边、窄弱前沿、亚核弱内容及等亮异色
反例继续有效；模型与自动工具不得据此代写人工 reference。

旧 registered-gray 路径的 S064 coarse-short broad 全部候选缺少共同物理直线；当前原生 16-bit 路径已安全自动批准。
现有 coarse-long 只得到全源 `[0,9898]`，没有 candidate-independent 照片组长轴域；后来的 phase
frame domains 不能反向授权新像素 query。不同材料层与 blank ends 的区分仍未成立；
不能缩小原区域多数分母、删除竞争、套用黄金位置或放宽预算解决它。

## 精确下一步与开放风险

1. 准确性仍以96项nominal全部安全自动通过为目标。H继续验证有实际最终裁切收益的通用材料／区域
   机制；三窗人工语义已到，固定RGB与仿射前缀已被反例否定，不再重复请求这三个标签或调节这些
   失败假设的阈值。保护原生弱／异色内容、全部合法物理线族与角点，保留fixed query与原预算。
2. W、phase、anchor与邻接工作可继续。Common-W必须先证明完整解释与后续几何的闭合，不能用
   best/runner/conditional或支持上界分量冒充全部成员。S032/S034只是已保留集合的必要预算检查
   通过；新增完整生成集和late反例见上述归档。共同W权限扩展等待已提交的用户决定，不能提前改合同。
   S040不能靠撤销获权边界或把负gap命名为overlap解决。区间包含、角色身份、权限用途及
   后续refit lineage应由其既有owner统一证明，存储计入真实共存峰值。
3. Local refinement保持完整查询、歧义与raw覆盖回链。S095的既有研究显示大量最近点歧义、无raw
   和单区域支持，解释某条track的拒绝原因不等于穷尽其它连接；对当前报告确认缺口后再修改owner。
   不清零scope、删除guard、覆盖原证据或把数值失败当成闭合。现有完整receipt及篡改回归继续保留。
4. S046存储压缩未完成原搜索，S048 membership仍有4096 visit界限，不能通过返回前缀集合、缩小
   区域多数分母或增加预算制造完整性。必要上界太宽也不能据此删除真实竞争。新机制先证明具体最终
   输出或权限证明收益，再进入生产；已有负面实验不继续围绕同一参数枚举。
5. 当前回执均为development；尚无sealed cohort，xpan/120-645/135-dual未被黄金覆盖。当前未启用
   概率选择；若启用，须满足独立calibration/sealed合同。当前通过与失败结果以本文件开头和对应
   生产commit为准，旧提交的统计、失败尝试及原始证据保留在Git历史和Test归档。
6. 准确性完成后，正式性能、TIFF/metadata、安装、三目标实机、打包与Hook/CI仍须绑定同一最终
   release commit。Intel Mac与Windows x64暂不可用是已确认发布阻碍，不阻止本机适用开发。
   未经用户发布确认不创建RC/tag/Release，不推送或部署。

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
