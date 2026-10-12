# 项目记忆

更新：2026-10-12。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按通用根因改善已有合格裁切的选择与安全准入，保持全部黄金任务的合格方案覆盖、完整验证与零危险
自动批准。5 秒 Gate 尚未通过，3 秒仍为非阻塞 challenge；本轮审计已合理收束，暂不发布。

## 最新可验证检查点

### 黄金与选择

源码提交 `3ca6619c` 的完整报告为 `Test/selection_admission_20261012/gold/`。
与 `7f822e72` 相比，110 条记录除耗时外全部字段一致，证据为同目录上级的 `gold_equivalence.json`。

| 项目 | 结果 |
|---|---|
| task / source | 110 / 106 |
| 完成 / 分析异常 | 110 / 0 |
| 至少一份黄金几何合格保留方案 | 110 |
| 主 proposal 几何合格 / 不合格 | 94 / 16 |
| 安全自动批准 / 危险自动批准 | 25 / 0 |
| nominal 自动批准 / Review；challenge Review | 25 / 71；14 |
| `release_detection_gate_ready` | `false` |

合格保留方案、主方案、candidate 资格与最终决定不能互换。源码、comparator 和 cohort 身份见报告
`analysis_identity`；后续文档检查点不改变生产源码。

53 个 nominal placement 阻断任务与评分选错的 17 个任务重叠 12 个，并集为 58 task / 57 source。
分组入口为 `Test/selection_admission_20261012/inventory.json`，核验结论为 `findings.json`：

- 53 个阻断任务中，38 个有长轴离散 phase 歧义，15 个有 Cross 非等价解释，两组可能重叠。
  Cross 权限缺口多数同时有 phase 失败；仅处理两份 retained 不能代表完整竞争池。
- 17 个评分错误中，15 个只在长轴越线，2 个在短轴越线。S013/S033 的 conditional 直接角色虽已获权，
  仍依赖未闭合 family；不能只增加 role-authorized 指示或将所有 conditional 判负。
- 25 个任务虽有安全几何，却没有预算通过的安全方案；12 个仅涉及 W 超窗、4 个仅 H、9 个两轴。
  未发现重复计费或浮点边界误拒绝，不能直接删除完整物理保护。
- 现有排序仍为 OOF 93 safe / 17 unsafe。S070/S074 各有同 task、同 28 特征及缺失模式而黄金标签相反
  的候选组；开发排序 v5 已显式报告。新旧模型、分数与排名完全一致，见 `ranking_equivalence.json`。
- 成对 Ridge 排序由 93 退步到 90；序列中心特征虽净增 1，却引入 2 个退步；晚期硬反证重排因备选
  未完成有效投影而无收益，均未合入。实验分别保留在 `pairwise_experiment.json`、
  `center_feature_experiment.json` 和 `reorder_targeted_gold/`。

本轮只合入局部候选筛选的共用逻辑与特征冲突诊断。生产源码减 12 行，源码、工具和测试合计净减 1 行，
没有新增模块；公共产品行为、评分方法与自动准入均未改变，公共中英文手册无需改写。

### 性能与工程

`Test/selection_admission_20261012/performance_receipt.json` 绑定 `3ca6619c`。
24-source 完整路径均值为 5.137881 秒，p50 / p95 为 4.903851 / 8.914215 秒；平均 peak RSS 为
791.25 MiB，最大为 S024 的 1269.67 MiB。5 秒 Gate 失败，3 秒 challenge 未达到，原始失败记录保留。
与 `7f822e72` 的 cohort、环境、硬件、决定和输出数量一致，见 `performance_comparison.json`；
上次均值 5.163244 秒，小幅变化不归因为本轮简化，p95 略升，不宣称性能改善。

正常 pre-push full Hook 通过 1252 项测试、2 项跳过，依赖、编译、cohort、脚本与差异检查通过；
`3ca6619c` 已推送，12 组 CI 全部通过。记录为同目录的 `push_3ca6619c.log` 与 `ci_3ca6619c.json`。
CI 不替代目标平台实机或发布 receipt。

## 保留的人工局部事实

用户已确认以下 Orientation=1 原 TIFF 半开坐标窗口的材料语义：

- M1：S064 `[0,8845,330,9445)`；M2：S064 `[2450,7172,2797,7772)`。黑色为外部材料，其余为照片。
- M3：S006 `[1975,2309,2615,2797)`。白色为外部材料，其余为照片。

记录位于 `Test/gold_analysis/material_identity_gap_20261002/review/human_semantics_20261002.json`，
SHA256 为 `c3d8fdbafc29e93fb0828f1cd90191697713bafa86ffe199f948d55535d00994`；其中绑定原话、
source SHA 与窗口像素身份。不再重复请求这三窗确认。精确过渡坐标仍未确认，这些局部语义不授予
通用颜色分类、pixel mask、全源连续性或黄金 reference 权限。

另有已确认的展示窗口事实：`bounded_competitors.png` 中 S047/S003/S064 蓝线接触准确，S016 不准确。
窗口映射为 `Test/gold_analysis/gold_boundary_features_native_20260921/bounded_competitors.json`；
交付图 SHA256 为 `13cac1b104ba68ade9e45687c1e1e7c5ec1ee00c170a75b905832f02598a085a`。
JSON 只证明窗口映射，人工确认仅限展示范围，不扩展为整源或改写 gold；S064 旧窗不覆盖 M1/M2。

固定 RGB 前缀与仿射 seed 外推已被反例否定，不继续围绕同一失败假设调阈值。
反例入口与材料测量权限统一见架构第 5 节，原始证据保留在 `Test/gold_analysis/`。

## 开放风险

- 71 个 nominal 仍为 Review，检测发布 Gate 未 ready；110/110 方案覆盖不代表选择或自动准入完成。
- 5 秒均值仍差约 0.138 秒；3 秒仅为 challenge，不宣称已达到理论最优。
- 当前 gold 未覆盖 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort，不声称未见来源泛化。
  若让评分承担自动准入，还需独立 calibration、冻结风险/OOD 合同与 sealed acceptance。
- 发布前全部资格仍须按架构第 14 节绑定同一最终 commit；当前没有三目标平台完整实机、安装与打包
  验收闭环，也没有发布授权。

## 精确下一步

1. 优先在完整 phase 竞争 owner 内核对晚期硬反证与角色归属，先证明能在既有工作量上限内可靠区分；
   不从 primary/runner 两份显示记录推断已穷尽竞争，也不靠相同中心或 evidence ID 集合去重。
2. 针对已确认的特征冲突寻找可解释、无需新增像素查询的结构事实；先做 source 分组开发评估，有稳定
   收益再实现。现有黄金不能冒充独立校准，缺失证据继续保留 Review。
3. 只有新 profile 指向足够收益时再优化 5 秒路径；检测行为稳定后闭合架构第 14 节的全部发布证据，
   再请求发布授权，不围绕 3 秒或小幅计时差异反复微调。
