# 项目记忆

更新：2026-10-12。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

V5 保持 current-only、单一职责和零危险自动批准。本轮有界性能/RSS、架构、测试与文档审计已完成。
3 秒为非阻塞 challenge；发布未授权。

## 最新可验证检查点

### Development gold

最新完整报告为
`Test/engineering_audit_20261012/optimized_gold/gold_analysis_summary.json`，绑定 `45a66e36`。
后续 `ba3e9a94` 仅调整测试；detector/comparator 源码身份不变。与审计前完整 gold 相比，110 条记录
除耗时外完全相等，比较证据为 `Test/engineering_audit_20261012/gold_equivalence.json`。

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
detector   2008c5dd9ce7f0dc98b999f61047e94a1d06bf6afba2c90b6e4c46258cde332b
comparator 67ac1b0c03bc674e23e9325020936aaa8ae5538bd50825df0b73404eec87bf25
```

### 性能与 RSS

同一 24-source cohort、环境与硬件的成对测量位于 `Test/engineering_audit_20261012/`：
`baseline_performance_receipt.json` 绑定 `cf5e2a49`，`optimized_performance_receipt.json` 绑定
`ba3e9a94`；汇总重算一致，正式输出状态与 TIFF 数量不变。

| 指标 | 基线 | 优化后 |
|---|---:|---:|
| 平均耗时 | 5.841136 s | 5.747780 s |
| p50 / p95 | 5.432742 / 9.396120 s | 5.302173 / 9.574647 s |
| 平均 peak RSS | 937.15 MiB | 795.47 MiB |
| 最大 peak RSS（S024） | 1612.39 MiB | 1270.48 MiB |

平均/最大 RSS 分别下降 15.1% / 21.2%；平均耗时下降 1.6%，p95 上升 1.9%，不宣称显著提速。
5 秒发布 Gate 未通过，3 秒 challenge 未达到；失败 receipt 完整保留。RGB 联合采样原型实测更慢、
临时分配更多，已拒绝；正式 sampler 未改。

### 架构、工具与文档

当前生产与验证 owner 已同步至架构第 13 节。测试共享 fixture 由纯 support owner 提供，peer test
imports 为 0；全部有效反例保留。源码规模与机械迁移证据位于上述审计目录。
全部文档按职责审核，内部合同由架构独占，公共中英文说明同步。

### 工程验收

`ba3e9a94` 的正常 pre-push full Hook 通过：1245 项测试、2 项跳过；依赖、编译、cohort authority、
脚本与差异检查通过。记录为 `Test/engineering_audit_20261012/push_ba3e9a94.log`。该提交的 12 组合
CI 全部通过，记录为 `Test/engineering_audit_20261012/ci_ba3e9a94_final.json`；后续仅更新检查点文档。
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
- 优化后性能仍未过 5 秒发布 Gate；3 秒仅为 challenge，不宣称达到理论最优。
- 开发 gold、性能与工程检查各自绑定上述提交；发布 commit 的 accuracy、TIFF/metadata、安装、打包、
  Hook 和平台实机 receipt 仍需同一 commit 的证据闭合。
- 当前 gold 没有 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort；不得建立 format 特例或
  声称未见来源泛化。Runtime 排序和独立 calibration/sealed acceptance 仍未取得正式权限。

## 精确下一步

1. 后续性能优化以新的完整路径 profile 和有界等价性证据为起点，保持安全提案覆盖与零危险自动批准；
   不围绕 3 秒目标无限微调。
2. 发布前按架构第 14 节闭合 accuracy、性能、平台、安装、TIFF/metadata、打包与 Hook/CI，再请求发布授权。
