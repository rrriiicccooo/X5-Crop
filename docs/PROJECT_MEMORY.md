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

Runtime 最近改动提交为 `691e33edda3f46331419004a0f4dc594e9ff519e`；当前验证基座为
`058a5d56b8fe3a06a8e9330c1486a8a107d3f5f6`，已正常推送 `main`。
该基座正常 pre-push Hook 的 866 项工程测试通过、2 项按既定条件跳过；
[Verify](https://github.com/rrriiicccooo/X5-Crop/actions/runs/34161454158)
的 12 个 OS/Python 矩阵任务全部通过。工程 CI 不替代最终三目标实机发布 receipt。
本轮闭合局部 Cross 测量、角色权限与全局 solver 输入之间的阶段合同，
未放宽测量阈值、producer／solver 上限、Gate 或人工 reference。

- 单区域片段先进入完整 family 联合证明；不能仅因三个 selected domains 同落一区域而获权。
  原始账本保留全部片段，全局输入只消费达到原始两区域要求的线；未知背景的独立线仍保留。
  S002 正式报告记录 576 次拟合、574 条 raw、503 条局部假设、71 条 solver 输入，
  producer 仍为 TOP 391／BOTTOM 183；安全 primary 与原有 runner 均保留，未触发虚假全局超界。
  精修完整保留新增测量，不再在事后回填旧数组；真实 solver 超界仍由原 typed bound 拒绝。
- 真实源域为 `[-0.5,width-0.5] × [-0.5,height-0.5]`；只在真实 TIFF 外缘求交，
  不普遍外扩 requested 或内部照片边。内部 lane 保留原中心域限制，完整 requested 继续负责原有预算。
  恒等采样完整保留首末行列；8 种 Orientation、旋转、斜边和亚像素内切反例通过。
- 源边、query 或 broad `observable` 域截断的半高峰尾不再取得精确定位；内部已测弱尾仍保留原有
  localization、physical interval 与分组。探查不补读 TIFF、不扩大窗口，不把缺测当作缺边反证。
- 源截断后的实际确认 polygon 是包含检查对象。人工线确定物理轴与权限，受保护输出边的半平面
  检查全部确认顶点，且每个受保护侧都必须实际参与。完整自包含与逐侧诊断一致；
  亚像素内切、缺失受保护侧的斜凸多边形和 `visible_content_limit` 反例均保持失败。
- Material pair 保留 endpoint 原有像素角色候选；两种解释不增加独立票数或 rank，各自核验直接权限。
  S106 旧的第 2 格约 87 px 主缺口已闭合，但靠源边角点仍有约 5.33 px 端部内切，不能称该格完全安全。
- 纯离散歧义的 primary/runner 分别补全局部边界、投影晚期弱线并保留硬反证；不共享 selected W、
  不重新排序、不扩大 6-pass 上界。每个新增调用均记录实际工作量。
- Cross 分别编译两份候选的 N 格支撑区间，同一横向边界须逐组满足原有覆盖条件，不合计为 2N 票。
  S081 的直接 TOP/BOTTOM 闭环恢复，两份候选均安全；S015 新增安全 primary，但数值预算仍失败。
- Report revision 为 `x5crop_v5_template_report_72`，gold record / summary 为 v20 / v23。
  每条 direct Cross 保留原始独立区域数；raw、角色权限、solver 投影与三字段 registration work 回链受检。
  删除 raw、抬高区域数、篡改候选角色或漏计 coarse pair 均不能通过对应校验。
  Cross authority 保留逐候选实际区间与覆盖序号；校验与 Runtime 共用纯 canonical-support owner。
  成对删组、清空全部组或篡改 runner 区间均被拒绝；不复制检测或几何规则。
  每份 footprint 的 `source_extent` 绑定 canonical input、Orientation、measurement 与 deskew；
  源侧／lane 分类由真实源尺寸复算。Final polygon 必须复用 selected geometry，采样 box 由同一 affine
  与 polygon 重建。黄金仍严格比较物理 required polygon，不用采样 AABB 的单元余量豁免内切。
- 原有 `direct_lattice_conflict` 投影失败可通过严格报告校验；集合允许只有 runner 能物化，
  不伪造 primary、不把无法生成计为负例。两项均有失败后修复的回归测试。
- Enclosing aperture-center calibration v6 使用原资格、同源中位数、全体 hull 与 `0.001H` 向外量化。
  S103 的 coarse support 现为 `aggregate_support_unavailable`，退出 selected unique pair 资格；
  其余 17 个 source 的全部观测值不变，未改变区间或预算。
  当前区间为 `[-0.008H, +0.010H]`，精确 observation-set SHA 为
  `766ea7d1f857ba4970edb12d04c1fdae856c7221a051a0f5af919c65c560c12d`。
  成员变化不是单纯 hash 更新；登记本身不改变 pair 选择、采样 geometry 或既有 5% 阈值。

## 完整黄金与性能证据

最新完整开发 receipt：
`/private/tmp/x5crop-local-cross-stage-projection-full-gold-20260908a`。
110/110 完成、分析错误 0、全部物理校准登记一致：

| 层级 | 结果 |
|---|---|
| Primary proposal | 37 safe / 72 unsafe / 1 unavailable |
| Candidate | 24 safe / 12 unsafe / 74 unavailable |
| 最终决定 | 19 safe auto / 0 unsafe auto / 91 Review |
| Nominal | 19 safe auto / 77 Review |
| Challenge | 14 Review，尚无安全 auto |
| 保留候选集合 | 189 份；42 safe / 147 unsafe |
| 每任务至少一份安全 | 40；38 个单份安全、2 个多份安全 |
| 全部保留候选不安全 | 70 个任务 |
| 安全候选且有明确 placement 歧义 | 8 个任务 |

与 `/private/tmp/x5crop-source-cell-full-gold-20260908a` 相比，
全部 189 份候选的身份、角色、生成／预算状态、安全标签与 110 个决定不变，没有新增或失去安全 auto。
992 份 Frame footprint 中，除 S103 两份候选的 24 格外，其余 968 格几何和预算数值不变。
121 份候选的特征只发生 observation ID 重编号；S103 另两份的 Cross 特征值、输出保护与预算数值变化。
S103 新增局部片段后，原先两条 TOP 线的已合并 family 扩展为 11 成员 component，完整并集不能重拟合，
故原片段全部保留。当前 Review 的 TOP／BOTTOM 中心为 47.594098／1939.555653 px，
先前为 49.846194／1922.880939 px；纵向支撑仍不包围完整 template，两份均为 unsafe Review。
此变化已经前后正式 CLI 对照，不是安全覆盖改善，也不能称所有候选几何不变。
S081 两份候选均安全但仍为真实双解 Review；不能因黄金判安全就跳过 Runtime 选择能力缺口。
S079 仍保留安全 runner，当前 primary 不安全，选择能力缺口仍在。

42 份安全候选中 31 项预算 passed / 11 failed；147 份不安全候选中 25 passed / 122 failed。
这说明数值预算不能单独代替黄金安全，也不能据此整体关闭风险检查。

该黄金 receipt 生成于提交前，header 记录基座 `148f85f6` 与当时的 detector/comparator 工作树状态，
不是干净 release receipt。已核对运行时的源文件指纹与已提交的 `058a5d56` 一致：

- detector：`66a784e2b8f8a3a0bdc44370c2ee7afcded569332a52908de6a977db62459d08`
- comparator：`b850b9ae9dab0945129baa9bdfc08be3eb7f1884d31840d5632934e029b196b8`
- cohort：`c4f687b89d9c935eadccd81786476a7e718951b5890a8b421595b7ba3bddd61f`

干净 `058a5d56` 的正式 `tools/verify performance` receipt：
`build/v5-performance/performance_receipt.json`。24-source 完整用户路径均值 **3.825251 秒**，
5 秒 Gate 通过，3 秒挑战未达成；p95 为 6.609726 秒，最慢 S038 为 6.803222 秒。
未插桩进程峰值 RSS 最大 1,212,006,400 bytes。
此结果只证明该提交、当前机器、冻结依赖和本次决定分布，不外推其它平台或未来 release commit。
新黄金分析 development-detail mean 为 4.096786 秒，
不代替正式性能结果。

## 开放风险与精确下一步

1. 在阶段合同修复基础上，继续核查 family 成员关联与真实边界测量缺口。S103 前后正式报告分别为
   `/private/tmp/x5crop-S103-before-local-cross-report-20260908a/x5_crop_report.jsonl`（`148f85f6` 源码）和
   `/private/tmp/x5crop-S103-local-cross-projection-report-20260908a/x5_crop_report.jsonl`（当前检测源码）。
   旧 TOP 两成员完整 15-transition union 可以成线；新增局部假设后 TOP／BOTTOM 各形成 11 成员组件，
   全部并集失败，保留 22 条 raw／18 条局部假设／4 条 solver 线。当前唯一直接 pair 为中段 TOP 13 点与
   BOTTOM 4 点，纵向支撑不足。下一步应证明哪些成员物理上可以关联；不能仅凭旧答案较有利选择性
   合并子集、抛弃新测量或降低完整并集要求。S103 与 S106 均为 nominal，不因源截断就改归 challenge。
2. S106 最新正式测量报告为
   `/private/tmp/x5crop-S106-local-cross-projection-report-20260908a/x5_crop_report.jsonl`。
   当前 11 次拟合保留 10 条 raw／9 条局部假设／1 条 solver 线：8 条 TOP 都只有一区域支持；
   BOTTOM 的局部轨迹现已成功保留为 `format-role-bound-line:9`，robust fit 留下 11 点（trace 3341–5134），
   外侧背景偏好为 0.727273，但仍只有一区域，不能成为全局边界。唯一全局 BOTTOM 为
   `format-role-bound-line:10`，83 点覆盖 407–13773，外侧背景偏好仍为 0.433735，角色未获权。
   TOP query `[0,172.624857]`、113 traces、window=21/gap=5 的可测下界为 26 px，
   人工真实 TOP 投影约为 -31.23 至 18.01 px，当前窗口并未观察到；不能将 query 完成当作缺边反证。
   其它真实附近短轨迹仍存在 material 门槛，后续需按当前源码重新观察，不能认为注册修复解决整条底边。
   源域统一后，第 1、3–7 格不再有源侧内切；第 2 格仍在 TOP 附近有约 5.33 px `sequence_end`
   内切。第 8–12 格 required TOP 仍分别为 10.761929、12.761929、27.044140、27.044140、
   27.044140 px，仍有真实图内缺口。保持严格黄金包含，不移动人工线或增加容差。
3. 先澄清平顶峰分区的定位与物理区间职责，再改分区。200 px trace、背景 20、`values[50:60]=220`、
   scale=81.514422、query=`[0,199]` 的完整梯度平台中心为 50 px，现有分区后 canonical 为 48.5 px；
   实际像素阶跃分界为 49.5 px，仍在现有 localization `[45.5,51.5]` 内。不能仅凭中心偏移就判定
   坐标权限不安全，或把平台中心当成人工 reference。
   将分区改为相反极性 run 之间会同时重分配 physical interval；正式单因素对照使 S086 获得
   不安全 auto、S003/S095 失去安全 auto，因此该实验未合入。不能只修中心而忽略区间消费。
   对照目录为 `/private/tmp/x5crop-localization-S086-baseline-20260908a` 和
   `/private/tmp/x5crop-localization-S086-partition-20260908a`，均含 `x5_crop_report.jsonl`；
   精确下一步是对 5 条 coarse sharp trace（130、3784、7177、10570、14141）核对原／新峰区间、
   `_unique_nearest` 与物理直线可行性，仍调用正式完整 flow，不另造更容易通过的 detector path。
4. 继续核查 S069 transition 1330 的上游身份。其完整 union 曾因 28 条中的 1 条超出 0.10 mm 而被
   exact-union 正确拒绝，三条区间已有共同直线无解证书：
   `/private/tmp/x5crop-family-S069-20260908.jsonl`。不以黄金斜率强行合并或放宽容差。
5. 继续处理尚无安全候选的生成根因和已有安全候选的选择缺口。首轮离线 ridge 排序
   `/private/tmp/x5crop-placement-ranking-20260907a/placement_ranking.json`
   仍绑定旧 `38178c4a` 数据，不是当前集合重训结果；旧折外选择由 36 safe 降到 34，
   S041/S069 退步，因此未接入 Runtime。S028/S041/S069 的既有 content 检查没有 veto fact，
   不再假设重复增加该 receipt 能解决选择问题。
6. 当前仍为 `development_only_not_release_ready`。没有 sealed cohort，黄金未覆盖
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
