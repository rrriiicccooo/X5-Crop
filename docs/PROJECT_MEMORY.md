# 项目记忆

更新：2026-10-15。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

先使既有样片与本机项目达到对应发布标准，新增扫描和其它平台实测留待随后。按选择与安全准入、
5 秒性能 Gate、完整发布验收的顺序继续推进；达成架构第 14 节全部发布标准后
停止等待用户确认，暂不发布。保持全部黄金任务的合格方案覆盖、完整验证与零危险自动批准；
3 秒为非阻塞 challenge，只合入有明确收益的机制，不反复微调已无收益的方向。

## 最新可验证检查点

### 黄金与选择

当前 pip 环境完整报告为 `Test/release_readiness_20261015/gold_material_validation/`，110 条均完成、
无异常。材料验证修复后，全部记录除耗时外与同目录上级的 `gold_profile_qualification/` 逐字段全同，
证据为 `material_validation_gold_equivalence.json`；production 源码未变。这是开发回归，发布验收
仍须绑定最终 release commit。依赖环境调整后，S086 的主方案由合格变为不合格，合格备选和 Review
阻断均保留。

| 项目 | 结果 |
|---|---|
| task / source | 110 / 106 |
| 完成 / 分析异常 | 110 / 0 |
| 至少一份黄金几何合格保留方案 | 110 |
| 主 proposal 几何合格 / 不合格 | 93 / 17 |
| 安全自动批准 / 危险自动批准 | 25 / 0 |
| nominal 自动批准 / Review；challenge Review | 25 / 71；14 |
| `release_detection_gate_ready` | `false` |

合格保留方案、主方案、candidate 资格与最终决定不能互换。源码、comparator 和 cohort 身份见报告
`analysis_identity`。

上轮 53 个 nominal placement 阻断任务的分组仍有效：38 个有长轴 phase 歧义，15 个有 Cross
非等价解释，可能重叠；入口为 `Test/selection_admission_20261012/inventory.json` 与 `findings.json`。
当前机制证据：

- 两项反向不变的源截断长度比例保留于特征 owner。新环境 source 分组 OOF 为 98 safe / 12 unsafe，
  canonical 为 97 / 13，特征完全相同而标签相反的冲突为零。
  正式排序为 `Test/release_readiness_20261014/ranking_bc405d23/placement_ranking.json`。
  `admission_enabled=false`；这些已查看开发数据不能替代独立 calibration。
- 剩余 12 个排序错误中，10 个涉及长轴，2 个涉及短轴。错误方案预算通过、合格方案预算失败的
  反例仍存在；截断较少也不必然安全，不能把这些代理整体硬化成准入规则。
- 完整 phase 池的预补全增加 lookup，未解决 S005/S026/S102 的真实身份、ordinal、邻接或权限差异。
  投影终止 raw fit 的 residual 反证仍须保留；残差量化使 S086 变好、S068 变差，没有净收益，已撤回。
  不继续围绕完整池强行合并、删除反证或舍入精度调参。实验入口分别为
  `Test/release_readiness_20261012/full_competition_role_replay.json` 与 `gold_1a5bd053/`。
- 22 个 nominal phase ambiguous、Cross resolved 任务中，仅 6 个主备 pair 满足共同固定框的必要
  几何条件。完整池重放后，S006/S026/S075/S080/S081 均有槽位放不下；S005 仅必要几何可行，
  尚无共同 W 准入。S080/S081 对全部 7 / 6 个 ordered 成员分别执行 late local binding 后，
  三个槽位仍均放不下；只保留 source-W supported 子集不能代表完整竞争。
  Source W 只对自己的 placement identity 有效；成员须从原始 source state 独立核验。
  可复现实验为 `Test/release_readiness_20261014/common_window_pair_screen.json`、
  `common_window_pool_replay.json`、`common_window_late_pool_replay.json` 与同目录
  `replay_common_window_pool.py`，均未授予自动批准。
- 15 个 Cross `non_equivalent_fits` 阻断中，8 个同时有 phase 失败；S019 的合格方案均预算失败，
  S048/S074 仍有不合格解释。其余 S002 有 22 条 trace 的局部选择歧义，S015 的 5 个 canonical 组
  缺少纵向投影权限。S028/S045 即使完成全部归属搜索，新增唯一 union 也分别为 174 / 145；
  已完成作用域的必要拟合数量就超过原预算，单独优化搜索不能回收自动批准。
  精确作用域与预检见 `Test/release_readiness_20261015/common_h_closure_audit.json`，未放宽工作量上限。
- S042 在同一冻结 trace 上比较 uint8、原生亮度、RGB/opponent 与原生宽缓测量。原生宽缓峰由
  4352 增至 7387，但未补齐完整可准入边界；增加信号不等于取得角色或邻接权限。
  证据为 `Test/release_readiness_20261015/S042_registered_native_probe_broad_edges.json`，未合入生产。
