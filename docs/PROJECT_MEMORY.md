# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

用已确认黄金集按三个阶段改进 V5 的通用检测：基础 nominal、较难 nominal、challenge。第一硬目标始终是
危险自动批准为 0；随后才提高 nominal 自动覆盖、速度与 challenge 能力。不能放宽 Gate、强制 review、
增加样片特例或牺牲性能来改善数字。Challenge 是运行前难度角色，不是预定终态；安全 auto 是能力发现，
安全 review 也是合格结果。

## Stage 0 检查点

- 统一黄金 reference 含 106 个唯一 source SHA、110 个显式 count task，均已人工确认；96 个 nominal、
  14 个 challenge，优化分层为 66 / 30 / 14。同源多 count 为 S010/S049、S041/S050、S046/S057、
  S107/S112，共享物理边界但独立验证 count。
- 完整 development gold：110/110 完成、分析错误 0、危险自动批准 0；9 个安全 `approved_auto`、101 个
  `needs_review`。基础 nominal 只有 8/66 安全自动批准，较难 nominal 为 1/30，challenge 14 个均安全
  review。Review candidate 为 67 个不可用、20 个安全、23 个不安全；这些是机制诊断，不是正式危险输出。
- 同源 count 变体没有 candidate safety mismatch；先前 S057 的危险批准已消失。当前安全基线已经建立，
  但基础 nominal 能力远未完成，不能把 0 危险批准解释为 detector 已经准确或可发布。
- Stage 0 已使直接 start/end 的 native observation 成为最终几何 authority；Grid 只补齐缺失角色。每个
  唯一绑定 separator 可约束自己的 local advance，全部关系仍以 O(count) 一次传播。Phase support 按
  物理 lattice location 计数，短轴竞争保存 typed winner basis，横竖 source-axis authority 只映射一次。
- 物理先验诊断按 SHA 去重覆盖 106 个 source：scan-canvas/profile 全部匹配；395 个直接可见 pitch 中
  391 个落在当前 runtime interval。`135`/`half` 的 347 个直接可见 separator gap 只有 20 个落入窄
  gap 先验，证明稳定量是局部 pitch，而非固定 separator 宽度。494 个直接可见 Frame 比例没有一个高于
  catalog 上界；较低值不能反向校准 W/H，因为黄金线是最内侧可接受裁切，不是片门真值。
- 编译后的 top/bottom corridor 对绝大多数 source 包含人工线；5 个 source 存在源边界附近的越界 trace，
  其中包括源截断与极小边缘偏差。它们用于继续验证通用 source-boundary 语义，不能生成样片规则。
- 黄金 unique-source 格式覆盖为 `135` 57、`120-66` 32、`120-67` 3、`half` 14；尚无 `xpan`、
  `120-645` 或 `135-dual`。当前全部为可查看的 `development_gold`，没有 sealed acceptance，不能宣称
  未见 X5 扫描泛化或 release readiness。

## 开放风险与下一步

1. 先把 58 个基础 nominal review 按 phase、cross、direct-use budget 与 source authority 分开。每次只修
   一个通用根因，并复测完整黄金的 0 危险批准；不得把安全的 source 越界或预算 review 改成静默裁小。
2. Cross 的局部 fragment 只能在连接、角色与方向共同证明同一物理 side track 时合并。S004 存在覆盖与
   residual 取舍，说明 support/residual 分数或 Pareto 规则都不足以选边；没有新物理证明就保持 review。
3. 性能仍是独立硬合同：每个候选提交在干净 commit 上运行 24-source 完整用户路径，mean `<= 5s` 阻断，
   `<= 3s` 只作 challenge。黄金 diagnostic 的 2.45s mean 不是正式性能证据。
4. 基础 nominal 稳定后再处理弱边缘、片距变化和宽度估计，最后处理 contact/overlap 等 challenge。未来
   新 source 必须在查看 detector 输出前按 SHA 分为 development 或 sealed；缺失格式只能由真实来源补齐。
