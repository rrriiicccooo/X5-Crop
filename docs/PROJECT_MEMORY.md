# 项目记忆

更新：2026-08-26；以现场 `main`、tracked cohort、source SHA 和本地标注状态为准。

本文件只保存跨会话继续工作所需的当前目标、检查点、风险和下一步。长期合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，黄金标注与验收规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，验证与协作规则见
[../AGENTS.md](../AGENTS.md)。

## 当前目标

在本地标注器中审核 94 个由用户红线恢复的 `gold_calibration_v2` 草稿，逐个 count 完成原生像素
检查和人工确认，再独立决定是否纳入阻断黄金。S043、S047、S105 没有人工红线，继续保持
`machine_proposal`。S107 同一 source 同时保留 count=2 的 S107 task 与 count=1 的 S112 task；两者
共享物理边界，但必须分别审核。

机器拟合、红线导入、review JPG 和 detector 输出都只提供 proposal。任何 v2 记录都不得因算法一致、
当前通过率或生成图看似合理而自动晋升。黄金方向性验收以
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md#黄金验收语义) 为唯一操作说明。

## 当前检查点

- 仓库只有 V5 current-only production path；公开稳定版仍为 `v4.2.8`，V5 尚未发布。
- 受跟踪的 accuracy cohort 为九项 `gold_accuracy_blocking`；diagnostic cohort 为 110 个显式 count task，
  只证明工程合同、authority、schema 与终止性，不提供 accuracy verdict。
- 本地标注状态覆盖 106 个唯一 source、110 个 task：94 个 `human_adjusted`、3 个
  `machine_proposal`、9 个 `user_confirmed`。S107/S112 共享 SHA；count=1 已映射到可见照片，count=2
  还包含大部分完全曝光的一格。
- Annotation schema 用 typed `slots`、`adjacencies`、`slot_kind` 和逐线 `review_basis` 表达空片、
  残缺、接触、叠片、机器补线与 frame-width estimate。同源多 count 中，被其它 task 使用的红线不再
  误报为 source-level unmatched。

## 开放风险

- 未经用户逐 task 确认的边界仍不是 reference；肉眼或原生像素也无法确定的边保持 unresolved。
- S101、S102、S106 各有一条因源栅格约束而保留的机器共享边；S007、S010/S049、S041/S050、S044、
  S054、S056、S070 仍含明确机器补线，必须逐项检查。
- `review_context.json` 中的漏光、小角和正负片只用于评估通用证据与覆盖面，不产生样片 whitelist、
  runtime 阈值分支或另一条 detector path。
- 当前 commit 尚无新的 accuracy、diagnostic、performance 或三平台 receipt。Release 仍需同一最终
  commit 上的准确性、性能、依赖、TIFF、中文路径、文件系统恢复及三目标实机证据。

## 精确下一步

1. 在浏览器标注器中按 `human_adjusted` 筛选，逐张审核共享边、各 count 边界、机器补线和
   `review_context`；每次只查看一张原 TIFF。
2. 用户确认后核对 source SHA、format、count、baseline schema 与 digest，再独立更新
   `gold_accuracy_blocking` cohort 并运行 accuracy。
3. Detector 改动后运行 source-bound diagnostic；提交和推送只使用正常 Hook 已覆盖的验证，不手工
   重复。Performance 与三平台 receipt 仅在最终 release commit 冻结后重建。
