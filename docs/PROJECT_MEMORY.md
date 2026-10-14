# 项目记忆

更新：2026-10-14。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

先使既有样片与本机项目达到对应发布标准，新增扫描和其它平台实测留待随后。按选择与安全准入、
5 秒性能 Gate、完整发布验收的顺序继续推进；达成架构第 14 节全部发布标准后
停止等待用户确认，暂不发布。保持全部黄金任务的合格方案覆盖、完整验证与零危险自动批准；
3 秒为非阻塞 challenge，只合入有明确收益的机制，不反复微调已无收益的方向。

## 最新可验证检查点

### 黄金与选择

以下为依赖安装调整前的最后已验证检查点，新环境正在重验。
生产源码 `588e35d3` 的完整报告为 `Test/release_readiness_20261013/gold_588e35d3/`。
与上轮相比，110 条记录只改变耗时、特征 schema 与两项追加特征；原 28 项特征逐值一致，
几何、候选、决定与黄金标签不变。证据为同目录上级的 `gold_diff.json`。

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

上轮 53 个 nominal placement 阻断任务的分组仍有效：38 个有长轴 phase 歧义，15 个有 Cross
非等价解释，可能重叠；入口为 `Test/selection_admission_20261012/inventory.json` 与 `findings.json`。
当前新增证据：

- 两项反向不变的源截断长度比例使 source 分组 OOF 从 93 safe / 17 unsafe 提升到 98 / 12；
  恢复 S042/S044/S071/S072/S098，无退步；canonical 为 97 / 13，特征完全相同而标签相反的冲突为零。
  正式开发排序为 `ranking_588e35d3/placement_ranking.json`，对照为 `ranking_comparison.json`。
  `admission_enabled=false`；这些已查看开发数据不能替代独立 calibration。
- 剩余 12 个排序错误中，10 个涉及长轴，2 个涉及短轴。错误方案预算通过、合格方案预算失败的
  反例仍存在；截断较少也不必然安全，不能把这些代理整体硬化成准入规则。
- 完整 phase 池的预补全实验增加大量 lookup，未解决测试案例的歧义。S005/S026/S102 的剩余成员
  确有 observation、ordinal、邻接或权限差异；相同完整解释已被现有连续合并吸收，不能合并整个池。
  实验位于 `Test/release_readiness_20261012/full_competition_role_replay.json`，没有合入生产。
- residual 反证保留投影终止 raw fit 是架构已有的明确合同；三个重放仍有其它合法竞争，
  没有证明删除这种反证可安全增加自动批准，该方向暂收束。

本轮共用选择结果构造、来源失败与撤回逻辑，生产代码净减 21 行，源码、工具和测试合计净减 7 行；
没有新增模块。产品裁切行为与自动准入不变，公共中英文手册无需改写。

### 性能与工程

同一工作集的 `performance_receipt_588e35d3.json` 绑定生产提交：24-source 完整路径均值
5.160986 秒，p50 / p95 为 4.851217 / 8.312966 秒；平均 peak RSS 790.55 MiB，最大 S024 为
1269.50 MiB。5 秒 Gate 失败，3 秒 challenge 未达到，原始失败记录保留。

内部 affine 块使用精确等价路径，S096 三份正式 TIFF 的 SHA 全同，单次 CLI 重放 9.079→8.184 秒，
见 `sampling_probe/equivalence.json`。与上轮相比，采样 profile 均值约降 16%，但其它多数阶段略慢，
总均值没有改善；不把不同运行时段的差异全部归因于本轮源码，也不宣称 RSS 改善。
`performance_comparison.json` 保留同 cohort、依赖、决定、输出数量与阶段对照。

`f5de4a27` 修正测试中写死的旧特征数，不改变生产源码，已正常推送。pre-push full 通过 1254 项测试、
2 项跳过，依赖、编译、cohort、脚本与差异检查通过，见 `push_f5de4a27.log`；12 组 CI 全部通过，
见 `ci_f5de4a27.json`。
CI 不替代目标平台实机或发布 receipt。

现场依赖现从用户 pip 目录加载 NumPy 2.5.4、SciPy 1.18.1、OpenCV 5.0.0、tifffile 与 imagecodecs；
Pillow 仍来自 Homebrew。NumPy 合同由 2.5.3 同步到 2.5.4，保留本机安装；上述旧环境 receipt
不能直接证明当前环境。实际 import 身份位于 `Test/release_readiness_20261014/`，待重新完成验证。

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
- 当前 5 秒均值仍差约 0.161 秒；3 秒仅为 challenge，不宣称已达到理论最优。
- 当前 gold 未覆盖 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort，不声称未见来源泛化。
  若让评分承担自动准入，还需独立 calibration、冻结风险/OOD 合同与 sealed acceptance。
- 发布前全部资格仍须按架构第 14 节绑定同一最终 commit；当前没有三目标平台完整实机、安装与打包
  验收闭环。用户已确认可安排 Intel Mac 与 Windows x64 实测；待机制稳定后冻结同一验收提交。
  仍无发布授权。

## 精确下一步

1. 先复核新依赖环境的完整黄金、离线排序和正式性能，保持 110/110 合格方案覆盖与零危险 auto；
   安装渠道和二进制来源变化必须进入新环境身份，不沿用旧计时结论。
2. 对 phase 歧义而 Cross 已 resolved、source W 有独立权限的情况，先检查完整合法池的逐帧归属、
   邻接与固定窗口覆盖必要条件；共同 W 尚无准入权限，不能只凭两份 retained 或相同中心合并。
3. 拟合／候选评估只消除已证明输入等价的重复工作。S109 的密集区域 median 没有重复输入，
   转置 scratch 的同值实验无明确速度收益，不合入；完整 pass 和有效 LP 不直接删除。
   本机达标后再冻结最终 commit，补齐其它平台全部发布验收，达标即停止等待确认，暂不发布。
