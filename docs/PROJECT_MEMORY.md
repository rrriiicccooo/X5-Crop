# 项目记忆

更新：2026-09-01。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三层提高 V5 的通用检测能力。全部角色必须保持
`unsafe_approved_auto = 0`；development nominal 与未来 sealed nominal 的发布目标是全部安全
`approved_auto`。不得改样片角色、隐藏 runner、放宽黄金合同或牺牲正式 mean `<= 5s` 达标；3 秒 mean
仍是持续优化目标。

Grid 是唯一 placement 的主生成模型：format 提供带不确定性的理想 `W/H/pitch`，直接观察负责 absolute
phase、native boundary、source-level extent 与 local advance，反证负责淘汰非法状态。Grid 可以生成默认
placement，但不能靠自身取得自动批准。`approved_auto` 表示当前校准、证据、硬物理合同、剩余不确定性和
OOD 共同支持“风险低到可直接使用”，不是 runtime 已知黄金真值的数学证明。

每次只闭合一个通用物理机制，并同时交付合同/真值表、canonical owner、typed evidence/failure、Debug、
正反例、少量真实样片、完整黄金验收和性能。当前不启用概率 scorer；未来只允许在硬合法候选之后加入
经过独立 calibration、带高阈值、runner margin、OOD 与 abstention 的概率选择。

## 当前检查点

- `CalibratedNominalGridAuthority` 已进入唯一 Grid 路径。Format-specific W/H calibration 与 source-level
  nominal pitch interval 编译为 `CalibratedNominalGridPrior`；至少一个直接角色提供 absolute phase，
  `CalibratedNominalGridFitState` 保存相关 phase/W/pitch/scale，逐 adjacency coverage 和反证决定 selected
  evidence，最终 output geometry 另行绑定 authority。直接边界保留 native coordinate，local advance 仍只
  传播一次；该路径不新增 TIFF query、第二 Grid、fallback 或 score。
- Pitch calibration 使用 frozen development cohort、每 source 至少两个直接 separator adjacency、source
  中位值、跨 source hull 与 0.05 mm 向外量化。当前为：135 37.65–38.20 mm（44/198）、half
  18.70–19.05 mm（11/98）、120-66 60.05–62.55 mm（26/52）、120-67 73.40–74.45 mm（3/6）；其它
  format 保持 unavailable。
- Grid 可以生成完整 diagnostic candidate，但当前 hard-fact 自动批准要求每张 Frame 至少有一侧直接角色。
  双侧都未绑定时，evidence 保存 Frame ordinal，并以 `nominal_grid_complete_frame_unobserved` review；S040、
  S056 是该合同的真实安全反例。Report revision 为 `x5crop_v5_template_report_35`。
- 普通 local refinement 使用完整 format W，不能让正在受检验的 fitted Grid W 过滤自己的反证。唯一
  placement 中至少两张其它完整直接 Frame 闭合的 `SourceFrameWidthAuthority` 可以追加一次有界 lookup，
  在某个双侧未绑定 Frame 中唯一选择已经注册且各自有坐标权限的 native edge pair；没有合格解释或多解
  仍 review。
  双侧未绑定 Frame 若只有一侧唯一 intrinsic edge、另一侧完整 corridor 无候选，也可保留该 native 坐标并
  由同一相关 W 推导 opposite；这同样适用于 calibrated Grid selected fit，但 format/Grid W 没有该权限。
  Source W 不创造坐标、不改变 phase/pitch/ordinal，最终仍重新检查 direct-role、outer、coverage 与预算。
- `SequenceAnchorDiscoveryDomain` 现在以左右锚定的完整 W/pitch role core 为种子，把 coarse support 内每个
  可测整数像素中心恰好分给一个预登记窗口。相邻窗口的 measurement halo 可以重叠，transition ownership
  无重叠、无缺口；逐 adjacency coverage 按离散坐标计数。它复用同一全长 baseline，不新增 TIFF 读取、
  query、winner-specific requery 或第二 detector。
- `AdjacencyContinuityObservation` 现在把 selected placement 的既有 registered facts 按 ordinal 映射为
  `separator_material | no_counterevidence_observed | separator_material_unresolved |
  contact | normal_separator_counterevidence | unresolved | coverage_incomplete`。正序 material band 产生
  separator delta；完整走廊无反证只维持正常 Grid；唯一共享 physical edge 可以产生 Contact。Continuity
  与 topology 分别使用 typed Gate failure，report/Debug 保存完整 ledger。
- `template_contact.py` 从既有 authoritative edge ledger 候选无关地产生 `ContactEdgeObservation`；
  `ContactRelation` 把同一 edge 原子绑定到相邻 END/START，并以 `delta = W - pitch` 进入唯一 prefix 模型。
  重叠的独立 edge identity、separator 竞争、覆盖不完整或多种 ordinal 映射均保持 review。Contact 两侧
  不参加 source W 独立支撑；输出只在两个共享边界增加一份基础 sequence bleed，并继续受同一 5% 预算。
  该机制不新增像素读取、第二 detector、fallback、score 或 topology 特例；Overlap 仍未启用。
