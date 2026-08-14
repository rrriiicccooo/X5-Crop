# 项目记忆

更新：2026-08-14

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场源码、原 TIFF、
current report、Debug Analysis 和最新命令输出优先。

## 当前目标

保持一条简单、有界的 V5 模板对准路径：format、mode 和 count 先建立固定模板，独立像素证据只负责
对准、解释少量物理偏差和否决危险输出。本轮自动修复已经结束；下一步由用户人工检查 fresh Debug
Analysis。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- Production 使用 `TemplateMeasurementPlan → SequenceFit/CrossFit → FormatPlacement → selected-only
  safety`。物理斜率可行性预筛只跳过不可能成立的 edge family，不改变可行候选；内容只在唯一
  placement 后否决。
- 当前验证边界：full 为 284 项、2 项平台 skip；九张黄金 9/9 安全，其中 7 张正确自动批准；
  111-source diagnostic 全部工程闭合，其中 17 张批准、94 张 review；24-source 完整路径平均满足
  5 秒上限且 RSS 非零。
- Review 主因是 `placement_unresolved` 69 张，其次是 direct-use budget 17 张、content protection 7 张
  和 local advance 1 张。Diagnostic 没有几何真值，这些计数只用于确定改进顺序。

## 开放风险

- 剩余 placement review 缺少能够安全区分离散答案的通用硬事实；不得用 support、残差、内容或
  holder center 排名补偿。
- 黄金不得错误自动通过，已经正确批准的样片不得降级；challenge 只有在黄金几何和安全校验都
  通过时才可从 review 升为自动批准。
- 目标平台 receipt 仍须在发布 commit 上由真实 Intel macOS 与 Windows 文件系统生成。

## 下一步

1. 用户检查本轮 111 张 fresh Debug Analysis，确认模板位置、winner/runner、内容否决与根 Gate。
2. 只有人工反馈揭示常见、独立、有界的物理缺失事实时才继续修改；不为单一样片增加规则。
3. 准备发布时再补齐同一 release commit 的目标平台 receipt；在此之前不创建 RC、tag、Release
   或公开 ZIP。
