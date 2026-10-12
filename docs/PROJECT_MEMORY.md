# 项目记忆

更新：2026-10-12。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

V5 保持 current-only、单一职责和零危险自动批准。拟合与候选评估的重复计算优化已完成并合理收束；
5 秒性能 Gate 尚未通过，3 秒仍为非阻塞 challenge。发布未授权。

## 最新可验证检查点

### Development gold

最新完整报告为
`Test/fit_candidate_optimization_20261012/optimized_gold/gold_analysis_summary.json`，绑定 `89956fdf`。
与上一轮完整 gold 相比，110 条记录除耗时外完全相等，比较证据为
`Test/fit_candidate_optimization_20261012/gold_equivalence.json`。

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
detector   7bda8238abedb72e719bd8a9d3e95d0ed540c6c09eb9177f30b09f5f629ffe3c
comparator 67ac1b0c03bc674e23e9325020936aaa8ae5538bd50825df0b73404eec87bf25
```

### 性能与 RSS

同一 24-source cohort、环境与硬件的完整测量为：
`Test/engineering_audit_20261012/optimized_performance_receipt.json`（`ba3e9a94`）与
`Test/fit_candidate_optimization_20261012/optimized_performance_receipt.json`（`89956fdf`）。
汇总重算一致，正式输出状态与 TIFF 数量不变；比较证据为后一个目录的 `performance_comparison.json`。

| 指标 | 基线 | 优化后 |
|---|---:|---:|
| 平均耗时 | 5.747780 s | 5.214285 s |
| p50 / p95 | 5.302173 / 9.574647 s | 4.940840 / 8.765501 s |
| 平均 peak RSS | 795.47 MiB | 793.76 MiB |
| 最大 peak RSS（S024） | 1270.48 MiB | 1274.69 MiB |

本次观察到平均耗时下降 9.3%、p95 下降 8.5%，RSS 基本持平。5 秒发布 Gate 未通过，3 秒 challenge
未达到；失败 receipt 完整保留。追加的 seed 系数复用原型在 S109 / S106 回放中各省
0.017 / 0.044 秒，已撤回。RGB 联合采样旧原型更慢且临时分配更多，不重复同一方向。

### 架构、工具与文档

当前 owner 与拟合数值合同见架构第 7、12、13 节。实现提交生产代码净减 134 行，含新增反例测试和合同
说明的 tracked 内容净减 80 行，没有新增模块。16,730 个真实线性输入、5,270 个 seed 和 8,000 个边界
案例回放完全相等；证据保存在上述优化目录。公共产品行为未变。

### 工程验收

`89956fdf` 的正常 pre-push full Hook 通过：1247 项测试、2 项跳过；依赖、编译、cohort authority、
脚本与差异检查通过。记录为 `Test/fit_candidate_optimization_20261012/push_89956fdf.log`。
该提交的 12 组合 CI 全部通过，记录为同目录 `ci_89956fdf.json`；后续仅更新检查点文档。
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
- 优化后距 5 秒均值仍差 0.214 秒；3 秒仅为 challenge，不宣称达到理论最优。
- 开发 gold、性能与工程检查各自绑定上述提交；发布 commit 的 accuracy、TIFF/metadata、安装、打包、
  Hook 和平台实机 receipt 仍需同一 commit 的证据闭合。
- 当前 gold 没有 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort；不得建立 format 特例或
  声称未见来源泛化。Runtime 排序和独立 calibration/sealed acceptance 仍未取得正式权限。

## 精确下一步

1. 只有新的 profile 指向足够收益时再继续性能优化；保持完整黄金、安全提案覆盖与零危险自动批准，
   不围绕 3 秒或剩余小差距无限微调。
2. 发布前按架构第 14 节闭合 accuracy、性能、平台、安装、TIFF/metadata、打包与 Hook/CI，再请求发布授权。
