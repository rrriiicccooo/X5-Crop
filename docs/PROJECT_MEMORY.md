# 项目记忆

更新：2026-08-14

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，稳定合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 与最新命令输出优先。

## 当前目标

完成唯一 V5 current-only 模板对准器：format/count 先编译固定模板，像素只负责对准、解释有限物理
偏差和否决危险输出。九项用户确认黄金必须安全，111-source diagnostic 必须工程闭合，24-source
完整用户路径平均必须不超过 5 秒。V5 尚未发布，公开稳定版仍为 `v4.2.8`。

## 当前检查点

- 旧 chain/proposal/materialization/cache/dominance runtime 与直接依赖测试已删除；production 唯一路径是
  `TemplateMeasurementPlan → SequenceFit/CrossFit → FormatPlacement → selected-only safety`。Phase 与
  cross 的 records、候选构造和编排已有独立 owner；仓库合同限制所有 `template_*.py` 不超过 1000 行，
  并禁止算法模块重导出 canonical records。
- Phase 以 lattice phase、source pitch 和少量有直接证据的 local advance 对齐固定模板；cross 以固定 H、
  role-authorized direct evidence 与共同方向闭合。二维内容只做 negative veto，不移动 placement。
- Debug Analysis 分开显示 role-free observations、完整 winner/best、真正不同的 runner、typed phase
  `winner_basis`、minimum missing fact 与根 DecisionGate；review 的最终输出面板不显示候选 SafeCrop。
- 当前实现的提交前检查通过：`tools/verify full` 为 281 项、2 项环境跳过，13 个 format/mode 与 cohort
  count authority 有效；`tools/verify accuracy` 为 9/9 safe，S027、S035、S051、S062、S091、S094、
  S109 自动批准，S055、S098 安全 review。
- Accuracy、diagnostic、performance 与 platform 的最终事实只以当前 `HEAD` 对应 receipt identity 和
  `tools/verify` 输出为准；本文件不复制会在 tracked 变化后失效的 release 证明。
- 物理模型、current-only runtime、轻量普通 report、selected-only output 和两级 Gate 的唯一说明见
  [ARCHITECTURE.md](ARCHITECTURE.md)。

## 开放风险

1. 最近一次 clean-commit 24-source 均值距离 5 秒余量很小；必须按当前 receipt 的
   decode/measurement/fit/sampling/write/readback 阶段统计决定优化对象，不凭单张样片或 profiler
   放大后的绝对秒数决策。
2. Diagnostic 没有用户真值；后续应按 minimum missing fact 统计 phase/cross/shared/content/budget
   根因，不得为提高自动通过率放松 content veto 或 5%/3%。
3. 中心线仍以共同直线为默认；只有黄金证明真实连续弯曲不可忽略时，才增加少量有直接证据的关系。
4. 任何 tracked 变化都会使 accuracy、diagnostic、performance 与平台证据的 commit identity 失效。

## 下一步

1. 每次开始先核对 current `HEAD`、工作树与 receipt identity；任何 tracked 变化后只接受重新生成的
   `tools/verify` 结果。
2. 继续用 Debug Analysis 的 observation、理论模板、偏差、winner/runner 与 minimum missing fact 细分
   placement unresolved，不增加格式或样片特判。
3. 根据 current 24-source 阶段计时与双预算决定下一项性能工作；工作量稳定而总耗时偏高时优先处理
   TIFF I/O 或 affine ROI sampling，不继续扩张 detector。
4. 全部 release receipt 绑定同一最终 commit 前，不创建 RC、tag、GitHub Release 或公开 ZIP。
