# 项目记忆

更新：2026-08-13

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，稳定合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 与最新命令输出始终优先。

## 当前目标

用九项用户确认黄金验证并调试唯一 V5 current-only fixed-format detector；nominal 必须安全
`approved_auto`，challenge 只要求不错误自动批准。准确性闭合后再完成 111-source diagnostic、
24-source performance 与发布前平台证据。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 已落地结构

- Full 表示用户确认匹配片夹的完整铺满布局；partial 表示没有铺满并要求明确
  `1 <= count <= full_count`。Partial 即使 count 相同也没有长轴居中权限。两种模式都默认正常
  间隙，但缺失 separator 只有在 `G_source supported` 时才能补全。
- Source 共享 W/H 与方向族；lane 独立拥有中心线、phase、`G_source` 与异常。Cross、sequence、
  shared authority 分轴成立，任何一轴不能替另一轴补票；选择使用 componentwise Pareto dominance，
  不使用总分、margin 或 top-K。
- 原始 edge 先按 transition identity、位置/方向区间和连续支持形成物理 family。连通 family 只有
  整体共同拟合时才合并，否则保留全部竞争观察。完整直接 separator 通过固定 W 有向邻接路径建立，
  band 仅在左右 edge 实际绑定同一 adjacency 的 end/start 角色时获得一票。
- 便宜的顺序、W/H、方向、authority、重复 observation 与缺失-gap 检查在完整 sampling/report 前
  执行；明显被三轴严格支配的 placement 提前淘汰，不可比较者全部保留。
- 双 lane 在选择前绑定共同 source W/H。选择后的 `CompleteFormatChain` 不再重新求解或重新绑定；
  separator、ordinal、角色、方向、W/H、gap、局部 advance、cross evidence 与边界区间由完整签名
  冻结，输出只增加 sampling 与 selected-only envelope。
- 内容层使用 OpenCV Scharr/structure tensor 与 SciPy topology，只产生候选无关二维 observation；
  placement 层只把可靠跨界解释为负向 veto。只在相邻两边交角发生的局部擦边、锯齿与尘点保持
  中性；内容必须离开角落、跨过完整边界不确定区间并在内外各有连续深度才可否决。
- SciPy `least_squares(loss="huber")` 只拟合已经形成的 edge family，并输出收敛 receipt、残差与
  物理方向区间；优化器不拥有角色或 placement。OpenCV/SciPy 不进入 proposal 投票。
- 旧 `solver.py`、`selection.py`、`measurement.py`、report reuse、旧 schema reader、AUTO、Grid、
  phase-vote、first-N、retained union、minimum guard、平行 detector 与兼容 wrapper 已删除。
  Detector、measurement、content、gap、records、selection、output 与 Debug 面板均有单向小 owner；
  当前生产模块依赖图无循环。
- 经验数值分为物理/产品合同、采样/统计恒等量和具名测量校准。Format gap 只保留在 catalog，
  不再进入 `LaneGapModel`；内容与照片边界各有独立 spec，report 保存其当前值。AST 审计未发现
  未使用生产 import 或参数。
- 普通 runtime 不做文件哈希、依赖 provider 调查、旧 report 复用、磁盘预留或完整像素回读；普通
  report 只保存最终选择和安全结果，完整 observations、chains、ledger 与 work receipt 只在显式
  Debug/验证路径生成。输出只发布到全新目录，已有 target 直接拒绝，不接管或删除用户文件。

## 当前验证事实

- `tools/verify full` 于 2026-08-13 fresh 通过：218 项通过，2 项环境跳过；configuration
  consistency 与 hygiene 同时通过。
- 本轮按用户明确要求人工 override performance，未运行 24-source performance；这不是性能通过，
  也不能生成或替代绑定当前 commit 的 performance receipt。
- 本轮尚未运行九项黄金 accuracy 或 111-source diagnostic，因此不能声称几何准确性闭合、性能达标、
  可发布或可创建 RC/tag/Release。
- 旧的 S027/S094 report、S062/S091/S109 定向结果与 profiler 只作历史线索；源码结构已经变化，
  不得作为当前行为结论。

## 开放风险

1. 黄金仍可能暴露 edge family、方向、内容 veto 或分轴 authority 的真实行为问题；必须按原 TIFF、
   用户 baseline 与 current Debug facts 修复，不能调松 5%/3%、增加样片规则或恢复综合评分。
2. 中心线当前默认共同直线并允许证据约束的小偏移；“重复证据支持的少量连续分段弯曲”尚未需要
   SciPy 约束求解。只有黄金证明直线模型不足时才增加，不能为了使用优化器预先复杂化。
3. 性能和 111-source 工程稳定性尚未在最终提交上验证；performance override 只改变本次推送停点，
   不改变发布 Gate。

## 精确下一步

1. 从 clean `main` 检查本提交与 `origin/main` 一致，随后 fresh 运行九项黄金 accuracy。
2. 对失败项先核对 selected chain、sequence/cross/shared authority、content veto 与 selected-only
   envelope；challenge 可正确批准或安全 review，但不得错误自动批准。
3. 黄金闭合后 fresh 运行 111-source diagnostic 与 24-source performance；任何 tracked 修复都使
   旧 receipt 失效并要求重跑。
4. 全部 release receipt 绑定同一 commit 前，不创建 RC、tag、GitHub Release 或公开 ZIP。