- S042 第二个 separator 的 4 个 raw family 只在部分 trace 同点，3083 / 3340 上仍有不同原始
  transition，不能整体去重。保留四份解释的必要条件重放未区分最终 2 个候选，两份原 placement
  仍各有 8 条边超预算，见 `Test/release_readiness_20261015/alias_necessary_replay/verification.json`。
  没有执行新增 pair refit；当前证据不足以支持新增 alias 准入机制，不合入生产。
- S053 的唯一合格备选 `source-clipped-review-placement:3` 已严格绑定到当前正式 CLI 的完整原始
  diagnostic、六份 footprint、预算与黄金标签。END117 仍无权限；剩余获权 native full 区间在当前
  role/ordinal 映射下要求的两组等 pitch 区间相隔 20.748497 px，不依赖校准先验也不能相交。
  证据为 `Test/release_readiness_20261015/S053_selection_audit/current_ledger_binding.json`；
  该结论不排除不同角色身份或有独立实测支持的局部 advance，不能直接晋升 Review 方案。

选择结果构造、来源失败与撤回逻辑共用原 typed owner。长轴角色与配对资格也改为共用同一判定，
该去重使生产代码净减 31 行，没有新增模块；原实现的 11250 组完整 profile 比较全部一致，证据为
`Test/release_readiness_20261015/profile_qualification_equivalence.json`。
Development report 校验复用 typed parser 与材料 classifier，从各区域区间重建材料状态与完整包络；
原验证器接受的四类错误记录现均被拒绝，原报告仍通过，证据为同目录 `material_report_rejection.json`。
该修复只改变验证工具，不改变 detector、排序或自动批准权限。

### 性能与环境

新环境的 `Test/release_readiness_20261014/performance_receipt_bc405d23.json`：24-source 完整
用户路径均值 4.441367 秒，p50 / p95 为 4.149025 / 7.430305 秒；平均 peak RSS 747.97 MiB，
最大 S024 为 1227.78 MiB。5 秒 Gate 已通过，3 秒 challenge 未达到。

内部 affine 块使用精确等价路径，S096 三份正式 TIFF 的 SHA 全同，单次 CLI 重放 9.079→8.184 秒，
见 `Test/release_readiness_20261013/sampling_probe/equivalence.json`。旧环境 5.160986 秒的失败
receipt 保留；安装来源与数值后端同时变化，不能把本次总耗时或 RSS 改善全部归因于单项源码或库。

现场依赖现从用户 pip 目录加载 NumPy 2.5.4、SciPy 1.18.1、OpenCV 5.0.0、tifffile 与 imagecodecs；
Pillow 仍来自 Homebrew。NumPy 合同由 2.5.3 同步到 2.5.4，保留本机安装。实际 import 身份位于
`Test/release_readiness_20261014/dependency_imports_before_contract_update.json`；旧环境 receipt
不能替代当前环境证据。CI 不替代目标平台实机或发布 receipt。

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
- 本机 5 秒 Gate 已通过，后续机制改动须保留收益；3 秒仅为 challenge，不宣称已达到理论最优。
- 当前 gold 未覆盖 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort，不声称未见来源泛化。
  若让评分承担自动准入，还需独立 calibration、冻结风险/OOD 合同与 sealed acceptance。
- 发布前全部资格仍须按架构第 14 节绑定同一最终 commit；当前没有三目标平台完整实机、安装与打包
  验收闭环。用户已确认可安排 Intel Mac 与 Windows x64 实测；待机制稳定后冻结同一验收提交。
  仍无发布授权。

## 精确下一步

1. 从 S053 的 edge1 / 47 / 63 / 67 原始 role 与邻接事实，区分 aperture 角色绑定错误和已观察但未形成
   relation 的局部 advance；再按同类根因分组。当前完整五次 phase 返回在
   `Test/release_readiness_20261015/S053_phase_inputs.pkl`，正式报告在 `S053_current_phase/`。
   不只补 END117 或扩 Grid 先验，也不能只按预算换选：另两份预算通过的 Review 方案仍不合格。
2. 保持 110/110 合格方案覆盖、完整黄金与零危险 auto；不绕过已证明的共同框容量或拟合预算缺口。
   原生测量未证明准入收益前不合入，不围绕无净收益的残差量化微调。
3. 性能只消除已证明输入等价的重复工作。S109 的密集区域 median 没有重复输入，
   转置 scratch 的同值实验无明确速度收益，不合入；完整 pass 和有效 LP 不直接删除。
   本机检测与工程全部达标后再冻结最终 commit，补齐其它平台全部发布验收，达标即停止等待确认，暂不发布。
