# 项目记忆

更新：2026-08-13

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，稳定合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 与最新命令输出优先。

## 当前目标

用九项用户确认黄金闭合唯一 V5 fixed-format detector：nominal 必须安全 `approved_auto`，challenge
可以正确批准或安全 `needs_review`，但不得错误自动批准。之后再完成 111-source diagnostic、
24-source performance 与平台证据。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- 本轮已删除无调用者的 report comparator 与旧事务 crash worker；四类 cohort 统一使用当前 count
  authority，platform cohort 不再兼容 `requested_count`；大型 selection、measurement、layout 与
  current-only tests 已按职责拆分。
- Accuracy、diagnostic 与 SHA 计算各有唯一工具 owner；性能、平台和安装 receipt 已升级为唯一 current
  revision，旧 receipt 直接失效。普通生产路径不读取这些验证身份。
- `tools/verify full` 已在本轮最终审计工作树 fresh 通过：220 项通过、2 项环境跳过；configuration 与
  cohort count authority 同时通过。
- 物理模型、current-only runtime、轻量普通 report、selected-only output 和两级 Gate 的已确认合同
  只由 [ARCHITECTURE.md](ARCHITECTURE.md) 说明，不在这里复制。
- 九项黄金 accuracy、111-source diagnostic 与 24-source performance 尚未在最终审计提交上运行。
  因此当前不能声称几何准确性、性能、平台或发布条件已闭合。
- 本地 `main` 尚未推到 `origin/main`；正常 pre-push 需要绑定待推提交的有效 performance receipt。

## 开放风险

1. 黄金可能暴露 edge family、方向、内容 veto 或分轴 authority 的行为问题；只能根据原 TIFF、用户
   baseline 与 current Debug facts 修复，不能放松 5%/3%、增加样片规则或恢复综合评分。
2. 中心线目前以共同直线为默认；只有黄金证明真实连续弯曲不可忽略时，才增加少量有证据的分段约束。
3. 任何 tracked 修复都会使旧 full 结果和 performance receipt 失效；正常 pre-push 仍要求当前提交
   的 performance receipt，不能把人工跳过解释为通过。

## 下一步

1. Fresh 运行九项黄金；按 selected chain、三轴 authority、content veto 与 envelope 逐项修复。
2. 黄金闭合后运行 111-source diagnostic、24-source performance 与平台验证，再通过正常 hook 推送。
3. 全部 release receipt 绑定同一 commit 前，不创建 RC、tag、GitHub Release 或公开 ZIP。