- 三个固定高度区域现在复用同一 registered 全长 baseline，同时观察 0.25 mm local 与 0.50 mm broad
  material scale。Broad observation 要求 signed tone、uniformity/texture、polarity、低纹理背景侧和位置
  一致；不扩大 query halo、不增加 TIFF 读取，也不形成 enhanced detector。单条 aggregate edge 默认只作
  诊断；只有 END/START 角色和三区域 separator material 共同闭合的 pair 才能进入 placement。已由 direct
  或更早 aggregate separator 拥有的 edge 不得被重新配对；两区域 material、孤立 edge、角色冲突与多解
  都不取得坐标权限。S042 的三个真实 broad band 已进入 evidence ledger，S079/S095 的既有安全 placement
  在 canonical edge ownership 反例下保持不变。
- 完整 development gold 为 110/110、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
  17/66、较难 nominal 2/30、challenge 0/14；candidate 为 87 个不可用、20 个安全、3 个不安全，全部不安全
  candidate 均保持 review。与上一机制检查点相比，自动批准集合和 candidate 安全分类不变；9 张样片只
  迁移了最先暴露的 typed root failure，全部仍为 `needs_review / not_available`。
- Contact 检查点的 24-source 正式性能通过 mean `<= 5s` Gate；3 秒 non-blocking challenge 尚未达到。
  Receipt 必须绑定最终 clean commit，后续 tree 变化会立即使它失效。

## 证据与数据边界

- 106-source/110-task development gold 用于发现机制、调试和回归，不估计真实生产频率。生产中发现的危险
  自动裁切在完成人工 reference 后永久加入 development gold，作为 incident regression；修复必须通用，
  不能读取样片 identity 或建立 whitelist。
- 未来 sealed representative 必须在查看 detector 结果前按 source SHA 冻结，只输出 aggregate acceptance。
  打开 sealed source 调试后永久转入 development，并补充新的 sealed source。当前没有 sealed cohort，
  因而不能宣称未见 X5 扫描上的错误率或发布准确性。
- 概率选择还需要独立 calibration source；development、calibration、sealed 三种用途不能互相冒充。
  Incident regression 是 development 的来源，不建立第四套 reference 或平行黄金池。
- W/H guard 继续由 105 个合格 source、494 个完整直接 Frame 的 source-level 统计拥有；aspect ratio 是带
  不确定性的强先验，不是零误差 W→H 等式。Separator、holder extent、enclosing support、bleed 与 5%
  产品预算仍按各自物理含义独立拥有数值。

## 开放风险

- 基础 nominal 仍有 49/66 review，较难 nominal 有 28/30 review。当前 phase typed root 主要为 22 个
  `nominal_grid_complete_frame_unobserved`、12 个 `discrete_phase_ambiguous`、11 个
  `direct_role_binding_authority_unavailable`、10 个 `fixed_template_mismatch`、3 个
  `nominal_grid_phase_anchor_unavailable` 与 2 个 `adjacency_continuity_unresolved`；其它失败均保留各自
  typed owner，不能合并成“没找到线”。
- S040/S056 证明完整 query receipt 与 calibrated Grid 仍不足以硬授权整张未观察 Frame；这不是 Grid 的
  永久物理上限。未来只有更强的直接/continuity/topology evidence，或独立校准且可拒绝的概率层，才能
  改变该权限，不能简单删除 failure。
- S088 证明完整三区域联合 separator pair 可以补足 direct-role authority；S042 证明 broad material 能在
  真实低梯度区域形成 typed evidence，但没有足够 placement authority 时仍保持 review。其它仍存在多个
  硬合法 placement 的 source 继续保留 runner，不能用 residual、support 或未校准 score 强选。
- 现有黄金没有 `xpan`、`120-645`、`135-dual` 的合格覆盖；`120-67` 只有 3 个 source。

## 精确下一步

1. 下一个小机制是 Overlap：两条独立角色 edge 反序、合法 overlap interval、同一 5% 预算内的两侧保护、
   Gate 与 Debug；内容连续只能否定普通 separator，不能单独证明 overlap。
2. 剩余 22 个 `nominal_grid_complete_frame_unobserved` 不能靠继续加强边缘 detector 全部解决。完全未观察
   Frame 的校准 Grid 风险权限须先冻结条件、误差包络、OOD 与 abstention schema，并取得独立 calibration
   与 sealed representative；没有这些数据前不进入 runtime，也不能让 Grid/source W 创造像素事实。
3. 带拒绝选项的概率选择只在硬合法候选之后工作，必须冻结 feature/model/calibration schema、绝对概率、
   runner margin、coverage、OOD、性能上界与 typed failure；当前 development gold 不得自校准该权限。
4. 补充不同相机、片夹、曝光与扫描状态，以及缺失的 `xpan`、`120-645`、`135-dual` 格式；生产危险自动
   裁切经人工确认后进入 incident regression，并同时补充新的 sealed source。
