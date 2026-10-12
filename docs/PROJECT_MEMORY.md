# 项目记忆

更新：2026-10-12。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

V5 继续保持 current-only、单一职责和零危险自动批准。当前进行有界的性能/RSS、架构、测试与文档审计；
性能优化和模块 owner 更新仍在进行。发布未授权，不创建 RC、tag、
GitHub Release 或公开 ZIP。

## 最新可验证检查点

### Development gold

最新完整报告为
`Test/gold_analysis/proposal_sequence_20261011/full_holder_admission_partition/gold_analysis_summary.json`，
绑定 gold commit `c54fadeb`；当前 `cf5e2a49` 仅有测试 fixture 差异，不能把该报告当作当前发布证书。

| 项目 | 结果 |
|---|---|
| task / source | 110 / 106 |
| 完成 / 分析异常 | 110 / 0 |
| `approved_auto` / `needs_review` | 25 / 85 |
| 安全自动批准 / 危险自动批准 | 25 / 0 |
| 至少一份安全提案的 task | 110 |
| `release_detection_gate_ready` | `false` |

该集合仍是 development diagnostic；安全提案、候选资格和 Runtime 最终决定分别计数，不能互换权限。
对应 development cohort SHA 为
`daaea2ad49564616342051253c8fa67c4922a260d0dcc92f0d187f7b2eb10288`。

### 性能基线

当前基线 receipt 为 `Test/engineering_audit_20261012/baseline_performance_receipt.json`，绑定
`cf5e2a49`：24-source 平均 `5.841136s`，p50 `5.432742s`，p95 `9.396120s`，最慢 S096 为
`9.815311s`；RSS 平均 `982667946.67` bytes，峰值 `1690714112` bytes（S024）。5 秒 Gate 未通过，
3 秒 challenge 未达到。该结果只是本次 baseline，不能写成已优化最好或最终结果。

### CI

`Test/gold_analysis/proposal_sequence_20261011/ci_cf5e2a49_final.json` 记录当前 head SHA
`cf5e2a49` 的 12 个 CI job 全部 success/completed。CI 不能替代 Intel Mac、Windows x64 等真实机的
platform/package/release receipt，相关发布风险仍开放。

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
- 性能 baseline 未过 5 秒 Gate，性能/RSS 根因分析仍在进行；不得声称最终优化结果。
- 当前 gold 绑定 `c54fadeb`，当前审计基线为 `cf5e2a49`；最终 commit、TIFF/metadata、安装、打包、
  Hook、平台实机 receipt 仍需同一 commit 的证据闭合。
- 当前 gold 没有 `xpan`、`120-645`、`135-dual` 真实样片，也没有 sealed cohort；不得建立 format 特例或
  声称未见来源泛化。Runtime 排序和独立 calibration/sealed acceptance 仍未取得正式权限。

## 精确下一步

1. 完成有界性能/RSS 与架构、测试审计；主线程据最终证据补齐模块 owner 和性能结果，不提前写入未知事实。
2. 将修订后的代码、文档与验证绑定最终 commit，运行受影响的最小 `tools/verify` 检查，并补齐 Intel Mac、
   Windows x64 与打包/release receipt。
3. 只有 accuracy、性能、平台、安装、TIFF/metadata、打包和 Hook/CI 均按架构第 14 节闭合后，才进入发布
   决策；发布仍需用户明确授权。
