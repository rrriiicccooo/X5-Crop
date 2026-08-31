# 项目记忆

更新：2026-08-31。现场 `main`、tracked cohort、原 TIFF、source SHA、current report 与最新命令输出
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
  S056 是该合同的真实安全反例。Report revision 为 `x5crop_v5_template_report_31`。
- 完整 development gold 为 110/110、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础 nominal
  14/66、较难 nominal 2/30、challenge 0/14；candidate 为 88 个不可用、17 个安全、5 个不安全，全部不安全
  candidate 均保持 review。相对上一检查点，S023 安全进入 auto；S070 因 source W 冲突、S088 因两个合法
  direct placement 竞争回到 review。该阶段净少 1 个 auto，但关闭了两项危险自动批准，不以覆盖换安全。
- 24-source 性能只接受绑定最终干净 commit 的 receipt；5 秒 mean 是 blocking Gate，3 秒是 non-blocking
  目标。精确时间、RSS、依赖与机器身份不在本文件复制。

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

- 基础 nominal 仍有 52/66 review，较难 nominal 有 28/30 review。主要 Gate 根因是 26 个
  `nominal_grid_complete_frame_unobserved`、12 个 `phase_placement_ambiguous`、9 个
  `phase_template_mismatch`、8 个 `aperture_aspect_ratio_budget_exhausted`、7 个
  `direct_role_binding_authority_unavailable`、5 个 `direct_role_aperture_domain_unavailable`，另有 4 个
  `adjacency_observation_coverage_incomplete` 与 4 个 `nominal_grid_phase_anchor_unavailable`。
- S040/S056 证明完整 query receipt 与 calibrated Grid 仍不足以硬授权整张未观察 Frame；这不是 Grid 的
  永久物理上限。未来只有更强的直接/continuity/topology evidence，或独立校准且可拒绝的概率层，才能
  改变该权限，不能简单删除 failure。
- S088 证明多个 direct placement 可以都满足硬物理合同。后续不能用 residual、support 或未校准 score
  强选；它适合作为未来概率选择层的机制样片。
- 现有黄金没有 `xpan`、`120-645`、`135-dual` 的合格覆盖；`120-67` 只有 3 个 source。

## 精确下一步

1. 以一个小机制闭环完善 candidate-independent sequence 查询走廊，先消除真实的
   `adjacency_observation_coverage_incomplete`，并提高每张 Frame 至少一侧直接角色的观察覆盖；不得放宽
   `nominal_grid_complete_frame_unobserved` 或新增 winner-specific query。
2. 随后处理 nominal 的跨高度弱边缘、极低显著边缘与真实片距变化，让同一 registered measurement owner
   提供更多 typed observation，不建立 enhanced detector 或样片规则。
3. 再依次闭合 adjacency continuity、contact、overlap。概率选择层只设计 feature/calibration/OOD/
   abstention schema，等独立 calibration 与 sealed 数据具备后再进入 runtime。
