# 项目记忆

本工作树是原生 coarse/Cross 证据实验快照，未并入 main，不能当作发布版本。

更新：2026-10-02。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与执行顺序

已从暂停的“V5发布”会话 `01a07f23-208e-7871-ab28-65270d32dc9e` 交接至
`01a0e15e-4384-7972-9455-cd3a9af52ee0`，后者持有持续目标；不唤醒前者。
最新用户要求是在当前 Apple Silicon Mac 完成全部适用发布标准后，再由用户安排 Intel Mac 和
Windows x64 实机验收；跨平台待验不阻塞本阶段开发，也不算已通过。当前只授权本地开发和验证，
不推送、发布、部署、合并或建立公开包。原任务停在 `659d1847`，本轮从干净主工作区继续。

1. 先完成 H，验收对象是最终安全、留边合格、直接可用的裁切。当前优先识别外侧大面积纯色、低纹理
   或规律纹理片夹区域，再沿其内缘保留照片。保护给定 TIFF 中已经记录的可见内容，不恢复被片夹
   遮挡且没有记录的内容；人工黄金源内 polygon、逐侧 5% 上限及倾斜角点保护仍有效。
2. 区域身份、内缘位置、方向、H 与输出预算在现有模型和联合求解中闭合。低纹理或外侧位置本身不能
   证明片夹；照片贴到源边时不能凭空建立背景种子。允许无害不确定性，不为已可用样片继续精修。
3. H 验收后继续 W 的逐张左右边归属、间隔、接触、重叠与截断，再完成此前全部能力和下文延后审计。
   H 阶段冻结无关 W 算法修改；既有 W 与放置模型仍可约束 H。
4. 最终当前 development nominal 全部正确 `approved_auto`，所有角色
   `unsafe_approved_auto = 0`；challenge 尽量安全自动通过，安全 Review 不替代 nominal 能力。
   当前 cohort 为 110 task / 106 source，其中 nominal 96、challenge 14；数量以冻结 cohort 核对。
5. 完整用户路径 24-source 平均 `<=5s`，`<=3s` 为持续挑战目标。正式性能留在发布验收；
   工程、黄金、TIFF/metadata、安装、三目标实机、打包与 Hook/CI 都绑定同一最终提交。
   达到发布标准后仍由用户确认发布，不提前创建 RC、tag、Release 或公开 ZIP。

保持 current-only、唯一职责，无旧兼容、样片特例、隐性 fallback、放宽黄金或提高预算。
新机制须改善最终输出或解决具体证明缺口；只增加峰、解释数或中间精度不是整合依据。
同源 task 按 source SHA 组织研究；黄金只用于离线研究和评价，不进入运行时选边。

## 当前源码与验证身份

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

1. 原生 16-bit coarse-short 与共同 enclosing 输出保存在独立 worktree
   `/Users/zhyoung/Documents/Codex/2026-10-02/task/x5-association`，尚未并入 main。
   Schema96 由 canonical Cross 显式授予共同 support 资格，保留完整候选 fits；所有成员使用完整物理
   aperture 中心范围，不扩大 unique-pair 校准的适用域。共同 polygon 逐成员重算风险，alignment
   只计原 raw departure/pixel-center 保护，不重复计入解释/位置不确定性。报告独立重放资格、完整
   fits、物理中心权限与预算。S094 已恢复 safe auto，S064/S067 保持 safe auto。
   当前 full 为 1074 tests OK、2 Windows skipped；完整 110-task 全部完成、0 analysis errors，
   21 safe auto、0 unsafe auto、75 nominal Review、14 challenge Review。
   证据：`Test/gold_analysis/common_support_20261002_full`；detector
   `213c5b6b0b2d725579f01b855c7aa62aa5071766fb121756edf10a880fee30e6`，comparator
   `efc6294f2b1b15bde4d74899a7ae4d2abd3485cfd408bbd2ef7b8b1c1aecc97b`，cohort
   `c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`。
   S095 仍有真实 local refinement scope 1：bottom:98 是唯一 anchor，55 traces 中13个唯一最近点、
   40个歧义、2个无候选；拟合收敛但 role 不获权，方向也与anchor不相交，所以被拒。原selected输入
   全部仍在原raw observations中。下一步保留scope计数，补完整原owner receipt与可重放结构拒绝证明，
   不能清零、删除guard或把数值失败当作闭合。Canonical/proposed 单侧bottom组完全相同，可按完整
   fit身份证明没有新增解释，不能凭组名称丢弃真正不同的conditional解释。
   Main 已新增本地性能提交 `37f0607397e04f19410042dab3ae5ce8d4a7c2d2`：精确证明组外严格多数零值
   中位数。Main full 1063 tests OK、2 skipped；S101 12131次计算全部与原median一致，10280次可省
   partition；measurement/photo_geometry/candidate_gate/decision与优化前完全一致。正式性能正在单独
   运行，未宣布<=5s通过。该优化未进入此工作树；两处仍须按已验证范围串行整合，不推送。
2. 在旧 outer 的全任务候选研究上，验证有实际最终输出收益的通用整行区域统计。
   同时保护原生弱／异色内容、全部物理线族与角点；保留当前 fixed query、材料身份、来源、
   构造／实测分离、Gate 与预算。仍无材料权限时保持 unavailable，不把研究候选接成自动输出。
3. 只围绕实际 H 内切、外扩、预算和安全批准缺口推进；H 合格项继续回归，不以提高中间精度替代
   最终裁切验收。H 验收后再开展 W，已有 W 模型可以约束 H，但不提前扩大 W 算法范围。
4. 当前所有 receipt 均为 development；尚无 sealed cohort，xpan/120-645/135-dual 未被黄金覆盖。
   正式性能、TIFF/metadata、安装、三目标实机及打包验收仍须绑定同一最终 release commit。
   当前未启用概率选择；若启用，须独立 calibration/sealed 合同。未经用户确认不创建 RC/tag/Release。

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
