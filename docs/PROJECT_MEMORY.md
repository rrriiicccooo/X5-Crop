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

- 每个 bounded phase candidate 在离散竞争前对称执行 `PhaseCandidateAuthorityProjection`：
  `contradicted` 终止；`unavailable` binding 只有在投影后每张 Frame 至少保留一侧直接坐标、相关
  evidence-group 去重后的 `(phase,W,pitch)` rank 为 3、且原 template/ordinal/local topology 可以有界
  重拟合时才退出几何。Eligible candidate 重新 canonicalize 并竞争；弱线保留 provenance，不拥有 phase、
  收窄 W 或隐藏 runner。Report revision 为 `x5crop_v5_template_report_30`。
- 完整 development gold 为 110/110 完成、分析错误 0、`unsafe_approved_auto = 0`。安全 auto 为基础
  nominal 14/66、较难 nominal 3/30、challenge 0/14；candidate 为 88 个不可用、18 个安全、4 个不安全。
  四个不安全 candidate 均保持 review；全部 challenge 安全 review。
- 安全 auto 共 17 个：S003、S021、S022、S023、S025、S059、S063、S064、S067、S070、S081、S083、
  S085、S087、S089、S094、S095。相对上一检查点，S023 安全进入 auto；S088 因投影后暴露第二个 rank-3
  直接解释而回到 review。S098 暴露不安全 review candidate，S109 暴露安全 review candidate；总自动覆盖
  不变。
- 24-source 正式性能在 M2 Max 上继续通过 5 秒 mean Gate，3 秒 non-blocking 目标未达到。精确时间、RSS、
  依赖与机器身份只由绑定最终干净 commit 的 performance receipt 拥有，不在本文件复制成第二真相来源。

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

- 基础 nominal 仍有 52/66 review，较难 nominal 有 27/30 review。当前 phase 主要根因是 27 个
  `direct_role_binding_authority_unavailable`、13 个 `discrete_phase_ambiguous`、10 个
  `frame_width_inference_unavailable`、7 个 `global_lattice_authority_unavailable`、4 个
  `fixed_template_mismatch` 与 3 个 `separator_material_conflict`。
- 当前 direct-evidence 路径仍要求 rank 3，并把投影后双侧都未观察的 Frame 标为
  `complete_frame_unobserved`。这是一条保守路径，不是 Grid 的永久物理上限；规则 blank/低显著 Frame
  需要下一机制的 calibrated nominal authority 才能在不伪造直接证据的情况下安全补齐。
- S088 证明“去掉弱线”既可能释放正确候选，也可能揭示真实 runner。后续不能用 residual、support 或
  未校准 score 强选；它适合作为未来概率选择层的机制样片。
- 现有黄金没有 `xpan`、`120-645`、`135-dual` 的合格覆盖；`120-67` 只有 3 个 source。

## 精确下一步

1. 以一个小机制闭环实现 `CalibratedNominalGridAuthority`：format-specific calibrated W/H/pitch interval、
   至少一个 direct absolute phase anchor、逐 adjacency 完整走廊 coverage、无局部反证、相关 uncertainty
   随 slot 传播，并以最坏 OutputFootprint 检查 5% 预算。它是 direct rank-3 之外的另一条显式 authority，
   不冒充 direct evidence，也不建立第二 Grid。
2. 完成上述 owner、typed failure、Debug、正反例与真实 nominal 后，先跑完整黄金和正式性能，再扩大
   candidate-independent 查询 coverage；不能通过删除安全检查提高通过率。
3. 随后处理 nominal 弱边缘与真实片距变化，再依次闭合 adjacency continuity、contact、overlap。
   概率选择层只做 schema/data/风险设计，等独立 calibration 与 sealed 数据具备后再进入 runtime。
