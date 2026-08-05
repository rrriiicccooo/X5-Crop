# 项目记忆

更新：2026-08-05

这是唯一跨会话检查点，只保存当前目标、已验证检查点、开放风险与精确下一步。当前架构见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。源码、Git、
原 TIFF、current report、Debug Analysis 与现场命令输出始终优先。

## 当前目标

V4.9 已完成 template-first 架构实验使命，不再作为发布目标，也不再要求先修到黄金样片全部
通过。下一生产版本是 V5，直接在 `main` 上 current-only 实现，不创建 V5 开发分支。

V5 使用真正适合生产的像素与数值依赖实现项目目标：不切掉真实内容，同时提高识别覆盖、
边界准确率、安全自动批准率与速度。达到正确性下限后，deskew 优化排在速度之后；减少 blank
TIFF 排在最后，且不得损害任何更高优先级目标。

## V5 冻结方向

- 保留 format/count authority、template-first、source-wide joint geometry、NominalPitch、
  LocalAdvanceRelation、retained placements、MaximumLegalWindow、逐边 5%/3% 与两个 Gate。
- `tifffile + imagecodecs` 独占原 TIFF 解码和写出；NumPy 是统一数据层；OpenCV 只提供有界
  像素测量；SciPy 只提供峰值、拟合、区间与采样等数值原语；Pillow 只服务 Debug Analysis。
- Producer 不恢复 local-line 排名、通用 DP、top-K、width×height 笛卡尔积、逐帧 scale 或
  Hough line-family authority。分数只能选择 canonical，不能删除会改变安全 union 或 legal-
  window intersection 的完整摆放。
- 安全输出必须包含全部 retained full footprints，并位于全部 retained physical
  interpretations 的合法窗口交集内。Canonical 只负责代表 geometry、deskew、minimum guard
  与报告。
- V5 从首个端到端 vertical slice 开始使用 source-SHA-bound 黄金 geometry；只修通用算法，
  不增加样片规则、whitelist 或放宽安全预算。
- 当前所有 capacity slots 都按可能含照片处理。Authoritative blank producer 只作为核心 V5
  闭合后的独立低优先级能力；不确定时继续输出。
- 验证按 pushed paths 分级：纯 Markdown 只检查文档 diff；工具、测试、Hook 与发布配置运行
  full contracts；runtime、依赖或固定性能输入变化才要求 performance receipts。

## 已验证检查点

- Pre-V5 架构 checkpoint 为 `8c8040b0`；V4.9 current-only 替换已推送，旧 producer 与兼容路径
  已删除。
- 非黄金验证通过 81 个 current contracts、13 个配置 format/mode pairs、168-task 固定
  workload、compileall 与 standalone version。
- 111-source 工程诊断完成 111/111 terminal records，runtime、authority、query/template、内存
  与正式 TIFF failure 均为零；accuracy 明确为 `not_assessed`。
- 固定 S062 与 24-source/168-task 性能 receipts、代表性 Debug、中文路径、ZIP manifest、UTF-8
  文件名、CRC 复读与 lane-safe sampling 已通过实验检查点验证。

## 验证边界与开放风险

- 当前源码仍是 V4.9 实验实现；V5 dependency、runtime、schema、黄金 comparator 与发布包均未
  建立。
- V4.9 未读取黄金 accuracy cohort，不能证明真实 detection、placement survival、containment、
  自动批准率或 deskew；这些验证直接转入 V5。
- OpenCV/SciPy 必须带来可测量的准确率、批准率、速度或 deskew 收益，不能只增加包体、启动
  成本或第二套 owner。
- 任何通过丢弃有效竞争、放宽 5%/3%、增加样片阈值、扩大 review 或破坏 TIFF 保真换来的通过
  都无效。

## 精确下一步

1. 在 `main` 建立唯一 V5 runtime/schema 与生产依赖边界，同批删除被替代的 V4.9 实现。
2. 先完成一条 TIFF decode → registered measurement → template placement → safe output → TIFF
   readback 的端到端 vertical slice。
3. 同时建立 current-only V5 黄金 comparator，从第一条 vertical slice 验证真实边界、placement
   survival、containment、5%/3%、批准率与 deskew。
4. 按黄金与固定性能证据扩展全部 format/mode；核心目标闭合后再单独评估 blank producer。
