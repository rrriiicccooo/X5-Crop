# 项目记忆

更新：2026-08-22；源码检查点以本文件所在的 `main` commit 为准。

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前目标

V5 保持一条 current-only fixed-template-first production path，尚未发布。性能、RSS、runtime 状态、
测试工具和文档已完成一次有边界的 minimalism audit；后续通过率只按真实物理根因推进，不从 111 张
无真值样片反向调规则。5 秒 mean 是正式性能 Gate，3 秒 mean 只是 non-blocking challenge。

## 当前证据

- Fresh `tools/verify full`：412 tests 通过、skip 2；compile、configuration、cohort、shell、release
  standalone smoke 与 version contract 全部通过。
- Fresh `tools/verify accuracy`：九张 user-confirmed gold 均为 nominal，9/9 `approved_auto`；S055、
  S098 属于正常能力。
- Fresh `tools/verify diagnostic`：111/111 terminal、工程失败 0，52 张 `approved_auto`、59 张
  `needs_review`，recognition accuracy=`not_assessed`。Review 根因：content 9、direct-use 10、local
  advance 5、placement 19、source-lane 16；phase resolved/ambiguous/unresolved=99/5/7，cross
  resolved/unresolved=97/14。
- Runtime-identical implementation commit `c2c8718f` 的 clean-tree 24-source receipt：mean 3.106
  秒/张、p50 2.587 秒，未插桩 RSS mean 约 0.787 GB、max 约 1.171 GB；5 秒 Gate 通过，3 秒
  challenge 未达到。任何后续 commit 都须重建 receipt；正式结论只读取 `git_commit == HEAD` 的文件。
- Production 净删单字段 report/Gate wrapper 和重复 final state；普通输出只在 approved 后测 deskew，
  并在 TIFF sampling 前释放 registered gray。物理 solver、winner/runner、Gate 和 52/59 分布未改变。

## 开放风险与下一步

1. 59 张 review 不是准确率失败。继续按 minimum missing fact 和 stop-the-line fixture 优化；不用距离、
   强度、holder center 或统一阈值替 placement 选答案。
2. 物理求解仍是主要复杂度。巨大 cross/phase 函数不能靠拆文件变简单；只有明确退休一种 authority
   或能力并通过九金与 111-source delta，才同批删除对应分支和测试。
3. Release 前在同一最终 commit 重建 performance receipt，并取得 Apple Silicon macOS、Intel macOS、
   Windows x64 三份实机 receipt；此前不创建 RC、tag、Release 或公开 ZIP。
