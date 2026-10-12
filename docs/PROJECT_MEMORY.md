# 项目记忆

更新：2026-10-12。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

V5 保持 current-only、单一职责和零危险自动批准。几何求解与重复计算优化已完成并合理收束；
5 秒性能 Gate 尚未通过，3 秒仍为非阻塞 challenge。发布未授权。

## 最新可验证检查点

### Development gold

最新完整报告为
`Test/geometry_optimization_20261012/gold/gold_analysis_summary.json`，绑定 `7f822e72`。
与 `89956fdf` 相比，110 条记录的黄金语义和结论一致；实际投影计数减少或改为端点检查，
部分近共线顶点表示不同，边界最大偏差为 `1.82e-12 px`。比较证据为
`Test/geometry_optimization_20261012/gold_equivalence.json`。

| 项目 | 结果 |
|---|---|
| task / source | 110 / 106 |
| 完成 / 分析异常 | 110 / 0 |
| `approved_auto` / `needs_review` | 25 / 85 |
| 安全自动批准 / 危险自动批准 | 25 / 0 |
| 至少一份安全提案的 task | 110 |
| `release_detection_gate_ready` | `false` |

该集合仍是 development diagnostic；安全提案、候选资格和 Runtime 最终决定分别计数，不能互换权限。
对应 cohort、detector 和 comparator SHA 分别为：

```text
cohort     daaea2ad49564616342051253c8fa67c4922a260d0dcc92f0d187f7b2eb10288
detector   ae916d80041573e90477bfb9ca223cf27b3d38bd9bd182db472267c37e3391ef
comparator 67ac1b0c03bc674e23e9325020936aaa8ae5538bd50825df0b73404eec87bf25
```

### 性能与 RSS

同一 24-source cohort、环境与硬件的完整测量为：
`Test/fit_candidate_optimization_20261012/optimized_performance_receipt.json`（`89956fdf`）与
`Test/geometry_optimization_20261012/performance_receipt.json`（`7f822e72`）。
身份与汇总重算一致，输出状态与 TIFF 数量不变；比较证据为后一个目录的 `performance_comparison.json`。

| 指标 | 基线 | 优化后 |
|---|---:|---:|
| 平均耗时 | 5.214285 s | 5.163244 s |
| p50 / p95 | 4.940840 / 8.765501 s | 4.950683 / 8.820237 s |
| 平均 peak RSS | 793.76 MiB | 791.10 MiB |
| 最大 peak RSS（S024） | 1274.69 MiB | 1268.02 MiB |

配对完整 CLI A/B 均值为 5.211328 → 5.075379 秒，观察到 2.6% 提速；正式测量改善较小，RSS 基本
持平。5 秒 Gate 未通过，3 秒 challenge 未达到；失败测量完整保留。单侧准备缓存和采样行分块没有
明确收益；替代 affine 采样更慢且改变像素，均未合入。旧 seed 系数缓存与 RGB 联合采样原型也已否决。

### 架构、工具与文档

当前 owner 与数值合同见架构第 7、12、13 节。本轮生产代码净减 31 行，没有新增模块；必要回归测试
覆盖任意斜率域、退化区间、原生顶点代表与投影内复用。24 张真实输入重放的最大端点差为 `4.55e-13 px`；
S106 / S109 联合投影顶点逐位一致，LP 次数为 753 → 549 / 479 → 338。全部 25 个自动批准任务的
93 个 TIFF 字节完全相同，证据为上述目录的 `output_equivalence.json`。公共产品行为未变。

### 工程验收

`7f822e72` 的正常 pre-push full Hook 通过：1252 项测试、2 项跳过；依赖、编译、cohort authority、
脚本与差异检查通过。记录为 `Test/geometry_optimization_20261012/push_7f822e72.log`。
该提交的 12 组合 CI 全部通过，记录为同目录的 `ci_7f822e72.json`；后续只同步检查点文档。
CI 不能替代目标平台真实机的 platform/package/release receipt。

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

- 准确性 gate 尚未 ready；当前 25 个自动批准和 85 个 Review 不能替代完整 release 检查。
- 正式测量距 5 秒均值仍差 0.163 秒；3 秒仅为 challenge，不宣称达到理论最优。
- 开发 gold、性能与工程检查各自绑定上述提交；发布 commit 的 accuracy、TIFF/metadata、安装、打包、
  Hook 和平台实机 receipt 仍需同一 commit 的证据闭合。
- 当前 gold 没有 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort；不得建立 format 特例或
  声称未见来源泛化。Runtime 排序和独立 calibration/sealed acceptance 仍未取得正式权限。

## 精确下一步

1. 只有新的 profile 指向足够收益时再继续性能优化；保持完整黄金、安全提案覆盖与零危险自动批准，
   不围绕 3 秒或剩余小差距无限微调。
2. 发布前按架构第 14 节闭合 accuracy、性能、平台、安装、TIFF/metadata、打包与 Hook/CI，再请求发布授权。
