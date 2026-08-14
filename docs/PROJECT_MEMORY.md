# 项目记忆

更新：2026-08-14

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场源码、原 TIFF、
current report、Debug Analysis 和最新命令输出优先。

## 当前目标

保持一条简单、有界的 V5 模板对准路径：format、mode 和 count 先建立固定模板，独立像素证据只负责
对准、解释少量物理偏差和否决危险输出。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- Production 已使用 `TemplateMeasurementPlan → SequenceFit/CrossFit → FormatPlacement → selected-only
  safety`；旧 chain、proposal、materialization、cache 与兼容入口已经删除。
- 最近一次完整行为证据绑定提交 `7095e7ae`：九项黄金均安全，111-source diagnostic 工程闭合，
  24-source 完整路径均值 4.781 秒。后续 tracked 变化不会继承这些 receipt 的发布证明。
- 开发工具只保留正式验证、安装和发布所需入口；不保留没有生产或验证消费者的测量回放路径。

## 开放风险

- 24-source 性能距离 5 秒上限余量较小；下一次优化必须以完整路径分段计时为依据。
- Diagnostic 没有几何真值；它只能证明工程闭合，不能替代黄金准确性。
- 新物理自由度只有在常见、有界、可解释并有独立证据时才能加入。

## 下一步

1. 从 current report 的最小缺失事实统计中选择影响最多的正常失败类型，不为单一样片增加规则。
2. 若准备发布，先冻结最终 runtime，再在同一 commit 重跑 accuracy、diagnostic、performance 和目标
   平台验证；在此之前不创建 RC、tag、Release 或公开 ZIP。
