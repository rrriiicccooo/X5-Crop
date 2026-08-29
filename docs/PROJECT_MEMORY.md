# 项目记忆

更新：2026-08-29。现场 `main`、tracked cohort、原 TIFF、source SHA 和本地 source record 高于历史记录。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

完成统一黄金校准池的人工复核，再用当前确认基线校准 V5 的安全自动批准能力。准确性优先；nominal
必须安全自动批准，challenge 允许安全 `needs_review`，不能通过放宽 Gate 或样片特例提高通过率。

## 当前检查点

- Diagnostic authority 为 110 个显式 count task、106 个唯一 source SHA；四组同源多 count 共用物理
  几何，但 task authority 独立。
- 106 个 source record 均为当前 schema，全部活动线已分类并完成有界原像素精修：99 张有移动，7 张
  全部保留。当前为 48 张 `user_confirmed`、58 张 `human_adjusted`；确认汇总含 51 个 task。
- 当前自动派生为 94 张 nominal、12 张 challenge；task 维度为 97 个 nominal、13 个 challenge。角色及
  原因在确认时冻结，accuracy 会从冻结证据重新推导并核对，不能手填改类。
- 原始 TIFF、去重工作副本、有界预览、确认图与记录完整；没有 v1/v2 平行池、full/partial 目录、
  archive、blind selector 或孤立样片。S104 已从 authority 中移除。
- Tracked `gold_accuracy.jsonl` 当前为空，表示校准尚未完成；accuracy 必须明确失败为
  `calibration is incomplete`，不得回退旧黄金。
- V5 仍是 `main` 上唯一 current-only production path，尚未发布；公开稳定版仍为 `v4.2.8`。

## 开放风险

- 尚未确认的 58 张记录没有黄金权限；机器 proposal、精修结果、预览和确认图本身都不是 reference。
- Contact 与 overlap 永久属于 challenge；源截断、残缺曝光和非直接可见边界只在其证据使自动安全
  结论不充分时成为 challenge，不能按样片名建立例外。
- 新黄金尚未进入阻断 cohort，当前 detector 的黄金准确度和 release readiness 均未建立。性能与三平台
  receipt 也必须在最终 release commit 上重新生成。

## 下一步

1. 在本地标注器中完成剩余 58 张 source 的原生像素复核与明确确认。
2. 对确认汇总做独立完整性审计，再生成每个确认 task 恰好一行的 `gold_accuracy_blocking` cohort。
3. 运行 accuracy，按 nominal 自动批准率、challenge 安全 review 和几何失败分别修正通用 detector；
   之后再做 source-bound diagnostic。提交与推送遵守 [AGENTS.md](../AGENTS.md) 的 Hook 去重规则。
