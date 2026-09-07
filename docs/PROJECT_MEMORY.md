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

当前 Runtime 与验证基座为 `8b88ecee30fdd08f0e1a317b7099daf90adf7a1d`，已正常推送 `main`。
正常 pre-push Hook 的 877 项工程测试通过、2 项按既定条件跳过；
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34165001268)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。

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
- Report revision 为 `x5crop_v5_template_report_73`，gold record / summary 为 v20 / v23。
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
- Enclosing aperture-center calibration v7 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  本轮 selected unique pair 的 source 从 17 变为 20：新增 S028/S038/S074/S089/S092，
  移除 S042/S073；共同 15 项中仅 S008 的 support midpoint 由 1433.504671 变为 1433.419661 px。
  区间仍为 `[-0.008H, +0.010H]`，没有为更高通过率缩窄区间；精确 observation-set SHA 为
  `b3af27b93ef13bd0696c78d50ee4b68d408ea833a2a3b5d99b53a44e9298071e`。
  最终全量重新派生与登记一致；登记不改变 pair 选择、采样 geometry 或 5% 阈值。

## 完整黄金与性能证据

最新完整开发 receipt：
`/private/tmp/x5crop-cross-baseline-final-full-gold-20260908a`。
110/110 完成、分析错误 0、全部物理校准登记一致：

| 层级 | 结果 |
|---|---|
| Primary proposal | 38 safe / 71 unsafe / 1 unavailable |
| Candidate | 29 safe / 9 unsafe / 72 unavailable |
| 最终决定 | 21 safe auto / 0 unsafe auto / 89 Review |
| Nominal | 21 safe auto / 75 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 186 份；43 safe / 143 unsafe |
| 每任务至少一份安全 | 41；39 个单份安全、2 个多份安全 |
| 全部保留候选不安全 | 69 个任务 |
| 安全候选且有明确 placement 歧义 | 7 个任务 |

与上一版 `/private/tmp/x5crop-local-cross-stage-projection-full-gold-20260908a` 相比：
新增安全 auto 为 S004/S065/S069/S078/S082；S038/S064/S067 退回 Review，净增 2 项。
不能把净增当作没有退步。Final 与本轮 probe 的 110 个决定、proposal/candidate 安全标签和
逐 Frame 黄金几何诊断一致。安全歧义任务为 S005/S015/S029/S034/S035/S048/S067。

43 份安全候选中 29 项预算 passed / 14 failed；143 份不安全候选中 28 passed / 115 failed。
数值预算不能单独代替黄金安全，也不能据此整体关闭风险检查。

黄金 receipt 生成于提交前，header 记录基座 `f1e4324b` 与当时的工作树身份，
不是干净 release receipt。已核对以下运行源指纹与提交 `8b88ecee` 一致：

- detector：`0eb4691e262857bb001b4375e8e6508584c927802f565a2c2cfeab6e39386da3`
- comparator：`e70cd52ec25caa85969fd617cef1266cce3cbdd837501a3d84325f52411701b4`
- cohort：`c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`

干净 `8b88ecee` 的正式 `tools/verify performance` receipt：
`build/v5-performance/performance_receipt.json`。24-source 完整用户路径均值 **3.588597 秒**，
5 秒 Gate 通过，3 秒挑战未达成；p95 为 6.236651 秒，最慢 S091 为 6.557221 秒。
未插桩进程峰值 RSS 最大 1,208,647,680 bytes。
此结果只证明该提交、当前机器、冻结依赖和本次决定分布；S038 从 auto 变为 Review 减少了正式裁切输出，
不能把相对上一版 3.825251 秒的均值下降全部归因为检测优化。新黄金 development-detail mean 为
3.987565 秒，不替代正式性能。

## 开放风险与精确下一步

1. 先以正式完整 flow 对照本轮三个退步样片，区分测量、角色、选对与预算职责：
   S038 的 primary/candidate 仍安全，但由 enclosing support 输出，多个 top/bottom 最坏外扩超过
   1.2 mm，最大约 1.512 mm；同状态 alignment padding 仍通过。S064 新 primary 不安全，
   三格 outward cross_low 超限，并有 aperture-aspect-ratio conflict；S067 primary 安全但出现
   `non_equivalent_fits`，runner 第 1 格 sequence_start 不安全。不能为恢复旧 auto 回退共同基线、
   强选旧线或放宽 Gate。需要逐 trace 比较基线前后 material 与角色，再核对 selected pair 的物理权限。
2. S002 从安全 primary 变为 unsafe Review，当前唯一新增包含失败为第 1 格 sequence_end 的角点。
   当前 top/bottom 在黄金轴上的外扩仍约 40 px，不能简单归因于 bottom 直接内切；
   第 1 格 END 中心外扩由约 5.762 降到 1.876 px。正式报告为
   `/private/tmp/x5crop-S002-cross-baseline-report-20260908a/x5_crop_report.jsonl`。
   当前 raw 29／local 23／solver 6，拟合 31；旧为 574／503／71，拟合 576。
   下一步回链 Cross 变化如何影响同状态直线、角点与纵向联合保护，不能只看中心边距。
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
   首轮离线 ridge 排序 `/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`
   仍绑定旧 `38178c4a`，折外由 36 safe 降到 34，未接入 Runtime，不是当前集合重训结果。
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
