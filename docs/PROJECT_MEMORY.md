# 项目记忆

更新：2026-08-14

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场源码、原 TIFF、
current report、Debug Analysis 和最新命令输出优先。

## 当前目标

保持一条简单、有界的 V5 模板对准路径：format、mode 和 count 先建立固定模板，独立像素证据只负责
对准、解释少量物理偏差和否决危险输出。继续删除无消费者的接口与重复 owner，不以扩大搜索空间
换取个别异常样片通过。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- Production 已使用 `TemplateMeasurementPlan → SequenceFit/CrossFit → FormatPlacement → selected-only
  safety`；旧 chain、proposal、materialization、cache 与兼容入口已经删除。
- Detector 灰度图按有界行块生成，与原整数组逐像素一致，不再建立整张 float RGB 副本；正式输出
  仍从原始 16-bit RGB 采样。测试和生产代码不保留只为退休接口服务的 helper、type 或 wrapper。
- `tools/verify` 是唯一验证入口。Accuracy、diagnostic、performance 与 platform 各自证明不同事实；
  receipt 只有在其中记录的 commit 与当前 release commit 相同时有效。

## 开放风险

- 24-source 性能上限仍是完整用户路径平均 5 秒；任何后续优化必须以阶段计时和非零 RSS 为依据，
  不为速度改变物理 placement 或内容保护。
- Diagnostic 没有几何真值；它只能证明工程闭合，不能替代黄金准确性。
- 新物理自由度只有在常见、有界、可解释并有独立证据时才能加入。目标平台 receipt 仍须在发布
  commit 上由真实 Intel macOS 与 Windows 文件系统生成。

## 下一步

1. 从 current report 的最小缺失事实统计中选择影响最多的正常失败类型，不为单一样片增加规则。
2. 准备发布时冻结最终 commit，在同一 commit 上重跑 accuracy、diagnostic、performance 和目标平台
   验证；在此之前不创建 RC、tag、Release 或公开 ZIP。
