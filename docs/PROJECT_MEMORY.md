# 项目记忆

更新：2026-08-14

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，稳定合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 与最新命令输出优先。

## 当前目标

完成唯一 V5 current-only 模板对准器：format/count 先编译固定模板，像素只负责对准、解释有限物理
偏差和否决危险输出。九项用户确认黄金必须安全，111-source diagnostic 必须工程闭合，24-source
完整用户路径平均必须不超过 5 秒。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- 旧 chain/proposal/materialization/cache/dominance runtime 与直接依赖测试已删除；production 只保留
  `TemplateMeasurementPlan → SequenceFit/CrossFit → FormatPlacement → selected-only safety`。
- `tools/verify full` fresh 通过：277 项、2 项环境跳过；13 个 format/mode configuration 与 cohort
  count authority 同时通过。
- `tools/verify accuracy` fresh 通过：9/9 safe；S027、S035、S051、S062、S091、S094、S109 为
  `approved_auto`，S055、S098 为安全 `needs_review`。
- `tools/verify diagnostic` fresh 通过：111/111 terminal，0 runtime error，0 engineering failure；
  13 张自动批准、98 张 review。Review 根因统计为 placement 60、content veto 19、direct-use budget
  18、local advance 1；该队列的 recognition accuracy 仍是 `not_assessed`。
- 24-source 同一完整 production timing boundary 的提交前预检均值为 4.782 秒，低于 5 秒但余量很小。
  外部 profiling 显示 decode/encode/readback 很小，主要成本是 detector 与 affine ROI sampling；
  正式 performance receipt 必须由 clean commit 的 `tools/verify performance` 生成并绑定其 SHA。
- 物理模型、current-only runtime、轻量普通 report、selected-only output 和两级 Gate 的唯一说明见
  [ARCHITECTURE.md](ARCHITECTURE.md)。

## 开放风险

1. 性能预检距离 5 秒只有约 0.218 秒；应以正式 24-source receipt 的阶段统计决定优化 detector 还是
   sampling，不凭单张样片或 cProfile 放大后的绝对秒数决策。
2. 111 张中 60 张卡在 placement uniqueness，后续应先按 minimum missing fact 分 phase/cross/shared
   根因；diagnostic 没有用户真值，不得为提高自动通过率放松 content veto 或 5%/3%。
3. 中心线仍以共同直线为默认；只有黄金证明真实连续弯曲不可忽略时，才增加少量有直接证据的关系。
4. 任何 tracked 变化都会使 accuracy、diagnostic、performance 与平台证据的 commit identity 失效。

## 下一步

1. 通过正常 hook 提交并推送 current-only 模板对准器；不得 `--no-verify`。
2. 在 clean commit 上生成并校验 24-source performance receipt，检查 mean、RSS、temporary memory 与
   decode/detection/sampling/write/readback 阶段统计；随后运行 platform 验证。
3. 继续用 Debug Analysis 的 observation、理论模板、偏差、winner/runner 与 minimum missing fact 细分
   placement unresolved，不增加格式或样片特判。
4. 全部 release receipt 绑定同一最终 commit 前，不创建 RC、tag、GitHub Release 或公开 ZIP。
