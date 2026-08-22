# 项目记忆

更新：2026-08-23；源码检查点以本文件所在的 `main` commit 为准。

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前状态

V5 保持一条 current-only、fixed-template-first production path，尚未发布。Deskew 只在安全决定之后
作非阻断的小角度整理；检测 placement 始终在 source axis 上完成。正式性能 Gate 是 24-source 完整
用户路径 mean 不超过 5 秒，3 秒 mean 只是不阻断的 challenge。

## 已验证事实

- `tools/verify full`：408 tests 通过、skip 2；compile、cohort、shell 与 version contract 通过。
- `tools/verify accuracy`：九张 user-confirmed gold 均为 `approved_auto`，9/9 安全；S055、S098 属于
  nominal。
- Fresh `tools/verify diagnostic`：111/111 terminal、工程失败 0，55 张 `approved_auto`、56 张
  `needs_review`，recognition accuracy=`not_assessed`。与审计前 `a8f0844b` 基线逐样片比较，status、
  reason、Gate、placement、phase/cross、slot identity、deskew assessment 和工作量差异均为 0。
- Production 为 150 个 Python 模块、29,918 行；没有达到 1,000 行的模块或 700 行的函数。本轮删除
  3 个 production 模块和 1,148 行 production code，同时移除无消费者工具、旧字段与重复 report state。
- `build/v5-performance/performance_receipt.json` 是性能、未插桩 RSS 与 profiling RSS 的唯一数值
  authority；只有 `git_commit == HEAD` 且 receipt 自校验通过时才有效，任何 tracked 变更都会使它失效。

## 开放风险与下一步

1. 56 张 review 不是准确率失败。下一轮只按 minimum missing fact 和先失败 fixture 优化，不从无真值
   样片反向放宽阈值；错误通过立即停止。
2. Cross/phase 的长度来自仍在支持的物理状态。只有明确退休一种 authority 或能力，且九金与 111 张
   delta 不变，才继续删除对应分支；不做增加接口和总行数的机械拆分。
3. Release 前须让 accuracy、performance、依赖和 Apple Silicon macOS、Intel macOS、Windows x64
   三目标实机 receipt 绑定同一最终 commit；此前不创建 RC、tag、Release 或公开 ZIP。
