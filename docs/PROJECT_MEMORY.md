# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

用已确认黄金集改进 V5 的通用检测能力。第一硬目标是危险自动批准为 0；不能通过放宽 Gate、样片特例或
强制 review 隐藏问题。Challenge 是运行前的难度角色，不是预定终态：安全 `approved_auto` 与安全
`needs_review` 都是有效结果，前者应作为新的能力证据保留。

优化顺序固定为：先解决片距稳定、边界直接可见的基础 nominal；再处理弱边缘、片距变化与宽度估计；
最后处理 contact、overlap、浮动残缺序列等 challenge。每一阶段都先保持危险自动批准为 0，再提高
nominal 自动覆盖、速度与 challenge 能力。

## 当前检查点

- 统一黄金 reference 含 106 个唯一 source SHA、110 个显式 count task，均已人工确认；task 角色为
  96 个 nominal、14 个 challenge，优化阶段为 66 / 30 / 14。
- 四组同源多 count 为 S010/S049、S041/S050、S046/S057、S107/S112。它们共用物理 Frame 和边界，
  但分别验证 count 解释与终态。当前 S010/S049、S046/S057 的 candidate 存在跨 count 分歧，其中
  S057 是危险自动批准；前者只作诊断，后者必须修复。
- 当前 detector 源码对照点为 `e0aa5365`：54 个 `approved_auto`、56 个 `needs_review`、20 个危险自动
  批准、47 个 nominal review。完整 development contract 还包含 candidate 几何与 nominal 目标，不能把
  单一通过数称为项目准确率；这些数字只是改进起点。
- 黄金 task 格式覆盖为 `135` 60、`120-66` 32、`120-67` 3、`half` 15；尚无 `xpan`、`120-645`
  或 `135-dual` 黄金 source。
- 当前已查看黄金统一属于 `development_gold`；`development_diagnostic` 只验证工程和报告合同。人工
  确认授予 reference 权限，不授予独立验收资格。当前没有 sealed acceptance 集，不能据此宣称对未见
  X5 扫描的泛化能力或 release readiness。
- V5 仍是 `main` 上唯一 current-only production path，尚未发布；公开稳定版仍为 `v4.2.8`。

## 开放风险

- 最紧急风险是 20 个危险自动批准。必须先区分“像素没有观察到边界”与“已观察但 placement 未采用”，
  再修正通用 observation、binding、solver 或 Gate，不能按 sample ID 补丁。
- 可靠局部边界对最终 canonical crop 的约束仍不足；Grid 应补齐无证据位置，不能覆盖直接证据。多处片距
  小幅变化需要有证据约束的局部锚点，不能引入逐 Frame 无界自由度。
- 片夹遮挡共享 top/bottom 与 TIFF 源截断构成独立短轴难度；只改善 start/end 不足以证明基础能力。
- 现有黄金全部参与开发。未来新 source 必须在查看 detector 结果前按 source SHA 密封；同 SHA 的不同
  count 同分区。任何被解封用于调试的 source 永久转为 development，并补充新的 sealed source。

## 下一步

1. 用 development analysis 分开报告危险自动批准、Review candidate 几何、nominal 自动覆盖和
   challenge 能力，并以 source-bound Debug Analysis 定位基础 nominal 的首个通用机制缺口。
2. 按 66 个基础 nominal → 30 个较难 nominal → 14 个 challenge 的顺序改 detector；每次变更先证明
   不新增危险自动批准，再评估覆盖率与速度。
3. 保留 challenge 的安全 auto 作为能力发现；不建立第二套 detector、特殊 bleed、格式 denylist 或
   样片 whitelist。
4. 准备发布前再建立未见 source 的 sealed acceptance，并在同一 release commit 上取得 accuracy、性能、
   TIFF 与三平台 receipt。
